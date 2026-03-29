"""
Lumare WebSocket — Real-time price streaming.

Pushes live price ticks to connected frontend clients.
Supports multiple symbols (crypto + equities) via a single connection.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts price updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._running = False
        self._task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WS client connected ({len(self.active_connections)} total)")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WS client disconnected ({len(self.active_connections)} total)")

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        if not self.active_connections:
            return
        payload = json.dumps(message)
        disconnected = set()
        for ws in self.active_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.active_connections.discard(ws)

    async def start_price_stream(self, engine):
        """Background task: poll prices and push to all clients."""
        if self._running:
            return
        self._running = True
        logger.info("WebSocket price stream started")

        while self._running:
            try:
                if not self.active_connections:
                    await asyncio.sleep(1)
                    continue

                prices = await _fetch_all_prices(engine)
                if prices:
                    await self.broadcast({
                        "type": "prices",
                        "data": prices,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # Stream at ~2 second intervals for crypto, 5s for equities
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"WS price stream error: {exc}")
                await asyncio.sleep(5)

        self._running = False
        logger.info("WebSocket price stream stopped")

    def stop(self):
        self._running = False


# Singleton
ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Kraken symbol mapping (Lumare symbol -> Kraken pair)
# ---------------------------------------------------------------------------
_KRAKEN_MAP = {
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "SOLUSDT": "SOLUSD",
    "XRPUSDT": "XRPUSD",
    "DOGEUSDT": "XDGUSD",
    "ADAUSDT": "ADAUSD",
    "AVAXUSDT": "AVAXUSD",
    "LINKUSDT": "LINKUSD",
    "DOTUSDT": "DOTUSD",
    "MATICUSDT": "MATICUSD",
}

# Reusable httpx client
_http_client: "httpx.AsyncClient | None" = None


async def _get_http_client():
    global _http_client
    if _http_client is None or _http_client.is_closed:
        import httpx
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0))
    return _http_client


async def _fetch_kraken_prices(client, symbols: list[str]) -> dict[str, dict]:
    """
    Fetch tickers from Kraken public API (free, no key, US-legal).
    Returns a dict keyed by Lumare symbol.
    """
    # Build Kraken pair list
    kraken_pairs = []
    kraken_to_lumare = {}
    for sym in symbols:
        kp = _KRAKEN_MAP.get(sym)
        if kp:
            kraken_pairs.append(kp)
            kraken_to_lumare[kp] = sym

    if not kraken_pairs:
        return {}

    try:
        resp = await client.get(
            "https://api.kraken.com/0/public/Ticker",
            params={"pair": ",".join(kraken_pairs)},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("error") and len(data["error"]) > 0:
            logger.warning(f"Kraken API errors: {data['error']}")
            return {}

        result = {}
        for kraken_key, ticker in data.get("result", {}).items():
            # Kraken returns keys like XXBTZUSD or XBTUSD — match flexibly
            lumare_sym = None
            for kp, ls in kraken_to_lumare.items():
                if kp in kraken_key or kraken_key.endswith(kp):
                    lumare_sym = ls
                    break

            if not lumare_sym:
                continue

            last = float(ticker["c"][0])  # c = last trade [price, volume]
            open_price = float(ticker["o"])  # o = today's opening price
            high = float(ticker["h"][1])  # h = [today, 24h]
            low = float(ticker["l"][1])  # l = [today, 24h]
            volume = float(ticker["v"][1])  # v = [today, 24h]
            bid = float(ticker["b"][0])  # b = [price, whole lot vol, lot vol]
            ask = float(ticker["a"][0])  # a = [price, whole lot vol, lot vol]

            change_pct = ((last - open_price) / open_price * 100) if open_price else 0

            result[lumare_sym] = {
                "symbol": lumare_sym,
                "price": round(last, 2),
                "change_24h": round(change_pct, 2),
                "volume_24h": round(volume * last, 2),  # Convert to USD notional
                "high_24h": round(high, 2),
                "low_24h": round(low, 2),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "asset_class": "crypto",
            }

        if result:
            logger.debug(f"Kraken: fetched {len(result)} tickers")
        return result

    except Exception as exc:
        logger.warning(f"Kraken ticker fetch failed: {exc}")
        return {}


async def _fetch_coingecko_prices(client, symbols: list[str]) -> dict[str, dict]:
    """
    Fallback: CoinGecko free API (no key, US-legal, rate-limited).
    """
    cg_ids = {
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "SOLUSDT": "solana",
        "XRPUSDT": "ripple",
        "DOGEUSDT": "dogecoin",
        "ADAUSDT": "cardano",
        "AVAXUSDT": "avalanche-2",
        "LINKUSDT": "chainlink",
        "DOTUSDT": "polkadot",
        "MATICUSDT": "matic-network",
    }

    ids_needed = [cg_ids[s] for s in symbols if s in cg_ids]
    if not ids_needed:
        return {}

    id_to_lumare = {v: k for k, v in cg_ids.items() if k in symbols}

    try:
        resp = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": ",".join(ids_needed),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        result = {}
        for cg_id, info in data.items():
            lumare_sym = id_to_lumare.get(cg_id)
            if not lumare_sym:
                continue
            price = float(info.get("usd", 0))
            result[lumare_sym] = {
                "symbol": lumare_sym,
                "price": round(price, 2),
                "change_24h": round(float(info.get("usd_24h_change", 0)), 2),
                "volume_24h": round(float(info.get("usd_24h_vol", 0)), 2),
                "high_24h": None,
                "low_24h": None,
                "bid": None,
                "ask": None,
                "asset_class": "crypto",
            }

        if result:
            logger.debug(f"CoinGecko: fetched {len(result)} tickers")
        return result

    except Exception as exc:
        logger.warning(f"CoinGecko ticker fetch failed: {exc}")
        return {}


async def _fetch_all_prices(engine) -> list:
    """Fetch latest prices from all configured feeds."""
    prices = []
    crypto_pairs = engine.settings.instruments.crypto_pairs
    client = await _get_http_client()

    # ---- Crypto: Kraken (primary) -> CoinGecko (fallback) ----
    kraken_data = await _fetch_kraken_prices(client, crypto_pairs)

    # Find any symbols Kraken didn't cover
    missing = [s for s in crypto_pairs if s not in kraken_data]

    coingecko_data = {}
    if missing:
        coingecko_data = await _fetch_coingecko_prices(client, missing)

    for symbol in crypto_pairs:
        if symbol in kraken_data:
            prices.append(kraken_data[symbol])
        elif symbol in coingecko_data:
            prices.append(coingecko_data[symbol])
        else:
            # Last resort: use CryptoFeed mock (instant, no network)
            t = engine.crypto_feed._generate_mock_ticker(symbol)
            prices.append({
                "symbol": symbol,
                "price": float(t.get("last_price", 0)),
                "change_24h": float(t.get("change_24h_pct", 0)),
                "volume_24h": float(t.get("volume_24h", 0)),
                "high_24h": float(t.get("high_24h", 0)),
                "low_24h": float(t.get("low_24h", 0)),
                "bid": float(t.get("bid", 0)),
                "ask": float(t.get("ask", 0)),
                "asset_class": "crypto",
            })

    # ---- Equity prices via Polygon or fallback ----
    equity_symbols = engine.settings.instruments.equity_symbols
    if equity_symbols and hasattr(engine, "equities_feed"):
        for symbol in equity_symbols:
            try:
                quote = await engine.equities_feed.get_quote(symbol)
                if quote:
                    prices.append({
                        "symbol": symbol,
                        "price": float(quote.get("price", 0)),
                        "change_24h": float(quote.get("change_pct", 0)) if quote.get("change_pct") else None,
                        "volume_24h": float(quote.get("volume", 0)) if quote.get("volume") else None,
                        "high_24h": float(quote.get("high", 0)) if quote.get("high") else None,
                        "low_24h": float(quote.get("low", 0)) if quote.get("low") else None,
                        "prev_close": float(quote.get("prev_close", 0)) if quote.get("prev_close") else None,
                        "asset_class": "equity",
                    })
            except Exception as exc:
                logger.debug(f"WS equity price fetch failed for {symbol}: {exc}")

    return prices
