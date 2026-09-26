"""Deterministic demo data: one Dubai agency, three brokers, listings, leads, viewings, follow-ups.

Run with ``python -m app.seed`` or set ``CRM_DEMO_SEED=1``. Idempotent — skips if the demo agency exists.
Demo logins: owner@demo.ae / agent1@demo.ae / agent2@demo.ae, password ``demo1234``.
"""
from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from sqlalchemy import select

from app.db import init_db, sessionmaker, utcnow
from app.models import Activity, Agency, ApiKey, Followup, Lead, Listing, User, Viewing
from app.security import hash_api_key, hash_password
from app.services.leads import band_for

COMMUNITIES = ["Dubai Marina", "Downtown Dubai", "Palm Jumeirah", "Jumeirah Village Circle", "Business Bay", "Dubai Hills Estate", "Arabian Ranches", "Jumeirah Beach Residence", "Dubai Creek Harbour", "Damac Hills", "Al Furjan", "Mohammed Bin Rashid City"]
FIRST = ["Ahmed", "Fatima", "Omar", "Layla", "Rahul", "Priya", "James", "Sophie", "Chen", "Aisha", "Mohammed", "Elena", "Yusuf", "Natalia", "Daniel", "Zainab"]
LAST = ["Al Mansoori", "Khan", "Sharma", "Smith", "Ivanova", "Haddad", "Patel", "Nguyen", "Rossi", "Al Farsi", "Okafor", "Müller"]
SOURCES = ["property_finder", "bayut", "dubizzle", "meta_ads", "whatsapp", "website", "referral", "walk_in"]
TIMELINES = ["asap", "1-3 months", "3-6 months", "6+ months", "just browsing"]
DEMO_KEY_PLAINTEXT = "crm_live_demo-key-for-local-agent-platform-testing-0000"


async def seed_demo() -> dict[str, str]:
    rng = random.Random(7)
    now = utcnow()
    async with sessionmaker()() as s:
        existing = (await s.execute(select(Agency).where(Agency.slug == "demo-realty"))).scalar_one_or_none()
        if existing:
            return {"agency_id": existing.id, "status": "exists"}
        agency = Agency(name="Demo Realty LLC", slug="demo-realty", rera_orn="12345", trade_license="CN-1234567", phone="+971 4 123 4567", email="hello@demo.ae")
        s.add(agency)
        await s.flush()
        pw = hash_password("demo1234")
        owner = User(agency_id=agency.id, email="owner@demo.ae", full_name="Sara Al Nuaimi", role="owner", rera_brn="30001", password_hash=pw, phone="+971501000001", external_ref="owner")
        a1 = User(agency_id=agency.id, email="agent1@demo.ae", full_name="Karim Haddad", role="agent", rera_brn="30002", password_hash=pw, phone="+971501000002", areas=["Dubai Marina", "Jumeirah Beach Residence", "Palm Jumeirah"], languages=["en", "ar"], external_ref="karim")
        a2 = User(agency_id=agency.id, email="agent2@demo.ae", full_name="Neha Kapoor", role="agent", rera_brn="30003", password_hash=pw, phone="+971501000003", areas=["Downtown Dubai", "Business Bay", "Dubai Hills Estate"], languages=["en", "hi"], external_ref="neha")
        s.add_all([owner, a1, a2])
        await s.flush()
        s.add(ApiKey(agency_id=agency.id, name="AI agent platform (demo)", prefix=DEMO_KEY_PLAINTEXT[:12], key_hash=hash_api_key(DEMO_KEY_PLAINTEXT), scopes=["*"], created_by=owner.id))

        listings: list[Listing] = []
        for i in range(40):
            community = rng.choice(COMMUNITIES)
            sale = rng.random() < 0.65
            beds = rng.choice([0, 1, 1, 2, 2, 3, 4, 5])
            ptype = "villa" if beds >= 4 or community in ("Arabian Ranches", "Damac Hills") else ("townhouse" if beds == 3 and rng.random() < 0.4 else "apartment")
            price = (rng.randint(6, 60) * 100_000 * (1 + beds)) if sale else rng.randint(45, 400) * 1000
            row = Listing(
                agency_id=agency.id, reference=f"DR-{1000 + i}", title=f"{beds or 'Studio'}{' BR' if beds else ''} {ptype} in {community}", listing_type="sale" if sale else "rent", status=rng.choice(["live", "live", "live", "live", "draft", "under_offer"]),
                property_type=ptype, community=community, building=f"{community.split()[0]} Tower {rng.randint(1, 9)}" if ptype == "apartment" else None, bedrooms=beds, bathrooms=max(1, beds), size_sqft=float(rng.randint(450, 900) * (1 + beds)),
                price_aed=float(price), rent_frequency=None if sale else "yearly", completion_status="off_plan" if rng.random() < 0.2 else "ready", permit_number=f"{rng.randint(10**10, 10**11 - 1)}", dld_number=f"DLD-{rng.randint(100000, 999999)}",
                agent_id=rng.choice([a1.id, a2.id]), amenities=rng.sample(["pool", "gym", "parking", "sea view", "maid's room", "balcony", "concierge"], 3), portals={"property_finder": {"listed": True}, "bayut": {"listed": rng.random() < 0.7}},
                last_verified_at=now - timedelta(days=rng.randint(0, 40)),
            )
            listings.append(row)
        s.add_all(listings)
        await s.flush()

        stages = ["new"] * 6 + ["qualifying"] * 5 + ["qualified"] * 4 + ["handed_off"] * 2 + ["viewing_booked"] * 3 + ["offer"] * 1 + ["closed"] * 2 + ["lost"] * 2
        leads: list[Lead] = []
        for i in range(60):
            stage = rng.choice(stages)
            agent = rng.choice([a1, a2, a1, a2, None]) if stage == "new" else rng.choice([a1, a2])
            created = now - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 23))
            purpose = rng.choice(["buy", "buy", "rent", "invest"])
            areas = rng.sample(COMMUNITIES, rng.randint(1, 2))
            score = None if stage == "new" and rng.random() < 0.5 else rng.randint(15, 98)
            lead = Lead(
                agency_id=agency.id, first_name=rng.choice(FIRST), last_name=rng.choice(LAST), phone=f"+9715{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}", email=None if rng.random() < 0.3 else f"lead{i}@example.com",
                nationality=rng.choice(["AE", "IN", "GB", "RU", "PK", "CN", "EG"]), language=rng.choice(["en", "en", "ar", "hi", "ru"]), source=rng.choice(SOURCES), external_id=f"ext-{i:04d}",
                purpose=purpose, property_type=rng.choice(["apartment", "apartment", "villa", "townhouse"]), bedrooms=rng.choice([1, 2, 3, 4]), areas=areas,
                budget_min_aed=float(rng.randint(8, 30) * 100_000) if purpose != "rent" else float(rng.randint(60, 150) * 1000), budget_max_aed=float(rng.randint(30, 80) * 100_000) if purpose != "rent" else float(rng.randint(150, 350) * 1000),
                timeline=rng.choice(TIMELINES), payment_method=rng.choice(["cash", "mortgage", None]), stage=stage, stage_changed_at=created + timedelta(days=rng.randint(0, 5)), assigned_agent_id=agent.id if agent else None,
                ai_score=score, ai_band=band_for(score), ai_scored_at=created + timedelta(hours=1) if score is not None else None, ai_summary=f"Wants a {purpose} in {areas[0]}; {rng.choice(TIMELINES)}." if score else None,
                consent_marketing=True, last_contacted_at=None if stage == "new" else now - timedelta(days=rng.randint(0, 12)), next_follow_up_at=now + timedelta(days=rng.randint(-2, 6)) if stage in ("qualifying", "qualified", "handed_off") else None,
                lost_reason="budget too low" if stage == "lost" else None,
            )
            lead.created_at = created
            lead.updated_at = created + timedelta(hours=rng.randint(1, 72))
            leads.append(lead)
        s.add_all(leads)
        await s.flush()

        for lead in leads:
            s.add(Activity(agency_id=agency.id, lead_id=lead.id, kind="created", summary=f"Lead created from {lead.source}", actor_type="system", created_at=lead.created_at))
            if lead.ai_score is not None:
                s.add(Activity(agency_id=agency.id, lead_id=lead.id, kind="ai_scored", summary=f"AI score {lead.ai_score} ({lead.ai_band})", actor_type="api", data={"score": lead.ai_score}, created_at=lead.created_at + timedelta(hours=1)))
            if lead.stage in ("qualifying", "qualified", "handed_off") and lead.next_follow_up_at:
                s.add(Followup(agency_id=agency.id, lead_id=lead.id, agent_id=lead.assigned_agent_id, due_at=lead.next_follow_up_at, channel=rng.choice(["call", "whatsapp"]), title=f"Follow up on {lead.areas[0]} {lead.purpose}"))
            if lead.stage in ("viewing_booked", "offer", "closed"):
                listing = rng.choice([x for x in listings if x.listing_type == ("rent" if lead.purpose == "rent" else "sale")] or listings)
                s.add(Viewing(agency_id=agency.id, lead_id=lead.id, listing_id=listing.id, agent_id=lead.assigned_agent_id, scheduled_at=now + timedelta(days=rng.randint(-3, 5), hours=rng.randint(9, 18)), status=rng.choice(["requested", "confirmed", "confirmed", "done"]) if lead.stage == "viewing_booked" else "done"))
        await s.commit()
        return {"agency_id": agency.id, "status": "seeded"}


async def _main() -> None:
    await init_db()
    print(await seed_demo())


if __name__ == "__main__":
    asyncio.run(_main())
