"""
multi_asset_backtest.py — Run the Lumare backtest across crypto + equities
and print a per-symbol results table.

Uses a 60-day window so all symbols have comparable data (yfinance 5m cap).
"""

import sys
import os
from datetime import datetime, timezone, timedelta

from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import LumareEngine
from backend.backtest.replay_engine import ReplayEngine

# Diagnostic mode: lower score threshold to prove execution path works end-to-end
# on equities whose 58-day window happens to be choppy. Production threshold = 65.
DIAGNOSTIC_THRESHOLD = int(os.getenv("LUMARE_DIAG_THRESHOLD", "0"))
if DIAGNOSTIC_THRESHOLD:
    ReplayEngine.SCORE_THRESHOLD = DIAGNOSTIC_THRESHOLD
    logger.warning("DIAGNOSTIC MODE — SCORE_THRESHOLD lowered to {}", DIAGNOSTIC_THRESHOLD)


SYMBOLS = [
    # Crypto
    "BTCUSDT", "ETHUSDT",
    # Mag 7
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    # Index ETFs
    "SPY", "QQQ",
]


def main():
    engine = LumareEngine()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=58)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    logger.info("Multi-asset backtest window: {} → {}", start_s, end_s)

    rows = []
    for sym in SYMBOLS:
        logger.info("▶  {}", sym)
        try:
            result = engine.run_backtest(
                symbol=sym,
                start_date=start_s,
                end_date=end_s,
                initial_capital=100_000.0,
            )
        except Exception as exc:
            logger.error("{} failed: {}", sym, exc)
            rows.append((sym, 0, 0, 0, 0, 0, 0, "ERROR"))
            continue

        m = result.metrics
        if not m or m.total_trades == 0:
            rows.append((sym, 0, 0.0, 0.0, 0.0, 0.0, 0.0, "NO TRADES"))
            continue

        rows.append((
            sym,
            m.total_trades,
            m.sharpe,
            m.profit_factor,
            m.win_rate * 100,
            m.max_drawdown.get("max_dd", 0.0) * 100,
            m.annual_return * 100,
            "",
        ))

    # Print table
    header = f"{'SYMBOL':<10}{'TRADES':>8}{'SHARPE':>10}{'PF':>8}{'WR%':>8}{'DD%':>8}{'ANN%':>10}  NOTE"
    print("\n" + "=" * 80)
    print(header)
    print("=" * 80)
    for r in rows:
        sym, trades, sharpe, pf, wr, dd, ann, note = r
        print(f"{sym:<10}{trades:>8}{sharpe:>10.2f}{pf:>8.2f}{wr:>8.1f}{dd:>8.1f}{ann:>10.1f}  {note}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
