"""Outbound webhooks: durable delivery rows + HMAC-signed POSTs with exponential retry.

``emit()`` only writes ``webhook_deliveries`` rows; ``deliver_pending()`` sends them.
The app schedules ``deliver_pending`` after each request (BackgroundTasks) and a
periodic sweeper retries failures, so a slow subscriber never blocks an API call.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import socket
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import sessionmaker, utcnow
from app.models import Webhook, WebhookDelivery
from app.security import sign

logger = logging.getLogger(__name__)
BACKOFF_S = (30, 120, 600, 1800, 3600)


def validate_webhook_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("webhook URL must be an absolute http(s) URL")
    if parts.scheme == "http" and not get_settings().allow_private_webhook_hosts:
        raise ValueError("webhook URL must use https")
    if not get_settings().allow_private_webhook_hosts:
        try:
            infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise ValueError("webhook host does not resolve") from None
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise ValueError("webhook host resolves to a non-public address")
    return url


def _matches(webhook: Webhook, event: str) -> bool:
    subs = webhook.events or []
    return "*" in subs or event in subs or any(s.endswith(".*") and event.startswith(s[:-1]) for s in subs)


async def emit(session: AsyncSession, agency_id: str, event: str, payload: dict[str, Any]) -> int:
    hooks = (await session.execute(select(Webhook).where(Webhook.agency_id == agency_id, Webhook.active.is_(True)))).scalars().all()
    n = 0
    for hook in hooks:
        if _matches(hook, event):
            session.add(WebhookDelivery(agency_id=agency_id, webhook_id=hook.id, event=event, payload=payload))
            n += 1
    return n


def _body(delivery: WebhookDelivery) -> bytes:
    return json.dumps({"id": delivery.id, "event": delivery.event, "created_at": delivery.created_at.isoformat() + "Z", **delivery.payload}, separators=(",", ":"), default=str).encode("utf-8")


async def deliver_pending(*, limit: int = 50, client: httpx.AsyncClient | None = None) -> dict[str, int]:
    settings = get_settings()
    sent = failed = 0
    async with sessionmaker()() as session:
        rows = (
            await session.execute(
                select(WebhookDelivery).where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= utcnow()).order_by(WebhookDelivery.created_at).limit(limit)
            )
        ).scalars().all()
        own_client = client is None
        client = client or httpx.AsyncClient(timeout=settings.webhook_timeout_s, trust_env=False, follow_redirects=False)
        try:
            for d in rows:
                hook = await session.get(Webhook, d.webhook_id)
                if not hook or not hook.active:
                    d.status, d.error = "failed", "webhook removed or paused"
                    continue
                body = _body(d)
                headers = {"Content-Type": "application/json", "X-Signature-256": sign(hook.secret, body), "X-Event": d.event, "X-Delivery-Id": d.id, "User-Agent": "realestate-crm-webhooks/1"}
                d.attempts += 1
                try:
                    resp = await client.post(hook.url, content=body, headers=headers)
                    d.response_status = resp.status_code
                    ok = resp.status_code < 300
                    d.error = None if ok else f"HTTP {resp.status_code}"
                except httpx.HTTPError as exc:
                    ok, d.response_status, d.error = False, None, type(exc).__name__
                hook.last_delivery_at, hook.last_status = utcnow(), d.response_status
                if ok:
                    d.status, hook.failure_count = "delivered", 0
                    sent += 1
                else:
                    hook.failure_count += 1
                    if d.attempts >= settings.webhook_max_attempts:
                        d.status = "failed"
                        failed += 1
                    else:
                        d.next_attempt_at = utcnow() + timedelta(seconds=BACKOFF_S[min(d.attempts - 1, len(BACKOFF_S) - 1)])
            await session.commit()
        finally:
            if own_client:
                await client.aclose()
    return {"sent": sent, "failed": failed, "pending": len(rows) - sent - failed}


async def deliver_soon() -> None:
    if not get_settings().webhook_inline_delivery:
        return
    try:
        await deliver_pending()
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook delivery sweep failed: %s", type(exc).__name__)
