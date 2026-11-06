"""Replies.

Read them from your own mailbox over IMAP, classify them with keyword rules (not
a model call), and put an answer in the outbox for approval. Opt-outs are
honoured before anything else happens.
"""

from __future__ import annotations

import email
import imaplib
import re
from email.header import decode_header, make_header
from email.utils import parseaddr

from . import config as config_mod
from . import db
from .write import first_name

OPT_OUT = re.compile(
    r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting)|do not contact|"
    r"don'?t contact|not interested|no thanks|no thank you|wrong person)\b",
    re.I,
)
INTERESTED = re.compile(
    r"\b(interested|tell me more|sounds good|let'?s talk|happy to chat|call me|"
    r"schedule|book a (call|demo|time)|send (me )?(more|details|info)|yes please)\b",
    re.I,
)
OBJECTION = re.compile(
    r"\b(too expensive|price|pricing|cost|budget|already (use|have|work with)|"
    r"not (right )?now|next (quarter|year)|too busy|contract)\b",
    re.I,
)


def classify(subject: str, body: str) -> str:
    text = f"{subject or ''}\n{body or ''}"
    if OPT_OUT.search(text):
        return "unsubscribe"
    if INTERESTED.search(text):
        return "interested"
    if OBJECTION.search(text):
        return "objection"
    if "?" in text:
        return "question"
    return "other"


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except (LookupError, UnicodeDecodeError):
        return value or ""


def _plain_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def _match_prospect(con, sender: str):
    domain = db.normalize_domain(sender)
    if not domain:
        return None
    row = con.execute("SELECT * FROM prospects WHERE domain = ?", (domain,)).fetchone()
    if row:
        return row
    # Fall back to a looser match on the registrable part of the domain.
    parts = domain.split(".")
    if len(parts) >= 2:
        stem = parts[-2]
        return con.execute(
            "SELECT * FROM prospects WHERE domain LIKE ?", (f"%{stem}%",)
        ).fetchone()
    return None


def poll(cfg, con, limit=20) -> int:
    """Pull unseen mail and record replies. Returns how many were new."""
    if not cfg.path("replies.enabled"):
        return 0
    user, password = config_mod.imap_credentials()
    if not user or not password:
        db.log(con, "reply_poll_error", detail="IMAP credentials missing")
        return 0

    host = cfg.path("replies.imap_host", "imap.gmail.com")
    added = 0
    try:
        conn = imaplib.IMAP4_SSL(host, timeout=30)
        conn.login(user, password)
        conn.select("INBOX")
        _typ, data = conn.search(None, "UNSEEN")
        for num in (data[0].split() if data and data[0] else [])[-limit:]:
            _typ, raw = conn.fetch(num, "(RFC822)")
            if not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            sender = parseaddr(msg.get("From", ""))[1]
            subject = _decode(msg.get("Subject"))
            body = _plain_text(msg)[:4000]
            prospect = _match_prospect(con, sender)
            label = classify(subject, body)
            db.add_reply(
                con, prospect["id"] if prospect else None, subject, body, label,
                received_at=msg.get("Date") or None,
            )
            if prospect is not None:
                if label == "unsubscribe":
                    db.set_status(con, prospect["id"], "opted_out")
                else:
                    db.set_status(con, prospect["id"], "replied")
            db.log(con, "reply", prospect["id"] if prospect else None, label)
            added += 1
        conn.logout()
    except (imaplib.IMAP4.error, OSError) as exc:
        db.log(con, "reply_poll_error", detail=f"{type(exc).__name__}: {exc}")
    return added


def _re_subject(reply, product) -> str:
    subject = (reply["subject"] or f"{product}").strip()
    if subject.lower().startswith("re:"):
        return subject
    return "Re: " + subject


def _reply_copy(cfg, reply, prospect) -> tuple:
    name = first_name(prospect["name"]) if prospect else "there"
    product = cfg.path("product.name", "")
    sender = cfg.path("sender.name", "")
    label = reply["classification"]

    if label == "interested":
        subject = _re_subject(reply, product)
        body = (
            f"Hi {name},\n\n"
            f"Good to hear. Two slots that usually work: Tuesday morning or Thursday "
            f"afternoon. Tell me which is easier and I will send an invite.\n\n"
            f"If it helps first, I can send a two minute screen recording instead.\n\n"
            f"- {sender}"
        )
    elif label == "objection":
        subject = _re_subject(reply, product)
        body = (
            f"Hi {name},\n\n"
            f"Fair. Most shops we work with said the same thing before they saw the "
            f"no-show numbers. Happy to send the one page breakdown, no call needed.\n\n"
            f"- {sender}"
        )
    elif label == "question":
        subject = _re_subject(reply, product)
        body = (
            f"Hi {name},\n\n"
            f"Short answer: {cfg.path('product.one_liner', 'happy to explain')}. "
            f"If you want the detail, I can send it over as a one pager.\n\n"
            f"- {sender}"
        )
    else:
        subject = _re_subject(reply, product)
        body = (
            f"Hi {name},\n\n"
            f"Thanks for coming back to me. Should I close the loop here, or is there "
            f"a better time later in the year?\n\n"
            f"- {sender}"
        )
    return subject, body


def handle_unhandled(cfg, con, limit=10) -> int:
    """Turn each unhandled reply into a draft answer. Opt-outs get none."""
    made = 0
    for reply in db.replies(con, unresolved=True, limit=limit):
        if reply["classification"] == "unsubscribe":
            if reply["prospect_id"]:
                db.set_status(con, reply["prospect_id"], "opted_out")
                # Anything already written to them dies here.
                for open_draft in db.drafts(con, status="draft", limit=100):
                    if open_draft["prospect_id"] == reply["prospect_id"]:
                        db.set_draft_status(con, open_draft["id"], "skipped", error="opted out")
            db.mark_reply_handled(con, reply["id"])
            db.log(con, "opted_out", reply["prospect_id"], reply["domain"] or "")
            continue
        if reply["prospect_id"] and db.has_open_draft(con, reply["prospect_id"], kind="reply"):
            db.mark_reply_handled(con, reply["id"])
            continue
        prospect = db.get_prospect(con, reply["prospect_id"]) if reply["prospect_id"] else None
        if prospect is None:
            db.mark_reply_handled(con, reply["id"])
            continue
        subject, body = _reply_copy(cfg, reply, prospect)
        db.add_draft(con, prospect["id"], subject, body, kind="reply")
        db.mark_reply_handled(con, reply["id"])
        db.log(con, "reply_drafted", prospect["id"], reply["classification"])
        made += 1
    return made
