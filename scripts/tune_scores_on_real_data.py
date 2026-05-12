"""
tune_scores_on_real_data.py — observe-only score harness.

Fetches live OHLCV for a per-asset-class symbol basket, runs the full
scoring engine against it, captures the resulting score distribution,
and recommends a realistic ``min_score_to_trade`` per asset class.

The intent: replace gut-feel thresholds with empirical ones grounded in
how the scoring engine actually behaves on today's market.

Usage:

    python scripts/tune_scores_on_real_data.py
    python scripts/tune_scores_on_real_data.py --iterations 20 --pause 5

Writes ``docs/score_distribution.json`` with the raw histogram and the
recommended threshold per asset class.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

# Quiet the noisy library warnings during the run
logger.remove()
logger.add(lambda msg: None, level="WARNING")

from backend.config.settings import SETTINGS, RegimeState
from backend.data.storage import Storage
from backend.data.aggregator import DataAggregator
from backend.core.regime_engine import RegimeClassifier
from backend.core.trend_engine import TrendEngine
from backend.core.momentum_engine import MomentumEngine
from backend.core.structure_engine import StructureEngine
from backend.core.flow_engine import FlowEngine
from backend.core.macro_engine import MacroEngine
from backend.core.scoring_engine import ScoringEngine
from backend.orchestrator.autobot import _ApiRunner  # noqa: F401  (regime helper)


ASSET_BASKETS = {
    "crypto": ["BTC", "ETH", "SOL", "XRP", "AVAX", "ADA"],
    "equity": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "META", "GOOGL"],
    "options": ["SPY", "QQQ", "AAPL", "NVDA", "TSLA"],
    "futures": ["ES", "NQ"],  # yfinance handles via "ES=F" but our path uses "equity"
}


async def _score_one(
    aggregator: DataAggregator,
    scoring_engine: ScoringEngine,
    regime_engine: RegimeClassifier,
    symbol: str,
    fetch_class: str,
) -> dict | None:
    try:
        snap = await aggregator.fetch_full_snapshot(symbol, fetch_class)
    except Exception as exc:
        return {"error": f"fetch: {exc}"}

    if (snap.candles.get("5M") is None or snap.candles["5M"].empty):
        return {"error": "no 5M data"}

    # Use the same regime input helper as the live runner so the scores
    # we observe match what the bot would see.
    regime_inputs = _ApiRunner._compute_regime_inputs(snap.candles)
    try:
        result = regime_engine.classify(regime_inputs)
        regime_state = result.state if hasattr(result, "state") else RegimeState.RISK_ON
    except Exception:
        regime_state = RegimeState.RISK_ON

    market_data = {
        "symbol": symbol,
        "candles": snap.candles,
        "timeframe_data": snap.candles,  # what sub-engines actually read
        "last_price": snap.last_price
        or float(snap.candles["5M"]["close"].iloc[-1]),
    }

    out = {"regime": regime_state.value}
    for direction in ("LONG", "SHORT"):
        try:
            sr = scoring_engine.score(market_data, regime_state, direction)
        except Exception as exc:
            out[direction] = {"error": str(exc)}
            continue
        if isinstance(sr, dict):
            score = float(sr.get("total_score", 0))
        else:
            score = float(getattr(sr, "total_score", 0))
        out[direction] = {"score": score}
    return out


def _summarise(scores: list[float]) -> dict:
    if not scores:
        return {"n": 0}
    s = sorted(scores)

    def pct(p: float) -> float:
        idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
        return s[idx]

    return {
        "n": len(scores),
        "min": s[0],
        "max": s[-1],
        "mean": statistics.mean(s),
        "median": pct(0.5),
        "p25": pct(0.25),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "stdev": statistics.pstdev(s) if len(s) > 1 else 0.0,
    }


def _recommend(summary: dict) -> int:
    """Recommend a min_score that lets the top ~10% of signals through.

    Real-money trading wants the strongest signals, not a thrice-daily
    firehose. p90 lets ~10% of scored events qualify, matching standard
    Phase 4 calibration on BTC where the bot fired ~2 trades/day.
    """
    if summary.get("n", 0) < 5:
        return 70  # fallback to project default when sample is thin
    p90 = summary.get("p90", 50.0)
    p75 = summary.get("p75", 50.0)
    # Floor at p75+5 so the threshold isn't an outlier of one sample.
    rec = max(p90, p75 + 5)
    rec = max(20, min(90, int(round(rec))))
    return rec


async def run(iterations: int, pause: float) -> dict:
    storage = Storage(SETTINGS.db_path)
    storage.init_db()
    aggregator = DataAggregator(SETTINGS, storage)

    regime_engine = RegimeClassifier(
        confirmation_bars=SETTINGS.regime.regime_confirmation_bars
    )
    trend = TrendEngine(SETTINGS)
    mom = MomentumEngine(SETTINGS)
    struct = StructureEngine(SETTINGS)
    flow = FlowEngine(SETTINGS)
    macro = MacroEngine(SETTINGS)
    scoring = ScoringEngine(
        trend_engine=trend,
        momentum_engine=mom,
        structure_engine=struct,
        flow_engine=flow,
        macro_engine=macro,
        settings=SETTINGS,
    )

    raw: dict[str, list[float]] = defaultdict(list)
    by_symbol: dict[str, list[float]] = defaultdict(list)
    started = datetime.now(timezone.utc).isoformat()

    for i in range(iterations):
        print(f"\n--- iteration {i + 1}/{iterations} ---")
        for asset_class, basket in ASSET_BASKETS.items():
            fetch_class = (
                "equity" if asset_class in ("equity", "options", "futures")
                else "crypto"
            )
            for sym in basket:
                got = await _score_one(
                    aggregator, scoring, regime_engine, sym, fetch_class
                )
                if not got or "error" in got:
                    print(f"  {asset_class:7s} {sym:6s}  skipped ({got.get('error') if got else 'no data'})")
                    continue
                long_s = got.get("LONG", {}).get("score")
                short_s = got.get("SHORT", {}).get("score")
                if isinstance(long_s, (int, float)):
                    raw[asset_class].append(long_s)
                    by_symbol[f"{sym}:LONG"].append(long_s)
                if isinstance(short_s, (int, float)):
                    raw[asset_class].append(short_s)
                    by_symbol[f"{sym}:SHORT"].append(short_s)
                print(
                    f"  {asset_class:7s} {sym:6s}  regime={got['regime']:10s}  "
                    f"LONG={long_s:>5.1f}  SHORT={short_s:>5.1f}"
                    if isinstance(long_s, (int, float)) and isinstance(short_s, (int, float))
                    else f"  {asset_class:7s} {sym:6s}  partial sample"
                )
        if i < iterations - 1:
            await asyncio.sleep(pause)

    summary = {
        "started": started,
        "ended": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
        "by_asset_class": {
            k: {**_summarise(v), "recommended_min_score": _recommend(_summarise(v))}
            for k, v in raw.items()
        },
        "by_symbol": {k: _summarise(v) for k, v in by_symbol.items()},
        "raw_counts": {k: len(v) for k, v in raw.items()},
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Score-distribution tuner")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument(
        "--out",
        type=str,
        default="docs/score_distribution.json",
    )
    args = parser.parse_args()

    summary = asyncio.run(run(args.iterations, args.pause))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print("\n=== RECOMMENDED THRESHOLDS ===")
    print(f"{'asset':10s} {'n':>5s} {'mean':>7s} {'p75':>7s} {'p90':>7s} {'p95':>7s} {'rec':>5s}")
    for ac, s in summary["by_asset_class"].items():
        if s.get("n", 0) == 0:
            print(f"{ac:10s}  (no samples)")
            continue
        print(
            f"{ac:10s} {s['n']:>5d} {s['mean']:>7.1f} {s['p75']:>7.1f} "
            f"{s['p90']:>7.1f} {s['p95']:>7.1f} {s['recommended_min_score']:>5d}"
        )
    print(f"\nFull distribution written to {out_path}")


if __name__ == "__main__":
    main()
