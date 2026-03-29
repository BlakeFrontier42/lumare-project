"""
Lumare MIE — SQLite Storage Layer

Thread-safe, production-grade storage for all system data:
- OHLCV candles (multi-symbol, multi-timeframe)
- Trade logs with full metadata
- Signal computation logs
- Regime transition logs
- Portfolio snapshots
- Risk events
- Performance snapshots

All timestamps are enforced as UTC ISO-8601 strings to prevent lookahead bias.
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when a storage operation fails."""


def _utc_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_timestamp(ts: str, field_name: str = "timestamp") -> str:
    """
    Validate and normalize a timestamp string to ISO-8601 UTC.
    Raises StorageError if the timestamp is unparseable.
    """
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            # Assume UTC if no timezone provided
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError) as exc:
        raise StorageError(
            f"Invalid timestamp for '{field_name}': {ts!r}"
        ) from exc


# ─── Schema Definitions ────────────────────────────────────

_SCHEMA_SQL = """
-- OHLCV candle data, partitioned by symbol and timeframe
CREATE TABLE IF NOT EXISTS candles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,   -- ISO-8601 UTC, bar open time
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          REAL    NOT NULL,
    trade_count     INTEGER,            -- optional: number of trades
    vwap            REAL,               -- optional: volume-weighted avg price
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candles_sym_tf_ts
    ON candles(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_candles_ts
    ON candles(timestamp);

-- Trade log: every executed trade with full metadata
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL UNIQUE,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL CHECK(side IN ('LONG', 'SHORT')),
    entry_time      TEXT    NOT NULL,
    exit_time       TEXT,
    entry_price     REAL    NOT NULL,
    exit_price      REAL,
    quantity        REAL    NOT NULL,
    leverage        REAL    NOT NULL DEFAULT 1.0,
    stop_loss       REAL,
    take_profit     REAL,
    risk_pct        REAL,               -- % of portfolio risked
    pnl             REAL,               -- realized P&L
    pnl_pct         REAL,               -- P&L as % of entry notional
    r_multiple      REAL,               -- P&L in R-units
    fees            REAL    DEFAULT 0.0,
    slippage        REAL    DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT 'OPEN'
                        CHECK(status IN ('OPEN', 'CLOSED', 'CANCELLED', 'PARTIAL')),
    strategy        TEXT,               -- strategy name that generated this
    regime          TEXT,               -- regime at entry
    signal_score    INTEGER,            -- composite score at entry
    timeframe       TEXT,
    tags            TEXT,               -- JSON array of tags
    notes           TEXT,
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);

-- Signal computation log: every signal evaluation
CREATE TABLE IF NOT EXISTS signal_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL,
    trend_score     REAL,
    momentum_score  REAL,
    structure_score REAL,
    flow_score      REAL,
    macro_score     REAL,
    composite_score REAL    NOT NULL,
    direction       TEXT    CHECK(direction IN ('LONG', 'SHORT', 'NEUTRAL')),
    regime          TEXT,
    components      TEXT,               -- JSON blob of sub-component details
    action_taken    TEXT,               -- TRADE / SKIP / WATCH
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_signal_logs_sym_ts
    ON signal_logs(symbol, timestamp);

-- Regime transition log
CREATE TABLE IF NOT EXISTS regime_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    previous_regime TEXT,
    new_regime      TEXT    NOT NULL,
    trigger_reason  TEXT,               -- what caused the transition
    adx_value       REAL,
    atr_percentile  REAL,
    vol_percentile  REAL,
    confirmation_bars INTEGER,
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_regime_logs_sym_ts
    ON regime_logs(symbol, timestamp);

-- Portfolio snapshots (periodic state capture)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    total_equity    REAL    NOT NULL,
    cash            REAL    NOT NULL,
    unrealized_pnl  REAL    NOT NULL DEFAULT 0.0,
    realized_pnl    REAL    NOT NULL DEFAULT 0.0,
    portfolio_heat  REAL    NOT NULL DEFAULT 0.0,   -- % of capital at risk
    open_positions  INTEGER NOT NULL DEFAULT 0,
    drawdown_pct    REAL    NOT NULL DEFAULT 0.0,
    peak_equity     REAL    NOT NULL,
    positions_json  TEXT,               -- JSON snapshot of all positions
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_portfolio_ts
    ON portfolio_snapshots(timestamp);

-- Risk events (circuit breakers, warnings, anomalies)
CREATE TABLE IF NOT EXISTS risk_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,   -- DRAWDOWN_PAUSE, DRAWDOWN_REDUCE,
                                        -- DRAWDOWN_SHUTDOWN, CORRELATION_BREACH,
                                        -- VAR_BREACH, DAILY_LOSS_CAP, etc.
    severity        TEXT    NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
    description     TEXT    NOT NULL,
    current_value   REAL,               -- the metric value that triggered it
    threshold_value REAL,               -- the threshold that was breached
    action_taken    TEXT,               -- what the system did in response
    metadata        TEXT,               -- JSON blob of additional context
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_risk_events_ts
    ON risk_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_risk_events_type
    ON risk_events(event_type);

-- Performance snapshots (daily or periodic metrics)
CREATE TABLE IF NOT EXISTS performance_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    period          TEXT    NOT NULL DEFAULT 'daily',   -- daily, weekly, monthly
    total_trades    INTEGER NOT NULL DEFAULT 0,
    winning_trades  INTEGER NOT NULL DEFAULT 0,
    losing_trades   INTEGER NOT NULL DEFAULT 0,
    win_rate        REAL,
    avg_win         REAL,
    avg_loss        REAL,
    profit_factor   REAL,
    sharpe_ratio    REAL,
    sortino_ratio   REAL,
    calmar_ratio    REAL,
    max_drawdown    REAL,
    total_pnl       REAL,
    avg_r_multiple  REAL,
    best_trade_pnl  REAL,
    worst_trade_pnl REAL,
    avg_hold_time_minutes REAL,
    metadata        TEXT,               -- JSON blob for additional metrics
    inserted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_performance_ts
    ON performance_snapshots(timestamp);
"""


class Storage:
    """
    Thread-safe SQLite storage engine for the Lumare MIE.

    Usage:
        storage = Storage("data/lumare.db")
        storage.init_db()
        storage.store_candles("BTCUSDT", "1H", candles_df)
    """

    def __init__(self, db_path: str = "data/lumare.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()

        # Ensure parent directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ─── Connection Management ──────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a thread-local connection. Each thread gets its own
        connection to avoid SQLite threading issues.
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self._db_path,
                timeout=30.0,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """
        Context manager that yields a cursor inside a transaction.
        Commits on success, rolls back on exception.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN")
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    @contextmanager
    def _read_cursor(self):
        """Context manager for read-only operations."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def close(self):
        """Close the thread-local connection if it exists."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # ─── Schema Initialization ──────────────────────────────

    def init_db(self) -> None:
        """Create all tables and indexes. Safe to call multiple times."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized at %s", self._db_path)

    # ─── Candle Storage ─────────────────────────────────────

    def store_candles(
        self,
        symbol: str,
        timeframe: str,
        candles_df: pd.DataFrame,
    ) -> int:
        """
        Store OHLCV candles from a DataFrame.

        Expected columns: timestamp, open, high, low, close, volume
        Optional columns: trade_count, vwap

        Uses INSERT OR REPLACE to handle duplicates on
        (symbol, timeframe, timestamp).

        Returns the number of rows inserted/replaced.
        """
        if candles_df.empty:
            return 0

        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(candles_df.columns)
        if missing:
            raise StorageError(
                f"candles_df missing required columns: {missing}"
            )

        rows = []
        for _, row in candles_df.iterrows():
            ts = str(row["timestamp"])
            ts = _validate_timestamp(ts, "candle.timestamp")
            rows.append((
                symbol,
                timeframe,
                ts,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
                int(row["trade_count"]) if "trade_count" in row and pd.notna(row.get("trade_count")) else None,
                float(row["vwap"]) if "vwap" in row and pd.notna(row.get("vwap")) else None,
            ))

        with self._transaction() as cursor:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO candles
                    (symbol, timeframe, timestamp, open, high, low, close,
                     volume, trade_count, vwap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        logger.debug(
            "Stored %d candles for %s/%s", len(rows), symbol, timeframe
        )
        return len(rows)

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        Retrieve OHLCV candles for a symbol/timeframe within a time range.

        Anti-lookahead: only returns candles with timestamp < end (exclusive)
        so that the bar at 'end' is not included (it may still be forming).

        Args:
            symbol: e.g. "BTCUSDT"
            timeframe: e.g. "1H"
            start: ISO-8601 start time (inclusive)
            end: ISO-8601 end time (exclusive -- prevents lookahead)

        Returns:
            DataFrame with columns matching the candles table.
        """
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        with self._read_cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, open, high, low, close, volume,
                       trade_count, vwap
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                  AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC
                """,
                (symbol, timeframe, start, end),
            )
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "timestamp", "open", "high", "low", "close",
                    "volume", "trade_count", "vwap",
                ]
            )

        df = pd.DataFrame([dict(r) for r in rows])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df

    # ─── Trade Storage ──────────────────────────────────────

    def store_trade(self, trade: Dict[str, Any]) -> None:
        """
        Store a trade record. Required keys: trade_id, symbol, side,
        entry_time, entry_price, quantity.
        """
        required = {"trade_id", "symbol", "side", "entry_time", "entry_price", "quantity"}
        missing = required - set(trade.keys())
        if missing:
            raise StorageError(f"Trade dict missing required keys: {missing}")

        trade["entry_time"] = _validate_timestamp(
            str(trade["entry_time"]), "entry_time"
        )
        if trade.get("exit_time"):
            trade["exit_time"] = _validate_timestamp(
                str(trade["exit_time"]), "exit_time"
            )

        tags_json = json.dumps(trade.get("tags")) if trade.get("tags") else None

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO trades
                    (trade_id, symbol, side, entry_time, exit_time,
                     entry_price, exit_price, quantity, leverage,
                     stop_loss, take_profit, risk_pct, pnl, pnl_pct,
                     r_multiple, fees, slippage, status, strategy,
                     regime, signal_score, timeframe, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade["trade_id"],
                    trade["symbol"],
                    trade["side"],
                    trade["entry_time"],
                    trade.get("exit_time"),
                    float(trade["entry_price"]),
                    float(trade["exit_price"]) if trade.get("exit_price") else None,
                    float(trade["quantity"]),
                    float(trade.get("leverage", 1.0)),
                    float(trade["stop_loss"]) if trade.get("stop_loss") else None,
                    float(trade["take_profit"]) if trade.get("take_profit") else None,
                    float(trade["risk_pct"]) if trade.get("risk_pct") else None,
                    float(trade["pnl"]) if trade.get("pnl") is not None else None,
                    float(trade["pnl_pct"]) if trade.get("pnl_pct") is not None else None,
                    float(trade["r_multiple"]) if trade.get("r_multiple") is not None else None,
                    float(trade.get("fees", 0.0)),
                    float(trade.get("slippage", 0.0)),
                    trade.get("status", "OPEN"),
                    trade.get("strategy"),
                    trade.get("regime"),
                    int(trade["signal_score"]) if trade.get("signal_score") is not None else None,
                    trade.get("timeframe"),
                    tags_json,
                    trade.get("notes"),
                ),
            )

        logger.debug("Stored trade %s", trade["trade_id"])

    def get_trades(
        self,
        start: str,
        end: str,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve trades within a time range (by entry_time).

        Args:
            start: ISO-8601 start (inclusive)
            end: ISO-8601 end (exclusive)
            symbol: optional filter
            status: optional filter (OPEN, CLOSED, CANCELLED, PARTIAL)
        """
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        query = """
            SELECT * FROM trades
            WHERE entry_time >= ? AND entry_time < ?
        """
        params: list = [start, end]

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY entry_time ASC"

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("tags"):
                try:
                    d["tags"] = json.loads(d["tags"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    # ─── Signal Log Storage ─────────────────────────────────

    def store_signal_log(self, signal: Dict[str, Any]) -> None:
        """
        Store a signal computation record.
        Required keys: timestamp, symbol, timeframe, composite_score.
        """
        required = {"timestamp", "symbol", "timeframe", "composite_score"}
        missing = required - set(signal.keys())
        if missing:
            raise StorageError(
                f"Signal dict missing required keys: {missing}"
            )

        signal["timestamp"] = _validate_timestamp(
            str(signal["timestamp"]), "signal.timestamp"
        )

        components_json = (
            json.dumps(signal["components"])
            if signal.get("components")
            else None
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO signal_logs
                    (timestamp, symbol, timeframe, trend_score,
                     momentum_score, structure_score, flow_score,
                     macro_score, composite_score, direction,
                     regime, components, action_taken)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["timestamp"],
                    signal["symbol"],
                    signal["timeframe"],
                    signal.get("trend_score"),
                    signal.get("momentum_score"),
                    signal.get("structure_score"),
                    signal.get("flow_score"),
                    signal.get("macro_score"),
                    float(signal["composite_score"]),
                    signal.get("direction"),
                    signal.get("regime"),
                    components_json,
                    signal.get("action_taken"),
                ),
            )

        logger.debug(
            "Stored signal log: %s %s score=%s",
            signal["symbol"],
            signal["timestamp"],
            signal["composite_score"],
        )

    # ─── Regime Change Storage ──────────────────────────────

    def store_regime_change(self, regime: Dict[str, Any]) -> None:
        """
        Store a regime transition event.
        Required keys: timestamp, symbol, new_regime.
        """
        required = {"timestamp", "symbol", "new_regime"}
        missing = required - set(regime.keys())
        if missing:
            raise StorageError(
                f"Regime dict missing required keys: {missing}"
            )

        regime["timestamp"] = _validate_timestamp(
            str(regime["timestamp"]), "regime.timestamp"
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO regime_logs
                    (timestamp, symbol, previous_regime, new_regime,
                     trigger_reason, adx_value, atr_percentile,
                     vol_percentile, confirmation_bars)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    regime["timestamp"],
                    regime["symbol"],
                    regime.get("previous_regime"),
                    regime["new_regime"],
                    regime.get("trigger_reason"),
                    regime.get("adx_value"),
                    regime.get("atr_percentile"),
                    regime.get("vol_percentile"),
                    regime.get("confirmation_bars"),
                ),
            )

        logger.debug(
            "Stored regime change: %s -> %s at %s",
            regime.get("previous_regime"),
            regime["new_regime"],
            regime["timestamp"],
        )

    # ─── Portfolio Snapshot Storage ─────────────────────────

    def store_portfolio_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Store a portfolio state snapshot.
        Required keys: timestamp, total_equity, cash, peak_equity.
        """
        required = {"timestamp", "total_equity", "cash", "peak_equity"}
        missing = required - set(snapshot.keys())
        if missing:
            raise StorageError(
                f"Snapshot dict missing required keys: {missing}"
            )

        snapshot["timestamp"] = _validate_timestamp(
            str(snapshot["timestamp"]), "snapshot.timestamp"
        )

        positions_json = (
            json.dumps(snapshot["positions_json"])
            if snapshot.get("positions_json") and not isinstance(snapshot["positions_json"], str)
            else snapshot.get("positions_json")
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO portfolio_snapshots
                    (timestamp, total_equity, cash, unrealized_pnl,
                     realized_pnl, portfolio_heat, open_positions,
                     drawdown_pct, peak_equity, positions_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["timestamp"],
                    float(snapshot["total_equity"]),
                    float(snapshot["cash"]),
                    float(snapshot.get("unrealized_pnl", 0.0)),
                    float(snapshot.get("realized_pnl", 0.0)),
                    float(snapshot.get("portfolio_heat", 0.0)),
                    int(snapshot.get("open_positions", 0)),
                    float(snapshot.get("drawdown_pct", 0.0)),
                    float(snapshot["peak_equity"]),
                    positions_json,
                ),
            )

        logger.debug(
            "Stored portfolio snapshot: equity=%.2f at %s",
            snapshot["total_equity"],
            snapshot["timestamp"],
        )

    # ─── Risk Event Storage ─────────────────────────────────

    def store_risk_event(self, event: Dict[str, Any]) -> None:
        """
        Store a risk event (circuit breaker, warning, anomaly).
        Required keys: timestamp, event_type, severity, description.
        """
        required = {"timestamp", "event_type", "severity", "description"}
        missing = required - set(event.keys())
        if missing:
            raise StorageError(
                f"Risk event dict missing required keys: {missing}"
            )

        event["timestamp"] = _validate_timestamp(
            str(event["timestamp"]), "risk_event.timestamp"
        )

        metadata_json = (
            json.dumps(event["metadata"])
            if event.get("metadata") and not isinstance(event["metadata"], str)
            else event.get("metadata")
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO risk_events
                    (timestamp, event_type, severity, description,
                     current_value, threshold_value, action_taken,
                     metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["timestamp"],
                    event["event_type"],
                    event["severity"],
                    event["description"],
                    event.get("current_value"),
                    event.get("threshold_value"),
                    event.get("action_taken"),
                    metadata_json,
                ),
            )

        logger.info(
            "Risk event [%s/%s]: %s",
            event["severity"],
            event["event_type"],
            event["description"],
        )

    # ─── Equity Curve ───────────────────────────────────────

    def get_equity_curve(
        self,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        Retrieve the equity curve from portfolio snapshots.

        Returns a DataFrame with columns: timestamp, total_equity,
        drawdown_pct, portfolio_heat, open_positions, peak_equity.
        """
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        with self._read_cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, total_equity, drawdown_pct,
                       portfolio_heat, open_positions, peak_equity
                FROM portfolio_snapshots
                WHERE timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC
                """,
                (start, end),
            )
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "timestamp", "total_equity", "drawdown_pct",
                    "portfolio_heat", "open_positions", "peak_equity",
                ]
            )

        df = pd.DataFrame([dict(r) for r in rows])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    # ─── Performance Snapshot Storage ───────────────────────

    def store_performance_snapshot(self, metrics: Dict[str, Any]) -> None:
        """
        Store a performance metrics snapshot.
        Required keys: timestamp.
        """
        if "timestamp" not in metrics:
            raise StorageError(
                "Performance metrics dict missing required key: timestamp"
            )

        metrics["timestamp"] = _validate_timestamp(
            str(metrics["timestamp"]), "performance.timestamp"
        )

        metadata_json = (
            json.dumps(metrics["metadata"])
            if metrics.get("metadata") and not isinstance(metrics["metadata"], str)
            else metrics.get("metadata")
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO performance_snapshots
                    (timestamp, period, total_trades, winning_trades,
                     losing_trades, win_rate, avg_win, avg_loss,
                     profit_factor, sharpe_ratio, sortino_ratio,
                     calmar_ratio, max_drawdown, total_pnl,
                     avg_r_multiple, best_trade_pnl, worst_trade_pnl,
                     avg_hold_time_minutes, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?)
                """,
                (
                    metrics["timestamp"],
                    metrics.get("period", "daily"),
                    int(metrics.get("total_trades", 0)),
                    int(metrics.get("winning_trades", 0)),
                    int(metrics.get("losing_trades", 0)),
                    metrics.get("win_rate"),
                    metrics.get("avg_win"),
                    metrics.get("avg_loss"),
                    metrics.get("profit_factor"),
                    metrics.get("sharpe_ratio"),
                    metrics.get("sortino_ratio"),
                    metrics.get("calmar_ratio"),
                    metrics.get("max_drawdown"),
                    metrics.get("total_pnl"),
                    metrics.get("avg_r_multiple"),
                    metrics.get("best_trade_pnl"),
                    metrics.get("worst_trade_pnl"),
                    metrics.get("avg_hold_time_minutes"),
                    metadata_json,
                ),
            )

        logger.debug(
            "Stored performance snapshot at %s", metrics["timestamp"]
        )

    # ─── Query Helpers ──────────────────────────────────────

    def get_latest_regime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return the most recent regime for a symbol, or None."""
        with self._read_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM regime_logs
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (symbol,),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_open_trades(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all currently open trades, optionally filtered by symbol."""
        query = "SELECT * FROM trades WHERE status = 'OPEN'"
        params: list = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY entry_time ASC"

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("tags"):
                try:
                    d["tags"] = json.loads(d["tags"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_latest_portfolio_snapshot(self) -> Optional[Dict[str, Any]]:
        """Return the most recent portfolio snapshot, or None."""
        with self._read_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM portfolio_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("positions_json"):
            try:
                d["positions_json"] = json.loads(d["positions_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def get_risk_events(
        self,
        start: str,
        end: str,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve risk events within a time range with optional filters."""
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        query = """
            SELECT * FROM risk_events
            WHERE timestamp >= ? AND timestamp < ?
        """
        params: list = [start, end]

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY timestamp ASC"

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_signal_logs(
        self,
        symbol: str,
        start: str,
        end: str,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve signal logs for a symbol within a time range."""
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        query = """
            SELECT * FROM signal_logs
            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
        """
        params: list = [symbol, start, end]

        if min_score is not None:
            query += " AND composite_score >= ?"
            params.append(min_score)

        query += " ORDER BY timestamp ASC"

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("components"):
                try:
                    d["components"] = json.loads(d["components"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_performance_snapshots(
        self,
        start: str,
        end: str,
        period: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve performance snapshots within a time range."""
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        query = """
            SELECT * FROM performance_snapshots
            WHERE timestamp >= ? AND timestamp < ?
        """
        params: list = [start, end]

        if period:
            query += " AND period = ?"
            params.append(period)

        query += " ORDER BY timestamp ASC"

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def count_trades_in_period(
        self,
        start: str,
        end: str,
        symbol: Optional[str] = None,
    ) -> int:
        """Count closed trades in a period. Useful for validation checks."""
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        query = """
            SELECT COUNT(*) as cnt FROM trades
            WHERE status = 'CLOSED'
              AND entry_time >= ? AND entry_time < ?
        """
        params: list = [start, end]

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        with self._read_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return row["cnt"] if row else 0

    def get_daily_pnl(
        self,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        Compute daily P&L from closed trades.
        Returns DataFrame with columns: date, daily_pnl, trade_count.
        """
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")

        with self._read_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    DATE(exit_time) as date,
                    SUM(pnl) as daily_pnl,
                    COUNT(*) as trade_count
                FROM trades
                WHERE status = 'CLOSED'
                  AND exit_time >= ? AND exit_time < ?
                  AND pnl IS NOT NULL
                GROUP BY DATE(exit_time)
                ORDER BY date ASC
                """,
                (start, end),
            )
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(columns=["date", "daily_pnl", "trade_count"])

        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        return df


# ─── Module-level convenience ───────────────────────────────

def init_db(db_path: str = "data/lumare.db") -> Storage:
    """Create and initialize a Storage instance."""
    storage = Storage(db_path)
    storage.init_db()
    return storage
