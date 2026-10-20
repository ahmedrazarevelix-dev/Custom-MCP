"""Synthetic CSV edge cases for each loader function."""

from __future__ import annotations

import logging
from pathlib import Path

from linkedin_mcp import loader
from linkedin_mcp.models import Connection, Position, Post, Profile


def test_header_normalization_and_read_rows_edge_cases(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text(
        "\ufeffNotes: export preamble\n\n FIRST NAME , Last Name , Extra \n"
        " Ada , Lovelace , value , ignored\n\nGrace,Hopper\n",
        encoding="utf-8",
    )

    assert loader._norm("  First NAME ") == "first name"
    assert loader.read_rows(path, ["first name", "last name"]) == [
        {"first name": "Ada", "last name": "Lovelace", "extra": "value"},
        {"first name": "Grace", "last name": "Hopper", "extra": ""},
    ]


def test_read_rows_missing_file_and_invalid_or_late_header(
    tmp_path: Path, caplog
) -> None:
    missing = tmp_path / "missing.csv"
    invalid = tmp_path / "invalid.csv"
    late = tmp_path / "late.csv"
    invalid.write_text("title,body\nX,Y\n", encoding="utf-8")
    late.write_text(
        "note\n" * 20 + "First Name,Last Name\nAda,Lovelace\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        assert loader.read_rows(missing, ["first name"]) == []
        assert loader.read_rows(invalid, ["first name"]) == []
        assert loader.read_rows(late, ["first name", "last name"]) == []
    assert "Missing file" in caplog.text
    assert "No valid header row" in caplog.text


def test_each_loader_maps_fields_and_filters_empty_records(tmp_path: Path) -> None:
    (tmp_path / "Connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ada,Lovelace,https://example.invalid/ada,private@example.invalid,"
        "Analytical Engines,Programmer,01 Jan 2020\n",
        encoding="utf-8",
    )
    (tmp_path / "Profile.csv").write_text(
        "First Name,Last Name,Headline,Summary,Industry,Geo Location\n"
        "Ada,Lovelace,Mathematician,Analytical notes,Technology,London\n"
        "Ignored,Second,Ignored,Ignored,Ignored,Ignored\n",
        encoding="utf-8",
    )
    (tmp_path / "Shares.csv").write_text(
        "Date,ShareLink,ShareCommentary\n"
        "2020-01-01,https://example.invalid/post,Engine note\n"
        "2020-01-02,https://example.invalid/blank,\n",
        encoding="utf-8",
    )
    (tmp_path / "Positions.csv").write_text(
        "Company Name,Title,Description,Location,Started On,Finished On\n"
        "Analytical Engines,Programmer,Created an engine,London,Jan 2020,Dec 2022\n",
        encoding="utf-8",
    )
    (tmp_path / "Skills.csv").write_text("Name\nPython\n\n   \nSQL\n", encoding="utf-8")

    assert loader.load_connections(tmp_path) == [
        Connection(
            "Ada",
            "Lovelace",
            "Analytical Engines",
            "Programmer",
            "https://example.invalid/ada",
            "01 Jan 2020",
        )
    ]
    assert loader.load_profile(tmp_path) == Profile(
        "Ada", "Lovelace", "Mathematician", "Analytical notes", "Technology", "London"
    )
    assert loader.load_posts(tmp_path) == [
        Post("2020-01-01", "Engine note", "https://example.invalid/post")
    ]
    assert loader.load_positions(tmp_path) == [
        Position(
            "Analytical Engines",
            "Programmer",
            "Created an engine",
            "London",
            "Jan 2020",
            "Dec 2022",
        )
    ]
    assert loader.load_skills(tmp_path) == ["Python", "SQL"]


def test_loader_handles_files_with_no_usable_rows(tmp_path: Path) -> None:
    (tmp_path / "Profile.csv").write_text("First Name,Last Name\n", encoding="utf-8")
    (tmp_path / "Shares.csv").write_text(
        "Date,ShareCommentary\n2020-01-01,\n", encoding="utf-8"
    )
    (tmp_path / "Skills.csv").write_text("Name\n\n", encoding="utf-8")

    assert loader.load_profile(tmp_path) is None
    assert loader.load_posts(tmp_path) == []
    assert loader.load_skills(tmp_path) == []
