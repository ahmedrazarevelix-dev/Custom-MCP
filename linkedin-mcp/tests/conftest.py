from pathlib import Path

import pytest

from linkedin_mcp.repository import LinkedInData


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    # Real exports often have a notes preamble before the header row.
    (tmp_path / "Connections.csv").write_text(
        "Notes:\n"
        '"When exporting your connection data, you may notice some are missing."\n'
        "\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ali,Khan,https://li/ali,,Acme,Backend Engineer,01 Jan 2024\n"
        "Sara,Ahmed,https://li/sara,,Globex,Data Scientist,02 Feb 2024\n"
        "Omar,Sheikh,https://li/omar,,Acme,Designer,03 Mar 2024\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "Profile.csv").write_text(
        "First Name,Last Name,Headline,Summary,Industry,Geo Location\n"
        "Test,User,Engineer,Builds things,Software,Karachi\n"
    )
    (tmp_path / "Shares.csv").write_text(
        "Date,ShareLink,ShareCommentary\n"
        '2024-01-01,https://li/p1,"Excited about MCP servers"\n'
        '2024-02-01,https://li/p2,"Hiring a designer"\n'
    )
    (tmp_path / "Skills.csv").write_text("Name\nPython\nSQL\n")
    return tmp_path


@pytest.fixture
def data(export_dir: Path) -> LinkedInData:
    return LinkedInData.from_directory(export_dir)
