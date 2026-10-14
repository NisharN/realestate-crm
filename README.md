# PropX CRM

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
| Leads | Pipeline (new → qualifying → qualified → handed off → viewing booked → offer → closed/lost), dedupe on `source+external_id` then phone/e-mail, explainable 0–100 priority score, assignment, timeline |
| Listings | Sale & rent, Trakheesi permit + DLD number, owner details hidden from agents, portal/CRM imports, lead-to-listing suggestions, availability verification |
| Viewings | requested → confirmed → done / no-show / cancelled, feedback |
| Follow-ups | call / WhatsApp / WhatsApp call / e-mail / voice-note / meeting tasks, due queue, human completion and CRM write-back |
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
cd backend && ruff check . && pytest -q          # auth, tenancy, scopes, sync, webhooks…
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
| POST | `/v1/listings` | `listings:write` | one normalized listing or `{"listings":[…]}`; pass `source` (`property_finder`, `bayut`, `dubizzle`, etc.) and vendor `external_id` for idempotent upsert |
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

## Syncing leads from the AI platform

1. CRM → **Settings → API keys → Create** (copy the `crm_live_…` key; shown once).
2. Platform → **Operations → Connections → Standalone CRM**: base URL `https://realestate-crm-api-3zyr.onrender.com`, API key from step 1 → **Test** (calls `GET /v1/me`).
3. Platform → **Operations → Routines**: create `Select leads → Qualify (Jev) → Push leads to CRM` (or the "Portal leads → qualify → CRM" template) and **Run now**.
   Leads land via `POST /v1/leads` (idempotent on `external_id`) and scores/bands/summary via `PATCH /v1/leads/{id}`; re-runs update rather than duplicate.

## Priority, matching, and handoff workflow

New leads are scored locally and receive a score history snapshot with factors and the trigger. The 100-point model is deterministic and transparent: contactability (15), intent (10), timeline (15), budget (10), preferred area (10), property requirements (5), suitable live inventory (20), recent contact/viewing activity (10), and pipeline progress (5). Bands are hot (70+), warm (40–69), and cold (0–39). Marketing consent and Do Not Contact are kept separate from business priority.

The qualification action recalculates the score and requires a contact method, purpose, budget, preferred area, and a score of at least 60. Property suggestions rank live listings by purpose, property type, bedrooms, area, and budget fit. The lead screen shows the matching factors and can start a viewing request from a suggestion.

Use `GET /api/leads/{id}/scores`, `POST /api/leads/{id}/score`, and `GET /api/leads/{id}/recommendations` for the local workflow. `POST /api/leads/{id}/handoff` assigns the lead to an active agency agent and records the handoff note. Completed follow-ups, contacts, viewings, stage changes, and deals are added to the activity history and cause a score refresh.

Follow-ups are agent-owned reminders. This release does not send WhatsApp, e-mail, or voice calls automatically. WhatsApp messages and voice notes require marketing consent; WhatsApp-call tasks also require separate call permission. The UI hides contact links when consent is missing or Do Not Contact is enabled. A configured messaging/voice provider and agency credentials are required before outbound delivery can be enabled.

Portal data arrives through normalized, idempotent CRM imports. Property Finder’s [Enterprise API](https://support.propertyfinder.ae/hc/en-us/articles/28266806720914-How-to-integrate-your-CRM-with-PF-Expert-2-0-using-the-Enterprise-API) provides lead and listing access after the agency enables credentials. Bayut’s [Leads API](https://support.bayut.com/hc/en-us/articles/16703746688786-What-is-the-Leads-API) delivers leads into an agency CRM, and Bayut/dubizzle bulk property sync uses an [XML integration](https://support.bayut.com/hc/en-us/articles/18984946157714-Our-listings-are-posted-through-our-own-CRM-What-are-the-guidelines-for-posting-an-Off-plan-listing). This repo includes a normalized intake API but does not yet poll provider APIs, store provider credentials, or convert each provider’s native payload/feed format; those require the agency’s provider access and exact account documentation.

Example normalized listing import (a batch uses `{"listings":[…]}` with the same shape):

```json
{
  "source": "bayut",
  "external_id": "vendor-listing-123",
  "reference": "BAY-123",
  "title": "Two-bedroom apartment",
  "listing_type": "sale",
  "status": "live",
  "property_type": "apartment",
  "community": "Dubai Marina",
  "bedrooms": 2,
  "price_aed": 2400000
}
```
