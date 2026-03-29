"""
main.py — Lumare MIE Entry Point
Wires all modules together and provides CLI interface for:
- Running backtests
- Starting paper trading
- Starting live trading
- Running validation checks
- Generating reports
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger

from backend.config.settings import SETTINGS
from backend.data.storage import Storage
from backend.data.aggregator import DataAggregator
from backend.data.crypto_feed import CryptoFeed
from backend.data.equities_feed import EquitiesFeed
from backend.data.macro_feed import MacroFeed

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
from backend.core.explainability import ExplainabilityEngine

from backend.backtest.replay_engine import ReplayEngine
from backend.backtest.performance_metrics import PerformanceMetrics, validate_results

from backend.execution.paper_simulator import PaperSimulator
from backend.execution.blowfin_executor import BlowfinExecutor
from backend.execution.alpaca_executor import AlpacaExecutor

from backend.live.runner import LiveRunner
from backend.live.watchdog import Watchdog


# ─── Logger Setup ───────────────────────────────────────────

def setup_logging(level: str = "INFO"):
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
    )
    logger.add(
        "logs/lumare_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
    )


# ─── Factory ────────────────────────────────────────────────

class LumareEngine:
    """
    Master factory that wires all components together.
    Single object that provides access to the entire system.
    """

    def __init__(self, settings=None):
        self.settings = settings or SETTINGS

        # Storage
        self.storage = Storage(self.settings.db_path)
        self.storage.init_db()

        # Data feeds
        self.crypto_feed = CryptoFeed()
        self.equities_feed = EquitiesFeed()
        self.macro_feed = MacroFeed(self.settings)
        self.aggregator = DataAggregator(
            settings=self.settings,
            storage=self.storage,
            crypto_feed=self.crypto_feed,
            equities_feed=self.equities_feed,
            macro_feed=self.macro_feed,
        )

        # Core engines
        self.regime_engine = RegimeClassifier(self.settings)
        self.trend_engine = TrendEngine(self.settings)
        self.momentum_engine = MomentumEngine(self.settings)
        self.structure_engine = StructureEngine(self.settings)
        self.flow_engine = FlowEngine(self.settings)
        self.macro_engine = MacroEngine(self.settings)

        self.scoring_engine = ScoringEngine(
            settings=self.settings,
            trend_engine=self.trend_engine,
            momentum_engine=self.momentum_engine,
            structure_engine=self.structure_engine,
            flow_engine=self.flow_engine,
            macro_engine=self.macro_engine,
        )

        self.risk_engine = RiskEngine(self.settings, self.storage)
        self.portfolio_engine = PortfolioEngine(self.settings, self.storage, self.risk_engine)
        self.equity_governor = EquityGovernor()
        self.explainability = ExplainabilityEngine(self.storage)

        logger.info("Lumare Engine initialized — all modules wired")

    def run_backtest(
        self,
        symbol: str = "BTCUSDT",
        start_date: str = None,
        end_date: str = None,
        initial_capital: float = 100_000.0,
    ) -> dict:
        """Run a full backtest with validation."""
        logger.info(f"Starting backtest: {symbol} | Capital: ${initial_capital:,.2f}")

        engine = ReplayEngine(
            settings=self.settings,
            storage=self.storage,
            regime_engine=self.regime_engine,
            scoring_engine=self.scoring_engine,
            risk_engine=self.risk_engine,
            portfolio_engine=self.portfolio_engine,
            equity_governor=self.equity_governor,
        )

        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = engine.run(symbol, start_date, end_date, initial_capital)

        # Validate
        if hasattr(result, 'metrics') and result.metrics:
            validation = validate_results(result.metrics)
            passed = validation.passed
            logger.info(f"Validation: {'PASS' if passed else 'FAIL'}")
            for check_name, check_data in validation.checks.items():
                logger.info(f"  {check_name}: {check_data}")
        else:
            logger.warning("No metrics to validate — 0 trades were taken (sub-engines scored 0)")

        return result

    def run_walk_forward(
        self,
        symbol: str = "BTCUSDT",
        start_date: str = None,
        end_date: str = None,
    ) -> dict:
        """Run walk-forward validation."""
        logger.info(f"Starting walk-forward validation: {symbol}")

        engine = ReplayEngine(
            settings=self.settings,
            storage=self.storage,
            regime_engine=self.regime_engine,
            scoring_engine=self.scoring_engine,
            risk_engine=self.risk_engine,
            portfolio_engine=self.portfolio_engine,
            equity_governor=self.equity_governor,
        )

        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return engine.run_walk_forward(
            symbol, start_date, end_date,
            train_window=self.settings.backtest.train_window_days,
            test_window=self.settings.backtest.test_window_days,
            step=self.settings.backtest.walk_forward_step_days,
        )

    async def start_paper_trading(self, initial_capital: float = 100_000.0):
        """Start paper trading mode."""
        logger.info("Starting PAPER trading mode")

        simulator = PaperSimulator(self.settings, initial_capital)

        runner = LiveRunner(
            mode="paper",
            settings=self.settings,
            storage=self.storage,
            aggregator=self.aggregator,
            executor=simulator,
            initial_capital=initial_capital,
        )

        watchdog = Watchdog(
            settings=self.settings,
            storage=self.storage,
            aggregator=self.aggregator,
            runner=runner,
        )

        # Start watchdog in background
        watchdog_task = asyncio.create_task(watchdog.monitor(check_interval=60))

        try:
            await runner.run()
        finally:
            watchdog.stop()
            watchdog_task.cancel()

    async def start_live_trading(self, exchange: str = "blowfin"):
        """
        Start live trading mode.
        REQUIRES: All backtest validation metrics passed.
        """
        logger.critical("LIVE TRADING MODE — Real capital at risk")

        if exchange == "blowfin":
            executor = BlowfinExecutor(self.settings)
        elif exchange == "alpaca":
            executor = AlpacaExecutor(self.settings, paper=False)
        else:
            raise ValueError(f"Unknown exchange: {exchange}")

        runner = LiveRunner(
            mode="live",
            settings=self.settings,
            storage=self.storage,
            aggregator=self.aggregator,
            executor=executor,
        )

        watchdog = Watchdog(
            settings=self.settings,
            storage=self.storage,
            aggregator=self.aggregator,
            runner=runner,
        )

        watchdog_task = asyncio.create_task(watchdog.monitor(check_interval=30))

        try:
            await runner.run()
        finally:
            watchdog.stop()
            watchdog_task.cancel()
            if hasattr(executor, 'close'):
                executor.close()

    def generate_report(self) -> dict:
        """Generate a comprehensive system status report."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "settings": {
                "risk": {
                    "base_risk": self.settings.risk.base_risk_per_trade,
                    "max_heat": self.settings.risk.max_portfolio_heat,
                    "max_correlated": self.settings.risk.max_correlated_positions,
                    "dd_pause": self.settings.risk.drawdown_pause_threshold,
                    "dd_reduce": self.settings.risk.drawdown_reduce_threshold,
                    "dd_shutdown": self.settings.risk.drawdown_shutdown_threshold,
                    "daily_cap": self.settings.risk.daily_loss_cap,
                },
                "validation_targets": {
                    "min_win_rate": self.settings.validation.min_win_rate,
                    "min_sharpe": self.settings.validation.min_sharpe,
                    "min_pf": self.settings.validation.min_profit_factor,
                    "max_dd": self.settings.validation.max_drawdown,
                    "min_trades": self.settings.validation.min_trades,
                },
                "instruments": {
                    "crypto": self.settings.instruments.crypto_pairs,
                    "equities": self.settings.instruments.equity_symbols,
                },
            },
            "data_freshness": self.aggregator.get_data_freshness(),
        }


# ─── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lumare Macro Intelligence Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Backtest
    bt = subparsers.add_parser("backtest", help="Run backtest")
    bt.add_argument("--symbol", default="BTCUSDT")
    bt.add_argument("--start", default=None)
    bt.add_argument("--end", default=None)
    bt.add_argument("--capital", type=float, default=100_000)

    # Walk-forward
    wf = subparsers.add_parser("walk-forward", help="Run walk-forward validation")
    wf.add_argument("--symbol", default="BTCUSDT")
    wf.add_argument("--start", default=None)
    wf.add_argument("--end", default=None)

    # Paper trade
    paper = subparsers.add_parser("paper", help="Start paper trading")
    paper.add_argument("--capital", type=float, default=100_000)

    # Live trade
    live = subparsers.add_parser("live", help="Start live trading")
    live.add_argument("--exchange", default="blowfin", choices=["blowfin", "alpaca"])

    # Report
    subparsers.add_parser("report", help="Generate status report")

    args = parser.parse_args()

    setup_logging(SETTINGS.log_level)
    Path("logs").mkdir(exist_ok=True)

    engine = LumareEngine()

    if args.command == "backtest":
        result = engine.run_backtest(args.symbol, args.start, args.end, args.capital)
        logger.info(f"Backtest complete: {result}")

    elif args.command == "walk-forward":
        result = engine.run_walk_forward(args.symbol, args.start, args.end)
        logger.info(f"Walk-forward complete: {result}")

    elif args.command == "paper":
        asyncio.run(engine.start_paper_trading(args.capital))

    elif args.command == "live":
        asyncio.run(engine.start_live_trading(args.exchange))

    elif args.command == "report":
        report = engine.generate_report()
        import json
        print(json.dumps(report, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
