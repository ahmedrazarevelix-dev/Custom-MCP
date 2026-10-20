from pathlib import Path

import pytest

from linkedin_mcp.models import Post
from linkedin_mcp.repository import MAX_LIMIT, LinkedInData, clamp_limit


def test_loads_despite_notes_preamble(data: LinkedInData) -> None:
    assert len(data.connections) == 3


def test_search_requires_all_tokens(data: LinkedInData) -> None:
    results = data.search_connections("acme engineer")
    assert [c.full_name for c in results] == ["Ali Khan"]


def test_search_is_case_insensitive(data: LinkedInData) -> None:
    assert len(data.search_connections("GLOBEX")) == 1


def test_empty_query_returns_nothing(data: LinkedInData) -> None:
    assert data.search_connections("   ") == []


def test_public_dict_has_no_email(data: LinkedInData) -> None:
    keys = data.connections[0].to_public_dict().keys()
    assert "email" not in keys


def test_posts_search(data: LinkedInData) -> None:
    assert len(data.search_posts("mcp")) == 1


def test_public_post_text_is_truncated_with_ellipsis() -> None:
    text = "x" * 501
    public_post = Post(date="2024-01-01", text=text, link="https://example.invalid/post").to_public_dict()
    assert len(public_post["text"]) == 501
    assert public_post["text"] == ("x" * 500) + "…"


def test_missing_files_are_tolerated(tmp_path: Path) -> None:
    empty = LinkedInData.from_directory(tmp_path)
    assert empty.connections == [] and empty.profile is None


def test_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LinkedInData.from_directory(tmp_path / "nope")


@pytest.mark.parametrize(
    ("given", "expected"), [(-1, 10), (0, 10), (5, 5), (999, MAX_LIMIT)]
)
def test_clamp_limit(given: int, expected: int) -> None:
    assert clamp_limit(given) == expected
