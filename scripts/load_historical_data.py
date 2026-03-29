"""
load_historical_data.py — Fetch 1 year of 5M BTC/ETH candles from Binance
and store them in the local SQLite database.

Uses ccxt's public Binance endpoint — no API key required.

Usage (from project root, with .venv active):
    python scripts/load_historical_data.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd
from loguru import logger

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data.storage import Storage


def fetch_ohlcv(exchange, symbol_ccxt: str, timeframe: str, days: int) -> pd.DataFrame:
    """Fetch full history via paginated ccxt calls."""
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_bars = []

    logger.info("Fetching {} {} candles from {} ...", symbol_ccxt, timeframe, exchange.id)

    while True:
        bars = exchange.fetch_ohlcv(symbol_ccxt, timeframe, since=since_ms, limit=1000)
        if not bars:
            break
        all_bars.extend(bars)
        last_ts = bars[-1][0]
        since_ms = last_ts + 1  # next page starts after last bar
        logger.debug("  fetched {} bars, total so far: {}", len(bars), len(all_bars))
        if len(bars) < 1000:
            break  # last page

    if not all_bars:
        return pd.DataFrame()

    df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def main():
    storage = Storage("data/lumare.db")

    # Try exchanges in order until one works (Binance is geo-blocked in some regions)
    exchange = None
    for ex_id, ex_opts in [
        ("bybit",     {"enableRateLimit": True}),
        ("binanceus", {"enableRateLimit": True}),
        ("kraken",    {"enableRateLimit": True}),
    ]:
        try:
            candidate = getattr(ccxt, ex_id)(ex_opts)
            candidate.load_markets()
            exchange = candidate
            logger.info("Using exchange: {}", ex_id)
            break
        except Exception as exc:
            logger.warning("Exchange {} unavailable: {}", ex_id, exc)

    if exchange is None:
        logger.error("No exchange available. Check your internet connection or VPN.")
        return

    # Map symbol names per exchange
    btc_sym = "BTC/USDT:USDT" if exchange.id == "bybit" else "BTC/USDT"
    eth_sym = "ETH/USDT:USDT" if exchange.id == "bybit" else "ETH/USDT"

    pairs = [
        (btc_sym, "BTCUSDT"),
        (eth_sym, "ETHUSDT"),
    ]

    for symbol_ccxt, symbol_db in pairs:
        df = fetch_ohlcv(exchange, symbol_ccxt, "5m", days=365)
        if df.empty:
            logger.error("No data returned for {}", symbol_ccxt)
            continue

        count = storage.store_candles(symbol_db, "5M", df)
        logger.success(
            "Stored {:,} 5M candles for {} ({}–{})",
            count,
            symbol_db,
            df["timestamp"].iloc[0].date(),
            df["timestamp"].iloc[-1].date(),
        )

    logger.info("Done. Database: data/lumare.db")


if __name__ == "__main__":
    main()
