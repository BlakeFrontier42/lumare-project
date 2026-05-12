"""
autobot.py — REST-facing controller for the autonomous trading bot.

This module is the bridge between the FastAPI bot endpoints and the live
trading pipeline (LiveRunner). It exposes a stable, frontend-friendly
contract:

    autobot.start(symbols, strategies, interval_seconds, max_concurrent)
    autobot.stop()
    autobot.get_status()          -> BotStatus
    autobot.get_performance()     -> BotPerformance
    autobot.get_signals(limit)    -> list[BotSignal]
    autobot.get_activity_log(limit) -> list[ActivityEntry]
    autobot.update_closed_trades()

Internally it wraps a ``LiveRunner`` subclass that:
  - Iterates over the symbol list passed by the API (not the hardcoded
    settings.instruments.crypto_pairs).
  - Routes data fetches through the right asset-class feed via
    ``classify_symbol`` from ``backend.core.asset_profiles``.
  - Captures every scoring decision into an in-memory deque so the
    frontend can render real signals without depending on the SQLite
    signal_logs schema.
  - Uses a simple ``interval_seconds`` sleep instead of the 5-minute
    candle alignment, so the operator sees activity within seconds of
    pressing Start.

The runner is started as an asyncio task on the FastAPI event loop, so
no extra threads or processes are needed.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from loguru import logger

from backend.live.runner import LiveRunner, TradeProposal
from backend.config.settings import SETTINGS, RegimeState
from backend.core.asset_profiles import classify_symbol
from backend.core.options_pricer import (
    OptionContract,
    resolve_weekly_contract,
    price_option,
    estimate_iv_from_returns,
)


# ---------------------------------------------------------------------------
# Internal runner — overrides cycle/symbol/wait behavior for API usage
# ---------------------------------------------------------------------------

class _ApiRunner(LiveRunner):
    """LiveRunner variant driven by the AutoBot controller.

    Differences from the base runner:

    * Iterates ``self.api_symbols`` (set by AutoBot) instead of the
      hardcoded ``settings.instruments.crypto_pairs``.
    * Asset-class-aware data fetch: ``classify_symbol(symbol)`` is passed
      to ``aggregator.fetch_full_snapshot`` so equities, futures and
      options use the right feed.
    * Configurable cycle interval — defaults to 60s for responsive UX
      instead of the 5-minute alignment.
    * Pipes every signal/score event back to the parent ``AutoBot`` so
      the API can serve them without touching the SQLite signal_logs
      table (which has a different schema).
    """

    def __init__(self, parent: "AutoBot", *args: Any, **kwargs: Any) -> None:
        self._parent = parent
        self.api_symbols: List[str] = []
        self.interval_seconds: int = 60
        super().__init__(*args, **kwargs)
        # Live-mode executor selection. Triple-locked safety:
        #   1. mode="live" passed to /api/bot/start
        #   2. LUMARE_ALLOW_LIVE=1 in env
        #   3. The relevant broker's API keys are present
        # Any miss → falls back to PaperSimulator (safe default).
        if parent._config.get("mode", "paper") == "live":
            asset_class = parent._config.get("asset_class", "crypto")
            try:
                if asset_class == "crypto":
                    from backend.execution.coinbase_executor import CoinbaseExecutor
                    self.executor = CoinbaseExecutor(
                        settings=self.settings,
                        initial_capital=self.executor.initial_capital,
                    )
                    self.executor.sync_account_balance()
                    logger.warning(
                        "Live mode: swapped PaperSimulator → CoinbaseExecutor"
                    )
                elif asset_class == "equity":
                    from backend.execution.alpaca_executor import AutobotAlpacaExecutor
                    self.executor = AutobotAlpacaExecutor(
                        settings=self.settings,
                        initial_capital=self.executor.initial_capital,
                    )
                    self.executor.sync_account_balance()
                    logger.warning(
                        "Live mode: swapped PaperSimulator → AutobotAlpacaExecutor"
                    )
                else:
                    logger.warning(
                        f"Live mode requested for asset_class={asset_class} "
                        f"— no live broker wired, staying on PaperSimulator"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"Failed to initialise live executor for "
                    f"{asset_class}: {exc}. Staying on PaperSimulator."
                )

    # ------------------------------------------------------------------ cycle
    async def _run_cycle(self) -> None:  # type: ignore[override]
        cycle_start = datetime.now(timezone.utc)
        self.state.total_cycles += 1

        symbols = list(self.api_symbols) or list(
            self.settings.instruments.crypto_pairs
        )
        logger.info(
            f"─── AutoBot cycle {self.state.total_cycles} | "
            f"symbols={len(symbols)} | @ {cycle_start.isoformat()} ───"
        )
        self._parent._log_activity(
            "cycle",
            f"Cycle {self.state.total_cycles} starting — {len(symbols)} symbols",
        )

        # Refresh per-symbol kill states from recent closed trades.
        # A symbol whose rolling PF has degraded gets locked out of new
        # entries (existing positions are still managed).
        try:
            self._parent._update_symbol_kills(self.storage)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Kill-switch update skipped: {exc}")

        for symbol in symbols:
            kill = self._parent._symbol_kills.get(symbol.upper())
            if kill and kill.get("active"):
                self._parent._log_activity(
                    "kill",
                    f"{symbol} skipped — rolling PF {kill['pf']:.2f} "
                    f"below {kill['threshold']:.2f} after "
                    f"{kill['samples']} trades",
                )
                continue
            try:
                await self._process_symbol(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Error processing {symbol}: {exc}")
                self._parent._log_activity(
                    "error", f"{symbol}: {exc}"
                )

        # Manage open positions
        try:
            await self._manage_positions()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Position management error: {exc}")

        # Portfolio snapshot
        portfolio = (
            self.executor.get_portfolio()
            if hasattr(self.executor, "get_portfolio")
            else {}
        )
        total_value = portfolio.get("total_value", self._equity_history[-1])
        self._equity_history.append(total_value)

        try:
            peak = max(total_value, max(self._equity_history))
            self.storage.store_portfolio_snapshot({
                "timestamp": cycle_start.isoformat(),
                "total_equity": float(total_value),
                "peak_equity": float(peak),
                "cash": float(portfolio.get("cash", 0)),
                "num_positions": int(portfolio.get("num_positions", 0)),
                "unrealized_pnl": float(portfolio.get("unrealized_pnl", 0)),
                "realized_pnl": float(portfolio.get("realized_pnl", 0)),
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Portfolio snapshot store skipped: {exc}")

        self.state.last_cycle = cycle_start
        # Reset error streak on a clean cycle so the kill switch doesn't
        # latch on transient flakes.
        self.state.errors.clear()

        elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        logger.info(
            f"AutoBot cycle done in {elapsed:.1f}s | "
            f"Portfolio: ${total_value:,.2f}"
        )

    # ---------------------------------------------------------- symbol process
    async def _process_symbol(self, symbol: str) -> None:  # type: ignore[override]
        # The bot-level asset_class controls *trading behavior* (do we
        # buy the underlying or an option contract?). But data routing
        # is decided per-symbol — if you mix BTC and SPY in one run,
        # we still need Coinbase for BTC and yfinance for SPY.
        configured_class = self._parent._config.get("asset_class", "")
        natural_class = classify_symbol(symbol)
        asset_class = configured_class or natural_class
        # If the configured class doesn't match the symbol's natural
        # class (e.g. configured="crypto" but symbol="SPY"), prefer the
        # natural one for data fetching so we get real prices.
        data_fetch_class = natural_class
        if natural_class in ("options", "futures"):
            data_fetch_class = "equity"  # underlying always lives on equity feed

        try:
            snapshot = await self.aggregator.fetch_full_snapshot(
                symbol, data_fetch_class
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Snapshot fetch failed for {symbol}: {exc}")
            return

        candles_5m = snapshot.candles.get("5M")
        import pandas as pd  # local import to avoid cycles
        if candles_5m is None or (
            isinstance(candles_5m, pd.DataFrame) and candles_5m.empty
        ):
            logger.warning(f"No 5M data for {symbol}, skipping")
            return

        # Step 0: feed the latest bar into the executor so any open
        # orders from the previous cycle can fill, and existing
        # positions get their unrealized P&L updated. Without this the
        # executor is just a passive order queue and positions never
        # materialise.
        last_bar = candles_5m.iloc[-1]
        bar_dict = {
            "open": float(last_bar["open"]),
            "high": float(last_bar["high"]),
            "low": float(last_bar["low"]),
            "close": float(last_bar["close"]),
            "volume": float(last_bar.get("volume", 0) or 0),
            "timestamp": last_bar.get("timestamp"),
        }
        try:
            if hasattr(self.executor, "update_market_state"):
                # ATR estimate (used by slippage model)
                if len(candles_5m) >= 14:
                    highs = candles_5m["high"].astype(float).values[-14:]
                    lows = candles_5m["low"].astype(float).values[-14:]
                    atr_est = float((highs - lows).mean())
                else:
                    atr_est = float(bar_dict["close"]) * 0.01
                self.executor.update_market_state(
                    symbol,
                    price=bar_dict["close"],
                    adv=max(bar_dict["volume"] * 100, 1_000_000),
                    atr=atr_est,
                )
            if hasattr(self.executor, "process_bar"):
                self.executor.process_bar(symbol, bar_dict)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Executor pre-cycle bar update skipped: {exc}")

        market_data = {
            "symbol": symbol,
            "candles": snapshot.candles,
            # ScoringEngine sub-engines read market_data["timeframe_data"]
            # (a dict keyed by 1H/4H/1D etc). Provide both keys so the
            # live runner and the backtest path agree on the contract.
            "timeframe_data": snapshot.candles,
            "last_price": snapshot.last_price
            or float(candles_5m["close"].iloc[-1]),
            "funding_rate": getattr(snapshot, "funding_rate", None),
            "open_interest": getattr(snapshot, "open_interest", None),
            "oi_change_pct": getattr(snapshot, "oi_change_pct", None),
            "macro": getattr(snapshot, "macro", None) or {},
        }

        # Compute regime indicator inputs from 1H candles (the regime
        # engine expects pre-computed scalars, not raw OHLCV).
        regime_inputs = self._compute_regime_inputs(snapshot.candles)

        # Regime
        regime_result = self.regime_engine.classify(regime_inputs)
        regime_state = (
            regime_result.state
            if hasattr(regime_result, "state")
            else RegimeState.RISK_ON
        )
        self.state.current_regime = regime_state.value if hasattr(
            regime_state, "value"
        ) else str(regime_state)

        # Persist regime change (schema-correct)
        try:
            self.storage.store_regime_change({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "new_regime": self.state.current_regime,
                "trigger_reason": "scheduled_cycle",
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Regime log skipped: {exc}")

        if regime_state == RegimeState.CHAOTIC:
            self._parent._log_activity(
                "regime", f"{symbol}: CHAOTIC — no trading"
            )
            return

        # Score both directions
        for direction in ("LONG", "SHORT"):
            if direction == "LONG" and regime_state == RegimeState.RISK_OFF:
                continue

            try:
                raw_result = self.scoring_engine.score(
                    market_data, regime_state, direction
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Scoring failed {symbol} {direction}: {exc}")
                continue

            # Normalise ScoringResult / dict / None to a single dict view
            # so downstream code can safely call `.get()`.
            if isinstance(raw_result, dict):
                score_result = raw_result
            elif raw_result is None:
                score_result = {"total_score": 0}
            else:
                score_result = {
                    "total_score": float(
                        getattr(raw_result, "total_score", 0) or 0
                    ),
                    "component_scores": getattr(
                        raw_result, "component_scores", {}
                    ),
                    "confidence": getattr(raw_result, "confidence", 0.5),
                    "signals_active": getattr(
                        raw_result, "signals_active", []
                    ),
                    "trade_eligible": getattr(
                        raw_result, "trade_eligible", False
                    ),
                }

            total_score = float(score_result.get("total_score", 0))

            # Emit signal to autobot deque (frontend consumes from here).
            self._parent._record_signal({
                "signal_id": f"{symbol}-{direction}-{self.state.total_cycles}",
                "symbol": symbol,
                "strategy": "composite",
                "direction": direction.lower(),
                "confidence": float(total_score) / 100.0,
                "entry": float(market_data["last_price"]),
                "stop_loss": float(market_data["last_price"])
                * (0.985 if direction == "LONG" else 1.015),
                "take_profit": float(market_data["last_price"])
                * (1.03 if direction == "LONG" else 0.97),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "acted": False,
                "reason": (
                    f"score={total_score:.0f} "
                    f"regime={self.state.current_regime}"
                ),
            })

            # Also persist to signal_logs in the schema the storage layer
            # actually requires. The base LiveRunner had a schema-mismatch
            # bug that threw on every cycle.
            try:
                self.storage.store_signal_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "timeframe": "5M",
                    "composite_score": float(total_score),
                    "direction": direction,
                    "regime": self.state.current_regime,
                    "components": (
                        score_result.get("component_scores")
                        if isinstance(score_result, dict)
                        else None
                    ),
                    "action_taken": (
                        "EVALUATE"
                        if total_score
                        < self.settings.trade.min_score_to_trade
                        else "PROPOSE"
                    ),
                })
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Signal log skipped: {exc}")

            if total_score < self.settings.trade.min_score_to_trade:
                continue

            # Generate proposal
            proposal = self._generate_proposal(
                symbol, direction, market_data, score_result, regime_state
            )
            if not proposal:
                continue

            # Equity governor
            eq_curve = pd.Series(self._equity_history)
            gov_state = self.equity_governor.evaluate(eq_curve)
            if gov_state.size_modifier < 1.0:
                proposal.position_size *= gov_state.size_modifier
                proposal.risk_pct *= gov_state.size_modifier

            # Risk check — risk_engine expects strict TradeProposal /
            # PortfolioState dataclasses, not dicts.
            from backend.core.risk_engine import (
                TradeProposal as RETradeProposal,
                PortfolioState as REPortfolioState,
            )
            portfolio_state = self._get_portfolio_state()
            peak = max(self._equity_history) if self._equity_history else 0.0
            portfolio_obj = REPortfolioState(
                total_value=float(
                    portfolio_state.get(
                        "total_value", self._equity_history[-1]
                    )
                ),
                open_positions=list(
                    portfolio_state.get("positions", {}).values()
                )
                if isinstance(portfolio_state.get("positions"), dict)
                else list(portfolio_state.get("positions", [])),
                equity_curve=list(self._equity_history),
                daily_pnl=float(portfolio_state.get("daily_pnl", 0.0)),
                peak_equity=float(peak),
            )
            trade_obj = RETradeProposal(
                symbol=symbol,
                direction=direction.lower(),
                entry_price=float(proposal.entry_price),
                stop_price=float(proposal.stop_price),
                conviction_score=float(total_score),
                regime=regime_state,
                leverage=float(getattr(proposal, "leverage", 1.0)),
                asset_class=asset_class,
            )
            risk_decision_result = self.risk_engine.approve_trade(
                trade_obj, portfolio_obj
            )

            # approve_trade returns either dict or RiskDecision object —
            # normalise to a dict for consistent downstream access.
            if isinstance(risk_decision_result, dict):
                risk_decision = risk_decision_result
            else:
                risk_decision = {
                    "approved": getattr(risk_decision_result, "approved", False),
                    "adjusted_size": getattr(
                        risk_decision_result,
                        "adjusted_size",
                        proposal.position_size,
                    ),
                    "reason": getattr(risk_decision_result, "reason", ""),
                }

            if not risk_decision.get("approved", False):
                self._parent._log_activity(
                    "risk",
                    f"{symbol} {direction} rejected: "
                    f"{risk_decision.get('reason', 'unknown')}",
                )
                continue

            # Execute. For options the executor symbol becomes the
            # contract id and the order is priced in option premium,
            # not the underlying.
            adjusted_size = risk_decision.get(
                "adjusted_size", proposal.position_size
            )
            order_symbol = symbol
            order_price = float(proposal.entry_price)
            order_qty = float(adjusted_size)
            order_bar = bar_dict
            contract_obj: Optional[OptionContract] = None
            contract_meta: Optional[Dict[str, Any]] = None
            opt_stop = float(proposal.stop_price)
            opt_tp = float(getattr(proposal, "tp1_price", proposal.stop_price))

            if asset_class == "options":
                # Resolve a near-ATM weekly contract for this direction.
                underlying_price = float(market_data["last_price"])
                contract_obj = resolve_weekly_contract(
                    symbol, underlying_price, direction
                )
                # IV from realised vol on the 5M return series.
                ret_series = (
                    candles_5m["close"]
                    .astype(float)
                    .pct_change()
                    .dropna()
                    .tail(60)
                    .tolist()
                )
                iv = estimate_iv_from_returns(ret_series)
                quote = price_option(contract_obj, underlying_price, iv)
                opt_price = quote["price"]

                # Sizing in options: risk per trade ÷ stop distance per
                # contract, where each contract controls 100 shares.
                # Stop = 50% of premium loss; TP = 100% premium gain (2R).
                opt_stop = max(opt_price * 0.5, 0.05)
                opt_tp = max(opt_price * 2.0, opt_price + 0.10)
                stop_distance = opt_price - opt_stop
                portfolio_value = (
                    self._equity_history[-1]
                    if self._equity_history else 100_000.0
                )
                risk_dollars = portfolio_value * 0.005  # 0.5% per options trade
                contracts = max(
                    1, int(risk_dollars / max(stop_distance * 100.0, 0.01))
                )
                contracts = min(contracts, 50)  # never more than 50 contracts

                order_symbol = contract_obj.occ_symbol
                order_price = opt_price
                order_qty = float(contracts)

                # Synthesise an option-priced bar so process_bar can
                # actually fill the order at option premium.
                if contract_obj.option_type == "CALL":
                    bar_high_src = bar_dict["high"]
                    bar_low_src = bar_dict["low"]
                else:  # PUT inverts: option price rises when underlying drops
                    bar_high_src = bar_dict["low"]
                    bar_low_src = bar_dict["high"]
                order_bar = {
                    "open": price_option(
                        contract_obj, bar_dict["open"], iv
                    )["price"],
                    "high": price_option(
                        contract_obj, bar_high_src, iv
                    )["price"],
                    "low": price_option(
                        contract_obj, bar_low_src, iv
                    )["price"],
                    "close": opt_price,
                    "volume": bar_dict["volume"],
                    "timestamp": bar_dict["timestamp"],
                }

                contract_meta = {
                    **contract_obj.to_dict(),
                    "iv": iv,
                    "delta": quote["delta"],
                    "days_to_expiry": quote["days_to_expiry"],
                    "underlying_price_at_entry": underlying_price,
                    "asset_class": "options",
                }

                # Pre-seed the executor's market state with option pricing
                if hasattr(self.executor, "update_market_state"):
                    self.executor.update_market_state(
                        order_symbol,
                        price=opt_price,
                        adv=10_000_000,
                        atr=opt_price * 0.05,
                    )

            try:
                order = self.executor.submit_order(
                    symbol=order_symbol,
                    side="BUY",  # options are always bought long in this strategy
                    price=order_price,
                    quantity=order_qty,
                    leverage=1.0 if asset_class == "options" else proposal.leverage,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Order submit failed {order_symbol}: {exc}")
                continue

            status_value = (
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status)
            )
            if status_value != "REJECTED":
                self.state.total_trades += 1
                trade_label = (
                    f"{direction} {order_qty:.0f}× {contract_obj.contract_id}"
                    if contract_obj
                    else f"{direction} {order_qty:.4f} {symbol}"
                )
                self._parent._log_activity(
                    "trade",
                    f"{trade_label} @ {order_price:.2f} (score={total_score:.0f})",
                )

                # Store contract metadata so the UI can render it.
                if contract_meta is not None:
                    self._parent._contract_meta[order_symbol] = contract_meta

                # Immediately try to fill against the (synthesised, for
                # options) current bar.
                try:
                    if hasattr(self.executor, "process_bar"):
                        self.executor.process_bar(order_symbol, order_bar)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"Executor fill attempt skipped: {exc}")
                try:
                    self.storage.store_trade({
                        "trade_id": order.order_id,
                        # Persist whichever ticker the executor is keyed on
                        # so the position/trade lookups stay consistent.
                        "symbol": order_symbol,
                        "side": direction,  # storage requires LONG/SHORT
                        "entry_time": datetime.now(timezone.utc).isoformat(),
                        "entry_price": float(order_price),
                        "quantity": float(order_qty),
                        "leverage": (
                            1.0
                            if asset_class == "options"
                            else float(proposal.leverage)
                        ),
                        "stop_loss": float(opt_stop),
                        "take_profit": float(opt_tp),
                        "risk_pct": float(proposal.risk_pct),
                        "signal_score": int(total_score),
                        "regime": self.state.current_regime,
                        "status": "OPEN",
                        "strategy": "composite",
                        "timeframe": "5M",
                        # contract_id stored in notes so we can recover
                        # human-readable contract info from history.
                        "notes": (
                            contract_obj.contract_id if contract_obj else None
                        ),
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"Trade store skipped: {exc}")

    # ------------------------------------------------------ regime helper
    @staticmethod
    def _compute_regime_inputs(candles: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the scalar inputs the RegimeClassifier requires.

        Pulls from the 1H frame (fallback 4H, then 5M). Mirrors the logic
        used in backend/backtest/replay_engine.py::_classify_regime so
        live and backtest use the same regime definition.
        """
        import pandas as pd

        df = None
        for tf in ("1H", "4H", "5M"):
            cand = candles.get(tf)
            if cand is not None and not (
                isinstance(cand, pd.DataFrame) and cand.empty
            ):
                df = cand
                break

        # Conservative defaults so the engine can still classify even
        # when indicators are missing — better than throwing.
        if df is None or len(df) < 20:
            return {
                "vol_percentile": 50.0,
                "atr_percentile": 50.0,
                "adx": 20.0,
                "volume_ratio": 1.0,
                "breakout_detected": False,
                "macro_stress": False,
                "macro_liquidity_expanding": True,
            }

        closes = df["close"].astype(float)
        highs = df["high"].astype(float)
        lows = df["low"].astype(float)
        volumes = df.get("volume", pd.Series([1.0] * len(df))).astype(float)

        # ATR + ATR percentile
        prev_close = closes.shift(1)
        tr = pd.concat(
            [
                highs - lows,
                (highs - prev_close).abs(),
                (lows - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean()
        current_atr = float(atr.iloc[-1]) if not atr.empty else 0.0
        atr_pct = (
            float((atr.dropna() <= current_atr).mean() * 100)
            if not atr.dropna().empty
            else 50.0
        )

        # Vol percentile (annualised return std)
        returns = closes.pct_change().dropna()
        rolling_vol = returns.rolling(14).std()
        current_vol = (
            float(rolling_vol.iloc[-1]) if not rolling_vol.empty else 0.0
        )
        vol_pct = (
            float((rolling_vol.dropna() <= current_vol).mean() * 100)
            if not rolling_vol.dropna().empty
            else 50.0
        )

        # ADX (simple DX approximation)
        plus_dm = (highs.diff()).clip(lower=0)
        minus_dm = (-lows.diff()).clip(lower=0)
        plus_dm[plus_dm < minus_dm] = 0
        minus_dm[minus_dm < plus_dm] = 0
        smoothed_plus = plus_dm.rolling(14).mean()
        smoothed_minus = minus_dm.rolling(14).mean()
        smoothed_tr = tr.rolling(14).mean().replace(0, float("nan"))
        plus_di = 100 * smoothed_plus / smoothed_tr
        minus_di = 100 * smoothed_minus / smoothed_tr
        dx = (
            100
            * (plus_di - minus_di).abs()
            / (plus_di + minus_di).replace(0, float("nan"))
        )
        adx_val = (
            float(dx.rolling(14).mean().iloc[-1]) if not dx.empty else 20.0
        )
        if adx_val != adx_val:  # NaN guard
            adx_val = 20.0

        # Volume ratio
        avg_vol = float(volumes.rolling(20).mean().iloc[-1]) or 1.0
        vol_ratio = float(volumes.iloc[-1]) / avg_vol if avg_vol else 1.0

        # Breakout detection
        recent_high = (
            float(highs.iloc[-21:-1].max())
            if len(highs) > 21
            else float(highs.max())
        )
        breakout = bool(float(closes.iloc[-1]) > recent_high)

        return {
            "vol_percentile": vol_pct,
            "atr_percentile": atr_pct,
            "adx": adx_val,
            "volume_ratio": vol_ratio,
            "breakout_detected": breakout,
            "macro_stress": False,
            "macro_liquidity_expanding": True,
        }

    # ----------------------------------------------------------- wait override
    async def _wait_for_next_candle(self) -> None:  # type: ignore[override]
        await asyncio.sleep(max(int(self.interval_seconds), 5))


# ---------------------------------------------------------------------------
# AutoBot controller (singleton)
# ---------------------------------------------------------------------------

class AutoBot:
    """Singleton bot controller bridging FastAPI endpoints to a LiveRunner."""

    def __init__(self) -> None:
        self._runner: Optional[_ApiRunner] = None
        self._task: Optional[asyncio.Task] = None
        self._started_at: Optional[datetime] = None
        self._config: Dict[str, Any] = {
            "symbols": [],
            "strategies": [],
            "interval_seconds": 60,
            "max_concurrent": 3,
        }
        self._signals: Deque[Dict[str, Any]] = deque(maxlen=500)
        self._activity: Deque[Dict[str, Any]] = deque(maxlen=500)
        # When trading options/futures, the executor key isn't the bare
        # underlying — it's the contract id (e.g. "SPY260515C00740000").
        # This map lets get_open_positions enrich the response with the
        # human-readable contract metadata.
        self._contract_meta: Dict[str, Dict[str, Any]] = {}
        # Per-symbol kill switch state. When a symbol's rolling PF
        # drops below KILL_PF_THRESHOLD across at least KILL_MIN_SAMPLES
        # closed trades, it stops opening new positions automatically.
        # Existing positions are still managed (stops/TPs honoured).
        # Operator can re-enable via POST /api/bot/symbols/{sym}/reset
        self._symbol_kills: Dict[str, Dict[str, Any]] = {}
        # Tunable defaults — surfaced in get_status() as kill_config
        self._kill_min_samples = 10        # need 10 trades before kill applies
        self._kill_pf_threshold = 1.0      # PF < 1.0 = stop trading symbol
        self._kill_window = 25             # rolling window of last N trades

    # ------------------------------------------------------------------ public
    def start(
        self,
        symbols: List[str],
        strategies: List[str],
        interval_seconds: int,
        max_concurrent: int,
        min_score: Optional[int] = None,
        mode: str = "paper",
        asset_class: str = "crypto",
    ) -> None:
        if self._runner and self._runner.state.running:
            self._log_activity("info", "Start ignored — bot already running")
            return

        # PRODUCTION SAFETY: real-money trading requires an explicit env
        # var so an accidental "live" payload never sends real orders.
        # Hard-coerce mode to "paper" unless LUMARE_ALLOW_LIVE=1.
        import os
        if mode.lower() == "live" and os.getenv(
            "LUMARE_ALLOW_LIVE", "0"
        ) != "1":
            logger.warning(
                "Bot start requested mode=live but LUMARE_ALLOW_LIVE is "
                "not set. Coercing to mode=paper for safety."
            )
            self._log_activity(
                "warning",
                "Live-mode requested without LUMARE_ALLOW_LIVE=1 — "
                "running in PAPER mode for safety.",
            )
            mode = "paper"

        # Validate asset class — only the four supported markets get
        # specialised routing. Anything else falls through to spot.
        asset_class = (asset_class or "crypto").lower()
        if asset_class not in ("crypto", "equity", "futures", "options"):
            asset_class = "crypto"

        self._config = {
            "symbols": list(symbols),
            "strategies": list(strategies),
            "interval_seconds": int(interval_seconds),
            "max_concurrent": int(max_concurrent),
            "mode": mode,
            "min_score": int(min_score) if min_score is not None else None,
            "asset_class": asset_class,
        }

        # Build a fresh runner each start so config changes (symbols,
        # interval) take effect.
        self._runner = _ApiRunner(parent=self, mode=mode)
        self._runner.api_symbols = list(symbols)
        self._runner.interval_seconds = int(interval_seconds)

        # Optional min_score override (e.g. 25 in demo mode so the operator
        # actually sees trades fire on mock data). Defaults to whatever the
        # global settings.trade.min_score_to_trade is (typically 70).
        if min_score is not None:
            try:
                self._runner.settings.trade.min_score_to_trade = int(min_score)
            except Exception:  # noqa: BLE001
                pass

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Fallback: no running loop in this context (rare from FastAPI).
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._task = loop.create_task(self._runner.run())
        self._started_at = datetime.now(timezone.utc)
        self._log_activity(
            "start",
            f"Bot started — {len(symbols)} symbols, "
            f"{interval_seconds}s interval, "
            f"max {max_concurrent} concurrent positions",
        )
        logger.info(
            f"AutoBot started with {symbols} | "
            f"interval={interval_seconds}s"
        )

    def stop(self) -> None:
        if self._runner:
            self._runner.stop()
        if self._task and not self._task.done():
            self._task.cancel()
        self._log_activity("stop", "Bot stopped")
        logger.info("AutoBot stopped")

    # ----------------------------------------------------------- status / perf
    def get_status(self) -> Dict[str, Any]:
        runner = self._runner
        running = bool(runner and runner.state.running)
        if running and self._started_at:
            uptime = int(
                (datetime.now(timezone.utc) - self._started_at).total_seconds()
            )
        else:
            uptime = 0

        open_positions = 0
        if runner and hasattr(runner.executor, "positions"):
            open_positions = len(runner.executor.positions)

        # Pull per-symbol data provenance from the feeds (set on each
        # fetch). Lets the frontend show a LIVE / MOCK badge so the
        # operator never confuses simulated prices with real markets.
        data_sources: Dict[str, str] = {}
        any_mock = False
        if runner and runner.aggregator:
            cf = getattr(runner.aggregator, "crypto_feed", None)
            ef = getattr(runner.aggregator, "equities_feed", None)
            for sym in self._config["symbols"]:
                src = "unknown"
                if cf and sym in cf.last_data_source:
                    src = cf.last_data_source[sym]
                elif ef and sym in ef.last_data_source:
                    src = ef.last_data_source[sym]
                data_sources[sym] = src
                if src == "mock":
                    any_mock = True

        return {
            "running": running,
            "uptime_seconds": uptime,
            "symbols": self._config["symbols"],
            "strategies": self._config["strategies"],
            "interval_seconds": self._config["interval_seconds"],
            "max_concurrent_positions": self._config["max_concurrent"],
            "signals_generated": len(self._signals),
            "trades_placed": runner.state.total_trades if runner else 0,
            "open_positions": open_positions,
            "current_regime": runner.state.current_regime if runner else "UNKNOWN",
            "kill_switch": runner.state.kill_switch if runner else False,
            "total_cycles": runner.state.total_cycles if runner else 0,
            "last_cycle": (
                runner.state.last_cycle.isoformat()
                if runner and runner.state.last_cycle
                else None
            ),
            "mode": self._config.get("mode", "paper"),
            "data_sources": data_sources,
            "any_mock_data": any_mock,
            "symbol_kills": dict(self._symbol_kills),
            "kill_config": {
                "min_samples": self._kill_min_samples,
                "pf_threshold": self._kill_pf_threshold,
                "window": self._kill_window,
            },
        }

    def get_performance(self) -> Dict[str, Any]:
        """Compute portfolio performance from the live executor + storage."""
        runner = self._runner
        portfolio: Dict[str, Any] = {}
        closed_trades: List[Dict[str, Any]] = []

        if runner:
            if hasattr(runner.executor, "get_portfolio"):
                try:
                    portfolio = runner.executor.get_portfolio()
                except Exception:  # noqa: BLE001
                    portfolio = {}

            if hasattr(runner.executor, "closed_positions"):
                closed_trades = list(getattr(runner.executor, "closed_positions"))
            elif hasattr(runner.executor, "closed_trades"):
                closed_trades = list(getattr(runner.executor, "closed_trades"))

        total_pnl = float(
            portfolio.get(
                "realized_pnl",
                sum(float(t.get("pnl", 0)) for t in closed_trades),
            )
        )
        wins = [
            float(t.get("pnl", 0))
            for t in closed_trades
            if float(t.get("pnl", 0)) > 0
        ]
        losses = [
            float(t.get("pnl", 0))
            for t in closed_trades
            if float(t.get("pnl", 0)) < 0
        ]
        total_trades = len(closed_trades)
        win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
        avg_gain = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (
            (gross_profit / gross_loss) if gross_loss > 0 else (
                gross_profit if gross_profit else 0.0
            )
        )

        # Sharpe approx from runner equity history
        sharpe = 0.0
        if runner and len(runner._equity_history) > 5:
            import math
            import statistics
            eq = runner._equity_history
            rets = [
                (eq[i] - eq[i - 1]) / eq[i - 1]
                for i in range(1, len(eq))
                if eq[i - 1]
            ]
            if rets and statistics.pstdev(rets) > 0:
                sharpe = (
                    statistics.mean(rets)
                    / statistics.pstdev(rets)
                    * math.sqrt(252 * 78)  # 5m bars annualised
                )

        return {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_gain": avg_gain,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "sharpe": sharpe,
            "portfolio_value": float(
                portfolio.get(
                    "total_value",
                    runner._equity_history[-1] if runner else 100_000.0,
                )
            ),
            "unrealized_pnl": float(portfolio.get("unrealized_pnl", 0.0)),
            "strategy_breakdown": {
                "composite": {
                    "trades": total_trades,
                    "pnl": total_pnl,
                    "win_rate": win_rate,
                }
            },
        }

    # --------------------------------------------------------------- streams
    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._signals)[-int(limit):][::-1]

    def get_activity_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._activity)[-int(limit):][::-1]

    def update_closed_trades(self) -> None:
        """Hook called pre-status/performance. Currently a no-op because the
        runner already manages position lifecycle inline. Reserved for
        future syncing with external broker fills."""
        return None

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Force-close an open position at market price. Returns the
        realized P&L and removes the position from the executor."""
        runner = self._runner
        if not runner or not hasattr(runner.executor, "positions"):
            return {"closed": False, "reason": "bot not running"}
        executor = runner.executor
        sym = symbol.upper()
        if sym not in executor.positions:
            return {"closed": False, "reason": "no position for symbol"}

        pos = executor.positions[sym]
        # Use last known price (set by process_bar each cycle)
        last_price = float(
            getattr(executor, "_prices", {}).get(sym, pos.avg_entry_price)
            or pos.avg_entry_price
        )

        # Determine PnL
        from backend.execution.paper_simulator import OrderSide
        if pos.side == OrderSide.BUY:
            pnl = (last_price - pos.avg_entry_price) * pos.quantity * pos.leverage
        else:
            pnl = (pos.avg_entry_price - last_price) * pos.quantity * pos.leverage
        margin = (pos.avg_entry_price * pos.quantity) / pos.leverage

        # Return margin + PnL to cash, drop the position
        executor.cash += margin + pnl
        pos.realized_pnl += pnl
        del executor.positions[sym]

        # Persist a closed trade record matching storage.store_trade schema
        try:
            import uuid as _uuid
            entry_iso = (
                pos.opened_at.isoformat()
                if hasattr(pos, "opened_at") and pos.opened_at
                else datetime.now(timezone.utc).isoformat()
            )
            runner.storage.store_trade({
                "trade_id": f"manual-close-{sym}-{_uuid.uuid4().hex[:8]}",
                "symbol": sym,
                # CHECK constraint requires LONG/SHORT, not BUY/SELL
                "side": "LONG" if pos.side == OrderSide.BUY else "SHORT",
                "entry_time": entry_iso,
                "exit_time": datetime.now(timezone.utc).isoformat(),
                "entry_price": float(pos.avg_entry_price),
                "exit_price": float(last_price),
                "quantity": float(pos.quantity),
                "leverage": float(pos.leverage),
                "pnl": float(pnl),
                "regime": runner.state.current_regime,
                "status": "CLOSED",
                "strategy": "composite",
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Closed-trade store skipped: {exc}")

        self._log_activity(
            "trade",
            f"Manual close {sym} @ {last_price:.2f} | PnL ${pnl:+,.2f}",
        )
        return {
            "closed": True,
            "symbol": sym,
            "exit_price": last_price,
            "pnl": pnl,
        }

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Return open positions from the paper executor in a frontend-
        friendly shape that matches the bot page's OpenPosition type."""
        runner = self._runner
        out: List[Dict[str, Any]] = []
        if not runner or not hasattr(runner.executor, "positions"):
            return out
        positions = runner.executor.positions  # symbol -> SimPosition
        for sym, pos in positions.items():
            side_val = getattr(pos.side, "value", str(pos.side))
            direction = "LONG" if side_val == "BUY" else "SHORT"
            current_price = 0.0
            if hasattr(runner.executor, "_prices"):
                current_price = float(
                    runner.executor._prices.get(sym, pos.avg_entry_price) or 0
                )
            if current_price <= 0:
                current_price = float(pos.avg_entry_price)
            entry_dt = getattr(pos, "opened_at", None)
            entry_ms = (
                int(entry_dt.timestamp() * 1000)
                if entry_dt
                else int(datetime.now(timezone.utc).timestamp() * 1000)
            )
            meta = self._contract_meta.get(sym)
            display_symbol = sym
            instrument_type = "spot"
            option_type = None
            strike = None
            expiry = None
            contract_id = None
            if meta:
                instrument_type = meta.get("asset_class", "spot")
                display_symbol = meta.get("underlying", sym)
                option_type = meta.get("option_type")
                strike = meta.get("strike")
                expiry = meta.get("expiry")
                contract_id = meta.get("contract_id")
                # The bot direction follows the market view: long-call=LONG,
                # long-put=SHORT (bearish via puts).
                if option_type == "PUT":
                    direction = "SHORT"
                elif option_type == "CALL":
                    direction = "LONG"
            out.append({
                "id": f"pos-{sym}-{side_val}",
                "symbol": display_symbol,
                "direction": direction,
                "strategy": "composite",
                "entryPrice": float(pos.avg_entry_price),
                "currentPrice": current_price,
                "quantity": float(pos.quantity),
                "stopLoss": float(getattr(pos, "stop_loss", 0) or 0),
                "takeProfit": float(getattr(pos, "take_profit", 0) or 0),
                "entryTime": entry_ms,
                "leverage": float(getattr(pos, "leverage", 1.0)),
                "unrealizedPnl": float(getattr(pos, "unrealized_pnl", 0)),
                "instrumentType": instrument_type,
                "optionType": option_type,
                "strike": strike,
                "expiry": expiry,
                "contractId": contract_id,
            })
        return out

    def get_snapshot(self) -> Dict[str, Any]:
        """One-shot serialisable view of everything the bot UI cares
        about. Used by /ws/bot to push state at high frequency without
        forcing the frontend to coalesce 6 separate fetches."""
        return {
            "status": self.get_status(),
            "positions": self.get_open_positions(),
            "performance": self.get_performance(),
            "signals": self.get_signals(50),
            "activity": self.get_activity_log(50),
            "trades": self.get_closed_trades(50),
        }

    def get_closed_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return closed trades from storage in frontend-friendly shape."""
        runner = self._runner
        if not runner:
            return []
        try:
            # Query last `limit` trades regardless of window
            from datetime import timedelta
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=365)
            rows = runner.storage.get_trades(
                start=start.isoformat(),
                end=end.isoformat(),
                status="CLOSED",
            )
        except Exception:  # noqa: BLE001
            rows = []
        rows = rows[-int(limit):]
        out: List[Dict[str, Any]] = []
        for r in rows:
            entry_ts = r.get("entry_time") or r.get("timestamp") or 0
            exit_ts = r.get("exit_time") or entry_ts
            try:
                entry_ms = int(
                    datetime.fromisoformat(str(entry_ts)).timestamp() * 1000
                )
            except Exception:  # noqa: BLE001
                entry_ms = 0
            try:
                exit_ms = int(
                    datetime.fromisoformat(str(exit_ts)).timestamp() * 1000
                )
            except Exception:  # noqa: BLE001
                exit_ms = entry_ms
            out.append({
                "id": str(r.get("trade_id") or r.get("id") or entry_ts),
                "symbol": r.get("symbol", ""),
                "direction": r.get("side") or r.get("direction") or "LONG",
                "strategy": r.get("strategy") or "composite",
                "entryPrice": float(r.get("entry_price", 0) or 0),
                "exitPrice": float(r.get("exit_price", 0) or 0),
                "quantity": float(r.get("quantity", 0) or 0),
                "stopLoss": float(r.get("stop_loss", 0) or 0),
                "takeProfit": float(r.get("take_profit", 0) or 0),
                "entryTime": entry_ms,
                "exitTime": exit_ms,
                "pnl": float(r.get("pnl", 0) or 0),
            })
        return out

    # ------------------------------------------------------------ internal
    # ------------------------------------------------------------ kills
    def _update_symbol_kills(self, storage) -> None:
        """Recompute per-symbol rolling PF and toggle the kill state.

        A symbol gets killed when:
          * At least self._kill_min_samples closed trades exist
          * Rolling PF over last self._kill_window trades < self._kill_pf_threshold

        Killed symbols stay killed until an explicit reset
        (POST /api/bot/symbols/{symbol}/reset).
        """
        from datetime import timedelta
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=365)
            rows = storage.get_trades(
                start=start.isoformat(),
                end=end.isoformat(),
                status="CLOSED",
            ) or []
        except Exception:
            return

        # Group by underlying symbol — for options the storage symbol
        # is the OCC id, so we need to map back.
        by_symbol: dict[str, list[float]] = {}
        for r in rows[-1000:]:  # cap to last 1000 trades
            pnl = r.get("pnl")
            if pnl is None:
                continue
            sym = (r.get("symbol") or "").upper()
            # Map options OCC symbol back to underlying via contract_meta.
            meta = self._contract_meta.get(sym)
            display = meta.get("underlying", sym) if meta else sym
            by_symbol.setdefault(display, []).append(float(pnl))

        for sym, pnls in by_symbol.items():
            window = pnls[-self._kill_window:]
            if len(window) < self._kill_min_samples:
                # Not enough data — clear any stale kill state (if not
                # manually pinned).
                state = self._symbol_kills.get(sym)
                if state and not state.get("manual", False):
                    self._symbol_kills.pop(sym, None)
                continue

            wins = sum(p for p in window if p > 0)
            losses = abs(sum(p for p in window if p < 0))
            if losses == 0:
                pf = float("inf") if wins > 0 else 0.0
            else:
                pf = wins / losses

            should_kill = pf < self._kill_pf_threshold
            current = self._symbol_kills.get(sym)

            if should_kill:
                if not current or not current.get("active"):
                    # First trip — log it
                    self._log_activity(
                        "kill",
                        f"{sym} kill-switch ARMED — rolling PF "
                        f"{pf:.2f} after {len(window)} trades "
                        f"(threshold {self._kill_pf_threshold:.2f})",
                    )
                self._symbol_kills[sym] = {
                    "active": True,
                    "pf": round(pf if pf != float("inf") else 99.99, 3),
                    "samples": len(window),
                    "threshold": self._kill_pf_threshold,
                    "armed_at": datetime.now(timezone.utc).isoformat(),
                    "manual": bool(current.get("manual", False)) if current else False,
                }
            else:
                # PF recovered. Only auto-clear if not manually pinned.
                if current and current.get("active") and not current.get("manual", False):
                    self._log_activity(
                        "kill",
                        f"{sym} kill-switch CLEARED — rolling PF "
                        f"recovered to {pf:.2f}",
                    )
                    self._symbol_kills.pop(sym, None)

    def reset_symbol_kill(self, symbol: str) -> dict:
        """Operator override — clear a symbol's kill state immediately."""
        sym = symbol.upper()
        existed = self._symbol_kills.pop(sym, None)
        if existed:
            self._log_activity("kill", f"{sym} kill-switch RESET by operator")
            return {"reset": True, "symbol": sym, "previous_state": existed}
        return {"reset": False, "symbol": sym, "reason": "no active kill"}

    def kill_symbol(self, symbol: str, reason: str = "manual") -> dict:
        """Operator override — manually kill a symbol regardless of PF."""
        sym = symbol.upper()
        self._symbol_kills[sym] = {
            "active": True,
            "pf": 0.0,
            "samples": 0,
            "threshold": self._kill_pf_threshold,
            "armed_at": datetime.now(timezone.utc).isoformat(),
            "manual": True,
            "reason": reason,
        }
        self._log_activity("kill", f"{sym} MANUALLY KILLED — {reason}")
        return {"killed": True, "symbol": sym}

    def _record_signal(self, signal: Dict[str, Any]) -> None:
        self._signals.append(signal)

    def _log_activity(self, kind: str, message: str) -> None:
        self._activity.append({
            "type": kind,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# Module-level singleton — imported as ``from backend.orchestrator.autobot
# import autobot`` in backend/api/app.py.
autobot = AutoBot()
