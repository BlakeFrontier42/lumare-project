"""
alpaca_executor.py — US Equities Execution via Alpaca API
Phase 2 executor for stocks and options.

SAFETY: Market orders DISABLED. Kill switch enforced. Live mode gated
by LUMARE_ALLOW_LIVE=1.

Two surfaces:
  * AlpacaExecutor — the original direct API (place_limit_order, etc.)
    used by manual/REST callers.
  * AutobotAlpacaExecutor (at bottom) — autobot-compatible drop-in
    mirror of PaperSimulator / CoinbaseExecutor (submit_order,
    process_bar, positions: Dict[str, SimPosition], get_portfolio).
"""

import os
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from backend.config.settings import SETTINGS, Settings


@dataclass
class AlpacaOrderResponse:
    success: bool
    order_id: Optional[str] = None
    status: str = ""
    symbol: str = ""
    side: str = ""
    price: float = 0.0
    quantity: float = 0.0
    error: str = ""
    raw_response: Dict = None


class AlpacaExecutor:
    """
    Live execution on Alpaca for US equities.
    Uses Alpaca REST API v2 (paper or live based on URL).
    """

    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"
    DATA_URL = "https://data.alpaca.markets"

    def __init__(self, settings: Settings = None, paper: bool = True):
        self.settings = settings or SETTINGS
        self.base_url = self.PAPER_URL if paper else self.LIVE_URL
        # Settings.api.ALPACA_KEY may be unset — also accept env vars.
        self.api_key = getattr(
            getattr(self.settings, "api", None), "ALPACA_KEY", ""
        ) or os.getenv("ALPACA_API_KEY", "")
        self.api_secret = getattr(
            getattr(self.settings, "api", None), "ALPACA_SECRET", ""
        ) or os.getenv("ALPACA_API_SECRET", "")
        self._kill_switch = False
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.api_secret,
                "Content-Type": "application/json",
            },
        )

    def _request(self, method: str, path: str, data: Dict = None) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            if method.upper() == "GET":
                resp = self._client.get(url)
            elif method.upper() == "POST":
                resp = self._client.post(url, json=data)
            elif method.upper() == "DELETE":
                resp = self._client.delete(url)
            else:
                raise ValueError(f"Unsupported method: {method}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except httpx.HTTPStatusError as e:
            logger.error(f"Alpaca API error: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Alpaca request failed: {e}")
            raise

    # ─── Orders ─────────────────────────────────────────────

    def place_limit_order(self, symbol: str, side: str, price: float,
                          quantity: float, time_in_force: str = "day") -> AlpacaOrderResponse:
        """Place a limit order on Alpaca."""
        if self._kill_switch:
            return AlpacaOrderResponse(success=False, error="Kill switch active")

        try:
            data = {
                "symbol": symbol,
                "qty": str(quantity),
                "side": side.lower(),
                "type": "limit",
                "limit_price": str(price),
                "time_in_force": time_in_force,
            }
            result = self._request("POST", "/v2/orders", data)
            return AlpacaOrderResponse(
                success=True,
                order_id=result.get("id"),
                status=result.get("status", ""),
                symbol=symbol, side=side,
                price=price, quantity=quantity,
                raw_response=result,
            )
        except Exception as e:
            return AlpacaOrderResponse(success=False, error=str(e))

    def place_market_order(self, symbol: str, side: str,
                           quantity: float) -> AlpacaOrderResponse:
        """DISABLED: Market orders violate execution policy."""
        logger.error("Market order attempted on Alpaca — BLOCKED")
        return AlpacaOrderResponse(
            success=False,
            error="Market orders DISABLED. Use limit orders only.",
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._request("DELETE", f"/v2/orders/{order_id}")
            return True
        except Exception:
            return False

    def cancel_all_orders(self) -> bool:
        try:
            self._request("DELETE", "/v2/orders")
            return True
        except Exception:
            return False

    def get_order_status(self, order_id: str) -> Dict:
        try:
            return self._request("GET", f"/v2/orders/{order_id}")
        except Exception as e:
            return {"error": str(e)}

    def get_open_orders(self) -> List[Dict]:
        try:
            return self._request("GET", "/v2/orders?status=open")
        except Exception:
            return []

    # ─── Positions ──────────────────────────────────────────

    def get_positions(self) -> List[Dict]:
        try:
            return self._request("GET", "/v2/positions")
        except Exception:
            return []

    def close_position(self, symbol: str) -> AlpacaOrderResponse:
        """Close entire position for a symbol."""
        try:
            result = self._request("DELETE", f"/v2/positions/{symbol}")
            return AlpacaOrderResponse(
                success=True, order_id=result.get("id"),
                status="closing", symbol=symbol,
                raw_response=result,
            )
        except Exception as e:
            return AlpacaOrderResponse(success=False, error=str(e))

    def close_all_positions(self) -> bool:
        try:
            self._request("DELETE", "/v2/positions")
            return True
        except Exception:
            return False

    # ─── Account ────────────────────────────────────────────

    def get_account(self) -> Dict:
        try:
            return self._request("GET", "/v2/account")
        except Exception as e:
            return {"error": str(e)}

    def is_market_open(self) -> bool:
        try:
            clock = self._request("GET", "/v2/clock")
            return clock.get("is_open", False)
        except Exception:
            return False

    def get_clock(self) -> Dict:
        try:
            return self._request("GET", "/v2/clock")
        except Exception as e:
            return {"error": str(e)}

    # ─── Kill Switch ────────────────────────────────────────

    def activate_kill_switch(self, reason: str):
        self._kill_switch = True
        logger.critical(f"ALPACA KILL SWITCH: {reason}")
        self.cancel_all_orders()

    def deactivate_kill_switch(self):
        self._kill_switch = False

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def close(self):
        self._client.close()


# ---------------------------------------------------------------------------
# Autobot-compatible wrapper
# ---------------------------------------------------------------------------

from backend.execution.paper_simulator import (
    Order, OrderSide, OrderStatus, OrderType, SimPosition,
)


def is_live_trading_allowed() -> bool:
    return os.getenv("LUMARE_ALLOW_LIVE", "0") == "1"


def have_alpaca_credentials() -> bool:
    return bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"))


class AutobotAlpacaExecutor:
    """Autobot-compatible facade over AlpacaExecutor.

    Provides the same interface as PaperSimulator and CoinbaseExecutor:
      - submit_order(symbol, side, price, quantity, leverage) -> Order
      - process_bar(symbol, bar) — refreshes price + syncs fills
      - update_market_state(symbol, price, adv, atr)
      - get_portfolio() -> dict
      - positions: Dict[str, SimPosition]
      - cash, _prices

    Triple-locked safety (matches Coinbase pattern):
      1. LUMARE_ALLOW_LIVE=1
      2. ALPACA_API_KEY + ALPACA_API_SECRET set
      3. mode="live" passed by autobot
    Without all three: every order returns REJECTED, no HTTP.

    Defaults to **paper-api.alpaca.markets** even when armed. To send
    real-money orders set ALPACA_BASE_URL=https://api.alpaca.markets.
    """

    def __init__(self, settings=None, initial_capital: float = 100_000.0):
        self.settings = settings or SETTINGS
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, SimPosition] = {}
        self.open_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self._prices: Dict[str, float] = {}

        self.live_armed = is_live_trading_allowed() and have_alpaca_credentials()
        # Default to paper Alpaca even when armed
        base_url = os.getenv(
            "ALPACA_BASE_URL", AlpacaExecutor.PAPER_URL
        )
        self.is_paper = "paper" in base_url
        self._inner: Optional[AlpacaExecutor] = None
        if self.live_armed:
            try:
                self._inner = AlpacaExecutor(
                    settings=self.settings,
                    paper=self.is_paper,
                )
                # Override base_url if user provided an explicit one
                if base_url != self._inner.base_url:
                    self._inner.base_url = base_url
            except Exception as exc:
                logger.error(f"Alpaca init failed, staying disarmed: {exc}")
                self.live_armed = False

        if not self.live_armed:
            mode = "DISARMED (no creds or LUMARE_ALLOW_LIVE not set)"
        elif self.is_paper:
            mode = f"ARMED PAPER ({base_url})"
        else:
            mode = f"ARMED LIVE — REAL MONEY ({base_url})"
        logger.warning(f"AutobotAlpacaExecutor initialised — {mode}")

    def submit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        leverage: float = 1.0,
        order_type: str = "LIMIT",
    ) -> Order:
        oid = str(uuid.uuid4())
        order = Order(
            order_id=oid,
            symbol=symbol.upper(),
            side=OrderSide(side.upper()),
            order_type=OrderType.LIMIT if order_type.upper() == "LIMIT" else OrderType.MARKET,
            price=price,
            quantity=quantity,
            leverage=1.0,
            status=OrderStatus.PENDING,
        )

        if order.order_type == OrderType.MARKET:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Market orders disabled. Use LIMIT."
            self.order_history.append(order)
            return order

        if not self.live_armed or self._inner is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = (
                "Live trading disarmed (need LUMARE_ALLOW_LIVE=1 + "
                "ALPACA_API_KEY/SECRET)"
            )
            self.order_history.append(order)
            return order

        try:
            qty_int = max(int(quantity), 1)  # Alpaca needs whole shares
            resp = self._inner.place_limit_order(
                symbol.upper(),
                "buy" if side.upper() == "BUY" else "sell",
                price,
                qty_int,
            )
            if resp.success:
                order.status = OrderStatus.OPEN
                order.metadata = {
                    "alpaca_order_id": resp.order_id,
                    "alpaca_status": resp.status,
                    "raw": resp.raw_response,
                }
                self.open_orders[oid] = order
            else:
                order.status = OrderStatus.REJECTED
                order.reject_reason = resp.error or "alpaca rejected"
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"network: {exc}"
            logger.error(f"Alpaca submit failed: {exc}")

        self.order_history.append(order)
        return order

    def update_market_state(
        self, symbol: str, price: float, adv: float = 0, atr: float = 0
    ):
        self._prices[symbol] = price

    def process_bar(self, symbol: str, bar: dict):
        self._prices[symbol] = float(bar.get("close", 0))
        if not self.live_armed or self._inner is None:
            return
        try:
            positions = self._inner.get_positions()
        except Exception:
            return
        self.positions = {}
        for p in positions:
            try:
                sym = p.get("symbol", "").upper()
                qty = float(p.get("qty", 0) or 0)
                if qty == 0:
                    continue
                self.positions[sym] = SimPosition(
                    symbol=sym,
                    side=OrderSide.BUY if qty > 0 else OrderSide.SELL,
                    quantity=abs(qty),
                    avg_entry_price=float(p.get("avg_entry_price", 0) or 0),
                    leverage=1.0,
                    unrealized_pnl=float(p.get("unrealized_pl", 0) or 0),
                )
            except Exception as exc:
                logger.debug(f"Skip malformed Alpaca position: {exc}")

    def get_portfolio(self) -> Dict[str, Any]:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
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
            "realized_pnl": 0,
        }

    def sync_account_balance(self):
        if not self.live_armed or self._inner is None:
            return
        try:
            acct = self._inner.get_account()
            cash = float(acct.get("cash", 0) or 0)
            if cash > 0:
                self.cash = cash
                self.initial_capital = cash
                logger.info(f"Alpaca cash balance: ${cash:,.2f}")
        except Exception as exc:
            logger.warning(f"Alpaca account sync failed: {exc}")

    def close(self):
        if self._inner is not None:
            self._inner.close()
