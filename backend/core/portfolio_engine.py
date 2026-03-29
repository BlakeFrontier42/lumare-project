"""
portfolio_engine.py - Portfolio Management and Position Tracking

Tracks all open positions, manages stops/take-profits, and provides
portfolio-level analytics.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol

from backend.core.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class SettingsProvider(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...


class StorageBackend(Protocol):
    def save_position(self, position: dict[str, Any]) -> None: ...
    def load_positions(self) -> list[dict[str, Any]]: ...
    def save_trade_log(self, entry: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"


class CloseReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT_1 = "TAKE_PROFIT_1"
    TAKE_PROFIT_2 = "TAKE_PROFIT_2"
    TAKE_PROFIT_3 = "TAKE_PROFIT_3"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL = "MANUAL"
    KILL_SWITCH = "KILL_SWITCH"
    DRAWDOWN_SHUTDOWN = "DRAWDOWN_SHUTDOWN"
    SIGNAL_EXIT = "SIGNAL_EXIT"
    BREAKEVEN_STOP = "BREAKEVEN_STOP"


@dataclass
class TakeProfitLevel:
    price: float
    fraction: float     # fraction of position to close (e.g. 0.33)
    hit: bool = False
    hit_time: Optional[datetime] = None


@dataclass
class ScaleInEntry:
    """Tracks a scale-in addition to a position."""
    price: float
    size: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""


@dataclass
class Position:
    """Full position representation."""
    position_id: str
    symbol: str
    direction: str              # "long" or "short"
    entry_price: float
    current_price: float
    position_size: float        # total units
    stop_price: float
    initial_stop: float         # never changes - original stop
    take_profits: list[TakeProfitLevel] = field(default_factory=list)
    status: PositionStatus = PositionStatus.OPEN
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    highest_price: float = 0.0  # for trailing stop (long)
    lowest_price: float = 0.0   # for trailing stop (short)
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    close_reason: Optional[CloseReason] = None
    conviction_score: float = 0.0
    regime_at_entry: str = ""
    scale_ins: list[ScaleInEntry] = field(default_factory=list)
    original_size: float = 0.0  # size at entry before any scaling
    breakeven_moved: bool = False
    asset_class: str = "crypto"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "position_size": round(self.position_size, 8),
            "stop_price": self.stop_price,
            "initial_stop": self.initial_stop,
            "take_profits": [
                {"price": tp.price, "fraction": tp.fraction, "hit": tp.hit}
                for tp in self.take_profits
            ],
            "status": self.status.value,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 6),
            "realized_pnl": round(self.realized_pnl, 2),
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "close_reason": self.close_reason.value if self.close_reason else None,
            "conviction_score": self.conviction_score,
            "regime_at_entry": self.regime_at_entry,
            "scale_ins": [
                {"price": s.price, "size": s.size, "timestamp": s.timestamp.isoformat()}
                for s in self.scale_ins
            ],
            "breakeven_moved": self.breakeven_moved,
            "asset_class": self.asset_class,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "portfolio.trailing_stop_activation_pct": 0.02,   # activate trailing after 2% move
    "portfolio.trailing_stop_distance_pct": 0.015,     # trail 1.5% behind
    "portfolio.breakeven_after_tp1": True,
    "portfolio.max_scale_ins": 2,
    "portfolio.scale_in_min_move_pct": 0.01,           # need 1% in favor before scale-in
    "portfolio.default_tp_fractions": [0.33, 0.33, 0.34],  # 3 TP levels
}


# ---------------------------------------------------------------------------
# Portfolio Engine
# ---------------------------------------------------------------------------

class PortfolioEngine:
    """
    Portfolio management and position tracking.

    Manages the lifecycle of all positions: open, update, partial close,
    stop management, take-profit management, and full close.
    """

    def __init__(
        self,
        settings: Optional[SettingsProvider] = None,
        storage: Optional[StorageBackend] = None,
        risk_engine: Optional[RiskEngine] = None,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._risk_engine = risk_engine

        self._positions: dict[str, Position] = {}  # id -> Position
        self._closed_positions: list[Position] = []
        self._total_realized_pnl: float = 0.0

    # ------------------------------------------------------------------
    # Settings helper
    # ------------------------------------------------------------------

    def _cfg(self, key: str) -> Any:
        if self._settings is not None:
            val = self._settings.get(key)
            if val is not None:
                return val
        return DEFAULT_SETTINGS.get(key)

    # ==================================================================
    # POSITION LIFECYCLE
    # ==================================================================

    def add_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        position_size: float,
        stop_price: float,
        take_profit_prices: Optional[list[float]] = None,
        conviction_score: float = 0.0,
        regime: str = "",
        asset_class: str = "crypto",
        tags: Optional[list[str]] = None,
    ) -> Position:
        """Open a new position."""
        position_id = str(uuid.uuid4())[:12]

        # Build take-profit levels
        tp_fractions = self._cfg("portfolio.default_tp_fractions") or [0.33, 0.33, 0.34]
        take_profits: list[TakeProfitLevel] = []
        if take_profit_prices:
            for i, price in enumerate(take_profit_prices):
                frac = tp_fractions[i] if i < len(tp_fractions) else tp_fractions[-1]
                take_profits.append(TakeProfitLevel(price=price, fraction=frac))

        pos = Position(
            position_id=position_id,
            symbol=symbol,
            direction=direction.lower(),
            entry_price=entry_price,
            current_price=entry_price,
            position_size=position_size,
            stop_price=stop_price,
            initial_stop=stop_price,
            take_profits=take_profits,
            highest_price=entry_price,
            lowest_price=entry_price,
            conviction_score=conviction_score,
            regime_at_entry=regime,
            original_size=position_size,
            asset_class=asset_class,
            tags=tags or [],
        )

        self._positions[position_id] = pos

        logger.info(
            "Opened position %s: %s %s %.8f @ %.4f, stop=%.4f",
            position_id, direction, symbol, position_size, entry_price, stop_price,
        )

        if self._storage:
            try:
                self._storage.save_position(pos.to_dict())
            except Exception as exc:
                logger.warning("Failed to persist position: %s", exc)

        return pos

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: CloseReason = CloseReason.MANUAL,
        partial_fraction: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Close (or partially close) a position.

        Parameters
        ----------
        position_id : str
        exit_price : float
        reason : CloseReason
        partial_fraction : float or None
            If provided, close this fraction (0-1) of the position.
        """
        if position_id not in self._positions:
            raise KeyError(f"Position {position_id} not found")

        pos = self._positions[position_id]

        if partial_fraction is not None:
            partial_fraction = max(0.0, min(1.0, partial_fraction))
            close_size = pos.position_size * partial_fraction
        else:
            close_size = pos.position_size

        # Calculate PnL
        if pos.direction == "long":
            pnl = (exit_price - pos.entry_price) * close_size
        else:
            pnl = (pos.entry_price - exit_price) * close_size

        pos.realized_pnl += pnl
        self._total_realized_pnl += pnl

        # Update risk engine daily PnL
        if self._risk_engine:
            self._risk_engine.update_daily_pnl(pnl)

        remaining = pos.position_size - close_size

        result = {
            "position_id": position_id,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "close_size": round(close_size, 8),
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "reason": reason.value,
            "remaining_size": round(remaining, 8),
        }

        if remaining <= 1e-12:
            # Full close
            pos.position_size = 0.0
            pos.status = PositionStatus.CLOSED
            pos.closed_at = datetime.now(timezone.utc)
            pos.close_reason = reason
            self._closed_positions.append(pos)
            del self._positions[position_id]
            logger.info(
                "Closed position %s (%s %s) PnL=%.2f reason=%s",
                position_id, pos.direction, pos.symbol, pnl, reason.value,
            )
        else:
            pos.position_size = remaining
            pos.status = PositionStatus.PARTIALLY_CLOSED
            logger.info(
                "Partially closed %s: %.8f units, PnL=%.2f, remaining=%.8f",
                position_id, close_size, pnl, remaining,
            )

        if self._storage:
            try:
                self._storage.save_trade_log(result)
            except Exception as exc:
                logger.warning("Failed to persist trade log: %s", exc)

        return result

    def get_position(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)

    @property
    def open_positions(self) -> list[Position]:
        return list(self._positions.values())

    @property
    def closed_positions(self) -> list[Position]:
        return list(self._closed_positions)

    # ==================================================================
    # POSITION UPDATES
    # ==================================================================

    def update_positions(self, market_data: dict[str, float]) -> list[dict[str, Any]]:
        """
        Update all positions with current prices.

        Parameters
        ----------
        market_data : dict mapping symbol -> current price

        Returns
        -------
        List of events (stop hits, TP hits, etc.)
        """
        events: list[dict[str, Any]] = []

        for pos_id in list(self._positions.keys()):
            pos = self._positions.get(pos_id)
            if pos is None:
                continue

            price = market_data.get(pos.symbol)
            if price is None:
                continue

            pos.current_price = price

            # Track extremes
            if price > pos.highest_price:
                pos.highest_price = price
            if price < pos.lowest_price or pos.lowest_price == 0:
                pos.lowest_price = price

            # Update unrealised PnL
            if pos.direction == "long":
                pos.unrealized_pnl = (price - pos.entry_price) * pos.position_size
            else:
                pos.unrealized_pnl = (pos.entry_price - price) * pos.position_size

            if pos.entry_price > 0:
                if pos.direction == "long":
                    pos.unrealized_pnl_pct = (price - pos.entry_price) / pos.entry_price
                else:
                    pos.unrealized_pnl_pct = (pos.entry_price - price) / pos.entry_price

        return events

    # ==================================================================
    # STOP MANAGEMENT
    # ==================================================================

    def manage_stops(self, market_data: dict[str, float]) -> list[dict[str, Any]]:
        """
        Trail stops and move to breakeven after TP1.

        Returns list of triggered stop events.
        """
        events: list[dict[str, Any]] = []

        for pos_id in list(self._positions.keys()):
            pos = self._positions.get(pos_id)
            if pos is None:
                continue

            price = market_data.get(pos.symbol)
            if price is None:
                continue

            # -- Check if stop is hit --
            stop_hit = False
            if pos.direction == "long" and price <= pos.stop_price:
                stop_hit = True
            elif pos.direction == "short" and price >= pos.stop_price:
                stop_hit = True

            if stop_hit:
                reason = CloseReason.TRAILING_STOP if pos.breakeven_moved else CloseReason.STOP_LOSS
                result = self.close_position(pos_id, price, reason)
                events.append({"type": "stop_hit", **result})
                continue

            # -- Move to breakeven after TP1 --
            if self._cfg("portfolio.breakeven_after_tp1") and not pos.breakeven_moved:
                tp1_hit = any(tp.hit for tp in pos.take_profits[:1])
                if tp1_hit:
                    # Move stop to entry (breakeven)
                    pos.stop_price = pos.entry_price
                    pos.breakeven_moved = True
                    events.append({
                        "type": "stop_moved_breakeven",
                        "position_id": pos_id,
                        "symbol": pos.symbol,
                        "new_stop": pos.entry_price,
                    })
                    logger.info(
                        "Moved %s stop to breakeven @ %.4f", pos_id, pos.entry_price
                    )

            # -- Trailing stop --
            activation_pct = float(self._cfg("portfolio.trailing_stop_activation_pct"))
            trail_pct = float(self._cfg("portfolio.trailing_stop_distance_pct"))

            if pos.direction == "long":
                move_pct = (pos.highest_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
                if move_pct >= activation_pct:
                    new_stop = pos.highest_price * (1 - trail_pct)
                    if new_stop > pos.stop_price:
                        old_stop = pos.stop_price
                        pos.stop_price = round(new_stop, 8)
                        events.append({
                            "type": "trailing_stop_updated",
                            "position_id": pos_id,
                            "symbol": pos.symbol,
                            "old_stop": old_stop,
                            "new_stop": pos.stop_price,
                        })
            else:  # short
                move_pct = (pos.entry_price - pos.lowest_price) / pos.entry_price if pos.entry_price > 0 else 0
                if move_pct >= activation_pct and pos.lowest_price > 0:
                    new_stop = pos.lowest_price * (1 + trail_pct)
                    if new_stop < pos.stop_price:
                        old_stop = pos.stop_price
                        pos.stop_price = round(new_stop, 8)
                        events.append({
                            "type": "trailing_stop_updated",
                            "position_id": pos_id,
                            "symbol": pos.symbol,
                            "old_stop": old_stop,
                            "new_stop": pos.stop_price,
                        })

        return events

    # ==================================================================
    # TAKE-PROFIT MANAGEMENT
    # ==================================================================

    def manage_take_profits(self, market_data: dict[str, float]) -> list[dict[str, Any]]:
        """
        Check TP levels and execute partial exits.

        Returns list of TP hit events.
        """
        events: list[dict[str, Any]] = []

        for pos_id in list(self._positions.keys()):
            pos = self._positions.get(pos_id)
            if pos is None:
                continue

            price = market_data.get(pos.symbol)
            if price is None:
                continue

            for i, tp in enumerate(pos.take_profits):
                if tp.hit:
                    continue

                hit = False
                if pos.direction == "long" and price >= tp.price:
                    hit = True
                elif pos.direction == "short" and price <= tp.price:
                    hit = True

                if hit:
                    tp.hit = True
                    tp.hit_time = datetime.now(timezone.utc)

                    # Map index to CloseReason
                    reason_map = {
                        0: CloseReason.TAKE_PROFIT_1,
                        1: CloseReason.TAKE_PROFIT_2,
                        2: CloseReason.TAKE_PROFIT_3,
                    }
                    reason = reason_map.get(i, CloseReason.TAKE_PROFIT_3)

                    result = self.close_position(
                        pos_id, price, reason, partial_fraction=tp.fraction
                    )
                    events.append({"type": "take_profit_hit", "tp_level": i + 1, **result})

                    logger.info(
                        "TP%d hit for %s @ %.4f (%.0f%% of position)",
                        i + 1, pos_id, price, tp.fraction * 100,
                    )

                    # Only process one TP per update cycle per position
                    break

        return events

    # ==================================================================
    # SCALE-IN PROTOCOL
    # ==================================================================

    def scale_in(
        self,
        position_id: str,
        additional_size: float,
        price: float,
        reason: str = "scale_in",
    ) -> Optional[dict[str, Any]]:
        """
        Add to an existing position (scale in).

        Checks: max scale-ins, minimum move in our favour.
        """
        pos = self._positions.get(position_id)
        if pos is None:
            logger.warning("Scale-in failed: position %s not found", position_id)
            return None

        max_scale_ins = int(self._cfg("portfolio.max_scale_ins"))
        if len(pos.scale_ins) >= max_scale_ins:
            logger.warning(
                "Scale-in rejected: position %s already has %d scale-ins (max %d)",
                position_id, len(pos.scale_ins), max_scale_ins,
            )
            return None

        # Check minimum move in our favour
        min_move = float(self._cfg("portfolio.scale_in_min_move_pct"))
        if pos.direction == "long":
            current_move = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
        else:
            current_move = (pos.entry_price - price) / pos.entry_price if pos.entry_price > 0 else 0

        if current_move < min_move:
            logger.info(
                "Scale-in rejected: move %.2f%% < required %.2f%%",
                current_move * 100, min_move * 100,
            )
            return None

        # Update average entry price
        total_cost = pos.entry_price * pos.position_size + price * additional_size
        new_total_size = pos.position_size + additional_size
        pos.entry_price = total_cost / new_total_size if new_total_size > 0 else price
        pos.position_size = new_total_size

        pos.scale_ins.append(ScaleInEntry(
            price=price, size=additional_size, reason=reason,
        ))

        logger.info(
            "Scaled into %s: +%.8f @ %.4f, new avg=%.4f, total=%.8f",
            position_id, additional_size, price, pos.entry_price, pos.position_size,
        )

        return {
            "position_id": position_id,
            "symbol": pos.symbol,
            "additional_size": additional_size,
            "scale_in_price": price,
            "new_avg_entry": round(pos.entry_price, 8),
            "new_total_size": round(pos.position_size, 8),
            "scale_in_count": len(pos.scale_ins),
        }

    # ==================================================================
    # PORTFOLIO ANALYTICS
    # ==================================================================

    def get_portfolio_summary(self, portfolio_value: float = 0.0) -> dict[str, Any]:
        """Full portfolio status snapshot."""
        total_unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        total_realized = self._total_realized_pnl

        open_count = len(self._positions)

        # Heat calculation
        heat = 0.0
        if portfolio_value > 0:
            total_risk = 0.0
            for pos in self._positions.values():
                stop_dist = abs(pos.entry_price - pos.stop_price)
                total_risk += stop_dist * pos.position_size
            heat = total_risk / portfolio_value

        return {
            "total_value": round(portfolio_value, 2),
            "open_positions": open_count,
            "unrealized_pnl": round(total_unrealized, 2),
            "realized_pnl": round(total_realized, 2),
            "total_pnl": round(total_unrealized + total_realized, 2),
            "heat": round(heat, 6),
            "positions": [p.to_dict() for p in self._positions.values()],
        }

    def get_exposure_by_asset(self) -> dict[str, float]:
        """Sum of position values grouped by symbol."""
        exposure: dict[str, float] = {}
        for pos in self._positions.values():
            val = pos.position_size * pos.current_price
            exposure[pos.symbol] = exposure.get(pos.symbol, 0.0) + val
        return {k: round(v, 2) for k, v in exposure.items()}

    def get_exposure_by_direction(self) -> dict[str, float]:
        """Aggregate exposure split by long / short."""
        result = {"long": 0.0, "short": 0.0}
        for pos in self._positions.values():
            val = pos.position_size * pos.current_price
            result[pos.direction] = result.get(pos.direction, 0.0) + val
        return {k: round(v, 2) for k, v in result.items()}

    def get_open_position_dicts(self) -> list[dict[str, Any]]:
        """Return lightweight dicts for risk engine consumption."""
        return [
            {
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "stop_price": p.stop_price,
                "current_price": p.current_price,
                "position_size": p.position_size,
            }
            for p in self._positions.values()
        ]
