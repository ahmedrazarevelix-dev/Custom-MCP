"""MCP server exposing read-only tools over your LinkedIn data export.

Run:
    linkedin-mcp   (reads LINKEDIN_EXPORT_DIR from the environment or .env)

IMPORTANT: this is a stdio server. Never ``print()`` to stdout, because stdout
carries the protocol. All logging goes to stderr.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .config import ConfigError, Settings, load_settings
from .repository import LinkedInData

logger = logging.getLogger("linkedin_mcp")

INSTRUCTIONS = """\
Read-only access to the user's own LinkedIn data export.
- Start with get_profile_summary for general context about the user.
- Use search_connections only when the user asks about a specific person,
  company or role. Prefer narrow queries over broad ones.
- Use search_posts to find the user's own past posts by keyword.
- Use list_experience for career history and skills.
- Data is a static snapshot from the export date; say so if freshness matters.
- Nothing here can modify LinkedIn. Never claim an action was performed.
"""

READ_ONLY = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, open_world_hint=False
)


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_server(data: LinkedInData) -> MCPServer:
    """Build the server around an already-loaded dataset (easy to test)."""
    mcp = MCPServer("linkedin-data", instructions=INSTRUCTIONS)

    @mcp.tool(annotations=READ_ONLY)
    def get_profile_summary() -> dict[str, Any]:
        """Get the user's profile: name, headline, summary, industry, location."""
        if data.profile is None:
            return {"error": "Profile.csv not found in the export."}
        return {
            **data.profile.to_public_dict(),
            "connection_count": len(data.connections),
            "post_count": len(data.posts),
        }

    @mcp.tool(annotations=READ_ONLY)
    def search_connections(query: str, limit: int = 10) -> dict[str, Any]:
        """Search the user's 1st-degree connections.

        Args:
            query: Words matched against name, company and job title. All
                words must match (e.g. "google engineer").
            limit: Max results to return (1-50, default 10).
        """
        results = data.search_connections(query, limit)
        return {
            "query": query,
            "count": len(results),
            "results": [c.to_public_dict() for c in results],
        }

    @mcp.tool(annotations=READ_ONLY)
    def search_posts(query: str, limit: int = 10) -> dict[str, Any]:
        """Search the user's own LinkedIn posts by keyword.

        Args:
            query: Words that must all appear in the post text.
            limit: Max results to return (1-50, default 10).
        """
        results = data.search_posts(query, limit)
        return {
            "query": query,
            "count": len(results),
            "results": [p.to_public_dict() for p in results],
        }

    @mcp.tool(annotations=READ_ONLY)
    def list_experience() -> dict[str, Any]:
        """List the user's work positions and skills."""
        return {
            "positions": [p.to_public_dict() for p in data.positions],
            "skills": data.skills,
        }

    @mcp.resource("linkedin://schema")
    def schema() -> str:
        """Describes what data is available, so the model knows what to expect."""
        return json.dumps(
            {
                "source": "LinkedIn 'Get a copy of your data' export (static snapshot)",
                "counts": {
                    "connections": len(data.connections),
                    "posts": len(data.posts),
                    "positions": len(data.positions),
                    "skills": len(data.skills),
                },
                "not_included": ["messages", "connection emails"],
            },
            indent=2,
        )

    return mcp


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        # Logging is not configured yet; stderr is safe for stdio servers.
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _configure_logging(settings)
    data = LinkedInData.from_directory(settings.export_dir)
    logger.info(
        "Loaded %d connections, %d posts, %d positions",
        len(data.connections),
        len(data.posts),
        len(data.positions),
    )
    create_server(data).run(transport="stdio")


if __name__ == "__main__":
    main()
