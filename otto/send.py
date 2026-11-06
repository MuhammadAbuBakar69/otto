"""Delivering. Dry by default.

    delivery.mode = "dry_run"  -> nothing leaves the machine, ever
    delivery.mode = "smtp"     -> real email, your own mailbox, no ESP, no bill

Every message carries an opt-out line and a postal address because commercial
email legally needs both. If those are not filled in, Otto refuses to send.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from . import config as config_mod
from . import db

PLACEHOLDERS = {"", "your name", "your company", "your@email.com"}


def footer(cfg) -> str:
    company = cfg.path("sender.company", "") or cfg.path("product.name", "")
    address = cfg.path("sender.postal_address", "")
    lines = ["--"]
    if company:
        lines.append(company)
    if address:
        lines.append(address)
    lines.append("Not relevant? Reply 'unsubscribe' and I will not write again.")
    return "\n".join(lines)


def normalize_body(cfg, body: str) -> str:
    """Idempotent: never stack two footers on one message."""
    body = (body or "").strip()
    if body.endswith(footer(cfg)):
        return body
    return body + "\n\n" + footer(cfg)


def readiness(cfg) -> list:
    """What is missing before a real send is legal and possible. [] means ready."""
    problems = []
    user, password = config_mod.smtp_credentials()
    if not cfg.path("sender.email"):
        problems.append("sender.email is empty")
    if not cfg.path("sender.postal_address"):
        problems.append("sender.postal_address is empty (required by anti-spam law)")
    if cfg.path("sender.name", "").lower() in PLACEHOLDERS:
        problems.append("sender.name is still a placeholder")
    if not user or not password:
        problems.append("OTTO_SMTP_USER / OTTO_SMTP_PASSWORD missing from .env")
    return problems


def mode(cfg) -> str:
    return (cfg.path("delivery.mode") or "dry_run").lower()


def compose(cfg, to_email, subject, body) -> EmailMessage:
    sender_email = cfg.path("sender.email", "")
    sender_name = cfg.path("sender.name", "")
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender_email)) if sender_email else sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>"
    msg.set_content(normalize_body(cfg, body))
    return msg


def deliver(cfg, to_email, subject, body) -> tuple:
    """Return (ok, detail). Never raises for network problems."""
    if mode(cfg) != "smtp":
        return True, "dry_run"

    problems = readiness(cfg)
    if problems:
        return False, "; ".join(problems)

    user, password = config_mod.smtp_credentials()
    host = cfg.path("delivery.smtp_host", "smtp.gmail.com")
    port = int(cfg.path("delivery.smtp_port", 465))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(compose(cfg, to_email, subject, body))
        return True, "smtp"
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_approved(cfg, con, limit=None) -> dict:
    """Send every approved draft that has an address. Respects the daily cap."""
    cap = int(cfg.path("limits.max_daily_sends", 20))
    already = db.sent_today(con)
    room = max(0, cap - already)
    if limit is not None:
        room = min(room, limit)

    sent = failed = skipped = 0
    for draft in db.drafts(con, status="approved", limit=200):
        if sent >= room:
            break
        prospect = db.get_prospect(con, draft["prospect_id"])
        if prospect is None or prospect["status"] == "opted_out":
            db.set_draft_status(con, draft["id"], "skipped", error="prospect opted out")
            skipped += 1
            continue
        if not draft["email"]:
            db.set_draft_status(con, draft["id"], "skipped", error="no email address on file")
            skipped += 1
            continue

        ok, detail = deliver(cfg, draft["email"], draft["subject"], draft["body"])
        if ok:
            db.set_draft_status(con, draft["id"], "sent", delivery=detail)
            db.set_status(con, prospect["id"], "sent")
            db.log(con, "sent", prospect["id"], detail)
            sent += 1
        else:
            db.set_draft_status(con, draft["id"], "approved", error=detail)
            db.log(con, "send_failed", prospect["id"], detail)
            failed += 1
            break  # credentials or network problem: stop, do not hammer
    return {"sent": sent, "failed": failed, "skipped": skipped, "cap": cap}
