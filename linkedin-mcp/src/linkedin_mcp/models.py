"""Immutable data models for the records we expose."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Connection:
    first_name: str
    last_name: str
    company: str
    position: str
    url: str
    connected_on: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def searchable_text(self) -> str:
        return " ".join((self.full_name, self.company, self.position)).lower()

    def to_public_dict(self) -> dict[str, Any]:
        """Only the fields the model actually needs (no email, on purpose)."""
        return {
            "name": self.full_name,
            "company": self.company,
            "position": self.position,
            "url": self.url,
            "connected_on": self.connected_on,
        }


@dataclass(frozen=True, slots=True)
class Post:
    date: str
    text: str
    link: str

    def searchable_text(self) -> str:
        return self.text.lower()

    def to_public_dict(self, max_chars: int = 500) -> dict[str, Any]:
        text = self.text if len(self.text) <= max_chars else self.text[:max_chars] + "…"
        return {"date": self.date, "text": text, "link": self.link}


@dataclass(frozen=True, slots=True)
class Position:
    company: str
    title: str
    description: str
    location: str
    started_on: str
    finished_on: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Profile:
    first_name: str
    last_name: str
    headline: str
    summary: str
    industry: str
    location: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": f"{self.first_name} {self.last_name}".strip(),
            "headline": self.headline,
            "summary": self.summary,
            "industry": self.industry,
            "location": self.location,
        }
