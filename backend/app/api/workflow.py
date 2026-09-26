"""Viewings, follow-ups and deals — the work that happens after a lead exists."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.api.leads import load_lead
from app.db import utcnow
from app.deps import Principal, SessionDep, current_user
from app.models import Deal, Followup, Lead, Listing, Viewing
from app.schemas import DealIn, DealPatch, FollowupIn, FollowupPatch, LeadPatch, ViewingIn, ViewingPatch
from app.services import leads as svc
from app.services.webhooks import deliver_soon, emit

router = APIRouter(tags=["workflow"])


def _naive(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


async def _resolve_listing(session: AsyncSession, agency_id: str, listing_id: str | None, reference: str | None) -> str | None:
    if listing_id:
        row = (await session.execute(select(Listing.id).where(Listing.id == listing_id, Listing.agency_id == agency_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown listing")
        return row
    if reference:
        return (await session.execute(select(Listing.id).where(Listing.reference == reference, Listing.agency_id == agency_id))).scalar_one_or_none()
    return None


# ---- viewings -----------------------------------------------------------------
@router.get("/viewings")
async def list_viewings(
    principal: Principal = Depends(current_user),
    session: AsyncSession = SessionDep,
    status_: str | None = Query(default=None, alias="status"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    q = select(Viewing).where(Viewing.agency_id == principal.agency_id)
    if not principal.can_edit_all():
        q = q.where(Viewing.agent_id == principal.id)
    elif agent_id:
        q = q.where(Viewing.agent_id == agent_id)
    if status_:
        q = q.where(Viewing.status == status_)
    if from_:
        q = q.where(Viewing.scheduled_at >= _naive(from_))
    if to:
        q = q.where(Viewing.scheduled_at <= _naive(to))
    rows = (await session.execute(q.order_by(Viewing.scheduled_at.asc().nulls_last()).limit(limit))).scalars().all()
    lead_ids = {r.lead_id for r in rows}
    listing_ids = {r.listing_id for r in rows if r.listing_id}
    leads = {l.id: serializers.lead(l) for l in (await session.execute(select(Lead).where(Lead.id.in_(lead_ids)))).scalars().all()} if lead_ids else {}
    listings = {x.id: serializers.listing(x) for x in (await session.execute(select(Listing).where(Listing.id.in_(listing_ids)))).scalars().all()} if listing_ids else {}
    return {"items": [{**serializers.viewing(r), "lead": leads.get(r.lead_id), "listing": listings.get(r.listing_id or "")} for r in rows]}


@router.post("/viewings", status_code=201)
async def create_viewing(body: ViewingIn, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, body.lead_id)
    listing_id = await _resolve_listing(session, principal.agency_id, body.listing_id, body.listing_reference)
    row = Viewing(
        agency_id=principal.agency_id, lead_id=lead.id, listing_id=listing_id, agent_id=body.agent_id or lead.assigned_agent_id or principal.id,
        scheduled_at=_naive(body.scheduled_at), duration_min=body.duration_min, status=body.status, location_note=body.location_note, external_id=body.external_id, source=body.source,
    )
    session.add(row)
    await session.flush()
    svc.log(session, principal.agency_id, lead_id=lead.id, kind="viewing", summary=f"Viewing {row.status}" + (f" for {row.scheduled_at:%d %b %H:%M}" if row.scheduled_at else ""), actor_type="user", actor_id=principal.id, data={"viewing_id": row.id})
    if lead.stage in ("new", "qualifying", "qualified", "handed_off"):
        await svc.patch(session, lead, LeadPatch(stage="viewing_booked"), actor_type="system", actor_id=None)
    await emit(session, principal.agency_id, "viewing.created", {"viewing": serializers.viewing(row), "lead": serializers.lead(lead)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"viewing": serializers.viewing(row)}


@router.patch("/viewings/{viewing_id}")
async def patch_viewing(viewing_id: str, body: ViewingPatch, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Viewing, viewing_id)
    if not row or row.agency_id != principal.agency_id or (not principal.can_edit_all() and row.agent_id != principal.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "viewing not found")
    data = body.model_dump(exclude_unset=True)
    if "listing_id" in data:
        data["listing_id"] = await _resolve_listing(session, principal.agency_id, data["listing_id"], None)
    if "scheduled_at" in data:
        data["scheduled_at"] = _naive(data["scheduled_at"])
    changed = [k for k, v in data.items() if getattr(row, k) != v]
    for k in changed:
        setattr(row, k, data[k])
    if "status" in changed:
        lead = await session.get(Lead, row.lead_id)
        svc.log(session, principal.agency_id, lead_id=row.lead_id, kind="viewing", summary=f"Viewing {row.status}" + (f": {row.feedback}" if row.feedback and row.status == "done" else ""), actor_type="user", actor_id=principal.id, data={"viewing_id": row.id})
        if lead and row.status == "done":
            lead.last_contacted_at = utcnow()
    if changed:
        await emit(session, principal.agency_id, "viewing.updated", {"viewing": serializers.viewing(row), "changed": changed})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"viewing": serializers.viewing(row), "changed": changed}


# ---- follow-ups -----------------------------------------------------------------
@router.get("/followups")
async def list_followups(
    principal: Principal = Depends(current_user),
    session: AsyncSession = SessionDep,
    status_: str = Query(default="open", alias="status"),
    due_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    q = select(Followup).where(Followup.agency_id == principal.agency_id)
    if status_ != "all":
        q = q.where(Followup.status == status_)
    if not principal.can_edit_all():
        q = q.where(Followup.agent_id == principal.id)
    if due_before:
        q = q.where(Followup.due_at <= _naive(due_before))
    rows = (await session.execute(q.order_by(Followup.due_at).limit(limit))).scalars().all()
    ids = {r.lead_id for r in rows}
    leads = {l.id: serializers.lead(l) for l in (await session.execute(select(Lead).where(Lead.id.in_(ids)))).scalars().all()} if ids else {}
    now = utcnow()
    return {"items": [{**serializers.followup(r), "lead": leads.get(r.lead_id), "overdue": r.status == "open" and r.due_at < now} for r in rows]}


@router.post("/followups", status_code=201)
async def create_followup(body: FollowupIn, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, body.lead_id)
    row = Followup(agency_id=principal.agency_id, lead_id=lead.id, agent_id=body.agent_id or lead.assigned_agent_id or principal.id, due_at=_naive(body.due_at), channel=body.channel, title=body.title, note=body.note, external_id=body.external_id)
    session.add(row)
    await session.flush()
    if lead.next_follow_up_at is None or row.due_at < lead.next_follow_up_at:
        lead.next_follow_up_at = row.due_at
    svc.log(session, principal.agency_id, lead_id=lead.id, kind="followup_scheduled", summary=f"{body.channel.replace('_', ' ').title()} follow-up scheduled for {row.due_at:%d %b %H:%M}", actor_type="user", actor_id=principal.id, data={"followup_id": row.id})
    await emit(session, principal.agency_id, "followup.created", {"followup": serializers.followup(row), "lead": serializers.lead(lead)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"followup": serializers.followup(row)}


@router.patch("/followups/{followup_id}")
async def patch_followup(followup_id: str, body: FollowupPatch, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Followup, followup_id)
    if not row or row.agency_id != principal.agency_id or (not principal.can_edit_all() and row.agent_id != principal.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "follow-up not found")
    data = body.model_dump(exclude_unset=True)
    if "due_at" in data:
        data["due_at"] = _naive(data["due_at"])
    changed = [k for k, v in data.items() if getattr(row, k) != v]
    for k in changed:
        setattr(row, k, data[k])
    if "status" in changed and row.status == "done":
        row.done_at = utcnow()
        lead = await load_lead(session, principal, row.lead_id)
        lead.last_contacted_at = utcnow()
        nxt = (await session.execute(select(Followup.due_at).where(Followup.lead_id == lead.id, Followup.status == "open", Followup.id != row.id).order_by(Followup.due_at).limit(1))).scalar_one_or_none()
        lead.next_follow_up_at = nxt
        svc.log(session, principal.agency_id, lead_id=lead.id, kind=row.channel if row.channel in ("call", "whatsapp", "email", "meeting", "voice_note") else "note", summary=f"Done: {row.title}", actor_type="user", actor_id=principal.id, data={"followup_id": row.id})
    if changed:
        await emit(session, principal.agency_id, "followup.updated", {"followup": serializers.followup(row), "changed": changed})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"followup": serializers.followup(row), "changed": changed}


# ---- deals ---------------------------------------------------------------------
@router.get("/deals")
async def list_deals(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep, status_: str | None = Query(default=None, alias="status"), limit: int = Query(default=100, ge=1, le=500)) -> dict:
    q = select(Deal).where(Deal.agency_id == principal.agency_id)
    if not principal.can_edit_all():
        q = q.where(Deal.agent_id == principal.id)
    if status_:
        q = q.where(Deal.status == status_)
    rows = (await session.execute(q.order_by(Deal.updated_at.desc()).limit(limit))).scalars().all()
    return {"items": [serializers.deal(r) for r in rows]}


@router.post("/deals", status_code=201)
async def create_deal(body: DealIn, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, body.lead_id)
    listing_id = await _resolve_listing(session, principal.agency_id, body.listing_id, None)
    row = Deal(agency_id=principal.agency_id, lead_id=lead.id, listing_id=listing_id, agent_id=body.agent_id or lead.assigned_agent_id or principal.id, deal_type=body.deal_type, status=body.status, offer_aed=body.offer_aed, agreed_aed=body.agreed_aed, commission_pct=body.commission_pct, transfer_date=body.transfer_date, notes=body.notes)
    _commission(row)
    session.add(row)
    await session.flush()
    svc.log(session, principal.agency_id, lead_id=lead.id, kind="deal", summary="Offer recorded" + (f": AED {row.offer_aed:,.0f}" if row.offer_aed else ""), actor_type="user", actor_id=principal.id, data={"deal_id": row.id})
    if lead.stage not in ("offer", "closed", "lost", "opted_out"):
        await svc.patch(session, lead, LeadPatch(stage="offer"), actor_type="system", actor_id=None)
    await emit(session, principal.agency_id, "deal.created", {"deal": serializers.deal(row), "lead": serializers.lead(lead)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"deal": serializers.deal(row)}


def _commission(row: Deal) -> None:
    base = row.agreed_aed or row.offer_aed
    if base and row.commission_pct is not None:
        row.commission_aed = round(base * row.commission_pct / 100, 2)


@router.patch("/deals/{deal_id}")
async def patch_deal(deal_id: str, body: DealPatch, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await session.get(Deal, deal_id)
    if not row or row.agency_id != principal.agency_id or (not principal.can_edit_all() and row.agent_id != principal.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deal not found")
    data = body.model_dump(exclude_unset=True)
    if "mou_signed_at" in data:
        data["mou_signed_at"] = _naive(data["mou_signed_at"])
    changed = [k for k, v in data.items() if getattr(row, k) != v]
    for k in changed:
        setattr(row, k, data[k])
    _commission(row)
    if "status" in changed:
        lead = await load_lead(session, principal, row.lead_id)
        svc.log(session, principal.agency_id, lead_id=lead.id, kind="deal", summary=f"Deal → {row.status}", actor_type="user", actor_id=principal.id, data={"deal_id": row.id})
        if row.status == "closed":
            await svc.patch(session, lead, LeadPatch(stage="closed"), actor_type="system", actor_id=None)
        elif row.status == "lost":
            await svc.patch(session, lead, LeadPatch(stage="lost", lost_reason="deal fell through"), actor_type="system", actor_id=None)
    if changed:
        await emit(session, principal.agency_id, "deal.updated", {"deal": serializers.deal(row), "changed": changed})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"deal": serializers.deal(row), "changed": changed}
