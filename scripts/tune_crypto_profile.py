"""
tune_crypto_profile.py — Grid-search variants of the crypto AssetProfile
on BTC 1-year to find the highest-PF configuration.

Baseline (Phase 4 / current): stop=2.0 ATR, rr=2.5, trail=2.0, threshold=65 → PF 1.52

Tests several hypotheses:
  1. Higher threshold = fewer but stronger trades
  2. Wider R:R = let winners run further
  3. Tighter stop = smaller losers
  4. Tighter trailing = lock gains sooner
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import replace
from loguru import logger

from backend.main import LumareEngine
from backend.core import asset_profiles
from backend.core.asset_profiles import CRYPTO_PROFILE, PROFILES


VARIANTS = [
    # (label,              threshold, stop_mult, rr,   trail)
    ("baseline",             65,       2.0,      2.5,  2.0),
    ("rr_3.0",               65,       2.0,      3.0,  2.0),
    ("threshold_67",         67,       2.0,      2.5,  2.0),
    ("trail_1.5",            65,       2.0,      2.5,  1.5),
    ("t67_rr3.0_trail1.5",   67,       2.0,      3.0,  1.5),
]


def main():
    engine = LumareEngine()
    results = []

    for (label, thr, stop_m, rr, trail) in VARIANTS:
        # Install a fresh crypto profile variant into the registry
        variant = replace(
            CRYPTO_PROFILE,
            name=f"crypto_{label}",
            score_threshold=thr,
            stop_atr_mult=stop_m,
            rr_ratio=rr,
            trailing_mult=trail,
        )
        PROFILES["crypto"] = variant

        logger.info("=" * 70)
        logger.info("VARIANT {} | thr={} stop={} rr={} trail={}", label, thr, stop_m, rr, trail)
        logger.info("=" * 70)

        r = engine.run_backtest(
            symbol="BTCUSDT",
            start_date="2025-04-01",
            end_date="2026-03-20",
            initial_capital=100_000.0,
        )
        m = r.metrics
        if not m or m.total_trades == 0:
            results.append((label, 0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue

        results.append((
            label,
            m.total_trades,
            m.sharpe,
            m.profit_factor,
            m.win_rate * 100,
            m.max_drawdown.get("max_dd", 0.0) * 100,
            m.annual_return * 100,
        ))

    # Restore baseline
    PROFILES["crypto"] = CRYPTO_PROFILE

    # Print ranked table
    header = f"{'VARIANT':<24}{'TRD':>5}{'SHARPE':>9}{'PF':>8}{'WR%':>8}{'DD%':>7}{'ANN%':>9}"
    print("\n" + "=" * 78)
    print("CRYPTO PROFILE GRID SEARCH — BTC 1Y")
    print("=" * 78)
    print(header)
    print("-" * 78)
    # Sort by PF descending
    ranked = sorted(results, key=lambda r: r[3], reverse=True)
    for label, trd, sh, pf, wr, dd, ann in ranked:
        marker = " *" if pf > 1.52 else "  "
        print(f"{label:<24}{trd:>5}{sh:>9.2f}{pf:>8.2f}{wr:>8.1f}{dd:>7.1f}{ann:>9.1f}{marker}")
    print("=" * 78)
    print("* = PF above baseline 1.52\n")


if __name__ == "__main__":
    main()
