"""Central configuration for MAMA AGENT.

Values are read from environment variables first (local ``.env`` file), then from
Streamlit secrets (Streamlit Community Cloud). Nothing secret is hard-coded.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_MODEL = "gemini-flash-lite-latest"


def _get(name: str, default: str = "") -> str:
    """Read a setting from the environment, then from Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:  # no secrets file / not running under Streamlit
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    gemini_api_key: str
    model: str
    app_password: str
    max_steps: int
    log_level: str
    workspace_dir: Path
    db_path: Path
    turso_url: str = ""
    turso_token: str = ""

    @property
    def output_dir(self) -> Path:
        return self.workspace_dir / "output"

    def remote_db(self) -> tuple[str, str] | None:
        """(url, token) of the hosted database when both are set; otherwise None and a local file is used."""
        return (self.turso_url, self.turso_token) if self.turso_url and self.turso_token else None


def get_settings() -> Settings:
    """Build Settings and make sure the workspace folders exist."""
    workspace = Path(_get("WORKSPACE_DIR", str(BASE_DIR / "workspace"))).resolve()
    for sub in ("input", "output", "downloads", "temp"):
        (workspace / sub).mkdir(parents=True, exist_ok=True)
    db_path = Path(_get("DB_PATH", str(BASE_DIR / "data" / "agent.db"))).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        gemini_api_key=_get("GEMINI_API_KEY"),
        model=_get("GEMINI_MODEL", DEFAULT_MODEL),
        app_password=_get("APP_PASSWORD"),
        max_steps=max(1, min(_get_int("MAX_STEPS", 4), 6)),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
        workspace_dir=workspace,
        db_path=db_path,
        turso_url=_get("TURSO_DATABASE_URL"),
        turso_token=_get("TURSO_AUTH_TOKEN"),
    )


def setup_logging(settings: Settings) -> None:
    """Configure console logging once (Streamlit reruns the script often)."""
    root = logging.getLogger()
    if getattr(root, "_mama_configured", False):
        return
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root._mama_configured = True  # type: ignore[attr-defined]
