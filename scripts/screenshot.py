"""Regenerate docs/dashboard.png from a live dashboard.

The only tool in this repo that needs an install, and only for you:

    pip install playwright && python -m playwright install chromium
    python scripts/screenshot.py

It seeds the demo data into a throwaway directory, starts the dashboard on a
free port, screenshots it, and prints where the image landed. Nothing touches
your real data/otto.db.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))

from otto import config, dashboard, db, demo, pipeline  # noqa: E402


def main() -> int:
    output = ROOT / "docs" / "dashboard.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    cfg = config.load(ROOT)
    cfg.set("paths.data_dir", tempfile.mkdtemp(prefix="otto-shot-"))
    con = db.connect(cfg.db_path)
    demo.seed(cfg, con, out=print)
    pipeline.cycle(cfg, con, out=print)  # fills the outbox and drafts one answer

    port = 5599
    server = threading.Thread(
        target=dashboard.serve,
        args=(cfg, con),
        kwargs={"port": port, "out": print},
        daemon=True,
    )
    server.start()
    time.sleep(1.5)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && python -m playwright install chromium")
        return 1

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(output), full_page=True)
        browser.close()

    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
