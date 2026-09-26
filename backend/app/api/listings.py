from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import serializers
from app.db import utcnow
from app.deps import Principal, SessionDep, current_user
from app.models import Listing
from app.schemas import ListingIn, ListingPatch
from app.services.leads import log
from app.services.webhooks import deliver_soon, emit

router = APIRouter(prefix="/listings", tags=["listings"])


async def load_listing(session: AsyncSession, agency_id: str, listing_id: str) -> Listing:
    row = (await session.execute(select(Listing).where(Listing.id == listing_id, Listing.agency_id == agency_id, Listing.deleted_at.is_(None)))).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "listing not found")
    return row


@router.get("")
async def list_listings(
    principal: Principal = Depends(current_user),
    session: AsyncSession = SessionDep,
    q: str | None = Query(default=None, max_length=80),
    status_: str | None = Query(default=None, alias="status"),
    listing_type: str | None = None,
    community: str | None = None,
    agent_id: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    bedrooms: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    query = select(Listing).where(Listing.agency_id == principal.agency_id, Listing.deleted_at.is_(None))
    if status_:
        query = query.where(Listing.status == status_)
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)
    if community:
        query = query.where(func.lower(Listing.community) == community.lower())
    if agent_id:
        query = query.where(Listing.agent_id == agent_id)
    if min_price is not None:
        query = query.where(Listing.price_aed >= min_price)
    if max_price is not None:
        query = query.where(Listing.price_aed <= max_price)
    if bedrooms is not None:
        query = query.where(Listing.bedrooms == bedrooms)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Listing.title).like(like), func.lower(Listing.reference).like(like), func.lower(Listing.community).like(like), func.lower(Listing.building).like(like)))
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await session.execute(query.order_by(Listing.updated_at.desc()).limit(limit).offset(offset))).scalars().all()
    ser = serializers.listing_private if principal.is_manager else serializers.listing
    return {"items": [ser(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/stale")
async def stale(principal: Principal = Depends(current_user), session: AsyncSession = SessionDep, days: int = Query(default=14, ge=1, le=365)) -> dict:
    """Live listings nobody verified recently — the ones portals will penalise."""
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=days)
    rows = (await session.execute(select(Listing).where(Listing.agency_id == principal.agency_id, Listing.deleted_at.is_(None), Listing.status == "live", or_(Listing.last_verified_at.is_(None), Listing.last_verified_at < cutoff)).order_by(Listing.last_verified_at.asc().nulls_first()).limit(200))).scalars().all()
    return {"items": [serializers.listing(r) for r in rows], "days": days}


@router.post("", status_code=201)
async def create_listing(body: ListingIn, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    dup = (await session.execute(select(Listing.id).where(Listing.agency_id == principal.agency_id, Listing.reference == body.reference))).scalar_one_or_none()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "a listing with this reference already exists")
    row = Listing(agency_id=principal.agency_id, **body.model_dump())
    if row.agent_id is None:
        row.agent_id = principal.id
    session.add(row)
    await session.flush()
    log(session, principal.agency_id, lead_id=None, listing_id=row.id, kind="listing_created", summary=f"Listing {row.reference} created", actor_type="user", actor_id=principal.id)
    await emit(session, principal.agency_id, "listing.created", {"listing": serializers.listing(row)})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"listing": serializers.listing_private(row)}


@router.get("/{listing_id}")
async def get_listing(listing_id: str, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await load_listing(session, principal.agency_id, listing_id)
    return {"listing": serializers.listing_private(row) if principal.is_manager or row.agent_id == principal.id else serializers.listing(row)}


@router.patch("/{listing_id}")
async def patch_listing(listing_id: str, body: ListingPatch, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await load_listing(session, principal.agency_id, listing_id)
    if not principal.is_manager and row.agent_id not in (None, principal.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this listing belongs to another agent")
    data = body.model_dump(exclude_unset=True)
    changed = []
    for key, value in data.items():
        if key == "last_verified_at" and value is not None:
            value = value.replace(tzinfo=None)
        if getattr(row, key) != value:
            setattr(row, key, value)
            changed.append(key)
    if "status" in changed:
        log(session, principal.agency_id, lead_id=None, listing_id=row.id, kind="listing_status", summary=f"Listing {row.reference} → {row.status}", actor_type="user", actor_id=principal.id)
    if changed:
        await emit(session, principal.agency_id, "listing.updated", {"listing": serializers.listing(row), "changed": changed})
    await session.commit()
    tasks.add_task(deliver_soon)
    return {"listing": serializers.listing_private(row), "changed": changed}


@router.post("/{listing_id}/verify")
async def verify_listing(listing_id: str, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep) -> dict:
    row = await load_listing(session, principal.agency_id, listing_id)
    row.last_verified_at = utcnow()
    log(session, principal.agency_id, lead_id=None, listing_id=row.id, kind="listing_verified", summary=f"Listing {row.reference} verified as still available", actor_type="user", actor_id=principal.id)
    await session.commit()
    return {"listing": serializers.listing(row)}


@router.delete("/{listing_id}", status_code=204, response_class=Response)
async def delete_listing(listing_id: str, tasks: BackgroundTasks, principal: Principal = Depends(current_user), session: AsyncSession = SessionDep):
    row = await load_listing(session, principal.agency_id, listing_id)
    if not principal.is_manager and row.agent_id != principal.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this listing belongs to another agent")
    row.deleted_at = utcnow()
    await emit(session, principal.agency_id, "listing.deleted", {"listing": {"id": row.id, "reference": row.reference}})
    await session.commit()
    tasks.add_task(deliver_soon)
