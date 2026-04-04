"""
Memory Engine — Persistent user state, preferences, and decision history.

Stores:
- User preferences (risk tolerance, favorite symbols, display prefs)
- Signal outcomes (what signals were generated, were they acted on, P&L)
- Decision log (every orchestrator decision with reasoning)
- Conversation context (rolling window for session continuity)

Uses SQLite for durability. All writes are append-only with timestamps
for full auditability.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger


_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    signal_id   TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    direction   TEXT,
    score       REAL,
    entry_price REAL,
    outcome     TEXT,          -- 'win', 'loss', 'scratch', 'pending'
    pnl         REAL,
    pnl_pct     REAL,
    acted_on    INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS decision_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    query       TEXT NOT NULL,
    category    TEXT NOT NULL,
    confidence  REAL,
    adapters    TEXT,          -- JSON array
    policy_ok   INTEGER DEFAULT 1,
    policy_reason TEXT,
    response_summary TEXT,
    latency_ms  REAL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_context (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,  -- 'user' or 'system'
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prefs_user ON user_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_user ON signal_outcomes(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_user ON decision_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session ON session_context(user_id, session_id, created_at);
"""


class MemoryEngine:
    """Thread-safe persistent memory for user state and audit trail."""

    def __init__(self, db_path: str = "data/lumare_memory.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript(_MEMORY_SCHEMA)
        conn.commit()

    # ─── Preferences ──────────────────────────────────────

    def set_preference(self, user_id: str, key: str, value: Any) -> None:
        """Upsert a user preference."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO user_preferences (user_id, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (user_id, key, json.dumps(value), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        logger.debug(f"Memory: set preference {key} for {user_id}")

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a single preference."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM user_preferences WHERE user_id=? AND key=?",
            (user_id, key),
        ).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get all preferences for a user."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, value FROM user_preferences WHERE user_id=?",
            (user_id,),
        ).fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # ─── Signal Outcomes ──────────────────────────────────

    def log_signal(
        self,
        user_id: str,
        signal_id: str,
        symbol: str,
        direction: str,
        score: float,
        entry_price: float = 0,
    ) -> None:
        """Record a signal that was generated."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO signal_outcomes
               (user_id, signal_id, symbol, direction, score, entry_price, outcome, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (user_id, signal_id, symbol, direction, score, entry_price,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    def resolve_signal(
        self,
        signal_id: str,
        outcome: str,
        pnl: float = 0,
        pnl_pct: float = 0,
        acted_on: bool = False,
    ) -> None:
        """Update a signal with its outcome."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE signal_outcomes
               SET outcome=?, pnl=?, pnl_pct=?, acted_on=?, resolved_at=?
               WHERE signal_id=?""",
            (outcome, pnl, pnl_pct, int(acted_on),
             datetime.now(timezone.utc).isoformat(), signal_id),
        )
        conn.commit()

    def get_signal_history(
        self, user_id: str, limit: int = 50, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent signal outcomes for a user."""
        conn = self._get_conn()
        if symbol:
            rows = conn.execute(
                """SELECT * FROM signal_outcomes
                   WHERE user_id=? AND symbol=?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, symbol, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM signal_outcomes
                   WHERE user_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_signal_stats(self, user_id: str) -> Dict[str, Any]:
        """Aggregate signal performance stats."""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN outcome IN ('win','loss') THEN pnl_pct ELSE NULL END) as avg_pnl_pct,
                SUM(CASE WHEN acted_on=1 THEN 1 ELSE 0 END) as acted_on
               FROM signal_outcomes WHERE user_id=? AND outcome != 'pending'""",
            (user_id,),
        ).fetchone()
        total = row["total"] or 0
        wins = row["wins"] or 0
        return {
            "total_signals": total,
            "wins": wins,
            "losses": row["losses"] or 0,
            "win_rate": wins / total if total > 0 else 0,
            "avg_pnl_pct": row["avg_pnl_pct"] or 0,
            "acted_on": row["acted_on"] or 0,
        }

    # ─── Decision Log ─────────────────────────────────────

    def log_decision(
        self,
        request_id: str,
        user_id: str,
        query: str,
        category: str,
        confidence: float,
        adapters: List[str],
        policy_ok: bool,
        policy_reason: str = "",
        response_summary: str = "",
        latency_ms: float = 0,
    ) -> None:
        """Record an orchestrator decision for audit."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO decision_log
               (request_id, user_id, query, category, confidence, adapters,
                policy_ok, policy_reason, response_summary, latency_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request_id, user_id, query, category, confidence,
             json.dumps(adapters), int(policy_ok), policy_reason,
             response_summary, latency_ms,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    def get_decision_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent decisions for audit review."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM decision_log
               WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Session Context ──────────────────────────────────

    def append_context(
        self, user_id: str, session_id: str, role: str, content: str
    ) -> None:
        """Append a message to session context."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO session_context (user_id, session_id, role, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, session_id, role, content,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    def get_context(
        self, user_id: str, session_id: str, limit: int = 20
    ) -> List[Dict[str, str]]:
        """Get recent session context (rolling window)."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT role, content FROM session_context
               WHERE user_id=? AND session_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ─── User Profile Assembly ────────────────────────────

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Assemble complete user profile for adapter context injection.
        Used by SLM to personalize responses.
        """
        prefs = self.get_all_preferences(user_id)
        stats = self.get_signal_stats(user_id)
        return {
            "user_id": user_id,
            "preferences": prefs,
            "signal_stats": stats,
            "risk_tolerance": prefs.get("risk_tolerance", "moderate"),
            "experience_level": prefs.get("experience_level", "intermediate"),
            "favorite_symbols": prefs.get("favorite_symbols", []),
            "preferred_timeframes": prefs.get("preferred_timeframes", ["4H", "1D"]),
        }
