"""Row → JSON. One place, so the UI API and the integration API emit identical shapes."""
from __future__ import annotations

from typing import Any

from app.db import iso
from app.models import Activity, Agency, ApiKey, Deal, Followup, Lead, Listing, User, Viewing, Webhook, WebhookDelivery


def agency(a: Agency) -> dict[str, Any]:
    return {"id": a.id, "name": a.name, "slug": a.slug, "rera_orn": a.rera_orn, "trade_license": a.trade_license, "emirate": a.emirate, "phone": a.phone, "email": a.email, "currency": a.currency, "timezone": a.timezone}


def user(u: User) -> dict[str, Any]:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name, "phone": u.phone, "role": u.role, "rera_brn": u.rera_brn,
        "languages": u.languages or [], "areas": u.areas or [], "active": u.active, "external_ref": u.external_ref,
        "created_at": iso(u.created_at), "updated_at": iso(u.updated_at),
    }


def lead(l: Lead, *, agent: User | None = None) -> dict[str, Any]:
    return {
        "id": l.id, "name": l.name, "first_name": l.first_name, "last_name": l.last_name, "phone": l.phone, "email": l.email,
        "nationality": l.nationality, "language": l.language, "source": l.source, "external_id": l.external_id, "campaign": l.campaign,
        "listing_reference": l.listing_reference, "purpose": l.purpose, "property_type": l.property_type, "bedrooms": l.bedrooms,
        "areas": l.areas or [], "budget_min_aed": l.budget_min_aed, "budget_max_aed": l.budget_max_aed, "timeline": l.timeline,
        "payment_method": l.payment_method, "stage": l.stage, "stage_changed_at": iso(l.stage_changed_at), "lost_reason": l.lost_reason,
        "assigned_agent_id": l.assigned_agent_id, "assigned_agent": user(agent) if agent else None,
        "ai_score": l.ai_score, "ai_band": l.ai_band, "ai_summary": l.ai_summary, "ai_scored_at": iso(l.ai_scored_at), "ai_broker_ref": l.ai_broker_ref,
        "consent_marketing": l.consent_marketing, "do_not_contact": l.do_not_contact,
        "last_contacted_at": iso(l.last_contacted_at), "next_follow_up_at": iso(l.next_follow_up_at),
        "notes": l.notes, "tags": l.tags or [], "custom": l.custom or {},
        "created_at": iso(l.created_at), "updated_at": iso(l.updated_at),
    }


def listing(x: Listing) -> dict[str, Any]:
    return {
        "id": x.id, "reference": x.reference, "title": x.title, "listing_type": x.listing_type, "status": x.status, "property_type": x.property_type,
        "community": x.community, "sub_community": x.sub_community, "building": x.building, "emirate": x.emirate, "bedrooms": x.bedrooms, "bathrooms": x.bathrooms,
        "size_sqft": x.size_sqft, "price_aed": x.price_aed, "rent_frequency": x.rent_frequency, "furnished": x.furnished, "completion_status": x.completion_status,
        "handover_date": x.handover_date, "developer": x.developer, "permit_number": x.permit_number, "dld_number": x.dld_number,
        "latitude": x.latitude, "longitude": x.longitude, "description": x.description, "amenities": x.amenities or [], "photos": x.photos or [],
        "agent_id": x.agent_id, "portals": x.portals or {}, "last_verified_at": iso(x.last_verified_at),
        "created_at": iso(x.created_at), "updated_at": iso(x.updated_at),
    }


def listing_private(x: Listing) -> dict[str, Any]:
    return {**listing(x), "owner_name": x.owner_name, "owner_phone": x.owner_phone}


def viewing(v: Viewing) -> dict[str, Any]:
    return {
        "id": v.id, "lead_id": v.lead_id, "listing_id": v.listing_id, "agent_id": v.agent_id, "scheduled_at": iso(v.scheduled_at), "duration_min": v.duration_min,
        "status": v.status, "location_note": v.location_note, "feedback": v.feedback, "external_id": v.external_id, "source": v.source,
        "created_at": iso(v.created_at), "updated_at": iso(v.updated_at),
    }


def followup(f: Followup) -> dict[str, Any]:
    return {
        "id": f.id, "lead_id": f.lead_id, "agent_id": f.agent_id, "due_at": iso(f.due_at), "channel": f.channel, "title": f.title, "note": f.note,
        "status": f.status, "done_at": iso(f.done_at), "external_id": f.external_id, "created_at": iso(f.created_at), "updated_at": iso(f.updated_at),
    }


def deal(d: Deal) -> dict[str, Any]:
    return {
        "id": d.id, "lead_id": d.lead_id, "listing_id": d.listing_id, "agent_id": d.agent_id, "deal_type": d.deal_type, "status": d.status,
        "offer_aed": d.offer_aed, "agreed_aed": d.agreed_aed, "commission_pct": d.commission_pct, "commission_aed": d.commission_aed,
        "mou_signed_at": iso(d.mou_signed_at), "transfer_date": d.transfer_date, "notes": d.notes, "created_at": iso(d.created_at), "updated_at": iso(d.updated_at),
    }


def activity(a: Activity) -> dict[str, Any]:
    return {"id": a.id, "lead_id": a.lead_id, "listing_id": a.listing_id, "actor_type": a.actor_type, "actor_id": a.actor_id, "kind": a.kind, "summary": a.summary, "data": a.data or {}, "created_at": iso(a.created_at)}


def api_key(k: ApiKey) -> dict[str, Any]:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes or [], "last_used_at": iso(k.last_used_at), "revoked_at": iso(k.revoked_at), "created_at": iso(k.created_at)}


def webhook(w: Webhook, *, reveal_secret: bool = False) -> dict[str, Any]:
    out = {
        "id": w.id, "name": w.name, "url": w.url, "events": w.events or [], "active": w.active, "last_delivery_at": iso(w.last_delivery_at),
        "last_status": w.last_status, "failure_count": w.failure_count, "created_at": iso(w.created_at),
    }
    if reveal_secret:
        out["secret"] = w.secret
    return out


def delivery(d: WebhookDelivery) -> dict[str, Any]:
    return {"id": d.id, "webhook_id": d.webhook_id, "event": d.event, "status": d.status, "attempts": d.attempts, "response_status": d.response_status, "error": d.error, "next_attempt_at": iso(d.next_attempt_at), "created_at": iso(d.created_at)}
