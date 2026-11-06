"""Demo mode: invented data, no network, no credentials.

`python -m otto demo` fills a throwaway database with six fictional businesses on
`.test` domains so you can see the whole loop and the dashboard in ten seconds.
"""

from __future__ import annotations

from . import db, send, write

DEMO = [
    {
        "name": "Harbor Dental Studio",
        "domain": "harbordental.test",
        "email": "hello@harbordental.test",
        "city": "Karachi",
        "category": "dentist",
        "facts": {
            "title": "Harbor Dental Studio | Family dentistry in Clifton",
            "description": "Same-week appointments, evening slots and a hygiene plan for families.",
            "headings": ["Evening appointments", "Hygiene plans"],
            "paragraphs": ["We keep two evening slots open every day for people who cannot take time off work."],
        },
    },
    {
        "name": "Highline Roofing",
        "domain": "highlineroofing.test",
        "email": "office@highlineroofing.test",
        "city": "Karachi",
        "category": "roofer",
        "facts": {
            "title": "Highline Roofing",
            "description": "Flat roof repairs and waterproofing for commercial buildings since 1998.",
            "headings": ["Waterproofing", "Emergency repairs"],
            "paragraphs": ["We answer emergency calls within four hours, seven days a week."],
        },
    },
    {
        "name": "Phoenix HVAC",
        "domain": "phoenixhvac.test",
        "email": "dispatch@phoenixhvac.test",
        "city": "Karachi",
        "category": "hvac",
        "facts": {
            "title": "Phoenix HVAC - installation and servicing",
            "description": "Commercial air conditioning installs, plus a maintenance contract that includes two services a year.",
            "headings": ["Maintenance contracts"],
            "paragraphs": ["Our dispatcher books every job from a paper diary and two phone lines."],
        },
    },
    {
        "name": "Terrace Bistro",
        "domain": "terracebistro.test",
        "email": "team@terracebistro.test",
        "city": "Lahore",
        "category": "restaurant",
        "facts": {
            "title": "Terrace Bistro",
            "description": "A twenty seat room, a short menu that changes weekly, walk-ins welcome.",
            "headings": ["This week's menu"],
            "paragraphs": ["We take reservations by phone only, from eleven in the morning."],
        },
    },
    {
        "name": "Northline Physio",
        "domain": "northlinephysio.test",
        "email": "reception@northlinephysio.test",
        "city": "Islamabad",
        "category": "physiotherapist",
        "facts": {
            "title": "Northline Physio | Sports injury rehab",
            "description": "Rehabilitation for runners and cyclists, with gait analysis on site.",
            "headings": ["Gait analysis"],
            "paragraphs": ["We run six clinics a week and lose a third of them to no-shows."],
        },
    },
    {
        "name": "Cedar Lane Garage",
        "domain": "cedarlanegarage.test",
        "email": "workshop@cedarlanegarage.test",
        "city": "Karachi",
        "category": "car_repair",
        "facts": {
            "title": "Cedar Lane Garage",
            "description": "Servicing and MOT prep for family cars, loan car available.",
            "headings": ["Book a service"],
            "paragraphs": ["Most of our bookings come through WhatsApp messages that nobody answers until lunch."],
        },
    },
]


def seed(cfg, con, out=print) -> dict:
    created = 0
    for entry in DEMO:
        prospect_id = db.add_prospect(
            con,
            name=entry["name"],
            domain=entry["domain"],
            email=entry["email"],
            city=entry["city"],
            category=entry["category"],
            source="demo",
        )
        if not prospect_id:
            continue
        created += 1
        db.save_profile(con, prospect_id, entry["facts"], ok=True)
        db.set_status(con, prospect_id, "profiled")

    drafted = 0
    for prospect in db.prospects(con, status="profiled", limit=50):
        if prospect["source"] != "demo":
            continue
        facts = db.get_profile(con, prospect["id"])["facts"]
        subject, body, source = write.draft(cfg, prospect, facts)
        db.add_draft(con, prospect["id"], subject, send.normalize_body(cfg, body))
        db.set_status(con, prospect["id"], "drafted")
        drafted += 1

    # One conversation already in flight, one hard no.
    first = db.prospects(con, status="drafted", limit=5)
    if len(first) >= 1:
        db.add_reply(
            con,
            first[0]["id"],
            f"Re: {cfg.path('product.name', 'Bookwell')} for {first[0]['name']}",
            "Thanks for the note. We lose a lot of evening bookings to no-shows. "
            "What does it cost per month, and can we try it on one chair first?",
            "interested",
        )
        db.set_status(con, first[0]["id"], "replied")
    if len(first) >= 2:
        db.add_reply(
            con,
            first[1]["id"],
            "Re: quick question",
            "Please take me off this list. Not interested.",
            "unsubscribe",
        )
        db.set_status(con, first[1]["id"], "opted_out")

    db.log(con, "demo", detail=f"{created} prospects, {drafted} drafts")
    out(f"Demo data ready: {created} prospects, {drafted} drafts, 2 replies.")
    return {"prospects": created, "drafts": drafted}
