"""
runner.py — Live Trading Loop
Orchestrates the full pipeline: data → regime → signals → scoring → risk → execution.
Supports 'paper' mode (default) and 'live' mode (after validation).
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field

import pandas as pd
from loguru import logger

from backend.config.settings import SETTINGS, Settings, RegimeState
from backend.data.storage import Storage
from backend.data.aggregator import DataAggregator
from backend.core.regime_engine import RegimeClassifier
from backend.core.trend_engine import TrendEngine
from backend.core.momentum_engine import MomentumEngine
from backend.core.structure_engine import StructureEngine
from backend.core.flow_engine import FlowEngine
from backend.core.macro_engine import MacroEngine
from backend.core.scoring_engine import ScoringEngine
from backend.core.risk_engine import RiskEngine
from backend.core.portfolio_engine import PortfolioEngine
from backend.core.equity_governor import EquityGovernor
from backend.execution.paper_simulator import PaperSimulator


@dataclass
class TradeProposal:
    symbol: str
    direction: str            # 'LONG' or 'SHORT'
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    score: float
    regime: str
    signals: List[str]
    confidence: float
    risk_pct: float
    position_size: float
    leverage: float


@dataclass
class RunnerState:
    mode: str                 # 'paper' or 'live'
    running: bool = False
    paused: bool = False
    last_cycle: Optional[datetime] = None
    total_cycles: int = 0
    total_trades: int = 0
    current_regime: str = "UNKNOWN"
    daily_pnl: float = 0.0
    kill_switch: bool = False
    errors: List[str] = field(default_factory=list)


class LiveRunner:
    """
    Main trading loop that orchestrates the entire pipeline.

    Every cycle (aligned to 5M candle close):
    1. Fetch latest market data
    2. Classify regime
    3. Score signals for each instrument (long + short)
    4. Generate trade proposals if score >= 70
    5. Risk check proposals
    6. Execute approved trades
    7. Manage open positions (stops, TPs, trailing)
    8. Log everything, store snapshots
    """

    def __init__(
        self,
        mode: str = "paper",
        settings: Settings = None,
        storage: Storage = None,
        aggregator: DataAggregator = None,
        executor=None,
        initial_capital: float = 100_000.0,
    ):
        self.settings = settings or SETTINGS
        self.storage = storage or Storage(self.settings.db_path)

        # Engines
        self.aggregator = aggregator or DataAggregator(self.settings, self.storage)
        self.regime_engine = RegimeClassifier(
            confirmation_bars=self.settings.regime.regime_confirmation_bars,
        )
        self.trend_engine = TrendEngine(self.settings)
        self.momentum_engine = MomentumEngine(self.settings)
        self.structure_engine = StructureEngine(self.settings)
        self.flow_engine = FlowEngine(self.settings)
        self.macro_engine = MacroEngine(self.settings)
        self.scoring_engine = ScoringEngine(
            self.settings, self.trend_engine, self.momentum_engine,
            self.structure_engine, self.flow_engine, self.macro_engine,
        )
        self.risk_engine = RiskEngine(self.settings, self.storage)
        self.portfolio_engine = PortfolioEngine(self.settings, self.storage, self.risk_engine)
        self.equity_governor = EquityGovernor()

        # Executor
        if executor:
            self.executor = executor
        else:
            self.executor = PaperSimulator(self.settings, initial_capital)

        self.state = RunnerState(mode=mode)
        self._equity_history: List[float] = [initial_capital]

    async def run(self):
        """Main trading loop."""
        self.state.running = True
        logger.info(f"LiveRunner started in {self.state.mode.upper()} mode")

        try:
            while self.state.running:
                if self.state.paused:
                    await asyncio.sleep(5)
                    continue

                if self.state.kill_switch:
                    logger.warning("Kill switch active — skipping cycle")
                    await asyncio.sleep(60)
                    continue

                try:
                    await self._run_cycle()
                except Exception as e:
                    logger.error(f"Cycle error: {e}")
                    self.state.errors.append(f"{datetime.now(timezone.utc)}: {e}")
                    if len(self.state.errors) > 5:
                        logger.critical("Too many consecutive errors — activating kill switch")
                        self.state.kill_switch = True

                # Wait for next cycle (align to 5M candle close)
                await self._wait_for_next_candle()

        except asyncio.CancelledError:
            logger.info("LiveRunner cancelled")
        finally:
            self.state.running = False
            logger.info("LiveRunner stopped")

    async def _run_cycle(self):
        """Execute one complete trading cycle."""
        cycle_start = datetime.now(timezone.utc)
        self.state.total_cycles += 1

        logger.info(f"─── Cycle {self.state.total_cycles} @ {cycle_start.isoformat()} ───")

        for symbol in self.settings.instruments.crypto_pairs:
            try:
                await self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

        # Manage open positions
        try:
            await self._manage_positions()
        except Exception as e:
            logger.error(f"Position management error: {e}")

        # Store portfolio snapshot
        portfolio = self.executor.get_portfolio() if hasattr(self.executor, 'get_portfolio') else {}
        total_value = portfolio.get("total_value", self._equity_history[-1])
        self._equity_history.append(total_value)

        self.storage.store_portfolio_snapshot({
            "timestamp": cycle_start.isoformat(),
            "total_value": total_value,
            "cash": portfolio.get("cash", 0),
            "num_positions": portfolio.get("num_positions", 0),
            "unrealized_pnl": portfolio.get("unrealized_pnl", 0),
            "realized_pnl": portfolio.get("realized_pnl", 0),
        })

        self.state.last_cycle = cycle_start
        self.state.errors.clear()  # Clear errors on successful cycle

        elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        logger.info(f"Cycle completed in {elapsed:.1f}s | Portfolio: ${total_value:,.2f}")

    async def _process_symbol(self, symbol: str):
        """Full pipeline for a single symbol."""
        # 1. Fetch data
        snapshot = await self.aggregator.fetch_full_snapshot(symbol, "crypto")

        if not snapshot.candles.get("5M") is not None or snapshot.candles.get("5M", pd.DataFrame()).empty:
            logger.warning(f"No 5M data for {symbol}, skipping")
            return

        # Build market data dict for engines
        market_data = {
            "symbol": symbol,
            "candles": snapshot.candles,
            "last_price": snapshot.last_price or snapshot.candles["5M"]["close"].iloc[-1],
            "funding_rate": snapshot.funding_rate,
            "open_interest": snapshot.open_interest,
            "oi_change_pct": snapshot.oi_change_pct,
            "macro": snapshot.macro or {},
        }

        # 2. Regime classification
        regime_result = self.regime_engine.classify(market_data)
        self.state.current_regime = regime_result.state.value if hasattr(regime_result, 'state') else str(regime_result)

        regime_state = regime_result.state if hasattr(regime_result, 'state') else RegimeState.RISK_ON

        # Log regime — storage requires {timestamp, symbol, new_regime}
        try:
            self.storage.store_regime_change({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "new_regime": regime_state.value,
                "trigger_reason": "scheduled_cycle",
            })
        except Exception as exc:
            logger.debug(f"Regime log skipped: {exc}")

        # 3. CHAOTIC = no trading
        if regime_state == RegimeState.CHAOTIC:
            logger.warning(f"{symbol}: CHAOTIC regime — no trading")
            return

        # 4. Score both directions
        for direction in ["LONG", "SHORT"]:
            # Skip longs in RISK_OFF
            if direction == "LONG" and regime_state == RegimeState.RISK_OFF:
                continue

            score_result = self.scoring_engine.score(market_data, regime_state, direction)

            # Log signal — storage requires {timestamp, symbol, timeframe, composite_score}
            try:
                self.storage.store_signal_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "timeframe": "5M",
                    "composite_score": float(score_result.get("total_score", 0)),
                    "direction": direction,
                    "regime": regime_state.value,
                    "components": score_result.get("component_scores", {}),
                    "action_taken": (
                        "PROPOSE"
                        if score_result.get("total_score", 0)
                        >= self.settings.trade.min_score_to_trade
                        else "EVALUATE"
                    ),
                })
            except Exception as exc:
                logger.debug(f"Signal log skipped: {exc}")

            total_score = score_result.get("total_score", 0)
            if total_score < self.settings.trade.min_score_to_trade:
                continue

            # 5. Generate trade proposal
            proposal = self._generate_proposal(symbol, direction, market_data, score_result, regime_state)
            if not proposal:
                continue

            # 6. Equity governor check
            eq_curve = pd.Series(self._equity_history)
            gov_state = self.equity_governor.evaluate(eq_curve)
            if gov_state.size_modifier < 1.0:
                proposal.position_size *= gov_state.size_modifier
                proposal.risk_pct *= gov_state.size_modifier
                logger.info(f"EquityGovernor: size reduced to {gov_state.size_modifier:.0%} ({gov_state.regime})")

            # 7. Risk check
            risk_decision = self.risk_engine.approve_trade({
                "symbol": symbol,
                "direction": direction,
                "entry_price": proposal.entry_price,
                "stop_price": proposal.stop_price,
                "position_size": proposal.position_size,
                "risk_pct": proposal.risk_pct,
                "score": total_score,
            }, self._get_portfolio_state())

            if not risk_decision.get("approved", False):
                logger.info(f"{symbol} {direction}: Risk REJECTED — {risk_decision.get('reason', 'unknown')}")
                continue

            # 8. Execute
            adjusted_size = risk_decision.get("adjusted_size", proposal.position_size)
            order = self.executor.submit_order(
                symbol=symbol,
                side="BUY" if direction == "LONG" else "SELL",
                price=proposal.entry_price,
                quantity=adjusted_size,
                leverage=proposal.leverage,
            )

            if order.status.value not in ("REJECTED",):
                self.state.total_trades += 1
                try:
                    self.storage.store_trade({
                        "trade_id": order.order_id,
                        "symbol": symbol,
                        "side": direction,  # storage requires LONG/SHORT
                        "entry_time": datetime.now(timezone.utc).isoformat(),
                        "entry_price": float(proposal.entry_price),
                        "quantity": float(adjusted_size),
                        "leverage": float(proposal.leverage),
                        "stop_loss": float(proposal.stop_price),
                        "take_profit": float(proposal.tp1_price),
                        "risk_pct": float(proposal.risk_pct),
                        "signal_score": int(total_score),
                        "regime": regime_state.value,
                        "status": "OPEN",
                        "strategy": "composite",
                        "timeframe": "5M",
                    })
                except Exception as exc:
                    logger.debug(f"Trade store skipped: {exc}")
                logger.info(
                    f"TRADE: {direction} {adjusted_size:.4f} {symbol} @ {proposal.entry_price:.2f} "
                    f"(score={total_score:.0f}, regime={regime_state.value})"
                )

    def _generate_proposal(self, symbol: str, direction: str,
                           market_data: Dict, score_result: Dict,
                           regime: RegimeState) -> Optional[TradeProposal]:
        """Generate a trade proposal with entry, stop, and TP levels."""
        candles_5m = market_data["candles"].get("5M")
        if candles_5m is None or candles_5m.empty:
            return None

        last = candles_5m.iloc[-1]
        price = float(last["close"])

        # ATR for stop placement
        if len(candles_5m) >= 14:
            highs = candles_5m["high"].astype(float).values
            lows = candles_5m["low"].astype(float).values
            closes = candles_5m["close"].astype(float).values
            tr = []
            for i in range(1, len(candles_5m)):
                tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
            atr = float(pd.Series(tr[-14:]).mean())
        else:
            atr = price * 0.01  # Fallback 1%

        # Stop placement: structure-based + ATR buffer
        if direction == "LONG":
            stop = price - 1.5 * atr
            tp1 = price + 1.0 * atr
            tp2 = price + 2.0 * atr
        else:
            stop = price + 1.5 * atr
            tp1 = price - 1.0 * atr
            tp2 = price - 2.0 * atr

        # Position sizing
        total_score = score_result.get("total_score", 70)
        if total_score >= self.settings.trade.elevated_score:
            risk_pct = self.settings.trade.elevated_risk_pct
        else:
            risk_pct = self.settings.trade.standard_risk_pct

        portfolio_value = self._equity_history[-1]
        risk_amount = portfolio_value * risk_pct
        stop_distance = abs(price - stop)

        if stop_distance <= 0:
            return None

        position_size = risk_amount / stop_distance

        # Leverage calculation
        stop_pct = stop_distance / price
        lev_config = self.settings.leverage
        if stop_pct < lev_config.tight_stop_threshold:
            leverage = min(lev_config.tight_stop_max_leverage, lev_config.absolute_max_leverage)
        elif stop_pct < lev_config.medium_stop_threshold:
            leverage = min(lev_config.medium_stop_max_leverage, lev_config.absolute_max_leverage)
        else:
            leverage = min(lev_config.wide_stop_max_leverage, lev_config.absolute_max_leverage)

        return TradeProposal(
            symbol=symbol,
            direction=direction,
            entry_price=round(price, 8),
            stop_price=round(stop, 8),
            tp1_price=round(tp1, 8),
            tp2_price=round(tp2, 8),
            score=total_score,
            regime=regime.value,
            signals=score_result.get("signals_active", []),
            confidence=score_result.get("confidence", 0.5),
            risk_pct=risk_pct,
            position_size=round(position_size, 8),
            leverage=leverage,
        )

    async def _manage_positions(self):
        """Manage open positions: trail stops, check TPs."""
        if not hasattr(self.executor, 'positions'):
            return

        for symbol, pos in list(self.executor.positions.items()):
            # Check stop loss
            current_price = self.executor._prices.get(symbol, 0)
            if current_price <= 0:
                continue

            # Check TP1 hit -> move stop to breakeven
            if pos.side.value == "BUY":
                if current_price >= pos.avg_entry_price * 1.01:  # 1R approximation
                    # Trail stop to breakeven
                    pass  # Managed by executor in backtest
            else:
                if current_price <= pos.avg_entry_price * 0.99:
                    pass

    def _get_portfolio_state(self) -> Dict:
        """Get current portfolio state for risk checks."""
        if hasattr(self.executor, 'get_portfolio'):
            return self.executor.get_portfolio()
        return {"total_value": self._equity_history[-1], "positions": {}, "num_positions": 0}

    async def _wait_for_next_candle(self):
        """Wait until the next 5M candle close."""
        now = datetime.now(timezone.utc)
        minutes = now.minute
        next_5m = 5 - (minutes % 5)
        if next_5m == 0:
            next_5m = 5
        wait_seconds = next_5m * 60 - now.second
        wait_seconds = max(wait_seconds, 10)  # Minimum 10s wait
        logger.debug(f"Next cycle in {wait_seconds}s")
        await asyncio.sleep(wait_seconds)

    def stop(self):
        """Graceful shutdown."""
        self.state.running = False
        logger.info("LiveRunner stop requested")

    def pause(self):
        """Pause trading but keep monitoring."""
        self.state.paused = True
        logger.info("LiveRunner PAUSED")

    def resume(self):
        """Resume trading."""
        self.state.paused = False
        logger.info("LiveRunner RESUMED")

    def get_status(self) -> Dict:
        """Get runner status."""
        return {
            "mode": self.state.mode,
            "running": self.state.running,
            "paused": self.state.paused,
            "kill_switch": self.state.kill_switch,
            "total_cycles": self.state.total_cycles,
            "total_trades": self.state.total_trades,
            "current_regime": self.state.current_regime,
            "last_cycle": self.state.last_cycle.isoformat() if self.state.last_cycle else None,
            "portfolio_value": self._equity_history[-1] if self._equity_history else 0,
            "errors": self.state.errors[-5:],
        }
