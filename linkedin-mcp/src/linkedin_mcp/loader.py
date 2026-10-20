"""CSV parsing for the LinkedIn data export.

LinkedIn's CSVs are not perfectly uniform: some files start with a few lines
of free-text notes before the real header row, and column names can drift
between exports. We therefore locate the header row dynamically and look
columns up case-insensitively, instead of assuming fixed positions.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from pathlib import Path

from .models import Connection, Position, Post, Profile

logger = logging.getLogger(__name__)

_MAX_HEADER_SCAN_LINES = 20


def _norm(value: str) -> str:
    return value.strip().lower()


def read_rows(path: Path, required: Iterable[str]) -> list[dict[str, str]]:
    """Read a LinkedIn CSV into a list of dicts keyed by lower-case header.

    Returns an empty list (and logs a warning) if the file is missing or no
    header row containing all ``required`` columns can be found.
    """
    if not path.is_file():
        logger.warning("Missing file: %s", path.name)
        return []

    required_set = {_norm(r) for r in required}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header: list[str] | None = None
        for line_no, row in enumerate(reader):
            if line_no >= _MAX_HEADER_SCAN_LINES:
                break
            if required_set <= {_norm(cell) for cell in row}:
                header = [_norm(cell) for cell in row]
                break
        if header is None:
            logger.warning("No valid header row in %s", path.name)
            return []

        rows: list[dict[str, str]] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            padded = row + [""] * (len(header) - len(row))
            rows.append(
                {key: value.strip() for key, value in zip(header, padded, strict=False)}
            )
        return rows


def load_connections(directory: Path) -> list[Connection]:
    rows = read_rows(directory / "Connections.csv", ["first name", "last name"])
    return [
        Connection(
            first_name=r.get("first name", ""),
            last_name=r.get("last name", ""),
            company=r.get("company", ""),
            position=r.get("position", ""),
            url=r.get("url", ""),
            connected_on=r.get("connected on", ""),
        )
        for r in rows
    ]

     
def load_posts(directory: Path) -> list[Post]:
    rows = read_rows(directory / "Shares.csv", ["date", "sharecommentary"])
    return [
        Post(
            date=r.get("date", ""),
            text=r.get("sharecommentary", ""),
            link=r.get("sharelink", ""),
        )
        for r in rows
        if r.get("sharecommentary")
    ]


def load_positions(directory: Path) -> list[Position]:
    rows = read_rows(directory / "Positions.csv", ["company name", "title"])
    return [
        Position(
            company=r.get("company name", ""),
            title=r.get("title", ""),
            description=r.get("description", ""),
            location=r.get("location", ""),
            started_on=r.get("started on", ""),
            finished_on=r.get("finished on", ""),
        )
        for r in rows
    ]


def load_skills(directory: Path) -> list[str]:
    rows = read_rows(directory / "Skills.csv", ["name"])
    return [r["name"] for r in rows if r.get("name")]


def load_profile(directory: Path) -> Profile | None:
    rows = read_rows(directory / "Profile.csv", ["first name", "last name"])
    if not rows:
        return None
    r = rows[0]
    return Profile(
        first_name=r.get("first name", ""),
        last_name=r.get("last name", ""),
        headline=r.get("headline", ""),
        summary=r.get("summary", ""),
        industry=r.get("industry", ""),
        location=r.get("geo location", ""),
    )
