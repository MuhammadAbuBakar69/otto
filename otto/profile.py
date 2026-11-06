"""Read a prospect's website without a model.

Three plain HTTP requests per prospect, $0. Everything here is regex and
`html.parser` from the standard library, so it works offline, in a container,
on a locked-down machine, and with no account anywhere.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "Otto/1.0 (+https://github.com/MuhammadAbuBakar69/otto; human-approved outreach)"
PAGES = ("", "about", "contact")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

# Links and boilerplate that never help personalisation.
NOISE = re.compile(
    r"(cookie|privacy|sign in|log in|subscribe|newsletter|all rights reserved|"
    r"javascript|skip to content)",
    re.IGNORECASE,
)


class _Extractor(HTMLParser):
    """Collect title, meta description, headings and short paragraphs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings = []
        self.paragraphs = []
        self._stack = []
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in ("title", "h1", "h2", "h3", "p"):
            self._stack.append(tag)
            self._buffer = []
        elif tag == "meta":
            attrs = dict(attrs)
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = (attrs.get("content") or "").strip()

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
            text = SPACE_RE.sub(" ", "".join(self._buffer)).strip()
            self._buffer = []
            if not text:
                return
            if tag == "title" and not self.title:
                self.title = text
            elif tag in ("h1", "h2", "h3"):
                self.headings.append(text)
            elif tag == "p":
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self._stack:
            self._buffer.append(data)


def strip_html(raw: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", raw or "")).strip()


def extract(raw_html: str, base_url: str = "") -> dict:
    parser = _Extractor()
    try:
        parser.feed(raw_html or "")
    except Exception:  # html.parser is lenient; never let a page break a cycle
        pass

    headings = [h for h in parser.headings if len(h) <= 90 and not NOISE.search(h)][:6]
    paragraphs = [
        p for p in parser.paragraphs if 40 <= len(p) <= 260 and not NOISE.search(p)
    ][:4]
    emails = sorted({e.lower() for e in EMAIL_RE.findall(raw_html or "")})
    emails = [e for e in emails if not e.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))]

    return {
        "title": parser.title[:160],
        "description": parser.description[:300],
        "headings": headings,
        "paragraphs": paragraphs,
        "emails": emails[:3],
        "base_url": base_url,
    }


def fetch(url: str, timeout=8) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(400_000)
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def profile_domain(domain: str, timeout=8) -> tuple:
    """Return (facts, ok, error). Always returns; never raises."""
    errors = []
    for scheme in ("https://", "http://"):
        base = scheme + domain
        tried = 0
        for page in PAGES:
            url = base + "/" + page
            try:
                raw = fetch(url, timeout=timeout)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                errors.append(f"{url}: {type(exc).__name__}")
                continue
            tried += 1
            facts = extract(raw, url)
            if tried == 1 and not (facts["title"] or facts["description"] or facts["headings"]):
                continue
            facts["domain"] = domain
            return facts, True, ""
    return {"domain": domain}, False, "; ".join(errors[:3]) or "no readable pages"
