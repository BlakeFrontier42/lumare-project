"""
risk_engine.py - Institutional-Grade Risk Management

Non-negotiable core. Every trade must pass through this engine.

Enforcement priority (highest first):
1. Kill switch
2. Drawdown shutdown (-15%)
3. Daily loss cap (4%)
4. Drawdown pause (-10%)
5. VaR limit
6. Portfolio heat limit
7. Correlation limit
8. Position size limits
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol

import numpy as np

from backend.core.regime_engine import RegimeState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class StorageBackend(Protocol):
    """Minimal storage interface expected by RiskEngine."""

    def get_daily_pnl(self, day: date) -> float: ...
    def save_daily_pnl(self, day: date, pnl: float) -> None: ...
    def get_equity_curve(self, lookback_days: int) -> list[float]: ...
    def get_kill_switch_state(self) -> dict[str, Any]: ...
    def set_kill_switch_state(self, state: dict[str, Any]) -> None: ...


class SettingsProvider(Protocol):
    """Minimal settings interface."""

    def get(self, key: str, default: Any = None) -> Any: ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class DrawdownLevel(str, Enum):
    NORMAL = "NORMAL"
    PAUSED = "PAUSED"      # -10%
    REDUCED = "REDUCED"    # -12%
    SHUTDOWN = "SHUTDOWN"  # -15%


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskDecision:
    """Result of a trade approval check."""
    approved: bool
    adjusted_size: float
    reason: str
    risk_level: RiskLevel
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "adjusted_size": round(self.adjusted_size, 8),
            "reason": self.reason,
            "risk_level": self.risk_level.value,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "details": self.details,
        }


@dataclass
class TradeProposal:
    """Incoming trade request to be risk-checked."""
    symbol: str
    direction: str           # "long" or "short"
    entry_price: float
    stop_price: float
    conviction_score: float  # 0-100
    regime: RegimeState
    leverage: float = 1.0
    asset_class: str = "crypto"  # "crypto", "equity", "forex"


@dataclass
class PortfolioState:
    """Snapshot of current portfolio for risk evaluation."""
    total_value: float
    open_positions: list[dict[str, Any]]  # list of position dicts
    equity_curve: list[float]
    daily_pnl: float = 0.0
    peak_equity: float = 0.0


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    parametric_var: float
    historical_var: float
    component_var: dict[str, float]
    confidence: float
    horizon_days: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "parametric_var": round(self.parametric_var, 4),
            "historical_var": round(self.historical_var, 4),
            "component_var": {k: round(v, 4) for k, v in self.component_var.items()},
            "confidence": self.confidence,
            "horizon_days": self.horizon_days,
        }


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "risk.base_risk_pct": 0.01,         # 1% base risk per trade
    "risk.min_risk_pct": 0.0075,         # 0.75% minimum
    "risk.max_risk_pct": 0.0125,         # 1.25% maximum
    "risk.max_portfolio_heat": 0.20,     # 20% max capital at risk
    "risk.max_correlated_positions": 3,
    "risk.correlation_threshold": 0.7,
    "risk.correlation_lookback": 30,
    "risk.drawdown_pause": -0.10,        # -10%
    "risk.drawdown_reduce": -0.12,       # -12%
    "risk.drawdown_shutdown": -0.15,     # -15%
    "risk.drawdown_reduce_factor": 0.5,
    "risk.daily_loss_cap": -0.04,        # -4%
    "risk.var_confidence": 0.99,
    "risk.var_limit_pct": 0.05,          # 5% of portfolio
    "risk.max_leverage_crypto": 3.0,
    "risk.max_leverage_equity": 2.0,
    "risk.max_leverage_forex": 10.0,
}


# ---------------------------------------------------------------------------
# Risk Engine
# ---------------------------------------------------------------------------

class RiskEngine:
    """
    Institutional-grade risk management engine.

    Every trade proposal passes through a layered enforcement chain.
    """

    def __init__(
        self,
        settings: Optional[SettingsProvider] = None,
        storage: Optional[StorageBackend] = None,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._kill_switch: bool = False
        self._kill_switch_reason: str = ""
        self._kill_switch_time: Optional[datetime] = None
        self._daily_pnl_cache: dict[str, float] = {}  # "YYYY-MM-DD" -> pnl

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
    # POSITION SIZING
    # ==================================================================

    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_price: float,
        score: float,
        regime: RegimeState,
        leverage: float = 1.0,
        asset_class: str = "crypto",
    ) -> dict[str, Any]:
        """
        ATR-based position sizing.

        risk_amount / abs(entry - stop) = position_size
        """
        if portfolio_value <= 0:
            return self._zero_size("Portfolio value <= 0")
        if entry_price <= 0 or stop_price <= 0:
            return self._zero_size("Invalid price")

        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return self._zero_size("Stop distance is zero")

        # Dynamic risk % based on conviction score (0-100)
        base_risk = float(self._cfg("risk.base_risk_pct"))
        min_risk = float(self._cfg("risk.min_risk_pct"))
        max_risk = float(self._cfg("risk.max_risk_pct"))

        # Linear interpolation: score 50 -> base, 100 -> max, 0 -> min
        if score >= 50:
            risk_pct = base_risk + (max_risk - base_risk) * ((score - 50) / 50)
        else:
            risk_pct = min_risk + (base_risk - min_risk) * (score / 50)

        risk_pct = max(min_risk, min(max_risk, risk_pct))

        # Regime modifier
        from backend.core.regime_engine import RegimeClassifier
        regime_mod = RegimeClassifier.get_position_size_modifier(regime)
        risk_pct *= regime_mod

        risk_amount = portfolio_value * risk_pct

        # Raw position size (in base units)
        position_size = risk_amount / stop_distance

        # Leverage capping
        max_lev = self._max_leverage(asset_class)
        effective_leverage = min(leverage, max_lev)

        # Position value check
        position_value = position_size * entry_price
        max_position_value = portfolio_value * effective_leverage
        if position_value > max_position_value:
            position_size = max_position_value / entry_price

        return {
            "position_size": round(position_size, 8),
            "position_value": round(position_size * entry_price, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_pct": round(risk_pct, 6),
            "stop_distance": round(stop_distance, 8),
            "stop_distance_pct": round(stop_distance / entry_price, 6),
            "regime_modifier": regime_mod,
            "effective_leverage": effective_leverage,
            "entry_price": entry_price,
            "stop_price": stop_price,
        }

    def _max_leverage(self, asset_class: str) -> float:
        mapping = {
            "crypto": "risk.max_leverage_crypto",
            "equity": "risk.max_leverage_equity",
            "forex": "risk.max_leverage_forex",
        }
        key = mapping.get(asset_class, "risk.max_leverage_crypto")
        return float(self._cfg(key))

    @staticmethod
    def _zero_size(reason: str) -> dict[str, Any]:
        return {
            "position_size": 0.0,
            "position_value": 0.0,
            "risk_amount": 0.0,
            "risk_pct": 0.0,
            "stop_distance": 0.0,
            "stop_distance_pct": 0.0,
            "regime_modifier": 0.0,
            "effective_leverage": 0.0,
            "reason": reason,
        }

    # ==================================================================
    # PORTFOLIO HEAT
    # ==================================================================

    def get_portfolio_heat(self, open_positions: list[dict[str, Any]]) -> float:
        """
        Total capital at risk as a fraction of portfolio value.

        Each position contributes: abs(entry - stop) * size / portfolio_value
        """
        if not open_positions:
            return 0.0

        total_risk = 0.0
        for pos in open_positions:
            entry = pos.get("entry_price", 0)
            stop = pos.get("stop_price", 0)
            size = pos.get("position_size", 0)
            if entry and stop and size:
                total_risk += abs(entry - stop) * size

        portfolio_value = sum(
            pos.get("position_size", 0) * pos.get("current_price", pos.get("entry_price", 0))
            for pos in open_positions
        )
        # Use total_value from positions or fallback
        if portfolio_value <= 0:
            return 0.0

        return total_risk / portfolio_value

    def check_portfolio_heat(
        self,
        proposed_trade: dict[str, Any],
        open_positions: list[dict[str, Any]],
        portfolio_value: float,
    ) -> bool:
        """Check if taking this trade would breach the heat limit."""
        current_heat_value = 0.0
        for pos in open_positions:
            entry = pos.get("entry_price", 0)
            stop = pos.get("stop_price", 0)
            size = pos.get("position_size", 0)
            current_heat_value += abs(entry - stop) * size

        new_risk = (
            abs(proposed_trade.get("entry_price", 0) - proposed_trade.get("stop_price", 0))
            * proposed_trade.get("position_size", 0)
        )

        total_risk = current_heat_value + new_risk
        max_heat = float(self._cfg("risk.max_portfolio_heat"))

        return (total_risk / portfolio_value) <= max_heat if portfolio_value > 0 else False

    # ==================================================================
    # CORRELATION CONTROLS
    # ==================================================================

    def calculate_correlation_matrix(
        self,
        returns_by_symbol: dict[str, list[float]],
        lookback: int = 30,
    ) -> dict[str, dict[str, float]]:
        """
        Compute pairwise Pearson correlations from return series.

        Parameters
        ----------
        returns_by_symbol : dict mapping symbol -> list of daily returns
        lookback : number of most recent periods to use

        Returns
        -------
        Nested dict: corr_matrix[sym_a][sym_b] = correlation
        """
        symbols = list(returns_by_symbol.keys())
        n = len(symbols)
        matrix: dict[str, dict[str, float]] = {s: {} for s in symbols}

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[symbols[i]][symbols[j]] = 1.0
                    continue
                a = np.array(returns_by_symbol[symbols[i]][-lookback:], dtype=np.float64)
                b = np.array(returns_by_symbol[symbols[j]][-lookback:], dtype=np.float64)
                min_len = min(len(a), len(b))
                if min_len < 5:
                    matrix[symbols[i]][symbols[j]] = 0.0
                    continue
                a, b = a[-min_len:], b[-min_len:]
                std_a, std_b = np.std(a), np.std(b)
                if std_a == 0 or std_b == 0:
                    matrix[symbols[i]][symbols[j]] = 0.0
                else:
                    corr = float(np.corrcoef(a, b)[0, 1])
                    matrix[symbols[i]][symbols[j]] = round(corr, 4)

        return matrix

    def check_correlation(
        self,
        new_symbol: str,
        open_positions: list[dict[str, Any]],
        returns_by_symbol: dict[str, list[float]],
    ) -> bool:
        """
        Check if adding new_symbol would breach the correlated-positions limit.

        Returns True if the trade is allowed, False if blocked.
        """
        threshold = float(self._cfg("risk.correlation_threshold"))
        max_corr = int(self._cfg("risk.max_correlated_positions"))
        lookback = int(self._cfg("risk.correlation_lookback"))

        if new_symbol not in returns_by_symbol:
            return True  # Can't check - allow (conservative alternative: block)

        correlated_count = 0
        for pos in open_positions:
            sym = pos.get("symbol", "")
            if sym == new_symbol:
                continue
            if sym not in returns_by_symbol:
                continue
            a = np.array(returns_by_symbol[new_symbol][-lookback:], dtype=np.float64)
            b = np.array(returns_by_symbol[sym][-lookback:], dtype=np.float64)
            min_len = min(len(a), len(b))
            if min_len < 5:
                continue
            a, b = a[-min_len:], b[-min_len:]
            std_a, std_b = np.std(a), np.std(b)
            if std_a == 0 or std_b == 0:
                continue
            corr = abs(float(np.corrcoef(a, b)[0, 1]))
            if corr > threshold:
                correlated_count += 1

        return correlated_count < max_corr

    # ==================================================================
    # DRAWDOWN CONTROLS
    # ==================================================================

    def calculate_drawdown(self, equity_curve: list[float]) -> dict[str, Any]:
        """Calculate current and maximum drawdown from equity curve."""
        if not equity_curve or len(equity_curve) < 2:
            return {
                "current_dd": 0.0,
                "max_dd": 0.0,
                "dd_duration": 0,
                "peak_equity": equity_curve[-1] if equity_curve else 0.0,
            }

        arr = np.array(equity_curve, dtype=np.float64)
        running_max = np.maximum.accumulate(arr)
        drawdowns = (arr - running_max) / np.where(running_max > 0, running_max, 1.0)

        current_dd = float(drawdowns[-1])
        max_dd = float(np.min(drawdowns))

        # Duration: bars since last peak
        peak_idx = int(np.argmax(arr))
        dd_duration = len(arr) - 1 - peak_idx if peak_idx < len(arr) - 1 else 0

        return {
            "current_dd": round(current_dd, 6),
            "max_dd": round(max_dd, 6),
            "dd_duration": dd_duration,
            "peak_equity": round(float(running_max[-1]), 2),
        }

    def check_drawdown_breaker(self, current_drawdown: float) -> DrawdownLevel:
        """
        Determine drawdown level. current_drawdown is negative (e.g., -0.12).
        """
        shutdown = float(self._cfg("risk.drawdown_shutdown"))
        reduce = float(self._cfg("risk.drawdown_reduce"))
        pause = float(self._cfg("risk.drawdown_pause"))

        if current_drawdown <= shutdown:
            return DrawdownLevel.SHUTDOWN
        if current_drawdown <= reduce:
            return DrawdownLevel.REDUCED
        if current_drawdown <= pause:
            return DrawdownLevel.PAUSED
        return DrawdownLevel.NORMAL

    # ==================================================================
    # VALUE AT RISK
    # ==================================================================

    def calculate_var(
        self,
        portfolio_returns: list[float],
        position_values: Optional[dict[str, float]] = None,
        confidence: float = 0.99,
    ) -> VaRResult:
        """
        Compute parametric and historical VaR.

        Parameters
        ----------
        portfolio_returns : list of daily portfolio returns
        position_values : dict of symbol -> current position value (for component VaR)
        confidence : confidence level (default 0.99)
        """
        if not portfolio_returns or len(portfolio_returns) < 10:
            return VaRResult(
                parametric_var=0.0,
                historical_var=0.0,
                component_var={},
                confidence=confidence,
            )

        returns = np.array(portfolio_returns, dtype=np.float64)

        # Parametric VaR (assumes normal distribution)
        mu = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))
        z_score = self._norm_ppf(confidence)
        parametric_var = abs(mu - z_score * sigma)

        # Historical VaR
        sorted_returns = np.sort(returns)
        idx = int(len(sorted_returns) * (1 - confidence))
        historical_var = abs(float(sorted_returns[idx]))

        # Component VaR (proportional allocation)
        component_var: dict[str, float] = {}
        if position_values:
            total_val = sum(abs(v) for v in position_values.values())
            if total_val > 0:
                for sym, val in position_values.items():
                    weight = abs(val) / total_val
                    component_var[sym] = round(parametric_var * weight, 6)

        return VaRResult(
            parametric_var=round(parametric_var, 6),
            historical_var=round(historical_var, 6),
            component_var=component_var,
            confidence=confidence,
        )

    def check_var_limit(
        self,
        portfolio_returns: list[float],
        portfolio_value: float,
    ) -> bool:
        """Return True if VaR is within acceptable limit."""
        var_result = self.calculate_var(portfolio_returns)
        limit = float(self._cfg("risk.var_limit_pct"))
        return var_result.parametric_var <= limit

    @staticmethod
    def _norm_ppf(confidence: float) -> float:
        """Approximate inverse normal CDF (good enough for 0.95-0.99)."""
        # Rational approximation (Abramowitz & Stegun 26.2.23)
        p = 1.0 - confidence
        if p <= 0 or p >= 1:
            return 2.326  # fallback ~99%
        t = math.sqrt(-2.0 * math.log(p))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        return t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t ** 3)

    # ==================================================================
    # DAILY LOSS TRACKING
    # ==================================================================

    def get_daily_pnl(self, portfolio_value: float = 0.0) -> float:
        """Get today's PnL as a fraction of portfolio value."""
        today_key = date.today().isoformat()
        if today_key in self._daily_pnl_cache:
            pnl = self._daily_pnl_cache[today_key]
            return pnl / portfolio_value if portfolio_value > 0 else 0.0

        if self._storage is not None:
            try:
                pnl = self._storage.get_daily_pnl(date.today())
                self._daily_pnl_cache[today_key] = pnl
                return pnl / portfolio_value if portfolio_value > 0 else 0.0
            except Exception:
                pass
        return 0.0

    def update_daily_pnl(self, pnl_change: float) -> None:
        """Accumulate PnL for today."""
        today_key = date.today().isoformat()
        current = self._daily_pnl_cache.get(today_key, 0.0)
        self._daily_pnl_cache[today_key] = current + pnl_change

    def check_daily_loss_cap(self, portfolio_value: float) -> bool:
        """Return True if daily loss is within the cap (trading allowed)."""
        daily_pnl_pct = self.get_daily_pnl(portfolio_value)
        cap = float(self._cfg("risk.daily_loss_cap"))
        return daily_pnl_pct >= cap  # cap is negative, so pnl must be >= cap

    # ==================================================================
    # KILL SWITCH
    # ==================================================================

    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def activate_kill_switch(self, reason: str) -> None:
        self._kill_switch = True
        self._kill_switch_reason = reason
        self._kill_switch_time = datetime.now(timezone.utc)
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

        if self._storage is not None:
            try:
                self._storage.set_kill_switch_state({
                    "active": True,
                    "reason": reason,
                    "timestamp": self._kill_switch_time.isoformat(),
                })
            except Exception:
                pass

    def deactivate_kill_switch(self) -> None:
        logger.warning(
            "Kill switch deactivated (was active since %s: %s)",
            self._kill_switch_time, self._kill_switch_reason,
        )
        self._kill_switch = False
        self._kill_switch_reason = ""
        self._kill_switch_time = None

        if self._storage is not None:
            try:
                self._storage.set_kill_switch_state({"active": False})
            except Exception:
                pass

    # ==================================================================
    # MASTER APPROVAL
    # ==================================================================

    def approve_trade(
        self,
        trade: TradeProposal,
        portfolio: PortfolioState,
        returns_by_symbol: Optional[dict[str, list[float]]] = None,
        portfolio_returns: Optional[list[float]] = None,
    ) -> RiskDecision:
        """
        Run the full enforcement chain.

        Enforcement order:
        1. Kill switch
        2. Drawdown shutdown (-15%)
        3. Daily loss cap (4%)
        4. Drawdown pause (-10%)
        5. VaR limit
        6. Portfolio heat limit
        7. Correlation limit
        8. Position size limits
        """
        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, Any] = {}

        # ---- 1. Kill switch ----
        if self._kill_switch:
            return RiskDecision(
                approved=False,
                adjusted_size=0.0,
                reason=f"Kill switch active: {self._kill_switch_reason}",
                risk_level=RiskLevel.CRITICAL,
                checks_failed=["kill_switch"],
                details={"kill_switch_reason": self._kill_switch_reason},
            )
        passed.append("kill_switch")

        # ---- 2 & 4. Drawdown ----
        dd_info = self.calculate_drawdown(portfolio.equity_curve)
        dd_level = self.check_drawdown_breaker(dd_info["current_dd"])
        details["drawdown"] = dd_info
        details["drawdown_level"] = dd_level.value

        if dd_level == DrawdownLevel.SHUTDOWN:
            self.activate_kill_switch(
                f"Drawdown shutdown triggered: {dd_info['current_dd']:.2%}"
            )
            return RiskDecision(
                approved=False,
                adjusted_size=0.0,
                reason=f"Drawdown shutdown at {dd_info['current_dd']:.2%}",
                risk_level=RiskLevel.CRITICAL,
                checks_passed=passed,
                checks_failed=["drawdown_shutdown"],
                details=details,
            )
        passed.append("drawdown_shutdown")

        # ---- 3. Daily loss cap ----
        if not self.check_daily_loss_cap(portfolio.total_value):
            return RiskDecision(
                approved=False,
                adjusted_size=0.0,
                reason="Daily loss cap breached",
                risk_level=RiskLevel.CRITICAL,
                checks_passed=passed,
                checks_failed=["daily_loss_cap"],
                details=details,
            )
        passed.append("daily_loss_cap")

        # ---- 4. Drawdown pause ----
        if dd_level == DrawdownLevel.PAUSED:
            return RiskDecision(
                approved=False,
                adjusted_size=0.0,
                reason=f"Trading paused: drawdown at {dd_info['current_dd']:.2%}",
                risk_level=RiskLevel.HIGH,
                checks_passed=passed,
                checks_failed=["drawdown_pause"],
                details=details,
            )
        passed.append("drawdown_pause")

        # Size reduction for REDUCED drawdown level
        dd_size_factor = 1.0
        if dd_level == DrawdownLevel.REDUCED:
            dd_size_factor = float(self._cfg("risk.drawdown_reduce_factor"))
            details["drawdown_size_factor"] = dd_size_factor

        # ---- 5. VaR limit ----
        if portfolio_returns and len(portfolio_returns) >= 10:
            if not self.check_var_limit(portfolio_returns, portfolio.total_value):
                return RiskDecision(
                    approved=False,
                    adjusted_size=0.0,
                    reason="VaR limit exceeded",
                    risk_level=RiskLevel.HIGH,
                    checks_passed=passed,
                    checks_failed=["var_limit"],
                    details=details,
                )
        passed.append("var_limit")

        # ---- Calculate position size ----
        sizing = self.calculate_position_size(
            portfolio_value=portfolio.total_value,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            score=trade.conviction_score,
            regime=trade.regime,
            leverage=trade.leverage,
            asset_class=trade.asset_class,
        )
        details["sizing"] = sizing

        raw_size = sizing["position_size"]
        adjusted_size = raw_size * dd_size_factor

        # ---- 6. Portfolio heat ----
        proposed = {
            "entry_price": trade.entry_price,
            "stop_price": trade.stop_price,
            "position_size": adjusted_size,
        }
        if not self.check_portfolio_heat(
            proposed, portfolio.open_positions, portfolio.total_value
        ):
            failed.append("portfolio_heat")
            return RiskDecision(
                approved=False,
                adjusted_size=0.0,
                reason="Portfolio heat limit would be breached",
                risk_level=RiskLevel.HIGH,
                checks_passed=passed,
                checks_failed=failed,
                details=details,
            )
        passed.append("portfolio_heat")

        # ---- 7. Correlation limit ----
        if returns_by_symbol is not None:
            if not self.check_correlation(
                trade.symbol, portfolio.open_positions, returns_by_symbol
            ):
                failed.append("correlation_limit")
                return RiskDecision(
                    approved=False,
                    adjusted_size=0.0,
                    reason=f"Too many correlated positions for {trade.symbol}",
                    risk_level=RiskLevel.MEDIUM,
                    checks_passed=passed,
                    checks_failed=failed,
                    details=details,
                )
        passed.append("correlation_limit")

        # ---- 8. Position size limits (already enforced in calculate_position_size) ----
        passed.append("position_size_limits")

        # Determine risk level
        if dd_level == DrawdownLevel.REDUCED:
            risk_level = RiskLevel.HIGH
        elif dd_info["current_dd"] < -0.05:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        return RiskDecision(
            approved=True,
            adjusted_size=round(adjusted_size, 8),
            reason="All risk checks passed",
            risk_level=risk_level,
            checks_passed=passed,
            details=details,
        )
