"""
alpaca_executor.py — US Equities Execution via Alpaca API
Phase 2 executor for stocks and options.

SAFETY: Market orders DISABLED. Kill switch enforced.
"""

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional

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
        self.api_key = self.settings.api.ALPACA_KEY
        self.api_secret = self.settings.api.ALPACA_SECRET
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
