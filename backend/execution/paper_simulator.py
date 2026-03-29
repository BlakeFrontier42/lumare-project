"""
paper_simulator.py — Paper Trading Simulation Environment
Mimics real-world execution: slippage, fees, latency, partial fills,
liquidity constraints, and market impact modeling.
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

import numpy as np
from loguru import logger

from backend.config.settings import SETTINGS, Settings


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    leverage: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    reject_reason: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    price: float
    quantity: float
    fees: float
    slippage_bps: float
    latency_ms: float
    timestamp: datetime
    market_impact_bps: float = 0.0


@dataclass
class SimPosition:
    symbol: str
    side: OrderSide
    quantity: float
    avg_entry_price: float
    leverage: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fills: List[Fill] = field(default_factory=list)


class PaperSimulator:
    """
    Simulated execution environment for paper trading.

    Models: slippage (5bps + vol-adjusted), fees (maker 0.05% / taker 0.1%),
    latency (50ms mean), partial fills (85% fill rate), market impact (sqrt model),
    position limits (5% ADV max).
    """

    def __init__(self, settings: Settings = None, initial_capital: float = 100_000.0):
        self.settings = settings or SETTINGS
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, SimPosition] = {}
        self.open_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self.fill_history: List[Fill] = []

        self.base_slippage_bps = self.settings.execution.max_slippage_bps / 2
        self.taker_fee = self.settings.backtest.commission_pct
        self.maker_fee = self.settings.backtest.maker_commission_pct
        self.latency_mean = self.settings.execution.latency_model_ms
        self.fill_prob = self.settings.execution.sim_fill_probability
        self.partial_min = self.settings.execution.sim_partial_fill_min

        self._prices: Dict[str, float] = {}
        self._adv: Dict[str, float] = {}
        self._vol: Dict[str, float] = {}

    def update_market_state(self, symbol: str, price: float,
                            adv: float = 1_000_000, atr: float = 0.0):
        self._prices[symbol] = price
        self._adv[symbol] = adv
        if atr > 0 and price > 0:
            self._vol[symbol] = atr / price

    def submit_order(self, symbol: str, side: str, price: float,
                     quantity: float, leverage: float = 1.0,
                     order_type: str = "LIMIT") -> Order:
        """Submit a simulated order. Market orders are REJECTED by policy."""
        oid = str(uuid.uuid4())

        if order_type.upper() == "MARKET":
            o = Order(order_id=oid, symbol=symbol, side=OrderSide(side.upper()),
                      order_type=OrderType.MARKET, price=price, quantity=quantity,
                      leverage=leverage, status=OrderStatus.REJECTED,
                      reject_reason="Market orders disabled. Use limit orders.")
            self.order_history.append(o)
            return o

        # ADV limit check
        adv = self._adv.get(symbol, 1_000_000)
        if quantity > 0.05 * adv:
            o = Order(order_id=oid, symbol=symbol, side=OrderSide(side.upper()),
                      order_type=OrderType.LIMIT, price=price, quantity=quantity,
                      leverage=leverage, status=OrderStatus.REJECTED,
                      reject_reason=f"Exceeds 5% ADV ({adv:.0f})")
            self.order_history.append(o)
            return o

        # Margin check
        margin_needed = (price * quantity) / leverage
        if margin_needed > self.cash:
            o = Order(order_id=oid, symbol=symbol, side=OrderSide(side.upper()),
                      order_type=OrderType.LIMIT, price=price, quantity=quantity,
                      leverage=leverage, status=OrderStatus.REJECTED,
                      reject_reason=f"Insufficient margin: need ${margin_needed:,.2f}")
            self.order_history.append(o)
            return o

        order = Order(order_id=oid, symbol=symbol, side=OrderSide(side.upper()),
                      order_type=OrderType.LIMIT, price=price, quantity=quantity,
                      leverage=leverage, status=OrderStatus.OPEN)
        self.open_orders[oid] = order
        self.order_history.append(order)
        logger.debug(f"Order: {oid[:8]} {side} {quantity:.4f} {symbol} @ {price:.2f} ({leverage}x)")
        return order

    def process_bar(self, symbol: str, bar: dict):
        """Process candle bar: check fills for open orders, update positions."""
        self._prices[symbol] = bar["close"]

        for order in [o for o in self.open_orders.values()
                      if o.symbol == symbol and o.status == OrderStatus.OPEN]:
            fill = self._try_fill(order, bar)
            if fill:
                self._apply_fill(order, fill)

        if symbol in self.positions:
            pos = self.positions[symbol]
            cp = bar["close"]
            if pos.side == OrderSide.BUY:
                pos.unrealized_pnl = (cp - pos.avg_entry_price) * pos.quantity * pos.leverage
            else:
                pos.unrealized_pnl = (pos.avg_entry_price - cp) * pos.quantity * pos.leverage

    def _try_fill(self, order: Order, bar: dict) -> Optional[Fill]:
        can_fill = ((order.side == OrderSide.BUY and bar["low"] <= order.price) or
                    (order.side == OrderSide.SELL and bar["high"] >= order.price))
        if not can_fill:
            return None

        # Fill probability
        if np.random.random() > self.fill_prob:
            if np.random.random() > 0.5:
                fill_ratio = np.random.uniform(self.partial_min, 0.99)
            else:
                return None
        else:
            fill_ratio = 1.0

        qty = order.quantity * fill_ratio

        # Slippage
        vol = self._vol.get(order.symbol, 0.02)
        vol_comp = (vol / 0.02) * self.base_slippage_bps * 0.5
        adv = self._adv.get(order.symbol, 1_000_000)
        size_comp = np.sqrt(qty / max(adv, 1)) * 10
        slip = max(0, self.base_slippage_bps + vol_comp + size_comp + np.random.normal(0, 1))

        if order.side == OrderSide.BUY:
            fp = order.price * (1 + slip / 10_000)
        else:
            fp = order.price * (1 - slip / 10_000)

        fees = fp * qty * self.maker_fee
        impact = np.sqrt(qty / max(adv, 1)) * 100
        latency = max(0, np.random.normal(self.latency_mean, self.latency_mean * 0.3))

        return Fill(
            fill_id=str(uuid.uuid4()), order_id=order.order_id,
            symbol=order.symbol, side=order.side,
            price=round(fp, 8), quantity=qty, fees=round(fees, 8),
            slippage_bps=round(slip, 2), latency_ms=round(latency, 1),
            timestamp=datetime.now(timezone.utc), market_impact_bps=round(impact, 2),
        )

    def _apply_fill(self, order: Order, fill: Fill):
        order.filled_quantity += fill.quantity
        order.fees += fill.fees
        if order.filled_quantity > 0:
            prev_cost = order.avg_fill_price * (order.filled_quantity - fill.quantity)
            order.avg_fill_price = (prev_cost + fill.price * fill.quantity) / order.filled_quantity

        if order.filled_quantity >= order.quantity * 0.999:
            order.status = OrderStatus.FILLED
            self.open_orders.pop(order.order_id, None)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        self.fill_history.append(fill)
        self.cash -= fill.fees
        self._update_position(fill, order.leverage)

    def _update_position(self, fill: Fill, leverage: float):
        sym = fill.symbol
        if sym in self.positions:
            pos = self.positions[sym]
            if pos.side == fill.side:
                total = pos.quantity + fill.quantity
                pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + fill.price * fill.quantity) / total
                pos.quantity = total
                self.cash -= (fill.price * fill.quantity) / leverage
            else:
                if fill.quantity >= pos.quantity:
                    pnl = ((fill.price - pos.avg_entry_price) * pos.quantity * leverage
                           if pos.side == OrderSide.BUY else
                           (pos.avg_entry_price - fill.price) * pos.quantity * leverage)
                    margin = (pos.avg_entry_price * pos.quantity) / pos.leverage
                    self.cash += margin + pnl
                    pos.realized_pnl += pnl
                    del self.positions[sym]
                else:
                    pnl = ((fill.price - pos.avg_entry_price) * fill.quantity * leverage
                           if pos.side == OrderSide.BUY else
                           (pos.avg_entry_price - fill.price) * fill.quantity * leverage)
                    margin = (pos.avg_entry_price * fill.quantity) / pos.leverage
                    self.cash += margin + pnl
                    pos.realized_pnl += pnl
                    pos.quantity -= fill.quantity
        else:
            self.cash -= (fill.price * fill.quantity) / leverage
            self.positions[sym] = SimPosition(
                symbol=sym, side=fill.side, quantity=fill.quantity,
                avg_entry_price=fill.price, leverage=leverage, fills=[fill],
            )

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.open_orders:
            self.open_orders[order_id].status = OrderStatus.CANCELLED
            del self.open_orders[order_id]
            return True
        return False

    def cancel_all_orders(self, symbol: str = None) -> int:
        ids = [oid for oid, o in self.open_orders.items()
               if symbol is None or o.symbol == symbol]
        for oid in ids:
            self.cancel_order(oid)
        return len(ids)

    def get_portfolio(self) -> dict:
        unreal = sum(p.unrealized_pnl for p in self.positions.values())
        real = sum(p.realized_pnl for p in self.positions.values())
        margin = sum((p.avg_entry_price * p.quantity) / p.leverage for p in self.positions.values())
        return {
            "cash": round(self.cash, 2),
            "margin_used": round(margin, 2),
            "total_value": round(self.cash + margin + unreal, 2),
            "unrealized_pnl": round(unreal, 2),
            "realized_pnl": round(real, 2),
            "total_fees": round(sum(f.fees for f in self.fill_history), 2),
            "num_positions": len(self.positions),
            "positions": {s: {"side": p.side.value, "qty": p.quantity,
                              "entry": p.avg_entry_price, "leverage": p.leverage,
                              "upnl": round(p.unrealized_pnl, 2)}
                          for s, p in self.positions.items()},
        }

    def get_total_value(self) -> float:
        return self.get_portfolio()["total_value"]

    def reset(self, capital: float = None):
        self.cash = capital or self.initial_capital
        self.positions.clear()
        self.open_orders.clear()
        self.order_history.clear()
        self.fill_history.clear()
