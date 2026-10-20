"""Serialization and search text contract for public model records."""

from linkedin_mcp.models import Connection, Position, Post, Profile


def test_connection_model_fields_and_private_email_boundary() -> None:
    item = Connection(
        "Ada",
        "Lovelace",
        "Analytical Engines",
        "Programmer",
        "https://example.invalid/ada",
        "01 Jan 2020",
    )
    assert item.full_name == "Ada Lovelace"
    assert item.searchable_text() == "ada lovelace analytical engines programmer"
    assert item.to_public_dict() == {
        "name": "Ada Lovelace",
        "company": "Analytical Engines",
        "position": "Programmer",
        "url": "https://example.invalid/ada",
        "connected_on": "01 Jan 2020",
    }
    assert "email" not in item.to_public_dict()


def test_post_search_and_public_text_boundary() -> None:
    exact = Post("2020-01-01", "x" * 500, "https://example.invalid/exact")
    long = Post("2020-01-02", "x" * 501, "https://example.invalid/long")
    assert exact.searchable_text() == "x" * 500
    assert exact.to_public_dict()["text"] == "x" * 500
    assert long.to_public_dict()["text"] == ("x" * 500) + "\u2026"
    assert long.to_public_dict()["date"] == "2020-01-02"
    assert long.to_public_dict()["link"] == "https://example.invalid/long"


def test_position_and_profile_public_fields() -> None:
    position = Position("Company", "Title", "Description", "Place", "Start", "End")
    assert position.to_public_dict() == {
        "company": "Company",
        "title": "Title",
        "description": "Description",
        "location": "Place",
        "started_on": "Start",
        "finished_on": "End",
    }
    profile = Profile("First", "Last", "Headline", "Summary", "Industry", "Place")
    assert profile.to_public_dict() == {
        "name": "First Last",
        "headline": "Headline",
        "summary": "Summary",
        "industry": "Industry",
        "location": "Place",
    }
