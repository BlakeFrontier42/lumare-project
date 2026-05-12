"""
tune_universal.py — joint grid search across any asset class.

Crypto / equity / futures / options each have their own AssetProfile.
This tuner takes an --asset-class flag and mutates the right profile,
then runs the replay engine across a basket of symbols from that
asset class on 1Y of real data.

Joint scoring penalises configs that overfit one symbol — every
symbol in the basket needs PF >= 1.2 with 15+ trades to qualify.

Usage:
  # crypto (BTC+ETH+SOL, 1Y Coinbase data)
  python scripts/tune_universal.py --asset-class crypto

  # equity (SPY+QQQ+AAPL+NVDA, 1Y yfinance data)
  python scripts/tune_universal.py --asset-class equity

  # full sweep (cycles through all four)
  python scripts/tune_universal.py --all

  # fast subset (~10-20min vs 2-6hr)
  python scripts/tune_universal.py --asset-class equity --fast
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
logger.remove()
logger.add(lambda m: None, level="ERROR")

from backend.main import LumareEngine
from backend.core import asset_profiles


# Per-asset baskets — symbols we have historical data for.
BASKETS = {
    "crypto":  ["BTC", "ETH", "SOL"],
    "equity":  ["SPY", "QQQ", "AAPL", "NVDA", "MSFT"],
    "futures": [],   # placeholder until futures data loader exists
    "options": [],   # tunes via underlying — uses equity basket through options profile
}

# Profile constants per class for the grid mutator
PROFILE_KEYS = {
    "crypto":  "CRYPTO_PROFILE",
    "equity":  "EQUITY_PROFILE",
    "futures": "FUTURES_PROFILE",
    "options": "OPTIONS_PROFILE",
}

# Grids — different sweet spots per asset class based on prior knowledge.
GRIDS = {
    "crypto": {
        "regime_mode":     ["bypass", "permissive"],
        "score_threshold": [60, 65, 70],
        "rr_ratio":        [2.0, 2.5, 3.0],
        "stop_atr_mult":   [1.5, 2.0, 2.5],
    },
    "equity": {
        # Equities have lower 5m vol — strict regime gating helps more.
        "regime_mode":     ["strict", "permissive"],
        "score_threshold": [55, 60, 65],
        "rr_ratio":        [2.0, 2.5, 3.0],
        "stop_atr_mult":   [2.0, 2.5, 3.0],   # wider stops for gap risk
    },
    "futures": {
        "regime_mode":     ["strict", "permissive"],
        "score_threshold": [60, 65, 70],
        "rr_ratio":        [2.0, 2.5, 3.0],
        "stop_atr_mult":   [1.5, 2.0, 2.5],
    },
    "options": {
        # Options need MORE conviction (theta decay)
        "regime_mode":     ["permissive", "strict"],
        "score_threshold": [65, 70, 75],
        "rr_ratio":        [2.5, 3.0, 3.5],
        "stop_atr_mult":   [2.0, 2.5, 3.0],
    },
}

GRIDS_FAST = {
    "crypto":  {"regime_mode": ["bypass", "permissive"], "score_threshold": [65, 70],
                "rr_ratio": [2.5, 3.0], "stop_atr_mult": [2.0]},
    "equity":  {"regime_mode": ["strict", "permissive"], "score_threshold": [60, 65],
                "rr_ratio": [2.5, 3.0], "stop_atr_mult": [2.5]},
    "futures": {"regime_mode": ["strict"], "score_threshold": [65, 70],
                "rr_ratio": [2.5, 3.0], "stop_atr_mult": [2.0, 2.5]},
    "options": {"regime_mode": ["permissive"], "score_threshold": [70, 75],
                "rr_ratio": [3.0, 3.5], "stop_atr_mult": [2.5, 3.0]},
}


def _generate_configs(grid: dict) -> list[dict]:
    out = [{}]
    for k, vs in grid.items():
        out = [{**c, k: v} for c in out for v in vs]
    return out


def _joint_score(by_symbol: dict, min_pf: float = 1.2, min_trades: int = 15) -> dict:
    pfs = [r["pf"] for r in by_symbol.values() if r.get("trades", 0) > 0]
    trades = [r["trades"] for r in by_symbol.values()]
    wrs = [r["wr"] for r in by_symbol.values() if r.get("trades", 0) > 0]

    if not pfs:
        return {"joint_score": 0.0, "qualified": False, "reason": "no trades"}

    sym_with_trades = sum(1 for r in by_symbol.values() if r.get("trades", 0) > 0)
    every_symbol_traded = sym_with_trades == len(by_symbol)

    qualified = (
        every_symbol_traded
        and min(pfs) >= min_pf
        and min(trades) >= min_trades
    )

    if qualified:
        product_pf = math.prod(pfs)
        joint = product_pf * math.sqrt(sum(trades))
    else:
        joint = 0.0

    return {
        "joint_score": round(joint, 3),
        "qualified": qualified,
        "min_pf": round(min(pfs), 3) if pfs else 0,
        "min_trades": min(trades) if trades else 0,
        "sum_trades": sum(trades),
        "avg_wr": round(sum(wrs) / len(wrs), 1) if wrs else 0,
        "every_symbol_traded": every_symbol_traded,
    }


def _mutate_profile(asset_class: str, cfg: dict, original):
    """Build a variant of the profile and install it in the registry."""
    variant = replace(
        original,
        name=f"tune_{asset_class}_{int(time.time())}",
        regime_mode=cfg["regime_mode"],
        score_threshold=cfg["score_threshold"],
        rr_ratio=cfg["rr_ratio"],
        stop_atr_mult=cfg["stop_atr_mult"],
    )
    asset_profiles.PROFILES[asset_class] = variant
    setattr(asset_profiles, PROFILE_KEYS[asset_class], variant)


def _restore_profile(asset_class: str, original):
    asset_profiles.PROFILES[asset_class] = original
    setattr(asset_profiles, PROFILE_KEYS[asset_class], original)


def run_class(asset_class: str, symbols: list[str], grid: dict,
              start: str, end: str) -> dict:
    """Run the grid for one asset class."""
    print(f"\n{'='*72}")
    print(f"  TUNING {asset_class.upper()}  |  symbols={symbols}")
    print(f"  window={start} to {end}")
    print(f"{'='*72}")

    configs = _generate_configs(grid)
    engine = LumareEngine()
    original = getattr(asset_profiles, PROFILE_KEYS[asset_class])

    print(f"\nGrid: {len(configs)} configs x {len(symbols)} symbols = "
          f"{len(configs)*len(symbols)} backtests\n")

    results = []
    t_start = time.monotonic()

    try:
        for i, cfg in enumerate(configs):
            print(f"  [{i+1:2d}/{len(configs)}] {cfg}", end="  ", flush=True)
            t0 = time.monotonic()
            _mutate_profile(asset_class, cfg, original)

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
                        by_symbol[sym] = {"trades": 0, "pf": 0, "wr": 0,
                                          "sharpe": 0, "max_dd": 0, "ann_ret": 0}
                except Exception as exc:
                    by_symbol[sym] = {"trades": 0, "pf": 0, "wr": 0,
                                      "error": str(exc)[:80]}

            score = _joint_score(by_symbol)
            elapsed = time.monotonic() - t0
            wall = time.monotonic() - t_start
            print(
                f"  joint={score['joint_score']:>6.2f}  "
                f"qual={str(score['qualified']):<5s}  "
                f"min_pf={score['min_pf']:>5.2f}  "
                f"sum_tr={score['sum_trades']:>4d}  "
                f"({elapsed:.0f}s wall={wall/60:.1f}m)"
            )
            results.append({"config": cfg, "by_symbol": by_symbol, "score": score})
    finally:
        _restore_profile(asset_class, original)

    results.sort(key=lambda r: r["score"]["joint_score"], reverse=True)
    return {
        "asset_class": asset_class,
        "symbols": symbols,
        "window": {"start": start, "end": end},
        "grid": grid,
        "results": results,
        "winner": results[0] if results else None,
    }


def print_top(out: dict, n: int = 5):
    print(f"\n--- TOP {n} for {out['asset_class'].upper()} ---")
    print(f"{'#':>2s}  {'regime':>10s}  {'thresh':>6s}  {'rr':>4s}  {'stop':>4s}  "
          f"{'joint':>6s}  {'qual':>5s}  per-symbol")
    for i, r in enumerate(out["results"][:n]):
        c = r["config"]
        s = r["score"]
        per = "  ".join(
            f"{k}: T={v.get('trades',0)} PF={v.get('pf',0):.2f}"
            for k, v in r["by_symbol"].items()
        )
        print(f"  {i+1}.  {c['regime_mode']:>10s}  {c['score_threshold']:>6d}  "
              f"{c['rr_ratio']:>4.1f}  {c['stop_atr_mult']:>4.1f}  "
              f"{s['joint_score']:>6.2f}  {str(s['qualified']):>5s}  {per}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset-class", choices=["crypto", "equity", "futures", "options"])
    ap.add_argument("--all", action="store_true",
                    help="Sweep all four asset classes")
    ap.add_argument("--symbols", default=None,
                    help="Override basket (comma-separated)")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end",   default=None)
    ap.add_argument("--out",   default="docs/tune_universal.json")
    args = ap.parse_args()

    if not args.asset_class and not args.all:
        ap.error("--asset-class or --all required")

    end = args.end or datetime.now(timezone.utc).date().isoformat()
    start = args.start or (
        datetime.now(timezone.utc) - timedelta(days=365)
    ).date().isoformat()

    grids = GRIDS_FAST if args.fast else GRIDS
    classes = [args.asset_class] if not args.all else ["crypto", "equity", "futures", "options"]

    all_results = {}
    for ac in classes:
        symbols = (
            [s.strip().upper() for s in (args.symbols or "").split(",") if s.strip()]
            or BASKETS[ac]
        )
        if ac == "options":
            # Tunes via the equity basket — options engine routes through
            # the underlying's bars and uses OPTIONS_PROFILE for risk.
            symbols = symbols or BASKETS["equity"]
        if not symbols:
            print(f"\nSKIPPING {ac}: no symbols configured")
            continue
        result = run_class(ac, symbols, grids[ac], start, end)
        all_results[ac] = result
        print_top(result)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nFull results -> {out_path}")

    print("\n=== WINNERS PER ASSET CLASS ===")
    for ac, r in all_results.items():
        w = r["winner"]
        if not w:
            print(f"  {ac}: no qualified configs")
            continue
        c = w["config"]
        s = w["score"]
        print(f"  {ac:7s}: regime={c['regime_mode']}  thresh={c['score_threshold']}  "
              f"rr={c['rr_ratio']}  stop={c['stop_atr_mult']}  "
              f"joint={s['joint_score']}  qualified={s['qualified']}")


if __name__ == "__main__":
    main()
