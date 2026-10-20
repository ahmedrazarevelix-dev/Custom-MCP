import asyncio
import json
import sys

import pytest

from linkedin_mcp import server as server_module
from linkedin_mcp.config import ConfigError, Settings
from linkedin_mcp.repository import LinkedInData
from linkedin_mcp.server import create_server


def _call(server, name: str, args: dict | None = None) -> dict:
    result = asyncio.run(server.call_tool(name, args or {}))
    return json.loads(result.content[0].text)


def test_tools_registered_and_read_only(data: LinkedInData) -> None:
    server = create_server(data)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_profile_summary",
        "search_connections",
        "search_posts",
        "list_experience",
    }
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_search_connections_tool(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_connections", {"query": "sara"})
    assert out["count"] == 1
    assert out["results"][0]["company"] == "Globex"


def test_search_connections_tool_empty_query(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_connections", {"query": "   "})
    assert out["count"] == 0
    assert out["results"] == []


def test_search_connections_tool_respects_limit(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_connections", {"query": "a", "limit": 1})
    assert out["count"] == 1


def test_search_posts_tool(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_posts", {"query": "mcp"})
    assert out["count"] == 1
    assert out["results"][0]["date"] == "2024-01-01"
    assert out["results"][0]["text"] == "Excited about MCP servers"


def test_search_posts_tool_empty_query(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_posts", {"query": "   "})
    assert out["count"] == 0
    assert out["results"] == []


def test_search_posts_tool_respects_limit(data: LinkedInData) -> None:
    out = _call(create_server(data), "search_posts", {"query": "e", "limit": 1})
    assert out["count"] == 1


def test_list_experience_tool(data: LinkedInData) -> None:
    out = _call(create_server(data), "list_experience")
    assert out["positions"] == []
    assert out["skills"] == ["Python", "SQL"]


def test_profile_tool(data: LinkedInData) -> None:
    out = _call(create_server(data), "get_profile_summary")
    assert out["connection_count"] == 3


def test_profile_tool_when_profile_is_missing() -> None:
    out = _call(create_server(LinkedInData()), "get_profile_summary")
    assert out == {"error": "Profile.csv not found in the export."}


def test_logging_is_configured_to_stderr(monkeypatch, tmp_path) -> None:
    captured = {}

    def record_config(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(server_module.logging, "basicConfig", record_config)
    server_module._configure_logging(Settings(tmp_path, "DEBUG"))
    assert captured["stream"] is sys.stderr
    assert captured["level"] == "DEBUG"
    assert "%(asctime)s" in captured["format"]


def test_main_exits_cleanly_on_configuration_error(monkeypatch, capsys) -> None:
    def fail_settings():
        raise ConfigError("test config is unavailable")

    monkeypatch.setattr(server_module, "load_settings", fail_settings)
    with pytest.raises(SystemExit) as exc:
        server_module.main()
    assert exc.value.code == 2
    assert "test config is unavailable" in capsys.readouterr().err


def test_main_loads_export_and_starts_stdio(monkeypatch, tmp_path) -> None:
    settings = Settings(tmp_path, "ERROR")
    data = LinkedInData()
    calls = {}

    class FakeServer:
        def run(self, *, transport):
            calls["transport"] = transport

    monkeypatch.setattr(server_module, "load_settings", lambda: settings)
    monkeypatch.setattr(
        server_module,
        "_configure_logging",
        lambda value: calls.update(settings=value),
    )
    monkeypatch.setattr(
        LinkedInData,
        "from_directory",
        lambda path: calls.update(path=path) or data,
    )
    monkeypatch.setattr(
        server_module,
        "create_server",
        lambda value: calls.update(data=value) or FakeServer(),
    )

    server_module.main()
    assert calls == {
        "settings": settings,
        "path": tmp_path,
        "data": data,
        "transport": "stdio",
    }
