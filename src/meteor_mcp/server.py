"""meteor-mcp: meteor scatter planning for amateur radio.

Two stations, one question: **can we work each other on this shower, and
when.** That is the shape of every tool here, because that is the shape of the
contact — meteor scatter is a point-to-point mode, and a radiant elevation on
its own does not tell an operator anything they can act on.

Almost nothing here is fetched. The shower radiants are the IAU Meteor Data
Center's, carried in the package with their provenance pinned by checksum; the
geometry and the solar-longitude arithmetic are computed locally. Only two
tools reach the network, because only two of them report what is happening
right now: the Global Meteor Network's observed counts and NASA CNEOS's
fireballs.

What this server will not do is score a path out of a hundred. The underlying
physics is a tangency condition on an ellipsoid, and what a station actually
hears depends on its power, its antenna and the sporadic background. A verdict
in words with the reason beside it is the honest form of that answer.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, NoReturn

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import __version__, geometry, grid, live, showers, sun

mcp = FastMCP(
    "meteor-mcp",
    version=__version__,
    instructions=(
        "Meteor scatter planning between two stations. Start with meteor_window, giving "
        "both grid squares (for example DN13 and EM12): it reports the path, which shower "
        "is nearest its peak, and hour by hour whether the geometry can actually reflect, "
        "in words with the reason. meteor_showers says what is near peak now; "
        "meteor_shower_info gives every published solution for one shower; "
        "meteor_activity and meteor_fireballs read live sources. Radiants come from the "
        "IAU Meteor Data Center and are cited in every answer that uses them."
    ),
)

# Ceilings, so no single request can make the server compute for ever.
MAX_HOURS = 24.0 * 14
MAX_ROWS = 2000
MIN_STEP_MINUTES = 1.0


# A locator coarser than this cannot support a path calculation. ADIF permits a
# 2-character MY_GRIDSQUARE, and it is a legitimate value — but a field is 10 by
# 20 degrees, roughly 1100 km across, which is wider than the entire usable
# meteor-scatter range. A path computed from one would be fiction.
MIN_LOCATOR_CHARS = 4


class EndpointError(ValueError):
    """One end of the path could not be located. The message is safe to show."""


def _endpoint(locator: str | None, latitude: float | None, longitude: float | None,
              role: str) -> tuple[float, float, dict[str, Any]]:
    """Locate one end of the path, from a locator or from coordinates.

    Coordinates win when given, because they are better data. ADIF carries
    both for a station — `MY_GRIDSQUARE` and `MY_LAT`/`MY_LON` — and a grid
    square is a rectangle whose centre this would otherwise have to assume. A
    4-character square is about 110 by 160 km, so when a station knows its
    actual position there is no reason to round it to the middle of a box.
    """
    if latitude is not None and longitude is not None:
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise EndpointError(f"{role} latitude and longitude must be numbers.") from None
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            raise EndpointError(
                f"{role} position {lat}, {lon} is off the Earth: latitude runs "
                "-90 to 90 and longitude -180 to 180.")
        return lat, lon, {"latitude": round(lat, 4), "longitude": round(lon, 4),
                          "from": "coordinates", "uncertainty_km": 0.0}

    if latitude is not None or longitude is not None:
        raise EndpointError(f"{role} needs both a latitude and a longitude, or neither.")

    if not locator:
        raise EndpointError(
            f"I do not have {role} location. Give a grid square, or a latitude "
            "and longitude."
            if role != "your own"
            else "I do not have your own location. Give my_grid, or my_lat and "
                 "my_lon, or set a default grid in your Station profile — that is "
                 "ADIF's MY_GRIDSQUARE, and it travels with whether you are at "
                 "home, portable, or operating a remote station.")

    try:
        place = grid.place(str(locator))
    except grid.GridError as error:
        raise EndpointError(str(error)) from None

    if place.precision_chars < MIN_LOCATOR_CHARS:
        raise EndpointError(
            f"{str(locator).upper()!r} is only {place.precision_chars} characters — a "
            "Maidenhead field about 1100 km across, which is wider than the whole "
            "usable meteor-scatter path range. A path cannot honestly be computed "
            "from it. Four characters or more, for example DN13.")

    return place.latitude, place.longitude, {
        "grid": place.locator,
        "precision_chars": place.precision_chars,
        "latitude": round(place.latitude, 4),
        "longitude": round(place.longitude, 4),
        "from": "grid square centre",
        "uncertainty_km": round(grid.uncertainty_km(place), 1),
    }


def _err(message: str) -> NoReturn:
    """Report a tool execution error the way the protocol specifies.

    This returned ``{"error": message}`` as a *successful* result, so a client could not
    tell a failure from an answer. The specification says of ``CallToolResult.isError``
    that otherwise "the LLM would not be able to see that an error occurred and
    self-correct".

    Nine call sites reach it, and they are two different kinds of failure, which the
    specification treats the same way:

    * **bad input** — a time that cannot be read, a shower not in the IAU MDC list, a
      limit that is not a whole number;
    * **an upstream source failing** — the Global Meteor Network or NASA CNEOS not
      answering.

    Both are errors *from the tool*, so both are ``isError: true`` rather than a
    JSON-RPC protocol error, which is reserved for a request the server cannot route at
    all. The upstream messages stay as vague as ``live.LiveError`` makes them: "the
    source answered 404", never the URL or the exception. That is deliberate, and
    tests/test_mcp_conformance.py holds it.
    """
    raise ToolError(message)


def _parse_when(when: str | None) -> datetime | None:
    """A UTC instant, or now. None means the text could not be read."""
    if not when:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=timezone.utc)


def _citation() -> dict[str, Any]:
    """The MDC's own words about how it wants to be credited.

    The citations travel in the answer, not only in the README. The MDC is
    maintained unpaid and asks to be cited; a credit the user never sees is not
    one. The four references are the owner's own list, reproduced as written.
    """
    info = showers.source()
    return {
        "owner": info.get("owner"),
        "edition": info.get("edition"),
        "url": info.get("url"),
        "terms": info.get("terms"),
        "citations": info.get("citations", []),
    }


def _peak_moment(shower: showers.Shower, moment: datetime) -> datetime | None:
    """The nearest occurrence of this shower's published maximum.

    Neighbouring years are candidates, not just the year `moment` falls in.
    A shower peaking in early January is nearest its maximum on the 30th of
    the previous December, and anchoring the search to the calendar year would
    have reported that peak as ten months past while the offset beside it said
    four days ahead.
    """
    if shower.solar_longitude_deg is None:
        return None
    candidates = [sun.peak_date(shower.solar_longitude_deg, year)
                  for year in (moment.year - 1, moment.year, moment.year + 1)]
    return min(candidates, key=lambda when: abs((when - moment).total_seconds()))


def _days_until_peak(shower: showers.Shower, moment: datetime) -> float | None:
    """Days to a shower's maximum: positive means still ahead.

    Derived from the peak instant itself rather than from the mean solar rate,
    so this and `peak_utc` cannot disagree. They did, by about an hour over ten
    days, because the Earth does not cover solar longitude at a constant rate
    and one of the two was pretending it does.

    The sign is named in the identifier on purpose — as a bare "offset" it was
    read backwards here, and the summary sentence announced that a shower four
    days away had already passed.
    """
    peak = _peak_moment(shower, moment)
    if peak is None:
        return None
    return (peak - moment).total_seconds() / 86400.0


def _shower_payload(shower: showers.Shower, moment: datetime) -> dict[str, Any]:
    peak = _peak_moment(shower, moment)
    offset = _days_until_peak(shower, moment)
    return {
        "iau_number": shower.iau_number,
        "code": shower.code,
        "name": shower.name,
        "activity": shower.activity,
        "radiant_ra_deg": shower.radiant_ra_deg,
        "radiant_dec_deg": shower.radiant_dec_deg,
        "velocity_km_s": shower.velocity_km_s,
        "solar_longitude_deg": shower.solar_longitude_deg,
        "peak_utc": peak.isoformat().replace("+00:00", "Z") if peak else None,
        "days_until_peak": round(offset, 2) if offset is not None else None,
        "solution": shower.solution,
        "solutions_available": shower.solutions_available,
        "solution_note": (
            f"The MDC lists {shower.solutions_available} published solutions for this "
            "shower; this is the first. Use meteor_shower_info for all of them — they "
            "are never averaged, because an average radiant is one nobody published."
        ) if shower.solutions_available > 1 else None,
    }


def _nearest_peak(moment: datetime) -> showers.Shower | None:
    """The shower closest to its published maximum at this moment."""
    rated = [(abs(d), s) for s in showers.showers()
             if (d := _days_until_peak(s, moment)) is not None]
    return min(rated, key=lambda pair: pair[0])[1] if rated else None


# MCP 2026-07-28 tool annotations. The defaults are pessimistic — a tool that declares
# nothing is advertised as destructive, non-idempotent and open-world, and the
# specification tells a client it may keep a human in the loop for that.
#
# This server needs **two** blocks, and that is the whole point of reading each tool
# rather than copying one. Five tools answer from the IAU Meteor Data Center's shower
# list carried in the package, plus arithmetic. Two read somebody else's live service.
# A single block would have advertised five closed-domain tools as open-world, or — far
# worse — advertised two network calls as closed.
_ANSWERS_FROM_CARRIED_DATA = {
    "readOnlyHint": True,
    "destructiveHint": False,
    # The shower list ships in the wheel and the geometry is arithmetic, so the same
    # arguments give the same answer until the package is upgraded.
    "idempotentHint": True,
    # Nothing leaves the machine.
    "openWorldHint": False,
}

_READS_A_LIVE_SERVICE = {
    "readOnlyHint": True,
    "destructiveHint": False,
    # True in the sense the specification means: the tool changes nothing at the far
    # end. Its *answers* move, because GMN rewrites today's file during the day and
    # CNEOS gains fireballs — which is why meteor_activity returns the generation time.
    "idempotentHint": True,
    # These reach the Global Meteor Network and NASA CNEOS. Neither is a closed domain:
    # we do not control what they hold and cannot enumerate it. The specification's own
    # closed-domain example is a database query, and this is the opposite of one.
    "openWorldHint": True,
}


@mcp.tool(annotations=_ANSWERS_FROM_CARRIED_DATA)
def meteor_window(
    their_grid: str | None = None,
    my_grid: str | None = None,
    their_lat: float | None = None,
    their_lon: float | None = None,
    my_lat: float | None = None,
    my_lon: float | None = None,
    shower: str | None = None,
    when: str | None = None,
    hours: float | None = 12.0,
    step_minutes: float | None = 30.0,
) -> dict[str, Any]:
    """When two stations can work each other by meteor scatter, and why.

    Give both grid squares. The answer covers the path itself (is it even a
    meteor-scatter distance), which shower is in play, and then hour by hour
    whether the geometry can reflect — reported as no / marginal / good / best
    with the reason that decided it.

    Three things decide it, and radiant elevation is only one: the path length,
    the radiant's elevation **at the path midpoint** (where the reflection
    happens, not at either station), and the angle between the radiant and the
    path. That last one is the one usually left out and the one that makes a
    reflection geometrically possible at all — a trail reflects only where it
    is tangent to the ellipsoid with both stations at its foci, so a radiant
    broadside to the path works and one up- or down-path does not, at the very
    same elevation.

    Your own end can be left out when the host supplies it from the operator's
    station profile — ADIF's `MY_GRIDSQUARE`, or `MY_LAT` and `MY_LON` when the
    exact position is known. Those fields describe the **transmitting station**,
    not where the operator is sitting, which is what makes a remote operation
    come out right: the reflection geometry depends on where the antenna is.

    Args:
        their_grid: The other station's Maidenhead locator, e.g. "EM12".
        my_grid: Your locator. Omitted, it must come from your station profile.
        their_lat: The other station's latitude, if known exactly.
        their_lon: The other station's longitude.
        my_lat: Your latitude, if known exactly — preferred over a grid square,
            which is a rectangle this would otherwise have to take the centre of.
        my_lon: Your longitude.
        shower: Shower code, IAU number or name. Omitted, the one nearest its
            published peak is used and named in the answer.
        when: UTC start, ISO 8601. Omitted, now.
        hours: How far ahead to look. Default 12, at most 14 days.
        step_minutes: Sampling interval. Default 30.
    """
    moment = _parse_when(when)
    if moment is None:
        _err(f"'{when}' is not a time I can read. Use ISO 8601, e.g. 2026-08-12T02:00Z.")

    try:
        here_lat, here_lon, here_where = _endpoint(my_grid, my_lat, my_lon, "your own")
        there_lat, there_lon, there_where = _endpoint(
            their_grid, their_lat, their_lon, "the other station's")
    except EndpointError as error:
        _err(str(error))

    span = min(max(float(hours if hours is not None else 12.0), 0.0), MAX_HOURS)
    step = max(float(step_minutes if step_minutes is not None else 30.0), MIN_STEP_MINUTES)

    if shower:
        chosen = showers.find(str(shower))
        if chosen is None:
            _err(f"I do not have a shower called '{shower}' in the IAU MDC list. "
                        "meteor_showers lists what is there.")
        picked_how = "as asked"
    else:
        chosen = _nearest_peak(moment)
        if chosen is None:
            _err("No shower in the carried catalogue has a published maximum.")
        picked_how = "nearest its published peak; none was named"

    distance_km, bearing = geometry.great_circle(
        here_lat, here_lon, there_lat, there_lon)
    mid_lat, mid_lon = geometry.midpoint(here_lat, here_lon, there_lat, there_lon)

    rows: list[dict[str, Any]] = []
    steps = min(int(span * 60.0 / step) + 1, MAX_ROWS)
    for index in range(steps):
        at = moment.timestamp() + index * step * 60.0
        stamp = datetime.fromtimestamp(at, tz=timezone.utc).replace(microsecond=0)
        jd = sun.to_julian_day(stamp)
        azimuth, elevation = geometry.radiant_look(
            jd, chosen.radiant_ra_deg, chosen.radiant_dec_deg, mid_lat, mid_lon)
        verdict = geometry.assess(azimuth, elevation, bearing)
        rows.append({
            "time_utc": stamp.isoformat().replace("+00:00", "Z"),
            "radiant_azimuth_deg": round(azimuth, 1),
            "radiant_elevation_deg": round(elevation, 1),
            "offset_from_path_deg": round(verdict.offset_deg, 1),
            "verdict": verdict.verdict,
            "why": verdict.why,
        })

    workable = [row for row in rows if row["verdict"] in ("good", "best")]
    note = geometry.path_note(distance_km)
    offset = _days_until_peak(chosen, moment)

    distance_ok = geometry.MIN_PATH_KM <= distance_km <= geometry.MAX_PATH_KM
    slack = float(here_where["uncertainty_km"]) + float(there_where["uncertainty_km"])
    precision_note = _precision_note(distance_km, slack, here_where, there_where)
    summary = _summarise(rows, workable, note, chosen, offset, distance_ok)
    if precision_note:
        summary = f"{summary} {precision_note}"

    return {
        "summary": summary,
        "path": {
            "from": here_where,
            "to": there_where,
            "distance_km": round(distance_km, 1),
            "bearing_deg": round(bearing, 1),
            "reverse_bearing_deg": round((bearing + 180.0) % 360.0, 1),
            "midpoint": {"latitude": round(mid_lat, 3), "longitude": round(mid_lon, 3)},
            "single_hop_note": note,
            "workable_distance": distance_ok,
            "distance_uncertainty_km": round(slack, 1),
            "precision_note": precision_note,
        },
        "shower": _shower_payload(chosen, moment) | {"chosen": picked_how},
        "best_times_utc": [row["time_utc"] for row in workable],
        "rows": rows,
        "hours": span,
        "step_minutes": step,
        "how_to_read_this": (
            "The verdict is in words on purpose. The physics is a tangency condition on an "
            "ellipsoid with both stations at its foci, and what you actually hear also "
            "depends on your power, your antenna and the sporadic background — a score out "
            "of a hundred would imply a precision none of that supports. Point both "
            "antennas near the path bearing, not at the radiant."
        ),
        "radiant_source": _citation(),
    }


def _precision_note(distance_km: float, slack: float,
                    here: dict[str, Any], there: dict[str, Any]) -> str | None:
    """Say so when the locators are too coarse to decide the single-hop call.

    A locator may arrive with 4, 6 or 8 characters. Operators often state 6 or
    8 for their own station, while a structured on-air exchange may carry only
    4 — and which modes constrain it is not something to assert here. ADIF
    enumerates every mode and submode but says nothing about payload length or
    message structure, so there is no authority to infer precision from mode,
    and a hand-built table of which modes are fixed-length would be a guess
    wearing a schema. **4 is the safe floor for all of them.**

    So this assumes nothing: the slack is computed from the characters each
    locator actually carried. At the 4-character floor two square centres put
    the path length within about 200 km. That is
    small against a 1500 km path and decisive against a threshold: a path
    reported as 2250 km could be anywhere from roughly 2050 to 2450, which
    straddles the 2300 km single-hop limit.

    Reporting the distance as though it were exact would make the tool look
    more certain than the data it was given. So when a limit falls inside the
    slack, the answer says the call cannot be made at this precision and what
    would settle it.
    """
    if slack <= 0.0:
        return None
    bounds = ((geometry.MIN_PATH_KM, "minimum"), (geometry.MAX_PATH_KM, "single-hop"))
    for limit, name in bounds:
        if abs(distance_km - limit) < slack:
            ends = []
            for label, where in (("yours", here), ("theirs", there)):
                if where.get("precision_chars"):
                    ends.append(f"{label} {where['precision_chars']} characters")
            how = " and ".join(ends) if ends else "the locators given"
            return (
                f"That {distance_km:.0f} km is within {slack:.0f} km of the {name} "
                f"limit of {limit:.0f} km, and {how} — a grid square is a rectangle, so "
                f"the true distance could be roughly {distance_km - slack:.0f} to "
                f"{distance_km + slack:.0f} km. Whether this path is inside single hop "
                "cannot be decided at that precision. A 6-character locator or an exact "
                "position for either end would settle it — but get it from a sked page, "
                "QRZ or the operator directly rather than expecting it on the air, since "
                "an on-air exchange may not carry more than four characters."
            )
    return None


def _summarise(rows: list[dict[str, Any]], workable: list[dict[str, Any]],
               note: str | None, shower: showers.Shower, offset: float | None,
               distance_ok: bool) -> str:
    """One plain sentence an operator can act on.

    The path verdict comes first when the path cannot work. Radiant geometry is
    assessed independently of distance, so a path well past single hop can
    still have a radiant beautifully placed — and this sentence used to open
    with "workable for 7 of 7 sampled times" on a 2535 km path that is
    physically unusable, burying the only fact that mattered at the end. An
    operator reading the first clause would have gone and listened.
    """
    if not rows:
        return "No time span was asked for."
    if offset is None:
        when_text = shower.name
    elif abs(offset) < 1:
        when_text = f"{shower.name} is at its peak now"
    elif offset > 0:
        when_text = f"{shower.name} peaks in {offset:.0f} days"
    else:
        when_text = f"{shower.name} peaked {abs(offset):.0f} days ago"
    if not distance_ok:
        # The radiant can be perfectly placed and it will still not matter.
        return (f"{note} The radiant's position does not change that, so this "
                f"pair cannot work each other by single-hop meteor scatter. "
                f"{when_text}.")
    if note and not workable:
        return f"{note} {when_text}."
    if not workable:
        return (f"Nothing in this window: the radiant never gets into a geometry that can "
                f"reflect on this path. {when_text}.")
    # The strongest row, not the earliest that cleared the bar: "best" spans a
    # wide elevation band, and the first one in it is often the weakest.
    rank = {"best": 2, "good": 1}
    head = max(workable, key=lambda row: (rank.get(row["verdict"], 0),
                                          row["radiant_elevation_deg"]))
    text = (f"Workable for {len(workable)} of {len(rows)} sampled times; the best geometry is "
            f"around {head['time_utc']}, radiant "
            f"{head['radiant_elevation_deg']:.0f} degrees up "
            f"and {head['offset_from_path_deg']:.0f} degrees off the path. {when_text}.")
    return f"{text} {note}" if note else text


@mcp.tool(annotations=_ANSWERS_FROM_CARRIED_DATA)
def meteor_showers(when: str | None = None, limit: int | None = 12) -> dict[str, Any]:
    """Which showers are near their peak, closest first.

    The IAU MDC publishes each maximum as a solar longitude rather than a date,
    because solar longitude names the same point in the stream every year while
    a date drifts. The longitude is converted here to the date it falls on in
    the year asked about.

    Args:
        when: UTC instant to rank around, ISO 8601. Omitted, now.
        limit: How many to return. Default 12.
    """
    moment = _parse_when(when)
    if moment is None:
        _err(f"'{when}' is not a time I can read. Use ISO 8601.")
    count = max(1, min(int(limit) if limit is not None else 12, 200))

    rated: list[tuple[float, showers.Shower]] = []
    for item in showers.showers():
        offset = _days_until_peak(item, moment)
        if offset is not None:
            rated.append((abs(offset), item))
    rated.sort(key=lambda pair: pair[0])

    return {
        "as_of_utc": moment.isoformat().replace("+00:00", "Z"),
        "solar_longitude_deg": round(sun.solar_longitude(sun.to_julian_day(moment)), 3),
        "showers": [_shower_payload(item, moment) for _, item in rated[:count]],
        "catalogue_size": len(showers.showers()),
        "note": (
            "Ranked by distance from the published maximum, nearest first. Being near a "
            "peak is not the whole story for a contact — the radiant still has to be in a "
            "geometry that can reflect on your path. meteor_window answers that."
        ),
        "source": _citation(),
    }


@mcp.tool(annotations=_ANSWERS_FROM_CARRIED_DATA)
def meteor_shower_info(shower: str) -> dict[str, Any]:
    """Every published solution for one shower, unaveraged.

    The MDC carries several solutions per shower, each from a different study,
    with slightly different radiants and speeds. All of them are returned. None
    is blended, because the average of two published radiants is a third that
    nobody published and no paper stands behind.

    Args:
        shower: Code, IAU number or name — "PER", "7", "Perseids", "perseid".
    """
    found = showers.find(str(shower))
    if found is None:
        _err(f"I do not have a shower called '{shower}' in the IAU MDC list. "
                    "meteor_showers lists what is there.")
    moment = datetime.now(timezone.utc)
    every = showers.solutions(found.iau_number)
    return {
        "iau_number": found.iau_number,
        "code": found.code,
        "name": found.name,
        "activity": found.activity,
        "first_listed": _shower_payload(found, moment),
        "solutions": [
            {
                "solution": item.solution,
                "radiant_ra_deg": item.radiant_ra_deg,
                "radiant_dec_deg": item.radiant_dec_deg,
                "velocity_km_s": item.velocity_km_s,
                "solar_longitude_deg": item.solar_longitude_deg,
            }
            for item in every
        ],
        "solutions_available": len(every),
        "note": (
            "Several solutions means several published studies, not disagreement to be "
            "resolved here. They are listed as the owner lists them and never averaged."
        ),
        "source": _citation(),
    }


@mcp.tool(annotations=_READS_A_LIVE_SERVICE)
def meteor_activity() -> dict[str, Any]:
    """How many meteors the Global Meteor Network has actually confirmed today.

    A count of observed trajectories broken down by shower — not a flux
    density, which is a different quantity GMN computes separately. The file is
    written during the day, so an early read covers a partial day; the
    generation time is in the answer.

    This reads the network. Attribution is a condition of GMN's CC BY 4.0
    licence and is carried in the result.
    """
    try:
        return live.activity()
    except live.LiveError as error:
        _err(f"The Global Meteor Network could not be read: {error}.")


@mcp.tool(annotations=_READS_A_LIVE_SERVICE)
def meteor_fireballs(limit: int | None = 10) -> dict[str, Any]:
    """Recent fireballs recorded by NASA CNEOS.

    Bolides bright enough to be detected from orbit — the "did anyone else see
    that" events, not a meteor rate. Reads the network.

    Args:
        limit: How many of the most recent to return. Default 10, at most 100.
    """
    try:
        return live.fireballs(int(limit) if limit is not None else 10)
    except live.LiveError as error:
        _err(f"NASA CNEOS could not be read: {error}.")
    except (TypeError, ValueError):
        _err("limit must be a whole number.")


@mcp.tool(annotations=_ANSWERS_FROM_CARRIED_DATA)
def meteor_source_info() -> dict[str, Any]:
    """Where every number in this server comes from, and how to cite it.

    The shower list is the IAU Meteor Data Center's, carried in the package
    with its checksum so the exact edition served is identifiable. The live
    sources are named with their licences. Nothing here is this project's own
    measurement, and the citations are the owners' own.
    """
    info = dict(showers.source())
    info["carried_showers"] = len(showers.showers())
    # The checksum is per-document in the provenance block; lift the one for
    # the file actually served so a caller can identify the edition without
    # having to know the shape of that block.
    published = info.get("published", {})
    served = published.get(info.get("document", ""), {})
    info["sha256"] = served.get("sha256")
    info["computed_locally"] = [
        "radiant azimuth and elevation at the path midpoint",
        "great-circle distance, bearing and midpoint",
        "solar longitude and the calendar date of each published maximum",
        "whether the geometry can reflect on a given path",
    ]
    return info


def _version_info_payload() -> dict[str, Any]:
    return {
        "service_name": "meteor-mcp",
        "service_version": __version__,
        "spec_version": f"IAU MDC {showers.source().get('edition', 'unknown')}",
    }


@mcp.tool(annotations=_ANSWERS_FROM_CARRIED_DATA)
def get_version_info() -> dict[str, Any]:
    """This server's version and the edition of the shower list it carries."""
    return _version_info_payload()


def main() -> None:
    if "--version" in sys.argv:
        info = _version_info_payload()
        print(f"{info['service_name']} {info['service_version']} ({info['spec_version']})")
        return
    mcp.run()


if __name__ == "__main__":
    main()
