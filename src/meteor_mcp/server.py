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
from typing import Any

from fastmcp import FastMCP

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


def _err(message: str) -> dict[str, Any]:
    return {"error": message}


def _parse_when(when: str | None) -> datetime | None:
    """A UTC instant, or now. None means the text could not be read."""
    if not when:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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


@mcp.tool()
def meteor_window(
    my_grid: str,
    their_grid: str,
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

    Args:
        my_grid: Your Maidenhead locator, e.g. "DN13" or "DN13la".
        their_grid: The other station's locator.
        shower: Shower code, IAU number or name. Omitted, the one nearest its
            published peak is used and named in the answer.
        when: UTC start, ISO 8601. Omitted, now.
        hours: How far ahead to look. Default 12, at most 14 days.
        step_minutes: Sampling interval. Default 30.
    """
    moment = _parse_when(when)
    if moment is None:
        return _err(f"'{when}' is not a time I can read. Use ISO 8601, e.g. 2026-08-12T02:00Z.")

    try:
        here = grid.place(str(my_grid))
        there = grid.place(str(their_grid))
    except grid.GridError as error:
        return _err(str(error))

    span = min(max(float(hours if hours is not None else 12.0), 0.0), MAX_HOURS)
    step = max(float(step_minutes if step_minutes is not None else 30.0), MIN_STEP_MINUTES)

    if shower:
        chosen = showers.find(str(shower))
        if chosen is None:
            return _err(f"I do not have a shower called '{shower}' in the IAU MDC list. "
                        "meteor_showers lists what is there.")
        picked_how = "as asked"
    else:
        chosen = _nearest_peak(moment)
        if chosen is None:
            return _err("No shower in the carried catalogue has a published maximum.")
        picked_how = "nearest its published peak; none was named"

    distance_km, bearing = geometry.great_circle(
        here.latitude, here.longitude, there.latitude, there.longitude)
    mid_lat, mid_lon = geometry.midpoint(
        here.latitude, here.longitude, there.latitude, there.longitude)

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

    summary = _summarise(rows, workable, note, chosen, offset)

    return {
        "summary": summary,
        "path": {
            "from": str(my_grid).upper(),
            "to": str(their_grid).upper(),
            "distance_km": round(distance_km, 1),
            "bearing_deg": round(bearing, 1),
            "reverse_bearing_deg": round((bearing + 180.0) % 360.0, 1),
            "midpoint": {"latitude": round(mid_lat, 3), "longitude": round(mid_lon, 3)},
            "single_hop_note": note,
            "workable_distance": geometry.MIN_PATH_KM <= distance_km <= geometry.MAX_PATH_KM,
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


def _summarise(rows: list[dict[str, Any]], workable: list[dict[str, Any]],
               note: str | None, shower: showers.Shower, offset: float | None) -> str:
    """One plain sentence an operator can act on."""
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
            f"around {head['time_utc']}, radiant {head['radiant_elevation_deg']:.0f} degrees up "
            f"and {head['offset_from_path_deg']:.0f} degrees off the path. {when_text}.")
    return f"{text} {note}" if note else text


@mcp.tool()
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
        return _err(f"'{when}' is not a time I can read. Use ISO 8601.")
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


@mcp.tool()
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
        return _err(f"I do not have a shower called '{shower}' in the IAU MDC list. "
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


@mcp.tool()
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
        return _err(f"The Global Meteor Network could not be read: {error}.")


@mcp.tool()
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
        return _err(f"NASA CNEOS could not be read: {error}.")
    except (TypeError, ValueError):
        return _err("limit must be a whole number.")


@mcp.tool()
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


@mcp.tool()
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
