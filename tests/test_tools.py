"""What a placeholder must still get right."""

from __future__ import annotations

from meteor_mcp import server


def test_version_info_reports_the_development_status() -> None:
    """The one tool answers, and says plainly that nothing works yet.

    A placeholder that looked finished would be worse than no package: someone
    would install it, ask it something, and get silence they could not explain.
    """
    info = server.get_version_info()
    assert info["service_name"] == "meteor-mcp"
    assert "development" in info["status"]
    assert info["tracking"].endswith("/51")
    assert info["planned"]


def test_the_instructions_say_so_too() -> None:
    """A client lists a server before it calls anything, so the warning has to
    be in the instructions, not only in a tool's reply."""
    instructions = server.mcp.instructions or ""
    assert "IN DEVELOPMENT" in instructions
    assert str(51) in instructions
