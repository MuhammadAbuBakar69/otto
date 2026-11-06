"""The model layer. Two providers, both $0.

    none    -> Otto's built-in templates. No download, no account, no network.
    ollama  -> a model already running on your machine (ollama serve).

There is no third option on purpose: no API keys, no per-token bills, no
subscription. If you cannot run it for free, Otto does not call it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def provider(cfg) -> str:
    return (cfg.path("model.provider") or "none").lower()


def describe(cfg) -> str:
    if provider(cfg) == "ollama":
        return f"ollama:{cfg.path('model.name', 'llama3.2')}"
    return "none (built-in templates)"


def _post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def available(cfg) -> bool:
    """Cheap probe. False means 'use templates', never an error."""
    if provider(cfg) != "ollama":
        return False
    host = cfg.path("model.host", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def generate(cfg, prompt, system=None, timeout=None) -> str:
    """Return raw model text, or '' when the model is not usable."""
    if provider(cfg) != "ollama":
        return ""
    host = cfg.path("model.host", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": cfg.path("model.name", "llama3.2"),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.6},
    }
    if system:
        payload["system"] = system
    try:
        body = _post_json(
            host + "/api/generate", payload, timeout or cfg.path("model.timeout", 90)
        )
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return (body.get("response") or "").strip()


def json_object(text) -> dict:
    """Pull the first {...} block out of model output. {} when it is junk."""
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
