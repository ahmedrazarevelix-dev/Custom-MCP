"""Opt-in integration checks against the LinkedIn export configured in .env.

Run with LINKEDIN_MCP_REAL_DATA_TESTS=1. Assertions intentionally avoid
printing names, post text, URLs, or other personal export contents.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import warnings

import pytest

from linkedin_mcp.config import load_settings
from linkedin_mcp.repository import LinkedInData
from linkedin_mcp.server import create_server

pytestmark = pytest.mark.skipif(
    os.environ.get("LINKEDIN_MCP_REAL_DATA_TESTS") != "1",
    reason="Set LINKEDIN_MCP_REAL_DATA_TESTS=1 to test the export configured in .env.",
)


@pytest.fixture(scope="module")
def real_data() -> LinkedInData:
    settings = load_settings()
    return LinkedInData.from_directory(settings.export_dir)


def _call_tool(data: LinkedInData, name: str, args: dict | None = None) -> dict:
    return _call_tools(data, [(name, args or {})])[0]


def _call_tools(data: LinkedInData, requests: list[tuple[str, dict]]) -> list[dict]:
    async def invoke_all() -> list[dict]:
        server = create_server(data)
        outputs = []
        for name, args in requests:
            result = await server.call_tool(name, args)
            outputs.append(json.loads(result.content[0].text))
        return outputs

    return asyncio.run(invoke_all())


def _safe_check(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message)


def _independent_search(items, query: str, limit: int) -> list[dict]:
    tokens = query.lower().split()
    maximum = 10 if limit <= 0 else min(limit, 50)
    if not tokens:
        return []
    matches = [
        item
        for item in items
        if all(token in item.searchable_text() for token in tokens)
    ]
    return [item.to_public_dict() for item in matches[:maximum]]


def _independent_csv_rows(
    export_dir, filename: str, required: set[str]
) -> list[dict[str, str]]:
    path = export_dir / filename
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = None
        for line_number, row in enumerate(reader):
            if line_number >= 20:
                break
            normalized = [cell.strip().lower() for cell in row]
            if required <= set(normalized):
                header = normalized
                break
        if header is None:
            return []
        rows = []
        for row in reader:
            if any(cell.strip() for cell in row):
                padded = row + [""] * max(0, len(header) - len(row))
                rows.append(
                    {
                        key: value.strip()
                        for key, value in zip(header, padded, strict=False)
                    }
                )
        return rows


def test_real_export_loads_without_exposing_connection_emails(
    real_data: LinkedInData,
) -> None:
    export_dir = load_settings().export_dir
    _safe_check(
        isinstance(real_data.connections, list), "Connections did not load as a list."
    )
    _safe_check(isinstance(real_data.posts, list), "Posts did not load as a list.")
    _safe_check(
        isinstance(real_data.positions, list), "Positions did not load as a list."
    )
    for connection in real_data.connections:
        _safe_check(
            "email" not in connection.to_public_dict(),
            "A public connection result included an email field.",
        )

    raw_connections = _independent_csv_rows(
        export_dir, "Connections.csv", {"first name", "last name"}
    )
    expected_connections = [
        (
            row.get("first name", ""),
            row.get("last name", ""),
            row.get("company", ""),
            row.get("position", ""),
            row.get("url", ""),
            row.get("connected on", ""),
        )
        for row in raw_connections
    ]
    actual_connections = [
        (
            item.first_name,
            item.last_name,
            item.company,
            item.position,
            item.url,
            item.connected_on,
        )
        for item in real_data.connections
    ]
    _safe_check(
        actual_connections == expected_connections,
        "Connection loader fields/rows differed from the raw export CSV.",
    )

    raw_profile = _independent_csv_rows(
        export_dir, "Profile.csv", {"first name", "last name"}
    )
    if raw_profile:
        row = raw_profile[0]
        expected_profile = (
            row.get("first name", ""),
            row.get("last name", ""),
            row.get("headline", ""),
            row.get("summary", ""),
            row.get("industry", ""),
            row.get("geo location", ""),
        )
        actual_profile = (
            (
                real_data.profile.first_name,
                real_data.profile.last_name,
                real_data.profile.headline,
                real_data.profile.summary,
                real_data.profile.industry,
                real_data.profile.location,
            )
            if real_data.profile
            else None
        )
        _safe_check(
            actual_profile == expected_profile,
            "Profile loader fields differed from the raw export CSV.",
        )

    raw_positions = _independent_csv_rows(
        export_dir, "Positions.csv", {"company name", "title"}
    )
    expected_positions = [
        (
            row.get("company name", ""),
            row.get("title", ""),
            row.get("description", ""),
            row.get("location", ""),
            row.get("started on", ""),
            row.get("finished on", ""),
        )
        for row in raw_positions
    ]
    actual_positions = [
        (
            item.company,
            item.title,
            item.description,
            item.location,
            item.started_on,
            item.finished_on,
        )
        for item in real_data.positions
    ]
    _safe_check(
        actual_positions == expected_positions,
        "Position loader fields/rows differed from the raw export CSV.",
    )

    raw_posts = _independent_csv_rows(
        export_dir, "Shares.csv", {"date", "sharecommentary"}
    )
    expected_posts = [
        (row.get("date", ""), row.get("sharecommentary", ""), row.get("sharelink", ""))
        for row in raw_posts
        if row.get("sharecommentary")
    ]
    actual_posts = [(item.date, item.text, item.link) for item in real_data.posts]
    _safe_check(
        actual_posts == expected_posts,
        "Post loader fields/rows differed from the raw export CSV.",
    )

    raw_skills = _independent_csv_rows(export_dir, "Skills.csv", {"name"})
    expected_skills = [row["name"] for row in raw_skills if row.get("name")]
    _safe_check(
        real_data.skills == expected_skills,
        "Skill loader fields/rows differed from the raw export CSV.",
    )


def test_real_profile_tool_matches_loaded_export(real_data: LinkedInData) -> None:
    result = _call_tool(real_data, "get_profile_summary")
    if real_data.profile is None:
        _safe_check(
            bool(result.get("error")), "Missing profile did not return an error result."
        )
        return

    expected = {
        **real_data.profile.to_public_dict(),
        "connection_count": len(real_data.connections),
        "post_count": len(real_data.posts),
    }
    _safe_check(
        result == expected, "Profile tool fields did not match the loaded export."
    )


def test_real_connection_tool_finds_a_record_from_the_export(
    real_data: LinkedInData,
) -> None:
    if not real_data.connections:
        result = _call_tool(real_data, "search_connections", {"query": "__no_match__"})
        _safe_check(
            result.get("count") == 0,
            "Empty connections export did not return zero matches.",
        )
        return

    # Verify every searchable record and every public field, not just one
    # sample. Queries are composed only from fields on that actual record.
    connection_requests = []
    expected_results = []
    expected_rows = []
    no_searchable_fields = 0
    for connection in real_data.connections:
        fields = [
            connection.first_name,
            connection.last_name,
            connection.company,
            connection.position,
        ]
        query = " ".join(part.strip() for part in fields if part.strip())
        if not query:
            no_searchable_fields += 1
            continue
        connection_requests.append(
            ("search_connections", {"query": query, "limit": 50})
        )
        expected_results.append(_independent_search(real_data.connections, query, 50))
        expected_rows.append(connection.to_public_dict())

    outputs = _call_tools(real_data, connection_requests)
    not_reachable_due_to_result_cap = 0
    for result, expected, expected_row in zip(
        outputs, expected_results, expected_rows, strict=True
    ):
        _safe_check(
            result.get("results") == expected and result.get("count") == len(expected),
            "Connection tool output differed from independently computed matches.",
        )
        if expected_row not in result.get("results", []):
            if len(result.get("results", [])) == 50:
                not_reachable_due_to_result_cap += 1
            else:
                _safe_check(
                    False, "A searchable connection was absent below the result cap."
                )
        _safe_check(
            all("email" not in item for item in result.get("results", [])),
            "A connection query exposed an email field.",
        )
    if not_reachable_due_to_result_cap or no_searchable_fields:
        warnings.warn(
            f"{no_searchable_fields} loaded connection record(s) have no searchable "
            "name/company/role fields; "
            f"{not_reachable_due_to_result_cap} further record(s) are beyond the "
            "50-result query cap. Those records cannot be individually surfaced "
            "through the search tool.",
            pytest.PytestWarning,
            stacklevel=1,
        )

    for query in ("", "   ", "__linkedin_mcp_no_match__"):
        result = _call_tool(real_data, "search_connections", {"query": query})
        _safe_check(
            result.get("count") == 0,
            "Empty or unmatched connection query returned results.",
        )

    if real_data.connections:
        sample = next(
            (c for c in real_data.connections if c.searchable_text().strip()), None
        )
        if sample:
            query = " ".join(
                part for part in (sample.first_name, sample.last_name) if part.strip()
            )
            query = query or sample.company.strip() or sample.position.strip()
            for limit, maximum in ((1, 1), (0, 10), (-1, 10), (999, 50)):
                output = _call_tool(
                    real_data, "search_connections", {"query": query, "limit": limit}
                )
                expected = _independent_search(real_data.connections, query, limit)
                _safe_check(
                    output.get("results") == expected
                    and len(output.get("results", [])) <= maximum,
                    "Connection limit output differed from repository results.",
                )


def test_real_posts_tool_finds_a_record_when_shares_exist(
    real_data: LinkedInData,
) -> None:
    if not real_data.posts:
        pytest.skip("Shares.csv is missing or contains no post text in this export.")

    searchable_posts = [item for item in real_data.posts if item.text.split()]
    if not searchable_posts:
        pytest.skip("Shares.csv contains no searchable post text in this export.")
    post_requests = []
    expected_posts = []
    expected_post_rows = []
    for post in searchable_posts:
        words = post.text.split()
        query = " ".join(words[:2]) if len(words) >= 2 else words[0]
        post_requests.append(("search_posts", {"query": query, "limit": 50}))
        expected_posts.append(_independent_search(real_data.posts, query, 50))
        expected_post_rows.append(post.to_public_dict())

    outputs = _call_tools(real_data, post_requests)
    posts_beyond_cap = 0
    for result, expected, expected_row in zip(
        outputs, expected_posts, expected_post_rows, strict=True
    ):
        _safe_check(
            result.get("results") == expected and result.get("count") == len(expected),
            "Post tool output differed from independently computed matches.",
        )
        if expected_row not in result.get("results", []) and len(expected) == 50:
            posts_beyond_cap += 1
        elif expected_row not in result.get("results", []):
            _safe_check(False, "A searchable post was absent below the result cap.")
    if posts_beyond_cap:
        warnings.warn(
            f"{posts_beyond_cap} post record(s) were beyond the 50-result query cap.",
            pytest.PytestWarning,
            stacklevel=1,
        )
    for query in ("", "   ", "__linkedin_mcp_no_match__"):
        result = _call_tool(real_data, "search_posts", {"query": query})
        _safe_check(
            result.get("count") == 0, "Empty or unmatched post query returned results."
        )
    post = searchable_posts[0]
    word = post.text.split()[0]
    for limit, maximum in ((1, 1), (0, 10), (-1, 10), (999, 50)):
        output = _call_tool(real_data, "search_posts", {"query": word, "limit": limit})
        expected = _independent_search(real_data.posts, word, limit)
        _safe_check(
            output.get("results") == expected
            and len(output.get("results", [])) <= maximum,
            "Post limit behavior/output differed from repository results.",
        )


def test_real_experience_tool_matches_loaded_export(real_data: LinkedInData) -> None:
    result = _call_tool(real_data, "list_experience")
    _safe_check(
        result.get("positions")
        == [item.to_public_dict() for item in real_data.positions],
        "Experience tool fields did not match every loaded position.",
    )
    _safe_check(
        result.get("skills") == real_data.skills,
        "Experience tool skills did not match the loaded export.",
    )
