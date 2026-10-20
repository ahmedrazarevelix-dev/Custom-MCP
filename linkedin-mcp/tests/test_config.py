from pathlib import Path

import pytest
    
from linkedin_mcp import config
from linkedin_mcp.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(config.ENV_EXPORT_DIR, raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    # Point project root at an empty temp dir so a real .env is never read.
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path / "root")
    monkeypatch.chdir(tmp_path)


def test_missing_variable_raises() -> None:
    with pytest.raises(ConfigError, match="not set"):
        load_settings()


def test_reads_from_dotenv_file(tmp_path: Path, monkeypatch) -> None:
    export = tmp_path / "export"
    export.mkdir()
    (tmp_path / ".env").write_text(f"LINKEDIN_EXPORT_DIR={export}\nLOG_LEVEL=debug\n")
    settings = load_settings()
    assert settings.export_dir == export
    assert settings.log_level == "DEBUG"


def test_real_env_beats_dotenv(tmp_path: Path, monkeypatch) -> None:
    real, other = tmp_path / "real", tmp_path / "other"
    real.mkdir()
    other.mkdir()
    (tmp_path / ".env").write_text(f"LINKEDIN_EXPORT_DIR={other}\n")
    monkeypatch.setenv(config.ENV_EXPORT_DIR, str(real))
    assert load_settings().export_dir == real


def test_nonexistent_folder_raises(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(config.ENV_EXPORT_DIR, str(tmp_path / "nope"))
    with pytest.raises(ConfigError, match="not a folder"):
        load_settings()
