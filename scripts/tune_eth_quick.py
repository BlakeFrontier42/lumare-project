"""
tune_eth_quick.py — single-symbol ETH grid, fast.

The joint BTC+ETH grid hangs because BTC takes too long (40+ min per
config) and never qualifies on this period anyway. ETH alone runs much
faster and is the symbol that DOES produce edge.

Picks the best single-symbol config for ETH then prints recommendations
for the CRYPTO_PROFILE update.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
logger.remove()
logger.add(lambda m: None, level="ERROR")

from backend.main import LumareEngine
from backend.core import asset_profiles
from backend.core.asset_profiles import CRYPTO_PROFILE


GRID = []
for regime_mode in ["bypass", "permissive"]:
    for thresh in [60, 65, 70]:
        for rr in [2.5, 3.0, 3.5]:
            GRID.append({
                "regime_mode": regime_mode,
                "score_threshold": thresh,
                "rr_ratio": rr,
                "stop_atr_mult": 2.0,
            })


def main():
    engine = LumareEngine()
    print(f"ETH-only grid: {len(GRID)} configs × 1 symbol = {len(GRID)} backtests\n")

    results = []
    t0_all = time.monotonic()

    for i, cfg in enumerate(GRID):
        print(f"  [{i+1:2d}/{len(GRID)}] {cfg}", end="  ", flush=True)
        variant = replace(
            CRYPTO_PROFILE,
            name=f"eth_tune_{i}",
            regime_mode=cfg["regime_mode"],
            score_threshold=cfg["score_threshold"],
            rr_ratio=cfg["rr_ratio"],
            stop_atr_mult=cfg["stop_atr_mult"],
        )
        asset_profiles.PROFILES["crypto"] = variant
        asset_profiles.CRYPTO_PROFILE = variant

        t0 = time.monotonic()
        try:
            r = engine.run_backtest(
                symbol="ETH", start_date="2025-05-12", end_date="2026-05-12",
                initial_capital=100_000.0,
            )
            m = r.metrics
            if m and m.total_trades > 0:
                metric = {
                    "trades": m.total_trades,
                    "win_rate": round(m.win_rate * 100, 1),
                    "pf": round(m.profit_factor, 3),
                    "sharpe": round(m.sharpe, 3),
                    "max_dd": round(m.max_drawdown.get("max_dd", 0) * 100, 2),
                    "ann_ret": round(m.annual_return * 100, 2),
                }
            else:
                metric = {"trades": 0, "win_rate": 0, "pf": 0,
                          "sharpe": 0, "max_dd": 0, "ann_ret": 0}
        except Exception as exc:
            metric = {"error": str(exc)[:80]}

        elapsed = time.monotonic() - t0
        total = (time.monotonic() - t0_all) / 60
        print(f"  trades={metric.get('trades',0):>3d}  WR={metric.get('win_rate',0):>5.1f}%  "
              f"PF={metric.get('pf',0):>5.2f}  ({elapsed:.0f}s, total {total:.1f}m)")

        results.append({"config": cfg, "metric": metric})

    # Restore
    asset_profiles.PROFILES["crypto"] = CRYPTO_PROFILE
    asset_profiles.CRYPTO_PROFILE = CRYPTO_PROFILE

    # Rank — prefer PF >= 1.5 with 15+ trades, then by PF
    def score(r):
        m = r["metric"]
        pf = m.get("pf", 0)
        tr = m.get("trades", 0)
        if pf == float("inf"):
            pf = 99.0
        if tr < 15:
            return -1  # disqualified
        return pf

    results.sort(key=score, reverse=True)

    print(f"\n=== TOP 5 ETH CONFIGS ===")
    print(f"{'#':>2s}  {'regime':>10s}  {'thresh':>6s}  {'rr':>4s}  "
          f"{'trades':>6s}  {'WR%':>5s}  {'PF':>5s}  {'Sharpe':>6s}  {'maxDD':>6s}")
    for i, r in enumerate(results[:5]):
        c = r["config"]
        m = r["metric"]
        print(f"  {i+1:>2d}  {c['regime_mode']:>10s}  {c['score_threshold']:>6d}  "
              f"{c['rr_ratio']:>4.1f}  {m.get('trades',0):>6d}  "
              f"{m.get('win_rate',0):>5.1f}  {m.get('pf',0):>5.2f}  "
              f"{m.get('sharpe',0):>6.2f}  {m.get('max_dd',0):>5.2f}%")

    Path("docs/eth_tune.json").write_text(json.dumps(results, indent=2))
    print(f"\nFull -> docs/eth_tune.json")


if __name__ == "__main__":
    main()
