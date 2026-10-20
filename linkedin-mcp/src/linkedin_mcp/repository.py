"""In-memory, read-only access layer over the loaded export."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import loader
from .models import Connection, Position, Post, Profile

MAX_LIMIT = 50


def _matches(haystack: str, query: str) -> bool:
    """True if every whitespace-separated token of ``query`` is in ``haystack``."""
    tokens = query.lower().split()
    return bool(tokens) and all(token in haystack for token in tokens)


def clamp_limit(limit: int, default: int = 10) -> int:
    if limit <= 0:
        return default
    return min(limit, MAX_LIMIT)


@dataclass(frozen=True, slots=True)
class LinkedInData:
    profile: Profile | None = None
    connections: list[Connection] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    @classmethod
    def from_directory(cls, directory: Path) -> LinkedInData:
        if not directory.is_dir():
            raise FileNotFoundError(f"Export directory not found: {directory}")
        return cls(
            profile=loader.load_profile(directory),
            connections=loader.load_connections(directory),
            posts=loader.load_posts(directory),
            positions=loader.load_positions(directory),
            skills=loader.load_skills(directory),
        )

    def search_connections(self, query: str, limit: int = 10) -> list[Connection]:
        found = (c for c in self.connections if _matches(c.searchable_text(), query))
        return [c for _, c in zip(range(clamp_limit(limit)), found, strict=False)]

    def search_posts(self, query: str, limit: int = 10) -> list[Post]:
        found = (p for p in self.posts if _matches(p.searchable_text(), query))
        return [p for _, p in zip(range(clamp_limit(limit)), found, strict=False)]
