"""
load_equity_history.py — pull deep equity history for backtest tuning.

yfinance caps 5m intraday at 60 days. For 1-year history we use 1H
which yfinance supports back to 2 years. The replay engine's
CandleAggregator can roll up from any base TF, so 1H is fine.

Loads: 5M (60 days), 1H (730 days), 1D (5 years) per symbol.

Run:
  python scripts/load_equity_history.py
  python scripts/load_equity_history.py --symbols SPY,QQQ,AAPL,NVDA,TSLA,MSFT,META,GOOGL
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
logger.remove()
logger.add(lambda m: None, level="ERROR")

import yfinance as yf
import pandas as pd

from backend.config.settings import SETTINGS
from backend.data.storage import Storage


# yfinance interval -> our internal timeframe label + max lookback
INTERVAL_PLAN = [
    ("5m",  "5M",  59),    # yfinance hard cap is 60 days
    ("15m", "15M", 59),
    ("1h",  "1H",  730),   # 2 years
    ("1d",  "1D",  1825),  # 5 years
]


def _pull_yf(symbol: str, interval: str, days: int) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    df = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance returns MultiIndex columns for some intervals → flatten
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index()
    # Normalise column names
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={
        ts_col: "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    return df


def run(symbols: list[str]):
    storage = Storage(SETTINGS.db_path)
    storage.init_db()

    for sym in symbols:
        print(f"\n>>> {sym}")
        for interval, tf_label, days in INTERVAL_PLAN:
            try:
                df = _pull_yf(sym, interval, days)
                if df.empty:
                    print(f"  {tf_label:3s} ({interval}, {days}d): empty")
                    continue
                storage.store_candles(sym, tf_label, df)
                print(
                    f"  {tf_label:3s} ({interval}, {days}d): "
                    f"stored {len(df)} bars "
                    f"({df.timestamp.min().date()} -> {df.timestamp.max().date()}, "
                    f"close=${float(df.close.iloc[-1]):.2f})"
                )
            except Exception as e:
                print(f"  {tf_label:3s} ({interval}, {days}d): ERROR {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbols",
        default="SPY,QQQ,AAPL,NVDA,TSLA,MSFT,META,GOOGL,AMZN,AMD",
    )
    args = p.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    run(syms)


if __name__ == "__main__":
    main()
