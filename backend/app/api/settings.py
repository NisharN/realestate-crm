from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.db import utcnow
from app.deps import Principal, SessionDep, current_user, manager_user
from app.models import ApiKey, User, Webhook, WebhookDelivery
from app.schemas import ApiKeyIn, UserIn, UserPatch, WebhookIn, WebhookPatch
from app.security import generate_api_key, generate_webhook_secret, hash_password
from app.services.webhooks import deliver_pending, validate_webhook_url

router = APIRouter(prefix="/settings", tags=["settings"])

KNOWN_SCOPES = ("leads:read", "leads:write", "listings:read", "listings:write", "viewings:read", "viewings:write", "followups:read", "followups:write", "agents:read", "*")
KNOWN_EVENTS = ("*", "lead.*", "lead.created", "lead.updated", "lead.contacted", "lead.deleted", "listing.*", "listing.created", "listing.updated", "listing.deleted", "viewing.*", "viewing.created", "viewing.updated", "followup.*", "followup.created", "followup.updated", "deal.*", "deal.created", "deal.updated")


# ---- team --------------------------------------------------------------------
@router.get("/team")
async def team(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    rows = (await session.execute(select(User).where(User.agency_id == principal.agency_id).order_by(User.created_at))).scalars().all()
    return {"items": [serializers.user(u) for u in rows]}


@router.post("/team", status_code=201)
async def add_member(body: UserIn, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    if body.role == "owner" and principal.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an owner can add owners")
    taken = (await session.execute(select(User.id).where(func.lower(User.email) == body.email.lower()))).scalar_one_or_none()
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "e-mail already in use")
    data = body.model_dump()
    data["email"] = data["email"].lower()
    password = data.pop("password")
    row = User(agency_id=principal.agency_id, password_hash=hash_password(password), **data)
    session.add(row)
    await session.commit()
    return {"user": serializers.user(row)}


@router.patch("/team/{user_id}")
async def patch_member(user_id: str, body: UserPatch, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(User, user_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    data = body.model_dump(exclude_unset=True)
    if not principal.is_manager:
        if row.id != principal.id or any(k in data for k in ("role", "active", "external_ref")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "agents can only edit their own profile")
    if data.get("role") == "owner" and principal.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an owner can promote to owner")
    if row.role == "owner" and (data.get("active") is False or (data.get("role") and data["role"] != "owner")):
        owners = (await session.execute(select(func.count()).select_from(User).where(User.agency_id == principal.agency_id, User.role == "owner", User.active.is_(True)))).scalar_one()
        if owners <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "an agency needs at least one active owner")
    if "password" in data:
        row.password_hash = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(row, k, v)
    await session.commit()
    return {"user": serializers.user(row)}


# ---- api keys -----------------------------------------------------------------
@router.get("/api-keys")
async def api_keys(principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    rows = (await session.execute(select(ApiKey).where(ApiKey.agency_id == principal.agency_id).order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"items": [serializers.api_key(k) for k in rows], "scopes": list(KNOWN_SCOPES)}


@router.post("/api-keys", status_code=201)
async def create_api_key(body: ApiKeyIn, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    bad = [s for s in body.scopes if s not in KNOWN_SCOPES]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown scopes: {', '.join(bad)}")
    plaintext, prefix, digest = generate_api_key()
    row = ApiKey(agency_id=principal.agency_id, name=body.name, prefix=prefix, key_hash=digest, scopes=body.scopes, created_by=principal.id)
    session.add(row)
    await session.commit()
    return {"api_key": serializers.api_key(row), "plaintext": plaintext}


@router.delete("/api-keys/{key_id}", status_code=204, response_class=Response)
async def revoke_api_key(key_id: str, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep):
    row = await session.get(ApiKey, key_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    row.revoked_at = utcnow()
    await session.commit()


# ---- webhooks -----------------------------------------------------------------
@router.get("/webhooks")
async def webhooks(principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    rows = (await session.execute(select(Webhook).where(Webhook.agency_id == principal.agency_id).order_by(Webhook.created_at.desc()))).scalars().all()
    return {"items": [serializers.webhook(w) for w in rows], "events": list(KNOWN_EVENTS)}


def _check_events(events: list[str]) -> None:
    bad = [e for e in events if e not in KNOWN_EVENTS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown events: {', '.join(bad)}")


@router.post("/webhooks", status_code=201)
async def create_webhook(body: WebhookIn, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    _check_events(body.events)
    try:
        url = validate_webhook_url(body.url)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    row = Webhook(agency_id=principal.agency_id, name=body.name, url=url, secret=body.secret or generate_webhook_secret(), events=body.events, active=body.active)
    session.add(row)
    await session.commit()
    return {"webhook": serializers.webhook(row, reveal_secret=True)}


@router.patch("/webhooks/{webhook_id}")
async def patch_webhook(webhook_id: str, body: WebhookPatch, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Webhook, webhook_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    data = body.model_dump(exclude_unset=True)
    rotate = data.pop("rotate_secret", False)
    if "events" in data:
        _check_events(data["events"])
    if "url" in data:
        try:
            data["url"] = validate_webhook_url(data["url"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    for k, v in data.items():
        setattr(row, k, v)
    if rotate:
        row.secret = generate_webhook_secret()
    if data.get("active"):
        row.failure_count = 0
    await session.commit()
    return {"webhook": serializers.webhook(row, reveal_secret=rotate)}


@router.get("/webhooks/{webhook_id}/secret")
async def reveal_secret(webhook_id: str, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Webhook, webhook_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    return {"secret": row.secret}


@router.delete("/webhooks/{webhook_id}", status_code=204, response_class=Response)
async def delete_webhook(webhook_id: str, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep):
    row = await session.get(Webhook, webhook_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    await session.delete(row)
    await session.commit()


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Webhook, webhook_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    d = WebhookDelivery(agency_id=principal.agency_id, webhook_id=row.id, event="ping", payload={"message": "Test delivery from your UAE Real Estate CRM"})
    session.add(d)
    await session.commit()
    await deliver_pending(limit=200)
    await session.refresh(d)
    return {"delivery": serializers.delivery(d)}


@router.get("/webhooks/{webhook_id}/deliveries")
async def deliveries(webhook_id: str, principal: Principal = Depends(manager_user), session: AsyncSession = SessionDep) -> dict:
    rows = (await session.execute(select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id, WebhookDelivery.agency_id == principal.agency_id).order_by(WebhookDelivery.created_at.desc()).limit(50))).scalars().all()
    return {"items": [serializers.delivery(d) for d in rows]}
