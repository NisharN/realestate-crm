from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC at millisecond precision, so stored stamps round-trip exactly through ``iso()``
    and changed-since cursors never re-deliver the boundary row."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="milliseconds") + "Z" if dt else None


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine():
    global _engine, _sessionmaker
    if _engine is None:
        cfg = get_settings()
        url = cfg.database_url
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
        elif cfg.environment == "test":
            kwargs = {"poolclass": NullPool}  # asyncpg connections are bound to the event loop that opened them
        else:
            kwargs = {"pool_pre_ping": True}
        _engine = create_async_engine(url, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session


async def init_db(*, drop_first: bool = False) -> None:
    """Dev/test convenience: create tables directly. Production runs ``alembic upgrade head`` instead."""
    from app import models  # noqa: F401  (register tables)

    if get_settings().is_production:
        return
    async with engine().begin() as conn:
        if drop_first:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def reset_engine() -> None:
    """Tests swap DATABASE_URL between runs."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
