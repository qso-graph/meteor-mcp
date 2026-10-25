# Changelog

All notable changes to `meteor-mcp` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

**Upgrading:** a tool that fails now returns `isError: true` instead of a successful result whose
payload carried an `error` key. That covers both kinds of failure — bad input, and the Global
Meteor Network or NASA CNEOS being unreachable. Anything reading `result["error"]` should read the
error flag instead. The messages are unchanged.

### MCP specification 2026-07-28 (#8)

- **Tool errors are flagged `isError`.** `_err` built `{"error": message}` and **nine** call sites
  returned it. It raises `ToolError` now, typed `NoReturn`.
- **Both kinds of failure are flagged, because the specification treats them the same.** Bad input
  (a time that cannot be read, a shower not in the IAU MDC list, a limit that is not a whole
  number) and an upstream source failing. A JSON-RPC protocol error is for a request the server
  cannot route at all; "an API request failure" is on the specification's own list of tool
  execution errors.
- **This server needed two annotation blocks, and that is the point of reading each tool.** Five
  answer from the MDC shower list carried in the package plus geometry; `meteor_activity` reads the
  Global Meteor Network and `meteor_fireballs` reads NASA CNEOS. **Five `false`, two `true`.** One
  block would have advertised five closed-domain tools as open-world — or, far worse, advertised
  two network calls as closed. `MT-C12` reads `server.py` and asserts that exactly the tools whose
  bodies reach `live.` are the ones publishing `openWorldHint: true`, compared against the
  *published* annotations rather than a list in the test, so moving a decorator cannot leave it
  green.
- **`certifi` is already correct here, and is now asserted rather than noted.** This is the only
  repo in the sweep where qso-graph-devel#73 applies at all: `live.py` builds its context with
  `ssl.create_default_context(cafile=certifi.where())`. `MT-C20` holds that, `MT-C21` holds that
  verification is never turned off, and `MT-C22` holds that `live.py` is the *only* module that
  reaches the network — so there is one place to get TLS right.
- **A failure says a source is down without describing our insides.** `live.LiveError` is
  deliberately vague ("the source could not be reached") and the tool adds only which source it
  was. `MT-C41` asserts no URL, traceback or filesystem path reaches the caller — an error path is
  exactly where that leaks by accident.
- **A test of mine could not fail, and falsifying it is what showed that.** `MT-C30` originally
  asserted only that bad input raised `ToolError`. With `_err` returning a payload instead of
  raising, the bare call sites let execution continue and the tool crashed a few lines later —
  `AttributeError: 'NoneType' object has no attribute 'iau_number'` — which FastMCP delivers as a
  `ToolError` too. **A crash and a refusal were indistinguishable to it.** It now asserts the
  message each refusal was written with, and `MT-C31` generalises that: whatever a tool refuses, it
  must not do it by leaking a Python exception.
- `tests/test_mcp_conformance.py` (MT-C01 onward, 16 tests). Every check falsified — **12 of 12** —
  including `MT-C30` and `MT-C31` against the patch that defeated the first version.
- **Nothing moved on the wire but the annotations**, verified through a real `fastmcp.Client`.

### Lint (#7)

- **`E501` is adopted.** 17 lines, not one a defect.
- **The publisher-name exemption is not needed, in the one repo where it nearly was.** One line
  quotes GMN's own file header verbatim — `# Unique trajectory identifier; Beginning Julian date;
  Beginning UTC Time; IAU No; IAU code` — and it splits as adjacent string literals, so the value
  is **byte-identical**; the test that parses GMN's real format still passes. Zero exemptions, and
  no `# noqa` anywhere in the repo.
- **Every tool description came out byte-identical**, because none of the long lines was in a
  docstring.
- Falsified: a long line planted in `src/`, caught.

## [0.1.0] — 2026-10-11

### Added

- **`meteor_window`** — the tool this server exists for. Two grid squares in; the path,
  the shower in play, and the hour-by-hour geometry out. Three factors decide a contact
  and all three are reported: the path length against single-hop limits, the radiant's
  elevation **at the path midpoint** (where the reflection happens, not at either
  station), and the angle between the radiant and the path. That last one decides whether
  a reflection is geometrically possible at all — a trail reflects only where it is
  tangent to the ellipsoid with both stations at its foci, so a radiant broadside to the
  path works and one up-path does not, at the same elevation.
- **Your own end of the path comes from the station profile.** `meteor_window` takes
  `their_grid` and leaves `my_grid` optional, so a host that knows the operator's station
  supplies it — QG Desktop's Station component, carrying **ADIF's `MY_GRIDSQUARE`**. Exact
  `MY_LAT`/`MY_LON` coordinates are accepted and preferred over a grid square, because a
  square is a rectangle whose centre would otherwise be assumed (about 110 by 160 km of
  slack at 4 characters; it moved one real path by 38 km). Home, portable and remote all
  work without a special case, because ADIF's location fields describe the transmitting
  station rather than where the operator sits. A 2-character locator is refused for a path
  with the reason, since ADIF permits it but 1100 km of ambiguity cannot support one.
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

- **The single-hop call is hedged when the locators cannot decide it.** A grid square is a
  rectangle and its centre is all a locator gives, so the distance carries slack. This is
  computed from the characters each locator actually carried rather than inferred from the
  mode — ADIF enumerates modes and submodes but says nothing about payload length, so
  there is no authority for such an inference and 4 is the safe floor for every mode. About
  ±100 km per end at 4 characters, a few km at 6. At the 4-character floor a path length
  is within roughly ±200 km — immaterial mid-range, decisive against a threshold, since
  2250 km could be 2050 to 2450 and straddle the 2300 km limit. When a limit falls inside
  the slack the answer says the call cannot be made at that precision and what would
  settle it. The slack is always reported.
- **The summary leads with the path verdict when the path cannot work.** Distance and
  radiant geometry are assessed independently, so a path far past single hop can still
  have a radiant beautifully placed — and the sentence opened with "workable for 7 of 7
  sampled times" on a 2535 km path that is physically unusable, mentioning the distance
  only at the end. An operator reading the first clause would have gone and listened.
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
