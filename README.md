# linkedin-mcp

A small, **read-only** MCP server that lets Claude query *your own* LinkedIn
data, using the archive from LinkedIn's "Get a copy of your data".

No scraping, no LinkedIn login, no API keys: everything runs locally on your
machine from CSV files you downloaded yourself.

## 1. Get your data

LinkedIn → Me → Settings & Privacy → Data privacy → **Get a copy of your data**
→ choose the larger archive → Request archive. LinkedIn emails a download link
(can take minutes to hours). Unzip it into a folder, e.g. `~/linkedin-export`.

Files used (all optional; missing ones are skipped):
`Connections.csv`, `Profile.csv`, `Shares.csv`, `Positions.csv`, `Skills.csv`.

Messages are deliberately **not** exposed (they contain other people's private
conversations). Connection emails are also never returned.

## 2. Install and configure

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"  (needs mcp>=2)
cp .env.example .env       # then edit .env
```

Set your export folder in `.env`:

```
LINKEDIN_EXPORT_DIR=/absolute/path/to/linkedin-export
```

`.env` is loaded by `src/linkedin_mcp/config.py`. Real environment variables
win over `.env`. `.env` and the export CSVs are git-ignored, so pushing to
GitHub only publishes `.env.example` (placeholder values).

```bash
uv run pytest              # tests
uv run ruff check .        # lint
```

## 3. Try it with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run linkedin-mcp
```

## 4. Connect to Claude Desktop

Add to `claude_desktop_config.json` (use absolute paths):

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "uv",
      "args": ["--directory", "/ABS/PATH/linkedin-mcp", "run", "linkedin-mcp"],
      "env": { "LINKEDIN_EXPORT_DIR": "/ABS/PATH/linkedin-export" }
    }
  }
}
```

The `env` block there overrides `.env`, so you can skip `.env` when using Claude Desktop. Restart Claude Desktop. Then ask e.g. *"Who in my connections works at Acme?"*

## Tools

| Tool | Purpose |
|---|---|
| `get_profile_summary` | Name, headline, summary, counts |
| `search_connections(query, limit)` | Match name / company / title |
| `search_posts(query, limit)` | Search your own posts |
| `list_experience` | Positions and skills |

Resource: `linkedin://schema` (what data exists and what doesn't).

## Design notes

- Every tool is read-only and annotated `readOnlyHint=True`.
- Result sizes are capped (max 50) and long posts are truncated.
- Never `print()` in a stdio server; logs go to stderr.
- Header row is detected dynamically because LinkedIn CSVs may start with notes.
- Data is a snapshot; re-export to refresh.
