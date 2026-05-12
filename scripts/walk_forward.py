"""
walk_forward.py — out-of-sample validation across rolling windows.

Runs the replay engine on the same symbol across several non-overlapping
test windows and reports PF / Sharpe / win-rate / drawdown per window
plus the cross-window mean + stdev. The point is to catch profiles
that look great on the calibration period but collapse elsewhere.

Constraints today:
- yfinance 5m intraday data only goes back 60 days
- Coinbase 5m similarly caps near ~30 days for free public access
- So this is a *short* walk-forward: 4-6 windows of 7-14 days each

Run:

    python scripts/walk_forward.py
    python scripts/walk_forward.py --symbols BTCUSDT,ETHUSDT --window 10 --folds 5
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

logger.remove()
logger.add(lambda msg: None, level="WARNING")

from backend.main import LumareEngine  # noqa: E402


def _walk_one_symbol(
    engine: LumareEngine, symbol: str, window_days: int, folds: int, gap_days: int = 0
):
    """Run ``folds`` consecutive windows of ``window_days``, gap between them."""
    end = datetime.now(timezone.utc) - timedelta(hours=2)  # leave room for partial bar
    results = []
    for i in range(folds):
        fold_end = end - timedelta(days=i * (window_days + gap_days))
        fold_start = fold_end - timedelta(days=window_days)
        s = fold_start.strftime("%Y-%m-%d")
        e = fold_end.strftime("%Y-%m-%d")
        try:
            r = engine.run_backtest(
                symbol=symbol, start_date=s, end_date=e, initial_capital=100_000.0
            )
        except Exception as exc:
            results.append({
                "fold": i + 1, "start": s, "end": e,
                "error": str(exc), "trades": 0,
            })
            continue
        m = r.metrics
        if not m or m.total_trades == 0:
            results.append({
                "fold": i + 1, "start": s, "end": e,
                "trades": 0, "note": "no trades",
            })
            continue
        results.append({
            "fold": i + 1,
            "start": s,
            "end": e,
            "trades": m.total_trades,
            "sharpe": round(float(m.sharpe), 3),
            "profit_factor": round(float(m.profit_factor), 3),
            "win_rate": round(float(m.win_rate) * 100, 1),
            "max_dd": round(float(m.max_drawdown.get("max_dd", 0)) * 100, 2),
            "annual_return": round(float(m.annual_return) * 100, 1),
        })
    return results


def _aggregate(per_fold):
    valid = [f for f in per_fold if "profit_factor" in f]
    if not valid:
        return {"n_folds_with_trades": 0}
    pfs = [f["profit_factor"] for f in valid]
    wrs = [f["win_rate"] for f in valid]
    sharpes = [f["sharpe"] for f in valid]
    dds = [f["max_dd"] for f in valid]
    rets = [f["annual_return"] for f in valid]
    trades = [f["trades"] for f in valid]

    def stats(xs):
        # Drop inf/nan that arise when a fold has no losses (PF = ∞)
        clean = [
            x for x in xs
            if isinstance(x, (int, float))
            and x == x  # not NaN
            and abs(x) != float("inf")
        ]
        if not clean:
            return {"mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0, "n": 0}
        return {
            "n": len(clean),
            "mean": round(statistics.mean(clean), 3),
            "stdev": round(statistics.pstdev(clean), 3) if len(clean) > 1 else 0.0,
            "min": round(min(clean), 3),
            "max": round(max(clean), 3),
        }

    return {
        "n_folds_with_trades": len(valid),
        "trades_per_fold": stats(trades),
        "profit_factor": stats(pfs),
        "win_rate_pct": stats(wrs),
        "sharpe": stats(sharpes),
        "max_dd_pct": stats(dds),
        "annual_return_pct": stats(rets),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SPY,QQQ,AAPL,NVDA",
                   help="Comma-separated symbols to validate")
    p.add_argument("--window", type=int, default=10,
                   help="Test window length (days)")
    p.add_argument("--folds", type=int, default=5,
                   help="Number of consecutive windows")
    p.add_argument("--gap", type=int, default=0,
                   help="Gap between windows (days). 0 = back-to-back.")
    p.add_argument("--out", default="docs/walk_forward.json")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    engine = LumareEngine()

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "window_days": args.window,
        "folds": args.folds,
        "gap_days": args.gap,
        "by_symbol": {},
    }

    print(f"\nWalk-forward: {len(symbols)} symbols × {args.folds} folds × {args.window}d\n")

    for sym in symbols:
        print(f">>> {sym}")
        per_fold = _walk_one_symbol(engine, sym, args.window, args.folds, args.gap)
        agg = _aggregate(per_fold)
        report["by_symbol"][sym] = {"folds": per_fold, "aggregate": agg}

        # Per-fold table
        header = f"  {'fold':>4}  {'start':>10}  {'end':>10}  {'trades':>7}  {'PF':>6}  {'WR%':>6}  {'Sharpe':>7}  {'DD%':>6}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for f in per_fold:
            if "error" in f:
                print(f"  {f['fold']:>4}  {f['start']:>10}  {f['end']:>10}  ERROR: {f['error'][:40]}")
            elif "note" in f and f["note"] == "no trades":
                print(f"  {f['fold']:>4}  {f['start']:>10}  {f['end']:>10}  {0:>7}  {'-':>6}  {'-':>6}  {'-':>7}  {'-':>6}")
            else:
                print(
                    f"  {f['fold']:>4}  {f['start']:>10}  {f['end']:>10}  "
                    f"{f['trades']:>7}  {f['profit_factor']:>6.2f}  "
                    f"{f['win_rate']:>6.1f}  {f['sharpe']:>7.2f}  {f['max_dd']:>6.2f}"
                )

        if agg.get("n_folds_with_trades", 0) > 0:
            pf = agg["profit_factor"]
            wr = agg["win_rate_pct"]
            print(f"  aggregate: PF {pf['mean']}±{pf['stdev']} "
                  f"(min={pf['min']}, max={pf['max']}) | "
                  f"WR {wr['mean']:.1f}±{wr['stdev']:.1f}%")
        else:
            print("  aggregate: no folds produced trades")
        print()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Full report -> {out}")

    # Cross-symbol verdict
    print("\n=== VERDICT ===")
    print(f"{'SYMBOL':<10} {'FOLDS':>6} {'PF_MEAN':>8} {'PF_STDEV':>9} {'WR_MEAN':>8}  status")
    for sym, data in report["by_symbol"].items():
        agg = data["aggregate"]
        n = agg.get("n_folds_with_trades", 0)
        if n == 0:
            print(f"{sym:<10} {'0':>6} {'-':>8} {'-':>9} {'-':>8}  no trades")
            continue
        pf = agg["profit_factor"]
        wr = agg["win_rate_pct"]
        status = (
            "PASS" if pf["mean"] >= 1.3 and pf["min"] >= 0.9 else "REVIEW"
        )
        print(f"{sym:<10} {n:>6} {pf['mean']:>8.2f} {pf['stdev']:>9.2f} {wr['mean']:>8.1f}  {status}")


if __name__ == "__main__":
    main()
