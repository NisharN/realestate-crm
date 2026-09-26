from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["CRM_DATABASE_URL"] = "sqlite+aiosqlite:///./test_crm.db"
os.environ["CRM_ALLOW_PRIVATE_WEBHOOK_HOSTS"] = "1"
os.environ["CRM_JWT_SECRET"] = "test-secret-not-for-prod-0123456789abcdef"
os.environ["CRM_WEBHOOK_INLINE_DELIVERY"] = "0"

from app.config import get_settings  # noqa: E402
from app.db import init_db, reset_engine  # noqa: E402
from app.main import create_app  # noqa: E402

get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _db():
    if os.path.exists("test_crm.db"):
        os.remove("test_crm.db")
    await init_db()
    yield
    await reset_engine()


@pytest_asyncio.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class Tenant:
    def __init__(self, token: str, agency_id: str, user_id: str, email: str):
        self.token, self.agency_id, self.user_id, self.email = token, agency_id, user_id, email

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def register(client: AsyncClient, name: str | None = None) -> Tenant:
    tag = uuid.uuid4().hex[:8]
    r = await client.post("/api/auth/register", json={"agency_name": name or f"Agency {tag}", "full_name": "Owner", "email": f"owner-{tag}@example.com", "password": "password123", "rera_orn": "1234"})
    assert r.status_code == 201, r.text
    d = r.json()
    return Tenant(d["token"], d["agency"]["id"], d["user"]["id"], d["user"]["email"])


async def api_key(client: AsyncClient, t: Tenant, scopes: list[str] | None = None) -> str:
    r = await client.post("/api/settings/api-keys", json={"name": "agent", "scopes": scopes or ["*"]}, headers=t.h)
    assert r.status_code == 201, r.text
    return r.json()["plaintext"]


@pytest_asyncio.fixture
async def tenant(client) -> Tenant:
    return await register(client)


@pytest_asyncio.fixture
async def other(client) -> Tenant:
    return await register(client)


@pytest.fixture
def lead_payload():
    tag = uuid.uuid4().hex[:6]
    return {"first_name": "Ahmed", "last_name": "Khan", "phone": f"05{uuid.uuid4().int % 10**8:08d}", "email": f"ahmed-{tag}@example.com", "source": "property_finder", "external_id": f"pf-{tag}", "purpose": "buy", "areas": ["Palm Jumeirah"], "budget_max_aed": 3_000_000}
