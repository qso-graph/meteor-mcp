<!-- mcp-name: io.github.qso-graph/meteor-mcp -->
# meteor-mcp

[![PyPI](https://img.shields.io/pypi/v/meteor-mcp?label=PyPI&color=blue)](https://pypi.org/project/meteor-mcp/)

Meteor scatter planning for amateur radio: **can these two stations work each other on
this shower, and when.**

That is the whole shape of it. Meteor scatter is a point-to-point mode, so a radiant
elevation on its own tells an operator nothing they can act on — the question is always
about a path between two stations.

Part of the [qso-graph](https://qso-graph.io/) project.

## What decides a meteor-scatter contact

Three things, and radiant elevation is only one of them.

**1. Path length.** Trails burn at about 85–120 km, so a single-hop reflection off
something that low works from roughly 400 km to about 2300 km. Shorter and the reflection
point would have to be nearly overhead, where there is very little qualifying sky; longer
and it sits below both horizons. 800–2000 km is where the geometry is best, and it is
what hams actually run.

**2. Radiant elevation at the path midpoint** — not at either station. The reflection
happens near the middle, so that is the sky that matters. Below the horizon there are no
trails to reflect from. Very high is also poor, because trails then run down the path
rather than across it.

**3. The angle between the radiant and the path.** This is the one usually left out, and
it is the one that decides whether a reflection is geometrically possible at all. A trail
reflects specularly only where it is **tangent to the ellipsoid with both stations at its
foci**. Trails running *along* the path can never be tangent to it; trails running
*across* it can. So a radiant broadside to the path is good and a radiant up- or
down-path is poor — at the very same elevation.

All three are reported, and the verdict says which one decided it.

### Why there is no score out of a hundred

Because the physics above is a tangency condition, and what a station actually hears also
depends on its power, its antenna and the sporadic background. A figure like "73" would
imply a precision none of that supports. So the answer is `no` / `marginal` / `good` /
`best`, each with the reason beside it.

## Where the numbers come from

Shower radiants, numbers and names are the **IAU Meteor Data Center's** — the body that
names and numbers meteor showers. The package carries the facts read from the MDC's
*Established showers* file with its URL and SHA-256 recorded, so the exact edition served
is identifiable. The MDC is maintained on an unpaid voluntary basis and asks to be cited;
its requested references are returned by `meteor_source_info`, printed in
[NOTICE](NOTICE), and travel inside every answer that uses a radiant.

The MDC lists **several published solutions per shower**, each from a different study.
All of them are kept and **none is blended** — the average of two published radiants is a
third that nobody published and no paper stands behind. Tools return the first-listed
solution, labelled, and `meteor_shower_info` gives them all.

Peaks are stored as **solar longitude**, not as dates, because that is how the catalogue
publishes them and it is the right way round: solar longitude names the same point in the
stream every year, while a date drifts. This server converts it to the date it falls on
in the year you ask about.

Two tools read the network, because only those two report what is happening right now:

| Source | Used for | Licence |
|--------|----------|---------|
| [Global Meteor Network](https://globalmeteornetwork.org/) | Confirmed meteor counts today, by shower | CC BY 4.0 — attribution is a licence condition, and is returned in the answer |
| [NASA CNEOS](https://ssd-api.jpl.nasa.gov/fireball.api) | Recent fireballs | US government work |

Everything else is computed locally and needs no network at all.

## Install

```bash
uvx meteor-mcp            # run it; nothing to install
```

No credentials, no accounts, no configuration.

## Tools

| Tool | Description |
|------|-------------|
| `meteor_window` | **Start here.** Two grid squares in, and the path, the shower, and the hour-by-hour geometry out |
| `meteor_showers` | Which showers are near their peak now, closest first, with the peak date |
| `meteor_shower_info` | Every published solution for one shower, unaveraged |
| `meteor_activity` | How many meteors the Global Meteor Network has confirmed today, by shower (reads the network) |
| `meteor_fireballs` | Recent fireballs from NASA CNEOS (reads the network) |
| `meteor_source_info` | Where every number comes from, the edition checksum, and how to cite it |
| `get_version_info` | Service version and the catalogue edition carried |

### A count is not a flux

`meteor_activity` returns the **number of confirmed trajectories** the Global Meteor
Network has recorded today, broken down by IAU shower code. That is not a flux density —
meteoroids per square kilometre per hour, corrected for camera coverage and limiting
magnitude — which is a different quantity GMN computes separately. The tool is named and
documented for what it actually returns. GMN writes the file during the day, so an early
read covers a partial day; the generation time comes back with the answer.

## Quick Start

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

### Questions it answers

> "Can I work EM12 from DN13 on the Perseids tonight, and when?"

> "Which meteor showers are near their peak this week?"

> "Is the radiant going to be broadside to my path or up it?"

> "Is 2100 km too far for single-hop meteor scatter?"

> "How many meteors has the Global Meteor Network actually seen today?"

> "Show me every published radiant for the Geminids, not an average."

> "Were there any fireballs this week?"

## Pointing

Point both antennas near the **path bearing**, not at the radiant. The reflection happens
near the path midpoint; the radiant's position decides whether a trail there can be
tangent to your path, not where to aim.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
