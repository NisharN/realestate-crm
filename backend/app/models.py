"""Relational model. One agency = one tenant; every business row carries ``agency_id``.

Stage vocabulary is shared with the AI agent platform so sync is lossless:
new → qualifying → qualified → handed_off → viewing_booked → offer → closed | lost | opted_out
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
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"), index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duration_min: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(16), default="requested", nullable=False)
    location_note: Mapped[str | None] = mapped_column(String(240))
    feedback: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(16), default="crm")


class Followup(Stamped, Base):
    __tablename__ = "followups"
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="call")  # call / whatsapp / email / voice_note / meeting
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)


class Deal(Stamped, Base):
    __tablename__ = "deals"
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"), index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deal_type: Mapped[str] = mapped_column(String(8), default="sale")  # sale / rent
    status: Mapped[str] = mapped_column(String(12), default="offer", nullable=False)
    offer_aed: Mapped[float | None] = mapped_column(Float)
    agreed_aed: Mapped[float | None] = mapped_column(Float)
    commission_pct: Mapped[float | None] = mapped_column(Float)
    commission_aed: Mapped[float | None] = mapped_column(Float)
    mou_signed_at: Mapped[datetime | None] = mapped_column(DateTime)
    transfer_date: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)


class Activity(Stamped, Base):
    """Immutable timeline. Written by the API on every change and by the AI platform via /v1/leads/{id}/activities."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activity_lead_created", "lead_id", "created_at"),)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(8), default="user")  # user / api / system
    actor_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # note, call, whatsapp, email, stage_changed, ai_scored, ...
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Webhook(Stamped, Base):
    """Outbound subscription. Events are HMAC-SHA256 signed (``X-Signature-256: sha256=<hex>``) over the raw body."""

    __tablename__ = "webhooks"
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, default=list)  # ["lead.created", "lead.updated", "*"]
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[int | None] = mapped_column(Integer)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class WebhookDelivery(Stamped, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_delivery_pending", "status", "next_attempt_at"),)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True, nullable=False)
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhooks.id", ondelete="CASCADE"), index=True, nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending / delivered / failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    response_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
