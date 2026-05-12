# Postgres Migration Guide

SQLite is fine for single-machine development. For cloud deployment / multi-instance / >10k trades/day, swap to Postgres. The storage layer is intentionally narrow (one `Storage` class with explicit methods) so the swap is mechanical.

## When to migrate

| Signal | SQLite OK | Migrate |
|---|---|---|
| Trades/day | < 10,000 | > 10,000 |
| Concurrent writers | 1 process | > 1 process |
| DB size | < 1 GB | > 1 GB |
| Deployment | single VM | Fly.io / Railway / Render / K8s |
| Backup needs | file snapshot OK | PITR required |

## What changes

Only `backend/data/storage.py` needs to swap drivers. Every other module talks to it through methods (`store_trade`, `store_signal_log`, `get_trades`, `get_candles`, etc.) — no SQL strings outside that file.

## Step-by-step

### 1. Provision Postgres

**Local dev** — `docker run -d --name lumare-pg -e POSTGRES_PASSWORD=lumare -p 5432:5432 postgres:16`

**Hosted** — Supabase, Neon, Railway, Fly Postgres, or AWS RDS. Any standard Postgres 14+ works.

### 2. Install the driver

```bash
pip install psycopg[binary]
```

Add to `backend/requirements.txt`:
```
psycopg[binary]>=3.2
```

### 3. Translate the schema

Open `backend/data/storage.py`. Each `CREATE TABLE IF NOT EXISTS …` block at the top of the file needs three small changes:

| SQLite | Postgres |
|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` |
| `REAL` | `DOUBLE PRECISION` |
| `TEXT` | `TEXT` (no change) |
| `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` | `to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')` |

Save the result as `backend/data/storage_pg.py` so you can fall back if needed.

### 4. Swap the connection layer

In `storage_pg.py`, replace the `_get_connection` block:

```python
import psycopg
from psycopg.rows import dict_row

def _get_connection(self) -> psycopg.Connection:
    if not hasattr(self._local, "conn") or self._local.conn is None:
        self._local.conn = psycopg.connect(
            self._db_path,            # repurpose to a DSN
            row_factory=dict_row,
            autocommit=False,
        )
    return self._local.conn
```

`self._db_path` becomes a DSN string like `postgresql://user:pass@host:5432/lumare`. Plumb it via env:

```python
# backend/config/settings.py
db_path: str = os.getenv(
    "DATABASE_URL", "data/lumare.db"
)
```

Anything starting with `postgresql://` or `postgres://` routes to Postgres; the SQLite path is the default fallback. Pick the right Storage class at import time:

```python
# backend/data/__init__.py
from backend.config.settings import SETTINGS
if SETTINGS.db_path.startswith(("postgres://", "postgresql://")):
    from .storage_pg import Storage  # noqa: F401
else:
    from .storage import Storage  # noqa: F401
```

### 5. Translate parameter placeholders

SQLite uses `?`, Postgres uses `%s`. Either:
- Find/replace `?` with `%s` in `storage_pg.py`, or
- Wrap with a tiny helper:
  ```python
  def _q(sql: str) -> str:
      return sql.replace("?", "%s")
  ```
  And use `cursor.execute(_q(sql), params)`.

### 6. Translate INSERT OR REPLACE

SQLite's `INSERT OR REPLACE INTO trades …` becomes Postgres `INSERT … ON CONFLICT (trade_id) DO UPDATE SET …`. Example:

```sql
INSERT INTO trades (trade_id, symbol, side, …)
VALUES (%s, %s, %s, …)
ON CONFLICT (trade_id) DO UPDATE
  SET status = EXCLUDED.status,
      exit_time = EXCLUDED.exit_time,
      exit_price = EXCLUDED.exit_price,
      pnl = EXCLUDED.pnl;
```

The only tables affected are `trades`, `candles`, `signal_logs`, `regime_logs`, `portfolio_snapshots`, and `performance_snapshots` — all six follow the same pattern.

### 7. Bulk-import existing data

```bash
# 1. Dump SQLite to CSV
sqlite3 data/lumare.db <<EOF
.mode csv
.headers on
.output trades.csv
SELECT * FROM trades;
.output candles.csv
SELECT * FROM candles;
EOF

# 2. Load into Postgres
psql "$DATABASE_URL" -c "\copy trades FROM 'trades.csv' WITH CSV HEADER"
psql "$DATABASE_URL" -c "\copy candles FROM 'candles.csv' WITH CSV HEADER"
```

### 8. Verify

```bash
DATABASE_URL=postgresql://… python -c "
from backend.data.storage import Storage
from backend.config.settings import SETTINGS
s = Storage(SETTINGS.db_path)
s.init_db()
rows = s.get_trades('2026-01-01', '2026-12-31')
print(f'{len(rows)} trades in Postgres')
"
```

If that count matches your SQLite trades count, you're migrated. Run the full smoke test (`start-lumare.bat` → start bot → verify positions open → close → see trade in history) against the Postgres DSN to confirm.

## Connection pooling

Add `psycopg_pool` for multi-process deployments:

```python
from psycopg_pool import ConnectionPool
pool = ConnectionPool(self._db_path, min_size=1, max_size=10)

def _get_connection(self):
    return pool.connection()
```

## Indexes worth adding immediately

```sql
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_ts ON candles(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_signal_logs_symbol_ts ON signal_logs(symbol, timestamp);
```

The replay engine and bot status queries hit `entry_time` and `(symbol, timeframe, timestamp)` heaviest. These five indexes make a 10M-row table feel like 100k.

## Rollback

Keep `storage.py` (SQLite) in the repo. Setting `DATABASE_URL=data/lumare.db` reverts to SQLite mode in one env var change. No code changes needed.
