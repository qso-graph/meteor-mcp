"""Solar longitude, and the calendar date a shower peaks on.

The MDC gives each shower's maximum as a **solar longitude**, not a date, and
that is the right way round: solar longitude is where the Earth is in its
orbit, so it names the same point in the meteoroid stream every year. A date
drifts — leap years alone move it by most of a day — which is why the
catalogue does not publish one.

So the catalogue keeps its longitude and this module converts, in both
directions:

* `solar_longitude(jd)` — where the Earth is now, so "what is near its peak
  today" can be answered from the owner's own number.
* `peak_date(longitude, year)` — the instant in a given year when the Earth
  reaches that longitude, found by bisection on the function above.

Meeus ch. 25, the low-precision series: good to about 0.01 degrees, which is
roughly 15 minutes of Earth travel. A shower's activity is days wide, so this
is far finer than the question needs.

Standard library only. No network.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

D2R = math.pi / 180.0


def julian_day(year: int, month: int, day: float) -> float:
    """Meeus 7.3, Gregorian calendar."""
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1))
            + day + b - 1524.5)


def to_julian_day(moment: datetime) -> float:
    """A UTC datetime as a Julian day."""
    moment = moment.astimezone(timezone.utc)
    fraction = (moment.hour + moment.minute / 60.0
                + (moment.second + moment.microsecond / 1e6) / 3600.0) / 24.0
    return julian_day(moment.year, moment.month, moment.day + fraction)


def from_julian_day(jd: float) -> datetime:
    """The inverse, to the second. Meeus ch. 7."""
    jd += 0.5
    z, f = int(jd), jd - int(jd)
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    whole = int(day)
    seconds = round((day - whole) * 86400.0)
    return (datetime(year, month, whole, tzinfo=timezone.utc)
            + timedelta(seconds=seconds))


def solar_longitude(jd: float) -> float:
    """The Sun's apparent geocentric longitude in degrees, 0-360.

    This is the Earth's position in its orbit expressed the way meteor
    astronomy expresses it. Meeus ch. 25 low-precision series.
    """
    t = (jd - 2451545.0) / 36525.0
    # Geometric mean longitude and the Sun's mean anomaly.
    mean_longitude = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    anomaly = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    m = anomaly * D2R
    # Equation of the centre.
    centre = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
              + (0.019993 - 0.000101 * t) * math.sin(2 * m)
              + 0.000289 * math.sin(3 * m))
    true_longitude = mean_longitude + centre
    # Apparent longitude: nutation and aberration.
    omega = 125.04 - 1934.136 * t
    apparent = true_longitude - 0.00569 - 0.00478 * math.sin(omega * D2R)
    return apparent % 360.0


# Degrees of solar longitude the Earth covers per day, on average.
DEGREES_PER_DAY = 360.0 / 365.2422


def _refine(jd: float, target: float) -> float:
    """Walk a close guess onto the exact longitude.

    A fixed-point step, not bisection. Bisection on a wrapped angle is a trap:
    the residual jumps from +180 to -180 somewhere in any year-long window, so
    such a window holds two sign changes — the root being sought and the
    discontinuity — and bisection has no way to tell them apart. It picked the
    wrong one, and every shower past 180 degrees of longitude came back half an
    orbit out. Starting within a couple of days of the answer keeps the
    residual small, where the wrap cannot be reached at all.
    """
    for _ in range(60):
        error = (target - solar_longitude(jd) + 180.0) % 360.0 - 180.0
        if abs(error) < 1e-9:
            break
        jd += error / DEGREES_PER_DAY
    return jd


def peak_date(longitude: float, year: int) -> datetime:
    """When in `year` the Earth reaches this solar longitude.

    Solar longitude is zero at the March equinox, so one pass through all 360
    degrees straddles two calendar years: a shower at 283 degrees (the
    Quadrantids) is reached in the January *after* the March it is measured
    from. Both anchors are therefore tried and the one landing in the year
    asked for is returned.
    """
    target = float(longitude) % 360.0
    attempt = None
    for anchor in (year, year - 1):
        start = julian_day(anchor, 3, 20.0)
        guess = start + ((target - solar_longitude(start)) % 360.0) / DEGREES_PER_DAY
        attempt = from_julian_day(_refine(guess, target))
        if attempt.year == year:
            return attempt
    assert attempt is not None
    return attempt


def degrees_apart(a: float, b: float) -> float:
    """The shorter way round between two longitudes, 0-180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)
