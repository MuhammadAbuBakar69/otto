"""The heartbeat.

Wake up, count four things, do the most important one, log it, sleep.

The decision is deterministic on purpose. Asking a model "what should I do
next?" spends money to answer a question four SQL counts already answer.
"""

from __future__ import annotations

import json
import time

from . import db, model, replies, send, write
from . import profile as profiler

BANNER = "=" * 62

# Highest priority first. Each one is a count in db.pipeline_counts().
ORDER = ("handle_replies", "send", "write", "profile", "idle")


def decide(counts: dict) -> str:
    if counts.get("unhandled_replies"):
        return "handle_replies"
    if counts.get("approved"):
        return "send"
    if counts.get("ready_to_write"):
        return "write"
    if counts.get("unprofiled"):
        return "profile"
    return "idle"


def profile_pending(cfg, con, limit=None) -> int:
    """Read sites for prospects we know nothing about yet."""
    limit = int(limit or cfg.path("limits.max_profiles_per_cycle", 5))
    done = 0
    for prospect in db.prospects(con, status="new", limit=200):
        if done >= limit:
            break
        facts, ok, error = profiler.profile_domain(prospect["domain"])
        db.save_profile(con, prospect["id"], facts, ok=ok, error=error)
        db.set_status(con, prospect["id"], "profiled" if ok else "failed")
        db.log(con, "profile", prospect["id"], "ok" if ok else error)
        done += 1
    return done


def write_pending(cfg, con, limit=None) -> int:
    """Draft outreach for profiled prospects, under the daily cap."""
    cap = int(cfg.path("limits.max_daily_drafts", 20))
    room = cap - db.drafted_today(con)
    limit = min(int(limit or room or 0), room)
    if limit <= 0:
        return 0

    made = 0
    rows = con.execute(
        """SELECT p.*, f.facts FROM prospects p
           JOIN profiles f ON f.prospect_id = p.id
           WHERE p.status IN ('profiled', 'new') AND f.ok = 1
           ORDER BY p.id LIMIT 200"""
    ).fetchall()
    for prospect in rows:
        if made >= limit:
            break
        if db.has_open_draft(con, prospect["id"]):
            continue
        facts = json.loads(prospect["facts"] or "{}")
        subject, body, source = write.draft(cfg, prospect, facts)
        db.add_draft(con, prospect["id"], subject, send.normalize_body(cfg, body))
        db.set_status(con, prospect["id"], "drafted")
        db.log(con, "draft", prospect["id"], source)
        made += 1
    return made


def cycle(cfg, con, out=print) -> dict:
    """One pass. Cheap work always rides along; the rest is picked by priority."""
    counts = db.pipeline_counts(con)
    action = decide(counts)
    result = {"action": action, "drafted": 0, "sent": 0, "profiled": 0, "answered": 0}

    if cfg.path("replies.enabled"):
        polled = replies.poll(cfg, con)
        if polled:
            out(f"  inbox    -> {polled} new reply(ies)")

    threads = replies.handle_unhandled(cfg, con)
    if threads:
        out(f"  handler  -> {threads} answer(s) drafted for approval")
    result["answered"] = threads

    sent = send.send_approved(cfg, con)
    if sent["sent"] or sent["skipped"]:
        out(f"  outbox   -> {sent['sent']} sent, {sent['skipped']} skipped ({sent['cap']}/day cap)")
    result["sent"] = sent["sent"]

    drafted = write_pending(cfg, con)
    if drafted:
        out(f"  writer   -> {drafted} draft(s) waiting for you")
    result["drafted"] = drafted

    profiled = profile_pending(cfg, con)
    if profiled:
        out(f"  reader   -> {profiled} site(s) read, $0")
    result["profiled"] = profiled

    if not any((threads, sent["sent"], drafted, profiled)):
        out("  idle     -> nothing to do. Add prospects with `otto discover`.")

    db.log(con, "cycle", detail=action)
    result["counts"] = db.pipeline_counts(con)
    return result


def run(cfg, con, interval=900, iterations=None, out=print) -> None:
    """Loop forever (or `iterations` times). Ctrl-C is a clean stop."""
    out(BANNER)
    out(f"Otto is online. Model: {model.describe(cfg)}. Delivery: {send.mode(cfg)}.")
    out(BANNER)
    done = 0
    try:
        while True:
            stamp = time.strftime("%H:%M:%S")
            out(f"\n[{stamp}] cycle")
            result = cycle(cfg, con, out=out)
            out(f"  decision -> {result['action']}")
            done += 1
            if iterations and done >= iterations:
                break
            out(f"  sleeping {interval}s. Ctrl-C to stop.")
            time.sleep(interval)
    except KeyboardInterrupt:
        out("\nstopped.")
