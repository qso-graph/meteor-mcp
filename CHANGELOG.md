# Changelog

All notable changes to `meteor-mcp` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`meteor_window`** — the tool this server exists for. Two grid squares in; the path,
  the shower in play, and the hour-by-hour geometry out. Three factors decide a contact
  and all three are reported: the path length against single-hop limits, the radiant's
  elevation **at the path midpoint** (where the reflection happens, not at either
  station), and the angle between the radiant and the path. That last one decides whether
  a reflection is geometrically possible at all — a trail reflects only where it is
  tangent to the ellipsoid with both stations at its foci, so a radiant broadside to the
  path works and one up-path does not, at the same elevation.
- **`meteor_showers`** — which showers are near their published maximum, closest first.
- **`meteor_shower_info`** — every published solution for one shower, never blended.
- **`meteor_activity`** — confirmed meteor counts today from the Global Meteor Network,
  by shower. A count, not a flux density; named and documented for what it returns.
- **`meteor_fireballs`** — recent fireballs from NASA CNEOS.
- **`meteor_source_info`** — provenance, the carried edition's SHA-256, and the MDC's own
  requested citations.
- 113 established showers and 594 published solutions read from the IAU Meteor Data
  Center, with the source file's URL, retrieval date, encoding and SHA-256 recorded. The
  file is latin-1 and the authors' names carry diacritics, so the encoding is pinned
  rather than guessed — a mangled name is a miscredit.
- Solar-longitude conversion both ways (Meeus ch. 25), so the catalogue's published
  maxima become dates in the year asked about. Checked against the peak dates every
  operator knows: Quadrantids, Lyrids, Perseids, Orionids, Leonids, Geminids, Ursids.

### Notes

- **The verdict is words, not a score.** The physics is a tangency condition and what a
  station hears also depends on its power, antenna and the sporadic background. A number
  out of a hundred would imply a precision none of that supports, so each verdict carries
  the reason that decided it.
- **No network for anything computed.** Only the two live tools reach out, and a test
  enforces that the other five stay offline.
- **TLS verification uses a current root set** (`certifi`) rather than whichever store the
  running Python was built against. NASA's API chains to a Sectigo root that older system
  OpenSSL stores do not carry, so on such a machine the fireball tool failed to connect
  while the GMN one worked. Verification is never disabled.

## [0.0.1] — 2026-10-11

- Placeholder release so the name is held on PyPI while the work is planned
  (qso-graph-devel#51). A pending trusted publisher does **not** reserve a name —
  PyPI's documentation is explicit that a name is held only once something is actually
  published — so this is a real, installable package rather than an empty repository.
- One tool, `get_version_info`, reporting the development status, what is planned, and
  where the work is tracked. The server's instructions say the same, so a client listing
  it sees the truth before calling anything.
