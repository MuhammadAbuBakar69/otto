"""Command line. Ten small commands, no framework.

    python -m otto demo        # see it work in ten seconds
    python -m otto run         # the heartbeat, every 15 minutes
    python -m otto dashboard   # the outbox on 127.0.0.1:5555
"""

from __future__ import annotations

import argparse
import sys

from . import config as config_mod
from . import dashboard, db, demo, discover, model, pipeline, send


def _open(cfg):
    return db.connect(cfg.db_path)


def cmd_init(args):
    cfg = config_mod.load(".")
    if cfg.config_path.exists() and not args.force:
        print(f"{cfg.config_path} already exists (use --force to rewrite).")
    else:
        config_mod.save(cfg)
        print(f"wrote {cfg.config_path}")
    print("\nnext:")
    print("  1. edit otto.json    -> your product, your name, your postal address")
    print("  2. python -m otto demo       (no network, no account)")
    print("  3. python -m otto dashboard  (approve drafts in the browser)")
    return 0


def cmd_doctor(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    print("otto doctor")
    print("-" * 46)
    print(f"python        {sys.version.split()[0]}")
    print(f"root          {cfg.root}")
    print(f"database      {cfg.db_path}")
    print(f"model         {model.describe(cfg)}")
    if model.provider(cfg) == "ollama":
        print(f"model online  {'yes' if model.available(cfg) else 'no - templates will be used'}")
    print(f"delivery      {send.mode(cfg)}")
    problems = send.readiness(cfg)
    if send.mode(cfg) == "smtp" and problems:
        print("send blocked  " + "; ".join(problems))
    elif send.mode(cfg) == "smtp":
        print("send ready    yes")
    else:
        print("send ready    n/a (dry_run: nothing leaves this machine)")
    counts = db.pipeline_counts(con)
    print("pipeline      " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"discovery     {cfg.path('discovery.source')} "
          f"({cfg.path('discovery.csv_path') if cfg.path('discovery.source') == 'csv' else cfg.path('discovery.osm_city') or 'no city set'})")
    return 0


def cmd_status(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    counts = db.pipeline_counts(con)
    print("pipeline")
    for key, value in counts.items():
        print(f"  {key:<20} {value}")
    print("\nrecent")
    for event in db.recent_events(con, limit=args.limit):
        print(f"  {event['created_at'][11:19]}  {event['kind']:<14} {event['detail']}")
    return 0


def cmd_demo(args):
    cfg = config_mod.load(".")
    if args.reset:
        db.connect(cfg.db_path).close()
        if cfg.db_path.exists():
            cfg.db_path.unlink()
    con = _open(cfg)
    demo.seed(cfg, con)
    print("\nmodel in use: " + model.describe(cfg))
    print("next: python -m otto dashboard")
    return 0


def cmd_discover(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    added = discover.discover(
        con, cfg, source=args.source, city=args.city,
        category=args.category, csv_path=args.csv,
    )
    print(f"{added} prospect(s) read from source={args.source or cfg.path('discovery.source')}")
    return 0


def cmd_profile(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    done = pipeline.profile_pending(cfg, con, limit=args.limit)
    print(f"{done} site(s) read")
    return 0


def cmd_write(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    made = pipeline.write_pending(cfg, con, limit=args.limit)
    print(f"{made} draft(s) created -> review with `python -m otto dashboard`")
    return 0


def cmd_send(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    if send.mode(cfg) != "smtp":
        print("delivery.mode is dry_run: nothing will leave this machine.")
        print("Set OTTO_DELIVERY_MODE=smtp and fill .env when you are ready.")
    result = send.send_approved(cfg, con, limit=args.limit)
    print(f"sent={result['sent']} failed={result['failed']} skipped={result['skipped']} cap={result['cap']}")
    return 0


def cmd_run(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    pipeline.run(cfg, con, interval=args.interval, iterations=args.once or None)
    return 0


def cmd_dashboard(args):
    cfg = config_mod.load(".")
    con = _open(cfg)
    dashboard.serve(cfg, con, port=args.port)
    return 0


def cmd_reset(args):
    cfg = config_mod.load(".")
    if not args.yes:
        print(f"this deletes {cfg.db_path}. re-run with --yes")
        return 1
    if cfg.db_path.exists():
        cfg.db_path.unlink()
    print("database deleted")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="otto",
        description="Autonomous outreach agent with a $0 model bill.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="write otto.json with sane defaults")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("doctor", help="check the install before a run")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("status", help="counts and recent events")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("demo", help="fill a throwaway database with invented data")
    p.add_argument("--reset", action="store_true", help="delete the existing database first")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("discover", help="find prospects (csv or OpenStreetMap)")
    p.add_argument("--source", choices=["csv", "osm"])
    p.add_argument("--csv")
    p.add_argument("--city")
    p.add_argument("--category")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("profile", help="read prospect websites")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("write", help="draft outreach for profiled prospects")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_write)

    p = sub.add_parser("send", help="send approved drafts")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("run", help="the heartbeat loop")
    p.add_argument("--interval", type=int, default=900, help="seconds between cycles")
    p.add_argument("--once", action="store_true", help="one cycle, then exit")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("dashboard", help="local outbox UI")
    p.add_argument("--port", type=int)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("reset", help="delete the local database")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_reset)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args) or 0
