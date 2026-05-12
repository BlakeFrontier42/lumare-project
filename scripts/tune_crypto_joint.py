"""
tune_crypto_joint.py — joint grid search across BTC + ETH on 1Y real data.

The goal: find a CRYPTO_PROFILE configuration where *both* symbols
produce a profitable backtest, not just one. A config that crushes BTC
but loses on ETH (or vice versa) is overfit to one market.

The grid sweeps the four highest-leverage knobs:
  * regime_mode    : bypass / permissive   (gate trading on regime?)
  * score_threshold: 60 / 65 / 70           (entry conviction floor)
  * rr_ratio       : 2.0 / 2.5 / 3.0        (R:R target)
  * stop_atr_mult  : 1.5 / 2.0 / 2.5        (stop distance)

That's 2×3×3×3 = 54 configs × 2 symbols = 108 backtests. Each 1Y BTC
backtest takes ~3-5 min on this machine, so the full sweep is ~6-8 hours.
A focused subset can be selected with --fast.

Scoring rule (the joint metric we maximize):
  qualified = (btc.PF >= 1.2 AND eth.PF >= 1.2 AND btc.trades >= 15
               AND eth.trades >= 15)
  score = btc.PF * eth.PF * sqrt(btc.trades + eth.trades)

The sqrt(trades) factor rewards configs that fire enough to be
statistically meaningful, not just "5 lucky trades that PF'd 3x".

Output:
  docs/tune_results.json — full grid with all metrics
  Prints a ranked table to stdout.

Run:
  python scripts/tune_crypto_joint.py
  python scripts/tune_crypto_joint.py --fast      # 12 configs only
  python scripts/tune_crypto_joint.py --symbols BTC,ETH,SOL
"""

from __future__ import annotations

import argparse
import json
import math
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


# Full grid
GRID = {
    "regime_mode":    ["bypass", "permissive"],
    "score_threshold": [60, 65, 70],
    "rr_ratio":        [2.0, 2.5, 3.0],
    "stop_atr_mult":   [1.5, 2.0, 2.5],
}

# Fast subset for short iterations
GRID_FAST = {
    "regime_mode":    ["bypass", "permissive"],
    "score_threshold": [65, 70],
    "rr_ratio":        [2.5, 3.0],
    "stop_atr_mult":   [2.0],
}


def _generate_configs(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    out = [{}]
    for k in keys:
        out = [
            {**c, k: v}
            for c in out
            for v in grid[k]
        ]
    return out


def _joint_score(by_symbol: dict[str, dict]) -> dict:
    """Return aggregate scoring + qualified flag."""
    if not by_symbol:
        return {"joint_score": 0.0, "qualified": False, "reason": "no symbols"}

    pfs = [r["pf"] for r in by_symbol.values() if r.get("trades", 0) > 0]
    trades = [r["trades"] for r in by_symbol.values()]
    wrs = [r["wr"] for r in by_symbol.values() if r.get("trades", 0) > 0]

    if not pfs:
        return {"joint_score": 0.0, "qualified": False, "reason": "no trades on any symbol"}

    min_pf = min(pfs)
    min_trades = min(trades) if trades else 0
    product_pf = math.prod(pfs)
    sum_trades = sum(trades)

    qualified = (
        min_pf >= 1.2
        and min_trades >= 15
        and len(pfs) == len(by_symbol)  # every symbol traded
    )

    joint_score = product_pf * math.sqrt(sum_trades) if qualified else 0.0

    return {
        "joint_score": round(joint_score, 3),
        "qualified": qualified,
        "min_pf": round(min_pf, 3),
        "min_trades": min_trades,
        "product_pf": round(product_pf, 3),
        "sum_trades": sum_trades,
        "avg_wr": round(sum(wrs) / len(wrs), 1) if wrs else 0,
    }


def run(symbols: list[str], grid: dict, start: str, end: str) -> dict:
    configs = _generate_configs(grid)
    engine = LumareEngine()

    print(f"\nGrid search: {len(configs)} configs × {len(symbols)} symbols = "
          f"{len(configs) * len(symbols)} backtests")
    print(f"Window: {start} -> {end}\n")

    results = []
    t_start = time.monotonic()

    for i, cfg in enumerate(configs):
        print(f"  [{i+1:2d}/{len(configs)}] {cfg}", end="  ", flush=True)
        t0 = time.monotonic()

        # Install variant into the live profile registry. The replay
        # engine reads from PROFILES dict by asset_class.
        variant = replace(
            CRYPTO_PROFILE,
            name=f"tune_{i}",
            regime_mode=cfg["regime_mode"],
            score_threshold=cfg["score_threshold"],
            rr_ratio=cfg["rr_ratio"],
            stop_atr_mult=cfg["stop_atr_mult"],
            # Trail and short bonus kept at Phase 4.6 defaults
        )
        asset_profiles.PROFILES["crypto"] = variant
        # CRYPTO_PROFILE is also referenced directly in some code paths
        asset_profiles.CRYPTO_PROFILE = variant

        by_symbol = {}
        for sym in symbols:
            try:
                r = engine.run_backtest(
                    symbol=sym, start_date=start, end_date=end,
                    initial_capital=100_000.0,
                )
                m = r.metrics
                if m and m.total_trades > 0:
                    by_symbol[sym] = {
                        "trades": m.total_trades,
                        "pf": round(m.profit_factor, 3),
                        "wr": round(m.win_rate * 100, 1),
                        "sharpe": round(m.sharpe, 3),
                        "max_dd": round(m.max_drawdown.get("max_dd", 0) * 100, 2),
                        "ann_ret": round(m.annual_return * 100, 2),
                    }
                else:
                    by_symbol[sym] = {"trades": 0, "pf": 0, "wr": 0, "sharpe": 0, "max_dd": 0, "ann_ret": 0}
            except Exception as exc:
                by_symbol[sym] = {"trades": 0, "pf": 0, "wr": 0, "error": str(exc)[:80]}

        score = _joint_score(by_symbol)
        elapsed = time.monotonic() - t0
        wall = time.monotonic() - t_start
        print(f"  joint={score['joint_score']:>6.2f}  qual={score['qualified']!s:<5}  "
              f"({elapsed:.0f}s, wall {wall/60:.1f}m)")

        results.append({
            "config": cfg,
            "by_symbol": by_symbol,
            "score": score,
        })

    # Restore original
    asset_profiles.PROFILES["crypto"] = CRYPTO_PROFILE
    asset_profiles.CRYPTO_PROFILE = CRYPTO_PROFILE

    # Rank
    results.sort(key=lambda r: r["score"]["joint_score"], reverse=True)

    return {
        "symbols": symbols,
        "window": {"start": start, "end": end},
        "grid": grid,
        "results": results,
        "winner": results[0] if results else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTC,ETH")
    ap.add_argument("--start", default="2025-05-12")
    ap.add_argument("--end", default="2026-05-12")
    ap.add_argument("--fast", action="store_true",
                    help="Use a smaller grid (~8 configs vs 54)")
    ap.add_argument("--out", default="docs/tune_results.json")
    args = ap.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    grid = GRID_FAST if args.fast else GRID

    out = run(syms, grid, args.start, args.end)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))

    # Print top 10
    print("\n=== TOP RESULTS (ranked by joint_score) ===")
    print(f"{'rank':>4s}  {'regime':>10s}  {'thresh':>6s}  {'rr':>4s}  {'stop':>4s}  "
          f"{'joint':>6s}  {'qual':>5s}  per-symbol")
    for i, r in enumerate(out["results"][:10]):
        c = r["config"]
        s = r["score"]
        bsym = "  ".join(
            f"{k}: trades={v.get('trades',0)} PF={v.get('pf',0):.2f} WR={v.get('wr',0):.0f}%"
            for k, v in r["by_symbol"].items()
        )
        print(f"  {i+1:>3d}.  {c['regime_mode']:>10s}  {c['score_threshold']:>6d}  "
              f"{c['rr_ratio']:>4.1f}  {c['stop_atr_mult']:>4.1f}  "
              f"{s['joint_score']:>6.2f}  {str(s['qualified']):>5s}  {bsym}")

    print(f"\nFull results -> {args.out}")
    if out["winner"]:
        w = out["winner"]
        print(f"\nWINNER: {w['config']}")
        print(f"  joint_score: {w['score']['joint_score']}  qualified: {w['score']['qualified']}")
        for sym, m in w["by_symbol"].items():
            print(f"  {sym}: trades={m.get('trades',0)} PF={m.get('pf',0):.2f} WR={m.get('wr',0):.0f}% Sharpe={m.get('sharpe',0):.2f}")


if __name__ == "__main__":
    main()
