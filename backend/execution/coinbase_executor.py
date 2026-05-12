"""
coinbase_executor.py — live execution against Coinbase Advanced Trade.

Drop-in replacement for PaperSimulator that routes orders to a real
broker. Honored ONLY when:
  * env var ``LUMARE_ALLOW_LIVE=1`` (hard safety gate)
  * env vars ``COINBASE_API_KEY`` and ``COINBASE_API_SECRET`` are set
  * the bot was started with ``mode="live"``

Coinbase Advanced Trade documentation:
  https://docs.cloud.coinbase.com/advanced-trade-api/docs/

Interface (matches PaperSimulator so autobot can swap them):
  - submit_order(symbol, side, price, quantity, leverage) -> Order
  - process_bar(symbol, bar) -> updates cached prices / unrealised P&L
  - update_market_state(symbol, price, adv, atr) -> caches price
  - get_portfolio() -> {total_value, cash, num_positions, unrealised_pnl, realised_pnl}
  - positions: Dict[str, SimPosition]
  - cash, _prices: like PaperSimulator
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from backend.execution.paper_simulator import (
    Order, OrderSide, OrderStatus, OrderType, SimPosition,
)


COINBASE_BASE = "https://api.coinbase.com"


def is_live_trading_allowed() -> bool:
    """Hard safety check. Real-money orders are only ever attempted
    when this returns True."""
    return os.getenv("LUMARE_ALLOW_LIVE", "0") == "1"


def have_coinbase_credentials() -> bool:
    return bool(
        os.getenv("COINBASE_API_KEY") and os.getenv("COINBASE_API_SECRET")
    )


# ---------------------------------------------------------------------------
# Symbol mapping (bot → Coinbase product_id)
# ---------------------------------------------------------------------------

def _to_product_id(symbol: str) -> str:
    """BTC / BTCUSDT / BTC-USD all → BTC-USD on Coinbase spot.

    Mirrors the logic in crypto_feed._to_coinbase_pair so the data feed
    and the executor agree on instrument identity.
    """
    s = symbol.upper().replace("-PERP", "").replace("_PERP", "")
    if "-" in s or "/" in s:
        parts = s.replace("/", "-").split("-")
        base = parts[0]
        return f"{base}-USD"
    for suf in ("USDT", "USDC", "BUSD", "DAI", "USD"):
        if s.endswith(suf) and len(s) > len(suf):
            return f"{s[: -len(suf)]}-USD"
    return f"{s}-USD"


# ---------------------------------------------------------------------------
# CoinbaseExecutor
# ---------------------------------------------------------------------------

class CoinbaseExecutor:
    """Live-execution counterpart to PaperSimulator.

    Falls back to read-only mode (no orders, but still tracks prices)
    when credentials are missing or ``LUMARE_ALLOW_LIVE`` is not set.
    This means the bot can be started with mode="live" against an
    unconfigured environment and *not* place orders by accident.
    """

    def __init__(self, settings=None, initial_capital: float = 100_000.0):
        self.settings = settings
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, SimPosition] = {}
        self.open_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self._prices: Dict[str, float] = {}

        self.api_key = os.getenv("COINBASE_API_KEY", "")
        self.api_secret = os.getenv("COINBASE_API_SECRET", "")
        self.live_armed = is_live_trading_allowed() and bool(self.api_key)

        self._client: Optional[httpx.Client] = None

        mode = "ARMED (real money)" if self.live_armed else "DISARMED (read-only)"
        logger.warning(f"CoinbaseExecutor initialised — {mode}")

    # ------------------------------------------------------------------ auth
    def _signed_headers(
        self, method: str, path: str, body: str = ""
    ) -> Dict[str, str]:
        ts = str(int(time.time()))
        message = f"{ts}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=COINBASE_BASE,
                timeout=httpx.Timeout(10.0, connect=4.0),
            )
        return self._client

    # ----------------------------------------------------------- order entry
    def submit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        leverage: float = 1.0,
        order_type: str = "LIMIT",
    ) -> Order:
        """Place a limit order on Coinbase Advanced Trade.

        SAFETY:
          * If live trading is not armed, the order is returned with
            status REJECTED and reason "live trading disarmed". No HTTP
            request is made. This is the primary safety gate.
          * MARKET orders are still rejected by policy (same as
            PaperSimulator) — we only ship limits to avoid runaway
            slippage on illiquid books.
        """
        order_id = str(uuid.uuid4())
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType.LIMIT if order_type.upper() == "LIMIT" else OrderType.MARKET,
            price=price,
            quantity=quantity,
            leverage=leverage,
            status=OrderStatus.PENDING,
        )

        if order.order_type == OrderType.MARKET:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Market orders disabled. Use LIMIT."
            self.order_history.append(order)
            return order

        if not self.live_armed:
            order.status = OrderStatus.REJECTED
            order.reject_reason = (
                "Live trading disarmed (need LUMARE_ALLOW_LIVE=1 and "
                "COINBASE_API_KEY/SECRET set)"
            )
            self.order_history.append(order)
            logger.warning(
                f"CoinbaseExecutor refused order {symbol} {side} "
                f"qty={quantity} @ {price}: disarmed"
            )
            return order

        product_id = _to_product_id(symbol)
        body_dict = {
            "client_order_id": order_id,
            "product_id": product_id,
            "side": "BUY" if side.upper() == "BUY" else "SELL",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{quantity:.8f}",
                    "limit_price": f"{price:.2f}",
                    "post_only": False,
                }
            },
        }
        body = json.dumps(body_dict, separators=(",", ":"))
        path = "/api/v3/brokerage/orders"

        try:
            resp = self._http().post(
                path,
                content=body,
                headers=self._signed_headers("POST", path, body),
            )
            data = resp.json() if resp.content else {}
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"network: {exc}"
            self.order_history.append(order)
            logger.error(f"Coinbase order POST failed: {exc}")
            return order

        success = data.get("success", False)
        if success:
            order.status = OrderStatus.OPEN
            order.metadata = {
                "broker_order_id": data.get("success_response", {}).get(
                    "order_id"
                ),
                "raw": data,
            }
            self.open_orders[order.order_id] = order
            logger.info(
                f"Coinbase order placed {symbol} {side} qty={quantity} "
                f"@ {price} broker_id={order.metadata['broker_order_id']}"
            )
        else:
            err = data.get("error_response", {}) or data
            order.status = OrderStatus.REJECTED
            order.reject_reason = (
                err.get("message")
                or err.get("error")
                or json.dumps(err)[:200]
            )
            logger.warning(
                f"Coinbase rejected order {symbol}: {order.reject_reason}"
            )

        self.order_history.append(order)
        return order

    # ------------------------------------------------------- market state
    def update_market_state(
        self, symbol: str, price: float, adv: float = 0, atr: float = 0
    ):
        self._prices[symbol] = price

    def process_bar(self, symbol: str, bar: dict):
        """Refresh price cache + sync fills from Coinbase.

        Paper-sim filled orders locally inside this method. Here we
        instead query Coinbase for any fills since the last cycle and
        update local position/cash to match the broker view.
        """
        self._prices[symbol] = float(bar.get("close", 0))

        if not self.live_armed:
            return

        # Sync fills for this symbol (cheap polling — Coinbase doesn't
        # support webhooks for retail).
        try:
            self._sync_fills_for(symbol)
        except Exception as exc:
            logger.debug(f"Fill sync error for {symbol}: {exc}")

        # Update unrealised P&L on any open position.
        pos = self.positions.get(symbol)
        if pos:
            cp = self._prices[symbol]
            mult = 1 if pos.side == OrderSide.BUY else -1
            pos.unrealized_pnl = (
                mult * (cp - pos.avg_entry_price) * pos.quantity * pos.leverage
            )

    def _sync_fills_for(self, symbol: str):
        """Poll Coinbase for new fills on our orders for this symbol and
        materialise them into local SimPosition state."""
        product_id = _to_product_id(symbol)
        path = (
            f"/api/v3/brokerage/orders/historical/fills"
            f"?product_id={product_id}&limit=25"
        )
        resp = self._http().get(
            path, headers=self._signed_headers("GET", path)
        )
        if resp.status_code != 200:
            return
        fills = resp.json().get("fills", []) or []
        for f in fills:
            order_client_id = f.get("client_order_id") or ""
            if order_client_id not in self.open_orders:
                continue  # not one we placed in this session
            qty = float(f.get("size", 0) or 0)
            price = float(f.get("price", 0) or 0)
            side = OrderSide(f.get("side", "BUY").upper())

            # Walk into / out of the position
            pos = self.positions.get(symbol)
            if pos is None:
                self.positions[symbol] = SimPosition(
                    symbol=symbol, side=side, quantity=qty,
                    avg_entry_price=price, leverage=1.0,
                )
                self.cash -= price * qty
            else:
                if pos.side == side:
                    total = pos.quantity + qty
                    pos.avg_entry_price = (
                        pos.avg_entry_price * pos.quantity + price * qty
                    ) / total
                    pos.quantity = total
                    self.cash -= price * qty
                else:
                    # Closing side
                    pnl_per_unit = (
                        price - pos.avg_entry_price
                        if pos.side == OrderSide.BUY
                        else pos.avg_entry_price - price
                    )
                    pnl = pnl_per_unit * min(qty, pos.quantity)
                    pos.realized_pnl += pnl
                    self.cash += price * qty + pnl
                    pos.quantity -= qty
                    if pos.quantity <= 1e-9:
                        del self.positions[symbol]

    # --------------------------------------------------------- portfolio
    def get_portfolio(self) -> Dict[str, Any]:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        realized = sum(p.realized_pnl for p in self.positions.values())
        notional = sum(
            p.quantity * self._prices.get(p.symbol, p.avg_entry_price)
            for p in self.positions.values()
        )
        return {
            "total_value": self.cash + notional + unrealized,
            "cash": self.cash,
            "num_positions": len(self.positions),
            "positions": {s: p for s, p in self.positions.items()},
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
        }

    # -------------------------------------------------------- account info
    def sync_account_balance(self):
        """Pull cash USD balance from Coinbase. Call once at startup."""
        if not self.live_armed:
            return
        path = "/api/v3/brokerage/accounts"
        try:
            resp = self._http().get(
                path, headers=self._signed_headers("GET", path)
            )
            data = resp.json()
        except Exception as exc:
            logger.warning(f"Account sync failed: {exc}")
            return
        accts = data.get("accounts", []) or []
        for a in accts:
            cur = a.get("currency", "")
            if cur == "USD":
                bal = a.get("available_balance", {}).get("value", "0")
                try:
                    self.cash = float(bal)
                    self.initial_capital = float(bal)
                    logger.info(
                        f"Coinbase USD balance: ${self.cash:,.2f}"
                    )
                except Exception:
                    pass

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None
