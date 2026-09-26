from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.leads import scoped
from app.db import utcnow
from app.deps import Principal, SessionDep, current_user
from app.models import PIPELINE_STAGES, Deal, Followup, Lead, Listing, Viewing

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    now = utcnow()
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    base = scoped(select(Lead), principal).whereclause
    stage_counts = dict((await session.execute(select(Lead.stage, func.count()).where(base).group_by(Lead.stage))).all())
    source_counts = dict((await session.execute(select(Lead.source, func.count()).where(base, Lead.created_at >= month).group_by(Lead.source))).all())
    band_counts = dict((await session.execute(select(Lead.ai_band, func.count()).where(base, Lead.stage.not_in(("closed", "lost", "opted_out"))).group_by(Lead.ai_band))).all())
    new_week = (await session.execute(select(func.count()).where(base, Lead.created_at >= week))).scalar_one()
    own = not principal.can_edit_all()
    fu = select(func.count()).select_from(Followup).where(Followup.agency_id == principal.agency_id, Followup.status == "open", Followup.due_at < now)
    vw = select(func.count()).select_from(Viewing).where(Viewing.agency_id == principal.agency_id, Viewing.status.in_(("requested", "confirmed")), Viewing.scheduled_at.between(now, now + timedelta(days=7)))
    if own:
        fu, vw = fu.where(Followup.agent_id == principal.id), vw.where(Viewing.agent_id == principal.id)
    overdue = (await session.execute(fu)).scalar_one()
    upcoming = (await session.execute(vw)).scalar_one()
    live = (await session.execute(select(func.count()).select_from(Listing).where(Listing.agency_id == principal.agency_id, Listing.deleted_at.is_(None), Listing.status == "live"))).scalar_one()
    dq = select(func.count(), func.coalesce(func.sum(Deal.commission_aed), 0.0)).select_from(Deal).where(Deal.agency_id == principal.agency_id, Deal.status == "closed", Deal.updated_at >= month)
    if own:
        dq = dq.where(Deal.agent_id == principal.id)
    closed, commission = (await session.execute(dq)).one()
    return {
        "stages": [{"stage": s, "count": int(stage_counts.get(s, 0))} for s in PIPELINE_STAGES],
        "sources_30d": [{"source": k or "other", "count": int(v)} for k, v in sorted(source_counts.items(), key=lambda kv: -kv[1])],
        "bands": {k or "unscored": int(v) for k, v in band_counts.items()},
        "new_leads_7d": int(new_week),
        "overdue_followups": int(overdue),
        "viewings_next_7d": int(upcoming),
        "live_listings": int(live),
        "closed_30d": int(closed),
        "commission_30d_aed": float(commission or 0),
    }
