"""meteor-mcp — Meteor scatter MCP server."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("meteor-mcp")
except PackageNotFoundError:  # a source tree without an install
    __version__ = "0.0.0"
