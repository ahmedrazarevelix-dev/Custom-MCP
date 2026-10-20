"""Configuration: reads settings from the environment, optionally via a .env file.

Priority (highest first):
1. Real environment variables (e.g. the "env" block in claude_desktop_config.json)
2. A ``.env`` file in the project root (the folder containing pyproject.toml)
3. A ``.env`` file found in the current working directory

``.env`` is for local development and is git-ignored. Only ``.env.example``
(with placeholder values) is committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
    
from dotenv import find_dotenv, load_dotenv

ENV_EXPORT_DIR = "LINKEDIN_EXPORT_DIR"

# config.py -> linkedin_mcp -> src -> <project root>
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    export_dir: Path
    log_level: str = "INFO"


def load_env_files() -> None:
    """Load .env files without overriding variables that are already set."""
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    cwd_env = find_dotenv(usecwd=True)
    if cwd_env:
        load_dotenv(cwd_env, override=False)


def load_settings() -> Settings:
    load_env_files()
    raw = os.environ.get(ENV_EXPORT_DIR, "").strip()
    if not raw:
        raise ConfigError(
            f"{ENV_EXPORT_DIR} is not set. Copy .env.example to .env and set it."
        )
    export_dir = Path(raw).expanduser()
    if not export_dir.is_dir():
        raise ConfigError(f"{ENV_EXPORT_DIR} is not a folder: {export_dir}")
    return Settings(
        export_dir=export_dir,
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
