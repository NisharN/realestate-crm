"""Relational model. One agency = one tenant; every business row carries ``agency_id``.

Stage vocabulary is shared with the AI agent platform so sync is lossless:
new â†’ qualifying â†’ qualified â†’ handed_off â†’ viewing_booked â†’ offer â†’ closed | lost | opted_out
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, new_id, utcnow

PIPELINE_STAGES: tuple[str, ...] = ("new", "qualifying", "qualified", "handed_off", "viewing_booked", "offer", "closed", "lost", "opted_out")
CLOSED_STAGES = frozenset({"closed", "lost", "opted_out"})
PURPOSES = ("buy", "rent", "invest")
LISTING_TYPES = ("sale", "rent")
LISTING_STATUSES = ("draft", "live", "under_offer", "sold", "rented", "withdrawn")
VIEWING_STATUSES = ("requested", "confirmed", "done", "no_show", "cancelled")
FOLLOWUP_STATUSES = ("open", "done", "skipped")
DEAL_STATUSES = ("offer", "mou", "deposit", "transfer", "closed", "lost")
USER_ROLES = ("owner", "manager", "agent")
LEAD_SOURCES = ("property_finder", "bayut", "dubizzle", "meta_lead_ads", "whatsapp", "website", "referral", "walk_in", "ai_agent", "import", "other")


class Stamped:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)


class Agency(Stamped, Base):
    __tablename__ = "agencies"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    rera_orn: Mapped[str | None] = mapped_column(String(40))  # RERA Office Registration Number
    trade_license: Mapped[str | None] = mapped_column(String(60))
    emirate: Mapped[str] = mapped_column(String(40), default="Dubai")
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Dubai")


class User(Stamped, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("agency_id", "email", name="uq_user_agency_email"),)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)
    rera_brn: Mapped[str | None] = mapped_column(String(40))  # RERA Broker Registration Number
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    areas: Mapped[list[str]] = mapped_column(JSON, default=list)  # communities the agent specialises in
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(64), index=True)  # broker id on the AI platform


class ApiKey(Stamped, Base):
    __tablename__ = "api_keys"
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)  # leads:read leads:write listings:read viewings:write ...
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))


class Lead(Stamped, Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_agency_updated", "agency_id", "updated_at"),
        Index("ix_leads_agency_stage", "agency_id", "stage"),
        Index("ix_leads_agency_phone", "agency_id", "phone"),
        UniqueConstraint("agency_id", "source", "external_id", name="uq_lead_source_external"),
    )
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(32))  # E.164
    email: Mapped[str | None] = mapped_column(String(160))
    nationality: Mapped[str | None] = mapped_column(String(60))
    language: Mapped[str | None] = mapped_column(String(8))  # en / ar / ...
    source: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120))  # id on the originating system
    campaign: Mapped[str | None] = mapped_column(String(120))
    listing_reference: Mapped[str | None] = mapped_column(String(80))  # the listing they enquired on
    purpose: Mapped[str | None] = mapped_column(String(8))  # buy / rent / invest
    property_type: Mapped[str | None] = mapped_column(String(32))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget_min_aed: Mapped[float | None] = mapped_column(Float)
    budget_max_aed: Mapped[float | None] = mapped_column(Float)
    timeline: Mapped[str | None] = mapped_column(String(40))
    payment_method: Mapped[str | None] = mapped_column(String(16))  # cash / mortgage
    stage: Mapped[str] = mapped_column(String(24), default="new", nullable=False)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    lost_reason: Mapped[str | None] = mapped_column(String(160))
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    ai_score: Mapped[int | None] = mapped_column(Integer)  # 0-100 from the AI platform
    ai_band: Mapped[str | None] = mapped_column(String(8))  # hot / warm / cold
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_scored_at: Mapped[datetime | None] = mapped_column(DateTime)
    ai_broker_ref: Mapped[str | None] = mapped_column(String(64))  # assigned_broker on the AI platform
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_contact_channel: Mapped[str | None] = mapped_column(String(16))
    preferred_contact_window: Mapped[str | None] = mapped_column(String(80))
    whatsapp_call_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    custom: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    @property
    def name(self) -> str:
        return " ".join(x for x in (self.first_name, self.last_name) if x) or self.phone or self.email or "Unknown"

    @property
    def outreach_eligible(self) -> bool:
        return bool(self.consent_marketing and not self.do_not_contact)


class Listing(Stamped, Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("agency_id", "reference", name="uq_listing_reference"),)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    listing_type: Mapped[str] = mapped_column(String(8), default="sale", nullable=False)  # sale / rent
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    property_type: Mapped[str] = mapped_column(String(32), default="apartment", nullable=False)
    community: Mapped[str] = mapped_column(String(120), nullable=False)
    sub_community: Mapped[str | None] = mapped_column(String(120))
    building: Mapped[str | None] = mapped_column(String(160))
    emirate: Mapped[str] = mapped_column(String(40), default="Dubai")
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    size_sqft: Mapped[float | None] = mapped_column(Float)
    price_aed: Mapped[float] = mapped_column(Float, nullable=False)
    rent_frequency: Mapped[str | None] = mapped_column(String(8))  # yearly / monthly
    furnished: Mapped[str | None] = mapped_column(String(16))
    completion_status: Mapped[str] = mapped_column(String(16), default="ready")  # ready / off_plan
    handover_date: Mapped[str | None] = mapped_column(String(10))
    developer: Mapped[str | None] = mapped_column(String(120))
    permit_number: Mapped[str | None] = mapped_column(String(40))  # Trakheesi / DLD permit
    dld_number: Mapped[str | None] = mapped_column(String(40))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    amenities: Mapped[list[str]] = mapped_column(JSON, default=list)
    photos: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_name: Mapped[str | None] = mapped_column(String(120))
    owner_phone: Mapped[str | None] = mapped_column(String(32))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    portals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"property_finder": {"id": ..., "url": ...}}
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class Viewing(Stamped, Base):
    __tablename__ = "viewings"
    agency_id: Mapped[str] = mapped_colum×Î½öÚ$z{-®éÜj×["lead"]
    theirs = (await client.post("/api/leads", json={**lead_payload, "phone": "0509999999", "email": None, "external_id": "pf-other", "assigned_agent_id": tenant.user_id}, headers=tenant.h)).json()["lead"]
    ids = {l["id"] for l in (await client.get("/api/leads", headers=ah)).json()["items"]}
    assert mine["id"] in ids and theirs["id"] not in ids
    assert (await client.get(f"/api/leads/{theirs['id']}", headers=ah)).status_code == 404
    assert (await client.get("/api/settings/api-keys", headers=ah)).status_code == 403
    assert (await client.delete(f"/api/leads/{mine['id']}", headers=ah)).status_code == 403


# ---- leads --------------------------------------------------------------------
async def test_lead_upsert_idempotent_and_merge(client, tenant, lead_payload):
    key = await api_key(client, tenant)
    kh = {"Authorization": f"Bearer {key}"}
    r1 = await client.post("/v1/leads", json=lead_payload, headers=kh)
    assert r1.status_code == 201 and r1.json()["created"] is True
    lead = r1.json()["lead"]
    assert lead["phone"].startswith("+971")
    r2 = await client.post("/v1/leads", json={**lead_payload, "bedrooms": 3}, headers=kh)
    assert r2.json()["created"] is False and r2.json()["lead"]["id"] == lead["id"] and r2.json()["lead"]["bedrooms"] == 3
    # same phone from a different source merges instead of duplicating
    r3 = await client.post("/v1/leads", json={"phone": lead_payload["phone"], "source": "bayut", "external_id": "b-1"}, headers=kh)
    assert r3.json()["created"] is False and r3.json()["lead"]["id"] == lead["id"]
    batch = await client.post("/v1/leads", json={"leads": [lead_payload, {"phone": "0501112222", "source": "meta_ads", "external_id": "m-1"}]}, headers=kh)
    assert batch.json()["created"] == 1 and batch.json()["merged"] == 1
    detail = (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()
    kinds = [a["kind"] for a in detail["activities"]]
    assert "created" in kinds and kinds.count("merged") == 3


async def test_write_back_score_stage_assignment(client, tenant, lead_payload):
    key = await api_key(client, tenant, ["leads:read", "leads:write"])
    kh = {"Authorization": f"Bearer {key}"}
    await client.patch(f"/api/settings/team/{tenant.user_id}", json={"external_ref": "broker-7"}, headers=tenant.h)
    lead = (await client.post("/v1/leads", json=lead_payload, headers=kh)).json()["lead"]
    r = await client.patch(f"/v1/leads/{lead['id']}", json={"score": 82, "stage": "qualified", "assigned_broker": "broker-7", "timeline": "asap", "area_preference": "Dubai Marina", "summary": "Cash buyer"}, headers=kh)
    assert r.status_code == 200, r.text
    d = r.json()["lead"]
    assert d["ai_score"] == 82 and d["ai_band"] == "hot" and d["stage"] == "qualified" and d["assigned_agent_id"] == tenant.user_id and d["timeline"] == "asap"
    assert d["areas"] == ["Palm Jumeirah"]  # never overwrites human-entered preferences
    r = await client.patch(f"/v1/leads/{lead['id']}", json={"score": 20, "unknown_field": 1}, headers=kh)
    assert r.status_code == 422
    r = await client.patch(f"/v1/leads/{lead['id']}", json={"score": 20}, headers=kh)
    assert r.json()["lead"]["ai_band"] == "cold"
    detail = (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()
    assert [a["kind"] for a in detail["activities"]].count("ai_scored") == 2


async def test_api_key_scopes_and_revoke(client, tenant, lead_payload):
    key = await api_key(client, tenant, ["leads:read"])
    kh = {"Authorization": f"Bearer {key}"}
    assert (await client.get("/v1/leads", headers=kh)).status_code == 200
    assert (await client.post("/v1/leads", json=lead_payload, headers=kh)).status_code == 403
    assert (await client.get("/v1/listings", headers=kh)).status_code == 403
    keys = (await client.get("/api/settings/api-keys", headers=tenant.h)).json()["items"]
    assert all("key_hash" not in k and "plaintext" not in k for k in keys)
    kid = next(k["id"] for k in keys if k["scopes"] == ["leads:read"])
    assert (await client.delete(f"/api/settings/api-keys/{kid}", headers=tenant.h)).status_code == 204
    assert (await client.get("/v1/leads", headers=kh)).status_code == 401
    assert (await client.get("/v1/leads", headers={"X-API-Key": "crm_live_nope"})).status_code == 401


async def test_changed_since_paging(client, tenant):
    key = await api_key(client, tenant)
    kh = {"Authorization": f"Bearer {key}"}
    for i in range(7):
        await client.post("/v1/leads", json={"phone": f"05012345{i:02d}", "source": "website", "external_id": f"w-{i}"}, headers=kh)
    seen, cursor = [], None
    for _ in range(10):
        r = await client.get("/v1/leads", params={"limit": 3, **({"cursor": cursor} if cursor else {})}, headers=kh)
        page = r.json()
        seen += [x["id"] for x in page["data"]]
        cursor = page["paging"]["next"]
        if not cursor:
            break
    assert len(seen) == 7 and len(set(seen)) == 7
    stamps = [x["updated_at"] for x in (await client.get("/v1/leads", headers=kh)).json()["data"]]
    assert stamps == sorted(stamps)
    # updated_after (generic connector style) excludes older rows
    r = await client.get("/v1/leads", params={"updated_after": stamps[3]}, headers=kh)
    assert len(r.json()["data"]) == sum(1 for s in stamps if s > stamps[3])
    # a write-back bumps updated_at so the next incremental pull picks it up
    await asyncio.sleep(0.002)
    await client.patch(f"/v1/leads/{seen[0]}", json={"score": 55}, headers=kh)
    r = await client.get("/v1/leads", params={"updated_after": stamps[-1]}, headers=kh)
    assert [x["id"] for x in r.json()["data"]] == [seen[0]]
    assert (await client.get("/v1/leads", params={"cursor": "garbage"}, headers=kh)).status_code == 422


# ---- listings / viewings / follow-ups / deals ----------------------------------------
async def test_listing_lifecycle_and_privacy(client, tenant):
    r = await client.post("/api/listings", json={"reference": "DR-1", "title": "2BR Marina", "community": "Dubai Marina", "price_aed": 2_000_000, "status": "live", "permit_number": "7112233", "owner_phone": "0501234567", "owner_name": "Owner"}, headers=tenant.h)
    assert r.status_code == 201
    lid = r.json()["listing"]["id"]
    assert (await client.post("/api/listings", json={"reference": "DR-1", "title": "dup", "community": "Marina", "price_aed": 1}, headers=tenant.h)).status_code == 409
    key = await api_key(client, tenant)
    pub = (await client.get("/v1/listings", headers={"Authorization": f"Bearer {key}"})).json()["data"]
    assert pub[0]["permit_number"] == "7112233" and "owner_phone" not in pub[0]
    stale = (await client.get("/api/listings/stale", params={"days": 14}, headers=tenant.h)).json()["items"]
    assert lid in {x["id"] for x in stale}
    await client.post(f"/api/listings/{lid}/verify", headers=tenant.h)
    assert lid not in {x["id"] for x in (await client.get("/api/listings/stale", headers=tenant.h)).json()["items"]}
    r = await client.patch(f"/api/listings/{lid}", json={"status": "under_offer"}, headers=tenant.h)
    assert r.json()["changed"] == ["status"]


async def test_viewing_followup_deal_flow(client, tenant, lead_payload):
    lead = (await client.post("/api/leads", json=lead_payload, headers=tenant.h)).json()["lead"]
    listing = (await client.post("/api/listings", json={"reference": "V-1", "title": "Villa", "community": "Arabian Ranches", "price_aed": 5_000_000}, headers=tenant.h)).json()["listing"]
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    v = await client.post("/api/viewings", json={"lead_id": lead["id"], "listing_id": listing["id"], "scheduled_at": when}, headers=tenant.h)
    assert v.status_code == 201
    assert (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()["lead"]["stage"] == "viewing_booked"
    vid = v.json()["viewing"]["id"]
    assert (await client.patch(f"/api/viewings/{vid}", json={"status": "confirmed"}, headers=tenant.h)).json()["viewing"]["status"] == "confirmed"
    assert (await client.patch(f"/api/viewings/{vid}", json={"status": "done", "feedback": "loved it"}, headers=tenant.h)).status_code == 200
    await client.patch(f"/api/leads/{lead['id']}", json={"consent_marketing": True}, headers=tenant.h)
    f = await client.post("/api/followups", json={"lead_id": lead["id"], "due_at": when, "title": "Call back", "channel": "whatsapp"}, headers=tenant.h)
    assert f.status_code == 201
    assert (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()["lead"]["next_follow_up_at"] is not None
    fid = f.json()["followup"]["id"]
    assert (await client.patch(f"/api/followups/{fid}", json={"status": "done"}, headers=tenant.h)).json()["followup"]["status"] == "done"
    lead_after = (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()["lead"]
    assert lead_after["next_follow_up_at"] is None and lead_after["last_contacted_at"] is not None
    d = await client.post("/api/deals", json={"lead_id": lead["id"], "listing_id": listing["id"], "offer_aed": 4_800_000, "commission_pct": 2}, headers=tenant.h)
    assert d.status_code == 201 and d.json()["deal"]["commission_aed"] == 96_000
    assert (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()["lead"]["stage"] == "offer"
    did = d.json()["deal"]["id"]
    await client.patch(f"/api/deals/{did}", json={"status": "closed", "agreed_aed": 4_900_000}, headers=tenant.h)
    assert (await client.get(f"/api/leads/{lead['id']}", headers=tenant.h)).json()["lead"]["stage"] == "closed"
    today = (await client.get("/api/leads/today", headers=tenant.h)).json()
    assert {"followups", "viewings", "hot_leads", "stale_leads"} <= set(today)
    dash = (await client.get("/api/dashboard", headers=tenant.h)).json()
    assert dash["closed_30d"] >= 1


async def test_v1_viewing_idempotent_on_external_id(client, tenant, lead_payload):
    key = await api_key(client, tenant)
    kh = {"Authorization": f"Bearer {key}"}
    lead = (await client.post("/v1/leads", json=lead_payload, headers=kh)).json()["lead"]
    body = {"lead_id": lead["id"], "external_id": "agent-viewing-1", "status": "requested", "source": "ai_agent"}
    a = await client.post("/v1/viewings", json=body, headers=kh)
    b = await client.post("/v1/viewings", json=body, headers=kh)
    assert a.json()["created"] is True and b.json()["created"] is False and a.json()["viewing"]["id"] == b.json()["viewing"]["id"]
    act = await client.post(f"/v1/leads/{lead['id']}/activities", json={"kind": "whatsapp", "summary": "Sent brochure"}, headers=kh)
    assert act.status_code == 201
    assert (await client.get(f"/v1/leads/{lead['id']}", headers=kh)).json()["lead"]["last_contacted_at"] is not None


# ---- webhooks --------------------------------------------------------------------
async def test_webhook_signed_delivery_and_secret_handling(client, tenant, lead_payload, monkeypatch):
    received: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    r = await client.post("/api/settings/webhooks", json={"name": "agent", "url": "http://127.0.0.1:9/hook", "events": ["lead.*"]}, headers=tenant.h)
    assert r.status_code == 201, r.text
    secret = r.json()["webhook"]["secret"]
    wid = r.json()["webhook"]["id"]
    listed = (await client.get("/api/settings/webhooks", headers=tenant.h)).json()["items"]
    assert all("secret" not in w for w in listed)
    assert (await client.get(f"/api/settings/webhooks/{wid}/secret", headers=tenant.h)).json()["secret"] == secret
    assert (await client.post("/api/settings/webhooks", json={"name": "bad", "url": "ftp://x", "events": ["*"]}, headers=tenant.h)).status_code == 422
    assert (await client.post("/api/settings/webhooks", json={"name": "bad", "url": "https://x.example", "events": ["nope"]}, headers=tenant.h)).status_code == 422
    # receiver-supplied secret (the agent platform generates one per inbound connection)
    supplied = (await client.post("/api/settings/webhooks", json={"name": "agent2", "url": "https://x.example/hook", "events": ["*"], "secret": "receiver-secret-0123456789"}, headers=tenant.h)).json()["webhook"]
    assert supplied["secret"] == "receiver-secret-0123456789"
    assert (await client.post("/api/settings/webhooks", json={"name": "short", "url": "https://x.example/h", "secret": "tooshort"}, headers=tenant.h)).status_code == 422

    lead = (await client.post("/api/leads", json=lead_payload, headers=tenant.h)).json()["lead"]
    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await webhooks.deliver_pending(client=mock)
    assert out["sent"] >= 1
    req = next(x for x in received if x.headers["X-Event"] == "lead.created")
    body = req.content
    assert json.loads(body)["lead"]["id"] == lead["id"]
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert req.headers["X-Signature-256"] == expected == sign(secret, body)
    deliveries = (await client.get(f"/api/settings/webhooks/{wid}/deliveries", headers=tenant.h)).json()["items"]
    assert deliveries and deliveries[0]["status"] == "delivered" and "secret" not in json.dumps(deliveries)
    # listing events are not subscribed
    await client.post("/api/listings", json={"reference": "W-1", "title": "t", "community": "c", "price_aed": 1}, headers=tenant.h)
    n = len(received)
    await webhooks.deliver_pending(client=mock)
    assert len(received) == n


async def test_webhook_retry_then_fail(client, tenant, lead_payload):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    await client.post("/api/settings/webhooks", json={"name": "flaky", "url": "http://127.0.0.1:9/flaky", "events": ["lead.created"]}, headers=tenant.h)
    await client.post("/api/leads", json=lead_payload, headers=tenant.h)
    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await webhooks.deliver_pending(client=mock)
    assert out["sent"] == 0 and out["pending"] >= 1 and calls >= 1
    hooks = (await client.get("/api/settings/webhooks", headers=tenant.h)).json()["items"]
    flaky = next(w for w in hooks if w["name"] == "flaky")
    assert flaky["failure_count"] >= 1 and flaky["last_status"] == 500


async def test_public_webhook_url_validation_blocks_private(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "allow_private_webhook_hosts", False)
    with pytest.raises(ValueError):
        webhooks.validate_webhook_url("https://127.0.0.1/x")
    with pytest.raises(ValueError):
        webhooks.validate_webhook_url("http://example.com/x")


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_owner_cannot_be_demoted_when_last(client, tenant):
    assert (await client.patch(f"/api/settings/team/{tenant.user_id}", json={"role": "agent"}, headers=tenant.h)).status_code == 409
    second = await register(client)
    assert (await client.patch(f"/api/settings/team/{second.user_id}", json={"role": "agent"}, headers=tenant.h)).status_code == 404


def test_api_key_prefix_fits_column():
    from app.models import ApiKey
    from app.security import generate_api_key

    _, prefix, _ = generate_api_key()
    assert len(prefix) <= ApiKey.__table__.c.prefix.type.length
