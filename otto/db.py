"""SQLite storage. One file, no server, no migrations folder.

    con = db.connect(cfg.db_path)
    db.add_prospect(con, name="Harbor Dental", domain="harbordental.test")
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    domain      TEXT    NOT NULL UNIQUE,
    email       TEXT    DEFAULT '',
    city        TEXT    DEFAULT '',
    category    TEXT    DEFAULT '',
    source      TEXT    DEFAULT 'csv',
    status      TEXT    NOT NULL DEFAULT 'new',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    prospect_id INTEGER PRIMARY KEY REFERENCES prospects(id) ON DELETE CASCADE,
    facts       TEXT    NOT NULL DEFAULT '{}',
    ok          INTEGER NOT NULL DEFAULT 0,
    error       TEXT    DEFAULT '',
    fetched_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL DEFAULT 'outreach',
    step        INTEGER NOT NULL DEFAULT 1,
    subject     TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'draft',
    delivery    TEXT    DEFAULT '',
    error       TEXT    DEFAULT '',
    created_at  TEXT    NOT NULL,
    sent_at     TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS replies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id    INTEGER REFERENCES prospects(id) ON DELETE SET NULL,
    subject        TEXT    DEFAULT '',
    body           TEXT    DEFAULT '',
    classification TEXT    NOT NULL DEFAULT 'other',
    received_at    TEXT    NOT NULL,
    handled        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,
    prospect_id INTEGER,
    detail      TEXT    DEFAULT '',
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
"""

# Prospect lifecycle.
STATUSES = (
    "new",        # discovered, nothing known yet
    "profiled",   # site read, no draft yet
    "drafted",    # a draft is waiting for approval
    "approved",   # approved, waiting for the next send pass
    "sent",       # handed to the mail server (or to the dry-run log)
    "replied",    # they answered
    "opted_out",  # never contact again
    "skipped",    # you said no thanks
    "failed",     # profile fetch kept failing
)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    con.commit()
    return con


# --- prospects ---------------------------------------------------------------

def add_prospect(con, name, domain, email="", city="", category="", source="csv"):
    """Insert unless the domain already exists. Returns the id either way."""
    domain = normalize_domain(domain)
    if not domain:
        return None
    stamp = now()
    con.execute(
        """INSERT INTO prospects (name, domain, email, city, category, source,
                                  status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)
           ON CONFLICT(domain) DO UPDATE SET
               email = CASE WHEN prospects.email = '' THEN excluded.email
                            ELSE prospects.email END,
               city  = CASE WHEN prospects.city = '' THEN excluded.city
                            ELSE prospects.city END,
               updated_at = excluded.updated_at
           """,
        (name or domain, domain, email or "", city or "", category or "", source, stamp, stamp),
    )
    con.commit()
    row = con.execute("SELECT id FROM prospects WHERE domain = ?", (domain,)).fetchone()
    return row["id"] if row else None


def get_prospect(con, prospect_id):
    return con.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()


def prospects(con, status=None, limit=500):
    if status:
        return con.execute(
            "SELECT * FROM prospects WHERE status = ? ORDER BY id LIMIT ?", (status, limit)
        ).fetchall()
    return con.execute("SELECT * FROM prospects ORDER BY id LIMIT ?", (limit,)).fetchall()


def set_status(con, prospect_id, status):
    con.execute(
        "UPDATE prospects SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), prospect_id),
    )
    con.commit()


def normalize_domain(value) -> str:
    """'https://HarborDental.test/about?x=1' -> 'harbordental.test'"""
    if not value:
        return ""
    text = str(value).strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.split("/")[0].split("?")[0].split("#")[0]
    if text.startswith("www."):
        text = text[4:]
    if "@" in text:
        text = text.split("@")[-1]
    return text.strip(".").strip()


# --- profiles ---------------------------------------------------------------

def save_profile(con, prospect_id, facts, ok=True, error=""):
    con.execute(
        """INSERT INTO profiles (prospect_id, facts, ok, error, fetched_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(prospect_id) DO UPDATE SET
               facts = excluded.facts, ok = excluded.ok,
               error = excluded.error, fetched_at = excluded.fetched_at""",
        (prospect_id, json.dumps(facts or {}), 1 if ok else 0, error, now()),
    )
    con.commit()


def get_profile(con, prospect_id):
    row = con.execute("SELECT * FROM profiles WHERE prospect_id = ?", (prospect_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["facts"] = json.loads(row["facts"] or "{}")
    return data


# --- drafts -----------------------------------------------------------------

def add_draft(con, prospect_id, subject, body, kind="outreach", step=1):
    cur = con.execute(
        """INSERT INTO drafts (prospect_id, kind, step, subject, body, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'draft', ?)""",
        (prospect_id, kind, step, subject, body, now()),
    )
    con.commit()
    return cur.lastrowid


def drafts(con, status=None, limit=100):
    if status:
        return con.execute(
            """SELECT d.*, p.name AS prospect_name, p.domain, p.email
               FROM drafts d JOIN prospects p ON p.id = d.prospect_id
               WHERE d.status = ? ORDER BY d.id DESC LIMIT ?""",
            (status, limit),
        ).fetchall()
    return con.execute(
        """SELECT d.*, p.name AS prospect_name, p.domain, p.email
           FROM drafts d JOIN prospects p ON p.id = d.prospect_id
           ORDER BY d.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def get_draft(con, draft_id):
    return con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()


def set_draft_status(con, draft_id, status, delivery=None, error=None):
    fields, values = ["status = ?"], [status]
    if delivery is not None:
        fields.append("delivery = ?")
        values.append(delivery)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if status == "sent":
        fields.append("sent_at = ?")
        values.append(now())
    values.append(draft_id)
    con.execute(f"UPDATE drafts SET {', '.join(fields)} WHERE id = ?", values)
    con.commit()


def reopen_draft(con, draft_id):
    con.execute(
        "UPDATE drafts SET status = 'draft', error = '', sent_at = '' WHERE id = ?",
        (draft_id,),
    )
    con.commit()


def has_open_draft(con, prospect_id, kind="outreach") -> bool:
    row = con.execute(
        "SELECT 1 FROM drafts WHERE prospect_id = ? AND kind = ? AND status IN "
        "('draft', 'approved') LIMIT 1",
        (prospect_id, kind),
    ).fetchone()
    return row is not None


def sent_today(con, kind=None) -> int:
    today = now()[:10]
    if kind:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'sent' AND sent_at LIKE ? AND kind = ?",
            (today + "%", kind),
        ).fetchone()
    else:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'sent' AND sent_at LIKE ?",
            (today + "%",),
        ).fetchone()
    return row["n"] if row else 0


def drafted_today(con) -> int:
    today = now()[:10]
    row = con.execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()
    return row["n"] if row else 0


# --- replies ----------------------------------------------------------------

def add_reply(con, prospect_id, subject, body, classification, received_at=None):
    cur = con.execute(
        """INSERT INTO replies (prospect_id, subject, body, classification, received_at)
           VALUES (?, ?, ?, ?, ?)""",
        (prospect_id, subject or "", body or "", classification, received_at or now()),
    )
    con.commit()
    return cur.lastrowid


def replies(con, unresolved=False, limit=50):
    query = """SELECT r.*, p.name AS prospect_name, p.domain, p.email
               FROM replies r LEFT JOIN prospects p ON p.id = r.prospect_id"""
    if unresolved:
        query += " WHERE r.handled = 0"
    query += " ORDER BY r.id DESC LIMIT ?"
    return con.execute(query, (limit,)).fetchall()


def mark_reply_handled(con, reply_id):
    con.execute("UPDATE replies SET handled = 1 WHERE id = ?", (reply_id,))
    con.commit()


# --- events -----------------------------------------------------------------

def log(con, kind, prospect_id=None, detail=""):
    con.execute(
        "INSERT INTO events (kind, prospect_id, detail, created_at) VALUES (?, ?, ?, ?)",
        (kind, prospect_id, detail, now()),
    )
    con.commit()


def recent_events(con, limit=20):
    return con.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def pipeline_counts(con) -> dict:
    """The four numbers the heartbeat decides from. No model call needed."""
    return {
        "unhandled_replies": con.execute(
            "SELECT COUNT(*) AS n FROM replies WHERE handled = 0"
        ).fetchone()["n"],
        "approved": con.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'approved'"
        ).fetchone()["n"],
        "awaiting_approval": con.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'draft'"
        ).fetchone()["n"],
        "unprofiled": con.execute(
            "SELECT COUNT(*) AS n FROM prospects p LEFT JOIN profiles f "
            "ON f.prospect_id = p.id WHERE p.status = 'new' AND f.prospect_id IS NULL"
        ).fetchone()["n"],
        "ready_to_write": con.execute(
            "SELECT COUNT(*) AS n FROM prospects p JOIN profiles f ON f.prospect_id = p.id "
            "WHERE p.status = 'profiled' AND f.ok = 1"
        ).fetchone()["n"],
    }
