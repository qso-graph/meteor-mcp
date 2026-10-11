"""The shower facts this package carries, as the IAU MDC publishes them.

The MDC lists **several solutions per shower**, each from a published study,
with slightly different radiants and velocities. They are all kept, and none
is blended: averaging two published radiants would produce a third that nobody
published. Solution "000" is the one the MDC lists first and is what a tool
returns unless asked otherwise — labelled, with the others counted so a caller
knows they exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any


@dataclass(frozen=True)
class Shower:
    """One published solution for one shower."""
    iau_number: int
    code: str
    name: str
    solution: str
    activity: str
    radiant_ra_deg: float
    radiant_dec_deg: float
    velocity_km_s: float | None
    solar_longitude_deg: float | None
    solutions_available: int


def _read(*parts: str) -> Any:
    resource = files("meteor_mcp.data")
    for part in parts:
        resource = resource / part
    return json.loads(resource.read_text(encoding="utf-8"))


@cache
def source() -> dict[str, Any]:
    """Who owns this list, which edition is served, and how they ask to be cited."""
    data: dict[str, Any] = _read("SOURCE.json")
    return data


@cache
def _all() -> dict[int, list[dict[str, Any]]]:
    data = _read("facts", "showers.json")
    return {entry["iau_number"]: entry["solutions"] for entry in data["showers"]}


def _as_shower(row: dict[str, Any], available: int) -> Shower | None:
    if row.get("radiant_ra_deg") is None or row.get("radiant_dec_deg") is None:
        return None
    return Shower(
        iau_number=row["iau_number"],
        code=row["code"],
        name=row["name"],
        solution=row["solution"],
        activity=row["activity"],
        radiant_ra_deg=row["radiant_ra_deg"],
        radiant_dec_deg=row["radiant_dec_deg"],
        velocity_km_s=row.get("velocity_km_s"),
        solar_longitude_deg=row.get("solar_longitude_deg"),
        solutions_available=available,
    )


@cache
def showers() -> list[Shower]:
    """Every shower, one entry each: the MDC's first-listed solution."""
    out: list[Shower] = []
    for number, rows in sorted(_all().items()):
        for row in rows:
            shower = _as_shower(row, len(rows))
            if shower is not None:
                out.append(shower)
                break
    return out


def find(key: str) -> Shower | None:
    """A shower by its three-letter code, IAU number, or name."""
    text = str(key).strip().lower()
    for shower in showers():
        if text in (shower.code.lower(), str(shower.iau_number), shower.name.lower()):
            return shower
    # A partial name, so "perseid" finds the Perseids. Exact matches win above.
    for shower in showers():
        if text and text in shower.name.lower():
            return shower
    return None


def solutions(iau_number: int) -> list[Shower]:
    """Every published solution for one shower, unblended."""
    rows = _all().get(iau_number, [])
    found = [_as_shower(row, len(rows)) for row in rows]
    return [s for s in found if s is not None]
