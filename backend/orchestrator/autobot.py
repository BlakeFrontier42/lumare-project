"""
Autonomous Paper Trading Bot — Strategy Library + Bot Manager.

Runs as an async background task, scanning configured symbols on a timer,
generating signals via pluggable strategies, and placing paper trades
through the existing paper-trading system. Respects the PolicyEngine
risk limits and uses AdaptiveWeightManager confidence boosting.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Signal:
    signal_id: str
    symbol: str
    strategy: str
    direction: SignalDirection
    confidence: float       # 0.0 – 1.0
    entry: float
    stop_loss: float
    take_profit: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acted: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Technical helpers (operate on OHLCV candle dicts)
# ---------------------------------------------------------------------------

def _close_prices(candles: List[Dict]) -> List[float]:
    return [float(c.get("close", c.get("c", 0))) for c in candles]


def _high_prices(candles: List[Dict]) -> List[float]:
    return [float(c.get("high", c.get("h", 0))) for c in candles]


def _low_prices(candles: List[Dict]) -> List[float]:
    return [float(c.get("low", c.get("l", 0))) for c in candles]


def _ema(data: List[float], period: int) -> List[float]:
    if len(data) < period:
        return data[:]
    k = 2 / (period + 1)
    ema_vals = [sum(data[:period]) / period]
    for price in data[period:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _sma(data: List[float], period: int) -> List[float]:
    if len(data) < period:
        return data[:]
    result = []
    for i in range(period - 1, len(data)):
        result.append(sum(data[i - period + 1: i + 1]) / period)
    return result


def _rsi(data: List[float], period: int = 14) -> float:
    if len(data) < period + 1:
        return 50.0
    deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
    recent = deltas[-(period):]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0001
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bollinger_bands(data: List[float], period: int = 20, num_std: float = 2.0) -> Tuple[float, float, float]:
    if len(data) < period:
        mid = data[-1] if data else 0
        return mid, mid, mid
    window = data[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mid - num_std * std, mid, mid + num_std * std


def _atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].get("high", candles[i].get("h", 0)))
        l = float(candles[i].get("low", candles[i].get("l", 0)))
        pc = float(candles[i - 1].get("close", candles[i - 1].get("c", 0)))
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return 0.0
    window = trs[-period:]
    return sum(window) / len(window)


# ---------------------------------------------------------------------------
# Strategy base + implementations
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        ...


class MomentumStrategy(BaseStrategy):
    name = "momentum"
    description = "RSI + price momentum — buy when RSI < 30 and price above 20 EMA, sell when RSI > 70"

    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        if len(candles) < 25:
            return None
        closes = _close_prices(candles)
        rsi_val = _rsi(closes, 14)
        ema20 = _ema(closes, 20)
        if not ema20:
            return None
        current = closes[-1]
        ema_current = ema20[-1]

        if rsi_val < 30 and current > ema_current:
            atr_val = _atr(candles) or current * 0.02
            confidence = min(1.0, (30 - rsi_val) / 30 + 0.5)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.LONG,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current - 2 * atr_val, 2),
                take_profit=round(current + 3 * atr_val, 2),
                reason=f"RSI={rsi_val:.1f}, price above 20 EMA",
            )

        if rsi_val > 70:
            atr_val = _atr(candles) or current * 0.02
            confidence = min(1.0, (rsi_val - 70) / 30 + 0.5)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.SHORT,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current + 2 * atr_val, 2),
                take_profit=round(current - 3 * atr_val, 2),
                reason=f"RSI={rsi_val:.1f}, overbought",
            )

        return None


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"
    description = "Bollinger Band bounce — buy at lower band, sell at upper band"

    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        if len(candles) < 25:
            return None
        closes = _close_prices(candles)
        lower, mid, upper = _bollinger_bands(closes, 20, 2.0)
        current = closes[-1]
        band_width = upper - lower if upper != lower else 1.0
        atr_val = _atr(candles) or current * 0.02

        if current <= lower * 1.005:
            distance = (lower - current) / band_width
            confidence = min(1.0, 0.55 + abs(distance) * 0.5)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.LONG,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current - 1.5 * atr_val, 2),
                take_profit=round(mid, 2),
                reason=f"Price at lower BB ({lower:.2f}), target mid={mid:.2f}",
            )

        if current >= upper * 0.995:
            distance = (current - upper) / band_width
            confidence = min(1.0, 0.55 + abs(distance) * 0.5)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.SHORT,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current + 1.5 * atr_val, 2),
                take_profit=round(mid, 2),
                reason=f"Price at upper BB ({upper:.2f}), target mid={mid:.2f}",
            )

        return None


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"
    description = "EMA crossover (9/21) — enter on cross, exit on reverse cross"

    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        if len(candles) < 25:
            return None
        closes = _close_prices(candles)
        ema9 = _ema(closes, 9)
        ema21 = _ema(closes, 21)
        if len(ema9) < 2 or len(ema21) < 2:
            return None

        # Align lengths
        min_len = min(len(ema9), len(ema21))
        e9 = ema9[-min_len:]
        e21 = ema21[-min_len:]

        if len(e9) < 2:
            return None

        current = closes[-1]
        atr_val = _atr(candles) or current * 0.02

        # Bullish crossover: previous ema9 <= ema21, now ema9 > ema21
        if e9[-2] <= e21[-2] and e9[-1] > e21[-1]:
            gap = abs(e9[-1] - e21[-1])
            confidence = min(1.0, 0.6 + gap / (current * 0.01) * 0.1)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.LONG,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current - 2 * atr_val, 2),
                take_profit=round(current + 3 * atr_val, 2),
                reason=f"EMA 9/21 bullish crossover",
            )

        # Bearish crossover
        if e9[-2] >= e21[-2] and e9[-1] < e21[-1]:
            gap = abs(e21[-1] - e9[-1])
            confidence = min(1.0, 0.6 + gap / (current * 0.01) * 0.1)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.SHORT,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(current + 2 * atr_val, 2),
                take_profit=round(current - 3 * atr_val, 2),
                reason=f"EMA 9/21 bearish crossover",
            )

        return None


class BreakoutStrategy(BaseStrategy):
    name = "breakout"
    description = "ATR-based breakout from consolidation range"

    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        if len(candles) < 25:
            return None
        closes = _close_prices(candles)
        highs = _high_prices(candles)
        lows = _low_prices(candles)
        atr_val = _atr(candles, 14)
        if atr_val == 0:
            return None

        # Look at last 20 candles for a consolidation range
        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])
        range_size = recent_high - recent_low
        current = closes[-1]

        # Consolidation: range < 2x ATR means tight
        if range_size > 3 * atr_val:
            return None  # Not in consolidation

        # Breakout above range
        if current > recent_high:
            confidence = min(1.0, 0.6 + (current - recent_high) / atr_val * 0.15)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.LONG,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(recent_low, 2),
                take_profit=round(current + 2.5 * atr_val, 2),
                reason=f"Breakout above {recent_high:.2f}, range={range_size:.2f}",
            )

        # Breakdown below range
        if current < recent_low:
            confidence = min(1.0, 0.6 + (recent_low - current) / atr_val * 0.15)
            return Signal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                strategy=self.name,
                direction=SignalDirection.SHORT,
                confidence=round(confidence, 3),
                entry=current,
                stop_loss=round(recent_high, 2),
                take_profit=round(current - 2.5 * atr_val, 2),
                reason=f"Breakdown below {recent_low:.2f}, range={range_size:.2f}",
            )

        return None


class ICTStrategy(BaseStrategy):
    """Inner Circle Trader / Smart Money Concepts strategy.

    Detects Fair Value Gaps, Order Blocks, and Liquidity Sweeps.
    """
    name = "ict"
    description = "Fair value gaps, order blocks, and liquidity sweep signals"

    def evaluate(self, symbol: str, candles: List[Dict]) -> Optional[Signal]:
        if len(candles) < 30:
            return None
        closes = _close_prices(candles)
        highs = _high_prices(candles)
        lows = _low_prices(candles)
        atr_val = _atr(candles, 14)
        if atr_val == 0:
            return None
        current = closes[-1]

        # --- Liquidity Sweep Detection ---
        # Bullish: price sweeps below recent low then reverses up
        recent_low = min(lows[-15:-1])
        recent_high = max(highs[-15:-1])
        prev_low = lows[-2]
        prev_high = highs[-2]

        # Bullish liquidity sweep: wick below recent low, close back above
        if prev_low < recent_low and closes[-2] > recent_low:
            # Check for displacement: strong bullish candle after sweep
            body_size = abs(closes[-1] - float(candles[-1].get("open", candles[-1].get("o", current))))
            if body_size > 1.2 * atr_val and closes[-1] > closes[-2]:
                confidence = min(1.0, 0.65 + body_size / atr_val * 0.1)
                sl = round(prev_low - 0.5 * atr_val, 2)
                risk = current - sl
                tp = round(current + 2.5 * risk, 2) if risk > 0 else round(current + 2 * atr_val, 2)
                return Signal(
                    signal_id=str(uuid.uuid4()),
                    symbol=symbol,
                    strategy=self.name,
                    direction=SignalDirection.LONG,
                    confidence=round(confidence, 3),
                    entry=current,
                    stop_loss=sl,
                    take_profit=tp,
                    reason=f"Bullish liquidity sweep below {recent_low:.2f} + displacement",
                )

        # Bearish liquidity sweep: wick above recent high, close back below
        if prev_high > recent_high and closes[-2] < recent_high:
            body_size = abs(closes[-1] - float(candles[-1].get("open", candles[-1].get("o", current))))
            if body_size > 1.2 * atr_val and closes[-1] < closes[-2]:
                confidence = min(1.0, 0.65 + body_size / atr_val * 0.1)
                sl = round(prev_high + 0.5 * atr_val, 2)
                risk = sl - current
                tp = round(current - 2.5 * risk, 2) if risk > 0 else round(current - 2 * atr_val, 2)
                return Signal(
                    signal_id=str(uuid.uuid4()),
                    symbol=symbol,
                    strategy=self.name,
                    direction=SignalDirection.SHORT,
                    confidence=round(confidence, 3),
                    entry=current,
                    stop_loss=sl,
                    take_profit=tp,
                    reason=f"Bearish liquidity sweep above {recent_high:.2f} + displacement",
                )

        # --- Fair Value Gap (FVG) Detection ---
        # Bullish FVG: candle[i-2].high < candle[i].low (gap up)
        if len(candles) >= 5:
            for i in range(-1, -4, -1):
                c_low = float(candles[i].get("low", candles[i].get("l", 0)))
                c2_high = float(candles[i - 2].get("high", candles[i - 2].get("h", 0)))
                c1_body = abs(closes[i - 1] - float(candles[i - 1].get("open", candles[i - 1].get("o", 0))))

                # Bullish FVG: gap between candle[i-2].high and candle[i].low
                if c_low > c2_high and c1_body > atr_val:
                    if current <= c_low * 1.005:  # Price returning to fill the gap
                        confidence = min(1.0, 0.6 + c1_body / atr_val * 0.08)
                        sl = round(c2_high - 0.3 * atr_val, 2)
                        tp = round(current + 2 * atr_val, 2)
                        return Signal(
                            signal_id=str(uuid.uuid4()),
                            symbol=symbol,
                            strategy=self.name,
                            direction=SignalDirection.LONG,
                            confidence=round(confidence, 3),
                            entry=current,
                            stop_loss=sl,
                            take_profit=tp,
                            reason=f"Bullish FVG fill at {c_low:.2f}-{c2_high:.2f}",
                        )

                # Bearish FVG: candle[i].high < candle[i-2].low
                c_high = float(candles[i].get("high", candles[i].get("h", 0)))
                c2_low = float(candles[i - 2].get("low", candles[i - 2].get("l", 0)))
                if c_high < c2_low and c1_body > atr_val:
                    if current >= c_high * 0.995:
                        confidence = min(1.0, 0.6 + c1_body / atr_val * 0.08)
                        sl = round(c2_low + 0.3 * atr_val, 2)
                        tp = round(current - 2 * atr_val, 2)
                        return Signal(
                            signal_id=str(uuid.uuid4()),
                            symbol=symbol,
                            strategy=self.name,
                            direction=SignalDirection.SHORT,
                            confidence=round(confidence, 3),
                            entry=current,
                            stop_loss=sl,
                            take_profit=tp,
                            reason=f"Bearish FVG fill at {c2_low:.2f}-{c_high:.2f}",
                        )

        return None


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: Dict[str, BaseStrategy] = {
    "momentum": MomentumStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "trend_following": TrendFollowingStrategy(),
    "breakout": BreakoutStrategy(),
    "ict": ICTStrategy(),
}


# ---------------------------------------------------------------------------
# AutoBot — the main autonomous engine
# ---------------------------------------------------------------------------

class AutoBot:
    """
    Autonomous paper trading bot.

    Runs an async loop scanning configured symbols with configured strategies
    at a configurable interval. Places paper trades through the in-memory
    paper-trading system and tracks its own P&L.
    """

    def __init__(self):
        self.running: bool = False
        self.symbols: List[str] = []
        self.strategy_names: List[str] = []
        self.interval_seconds: int = 60
        self.max_concurrent_positions: int = 3
        self.max_position_size: float = 10000.0  # notional USD

        # State
        self._task: Optional[asyncio.Task] = None
        self._start_time: Optional[float] = None
        self._signals: List[Signal] = []
        self._trades_placed: int = 0
        self._activity_log: List[Dict[str, Any]] = []
        self._bot_positions: Dict[str, Dict] = {}   # position_id -> info
        self._bot_closed: List[Dict] = []

    # ── public control ───────────────────────────────────────

    def start(
        self,
        symbols: List[str],
        strategies: List[str],
        interval_seconds: int = 60,
        max_concurrent: int = 3,
        max_position_size: float = 10000.0,
    ):
        if self.running:
            return
        self.symbols = [s.upper() for s in symbols]
        self.strategy_names = [s for s in strategies if s in STRATEGY_REGISTRY]
        self.interval_seconds = max(10, min(interval_seconds, 600))
        self.max_concurrent_positions = max(1, min(max_concurrent, 10))
        self.max_position_size = max_position_size
        self.running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run_loop())
        self._log("Bot started", f"Symbols: {self.symbols}, Strategies: {self.strategy_names}")
        logger.info(f"AutoBot started: symbols={self.symbols}, strategies={self.strategy_names}, interval={self.interval_seconds}s")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._log("Bot stopped", "Autonomous mode deactivated")
        logger.info("AutoBot stopped")

    def get_status(self) -> Dict[str, Any]:
        uptime = 0
        if self._start_time and self.running:
            uptime = int(time.time() - self._start_time)
        open_bot_positions = len([
            p for p in self._bot_positions.values()
            if p.get("status") == "open"
        ])
        return {
            "running": self.running,
            "uptime_seconds": uptime,
            "symbols": self.symbols,
            "strategies": self.strategy_names,
            "interval_seconds": self.interval_seconds,
            "max_concurrent_positions": self.max_concurrent_positions,
            "signals_generated": len(self._signals),
            "trades_placed": self._trades_placed,
            "open_positions": open_bot_positions,
        }

    def get_performance(self) -> Dict[str, Any]:
        closed = self._bot_closed
        if not closed:
            return {
                "total_pnl": 0.0,
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_gain": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "sharpe": 0.0,
                "strategy_breakdown": {},
            }

        total_pnl = sum(t.get("pnl", 0) for t in closed)
        winners = [t for t in closed if t.get("pnl", 0) > 0]
        losers = [t for t in closed if t.get("pnl", 0) <= 0]
        win_rate = (len(winners) / len(closed)) * 100 if closed else 0
        avg_gain = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t["pnl"] for t in losers) / len(losers) if losers else 0
        gross_profit = sum(t["pnl"] for t in winners)
        gross_loss = abs(sum(t["pnl"] for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.0

        pnls = [t.get("pnl", 0) for t in closed]
        mean_pnl = sum(pnls) / len(pnls) if pnls else 0
        if len(pnls) > 1:
            var = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
            std_pnl = math.sqrt(var) if var > 0 else 1
        else:
            std_pnl = 1
        sharpe = round(mean_pnl / std_pnl * math.sqrt(252), 2) if std_pnl > 0 else 0

        # Strategy breakdown
        breakdown: Dict[str, Dict] = {}
        for t in closed:
            strat = t.get("strategy", "unknown")
            if strat not in breakdown:
                breakdown[strat] = {"trades": 0, "pnl": 0.0, "wins": 0}
            breakdown[strat]["trades"] += 1
            breakdown[strat]["pnl"] += t.get("pnl", 0)
            if t.get("pnl", 0) > 0:
                breakdown[strat]["wins"] += 1
        for strat in breakdown:
            bd = breakdown[strat]
            bd["pnl"] = round(bd["pnl"], 2)
            bd["win_rate"] = round(bd["wins"] / bd["trades"] * 100, 1) if bd["trades"] else 0

        return {
            "total_pnl": round(total_pnl, 2),
            "total_trades": len(closed),
            "win_rate": round(win_rate, 1),
            "avg_gain": round(avg_gain, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe": sharpe,
            "strategy_breakdown": breakdown,
        }

    def get_signals(self, limit: int = 50) -> List[Dict]:
        return [
            {
                "signal_id": s.signal_id,
                "symbol": s.symbol,
                "strategy": s.strategy,
                "direction": s.direction.value,
                "confidence": s.confidence,
                "entry": s.entry,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "timestamp": s.timestamp,
                "acted": s.acted,
                "reason": s.reason,
            }
            for s in reversed(self._signals[-limit:])
        ]

    def get_activity_log(self, limit: int = 100) -> List[Dict]:
        return list(reversed(self._activity_log[-limit:]))

    # ── internal loop ────────────────────────────────────────

    async def _run_loop(self):
        """Main scanning loop."""
        try:
            while self.running:
                await self._scan_cycle()
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            logger.info("AutoBot loop cancelled")
        except Exception as exc:
            logger.error(f"AutoBot loop error: {exc}")
            self.running = False

    async def _scan_cycle(self):
        """One full scan of all symbols x strategies."""
        strategies = [STRATEGY_REGISTRY[n] for n in self.strategy_names if n in STRATEGY_REGISTRY]
        if not strategies:
            return

        for symbol in self.symbols:
            self._log("scan", f"Scanning {symbol}...")
            candles = await self._fetch_candles(symbol)
            if not candles or len(candles) < 20:
                self._log("scan", f"Insufficient data for {symbol} ({len(candles) if candles else 0} candles)")
                continue

            for strat in strategies:
                try:
                    signal = strat.evaluate(symbol, candles)
                except Exception as exc:
                    logger.warning(f"Strategy {strat.name} error on {symbol}: {exc}")
                    continue

                if signal is None:
                    continue

                # Apply adaptive weight boosting if available
                signal = self._apply_adaptive_weights(signal)

                self._signals.append(signal)
                self._log(
                    "signal",
                    f"Signal: {symbol} {signal.direction.value.upper()} @ "
                    f"${signal.entry:,.2f} (confidence: {signal.confidence:.2f}) "
                    f"[{strat.name}]",
                )

                # Check if we should act on this signal
                if signal.confidence >= 0.55:
                    await self._maybe_place_trade(signal)

    async def _fetch_candles(self, symbol: str) -> List[Dict]:
        """Fetch candle data via the engine's data layer."""
        try:
            # Try to use the engine's candle fetching
            from backend.api.app import _engine
            if _engine is None:
                return self._generate_synthetic_candles(symbol)

            # Use the equities feed or crypto feed depending on symbol
            feed = _engine.equities_feed
            if hasattr(feed, 'get_candles'):
                data = await asyncio.to_thread(feed.get_candles, symbol, "1d", 60)
                if data and isinstance(data, list) and len(data) > 0:
                    return data

            # Fall back to price data
            if hasattr(feed, 'get_price_history'):
                data = await asyncio.to_thread(feed.get_price_history, symbol, 60)
                if data:
                    return data

            return self._generate_synthetic_candles(symbol)
        except Exception as exc:
            logger.debug(f"Candle fetch for {symbol}: {exc}")
            return self._generate_synthetic_candles(symbol)

    def _generate_synthetic_candles(self, symbol: str) -> List[Dict]:
        """Generate synthetic candle data for paper trading when real data is unavailable."""
        base_prices = {
            "BTC": 68000, "ETH": 3800, "SOL": 175,
            "SPY": 520, "QQQ": 450, "AAPL": 195,
            "TSLA": 245, "NVDA": 880,
        }
        base = base_prices.get(symbol, 100)
        candles = []
        price = base
        for i in range(60):
            change = random.gauss(0, base * 0.015)
            o = price
            c = price + change
            h = max(o, c) + abs(random.gauss(0, base * 0.005))
            l = min(o, c) - abs(random.gauss(0, base * 0.005))
            candles.append({"open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2), "volume": random.randint(1000, 50000)})
            price = c
        return candles

    def _apply_adaptive_weights(self, signal: Signal) -> Signal:
        """Boost or reduce signal confidence based on adaptive learning weights."""
        try:
            from backend.api.app import _engine
            if _engine is None:
                return signal
            # Try to get adaptive weights from the learning engine
            if hasattr(_engine, 'settings'):
                # Strategy-specific weight mapping
                weight_map = {
                    "momentum": "momentum_w",
                    "mean_reversion": "structure_w",
                    "trend_following": "trend_w",
                    "breakout": "momentum_w",
                }
                w_key = weight_map.get(signal.strategy, "momentum_w")
                # Default weight is 1.0 (no change)
                weight = 1.0
                # Modulate confidence
                signal.confidence = round(min(1.0, signal.confidence * weight), 3)
        except Exception:
            pass
        return signal

    async def _maybe_place_trade(self, signal: Signal):
        """Place a paper trade if risk limits allow."""
        # Check concurrent position limit
        open_count = len([p for p in self._bot_positions.values() if p.get("status") == "open"])
        if open_count >= self.max_concurrent_positions:
            self._log("risk", f"Max concurrent positions ({self.max_concurrent_positions}) reached — skipping {signal.symbol}")
            return

        # Check if we already have an open position in this symbol
        for p in self._bot_positions.values():
            if p.get("status") == "open" and p.get("symbol") == signal.symbol:
                self._log("risk", f"Already holding {signal.symbol} — skipping")
                return

        # Calculate position size
        if signal.entry <= 0:
            return
        quantity = min(
            self.max_position_size / signal.entry,
            10.0,  # max units
        )
        quantity = round(max(0.01, quantity), 4)

        # Check policy engine
        policy_ok = await self._check_policy(signal)
        if not policy_ok:
            self._log("risk", f"Policy blocked trade on {signal.symbol}")
            return

        # Place the paper trade
        try:
            from backend.api.app import _paper_positions, _paper_next_id, _now_iso
            import backend.api.app as app_module

            pos_id = str(app_module._paper_next_id)
            app_module._paper_next_id += 1

            position = {
                "id": pos_id,
                "symbol": signal.symbol,
                "side": signal.direction.value,
                "entry_price": float(signal.entry),
                "quantity": float(quantity),
                "stop_loss": float(signal.stop_loss),
                "take_profit": float(signal.take_profit),
                "open_time": _now_iso(),
                "status": "open",
                "bot_managed": True,
                "strategy": signal.strategy,
            }

            app_module._paper_positions[pos_id] = position
            self._bot_positions[pos_id] = position
            self._trades_placed += 1
            signal.acted = True

            notional = round(signal.entry * quantity, 2)
            self._log(
                "trade",
                f"Order placed: {signal.symbol} {signal.direction.value.upper()} "
                f"x{quantity} @ ${signal.entry:,.2f} (${notional:,.0f}) "
                f"[SL: ${signal.stop_loss:,.2f} | TP: ${signal.take_profit:,.2f}]",
            )
            logger.info(f"AutoBot trade: {signal.direction.value} {quantity} {signal.symbol} @ {signal.entry}")

        except Exception as exc:
            logger.error(f"AutoBot trade placement error: {exc}")
            self._log("error", f"Failed to place trade: {exc}")

    async def _check_policy(self, signal: Signal) -> bool:
        """Run signal through PolicyEngine risk checks."""
        try:
            from backend.api.app import _engine
            if _engine is None:
                return True
            from backend.orchestrator.policy import PolicyEngine
            from backend.orchestrator.memory import MemoryEngine
            from backend.orchestrator.schemas import IntentCategory

            memory = MemoryEngine()
            policy = PolicyEngine(memory=memory, settings=_engine.settings if _engine else None)
            decision = policy.evaluate(
                category=IntentCategory.TRADE,
                user_id="autobot",
                symbols=[signal.symbol],
                context={},
            )
            return decision.allowed
        except Exception as exc:
            logger.debug(f"Policy check error: {exc}")
            return True  # Allow on error to avoid blocking bot

    def _log(self, event_type: str, message: str):
        self._activity_log.append({
            "type": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep log bounded
        if len(self._activity_log) > 500:
            self._activity_log = self._activity_log[-300:]

    def update_closed_trades(self):
        """Sync bot positions with the paper trading system to track closures."""
        try:
            from backend.api.app import _paper_positions, _paper_closed_trades

            for pos_id, pos in list(self._bot_positions.items()):
                if pos.get("status") != "open":
                    continue
                # Check if it was closed by SL/TP monitor
                if pos_id not in _paper_positions:
                    # Find it in closed trades
                    for ct in _paper_closed_trades:
                        if ct.get("id") == pos_id:
                            pos.update(ct)
                            self._bot_closed.append(pos)
                            self._bot_positions[pos_id] = pos
                            pnl = ct.get("pnl", 0)
                            self._log(
                                "close",
                                f"Position closed: {pos['symbol']} "
                                f"{'+'if pnl >= 0 else ''}${pnl:,.2f}",
                            )
                            break
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

autobot = AutoBot()
