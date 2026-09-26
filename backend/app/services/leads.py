"""Lead business rules shared by the UI API and the integration API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import CLOSED_STAGES, Activity, Lead, User
from app.schemas import LeadCreate, LeadPatch, LeadWriteBack
from app.serializers import lead as lead_json
from app.services import webhooks

BAND_FOR_SCORE = ((70, "hot"), (40, "warm"), (0, "cold"))


def band_for(score: int | None) -> str | None:
    if score is None:
        return None
    return next(b for floor, b in BAND_FOR_SCORE if score >= floor)


def _naive(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


def log(session: AsyncSession, agency_id: str, *, lead_id: str | None, kind: str, summary: str, actor_type: str, actor_id: str | None, data: dict[str, Any] | None = None, listing_id: str | None = None, created_at: datetime | None = None) -> Activity:
    row = Activity(agency_id=agency_id, lead_id=lead_id, listing_id=listing_id, kind=kind, summary=summary[:400], actor_type=actor_type, actor_id=actor_id, data=data or {})
    if created_at:
        row.created_at = _naive(created_at) or row.created_at
    session.add(row)
    return row


async def find_duplicate(session: AsyncSession, agency_id: str, *, source: str | None, external_id: str | None, phone: str | None, email: str | None) -> Lead | None:
    """Same source+external id wins; otherwise the same phone (or e-mail) on an open lead."""
    if source and external_id:
        row = (await session.execute(select(Lead).where(Lead.agency_id == agency_id, Lead.source == source, Lead.external_id == external_id, Lead.deleted_at.is_(None)))).scalar_one_or_none()
        if row:
            return row
    clauses = []
    if phone:
        clauses.append(Lead.phone == phone)
    if email:
        clauses.append(func.lower(Lead.email) == email.lower())
    if not clauses:
        return None
    q = select(Lead).where(Lead.agency_id == agency_id, Lead.deleted_at.is_(None), or_(*clauses), Lead.stage.not_in(tuple(CLOSED_STAGES))).order_by(Lead.updated_at.desc())
    return (await session.execute(q)).scalars().first()


def _apply(lead: Lead, data: dict[str, Any], *, fill_only: bool = False) -> list[str]:
    changed: list[str] = []
    for key, value in data.items():
        if value is None:
            continue
        current = getattr(lead, key)
        if fill_only and current not in (None, "", [], {}):
            continue
        if isinstance(value, datetime):
            value = _naive(value)
        if current != value:
            setattr(lead, key, value)
            changed.append(key)
    return changed


async def create_or_merge(session: AsyncSession, agency_id: str, body: LeadCreate, *, actor_type: str, actor_id: str | None, merge: bool = True) -> tuple[Lead, bool]:
    """Returns (lead, created). A duplicate is enriched (empty fields only) instead of duplicated."""
    data = body.model_dump(exclude_unset=True)
    existing = await find_duplicate(session, agency_id, source=data.get("source"), external_id=data.get("external_id"), phone=data.get("phone"), email=data.get("email")) if merge else None
    if existing:
        stage = data.pop("stage", None)
        changed = _apply(existing, data, fill_only=True)
        if stage and stage != existing.stage and existing.stage == "new":
            set_stage(existing, stage)
            changed.append("stage")
        log(session, agency_id, lead_id=existing.id, kind="merged", summary=f"Duplicate enquiry merged from {data.get('source') or 'unknown source'}", actor_type=actor_type, actor_id=actor_id, data={"fields": changed})
        await webhooks.emit(session, agency_id, "lead.updated", {"lead": lead_json(existing), "changed": changed})
        return existing, False
    lead = Lead(agency_id=agency_id, source=data.pop("source", None) or "other")
    _apply(lead, data)
    session.add(lead)
    await session.flush()
    log(session, agency_id, lead_id=lead.id, kind="created", summary=f"Lead created from {lead.source}", actor_type=actor_type, actor_id=actor_id)
    await webhooks.emit(session, agency_id, "lead.created", {"lead": lead_json(lead)})
    return lead, True


def set_stage(lead: Lead, stage: str, *, lost_reason: str | None = None) -> None:
    lead.stage = stage
    lead.stage_changed_at = utcnow()
    if stage == "lost":
        lead.lost_reason = lost_reason or lead.lost_reason
    if stage == "opted_out":
        lead.do_not_contact = True
        lead.consent_marketing = False


async def patch(session: AsyncSession, lead: Lead, body: LeadPatch, *, actor_type: str, actor_id: str | None) -> list[str]:
    data = body.model_dump(exclude_unset=True)
    stage = data.pop("stage", None)
    lost_reason = data.pop("lost_reason", None)
    changed = _apply(lead, data)
    if stage and stage != lead.stage:
        previous = lead.stage
        set_stage(lead, stage, lost_reason=lost_reason)
        changed.append("stage")
        log(session, lead.agency_id, lead_id=lead.id, kind="stage_changed", summary=f"Stage {previous} → {stage}", actor_type=actor_type, actor_id=actor_id, data={"from": previous, "to": stage, "lost_reason": lost_reason})
    elif lost_reason:
        lead.lost_reason = lost_reason
        changed.append("lost_reason")
    if changed:
        lead.updated_at = utcnow()
        await webhooks.emit(session, lead.agency_id, "lead.updated", {"lead": lead_json(lead), "changed": changed})
    return changed


async def write_back(session: AsyncSession, lead: Lead, body: LeadWriteBack, *, actor_id: str | None) -> list[str]:
    """The AI platform's PATCH: score/band/stage/assignment. Never downgrades consent or overwrites human-entered contact data."""
    data = body.model_dump(exclude_unset=True)
    changed: list[str] = []
    score = data.get("score", data.get("intent_score"))
    if score is not None:
        lead.ai_score, lead.ai_band, lead.ai_scored_at = int(score), data.get("band") or band_for(int(score)), utcnow()
        changed += ["ai_score", "ai_band"]
        log(session, lead.agency_id, lead_id=lead.id, kind="ai_scored", summary=f"AI score {lead.ai_score} ({lead.ai_band})", actor_type="api", actor_id=actor_id, data={"score": lead.ai_score, "band": lead.ai_band})
    elif data.get("band"):
        lead.ai_band = data["band"]
        changed.append("ai_band")
    if data.get("summary"):
        lead.ai_summary = data["summary"]
        changed.append("ai_summary")
    stage = data.get("stage")
    if stage and stage != lead.stage:
        previous = lead.stage
        set_stage(lead, stage)
        changed.append("stage")
        log(session, lead.agency_id, lead_id=lead.id, kind="stage_changed", summary=f"Stage {previous} → {stage} (AI agent)", actor_type="api", actor_id=actor_id, data={"from": previous, "to": stage})
    if data.get("assigned_broker") is not None and data["assigned_broker"] != lead.ai_broker_ref:
        lead.ai_broker_ref = data["assigned_broker"]
        changed.append("ai_broker_ref")
        agent = (await session.execute(select(User).where(User.agency_id == lead.agency_id, User.external_ref == data["assigned_broker"], User.active.is_(True)))).scalar_one_or_none()
        if agent and agent.id != lead.assigned_agent_id:
            lead.assigned_agent_id = agent.id
            changed.append("assigned_agent_id")
            log(session, lead.agency_id, lead_id=lead.id, kind="assigned", summary=f"Assigned to {agent.full_name} (AI agent)", actor_type="api", actor_id=actor_id)
    fill = {k: data.get(k) for k in ("purpose", "timeline", "budget_min_aed", "budget_max_aed")}
    changed += _apply(lead, fill, fill_only=True)
    area = data.get("area_preference")
    if area and not lead.areas:
        lead.areas = [area] if isinstance(area, str) else [a for a in area if a]
        changed.append("areas")
    for key in ("last_contacted_at", "next_follow_up_at"):
        if data.get(key):
            setattr(lead, key, _naive(data[key]))
            changed.append(key)
    if changed:
        lead.updated_at = utcnow()
        await webhooks.emit(session, lead.agency_id, "lead.updated", {"lead": lead_json(lead), "changed": changed, "origin": "ai_agent"})
    return changed
