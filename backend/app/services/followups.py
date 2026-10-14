"""Human-owned follow-up task guardrails."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models import Lead


def validate_channel(lead: Lead, channel: str) -> None:
    preference_channel = "whatsapp" if channel in ("voice_note", "whatsapp_call") else channel
    if lead.outreach_eligible and lead.preferred_contact_channel and channel in ("call", "whatsapp", "whatsapp_call", "voice_note", "email") and preference_channel != lead.preferred_contact_channel:
        raise ValueError(f"use the lead's preferred contact channel ({lead.preferred_contact_channel}) or update their preference first")
    if channel in ("call", "whatsapp", "email", "voice_note", "whatsapp_call") and not lead.outreach_eligible:
        raise ValueError("record marketing consent and clear Do not contact before scheduling outreach")
    if channel == "whatsapp_call" and (lead.do_not_contact or not lead.consent_marketing or not lead.whatsapp_call_consent):
        raise ValueError("record marketing consent and separate WhatsApp call permission before scheduling a WhatsApp call")


def validate_time(lead: Lead, channel: str, due_at: datetime) -> None:
    due = due_at.replace(tzinfo=timezone.utc) if due_at.tzinfo is None else due_at.astimezone(timezone.utc)
    local = due.astimezone(ZoneInfo("Asia/Dubai"))
    hour = local.hour
    if channel in ("call", "whatsapp_call") and not 9 <= hour < 18:
        raise ValueError("schedule marketing calls between 9:00 and 18:00 Dubai time")
    window = (lead.preferred_contact_window or "").casefold()
    intervals = {"morning": (9, 12), "afternoon": (12, 17), "evening": (17, 20)}
    interval = intervals.get(window)
    if interval and not interval[0] <= hour < interval[1]:
        raise ValueError(f"schedule within the lead's preferred {window} contact window")
    if interval and channel in ("call", "whatsapp_call") and window == "evening" and hour >= 18:
        raise ValueError("marketing calls must be scheduled before 18:00 Dubai time")
