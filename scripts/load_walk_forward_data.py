"""
load_walk_forward_data.py — fetch real OHLCV history and store it in SQLite
so the replay engine can run walk-forward tests.

Crypto: Coinbase Exchange public API (no key)
Equities: yfinance

Stores 5M, 15M, 1H, 4H, 1D candles per symbol.

    python scripts/load_walk_forward_data.py
    python scripts/load_walk_forward_data.py --symbols BTC,ETH,SPY --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
logger.remove()
logger.add(lambda m: None, level="WARNING")

from backend.config.settings import SETTINGS
from backend.data.storage import Storage
from backend.data.crypto_feed import CryptoFeed
from backend.data.equities_feed import EquitiesFeed
from backend.core.asset_profiles import classify_symbol


# Coinbase / yfinance both cap deep intraday history. These are the
# realistic limits we ship with:
CRYPTO_5M_DAYS = 30   # 300 bars × 8min ≈ 2 days per page, but Coinbase rate-limits
EQUITY_5M_DAYS = 58   # yfinance hard cap for 5m intraday


async def _pull_crypto_paginated(symbol: str, timeframe: str, total_bars: int):
    """Pull deep Coinbase history by paginating end-times backwards.

    Coinbase caps at 300 bars per request, so for 30 days of 5m
    (~8640 bars) we need ~29 paginated requests.
    """
    import httpx
    from backend.data.crypto_feed import CryptoFeed

    pair = CryptoFeed._to_coinbase_pair(symbol)
    gran_map = {"5M": 300, "15M": 900, "1H": 3600, "1D": 86400}
    gran = gran_map.get(timeframe.upper())
    if gran is None:
        return pd.DataFrame()

    out = []
    seen_ts = set()
    end_dt = datetime.now(timezone.utc)
    page_seconds = 300 * gran  # 300 bars per page
    pages_needed = (total_bars + 299) // 300

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0),
        headers={"User-Agent": "lumare/1.0"},
    ) as client:
        for _ in range(min(pages_needed, 40)):  # hard cap to avoid abuse
            start_dt = end_dt - timedelta(seconds=page_seconds)
            url = (
                f"https://api.exchange.coinbase.com/products/{pair}/candles"
                f"?granularity={gran}"
                f"&start={start_dt.isoformat()}"
                f"&end={end_dt.isoformat()}"
            )
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                rows = resp.json()
            except Exception:
                break
            if not rows:
                break
            for r in rows:
                ts = int(r[0])
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                out.append(r)
            end_dt = start_dt - timedelta(seconds=1)
            await asyncio.sleep(0.25)  # rate-limit polite

    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(
        out, columns=["time", "low", "high", "open", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["time"].astype(float), unit="s", utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True).tail(total_bars)
    return df


async def _pull_crypto(feed: CryptoFeed, symbol: str, timeframe: str, bars: int):
    # Use paginated pull for anything > 300 bars; otherwise the single-page
    # feed call.
    if bars > 300:
        return await _pull_crypto_paginated(symbol, timeframe, bars)
    df = await feed.get_ohlcv(symbol, timeframe, limit=bars)
    return df


async def _pull_equity(feed: EquitiesFeed, symbol: str, timeframe: str, days: int):
    """yfinance OHLCV via the equities_feed."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    # equities_feed uses "5min"/"15min"/etc. keys
    tf_map = {
        "5M": "5min",
        "15M": "15min",
        "1H": "1hour",
        "1D": "1day",
    }
    eq_tf = tf_map.get(timeframe.upper())
    if eq_tf is None:
        return pd.DataFrame()
    df = await feed.get_ohlcv(symbol, eq_tf, start.isoformat(), end.isoformat())
    return df


async def run(symbols: list[str], days: int):
    storage = Storage(SETTINGS.db_path)
    storage.init_db()
    crypto_feed = CryptoFeed()
    equity_feed = EquitiesFeed()

    timeframes_crypto = ["5M", "15M", "1H", "4H", "1D"]
    timeframes_equity = ["5M", "15M", "1H", "1D"]  # yfinance has no 4H

    print(f"Loading {len(symbols)} symbols × multiple timeframes "
          f"into {SETTINGS.db_path}")

    for sym in symbols:
        klass = classify_symbol(sym)
        print(f"\n>>> {sym} ({klass})")
        if klass == "crypto":
            for tf in timeframes_crypto:
                # Real target — not capped at 300; pagination handles it.
                limit = int(days * 24 * 60 / {
                    "5M": 5, "15M": 15, "1H": 60, "4H": 240, "1D": 1440,
                }[tf])
                limit = max(limit, 50)
                try:
                    df = await _pull_crypto(crypto_feed, sym, tf, limit)
                    if df is None or df.empty:
                        print(f"  {tf:3s}: empty")
                        continue
                    storage.store_candles(sym, tf, df)
                    print(f"  {tf:3s}: stored {len(df)} bars  "
                          f"(close=${float(df['close'].iloc[-1]):.2f})")
                except Exception as e:
                    print(f"  {tf:3s}: ERROR {e}")
        else:
            for tf in timeframes_equity:
                try:
                    df = await _pull_equity(equity_feed, sym, tf, days)
                    if df is None or df.empty:
                        print(f"  {tf:3s}: empty")
                        continue
                    storage.store_candles(sym, tf, df)
                    print(f"  {tf:3s}: stored {len(df)} bars  "
                          f"(close=${float(df['close'].iloc[-1]):.2f})")
                except Exception as e:
                    print(f"  {tf:3s}: ERROR {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbols",
        default="BTC,ETH,SOL,SPY,QQQ,AAPL,NVDA,MSFT,TSLA",
    )
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    asyncio.run(run(syms, args.days))


if __name__ == "__main__":
    main()
