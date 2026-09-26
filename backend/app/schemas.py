from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import DEAL_STATUSES, FOLLOWUP_STATUSES, LISTING_STATUSES, LISTING_TYPES, PIPELINE_STAGES, PURPOSES, USER_ROLES, VIEWING_STATUSES

Stage = Literal["new", "qualifying", "qualified", "handed_off", "viewing_booked", "offer", "closed", "lost", "opted_out"]
assert set(Stage.__args__) == set(PIPELINE_STAGES)  # type: ignore[attr-defined]


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = phonenumbers.parse(raw, "AE")
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    return digits or None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- auth ---------------------------------------------------------------
class RegisterAgency(Strict):
    agency_name: str = Field(min_length=2, max_length=160)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    rera_orn: str | None = None
    phone: str | None = None


class Login(Strict):
    email: EmailStr
    password: str


class UserIn(Strict):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["owner", "manager", "agent"] = "agent"
    phone: str | None = None
    rera_brn: str | None = None
    languages: list[str] = []
    areas: list[str] = []
    external_ref: str | None = None


class UserPatch(Strict):
    full_name: str | None = None
    role: Literal["owner", "manager", "agent"] | None = None
    phone: str | None = None
    rera_brn: str | None = None
    languages: list[str] | None = None
    areas: list[str] | None = None
    external_ref: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


assert set(USER_ROLES) == {"owner", "manager", "agent"}


# ---- leads ----------------------------------------------------------------
class LeadBase(Strict):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    phone: str | None = None
    email: EmailStr | None = None
    nationality: str | None = None
    language: str | None = Field(default=None, max_length=8)
    source: str | None = Field(default=None, max_length=32)
    external_id: str | None = Field(default=None, max_length=120)
    campaign: str | None = None
    listing_reference: str | None = None
    purpose: Literal["buy", "rent", "invest"] | None = None
    property_type: str | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    areas: list[str] | None = None
    budget_min_aed: float | None = Field(default=None, ge=0)
    budget_max_aed: float | None = Field(default=None, ge=0)
    timeline: str | None = None
    payment_method: Literal["cash", "mortgage"] | None = None
    assigned_agent_id: str | None = None
    consent_marketing: bool | None = None
    do_not_contact: bool | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = None
    tags: list[str] | None = None
    custom: dict[str, Any] | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return normalize_phone(v)


class LeadCreate(LeadBase):
    stage: Stage = "new"


class LeadPatch(LeadBase):
    stage: Stage | None = None
    lost_reason: str | None = None


class StageMove(Strict):
    stage: Stage
    lost_reason: str | None = None
    note: str | None = None


class NoteIn(Strict):
    kind: Literal["note", "call", "whatsapp", "email", "meeting", "voice_note"] = "note"
    summary: str = Field(min_length=1, max_length=400)
    data: dict[str, Any] = {}
    mark_contacted: bool = True


assert set(PURPOSES) == {"buy", "rent", "invest"}


# ---- integration write-back (AI platform → CRM) ------------------------------
class LeadWriteBack(Strict):
    """Field set the AI agent platform PATCHes. Unknown keys are rejected so a misconfigured connector fails loudly."""

    score: int | None = Field(default=None, ge=0, le=100)
    intent_score: int | None = Field(default=None, ge=0, le=100)
    band: Literal["hot", "warm", "cold"] | None = None
    stage: Stage | None = None
    status: str | None = None
    assigned_broker: str | None = None
    purpose: Literal["buy", "rent", "invest"] | None = None
    timeline: str | None = None
    budget_min_aed: float | None = Field(default=None, ge=0)
    budget_max_aed: float | None = Field(default=None, ge=0)
    area_preference: str | list[str] | None = None
    summary: str | None = Field(default=None, max_length=4000)
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None


class ActivityIn(Strict):
    kind: str = Field(min_length=1, max_length=32)
    summary: str = Field(min_length=1, max_length=400)
    data: dict[str, Any] = {}
    actor_id: str | None = None
    occurred_at: datetime | None = None


# ---- listings ---------------------------------------------------------------
class ListingIn(Strict):
    reference: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=2, max_length=200)
    listing_type: Literal["sale", "rent"] = "sale"
    status: Literal["draft", "live", "under_offer", "sold", "rented", "withdrawn"] = "draft"
    property_type: str = "apartment"
    community: str = Field(min_length=2, max_length=120)
    sub_community: str | None = None
    building: str | None = None
    emirate: str = "Dubai"
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    bathrooms: int | None = Field(default=None, ge=0, le=20)
    size_sqft: float | None = Field(default=None, gt=0)
    price_aed: float = Field(gt=0)
    rent_frequency: Literal["yearly", "monthly"] | None = None
    furnished: str | None = None
    completion_status: Literal["ready", "off_plan"] = "ready"
    handover_date: str | None = None
    developer: str | None = None
    permit_number: str | None = None
    dld_number: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    amenities: list[str] = []
    photos: list[str] = []
    owner_name: str | None = None
    owner_phone: str | None = None
    agent_id: str | None = None
    portals: dict[str, Any] = {}


class ListingPatch(Strict):
    title: str | None = None
    listing_type: Literal["sale", "rent"] | None = None
    status: Literal["draft", "live", "under_offer", "sold", "rented", "withdrawn"] | None = None
    property_type: str | None = None
    community: str | None = None
    sub_community: str | None = None
    building: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    size_sqft: float | None = None
    price_aed: float | None = Field(default=None, gt=0)
    rent_frequency: Literal["yearly", "monthly"] | None = None
    furnished: str | None = None
    completion_status: Literal["ready", "off_plan"] | None = None
    handover_date: str | None = None
    developer: str | None = None
    permit_number: str | None = None
    dld_number: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    amenities: list[str] | None = None
    photos: list[str] | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    agent_id: str | None = None
    portals: dict[str, Any] | None = None
    last_verified_at: datetime | None = None


assert set(LISTING_TYPES) == {"sale", "rent"} and len(LISTING_STATUSES) == 6


# ---- viewings / follow-ups / deals ------------------------------------------
class ViewingIn(Strict):
    lead_id: str
    listing_id: str | None = None
    listing_reference: str | None = None
    agent_id: str | None = None
    scheduled_at: datetime | None = None
    duration_min: int = Field(default=30, ge=10, le=480)
    status: Literal["requested", "confirmed", "done", "no_show", "cancelled"] = "requested"
    location_note: str | None = None
    external_id: str | None = None
    source: str = "crm"


class ViewingPatch(Strict):
    listing_id: str | None = None
    agent_id: str | None = None
    scheduled_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=10, le=480)
    status: Literal["requested", "confirmed", "done", "no_show", "cancelled"] | None = None
    location_note: str | None = None
    feedback: str | None = None


class FollowupIn(Strict):
    lead_id: str
    due_at: datetime
    title: str = Field(min_length=1, max_length=200)
    channel: Literal["call", "whatsapp", "email", "voice_note", "meeting"] = "call"
    note: str | None = None
    agent_id: str | None = None
    external_id: str | None = None


class FollowupPatch(Strict):
    due_at: datetime | None = None
    title: str | None = None
    channel: Literal["call", "whatsapp", "email", "voice_note", "meeting"] | None = None
    note: str | None = None
    agent_id: str | None = None
    status: Literal["open", "done", "skipped"] | None = None


class DealIn(Strict):
    lead_id: str
    listing_id: str | None = None
    agent_id: str | None = None
    deal_type: Literal["sale", "rent"] = "sale"
    status: Literal["offer", "mou", "deposit", "transfer", "closed", "lost"] = "offer"
    offer_aed: float | None = None
    agreed_aed: float | None = None
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    transfer_date: str | None = None
    notes: str | None = None


class DealPatch(Strict):
    listing_id: str | None = None
    agent_id: str | None = None
    status: Literal["offer", "mou", "deposit", "transfer", "closed", "lost"] | None = None
    offer_aed: float | None = None
    agreed_aed: float | None = None
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    mou_signed_at: datetime | None = None
    transfer_date: str | None = None
    notes: str | None = None


assert len(VIEWING_STATUSES) == 5 and len(FOLLOWUP_STATUSES) == 3 and len(DEAL_STATUSES) == 6


# ---- settings -------------------------------------------------------------
class ApiKeyIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = ["leads:read", "leads:write", "listings:read", "viewings:read", "viewings:write", "followups:write", "agents:read"]


class WebhookIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = ["*"]
    active: bool = True


class WebhookPatch(Strict):
    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    active: bool | None = None
    rotate_secret: bool = False
