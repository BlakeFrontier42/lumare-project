"""
options_recommender.py — score every contract in an options chain and
surface the top picks.

For each (symbol, expiration) the recommender ranks the chain and returns:

* ``top_itm_calls`` — top 2 in-the-money calls (bullish, conviction)
* ``top_otm_calls`` — top 2 out-of-the-money calls (bullish, leveraged)
* ``top_itm_puts``  — top 2 in-the-money puts (bearish, conviction)
* ``top_otm_puts``  — top 2 out-of-the-money puts (bearish, leveraged)

Across all (symbol × expiration) results we pick a single ``overall_best``
trade — the contract with the highest composite score across the whole
universe.

Scoring weights (composite 0-100):

* 30%  Risk/reward — based on POP and breakeven distance
* 25%  Liquidity   — volume + OI percentile
* 20%  Spread      — bid/ask tightness penalty
* 15%  Greek fit   — delta in target band for ITM (.55-.70) / OTM (.25-.40)
* 10%  IV value    — preference for IV ≤ realised vol (cheap premium)

The chain comes from a deterministic mock for now (same IV-smile model
as the frontend) but the recommender takes a generic ``chain_provider``
so we can drop in a real OPRA feed without touching the scoring logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from backend.core.options_pricer import (
    _norm_cdf,
    bsm_delta,
    bsm_price,
    estimate_iv_from_returns,
)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class ContractQuote:
    """Concrete tradeable option contract with live-style quote."""
    underlying: str
    expiry: date
    strike: float
    option_type: str          # "CALL" | "PUT"
    last: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    iv: float                 # decimal (e.g. 0.28)
    delta: float
    gamma: float
    theta: float
    vega: float
    spot: float
    dte: int

    @property
    def is_itm(self) -> bool:
        return (
            (self.option_type == "CALL" and self.strike < self.spot) or
            (self.option_type == "PUT" and self.strike > self.spot)
        )

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2 if self.ask > self.bid else self.last

    @property
    def spread_pct(self) -> float:
        if self.last <= 0:
            return 1.0
        return min(1.0, (self.ask - self.bid) / max(self.last, 0.01))

    @property
    def occ_symbol(self) -> str:
        yymmdd = self.expiry.strftime("%y%m%d")
        tag = "C" if self.option_type == "CALL" else "P"
        strike_int = int(round(self.strike * 1000))
        return f"{self.underlying}{yymmdd}{tag}{strike_int:08d}"

    @property
    def contract_id(self) -> str:
        tag = "C" if self.option_type == "CALL" else "P"
        strike_str = (
            f"{self.strike:.0f}" if self.strike >= 100 else f"{self.strike:.2f}"
        )
        return f"{self.underlying} {self.expiry.isoformat()} {tag} {strike_str}"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _probability_of_profit(c: ContractQuote, realised_vol: float) -> float:
    """Risk-neutral probability of finishing in-the-money + premium recovered.

    Uses the BSM delta proxy: |delta| is the rough probability the option
    expires ITM. We adjust by breakeven distance (need spot to move
    enough to recover premium paid).
    """
    if c.dte <= 0 or realised_vol <= 0:
        return abs(c.delta)
    T = c.dte / 365.0
    breakeven = (
        c.strike + c.mid if c.option_type == "CALL" else c.strike - c.mid
    )
    # log-return needed to reach breakeven
    if c.option_type == "CALL":
        if breakeven <= c.spot:
            return abs(c.delta)
        log_move = math.log(breakeven / c.spot)
    else:
        if breakeven >= c.spot:
            return abs(c.delta)
        log_move = math.log(c.spot / breakeven)
    sigma_t = max(realised_vol * math.sqrt(T), 0.001)
    z = log_move / sigma_t
    return max(0.05, 1.0 - _norm_cdf(z))


def _liquidity_score(c: ContractQuote, max_volume: int, max_oi: int) -> float:
    """0-100 score blending volume and open interest."""
    vol = (c.volume / max_volume * 100) if max_volume > 0 else 0
    oi = (c.open_interest / max_oi * 100) if max_oi > 0 else 0
    score = 0.6 * vol + 0.4 * oi
    return max(0.0, min(100.0, score))


def _spread_score(c: ContractQuote) -> float:
    """Tighter spread = better fill. 0% spread → 100, ≥10% → 0."""
    return max(0.0, 100.0 - c.spread_pct * 1000.0)


def _greek_fit_score(c: ContractQuote) -> float:
    """Delta band fit. ITM target |delta| 0.55–0.70, OTM 0.25–0.40."""
    d = abs(c.delta)
    if c.is_itm:
        target_lo, target_hi = 0.55, 0.70
    else:
        target_lo, target_hi = 0.25, 0.40
    if target_lo <= d <= target_hi:
        return 100.0
    if d < target_lo:
        gap = target_lo - d
    else:
        gap = d - target_hi
    return max(0.0, 100.0 - gap * 250.0)


def _iv_value_score(c: ContractQuote, realised_vol: float) -> float:
    """IV ≤ realised ⇒ cheap (high score). IV ≫ realised ⇒ expensive."""
    if c.iv <= 0:
        return 50.0
    ratio = realised_vol / c.iv
    if ratio >= 1.0:
        return 100.0  # premium is cheap relative to realised
    return max(0.0, ratio * 100.0)


def score_contract(
    c: ContractQuote,
    realised_vol: float,
    max_volume: int,
    max_oi: int,
) -> dict:
    """Return a dict with composite + component scores + extras."""
    liq = _liquidity_score(c, max_volume, max_oi)
    spr = _spread_score(c)
    greek = _greek_fit_score(c)
    iv_val = _iv_value_score(c, realised_vol)
    pop = _probability_of_profit(c, realised_vol) * 100  # 0-100

    composite = (
        0.30 * pop
        + 0.25 * liq
        + 0.20 * spr
        + 0.15 * greek
        + 0.10 * iv_val
    )
    breakeven = (
        c.strike + c.mid if c.option_type == "CALL" else c.strike - c.mid
    )
    max_loss = c.mid * 100  # 1 contract = 100 shares, debit ≤ premium
    return {
        "composite_score": round(composite, 1),
        "components": {
            "probability_of_profit": round(pop, 1),
            "liquidity": round(liq, 1),
            "spread": round(spr, 1),
            "greek_fit": round(greek, 1),
            "iv_value": round(iv_val, 1),
        },
        "extras": {
            "breakeven": round(breakeven, 2),
            "max_loss_per_contract": round(max_loss, 2),
            "premium": round(c.mid, 2),
            "realised_vol": round(realised_vol, 3),
            "is_itm": c.is_itm,
        },
    }


# ---------------------------------------------------------------------------
# Synthetic chain generator (deterministic, IV-smile-aware)
# ---------------------------------------------------------------------------

def _synth_chain(
    underlying: str,
    spot: float,
    expiry: date,
    strike_step: float,
    n_strikes: int = 11,
    base_iv: float = 0.30,
    now: Optional[datetime] = None,
) -> list[ContractQuote]:
    """Generate a plausible chain for one expiration.

    Deterministic seeded by symbol+spot+expiry so a refresh returns
    consistent quotes between requests. Real OPRA feeds (Polygon /
    TastyTrade / IBKR) plug in here when available.
    """
    now = now or datetime.now(timezone.utc)
    exp_dt = datetime.combine(expiry, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    dte = max(int((exp_dt - now).total_seconds() / 86400), 0)

    atm = round(spot / strike_step) * strike_step
    quotes: list[ContractQuote] = []
    half = n_strikes // 2

    # Deterministic seed so identical inputs return identical chains.
    # (Used only for volume/oi variance — pricing is pure BSM.)
    import random
    rng = random.Random(hash((underlying, round(spot, 2), expiry.isoformat())))

    for i in range(-half, half + 1):
        strike = atm + i * strike_step
        if strike <= 0:
            continue
        moneyness = abs(strike - spot) / spot
        # IV smile: OTM expensive, with put skew
        iv = base_iv + moneyness * 0.5
        if strike < spot:
            iv += 0.05  # put skew
        iv = max(0.10, min(iv, 1.50))

        for opt_type in ("CALL", "PUT"):
            price = bsm_price(spot, strike, dte, iv, opt_type)
            delta = bsm_delta(spot, strike, dte, iv, opt_type)
            spread_pct = 0.02 + moneyness * 0.05
            bid = max(0.01, price * (1 - spread_pct / 2))
            ask = price * (1 + spread_pct / 2)

            # Volume/OI peak around ATM, decay with moneyness
            volume = int(rng.uniform(200, 5000) * math.exp(-moneyness * 5))
            oi = int(rng.uniform(500, 30000) * math.exp(-moneyness * 4))

            # Gamma/theta/vega rough proxies
            T = max(dte / 365.0, 1e-6)
            try:
                d1 = (
                    math.log(spot / strike) + (0.05 + 0.5 * iv * iv) * T
                ) / (iv * math.sqrt(T))
                pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
                gamma = pdf / (spot * iv * math.sqrt(T))
                theta = (
                    -spot * pdf * iv / (2 * math.sqrt(T)) / 365.0
                )
                vega = spot * math.sqrt(T) * pdf / 100.0
            except (ValueError, ZeroDivisionError):
                gamma = 0.0
                theta = 0.0
                vega = 0.0

            quotes.append(ContractQuote(
                underlying=underlying.upper(),
                expiry=expiry,
                strike=strike,
                option_type=opt_type,
                last=round(price, 2),
                bid=round(bid, 2),
                ask=round(ask, 2),
                volume=volume,
                open_interest=oi,
                iv=iv,
                delta=round(delta, 4),
                gamma=round(gamma, 5),
                theta=round(theta, 3),
                vega=round(vega, 3),
                spot=spot,
                dte=dte,
            ))
    return quotes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _next_friday(from_date: date, weeks_ahead: int = 0) -> date:
    """Standard weekly expiry — Fridays."""
    days_until_friday = (4 - from_date.weekday()) % 7
    if days_until_friday == 0 and weeks_ahead == 0:
        days_until_friday = 7
    return from_date + timedelta(days=days_until_friday + 7 * weeks_ahead)


def _strike_step_for(price: float) -> float:
    if price >= 500:
        return 5.0
    if price >= 100:
        return 1.0
    if price >= 25:
        return 0.5
    return 0.25


def serialise(c: ContractQuote, score: dict) -> dict:
    return {
        "underlying": c.underlying,
        "contract_id": c.contract_id,
        "occ_symbol": c.occ_symbol,
        "option_type": c.option_type,
        "strike": c.strike,
        "expiry": c.expiry.isoformat(),
        "dte": c.dte,
        "last": c.last,
        "bid": c.bid,
        "ask": c.ask,
        "mid": round(c.mid, 2),
        "spread_pct": round(c.spread_pct * 100, 2),
        "volume": c.volume,
        "open_interest": c.open_interest,
        "iv": round(c.iv * 100, 2),
        "delta": c.delta,
        "gamma": c.gamma,
        "theta": c.theta,
        "vega": c.vega,
        "spot": c.spot,
        "is_itm": c.is_itm,
        **score,
    }


def recommend_for_symbol(
    underlying: str,
    spot: float,
    realised_vol: float,
    expiries_weeks_ahead: Iterable[int] = (0, 1, 2),
    top_n: int = 2,
    today: Optional[date] = None,
) -> dict:
    """Build recommendations for one underlying across multiple weekly expiries."""
    today = today or date.today()
    strike_step = _strike_step_for(spot)

    by_expiry: list[dict] = []
    overall_pool: list[dict] = []

    for w in expiries_weeks_ahead:
        expiry = _next_friday(today, weeks_ahead=w)
        chain = _synth_chain(underlying, spot, expiry, strike_step, base_iv=realised_vol)
        if not chain:
            continue
        max_vol = max(c.volume for c in chain) or 1
        max_oi = max(c.open_interest for c in chain) or 1

        scored: list[tuple[ContractQuote, dict]] = []
        for c in chain:
            s = score_contract(c, realised_vol, max_vol, max_oi)
            scored.append((c, s))

        def pick(opt: str, itm: bool) -> list[dict]:
            filtered = [
                (c, s) for c, s in scored
                if c.option_type == opt and c.is_itm == itm
            ]
            filtered.sort(key=lambda x: x[1]["composite_score"], reverse=True)
            return [serialise(c, s) for c, s in filtered[:top_n]]

        block = {
            "expiry": expiry.isoformat(),
            "dte": (datetime.combine(expiry, datetime.min.time()) - datetime.combine(today, datetime.min.time())).days,
            "top_itm_calls": pick("CALL", True),
            "top_otm_calls": pick("CALL", False),
            "top_itm_puts":  pick("PUT",  True),
            "top_otm_puts":  pick("PUT",  False),
        }
        # Sanity: an expiry that's same-day might have no ITM/OTM splits
        for c, s in scored:
            overall_pool.append(serialise(c, s))
        by_expiry.append(block)

    overall_best = None
    if overall_pool:
        overall_pool.sort(key=lambda x: x["composite_score"], reverse=True)
        overall_best = overall_pool[0]

    return {
        "underlying": underlying.upper(),
        "spot": round(spot, 2),
        "realised_vol_annualised": round(realised_vol, 3),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "by_expiry": by_expiry,
        "overall_best": overall_best,
    }


def recommend_universe(
    symbols_with_spot: list[tuple[str, float, list[float]]],
    expiries_weeks_ahead: Iterable[int] = (0, 1, 2),
    top_n: int = 2,
) -> dict:
    """Run the recommender across a universe and pick the cross-symbol best trade.

    ``symbols_with_spot`` items are ``(symbol, spot_price, recent_returns)``.
    Recent returns drive the realised-vol estimate which drives IV pricing
    and probability-of-profit.
    """
    by_symbol = []
    cross_best: dict | None = None
    for sym, spot, returns in symbols_with_spot:
        if spot <= 0:
            continue
        rv = estimate_iv_from_returns(returns or [])
        result = recommend_for_symbol(
            sym, spot, rv,
            expiries_weeks_ahead=expiries_weeks_ahead,
            top_n=top_n,
        )
        by_symbol.append(result)
        if result.get("overall_best"):
            if cross_best is None or result["overall_best"]["composite_score"] > cross_best["composite_score"]:
                cross_best = result["overall_best"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_symbol": by_symbol,
        "overall_best_trade": cross_best,
    }
