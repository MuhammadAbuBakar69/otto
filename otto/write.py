"""Writing the email.

Two ways to get a draft, same interface:

    template  deterministic, instant, $0, always available
    model     a local model through Ollama, when one is running

Both must clear the same bar: reference something real about the prospect, stay
under 130 words, one ask, no hype. A model that rambles gets replaced by the
template automatically.
"""

from __future__ import annotations

import re

from . import model

MAX_WORDS = 130

SYSTEM = (
    "You write short, plain cold emails for a small business owner. "
    "No hype, no adjectives stacked up, no 'I hope this email finds you well'. "
    "Mention one specific true detail about their business. One ask. Under 120 words. "
    "Reply with JSON only: {\"subject\": ..., \"body\": ...}"
)


def first_name(person_or_company: str) -> str:
    cleaned = re.sub(r"\b(inc|ltd|llc|pvt|co|company|studio|clinic|shop|group)\b\.?", "", person_or_company or "", flags=re.I)
    parts = [p for p in re.split(r"\s+", cleaned.strip()) if p]
    return parts[0] if parts else "there"


def best_detail(facts: dict) -> str:
    """The one concrete thing we can honestly mention."""
    for key in ("description", "title"):
        value = (facts.get(key) or "").strip()
        if 25 <= len(value) <= 240:
            return value.rstrip(".")
    for heading in facts.get("headings") or []:
        if 15 <= len(heading) <= 90:
            return heading.rstrip(".")
    for paragraph in facts.get("paragraphs") or []:
        sentence = re.split(r"(?<=[.!?])\s", paragraph)[0]
        if 25 <= len(sentence) <= 200:
            return sentence.rstrip(".")
    return ""


def template(cfg, prospect, facts) -> tuple:
    """Deterministic draft. Same input, same output, no network."""
    product = cfg.path("product.name", "our product")
    one_liner = cfg.path("product.one_liner", "")
    pitch = cfg.path("product.pitch", "")
    proof = cfg.path("product.proof", "")
    cta = cfg.path("product.cta", "Worth a quick call?")
    sender_name = cfg.path("sender.name", "Your Name")
    city = prospect["city"] or ""
    category = prospect["category"] or "business"
    detail = best_detail(facts or {})

    greeting = f"Hi {first_name(prospect['name'])},"

    hook = f"I came across {prospect['name']}"
    if city:
        hook += f" while looking at {category} in {city}"
    hook += "."

    if detail:
        specificity = f' Your site says "{detail}" - that line stuck with me.'
    else:
        specificity = " There is no marketing language on the site, which I liked."

    body_parts = [
        greeting,
        "",
        hook + specificity,
        "",
        f"I work on {product}, {one_liner}." if one_liner else f"I work on {product}.",
        pitch,
    ]
    if proof:
        body_parts.append(proof)
    body_parts += ["", cta, "", f"- {sender_name}"]
    body = "\n".join(part for part in body_parts if part is not None)

    subject = f"{product} for {prospect['name']}" if product else f"Quick question for {prospect['name']}"
    return subject[:78], trim(body)


def prompt_for(cfg, prospect, facts) -> str:
    detail_lines = []
    if facts.get("title"):
        detail_lines.append(f"Page title: {facts['title']}")
    if facts.get("description"):
        detail_lines.append(f"Meta description: {facts['description']}")
    for heading in (facts.get("headings") or [])[:4]:
        detail_lines.append(f"Heading: {heading}")
    for paragraph in (facts.get("paragraphs") or [])[:2]:
        detail_lines.append(f"Text: {paragraph}")

    return (
        f"Business: {prospect['name']}\n"
        f"Category: {prospect['category'] or 'unknown'}\n"
        f"City: {prospect['city'] or 'unknown'}\n"
        f"Website: {prospect['domain']}\n"
        + "\n".join(detail_lines)
        + "\n\nWhat we sell:\n"
        f"Product: {cfg.path('product.name', '')} - {cfg.path('product.one_liner', '')}\n"
        f"Pitch: {cfg.path('product.pitch', '')}\n"
        f"Proof: {cfg.path('product.proof', '')}\n"
        f"Ask: {cfg.path('product.cta', '')}\n"
        f"Signed by: {cfg.path('sender.name', '')}\n"
    )


def trim(body: str) -> str:
    words = body.split()
    if len(words) <= MAX_WORDS + 40:  # allow the signature and footer
        return body.strip()
    return " ".join(words[:MAX_WORDS]).strip() + "\n\n- " + body.splitlines()[-1].lstrip("- ").strip()


def from_model(cfg, prospect, facts) -> tuple:
    raw = model.generate(cfg, prompt_for(cfg, prospect, facts), system=SYSTEM)
    data = model.json_object(raw)
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not subject or not body:
        return None
    # A model that ignored the brief is worse than the template.
    if len(body.split()) > MAX_WORDS * 2 or "{" in body:
        return None
    return subject[:78], body


def draft(cfg, prospect, facts) -> tuple:
    """Return (subject, body, source). Falls back to the template silently."""
    if model.provider(cfg) == "ollama":
        made = from_model(cfg, prospect, facts)
        if made:
            return made[0], made[1], "model"
    subject, body = template(cfg, prospect, facts)
    return subject, body, "template"
