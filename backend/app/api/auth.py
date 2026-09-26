from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.deps import Principal, SessionDep, current_user
from app.models import Agency, User
from app.schemas import Login, RegisterAgency
from app.security import hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "agency"


@router.post("/register", status_code=201)
async def register(body: RegisterAgency, session: AsyncSession = SessionDep) -> dict:
    """Create an agency and its owner account. Meant for first-run / self-serve signup."""
    email = body.email.lower()
    taken = (await session.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this e-mail already exists")
    base = _slug(body.agency_name)
    slug, n = base, 1
    while (await session.execute(select(Agency.id).where(Agency.slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{base}-{n}"
    agency = Agency(name=body.agency_name, slug=slug, rera_orn=body.rera_orn, phone=body.phone, email=email)
    session.add(agency)
    await session.flush()
    owner = User(agency_id=agency.id, email=email, full_name=body.full_name, role="owner", phone=body.phone, password_hash=hash_password(body.password))
    session.add(owner)
    await session.commit()
    return {"token": issue_token(owner.id, agency.id, owner.role), "user": serializers.user(owner), "agency": serializers.agency(agency)}


@router.post("/login")
async def login(body: Login, session: AsyncSession = SessionDep) -> dict:
    user = (await session.execute(select(User).where(func.lower(User.email) == body.email.lower()))).scalar_one_or_none()
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid e-mail or password")
    agency = await session.get(Agency, user.agency_id)
    return {"token": issue_token(user.id, user.agency_id, user.role), "user": serializers.user(user), "agency": serializers.agency(agency) if agency else None}


@router.get("/me")
async def me(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    agency = await session.get(Agency, principal.agency_id)
    assert principal.user is not None
    return {"user": serializers.user(principal.user), "agency": serializers.agency(agency) if agency else None}
