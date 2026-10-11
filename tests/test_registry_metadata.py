"""server.json has to satisfy the MCP Registry before a release, not during one.

The Registry rejected eme-mcp 0.1.0 with a 422: its description was 133
characters and the limit is 100. PyPI had already accepted the upload, so that
release was half-done — on PyPI, absent from the Registry, untagged. A limit
discovered by a failing publish costs a version number every time.
"""

from __future__ import annotations

import json
import pathlib

SERVER_JSON = pathlib.Path(__file__).resolve().parent.parent / "server.json"

# From the 422 the Registry returns:
#   {"message": "expected length <= 100", "location": "body._meta.io.description"}
DESCRIPTION_LIMIT = 100


def test_description_is_within_the_registry_limit() -> None:
    """The check that would have caught eme-mcp's failed release."""
    description = json.loads(SERVER_JSON.read_text())["description"]
    assert len(description) <= DESCRIPTION_LIMIT, (
        f"server.json description is {len(description)} characters; the MCP "
        f"Registry refuses anything over {DESCRIPTION_LIMIT} and the publish "
        "fails after PyPI has already accepted the upload."
    )


def test_server_json_names_this_package() -> None:
    """A copied server.json naming another package would publish under it."""
    data = json.loads(SERVER_JSON.read_text())
    assert data["name"] == "io.github.qso-graph/meteor-mcp"
    assert data["packages"][0]["identifier"] == "meteor-mcp"


def test_versions_agree_with_each_other() -> None:
    """server.json carries the version twice; they must not drift apart."""
    data = json.loads(SERVER_JSON.read_text())
    assert data["version"] == data["packages"][0]["version"]
