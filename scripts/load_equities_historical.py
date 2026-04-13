"""
load_equities_historical.py — Fetch 5M OHLCV for Mag 7 + SPY + QQQ via
yfinance bulk download and insert into data/lumare.db.

yfinance limit: 5m interval → 60 days of history max.
We pull the full 60 days for a multi-asset backtest sweep.

Usage (from project root, with .venv active):
    python scripts/load_equities_historical.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data.storage import Storage


SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",  # Mag 7
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
]


def _normalize_bulk(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Extract a single symbol's OHLCV frame from a bulk yf.download result."""
    if df is None or df.empty:
        return pd.DataFrame()

    # Bulk download returns a MultiIndex column frame when tickers is a list.
    if isinstance(df.columns, pd.MultiIndex):
        # columns are (field, ticker)
        try:
            sub = df.xs(symbol, axis=1, level=1)
        except KeyError:
            return pd.DataFrame()
    else:
        sub = df

    sub = sub.reset_index()
    ts_col = "Datetime" if "Datetime" in sub.columns else "Date"
    rename = {
        ts_col: "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    sub = sub.rename(columns=rename)

    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in cols if c not in sub.columns]
    if missing:
        logger.warning("{}: missing columns {}", symbol, missing)
        return pd.DataFrame()

    sub = sub[cols].dropna(subset=["open", "high", "low", "close"])
    if sub["timestamp"].dt.tz is None:
        sub["timestamp"] = sub["timestamp"].dt.tz_localize("UTC")
    else:
        sub["timestamp"] = sub["timestamp"].dt.tz_convert("UTC")
    return sub.sort_values("timestamp").reset_index(drop=True)


def main():
    storage = Storage("data/lumare.db")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=59)  # yfinance hard cap is ~60 days for 5m
    start_s = start.strftime("%Y-%m-%d")
    end_s = (end + timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info(
        "Bulk-fetching 5m OHLCV for {} symbols: {} → {}",
        len(SYMBOLS), start_s, end_s,
    )

    raw = yf.download(
        tickers=" ".join(SYMBOLS),
        interval="5m",
        start=start_s,
        end=end_s,
        group_by="column",
        auto_adjust=False,
        prepost=False,
        threads=True,
        progress=False,
    )

    if raw is None or raw.empty:
        logger.error("yfinance returned nothing. Aborting.")
        return

    total_rows = 0
    for sym in SYMBOLS:
        df = _normalize_bulk(raw, sym)
        if df.empty:
            logger.warning("{}: no bars returned", sym)
            continue

        count = storage.store_candles(sym, "5M", df)
        total_rows += count
        logger.success(
            "Stored {:,} 5M candles for {} ({} → {})",
            count, sym,
            df["timestamp"].iloc[0].strftime("%Y-%m-%d"),
            df["timestamp"].iloc[-1].strftime("%Y-%m-%d"),
        )

    logger.info("Done. Inserted {:,} rows total into data/lumare.db", total_rows)


if __name__ == "__main__":
    main()
