from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session, utcnow
from app.models import ApiKey, User
from app.security import decode_token, hash_api_key

SessionDep = Depends(get_session)


@dataclass
class Principal:
    agency_id: str
    kind: str  # "user" | "api_key"
    id: str
    role: str | None = None
    scopes: tuple[str, ...] = ()
    user: User | None = None

    @property
    def is_manager(self) -> bool:
        return self.role in ("owner", "manager")

    def require(self, scope: str) -> None:
        if self.kind == "api_key" and scope not in self.scopes and "*" not in self.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key lacks scope {scope}")

    def can_edit_all(self) -> bool:
        return self.kind == "api_key" or self.is_manager


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def current_user(request: Request, session: AsyncSession = SessionDep) -> Principal:
    token = _bearer(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from None
    user = await session.get(User, claims.get("sub"))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled")
    return Principal(agency_id=user.agency_id, kind="user", id=user.id, role=user.role, user=user)


async def manager_user(principal: Principal = Depends(current_user)) -> Principal:
    if not principal.is_manager:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner or manager role required")
    return principal


async def api_principal(
    request: Request,
    session: AsyncSession = SessionDep,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    """Integration API auth: ``Authorization: Bearer crm_live_…`` or ``X-API-Key``."""
    raw = _bearer(request) or x_api_key
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key")
    row = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))).scalar_one_or_none()
    if not row or row.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
    row.last_used_at = utcnow()
    await session.commit()
    return Principal(agency_id=row.agency_id, kind="api_key", id=row.id, scopes=tuple(row.scopes or ()))
