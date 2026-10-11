<!-- mcp-name: io.github.qso-graph/meteor-mcp -->
# meteor-mcp

[![PyPI](https://img.shields.io/pypi/v/meteor-mcp?label=PyPI&color=blue)](https://pypi.org/project/meteor-mcp/)

> ### In development
>
> This package is published so the name is held while the work is planned in the open.
> It registers one tool, `get_version_info`, and **does nothing else yet**. If you install
> it expecting a working server, that is what you will find — which is why it says so
> here, in the server's own instructions, and in the one tool it has.
>
> PyPI does not reserve a name for a pending trusted publisher, so a name is only held
> once something is actually published. Given that, a package that says what it is beats
> an empty one that does not.

Shower timing and radiant elevation computed locally, plus live meteor flux from the Global Meteor Network and recent fireballs from NASA CNEOS. Shower identity comes from the IAU Meteor Data Center, which names and numbers them; the annual calendar of peaks and rates comes from the IMO.

Planned work, including the data sources it would use and whether each is actually
available, is tracked in
[qso-graph-devel#51](https://github.com/qso-graph/qso-graph-devel/issues/51).

Part of the [qso-graph](https://qso-graph.io/) project.

## Install

```bash
uvx meteor-mcp            # run it; nothing to install
```

## Tools

| Tool | Description |
|------|-------------|
| `get_version_info` | Service version, development status, and where the work is tracked |

## Quick Start

No credentials needed — install and configure your MCP client.

### Configure your MCP client

meteor-mcp works with any MCP-compatible client. Add the server config and restart.

#### Claude Desktop

Add to `claude_desktop_config.json` (`~/Library/Application Support/Claude/` on macOS,
`%APPDATA%\Claude\` on Windows):

```json
{
  "mcpServers": {
    "meteor": {
      "command": "uvx",
      "args": ["meteor-mcp"]
    }
  }
}
```

#### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "meteor": {
      "command": "uvx",
      "args": ["meteor-mcp"]
    }
  }
}
```

#### ChatGPT Desktop

Configure via Settings > Apps & Connectors, or in your agent definition:

```json
{
  "mcpServers": {
    "meteor": {
      "command": "uvx",
      "args": ["meteor-mcp"]
    }
  }
}
```

### Questions it will answer

Not yet — these are what the finished server is for:

> "Which meteor showers are active this week, and when do they peak?"

> "When is the Perseid radiant highest from my grid square?"

> "What is the meteor rate right now?"

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
