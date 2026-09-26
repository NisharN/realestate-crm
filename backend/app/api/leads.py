from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, String, cast, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.db import utcnow
from app.deps import Principal, SessionDep, current_user
from app.models import PIPELINE_STAGES, Activity, Deal, Followup, Lead, User, Viewing
from app.schemas import LeadCreate, LeadPatch, NoteIn, StageMove
from app.services import leads as svc
from app.services.webhooks import deliver_soon, emit

router = APIRouter(prefix="/leads", tags=["leads"])


def scoped(q: Select, principal: Principal) -> Select:
    q = q.where(Lead.agency_id == principal.agency_id, Lead.deleted_at.is_(None))
    if not principal.can_edit_all():
        q = q.where(or_(Lead.assigned_agent_id == principal.id, Lead.assigned_agent_id.is_(None)))
    return q


async def load_lead(session: AsyncSession, principal: Principal, lead_id: str) -> Lead:
    lead = (await session.execute(scoped(select(Lead).where(Lead.id == lead_id), principal))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
    return lead


async def _agents(session: AsyncSession, agency_id: str, ids: set[str | None]) -> dict[str, User]:
    wanted = [i for i in ids if i]
    if not wanted:
        return {}
    rows = (await session.execute(select(User).where(User.agency_id == agency_id, User.id.in_(wanted)))).scalars().all()
    return {u.id: u for u in rows}


@router.get("")
async def list_leads(
    principal: Principal = Depends(current_user),
    session: AsyncSession = SessionDep,
    stage: str | None = None,
    q: str | None = Query(default=None, max_length=80),
    source: str | None = None,
    band: str | None = None,
    agent_id: str | None = None,
    area: str | None = None,
    open_only: bool = True,
    sort: str = Query(default="updated_at", pattern="^(updated_at|created_at|ai_score|next_follow_up_at|budget_max_aed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    query = scoped(select(Lead), principal)
    if stage:
        query = query.where(Lead.stage == stage)
    elif open_only:
        query = query.where(Lead.stage.not_in(("closed", "lost", "opted_out")))
    if source:
        query = query.where(Lead.source == source)
    if band:
        query = query.where(Lead.ai_band == band)
    if agent_id:
        query = query.where(Lead.assigned_agent_id == agent_id)
    if area:
        query = query.where(func.lower(cast(Lead.areas, String)).contains(area.lower()))
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Lead.first_name).like(like), func.lower(Lead.last_name).like(like), Lead.phone.like(f"%{q}%"), func.lower(Lead.email).like(like)))
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    column = getattr(Lead, sort)
    order = column.asc() if sort == "next_follow_up_at" else column.desc()
    rows = (await session.execute(query.order_by(order.nulls_last(), Lead.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    agents = await _agents(session, principal.agency_id, {r.assigned_agent_id for r in rows})
    return {"items": [serializers.lead(r, agent=agents.get(r.assigned_agent_id or "")) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/pipeline")
async def pipeline(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep, agent_id: str | None = None) -> dict:
    """Stage counts + the top cards per stage, for the board view."""
    base = scoped(select(Lead), principal)
    if agent_id:
        base = base.where(Lead.assigned_agent_id == agent_id)
    counts = dict((await session.execute(select(Lead.stage, func.count()).where(base.whereclause).group_by(Lead.stage))).all())
    columns = []
    for stage in PIPELINE_STAGES:
        rows = (await session.execute(base.where(Lead.stage == stage).order_by(Lead.ai_score.desc().nulls_last(), Lead.updated_at.desc()).limit(25))).scalars().all()
        columns.append({"stage": stage, "count": int(counts.get(stage, 0)), "leads": [serializers.lead(r) for r in rows]})
    return {"columns": columns, "total": sum(counts.values())}


@router.get("/today")
async def today(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    """An agent's day: overdue + due follow-ups, viewings, fresh hot leads, stale leads."""
    now = utcnow()
    end = now + timedelta(hours=24)
    mine = scoped(select(Lead), principal)
    own = not principal.can_edit_all()
    fu_scope = (Followup.agent_id == principal.id) if own else true()
    vw_scope = (Viewing.agent_id == principal.id) if own else true()
    followups = (await session.execute(select(Followup).where(Followup.agency_id == principal.agency_id, Followup.status == "open", Followup.due_at <= end, fu_scope).order_by(Followup.due_at).limit(50))).scalars().all()
    viewings = (await session.execute(select(Viewing).where(Viewing.agency_id == principal.agency_id, Viewing.status.in_(("requested", "confirmed")), Viewing.scheduled_at.between(now - timedelta(hours=2), end), vw_scope).order_by(Viewing.scheduled_at).limit(50))).scalars().all()
    hot = (await session.execute(mine.where(Lead.ai_band == "hot", Lead.stage.in_(("new", "qualifying", "qualified"))).order_by(Lead.ai_score.desc(), Lead.created_at.desc()).limit(10))).scalars().all()
    stale_cutoff = now - timedelta(days=7)
    stale = (await session.execute(mine.where(Lead.stage.in_(("qualifying", "qualified", "handed_off")), or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at < stale_cutoff), Lead.updated_at < stale_cutoff).order_by(Lead.ai_score.desc().nulls_last()).limit(10))).scalars().all()
    lead_ids = {f.lead_id for f in followups} | {v.lead_id for v in viewings}
    leads = {l.id: serializers.lead(l) for l in (await session.execute(select(Lead).where(Lead.id.in_(lead_ids)))).scalars().all()} if lead_ids else {}
    return {
        "followups": [{**serializers.followup(f), "lead": leads.get(f.lead_id), "overdue": f.due_at < now} for f in followups],
        "viewings": [{**serializers.viewing(v), "lead": leads.get(v.lead_id)} for v in viewings],
        "hot_leads": [serializers.lead(l) for l in hot],
        "stale_leads": [serializers.lead(l) for l in stale],
    }


@router.post("", status_code=201)
async def create_lead(body: LeadCreate, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    if body.assigned_agent_id is None and not principal.is_manager:
        body = body.model_copy(update={"assigned_agent_id": principal.id})
    lead, created = await svc.create_or_merge(session, principal.agency_id, body, actor_type="user", actor_id=principal.id)
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"lead": serializers.lead(lead), "created": created}


@router.get("/{lead_id}")
async def get_lead(lead_id: str, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, lead_id)
    agent = await session.get(User, lead.assigned_agent_id) if lead.assigned_agent_id else None
    activities = (await session.execute(select(Activity).where(Activity.lead_id == lead.id).order_by(Activity.created_at.desc()).limit(200))).scalars().all()
    viewings = (await session.execute(select(Viewing).where(Viewing.lead_id == lead.id).order_by(Viewing.scheduled_at.desc().nulls_last()))).scalars().all()
    followups = (await session.execute(select(Followup).where(Followup.lead_id == lead.id).order_by(Followup.due_at))).scalars().all()
    deals = (await session.execute(select(Deal).where(Deal.lead_id == lead.id).order_by(Deal.created_at.desc()))).scalars().all()
    return {
        "lead": serializers.lead(lead, agent=agent),
        "activities": [serializers.activity(a) for a in activities],
        "viewings": [serializers.viewing(v) for v in viewings],
        "followups": [serializers.followup(f) for f in followups],
        "deals": [serializers.deal(d) for d in deals],
    }


@router.patch("/{lead_id}")
async def patch_lead(lead_id: str, body: LeadPatch, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, lead_id)
    if body.assigned_agent_id and body.assigned_agent_id != lead.assigned_agent_id:
        agent = await session.get(User, body.assigned_agent_id)
        if not agent or agent.agency_id != principal.agency_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown agent")
        if not principal.is_manager and body.assigned_agent_id != principal.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "agents can only claim leads for themselves")
        svc.log(session, principal.agency_id, lead_id=lead.id, kind="assigned", summary=f"Assigned to {agent.full_name}", actor_type="user", actor_id=principal.id)
    changed = await svc.patch(session, lead, body, actor_type="user", actor_id=principal.id)
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"lead": serializers.lead(lead), "changed": changed}


@router.post("/{lead_id}/stage")
async def move_stage(lead_id: str, body: StageMove, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, lead_id)
    changed = await svc.patch(session, lead, LeadPatch(stage=body.stage, lost_reason=body.lost_reason), actor_type="user", actor_id=principal.id)
    if body.note:
        svc.log(session, principal.agency_id, lead_id=lead.id, kind="note", summary=body.note, actor_type="user", actor_id=principal.id)
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"lead": serializers.lead(lead), "changed": changed}


@router.post("/{lead_id}/activities", status_code=201)
async def add_note(lead_id: str, body: NoteIn, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    lead = await load_lead(session, principal, lead_id)
    row = svc.log(session, principal.agency_id, lead_id=lead.id, kind=body.kind, summary=body.summary, actor_type="user", actor_id=principal.id, data=body.data)
    if body.mark_contacted and body.kind in ("call", "whatsapp", "email", "meeting", "voice_note"):
        lead.last_contacted_at = utcnow()
        await emit(session, principal.agency_id, "lead.contacted", {"lead": serializers.lead(lead), "activity": {"kind": body.kind, "summary": body.summary}})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"activity": serializers.activity(row)}


@router.delete("/{lead_id}", status_code=204, response_class=Response)
async def delete_lead(lead_id: str, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep):
    lead = await load_lead(session, principal, lead_id)
    if not principal.is_manager:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only owners/managers can delete leads")
    lead.deleted_at = utcnow()
    await emit(session, principal.agency_id, "lead.deleted", {"lead": {"id": lead.id}})
    await session.commit()
    tasks.add_task(deliver_soon)
