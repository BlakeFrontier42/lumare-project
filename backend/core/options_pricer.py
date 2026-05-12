"""
options_pricer.py — Black-Scholes pricing + contract resolution for the bot.

When the bot runs in ``asset_class="options"`` mode it doesn't trade the
underlying — it picks a near-ATM weekly option contract for each
underlying, computes an option price from the live underlying price,
and tracks P&L on the contract itself.

This module provides:

* ``OptionContract`` — a tiny dataclass holding underlying, strike,
  expiry, option type, contract id.
* ``resolve_weekly_contract`` — choose strike + expiry for a direction.
* ``bsm_price`` — Black-Scholes call/put price.
* ``bsm_delta`` — option delta (used to estimate P&L sensitivity).
* ``estimate_iv`` — quick implied-vol proxy from recent underlying
  return std (no chain available without a paid options data source).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional


OptionType = Literal["CALL", "PUT"]


# ---------------------------------------------------------------------------
# Contract dataclass
# ---------------------------------------------------------------------------

@dataclass
class OptionContract:
    """Minimal options contract reference for the bot.

    The bot doesn't know the *real* OPRA contract — it constructs a
    synthetic near-ATM weekly contract that mirrors what a retail
    operator would actually pick. The pricing path is BSM so the
    contract id is deterministic and shareable.
    """

    underlying: str
    strike: float
    expiry: date           # the option expiry date (Friday for weeklies)
    option_type: OptionType

    @property
    def contract_id(self) -> str:
        """Compact human-readable id like ``SPY 2026-05-15 C 740``."""
        tag = "C" if self.option_type == "CALL" else "P"
        strike_str = (
            f"{self.strike:.0f}"
            if self.strike >= 100
            else f"{self.strike:.2f}"
        )
        return f"{self.underlying} {self.expiry.isoformat()} {tag} {strike_str}"

    @property
    def occ_symbol(self) -> str:
        """OCC-style symbol like ``SPY260515C00740000`` — what a real
        broker would use. Useful when we later swap in a real options
        execution path."""
        yymmdd = self.expiry.strftime("%y%m%d")
        tag = "C" if self.option_type == "CALL" else "P"
        strike_int = int(round(self.strike * 1000))
        return f"{self.underlying}{yymmdd}{tag}{strike_int:08d}"

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying,
            "strike": float(self.strike),
            "expiry": self.expiry.isoformat(),
            "option_type": self.option_type,
            "contract_id": self.contract_id,
            "occ_symbol": self.occ_symbol,
        }


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------

def _next_weekly_expiry(today: Optional[date] = None) -> date:
    """Return the next Friday >= today + 1 day (the standard weekly expiry).

    If today *is* Friday, roll to the following Friday — operators
    typically don't open new positions on the day of expiry.
    """
    today = today or date.today()
    # Friday = weekday 4
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    return today + timedelta(days=days_until_friday)


def _round_strike(underlying_price: float) -> float:
    """Round to the nearest standard strike step.

    SPY / QQQ / heavy index ETFs trade $1 wide strikes.
    Single-name equities under $500 mostly trade $1 or $2.50 wide.
    Above $500 they trade $5 / $10 wide.
    """
    if underlying_price >= 500:
        step = 5.0
    elif underlying_price >= 100:
        step = 1.0
    elif underlying_price >= 25:
        step = 0.5
    else:
        step = 0.25
    return round(underlying_price / step) * step


def resolve_weekly_contract(
    underlying: str,
    underlying_price: float,
    direction: str,
    today: Optional[date] = None,
) -> OptionContract:
    """Pick a near-ATM weekly contract for ``direction`` ("LONG"/"SHORT").

    LONG  → buy a call slightly out of the money (delta ~0.45)
    SHORT → buy a put slightly out of the money (delta ~-0.45)
    """
    expiry = _next_weekly_expiry(today)
    strike = _round_strike(underlying_price)
    option_type: OptionType = "CALL" if direction.upper() == "LONG" else "PUT"
    return OptionContract(
        underlying=underlying.upper(),
        strike=strike,
        expiry=expiry,
        option_type=option_type,
    )


# ---------------------------------------------------------------------------
# Black-Scholes pricing
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf — no scipy dependency."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bsm_price(
    spot: float,
    strike: float,
    days_to_expiry: float,
    sigma: float,
    option_type: OptionType,
    risk_free_rate: float = 0.05,
) -> float:
    """Black-Scholes price for a European option.

    Defaults to a 5% risk-free rate which is reasonable for the current
    rate environment. ``sigma`` is annualised vol (e.g. 0.20 = 20% IV).
    """
    if days_to_expiry <= 0:
        intrinsic = (
            max(spot - strike, 0.0)
            if option_type == "CALL"
            else max(strike - spot, 0.0)
        )
        return intrinsic
    if sigma <= 0 or spot <= 0 or strike <= 0:
        return max(0.01, abs(spot - strike) * 0.05)

    T = days_to_expiry / 365.0
    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * T
    ) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "CALL":
        price = (
            spot * _norm_cdf(d1)
            - strike * math.exp(-risk_free_rate * T) * _norm_cdf(d2)
        )
    else:
        price = (
            strike * math.exp(-risk_free_rate * T) * _norm_cdf(-d2)
            - spot * _norm_cdf(-d1)
        )
    return max(price, 0.01)  # never quote zero — a real chain shows the bid floor


def bsm_delta(
    spot: float,
    strike: float,
    days_to_expiry: float,
    sigma: float,
    option_type: OptionType,
    risk_free_rate: float = 0.05,
) -> float:
    """Option delta. ATM call ≈ 0.5, ATM put ≈ -0.5."""
    if days_to_expiry <= 0 or sigma <= 0:
        return 0.5 if option_type == "CALL" else -0.5
    T = days_to_expiry / 365.0
    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * T
    ) / (sigma * math.sqrt(T))
    if option_type == "CALL":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


# ---------------------------------------------------------------------------
# IV estimation
# ---------------------------------------------------------------------------

def estimate_iv_from_returns(returns: list[float]) -> float:
    """Realised vol from a return series, annualised.

    Used as a proxy for IV when no options chain is available. Daily
    return std × sqrt(252). Floors at 10% so quiet markets still produce
    a tradeable option price.
    """
    if len(returns) < 5:
        return 0.20  # default 20%
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    daily_std = math.sqrt(var)
    annualised = daily_std * math.sqrt(252)
    return max(0.10, min(annualised, 1.50))  # clamp to [10%, 150%]


# ---------------------------------------------------------------------------
# Convenience: price an option from an underlying price + recent bars
# ---------------------------------------------------------------------------

def price_option(
    contract: OptionContract,
    underlying_price: float,
    iv_estimate: float,
    now: Optional[datetime] = None,
) -> dict:
    """Return ``{price, delta, days_to_expiry, iv}`` for a contract."""
    now = now or datetime.now(timezone.utc)
    expiry_dt = datetime.combine(contract.expiry, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    days_to_expiry = max((expiry_dt - now).total_seconds() / 86400.0, 0.0)
    price = bsm_price(
        underlying_price,
        contract.strike,
        days_to_expiry,
        iv_estimate,
        contract.option_type,
    )
    delta = bsm_delta(
        underlying_price,
        contract.strike,
        days_to_expiry,
        iv_estimate,
        contract.option_type,
    )
    return {
        "price": price,
        "delta": delta,
        "days_to_expiry": days_to_expiry,
        "iv": iv_estimate,
    }
