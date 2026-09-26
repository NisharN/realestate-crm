from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.security import sign
from app.services import webhooks
from tests.conftest import api_key, register

pytestmark = pytest.mark.asyncio


# ---- auth & tenancy ---------------------------------------------------------------
async def test_register_login_me(client, tenant):
    r = await client.post("/api/auth/login", json={"email": tenant.email, "password": "password123"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "owner"
    assert "password_hash" not in json.dumps(r.json())
    r = await client.get("/api/auth/me", headers=tenant.h)
    assert r.json()["agency"]["id"] == tenant.agency_id
    r = await client.post("/api/auth/login", json={"email": tenant.email, "password": "wrong"})
    assert r.status_code == 401
    assert (await client.get("/api/leads")).status_code == 401


async def test_tenant_isolation(client, tenant, other, lead_payload):
    r = await client.post("/api/leads", json=lead_payload, headers=tenant.h)
    lead_id = r.json()["lead"]["id"]
    assert (await client.get(f"/api/leads/{lead_id}", headers=other.h)).status_code == 404
    assert (await client.patch(f"/api/leads/{lead_id}", json={"notes": "x"}, headers=other.h)).status_code == 404
    listing = await client.post("/api/listings", json={"reference": "X-1", "title": "Marina apt", "community": "Dubai Marina", "price_aed": 1_500_000}, headers=tenant.h)
    assert (await client.get(f"/api/listings/{listing.json()['listing']['id']}", headers=other.h)).status_code == 404
    other_key = await api_key(client, other)
    r = await client.get("/v1/leads", headers={"Authorization": f"Bearer {other_key}"})
    assert r.status_code == 200 and r.json()["data"] == []
    assert (await client.patch(f"/v1/leads/{lead_id}", json={"score": 90}, headers={"Authorization": f"Bearer {other_key}"})).status_code == 404


async def test_agent_scope(client, tenant, lead_payload):
    r = await client.post("/api/settings/team", json={"email": f"agent-{tenant.agency_id[:6]}@example.com", "full_name": "Agent A", "role": "agent", "password": "password123"}, headers=tenant.h)
    assert r.status_code == 201
    agent_id = r.json()["user"]["id"]
    login = await client.post("/api/auth/login", json={"email": f"agent-{tenant.agency_id[:6]}@example.com", "password": "password123"})
    ah = {"Authorization": f"Bearer {login.json()['token']}"}
    mine = (await client.post("/api/leads", json={**lead_payload, "assigned_agent_id": agent_id}, headers=tenant.h)).json()["lead"]
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
