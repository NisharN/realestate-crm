# UAE Real Estate CRM

A CRM built for Dubai/UAE brokers and small agencies, and the **system of record** for the
[realestateai](https://github.com/NisharN/realestateai) AI agent platform. The agent pulls leads from
here, writes scores/stages/qualification back, and books viewings and follow-ups through the same API.

```
backend/   FastAPI + SQLAlchemy (async) · SQLite for dev, PostgreSQL for prod · Alembic migrations
frontend/  Next.js 14 broker workspace (port 3100)
```

## What it does

| Area | Highlights |
| --- | --- |
| Leads | Pipeline (new → qualifying → qualified → handed off → viewing booked → offer → closed/lost), dedupe on `source+external_id` then phone/e-mail, AI score/band/summary fields, assignment, timeline |
| Listings | Sale & rent, Trakheesi permit + DLD number, owner details hidden from agents, "still available" verification + stale-inventory view |
| Viewings | requested → confirmed → done / no-show / cancelled, feedback |
| Follow-ups | call / WhatsApp / e-mail / voice-note / meeting, due queue, marks lead as contacted |
| Deals | offer → MOU → deposit → transfer → closed, commission calculation |
| Team | owner / manager / agent roles; agents only see their own leads |
| Integrations | Scoped API keys, changed-since sync, idempotent upserts, signed webhooks with retries |

Every record is scoped to an `agency_id`; the integration API derives the agency from the API key.

## Run locally

Backend (Python 3.10+):

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
CRM_DEMO_SEED=1 uvicorn app.main:app --port 8100 --reload
```

`CRM_DEMO_SEED=1` creates **Demo Realty LLC** with `owner@demo.ae` / `agent1@demo.ae` / `agent2@demo.ae`
(password `demo1234`), 40 listings, 60 leads, viewings, follow-ups, and a local-only API key
(`crm_live_demo-key-for-local-agent-platform-testing-0000`). Never enable the seed in production.

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_CRM_API=http://localhost:8100
npm run dev                  # http://localhost:3100
```

Docker (PostgreSQL + API + web):

```bash
echo "CRM_JWT_SECRET=$(openssl rand -hex 32)" > .env
docker compose up --build
```

## Tests & checks

```bash
cd backend && ruff check . && pytest -q          # 15 tests: auth, tenancy, scopes, sync, webhooks…
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Migrations

Development and tests create tables directly (`init_db`). Production (`CRM_ENVIRONMENT=production`)
skips that and expects `alembic upgrade head`, which the backend Docker image runs on start.

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic check   # fails if models drifted from migrations (also run in CI)
```

## Integration API (`/v1`)

Authenticate with `Authorization: Bearer crm_live_…` (create keys under Settings → API keys).

| Method | Path | Scope | Notes |
| --- | --- | --- | --- |
| GET | `/v1/me` | any | agency + key scopes |
| GET | `/v1/agents` | `agents:read` | |
| GET | `/v1/leads` | `leads:read` | `updated_after=<ISO>` or `cursor=` · `limit≤500` · ordered by `updated_at,id` · `{"data":[…],"paging":{"next":…}}` |
| GET | `/v1/leads/{id}` | `leads:read` | |
| POST | `/v1/leads` | `leads:write` | one lead or `{"leads":[…]}`; idempotent on `source+external_id`, merges into open leads by phone/e-mail |
| PATCH | `/v1/leads/{id}` | `leads:write` | write-back: `ai_score`, `ai_band`, `ai_summary`, `stage`, `assigned_agent_id`, requirement fields |
| POST | `/v1/leads/{id}/activities` | `leads:write` | timeline entries (`mark_contacted` optional) |
| GET | `/v1/listings` | `listings:read` | changed-since paging, owner fields never exposed |
| GET/POST/PATCH | `/v1/viewings` | `viewings:*` | POST is idempotent on `external_id` |
| POST | `/v1/followups` | `followups:write` | |

### Webhooks

Settings → Webhooks. Each delivery is a JSON POST signed with HMAC-SHA256 over the exact body:

```
X-Signature-256: sha256=<hex>
X-Event: lead.updated
X-Delivery-Id: <uuid>
```

Events: `lead.*`, `listing.*`, `viewing.*`, `followup.*`, `deal.*`. Failed deliveries retry with
backoff (`CRM_WEBHOOK_MAX_ATTEMPTS`, default 5). Private/loopback destinations are rejected unless
`CRM_ALLOW_PRIVATE_WEBHOOK_HOSTS=1` (local dev only).

## Configuration

All settings are `CRM_`-prefixed env vars (see `backend/app/config.py`): `DATABASE_URL`, `JWT_SECRET`
(required in production), `CORS_ORIGINS`, `WEBHOOK_TIMEOUT_S`, `WEBHOOK_MAX_ATTEMPTS`,
`WEBHOOK_INLINE_DELIVERY`, `DEMO_SEED`.

## Deployment

- **API** — Render web service (`render.yaml`, Docker, free Postgres; `alembic upgrade head` runs on boot):
  https://realestate-crm-api-3zyr.onrender.com (auto-deploys from `main`, `backend/` root).
  `postgres://` URLs from managed providers are normalised to `postgresql+asyncpg://` automatically.
- **Web** — Vercel project `realestate-crm` (root `frontend/`, `NEXT_PUBLIC_CRM_API` points at the API):
  https://realestate-crm-coral.vercel.app (auto-deploys from `main`).
- Add every web origin to `CRM_CORS_ORIGINS` on the API service.
