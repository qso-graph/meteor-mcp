"""Meteor scatter geometry: when can these two stations actually work each other.

The question an operator asks is not "is the radiant up". It is "can I work
EM12 from DN13 on the Perseids tonight, and when". Three things decide that,
and only one of them is the radiant's elevation.

1. **Path length.** Meteor trails burn at about 85-120 km. A single-hop
   reflection off something that low works from roughly 500 km to about
   2300 km. Under 500 km the reflection point would have to be almost
   overhead and there is very little sky that qualifies; past ~2300 km the
   reflection point sits below both horizons.

2. **Radiant elevation, seen from the path midpoint** — not from either
   station. The reflection happens near the middle, so that is where the sky
   matters. Below the horizon there are no trails to reflect from. Very high
   is also poor: trails then run down the path rather than across it.

3. **The angle between the radiant and the path.** This is the one that gets
   left out, and it is the one that decides whether a reflection is
   geometrically possible at all. A trail reflects specularly only where it is
   tangent to the ellipsoid with the two stations at its foci. Trails running
   *along* the path can never be tangent to it; trails running *across* it can.
   So a radiant broadside to the path is good and a radiant up- or down-path is
   poor, at the same elevation.

Standard library only, and no network: the radiant comes from the IAU MDC data
the package carries (see data/SOURCE.json), and everything here is arithmetic
over it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

D2R = math.pi / 180.0
R2D = 180.0 / math.pi
EARTH_RADIUS_KM = 6371.0

# Where meteors burn, and so where a reflection can happen.
TRAIL_HEIGHT_KM = 100.0

# Single-hop limits. Under the first, almost no sky qualifies; past the second
# the reflection point is below the horizon at both ends.
MIN_PATH_KM = 400.0
MAX_PATH_KM = 2300.0
# Where the geometry is at its best, and what hams actually run.
BEST_PATH_KM = (800.0, 2000.0)


def great_circle(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Distance in km and initial bearing in degrees, A to B."""
    p1, p2 = lat1 * D2R, lat2 * D2R
    dl = (lon2 - lon1) * D2R
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    distance = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    bearing = math.atan2(math.sin(dl) * math.cos(p2),
                         math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))
    return distance, (bearing * R2D) % 360.0


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """The great-circle midpoint — where the reflection happens."""
    p1, p2 = lat1 * D2R, lat2 * D2R
    l1, dl = lon1 * D2R, (lon2 - lon1) * D2R
    bx = math.cos(p2) * math.cos(dl)
    by = math.cos(p2) * math.sin(dl)
    lat = math.atan2(math.sin(p1) + math.sin(p2),
                     math.sqrt((math.cos(p1) + bx) ** 2 + by ** 2))
    lon = l1 + math.atan2(by, math.cos(p1) + bx)
    return lat * R2D, ((lon * R2D + 540) % 360) - 180


def local_sidereal(jd: float, longitude: float) -> float:
    """Local apparent sidereal time in degrees."""
    t = (jd - 2451545.0) / 36525.0
    theta = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
             + 0.000387933 * t * t - t ** 3 / 38710000.0)
    return (theta + longitude) % 360.0


def radiant_look(jd: float, ra: float, dec: float,
                 latitude: float, longitude: float) -> tuple[float, float]:
    """A radiant's azimuth and elevation from a place.

    A shower radiant is effectively at infinity, so unlike the moon there is no
    parallax to apply: the same RA and Dec serve every observer.
    """
    hour_angle = (local_sidereal(jd, longitude) - ra) % 360.0
    h, d, p = hour_angle * D2R, dec * D2R, latitude * D2R
    azimuth = math.atan2(math.sin(h),
                         math.cos(h) * math.sin(p) - math.tan(d) * math.cos(p))
    elevation = math.asin(math.sin(p) * math.sin(d)
                          + math.cos(p) * math.cos(d) * math.cos(h))
    return (azimuth * R2D + 180.0) % 360.0, elevation * R2D


@dataclass(frozen=True)
class Geometry:
    """What the sky is doing for this particular path, at one moment."""
    radiant_azimuth: float
    radiant_elevation: float
    path_bearing: float
    # 0 means the radiant lies along the path, 90 means broadside to it.
    offset_deg: float
    verdict: str
    why: str


def angle_between(a: float, b: float) -> float:
    """The smaller angle between two bearings, folded to 0-90.

    Folded because a radiant 180 degrees from the path is along it just as
    surely as one at 0; what matters is along-versus-across, not which end.
    """
    difference = abs((a - b + 180.0) % 360.0 - 180.0)
    return 90.0 - abs(difference - 90.0)


def assess(radiant_azimuth: float, radiant_elevation: float,
           path_bearing: float) -> Geometry:
    """Plain words about this geometry, and the reason for them.

    Deliberately not a score out of a hundred. The underlying physics is a
    tangency condition on an ellipsoid, and the numbers a station actually
    gets also depend on its power, antenna and the sporadic background. A
    figure like "73" would imply a precision nothing here supports. The
    measurable parts are reported and the verdict says which of them decided
    it.
    """
    offset = angle_between(radiant_azimuth, path_bearing)

    if radiant_elevation <= 0:
        return Geometry(radiant_azimuth, radiant_elevation, path_bearing, offset,
                        "no", "the radiant is below the horizon at the path midpoint")
    if radiant_elevation < 15:
        quality, why = "marginal", "the radiant is barely up; few trails are high enough to reflect"
    elif radiant_elevation > 70:
        quality, why = "marginal", "the radiant is nearly overhead, so trails run down the path rather than across it"
    else:
        quality, why = "good", "the radiant is well placed in elevation"

    if offset < 30:
        if quality == "good":
            quality, why = "marginal", "the radiant lies close to the path bearing, so few trails can be tangent to it"
        else:
            why += ", and it lies close to the path bearing"
    elif offset > 60 and quality == "good":
        quality = "best"
        why = "the radiant is well up and broadside to the path, which is the geometry that reflects"

    return Geometry(radiant_azimuth, radiant_elevation, path_bearing, offset, quality, why)


def path_note(distance_km: float) -> str | None:
    """Whether this path is workable at all by single-hop meteor scatter."""
    if distance_km < MIN_PATH_KM:
        return (f"{distance_km:.0f} km is short for meteor scatter: under about "
                f"{MIN_PATH_KM:.0f} km the reflection point would have to be nearly "
                "overhead, and very little sky qualifies. Tropo or sporadic-E is the "
                "usual path at this range.")
    if distance_km > MAX_PATH_KM:
        return (f"{distance_km:.0f} km is beyond single-hop meteor scatter: past about "
                f"{MAX_PATH_KM:.0f} km a trail at {TRAIL_HEIGHT_KM:.0f} km is below the "
                "horizon from both ends.")
    low, high = BEST_PATH_KM
    if not low <= distance_km <= high:
        return (f"{distance_km:.0f} km is workable but outside the {low:.0f}-{high:.0f} km "
                "range where the geometry is most favourable.")
    return None
