"""Explainable, deterministic lead priority and property-fit scoring."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.models import Activity, Lead, LeadScoreHistory, Listing, Viewing


def _band(score: int) -> str:
    return "hot" if score >= 70 else "warm" if score >= 40 else "cold"


def listing_fit(lead: Lead, listing: Listing) -> tuple[int, dict[str, Any]]:
    """Return a 0–100 match with weighted, human-readable factor evidence."""
    if listing.status != "live" or listing.deleted_at is not None:
        return 0, {"eligible": False, "reason": "Property is not live"}
    desired_type = "rent" if lead.purpose == "rent" else "sale"
    if lead.purpose and listing.listing_type != desired_type:
        return 0, {"eligible": False, "reason": "Sale/rent type differs"}

    factors: dict[str, Any] = {}
    score = 0
    if lead.purpose:
        score += 20
        factors["purpose"] = {"points": 20, "reason": "Matches requested transaction"}
    if lead.property_type:
        points = 20 if lead.property_type.casefold() == listing.property_type.casefold() else 0
        score += points
        factors["property_type"] = {"points": points, "reason": "Property type match" if points else "Property type differs"}
    if lead.bedrooms is not None:
        points = 15 if lead.bedrooms == listing.bedrooms else 0
        score += points
        factors["bedrooms"] = {"points": points, "reason": "Bedroom count match" if points else "Bedroom count differs"}
    if lead.areas:
        area_match = any(a.casefold() in {listing.community.casefold(), (listing.sub_community or "").casefold(), (listing.building or "").casefold()} for a in lead.areas)
        points = 25 if area_match else 0
        score += points
        factors["area"] = {"points": points, "reason": "Preferred area match" if points else "Area differs"}
    if lead.budget_max_aed:
        price = listing.price_aed
        if lead.budget_min_aed and price < lead.budget_min_aed * 0.9:
            points, reason = 5, "Below requested budget range"
        elif price <= lead.budget_max_aed:
            points, reason = 20, "Within budget"
        elif price <= lead.budget_max_aed * 1.1:
            points, reason = 10, "Within 10% above budget"
        else:
            points, reason = 0, "Above budget"
        score += points
        factors["budget"] = {"points": points, "reason": reason}
    else:
        factors["budget"] = {"points": 10, "reason": "Budget not provided; no budget penalty"}
        score += 10
    return min(score, 100), {"eligible": True, "factors": factors}


async def recommendations(session: AsyncSession, lead: Lead, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Listing).where(
        Listing.agency_id == lead.agency_id,
        Listing.status == "live",
        Listing.deleted_at.is_(None),
    ))).scalars().all()
    matches = []
    for listing in rows:
        score, detail = listing_fit(lead, listing)
        if detail.get("eligible") and score >= 30:
            matches.append({"listing": listing, "score": score, "factors": detail["factors"]})
    matches.sort(key=lambda m: (m["score"], m["listing"].updated_at), reverse=True)
    return matches[:limit]


async def calculate(session: AsyncSession, lead: Lead) -> tuple[int, dict[str, Any]]:
    """Business priority score. Consent gates outreach separately; it does not lower value."""
    points: dict[str, dict[str, Any]] = {}
    score = 0

    contact = 10 if lead.phone or lead.email else 0
    if lead.first_name or lead.last_name:
        contact += 5
    points["contactability"] = {"score": contact, "max": 15, "reason": "Contact details and name are available" if contact >= 10 else "Contact details are incomplete"}
    score += contact

    intent = 10 if lead.purpose else 0
    points["intent"] = {"score": intent, "max": 10, "reason": "Purchase/rental intent captured" if intent else "Ask what the lead wants to buy or rent"}
    score += intent

    timeline = (lead.timeline or "").casefold()
    urgency = 15 if any(x in timeline for x in ("immediate", "asap", "urgent", "this month", "1 month")) else 10 if any(x in timeline for x in ("3 month", "quarter")) else 5 if timeline else 0
    points["timeline"] = {"score": urgency, "max": 15, "reason": "Near-term timeline" if urgency >= 10 else "Timeline captured" if urgency else "Timeline not captured"}
    score += urgency

    budget = 10 if lead.budget_max_aed else 0
    points["budget"] = {"score": budget, "max": 10, "reason": "Budget captured" if budget else "Budget not captured"}
    score += budget

    area = 10 if lead.areas else 0
    points["area"] = {"score": area, "max": 10, "reason": "Preferred area captured" if area else "Preferred area not captured"}
    score += area

    requirements = 5 if lead.property_type or lead.bedrooms is not None else 0
    points["property_requirements"] = {"score": requirements, "max": 5, "reason": "Property requirements captured" if requirements else "Property type or bedrooms not captured"}
    score += requirements

    matches = await recommendations(session, lead, limit=10)
    inventory = min(20, len(matches) * 5)
    points["inventory_match"] = {"score": inventory, "max": 20, "reason": f"{len(matches)} suitable live properties found" if matches else "No suitable live properties found"}
    score += inventory

    now = utcnow()
    engagement = 10 if lead.last_contacted_at and lead.last_contacted_at >= now - timedelta(days=7) else 5 if lead.last_contacted_at and lead.last_contacted_at >= now - timedelta(days=30) else 0
    viewing = await session.scalar(select(Viewing.id).where(Viewing.agency_id == lead.agency_id, Viewing.lead_id == lead.id, Viewing.status.in_(("requested", "confirmed", "done"))).limit(1))
    if viewing:
        engagement = 10
    points["engagement"] = {"score": engagement, "max": 10, "reason": "Property viewing activity recorded" if viewing else "Contacted in the last 7 days" if engagement == 10 else "Contacted in the last 30 days" if engagement else "No recent recorded contact"}
    score += engagement

    stage_points = 5 if lead.stage in ("qualified", "handed_off", "viewing_booked", "offer") else 0
    points["progress"] = {"score": stage_points, "max": 5, "reason": "Lead has progressed in the pipeline" if stage_points else "Lead has not reached qualification"}
    score += stage_points

    return min(100, score), points


async def recalculate(session: AsyncSession, lead: Lead, *, trigger: str) -> dict[str, Any]:
    score, factors = await calculate(session, lead)
    band = _band(score)
    lead.ai_score, lead.ai_band, lead.ai_scored_at = score, band, utcnow()
    lead.ai_summary = f"Priority {score}/100 ({band}). " + " ".join(
        f"{key.replace('_', ' ')}: {value['reason']}." for key, value in factors.items()
    )
    history = LeadScoreHistory(agency_id=lead.agency_id, lead_id=lead.id, score=score, band=band, stage=lead.stage, factors=factors, trigger=trigger)
    session.add(history)
    session.add(Activity(
        agency_id=lead.agency_id,
        lead_id=lead.id,
        actor_type="system",
        kind="priority_scored",
        summary=f"Priority score {score}/100 ({band})",
        data={"score": score, "band": band, "stage": lead.stage, "trigger": trigger, "factors": factors},
    ))
    return {"score": score, "band": band, "factors": factors}
