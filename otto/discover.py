"""Find businesses to talk to, for $0.

Two sources, both free and keyless:

    csv  -> prospects.csv you wrote yourself (works with no internet)
    osm  -> OpenStreetMap / Overpass, public and account-free

No Apollo, no ZoomInfo, no scraping of contact databases. If a source wants a
credit card, it does not belong here.
"""

from __future__ import annotations

import csv
import json
import urllib.error
import urllib.parse
import urllib.request

from . import db

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Otto/1.0 (open-source outreach agent; human-approved sends)"

CSV_COLUMNS = ("name", "domain", "email", "city", "category")


def from_csv(con, path) -> int:
    """Read name,domain,email,city,category. Header optional. Returns rows added."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from None
    if not text.strip():
        return 0

    rows = list(csv.reader(text.splitlines()))
    if rows and not set(c.strip().lower() for c in rows[0]) & set(CSV_COLUMNS):
        rows.insert(0, list(CSV_COLUMNS))

    header = [c.strip().lower() for c in rows[0]]
    added = 0
    for row in rows[1:]:
        record = {header[i]: (row[i].strip() if i < len(row) else "") for i in range(len(header))}
        domain = db.normalize_domain(record.get("domain") or record.get("website") or "")
        if not domain:
            continue
        db.add_prospect(
            con,
            name=record.get("name") or domain,
            domain=domain,
            email=record.get("email", ""),
            city=record.get("city", ""),
            category=record.get("category", ""),
            source="csv",
        )
        added += 1
    db.log(con, "discover", detail=f"csv:{added}")
    return added


def osm_query(city: str, category: str, limit: int) -> str:
    """Overpass QL: businesses in a city area that publish a website."""
    tag_filters = []
    if category:
        safe = category.replace('"', "")
        tag_filters = [f'["amenity"="{safe}"]', f'["shop"="{safe}"]', f'["office"="{safe}"]']
    else:
        tag_filters = ['["shop"]', '["amenity"]', '["office"]']
    area_name = city.replace('"', "")
    body = ""
    for tag in tag_filters:
        body += (
            f'nwr{tag}(area.searchArea)["website"];\n'
            f'nwr{tag}(area.searchArea)["contact:website"];\n'
        )
    return (
        "[out:json][timeout:60];\n"
        f'area["name"="{area_name}"]["boundary"="administrative"]->.searchArea;\n'
        "(\n" + body + ");\n"
        f"out tags {int(limit)};\n"
    )


def from_osm(con, city, category="", limit=25, timeout=90) -> int:
    if not city:
        raise SystemExit("Set discovery.osm_city (or pass --city) to use the OSM source.")
    query = osm_query(city, category, limit)
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS, data=data, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            f"OpenStreetMap lookup failed ({type(exc).__name__}). Try the csv source."
        ) from None

    added = 0
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        website = tags.get("website") or tags.get("contact:website") or ""
        domain = db.normalize_domain(website)
        if not domain:
            continue
        db.add_prospect(
            con,
            name=tags.get("name") or domain,
            domain=domain,
            email=tags.get("email") or tags.get("contact:email") or "",
            city=tags.get("addr:city") or city,
            category=category or tags.get("shop") or tags.get("amenity") or tags.get("office") or "",
            source="osm",
        )
        added += 1
    db.log(con, "discover", detail=f"osm:{added}")
    return added


def discover(con, cfg, source=None, city=None, category=None, csv_path=None) -> int:
    source = (source or cfg.path("discovery.source", "csv")).lower()
    if source == "osm":
        return from_osm(
            con,
            city or cfg.path("discovery.osm_city", ""),
            category or cfg.path("discovery.osm_category", ""),
            int(cfg.path("discovery.osm_limit", 25)),
        )
    path = csv_path or cfg.path("discovery.csv_path", "prospects.csv")
    if not str(path).startswith("/"):
        path = cfg.root / path
    return from_csv(con, path)
