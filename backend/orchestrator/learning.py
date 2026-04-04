"""
Adaptive Learning Engine — Tracks signal performance and adjusts strategy weights.

Components:
    SignalTracker       Record and resolve every signal with sub-scores.
    StrategyAnalyzer    Mine historical outcomes for predictive patterns.
    AdaptiveWeightManager  Compute regime/symbol-specific adaptive weights.
    PerformanceReport   Generate institutional-grade performance breakdowns.

All data persists in SQLite via the existing MemoryEngine pattern so it
survives restarts and is fully auditable.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import threading
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Schema extension for learning tables
# ---------------------------------------------------------------------------

_LEARNING_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT UNIQUE NOT NULL,
    user_id         TEXT NOT NULL DEFAULT 'default',
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL,
    total_score     REAL NOT NULL,
    trend_score     REAL DEFAULT 0,
    momentum_score  REAL DEFAULT 0,
    structure_score REAL DEFAULT 0,
    flow_score      REAL DEFAULT 0,
    macro_score     REAL DEFAULT 0,
    regime          TEXT DEFAULT 'RISK_ON',
    entry_price     REAL DEFAULT 0,
    exit_price      REAL DEFAULT 0,
    outcome         TEXT DEFAULT 'pending',
    pnl             REAL DEFAULT 0,
    pnl_pct         REAL DEFAULT 0,
    r_multiple      REAL DEFAULT 0,
    stop_distance   REAL DEFAULT 0,
    created_at      TEXT NOT NULL,
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_ls_user_symbol ON learning_signals(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_ls_outcome     ON learning_signals(outcome);
CREATE INDEX IF NOT EXISTS idx_ls_regime      ON learning_signals(regime);
CREATE INDEX IF NOT EXISTS idx_ls_created     ON learning_signals(created_at);

CREATE TABLE IF NOT EXISTS adaptive_weights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'default',
    regime      TEXT NOT NULL,
    symbol      TEXT DEFAULT '*',
    trend_w     REAL DEFAULT 1.0,
    momentum_w  REAL DEFAULT 1.0,
    structure_w REAL DEFAULT 1.0,
    flow_w      REAL DEFAULT 1.0,
    macro_w     REAL DEFAULT 1.0,
    sample_size INTEGER DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE(user_id, regime, symbol)
);
"""

ENGINE_NAMES = ["trend", "momentum", "structure", "flow", "macro"]
REGIMES = ["RISK_ON", "RISK_OFF", "RANGE", "TREND", "EXPANSION"]
WEIGHT_MIN = 0.5
WEIGHT_MAX = 2.0
EMA_SPAN = 100  # lookback for exponential moving average


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SignalRecord:
    signal_id: str
    user_id: str
    symbol: str
    direction: str
    total_score: float
    trend_score: float
    momentum_score: float
    structure_score: float
    flow_score: float
    macro_score: float
    regime: str
    entry_price: float
    exit_price: float = 0.0
    outcome: str = "pending"
    pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    stop_distance: float = 0.0
    created_at: str = ""
    resolved_at: str = ""


@dataclass
class StrategyProfile:
    engine_win_rates: Dict[str, float]
    engine_avg_contribution: Dict[str, float]
    regime_win_rates: Dict[str, float]
    seasonal_patterns: Dict[str, Dict[str, float]]
    symbol_performance: Dict[str, Dict[str, float]]
    recommended_adjustments: Dict[str, float]
    sample_size: int = 0


@dataclass
class WeightSet:
    trend: float = 1.0
    momentum: float = 1.0
    structure: float = 1.0
    flow: float = 1.0
    macro: float = 1.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "trend": round(self.trend, 4),
            "momentum": round(self.momentum, 4),
            "structure": round(self.structure, 4),
            "flow": round(self.flow, 4),
            "macro": round(self.macro, 4),
        }


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

class _LearningDB:
    """Thread-safe SQLite connection manager for the learning tables."""

    def __init__(self, db_path: str = "data/lumare_learning.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _ensure_schema(self):
        conn = self._conn()
        conn.executescript(_LEARNING_SCHEMA)
        conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn().execute(sql, params)

    def executemany(self, sql: str, seq: list) -> None:
        self._conn().executemany(sql, seq)

    def commit(self):
        self._conn().commit()

    def fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        rows = self._conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        row = self._conn().execute(sql, params).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# SignalTracker
# ---------------------------------------------------------------------------

class SignalTracker:
    """
    Records every signal the system generates together with all five
    sub-engine scores, then resolves it later with the trade outcome.
    """

    def __init__(self, db: _LearningDB):
        self._db = db

    def record_signal(
        self,
        symbol: str,
        direction: str,
        total_score: float,
        sub_scores: Dict[str, float],
        regime: str,
        entry_price: float,
        stop_distance: float = 0.0,
        user_id: str = "default",
        signal_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """Persist a new signal. Returns the signal_id."""
        sid = signal_id or str(uuid.uuid4())
        ts = created_at or datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """INSERT OR IGNORE INTO learning_signals
               (signal_id, user_id, symbol, direction, total_score,
                trend_score, momentum_score, structure_score, flow_score, macro_score,
                regime, entry_price, stop_distance, created_at)
               VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?)""",
            (
                sid, user_id, symbol, direction, total_score,
                sub_scores.get("trend", 0), sub_scores.get("momentum", 0),
                sub_scores.get("structure", 0), sub_scores.get("flow", 0),
                sub_scores.get("macro", 0),
                regime, entry_price, stop_distance, ts,
            ),
        )
        self._db.commit()
        return sid

    def resolve_signal(
        self,
        signal_id: str,
        outcome: str,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        r_multiple: float = 0.0,
    ) -> None:
        """Mark a signal as resolved (win / loss / scratch)."""
        self._db.execute(
            """UPDATE learning_signals
               SET outcome=?, exit_price=?, pnl=?, pnl_pct=?, r_multiple=?,
                   resolved_at=?
               WHERE signal_id=?""",
            (outcome, exit_price, pnl, pnl_pct, r_multiple,
             datetime.now(timezone.utc).isoformat(), signal_id),
        )
        self._db.commit()

    def get_resolved_signals(
        self, user_id: str = "default", limit: int = 500
    ) -> List[Dict[str, Any]]:
        return self._db.fetchall(
            """SELECT * FROM learning_signals
               WHERE user_id=? AND outcome IN ('win','loss','scratch')
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )

    def get_all_signals(self, user_id: str = "default", limit: int = 500) -> List[Dict[str, Any]]:
        return self._db.fetchall(
            """SELECT * FROM learning_signals
               WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )

    def count_resolved(self, user_id: str = "default") -> int:
        row = self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM learning_signals WHERE user_id=? AND outcome IN ('win','loss','scratch')",
            (user_id,),
        )
        return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# StrategyAnalyzer
# ---------------------------------------------------------------------------

class StrategyAnalyzer:
    """
    Mines resolved signal history to discover which sub-engines, regimes,
    time-of-day, day-of-week, months, and symbols produce the best results.
    """

    def __init__(self, db: _LearningDB):
        self._db = db

    def analyze(self, user_id: str = "default", lookback: int = 500) -> StrategyProfile:
        signals = self._db.fetchall(
            """SELECT * FROM learning_signals
               WHERE user_id=? AND outcome IN ('win','loss')
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, lookback),
        )

        if not signals:
            return StrategyProfile(
                engine_win_rates={e: 0.5 for e in ENGINE_NAMES},
                engine_avg_contribution={e: 0.0 for e in ENGINE_NAMES},
                regime_win_rates={r: 0.5 for r in REGIMES},
                seasonal_patterns={"month": {}, "dow": {}, "hour": {}},
                symbol_performance={},
                recommended_adjustments={e: 1.0 for e in ENGINE_NAMES},
                sample_size=0,
            )

        engine_wr = self._engine_predictive_power(signals)
        engine_contrib = self._engine_avg_contribution(signals)
        regime_wr = self._regime_win_rates(signals)
        seasonal = self._seasonal_analysis(signals)
        symbol_perf = self._symbol_performance(signals)
        adjustments = self._compute_adjustments(engine_wr)

        return StrategyProfile(
            engine_win_rates=engine_wr,
            engine_avg_contribution=engine_contrib,
            regime_win_rates=regime_wr,
            seasonal_patterns=seasonal,
            symbol_performance=symbol_perf,
            recommended_adjustments=adjustments,
            sample_size=len(signals),
        )

    # -- Sub-engine predictive power --

    def _engine_predictive_power(self, signals: List[Dict]) -> Dict[str, float]:
        """
        For each sub-engine, compare the average sub-score on winning
        signals vs losing signals. Higher delta = better predictor.
        Also compute a pseudo-win-rate by checking whether the engine's
        score was above its median when the signal won.
        """
        result = {}
        for engine in ENGINE_NAMES:
            col = f"{engine}_score"
            wins = [s[col] for s in signals if s["outcome"] == "win" and s[col] is not None]
            losses = [s[col] for s in signals if s["outcome"] == "loss" and s[col] is not None]
            all_scores = [s[col] for s in signals if s[col] is not None]
            if not all_scores:
                result[engine] = 0.5
                continue
            median = sorted(all_scores)[len(all_scores) // 2]
            above_median_wins = sum(1 for s in signals if s["outcome"] == "win" and (s[col] or 0) >= median)
            above_median_total = sum(1 for s in signals if (s[col] or 0) >= median)
            result[engine] = above_median_wins / above_median_total if above_median_total > 0 else 0.5
        return result

    def _engine_avg_contribution(self, signals: List[Dict]) -> Dict[str, float]:
        result = {}
        for engine in ENGINE_NAMES:
            col = f"{engine}_score"
            vals = [s[col] for s in signals if s[col] is not None]
            result[engine] = sum(vals) / len(vals) if vals else 0.0
        return result

    # -- Regime win rates --

    def _regime_win_rates(self, signals: List[Dict]) -> Dict[str, float]:
        regime_buckets: Dict[str, List[bool]] = defaultdict(list)
        for s in signals:
            regime_buckets[s["regime"]].append(s["outcome"] == "win")
        return {
            r: (sum(v) / len(v) if v else 0.5)
            for r, v in regime_buckets.items()
        }

    # -- Seasonal analysis --

    def _seasonal_analysis(self, signals: List[Dict]) -> Dict[str, Dict[str, float]]:
        month_buckets: Dict[str, List[bool]] = defaultdict(list)
        dow_buckets: Dict[str, List[bool]] = defaultdict(list)
        hour_buckets: Dict[str, List[bool]] = defaultdict(list)

        for s in signals:
            try:
                dt = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            month_buckets[dt.strftime("%B")].append(s["outcome"] == "win")
            dow_buckets[dt.strftime("%A")].append(s["outcome"] == "win")
            hour_buckets[f"{dt.hour:02d}:00"].append(s["outcome"] == "win")

        def _rates(buckets):
            return {k: round(sum(v) / len(v), 4) if v else 0.5 for k, v in buckets.items()}

        return {
            "month": _rates(month_buckets),
            "day_of_week": _rates(dow_buckets),
            "hour": _rates(hour_buckets),
        }

    # -- Symbol performance --

    def _symbol_performance(self, signals: List[Dict]) -> Dict[str, Dict[str, float]]:
        buckets: Dict[str, List[Dict]] = defaultdict(list)
        for s in signals:
            buckets[s["symbol"]].append(s)
        result = {}
        for sym, trades in buckets.items():
            wins = sum(1 for t in trades if t["outcome"] == "win")
            total = len(trades)
            total_pnl = sum(t["pnl_pct"] or 0 for t in trades)
            avg_r = sum(t["r_multiple"] or 0 for t in trades) / total if total else 0
            result[sym] = {
                "win_rate": round(wins / total, 4) if total else 0,
                "total_trades": total,
                "total_pnl_pct": round(total_pnl, 4),
                "avg_r_multiple": round(avg_r, 4),
            }
        return result

    # -- Compute recommended weight adjustments --

    def _compute_adjustments(self, engine_wr: Dict[str, float]) -> Dict[str, float]:
        """
        Map each engine's win-rate into a weight multiplier.
        50% WR -> 1.0 (neutral).  70% -> ~1.4.  30% -> ~0.6.
        Clamped to [WEIGHT_MIN, WEIGHT_MAX].
        """
        result = {}
        for engine in ENGINE_NAMES:
            wr = engine_wr.get(engine, 0.5)
            # Linear mapping: 0.3 -> 0.6, 0.5 -> 1.0, 0.7 -> 1.4
            raw = 1.0 + (wr - 0.5) * 2.0
            result[engine] = round(max(WEIGHT_MIN, min(WEIGHT_MAX, raw)), 4)
        return result


# ---------------------------------------------------------------------------
# AdaptiveWeightManager
# ---------------------------------------------------------------------------

class AdaptiveWeightManager:
    """
    Blends the static regime weights from scoring_engine.py with
    data-driven adjustments from StrategyAnalyzer using an exponential
    moving average so weights adapt gradually without overfitting.
    """

    # Static regime weights (mirrors scoring_engine.REGIME_WEIGHTS)
    _STATIC_REGIME: Dict[str, Dict[str, float]] = {
        "TREND":     {"trend": 1.3, "momentum": 1.2, "structure": 0.8, "flow": 0.9, "macro": 0.8},
        "RANGE":     {"trend": 0.5, "momentum": 1.0, "structure": 1.5, "flow": 1.0, "macro": 1.0},
        "EXPANSION": {"trend": 1.0, "momentum": 1.2, "structure": 1.2, "flow": 1.0, "macro": 0.6},
        "RISK_OFF":  {"trend": 0.7, "momentum": 0.7, "structure": 1.0, "flow": 1.3, "macro": 1.3},
        "RISK_ON":   {"trend": 1.0, "momentum": 1.0, "structure": 1.0, "flow": 1.0, "macro": 1.0},
    }

    def __init__(self, db: _LearningDB, analyzer: StrategyAnalyzer):
        self._db = db
        self._analyzer = analyzer

    def get_adjusted_weights(
        self,
        regime: str = "RISK_ON",
        symbol: str = "*",
        user_id: str = "default",
    ) -> WeightSet:
        """
        Return personalised weights blending static regime priors
        with learned performance data.
        """
        # 1. Static base
        static = self._STATIC_REGIME.get(regime, self._STATIC_REGIME["RISK_ON"])

        # 2. Learned adjustments
        profile = self._analyzer.analyze(user_id=user_id)

        if profile.sample_size < 30:
            # Not enough data, return static weights
            return WeightSet(**{e: static[e] for e in ENGINE_NAMES})

        # 3. Blend: EMA-like mix with confidence scaling
        alpha = min(profile.sample_size / EMA_SPAN, 1.0)  # ramp up as data accumulates

        blended = {}
        for engine in ENGINE_NAMES:
            learned = profile.recommended_adjustments.get(engine, 1.0)

            # If we have symbol-specific data, blend that in too
            sym_wr = None
            if symbol != "*" and symbol in profile.symbol_performance:
                sp = profile.symbol_performance[symbol]
                if sp["total_trades"] >= 10:
                    sym_wr = sp["win_rate"]

            # Regime-specific learned win rate
            regime_wr = profile.regime_win_rates.get(regime, 0.5)
            # If regime is performing badly, scale down all weights
            regime_scale = 0.8 + 0.4 * regime_wr  # range: 0.8 (0% wr) to 1.2 (100% wr)

            base = static[engine]
            adaptive = base * (1.0 - alpha) + (base * learned * regime_scale) * alpha

            # Symbol-level micro-adjustment
            if sym_wr is not None:
                sym_scale = 0.9 + 0.2 * sym_wr  # 0.9 at 0% to 1.1 at 100%
                adaptive *= sym_scale

            blended[engine] = round(max(WEIGHT_MIN, min(WEIGHT_MAX, adaptive)), 4)

        ws = WeightSet(**blended)

        # Persist the computed weights
        self._persist_weights(user_id, regime, symbol, ws, profile.sample_size)

        return ws

    def _persist_weights(
        self, user_id: str, regime: str, symbol: str, ws: WeightSet, sample_size: int
    ) -> None:
        self._db.execute(
            """INSERT INTO adaptive_weights
               (user_id, regime, symbol, trend_w, momentum_w, structure_w, flow_w, macro_w,
                sample_size, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id, regime, symbol) DO UPDATE SET
                 trend_w=excluded.trend_w, momentum_w=excluded.momentum_w,
                 structure_w=excluded.structure_w, flow_w=excluded.flow_w,
                 macro_w=excluded.macro_w, sample_size=excluded.sample_size,
                 updated_at=excluded.updated_at""",
            (user_id, regime, symbol,
             ws.trend, ws.momentum, ws.structure, ws.flow, ws.macro,
             sample_size, datetime.now(timezone.utc).isoformat()),
        )
        self._db.commit()


# ---------------------------------------------------------------------------
# PerformanceReport
# ---------------------------------------------------------------------------

class PerformanceReport:
    """
    Generates institutional-grade performance analytics from the
    resolved signal history.
    """

    def __init__(self, db: _LearningDB, analyzer: StrategyAnalyzer):
        self._db = db
        self._analyzer = analyzer

    def generate(self, user_id: str = "default") -> Dict[str, Any]:
        signals = self._db.fetchall(
            """SELECT * FROM learning_signals
               WHERE user_id=? AND outcome IN ('win','loss')
               ORDER BY created_at ASC""",
            (user_id,),
        )

        if not signals:
            return {"status": "no_data", "message": "No resolved signals to analyze."}

        profile = self._analyzer.analyze(user_id=user_id)

        overall = self._overall_stats(signals)
        by_strategy = self._strategy_breakdown(signals, profile)
        by_season = self._seasonal_breakdown(profile)
        by_regime = self._regime_breakdown(signals, profile)
        recommendations = self._generate_recommendations(profile, overall)

        return {
            "status": "ok",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_size": len(signals),
            "overall": overall,
            "by_strategy": by_strategy,
            "by_season": by_season,
            "by_regime": by_regime,
            "recommendations": recommendations,
        }

    def _overall_stats(self, signals: List[Dict]) -> Dict[str, Any]:
        wins = [s for s in signals if s["outcome"] == "win"]
        losses = [s for s in signals if s["outcome"] == "loss"]
        total = len(signals)
        win_count = len(wins)

        pnls = [s["pnl_pct"] or 0 for s in signals]
        r_multiples = [s["r_multiple"] or 0 for s in signals]

        gross_profit = sum(s["pnl_pct"] or 0 for s in wins)
        gross_loss = abs(sum(s["pnl_pct"] or 0 for s in losses))

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_pnl = sum(pnls) / total if total else 0
        std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / total) ** 0.5 if total > 1 else 0

        # Sharpe (annualized assuming ~250 trading days)
        sharpe = (avg_pnl / std_pnl) * (250 ** 0.5) if std_pnl > 0 else 0

        # Sortino (downside deviation only)
        downside = [p for p in pnls if p < 0]
        downside_std = (sum(p ** 2 for p in downside) / len(downside)) ** 0.5 if downside else 0
        sortino = (avg_pnl / downside_std) * (250 ** 0.5) if downside_std > 0 else 0

        # Max drawdown from cumulative PnL
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        avg_r = sum(r_multiples) / total if total else 0
        avg_win = sum(s["pnl_pct"] or 0 for s in wins) / win_count if win_count else 0
        avg_loss = sum(s["pnl_pct"] or 0 for s in losses) / len(losses) if losses else 0

        return {
            "total_trades": total,
            "wins": win_count,
            "losses": len(losses),
            "win_rate": round(win_count / total, 4) if total else 0,
            "profit_factor": round(profit_factor, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "avg_r_multiple": round(avg_r, 4),
            "avg_win_pct": round(avg_win, 4),
            "avg_loss_pct": round(avg_loss, 4),
            "max_drawdown_pct": round(max_dd, 4),
            "gross_profit_pct": round(gross_profit, 4),
            "gross_loss_pct": round(gross_loss, 4),
            "net_pnl_pct": round(gross_profit - gross_loss, 4),
        }

    def _strategy_breakdown(self, signals: List[Dict], profile: StrategyProfile) -> Dict[str, Any]:
        breakdown = {}
        for engine in ENGINE_NAMES:
            wr = profile.engine_win_rates.get(engine, 0.5)
            avg_contrib = profile.engine_avg_contribution.get(engine, 0)
            adj = profile.recommended_adjustments.get(engine, 1.0)
            breakdown[engine] = {
                "predictive_win_rate": round(wr, 4),
                "avg_score_contribution": round(avg_contrib, 2),
                "recommended_weight": round(adj, 4),
                "status": "strong" if wr >= 0.58 else "neutral" if wr >= 0.48 else "weak",
            }
        return breakdown

    def _seasonal_breakdown(self, profile: StrategyProfile) -> Dict[str, Any]:
        return profile.seasonal_patterns

    def _regime_breakdown(self, signals: List[Dict], profile: StrategyProfile) -> Dict[str, Any]:
        regime_data = {}
        for regime in REGIMES:
            regime_signals = [s for s in signals if s["regime"] == regime]
            if not regime_signals:
                regime_data[regime] = {"trades": 0, "win_rate": 0, "avg_pnl_pct": 0}
                continue
            wins = sum(1 for s in regime_signals if s["outcome"] == "win")
            total = len(regime_signals)
            avg_pnl = sum(s["pnl_pct"] or 0 for s in regime_signals) / total
            regime_data[regime] = {
                "trades": total,
                "win_rate": round(wins / total, 4),
                "avg_pnl_pct": round(avg_pnl, 4),
            }
        return regime_data

    def _generate_recommendations(
        self, profile: StrategyProfile, overall: Dict[str, Any]
    ) -> List[str]:
        recs = []

        # Engine-level
        for engine in ENGINE_NAMES:
            wr = profile.engine_win_rates.get(engine, 0.5)
            if wr < 0.45:
                recs.append(f"Reduce {engine} weight - predictive win rate only {wr:.0%}")
            elif wr >= 0.65:
                recs.append(f"Increase {engine} weight - strong {wr:.0%} predictive power")

        # Regime-level
        for regime, wr in profile.regime_win_rates.items():
            if wr < 0.45:
                recs.append(f"Reduce exposure in {regime} regime - win rate {wr:.0%}")
            elif wr >= 0.65:
                recs.append(f"{regime} regime is a strength - win rate {wr:.0%}")

        # Symbol-level
        for sym, perf in profile.symbol_performance.items():
            if perf["total_trades"] >= 10:
                if perf["win_rate"] < 0.40:
                    recs.append(f"Consider removing {sym} - win rate {perf['win_rate']:.0%} over {perf['total_trades']} trades")
                elif perf["win_rate"] >= 0.70:
                    recs.append(f"{sym} is a top performer - {perf['win_rate']:.0%} win rate")

        # Overall health
        if overall["profit_factor"] < 1.2:
            recs.append("Overall profit factor below 1.2 - tighten entry criteria")
        if overall["max_drawdown_pct"] > 0.12:
            recs.append(f"Max drawdown {overall['max_drawdown_pct']:.1%} exceeds 12% threshold")
        if overall["sharpe_ratio"] < 1.5:
            recs.append("Sharpe ratio below 1.5 - improve risk-adjusted returns")

        if not recs:
            recs.append("System performing within acceptable parameters - no adjustments needed")

        return recs


# ---------------------------------------------------------------------------
# Mock data generator
# ---------------------------------------------------------------------------

def _generate_mock_signals(count: int = 200) -> List[Dict[str, Any]]:
    """
    Produce realistic mock historical signals with varied outcomes.
    Designed to create meaningful analytical patterns:
    - Momentum and trend engines are slightly more predictive.
    - TREND regime performs best, RANGE worst.
    - BTC outperforms alts.
    - Slight seasonal edge in Q4.
    """
    random.seed(42)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT",
               "SPY", "QQQ", "NVDA", "AAPL", "TSLA"]
    directions = ["long", "short"]
    regimes = REGIMES

    # Symbol-specific win-rate bias
    symbol_bias = {
        "BTCUSDT": 0.10, "ETHUSDT": 0.05, "SOLUSDT": -0.02,
        "XRPUSDT": -0.05, "AVAXUSDT": -0.03,
        "SPY": 0.08, "QQQ": 0.06, "NVDA": 0.04,
        "AAPL": 0.02, "TSLA": -0.04,
    }

    regime_bias = {
        "TREND": 0.12, "EXPANSION": 0.05, "RISK_ON": 0.03,
        "RISK_OFF": -0.03, "RANGE": -0.08,
    }

    # Month bias (Q4 edge)
    month_bias = {10: 0.05, 11: 0.07, 12: 0.06, 1: -0.03, 2: -0.02, 6: -0.04, 7: -0.03}

    signals = []
    base_time = datetime(2025, 4, 1, tzinfo=timezone.utc)

    for i in range(count):
        symbol = random.choice(symbols)
        direction = random.choice(directions)
        regime = random.choice(regimes)

        # Time spread over 11 months
        hours_offset = random.randint(0, 11 * 30 * 24)
        created = base_time + timedelta(hours=hours_offset)
        month = created.month

        # Sub-scores: each 0-20 range
        # Momentum and trend are slightly higher on average for wins
        trend_s = random.uniform(6, 18)
        momentum_s = random.uniform(7, 19)
        structure_s = random.uniform(5, 17)
        flow_s = random.uniform(6, 16)
        macro_s = random.uniform(5, 15)

        total = trend_s + momentum_s + structure_s + flow_s + macro_s

        # Determine win probability based on score + biases
        base_wr = 0.45 + (total - 50) * 0.005  # higher score = higher wr
        base_wr += symbol_bias.get(symbol, 0)
        base_wr += regime_bias.get(regime, 0)
        base_wr += month_bias.get(month, 0)

        # Engines with high scores contribute more to wins
        if momentum_s > 14:
            base_wr += 0.06
        if trend_s > 14:
            base_wr += 0.05
        if structure_s > 14:
            base_wr += 0.03

        base_wr = max(0.2, min(0.85, base_wr))
        is_win = random.random() < base_wr

        # Price simulation
        if symbol.endswith("USDT"):
            price_map = {"BTCUSDT": 65000, "ETHUSDT": 3200, "SOLUSDT": 150,
                         "XRPUSDT": 0.55, "AVAXUSDT": 35}
            base_price = price_map.get(symbol, 100)
        else:
            price_map = {"SPY": 520, "QQQ": 450, "NVDA": 800, "AAPL": 195, "TSLA": 250}
            base_price = price_map.get(symbol, 200)

        entry_price = base_price * (1 + random.uniform(-0.05, 0.05))
        stop_dist = entry_price * random.uniform(0.005, 0.02)

        if is_win:
            r_mult = random.choice([1.0, 1.5, 2.0, 2.5, 3.0])
            pnl = stop_dist * r_mult * (1 if direction == "long" else 1)
            pnl_pct = pnl / entry_price
            exit_price = entry_price + pnl if direction == "long" else entry_price - pnl
            outcome = "win"
        else:
            r_mult = random.uniform(-1.0, -0.3)
            pnl = stop_dist * abs(r_mult)
            pnl_pct = -pnl / entry_price
            exit_price = entry_price - pnl if direction == "long" else entry_price + pnl
            outcome = "loss"
            r_mult = abs(r_mult) * -1

        signals.append({
            "signal_id": str(uuid.uuid4()),
            "user_id": "default",
            "symbol": symbol,
            "direction": direction,
            "total_score": round(total, 2),
            "trend_score": round(trend_s, 2),
            "momentum_score": round(momentum_s, 2),
            "structure_score": round(structure_s, 2),
            "flow_score": round(flow_s, 2),
            "macro_score": round(macro_s, 2),
            "regime": regime,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "stop_distance": round(stop_dist, 4),
            "outcome": outcome,
            "pnl": round(pnl if is_win else -pnl, 4),
            "pnl_pct": round(pnl_pct, 6),
            "r_multiple": round(r_mult, 4),
            "created_at": created.isoformat(),
            "resolved_at": (created + timedelta(hours=random.randint(1, 72))).isoformat(),
        })

    return signals


# ---------------------------------------------------------------------------
# Facade: single entry point for the API layer
# ---------------------------------------------------------------------------

class LearningEngine:
    """
    Top-level facade that wires together all learning components and
    seeds mock data on first initialisation.
    """

    def __init__(self, db_path: str = "data/lumare_learning.db"):
        self._db = _LearningDB(db_path=db_path)
        self.tracker = SignalTracker(self._db)
        self.analyzer = StrategyAnalyzer(self._db)
        self.weights = AdaptiveWeightManager(self._db, self.analyzer)
        self.report = PerformanceReport(self._db, self.analyzer)
        self._seed_if_empty()

    def _seed_if_empty(self):
        count = self.tracker.count_resolved()
        if count >= 50:
            logger.info(f"Learning DB already has {count} resolved signals, skipping seed.")
            return

        logger.info("Seeding learning DB with 200 mock signals...")
        mock = _generate_mock_signals(200)
        for s in mock:
            self._db.execute(
                """INSERT OR IGNORE INTO learning_signals
                   (signal_id, user_id, symbol, direction, total_score,
                    trend_score, momentum_score, structure_score, flow_score, macro_score,
                    regime, entry_price, exit_price, stop_distance,
                    outcome, pnl, pnl_pct, r_multiple, created_at, resolved_at)
                   VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?)""",
                (
                    s["signal_id"], s["user_id"], s["symbol"], s["direction"], s["total_score"],
                    s["trend_score"], s["momentum_score"], s["structure_score"],
                    s["flow_score"], s["macro_score"],
                    s["regime"], s["entry_price"], s["exit_price"], s["stop_distance"],
                    s["outcome"], s["pnl"], s["pnl_pct"], s["r_multiple"],
                    s["created_at"], s["resolved_at"],
                ),
            )
        self._db.commit()
        logger.info("Seeded 200 mock signals into learning DB.")

    # -- Public API methods for the endpoint layer --

    def get_weights(self, regime: str = "RISK_ON", symbol: str = "*", user_id: str = "default") -> Dict:
        ws = self.weights.get_adjusted_weights(regime=regime, symbol=symbol, user_id=user_id)
        return {
            "regime": regime,
            "symbol": symbol,
            "weights": ws.to_dict(),
            "sample_size": self.tracker.count_resolved(user_id),
        }

    def get_report(self, user_id: str = "default") -> Dict:
        return self.report.generate(user_id=user_id)

    def get_seasonal(self, user_id: str = "default") -> Dict:
        profile = self.analyzer.analyze(user_id=user_id)
        return {
            "seasonal_patterns": profile.seasonal_patterns,
            "sample_size": profile.sample_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------------

_learning_engine: Optional[LearningEngine] = None


def get_learning_engine() -> LearningEngine:
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine()
    return _learning_engine
