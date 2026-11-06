"""Configuration for Otto.

One JSON file (`otto.json`) holds everything that is not a secret. Secrets live
in `.env` and are read from the environment. No YAML, no pydantic, no magic.

    cfg = config.load(".")
    cfg.path("product.name")        # "Bookwell"
    cfg.path("model.provider")      # "none" | "ollama"
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULTS = {
    "product": {
        "name": "Bookwell",
        "one_liner": "online booking for small service businesses",
        "pitch": (
            "We put your calendar, reminders and no-show follow-up in one place, "
            "so the front desk stops chasing texts."
        ),
        "proof": "Shops on Bookwell cut no-shows by about a third in the first month.",
        "cta": "Worth a 10 minute call next week?",
        "url": "https://example.com",
    },
    "sender": {
        "name": "Your Name",
        "email": "",
        "company": "Your Company",
        "postal_address": "",
    },
    "model": {
        # "none" uses Otto's built-in templates: $0, no download, no account.
        # "ollama" uses a local model you already run. Still $0 per token.
        "provider": "none",
        "host": "http://127.0.0.1:11434",
        "name": "llama3.2",
        "timeout": 90,
    },
    "delivery": {
        # "dry_run" never touches a network. "smtp" really sends.
        "mode": "dry_run",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
    },
    "limits": {
        "max_daily_drafts": 20,
        "max_daily_sends": 20,
        "max_profiles_per_cycle": 5,
    },
    "discovery": {
        "source": "csv",
        "csv_path": "prospects.csv",
        "osm_city": "",
        "osm_category": "",
        "osm_limit": 25,
    },
    "replies": {
        "enabled": False,
        "imap_host": "imap.gmail.com",
    },
    "paths": {"data_dir": "data"},
}


class Config(dict):
    """Merged config with dotted-path access."""

    def __init__(self, data, root: Path):
        super().__init__(data)
        self.root = Path(root)

    def path(self, dotted, default=None):
        node = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted, value):
        parts = dotted.split(".")
        node = self
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @property
    def data_dir(self) -> Path:
        raw = Path(self.path("paths.data_dir", "data"))
        directory = raw if raw.is_absolute() else self.root / raw
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def db_path(self) -> Path:
        return self.data_dir / "otto.db"

    @property
    def config_path(self) -> Path:
        return self.root / "otto.json"


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_env(path: Path):
    """Read KEY=value lines from a .env file. Never overrides real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


ENV_MAP = {
    "OTTO_MODEL_PROVIDER": "model.provider",
    "OTTO_MODEL_NAME": "model.name",
    "OTTO_MODEL_HOST": "model.host",
    "OTTO_DELIVERY_MODE": "delivery.mode",
    "OTTO_DATA_DIR": "paths.data_dir",
    "OTTO_SENDER_EMAIL": "sender.email",
    "OTTO_SENDER_NAME": "sender.name",
}


def load(root=".") -> Config:
    root = Path(root).resolve()
    load_env(root / ".env")
    user = {}
    if (root / "otto.json").exists():
        try:
            user = json.loads((root / "otto.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"otto.json is not valid JSON: {exc}") from None
    data = _deep_merge(DEFAULTS, user)
    cfg = Config(data, root)
    for env_key, dotted in ENV_MAP.items():
        value = os.environ.get(env_key)
        if value:
            cfg.set(dotted, value)
    return cfg


def save(cfg: Config):
    cfg.config_path.write_text(
        json.dumps(dict(cfg), indent=2) + "\n", encoding="utf-8"
    )
    return cfg.config_path


def smtp_credentials():
    return os.environ.get("OTTO_SMTP_USER", ""), os.environ.get("OTTO_SMTP_PASSWORD", "")


def imap_credentials():
    return os.environ.get("OTTO_IMAP_USER", ""), os.environ.get("OTTO_IMAP_PASSWORD", "")
