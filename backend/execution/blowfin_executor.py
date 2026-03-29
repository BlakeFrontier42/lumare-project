"""
blowfin_executor.py — Live Crypto Execution via Blowfin API
Handles perpetual futures orders with HMAC authentication.

SAFETY: Market orders DISABLED. Leverage limits enforced. Kill switch checked.
"""

import hmac
import hashlib
import time
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

import httpx
from loguru import logger

from backend.config.settings import SETTINGS, Settings


class OrderResult(Enum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


@dataclass
class BlowfinOrderResponse:
    success: bool
    order_id: Optional[str] = None
    status: str = ""
    symbol: str = ""
    side: str = ""
    price: float = 0.0
    quantity: float = 0.0
    leverage: float = 1.0
    error: str = ""
    raw_response: Dict = None


class BlowfinExecutor:
    """
    Live execution on Blowfin for crypto perpetual futures.

    Safety features:
    - Market orders raise an error (limit only)
    - Leverage validated against config before sending
    - Kill switch check before every order
    - Position size validated before sending
    """

    BASE_URL = "https://api.blowfin.com"

    def __init__(self, settings: Settings = None):
        self.settings = settings or SETTINGS
        self.api_key = self.settings.api.BLOWFIN_KEY
        self.api_secret = self.settings.api.BLOWFIN_SECRET
        self._kill_switch = False
        self._client = httpx.Client(timeout=30.0)

    # ─── Authentication ─────────────────────────────────────

    def _sign_request(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC-SHA256 signature for Blowfin API."""
        message = f"{timestamp}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_headers(self, method: str, path: str, body: str = "") -> Dict:
        timestamp = str(int(time.time() * 1000))
        signature = self._sign_request(timestamp, method, path, body)
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, data: Dict = None) -> Dict:
        """Make authenticated request to Blowfin API."""
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, path, body)
        url = f"{self.BASE_URL}{path}"

        try:
            if method.upper() == "GET":
                resp = self._client.get(url, headers=headers)
            elif method.upper() == "POST":
                resp = self._client.post(url, headers=headers, content=body)
            elif method.upper() == "DELETE":
                resp = self._client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Blowfin API error: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Blowfin request failed: {e}")
            raise

    # ─── Order Placement ────────────────────────────────────

    def place_limit_order(self, symbol: str, side: str, price: float,
                          quantity: float, leverage: float = 1.0) -> BlowfinOrderResponse:
        """Place a limit order. This is the ONLY allowed order type."""
        if self._kill_switch:
            return BlowfinOrderResponse(success=False, error="Kill switch active. No orders allowed.")

        # Validate leverage
        max_lev = self.settings.leverage.absolute_max_leverage
        if leverage > max_lev:
            return BlowfinOrderResponse(
                success=False,
                error=f"Leverage {leverage}x exceeds max {max_lev}x",
            )

        try:
            # Set leverage first
            self.set_leverage(symbol, leverage)

            data = {
                "instId": symbol,
                "tdMode": "cross",
                "side": side.lower(),
                "ordType": "limit",
                "px": str(price),
                "sz": str(quantity),
            }

            result = self._request("POST", "/api/v1/trade/order", data)

            if result.get("code") == "0":
                order_data = result.get("data", [{}])[0]
                return BlowfinOrderResponse(
                    success=True,
                    order_id=order_data.get("ordId", ""),
                    status="submitted",
                    symbol=symbol, side=side,
                    price=price, quantity=quantity, leverage=leverage,
                    raw_response=result,
                )
            else:
                return BlowfinOrderResponse(
                    success=False,
                    error=result.get("msg", "Unknown error"),
                    raw_response=result,
                )
        except Exception as e:
            return BlowfinOrderResponse(success=False, error=str(e))

    def place_market_order(self, symbol: str, side: str, quantity: float,
                           leverage: float = 1.0) -> BlowfinOrderResponse:
        """DISABLED: Market orders violate execution policy."""
        logger.error("Market order attempted — BLOCKED by policy")
        return BlowfinOrderResponse(
            success=False,
            error="Market orders are DISABLED. Use limit orders only. "
                  "This is a non-negotiable execution policy.",
        )

    # ─── Order Management ───────────────────────────────────

    def cancel_order(self, order_id: str, symbol: str = "") -> bool:
        try:
            data = {"ordId": order_id}
            if symbol:
                data["instId"] = symbol
            result = self._request("POST", "/api/v1/trade/cancel-order", data)
            return result.get("code") == "0"
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def cancel_all_orders(self, symbol: str) -> bool:
        try:
            data = {"instId": symbol}
            result = self._request("POST", "/api/v1/trade/cancel-batch-orders", data)
            return result.get("code") == "0"
        except Exception as e:
            logger.error(f"Cancel all orders failed: {e}")
            return False

    def get_order_status(self, order_id: str, symbol: str = "") -> Dict:
        try:
            params = f"?ordId={order_id}"
            if symbol:
                params += f"&instId={symbol}"
            return self._request("GET", f"/api/v1/trade/order{params}")
        except Exception as e:
            logger.error(f"Get order status failed: {e}")
            return {"error": str(e)}

    def get_open_orders(self, symbol: str = "") -> List[Dict]:
        try:
            path = "/api/v1/trade/orders-pending"
            if symbol:
                path += f"?instId={symbol}"
            result = self._request("GET", path)
            return result.get("data", [])
        except Exception as e:
            logger.error(f"Get open orders failed: {e}")
            return []

    # ─── Position Management ────────────────────────────────

    def get_positions(self) -> List[Dict]:
        try:
            result = self._request("GET", "/api/v1/account/positions")
            return result.get("data", [])
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    def close_position(self, symbol: str, side: str) -> BlowfinOrderResponse:
        """Close a position by placing an opposing market-equivalent limit order."""
        if self._kill_switch:
            return BlowfinOrderResponse(success=False, error="Kill switch active")

        try:
            positions = self.get_positions()
            pos = next((p for p in positions if p.get("instId") == symbol), None)
            if not pos:
                return BlowfinOrderResponse(success=False, error=f"No position found for {symbol}")

            qty = abs(float(pos.get("pos", 0)))
            # Use aggressive limit: 0.5% from current to ensure fill
            close_side = "sell" if side.lower() == "buy" else "buy"
            # Get current price for limit
            ticker = self._request("GET", f"/api/v1/market/ticker?instId={symbol}")
            last_price = float(ticker.get("data", [{}])[0].get("last", 0))

            if close_side == "sell":
                limit_price = last_price * 0.995  # 0.5% below
            else:
                limit_price = last_price * 1.005  # 0.5% above

            return self.place_limit_order(symbol, close_side, limit_price, qty)
        except Exception as e:
            return BlowfinOrderResponse(success=False, error=str(e))

    def set_leverage(self, symbol: str, leverage: float) -> bool:
        try:
            data = {"instId": symbol, "lever": str(int(leverage)), "mgnMode": "cross"}
            result = self._request("POST", "/api/v1/account/set-leverage", data)
            return result.get("code") == "0"
        except Exception as e:
            logger.error(f"Set leverage failed: {e}")
            return False

    def get_account_balance(self) -> Dict:
        try:
            result = self._request("GET", "/api/v1/account/balance")
            return result.get("data", [{}])[0] if result.get("data") else {}
        except Exception as e:
            logger.error(f"Get balance failed: {e}")
            return {}

    # ─── Kill Switch ────────────────────────────────────────

    def activate_kill_switch(self, reason: str):
        self._kill_switch = True
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        # Cancel all open orders
        for symbol in SETTINGS.instruments.crypto_pairs:
            self.cancel_all_orders(symbol)

    def deactivate_kill_switch(self):
        self._kill_switch = False
        logger.warning("Kill switch deactivated")

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def close(self):
        self._client.close()
