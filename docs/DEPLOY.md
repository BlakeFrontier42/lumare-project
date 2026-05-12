# Cloud Deployment Guide

Three platforms cover the spectrum, easiest first:

| Platform | Cost (hobby) | Setup time | Auto-deploy | Postgres included |
|---|---|---|---|---|
| **Fly.io** | Free tier covers small bot | 15 min | yes (git push) | $1.94/mo |
| **Railway** | $5/mo credit | 5 min | yes (git push) | $5/mo |
| **Render** | Free with sleep, $7/mo always-on | 10 min | yes (git push) | $7/mo |

Pick **Railway** if you want the fastest "click and ship" experience. Pick **Fly.io** if you want global region selection and lower cost at scale. Pick **Render** if you want explicit infrastructure-as-code via `render.yaml`.

---

## Railway (fastest path)

1. Push your fork to GitHub (already done if you've been committing along).
2. Visit https://railway.app → New Project → Deploy from GitHub repo → pick `lumare-project`.
3. Railway auto-detects Python and Node, builds both services.
4. **Backend service** — set these env vars in the Railway UI:
   ```
   DATABASE_URL=<auto-provided when you add Postgres>
   LUMARE_ALLOW_LIVE=0                  # flip to 1 only after validation
   LUMARE_JWT_SECRET=<long random>      # if you want multi-tenant
   COINBASE_API_KEY=<optional>
   COINBASE_API_SECRET=<optional>
   ALPACA_API_KEY=<optional>
   ALPACA_API_SECRET=<optional>
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   POLYGON_API_KEY=<optional>
   FRED_API_KEY=<optional>
   ```
5. **Frontend service** — set:
   ```
   NEXT_PUBLIC_API_URL=https://<your-backend>.railway.app
   ```
6. Add Postgres → Database → Provision → wait 30s → `DATABASE_URL` is auto-injected into the backend service.
7. Run the migration:
   ```bash
   railway run python -c "from backend.data.storage import Storage; from backend.config.settings import SETTINGS; Storage(SETTINGS.db_path).init_db()"
   ```
8. Open the frontend URL Railway gives you. The bot page should load.

---

## Fly.io (cheapest at scale)

```bash
# 1. Install flyctl
brew install flyctl  # or curl -L https://fly.io/install.sh | sh

# 2. Auth
fly auth login

# 3. Create the app
cd lumare-project
fly launch --no-deploy --name lumare-bot --region iad
# (says yes to Postgres when prompted)
```

Add a minimal `fly.toml`:

```toml
app = "lumare-bot"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  LUMARE_ALLOW_LIVE = "0"
  ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

[[services]]
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    handlers = ["http"]
    port = 80

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443

[[mounts]]
  source = "lumare_data"
  destination = "/data"
```

Backend `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY data ./data
EXPOSE 8000
CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

> **`--workers 1` is intentional.** The autobot is currently a singleton with an in-memory asyncio task. With 2 workers you get 2 bots fighting over the same DB. Either keep workers=1 OR migrate to multi-tenant + Postgres + a job-queue worker (Phase 8).

Deploy:
```bash
fly secrets set LUMARE_JWT_SECRET="$(openssl rand -hex 32)"
fly secrets set COINBASE_API_KEY=... COINBASE_API_SECRET=...
fly secrets set ALPACA_API_KEY=... ALPACA_API_SECRET=...
fly secrets set POLYGON_API_KEY=...
fly deploy
```

Frontend separately — easiest is Vercel:
```bash
cd frontend && vercel
# Add NEXT_PUBLIC_API_URL=https://lumare-bot.fly.dev in Vercel env
```

---

## Render (infrastructure-as-code)

Add `render.yaml` at repo root:

```yaml
databases:
  - name: lumare-db
    plan: starter
    databaseName: lumare
    user: lumare

services:
  - type: web
    name: lumare-backend
    runtime: python
    plan: starter
    region: oregon
    rootDir: .
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn backend.api.app:app --host 0.0.0.0 --port $PORT --workers 1
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: lumare-db
          property: connectionString
      - key: LUMARE_ALLOW_LIVE
        value: "0"
      - key: ALPACA_BASE_URL
        value: https://paper-api.alpaca.markets
      - key: PYTHON_VERSION
        value: 3.11.9

  - type: web
    name: lumare-frontend
    runtime: node
    rootDir: frontend
    buildCommand: npm install && npm run build
    startCommand: npm run start
    envVars:
      - key: NEXT_PUBLIC_API_URL
        fromService:
          name: lumare-backend
          type: web
          property: host
```

Push, Render auto-detects, click "Apply" in the dashboard. Done.

---

## Production hardening checklist

Before flipping `LUMARE_ALLOW_LIVE=1`:

- [ ] Walk-forward results show PF ≥ 1.3 with PF.min ≥ 0.9 across 6+ folds. Current 30d run is below this bar — wait for more data.
- [ ] `DATABASE_URL` points to Postgres, not SQLite, in prod.
- [ ] `LUMARE_JWT_SECRET` is set to a long random value.
- [ ] CORS is locked down — current `app.py` allows `*` for dev. Restrict to your frontend's hostname:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://yourapp.com"],
      allow_credentials=True,
      allow_methods=["GET", "POST", "DELETE"],
      allow_headers=["*"],
  )
  ```
- [ ] Rate-limit `/api/bot/start` and `/api/bot/positions/{symbol}/close` (slowapi or your reverse proxy).
- [ ] Set up Sentry or another error tracker — paste `SENTRY_DSN=...` and add `sentry_sdk.init` near the top of `backend/api/app.py`.
- [ ] Set up a cron / scheduler to periodically VACUUM Postgres (Railway/Render do this automatically).
- [ ] **Capital limits in env** — `MAX_POSITION_USD`, `MAX_DAILY_LOSS_USD`. The bot reads them and refuses orders that would breach.

---

## Cost ballpark (May 2026)

For 1 user, 1 bot, paper trading, polling 5 symbols every 15s:

| Component | Railway | Fly.io | Render |
|---|---|---|---|
| Backend container | $5-7/mo | $0-3/mo | $7/mo |
| Postgres | $5/mo | $1.94/mo | $7/mo |
| Frontend | $5/mo | $0 (Vercel free) | $7/mo |
| **Total** | **$15-17/mo** | **$2-5/mo** | **$21/mo** |

Live trading cost is the same. Real money risk is on you, not the cloud bill.

---

## Logs + observability

All three platforms surface `stdout` logs in their dashboard. The bot logs structured loguru output — searchable on the platform side.

For real telemetry, add Datadog or Logtail. Backend already uses `loguru` so adding a sink is one line:

```python
from loguru import logger
logger.add("https://in.logtail.com/...", level="INFO")
```
