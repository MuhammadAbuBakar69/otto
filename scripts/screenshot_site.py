"""Screenshot the landing page from site/ (dev only, not needed to run Otto).

    pip install playwright && python -m playwright install chromium
    python scripts/screenshot_site.py

Serves site/ on a free port, captures the hero and the demo section, and writes
docs/site.png. Same playwright requirement as scripts/screenshot.py.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))


def serve(directory: Path, port: int):
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    output = ROOT / "docs" / "site.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    port = 5600
    httpd = serve(SITE, port)
    time.sleep(0.8)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && python -m playwright install chromium")
        return 1

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

        # fill the outbox before taking the picture
        page.click("#run-cycle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(output))

        # console errors are a failure: a blank panel should not ship
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        cards = page.locator("#demo-panel .draft").count()
        decision = page.inner_text('[data-stat="decision"]')
        browser.close()

    if errors:
        raise SystemExit("page errors: " + "; ".join(errors))
    print(f"wrote {output}")
    print(f"demo rendered {cards} draft card(s), decision={decision.strip()}")
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
