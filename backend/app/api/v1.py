"""Integration API (``/v1``) — what the AI agent platform and other systems talk to.

Auth: ``Authorization: Bearer crm_live_…`` (an API key from Settings → API keys).

Changed-since paging (leads, listings, viewings): rows are ordered by ``updated_at, id``
ascending. Pass either ``updated_after=<ISO timestamp>`` (compatible with the agent
platform's generic CRM pull connector: ``cursor_param=updated_after``,
``cursor_field=updated_at``, ``records_path=data``, ``next_cursor_path=paging.next``)
or the opaque ``cursor`` returned in ``paging.next``. Every response also includes
``paging.next`` (``null`` when there is nothing more).
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.config import get_settings
from app.db import utcnow
from app.deps import Principal, SessionDep, api_principal
from app.models import PIPELINE_STAGES, Agency, Followup, Lead, Listing, User, Viewing
from app.schemas import ActivityIn, FollowupIn, LeadCreate, LeadWriteBack, ViewingIn, ViewingPatch
from app.services import leads as svc
from app.services.webhooks import deliver_soon, emit

router = APIRouter(prefix="/v1", tags=["integration"])


class LeadBatch(BaseModel):
    leads: list[LeadCreate]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "updated_after must be an ISO-8601 timestamp") from None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _encode_cursor(updated_at: datetime, row_id: str) -> str:
    return base64.urlsafe_b64encode(f"{updated_at.isoformat()}|{row_id}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, row_id = raw.split("|", 1)
        return datetime.fromisoformat(stamp), row_id
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid cursor") from None


def _paged(model: Any, query: Select, *, updated_after: str | None, cursor: str | None) -> Select:
    if cursor:
        stamp, row_id = _decode_cursor(cursor)
        query = query.where(or_(model.updated_at > stamp, and_(model.updated_at == stamp, model.id > row_id)))
    elif updated_after:
        query = query.where(model.updated_at > _parse_ts(updated_after))
    return query.order_by(model.updated_at.asc(), model.id.asc())


def _page(rows: list[Any], limit: int, serialize: Any) -> dict[str, Any]:
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = _encode_cursor(rows[-1].updated_at, rows[-1].id) if rows and more else None
    return {"data": [serialize(r) for r in rows], "paging": {"next": nxt, "count": len(rows)}}


def _limit(limit: int) -> int:
    return min(limit, get_settings().api_page_limit)


# ---- meta ---------------------------------------------------------------------
@router.get("/me")
async def me(principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    agency = await session.get(Agency, principal.agency_id)
    return {"agency": serializers.agency(agency) if agency else None, "scopes": list(principal.scopes), "stages": list(PIPELINE_STAGES)}


@router.get("/agents")
async def agents(principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    principal.require("agents:read")
    rows = (await session.execute(select(User).where(User.agency_id == principal.agency_id, User.active.is_(True)).order_by(User.full_name))).scalars().all()
    return {"data": [{k: v for k, v in serializers.user(u).items() if k != "email"} | {"email": u.email} for u in rows]}


# ---- leads --------------------------------------------------------------------
@router.get("/leads")
async def list_leads(
    principal: Principal = Depends(api_principal),
    session: AsyncSession = SessionDep,
    updated_after: str | None = None,
    cursor: str | None = None,
    stage: str | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    principal.require("leads:read")
    limit = _limit(limit)
    q = select(Lead).where(Lead.agency_id == principal.agency_id)
    if not include_deleted:
        q = q.where(Lead.deleted_at.is_(None))
    if stage:
        q = q.where(Lead.stage == stage)
    rows = (await session.execute(_paged(Lead, q, updated_after=updated_after, cursor=cursor).limit(limit + 1))).scalars().all()
    agent_ids = {r.assigned_agent_id for r in rows if r.assigned_agent_id}
    agents_ = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(agent_ids)))).scalars().all()} if agent_ids else {}
    return _page(list(rows), limit, lambda r: {**serializers.lead(r, agent=agents_.get(r.assigned_agent_id or "")), "deleted_at": r.deleted_at.isoformat() + "Z" if r.deleted_at else None})


async def _load(session: AsyncSession, principal: Principal, lead_id: str) -> Lead:
    row = await session.get(Lead, lead_id)
    if not row or row.agency_id != principal.agency_id or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
    return row


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    principal.require("leads:read")
    row = await _load(session, principal, lead_id)
    return {"lead": serializers.lead(row)}


@router.post("/leads", status_code=201)
async def upsert_leads(body: LeadCreate | LeadBatch, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    """Create or merge. Single object or ``{"leads": [...]}``. Idempotent on (source, external_id), then phone/e-mail."""
    principal.require("leads:write")
    items = body.leads if isinstance(body, LeadBatch) else [body]
    if len(items) > 500:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "max 500 leads per request")
    out = []
    for item in items:
        if item.source is None:
            item = item.model_copy(update={"source": "ai_agent"})
        lead, created = await svc.create_or_merge(session, principal.agency_id, item, actor_type="api", actor_id=principal.id)
        out.append({"id": lead.id, "created": created, "external_id": lead.external_id, "stage": lead.stage})
    await session.commit()
    tasks.add_task(deliver_soon)
    if isinstance(body, LeadBatch):
        return {"results": out, "created": sum(1 for o in out if o["created"]), "merged": sum(1 for o in out if not o["created"])}
    lead = await _load(session, principal, out[0]["id"])
    return {"lead": serializers.lead(lead), "created": out[0]["created"]}


@router.patch("/leads/{lead_id}")
async def write_back(lead_id: str, body: LeadWriteBack, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    """Write-back from the AI platform: score / band / stage / assigned_broker / qualification facts."""
    principal.require("leads:write")
    row = await _load(session, principal, lead_id)
    changed = await svc.write_back(session, row, body, actor_id=principal.id)
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"lead": serializers.lead(row), "changed": changed}


@router.post("/leads/{lead_id}/activities", status_code=201)
async def add_activity(lead_id: str, body: ActivityIn, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    """Timeline entries from outside systems (WhatsApp sent, voice note delivered, AI conversation summary…)."""
    principal.require("leads:write")
    row = await _load(session, principal, lead_id)
    act = svc.log(session, principal.agency_id, lead_id=row.id, kind=body.kind, summary=body.summary, actor_type="api", actor_id=body.actor_id or principal.id, data=body.data, created_at=body.occurred_at)
    if body.kind in ("whatsapp", "call", "email", "voice_note", "meeting"):
        row.last_contacted_at = (body.occurred_at.replace(tzinfo=None) if body.occurred_at and body.occurred_at.tzinfo else body.occurred_at) or utcnow()
        await emit(session, principal.agency_id, "lead.contacted", {"lead": serializers.lead(row), "activity": {"kind": body.kind, "summary": body.summary}})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"activity": serializers.activity(act)}


# ---- listings ------------------------------------------------------------------
@router.get("/listings")
async def list_listings(
    principal: Principal = Depends(api_principal),
    session: AsyncSession = SessionDep,
    updated_after: str | None = None,
    cursor: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    listing_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    principal.require("listings:read")
    limit = _limit(limit)
    q = select(Listing).where(Listing.agency_id == principal.agency_id, Listing.deleted_at.is_(None))
    if status_:
        q = q.where(Listing.status == status_)
    if listing_type:
        q = q.where(Listing.listing_type == listing_type)
    rows = (await session.execute(_paged(Listing, q, updated_after=updated_after, cursor=cursor).limit(limit + 1))).scalars().all()
    return _page(list(rows), limit, serializers.listing)


# ---- viewings / follow-ups -------------------------------------------------------
@router.get("/viewings")
async def list_viewings(principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep, updated_after: str | None = None, cursor: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    principal.require("viewings:read")
    limit = _limit(limit)
    q = select(Viewing).where(Viewing.agency_id == principal.agency_id)
    rows = (await session.execute(_paged(Viewing, q, updated_after=updated_after, cursor=cursor).limit(limit + 1))).scalars().all()
    return _page(list(rows), limit, serializers.viewing)


@router.post("/viewings", status_code=201)
async def create_viewing(body: ViewingIn, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    """Idempotent on ``external_id`` (the viewing id on the calling system)."""
    principal.require("viewings:write")
    lead = await _load(session, principal, body.lead_id)
    if body.external_id:
        dup = (await session.execute(select(Viewing).where(Viewing.agency_id == principal.agency_id, Viewing.external_id == body.external_id))).scalar_one_or_none()
        if dup:
            return {"viewing": serializers.viewing(dup), "created": False}
    listing_id = body.listing_id
    if not listing_id and body.listing_reference:
        listing_id = (await session.execute(select(Listing.id).where(Listing.agency_id == principal.agency_id, Listing.reference == body.listing_reference))).scalar_one_or_none()
    scheduled = body.scheduled_at.replace(tzinfo=None) if body.scheduled_at and body.scheduled_at.tzinfo else body.scheduled_at
    row = Viewing(agency_id=principal.agency_id, lead_id=lead.id, listing_id=listing_id, agent_id=body.agent_id or lead.assigned_agent_id, scheduled_at=scheduled, duration_min=body.duration_min, status=body.status, location_note=body.location_note, external_id=body.external_id, source=body.source if body.source != "crm" else "ai_agent")
    session.add(row)
    await session.flush()
    svc.log(session, principal.agency_id, lead_id=lead.id, kind="viewing", summary=f"Viewing {row.status} via {row.source}", actor_type="api", actor_id=principal.id, data={"viewing_id": row.id})
    if lead.stage in ("new", "qualifying", "qualified", "handed_off"):
        svc.set_stage(lead, "viewing_booked")
    await emit(session, principal.agency_id, "viewing.created", {"viewing": serializers.viewing(row), "lead": serializers.lead(lead)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"viewing": serializers.viewing(row), "created": True}


@router.patch("/viewings/{viewing_id}")
async def patch_viewing(viewing_id: str, body: ViewingPatch, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    principal.require("viewings:write")
    row = await session.get(Viewing, viewing_id)
    if not row or row.agency_id != principal.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "viewing not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("scheduled_at") is not None and data["scheduled_at"].tzinfo:
        data["scheduled_at"] = data["scheduled_at"].replace(tzinfo=None)
    changed = [k for k, v in data.items() if getattr(row, k) != v]
    for k in changed:
        setattr(row, k, data[k])
    if "status" in changed:
        svc.log(session, principal.agency_id, lead_id=row.lead_id, kind="viewing", summary=f"Viewing {row.status}", actor_type="api", actor_id=principal.id, data={"viewing_id": row.id})
    if changed:
        await emit(session, principal.agency_id, "viewing.updated", {"viewing": serializers.viewing(row), "changed": changed})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"viewing": serializers.viewing(row), "changed": changed}


@router.post("/followups", status_code=201)
async def create_followup(body: FollowupIn, tasks: BackgroundTasks, principal: Principal = Depends(api_principal), session: AsyncSession = SessionDep) -> dict:
    principal.require("followups:write")
    lead = await _load(session, principal, body.lead_id)
    if body.external_id:
        dup = (await session.execute(select(Followup).where(Followup.agency_id == principal.agency_id, Followup.external_id == body.external_id))).scalar_one_or_none()
        if dup:
            return {"followup": serializers.followup(dup), "created": False}
    due = body.due_at.replace(tzinfo=None) if body.due_at.tzinfo else body.due_at
    row = Followup(agency_id=principal.agency_id, lead_id=lead.id, agent_id=body.agent_id or lead.assigned_agent_id, due_at=due, channel=body.channel, title=body.title, note=body.note, external_id=body.external_id)
    session.add(row)
    await session.flush()
    if lead.next_follow_up_at is None or due < lead.next_follow_up_at:
        lead.next_follow_up_at = due
    svc.log(session, principal.agency_id, lead_id=lead.id, kind="followup_scheduled", summary=f"{body.channel.replace('_', ' ').title()} follow-up scheduled (AI agent)", actor_type="api", actor_id=principal.id, data={"followup_id": row.id})
    await emit(session, principal.agency_id, "followup.created", {"followup": serializers.followup(row), "lead": serializers.lead(lead)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"followup": serializers.followup(row), "created": True}
