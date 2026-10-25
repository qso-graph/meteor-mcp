"""The arithmetic, against things known independently of this code.

Two modules here compute rather than look up — `sun` converts between solar
longitude and the calendar, and `geometry` decides whether a path can reflect.
Both are checked against facts that exist outside this repository: the shower
peak dates every operator knows, and the physics of specular reflection.

Each group carries a **control** — a test that fails if the check above it has
been loosened into something that passes on anything. Two of them are here
because the bug they describe actually happened during the build.
"""

from __future__ import annotations

import pytest

from meteor_mcp import geometry, showers, sun

# Peak dates from outside this code: these are the dates in every meteor
# calendar and almanac. The catalogue stores only a solar longitude, so if the
# conversion is wrong these move.
KNOWN_PEAKS = [
    ("QUA", 1, (2, 5)),    # Quadrantids, 3-4 January
    ("LYR", 4, (21, 24)),  # April Lyrids, 22-23 April
    ("PER", 8, (11, 14)),  # Perseids, 12-13 August
    ("ORI", 10, (20, 23)),  # Orionids, 21-22 October
    ("LEO", 11, (16, 19)),  # Leonids, 17-18 November
    ("GEM", 12, (12, 15)),  # Geminids, 13-14 December
    ("URS", 12, (21, 24)),  # Ursids, 22-23 December
]


MONTHS = ("January February March April May June July August September "
          "October November December").split()


class TestSolarLongitude:
    @pytest.mark.parametrize("code,month,day_range", KNOWN_PEAKS)
    def test_the_catalogue_longitude_lands_on_the_known_date(
            self, code: str, month: int, day_range: tuple[int, int]) -> None:
        """MET-001: the MDC's solar longitude converts to the date hams know.

        The catalogue publishes a longitude and no date, deliberately — a date
        drifts between years and a longitude does not. That makes the known
        dates a free oracle for the conversion.
        """
        shower = showers.find(code)
        assert shower is not None, code
        assert shower.solar_longitude_deg is not None, code
        peak = sun.peak_date(shower.solar_longitude_deg, 2026)
        low, high = day_range
        assert peak.month == month and low <= peak.day <= high, (
            f"{code}: solar longitude {shower.solar_longitude_deg} converted to "
            f"{peak:%d %B}, but it is known to peak {low}-{high} "
            f"{MONTHS[month - 1]}")

    def test_a_longitude_past_180_is_not_half_an_orbit_out(self) -> None:
        """MET-002: the control, and a bug that really happened.

        The first inversion bisected on a residual wrapped to plus or minus
        180 degrees. Any year-long window holds two sign changes in that
        residual — the root being sought and the wrap discontinuity — and
        bisection cannot tell them apart. It chose wrong, and every shower past
        180 degrees came back exactly half an orbit out: the Quadrantids
        peaked in July.

        Both halves of the circle are asserted, because the old code passed
        everything below 180 and would have passed a test that only looked
        there.
        """
        assert sun.peak_date(283.28, 2026).month == 1, "Quadrantids are not a July shower"
        assert sun.peak_date(261.60, 2026).month == 12, "Geminids are not a June shower"
        assert sun.peak_date(139.70, 2026).month == 8, "Perseids are an August shower"

    def test_the_conversion_round_trips(self) -> None:
        """MET-003: longitude to date to longitude, all the way round."""
        for longitude in (0.1, 32.2, 139.7, 179.9, 180.1, 208.7, 283.28, 359.9):
            back = sun.solar_longitude(sun.to_julian_day(sun.peak_date(longitude, 2026)))
            assert sun.degrees_apart(back, longitude) < 1e-4, longitude

    def test_every_longitude_lands_in_the_year_asked_for(self) -> None:
        """MET-004: the whole circle, not just the convenient part.

        Solar longitude is zero at the March equinox, so one pass through 360
        degrees straddles two calendar years. Asking for a year must give that
        year.
        """
        for longitude in range(0, 360, 3):
            assert sun.peak_date(float(longitude), 2026).year == 2026, longitude

    def test_julian_day_round_trips(self) -> None:
        """MET-005: the date arithmetic underneath all of it."""
        from datetime import datetime, timezone
        for moment in (datetime(2026, 1, 1, tzinfo=timezone.utc),
                       datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc),
                       datetime(2024, 2, 29, 12, 0, tzinfo=timezone.utc),
                       datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc)):
            back = sun.from_julian_day(sun.to_julian_day(moment))
            assert abs((back - moment).total_seconds()) < 1.5, moment


class TestReflectionGeometry:
    def test_a_radiant_below_the_horizon_cannot_work(self) -> None:
        """MET-010: no trails below the horizon, whatever else is true."""
        assert geometry.assess(0.0, -1.0, 90.0).verdict == "no"
        assert geometry.assess(0.0, -45.0, 90.0).verdict == "no"

    def test_broadside_beats_along_path_at_the_very_same_elevation(self) -> None:
        """MET-011: the control for the factor that is usually left out.

        A trail reflects specularly only where it is tangent to the ellipsoid
        with both stations at its foci. Trails running *along* the path can
        never be tangent to it; trails running *across* it can. So with the
        radiant elevation held identical, broadside must beat up-path.

        If this passes for both, the server is grading on elevation alone and
        the third factor is decorative.
        """
        elevation, bearing = 40.0, 90.0
        broadside = geometry.assess(0.0, elevation, bearing)    # 90 degrees off
        along = geometry.assess(90.0, elevation, bearing)       # 0 degrees off
        assert broadside.offset_deg > along.offset_deg
        assert broadside.verdict == "best"
        assert along.verdict == "marginal"
        assert "path bearing" in along.why

    def test_nearly_overhead_is_not_ideal_either(self) -> None:
        """MET-012: high is not simply better; trails run down the path."""
        assert geometry.assess(0.0, 85.0, 90.0).verdict == "marginal"

    def test_the_offset_folds_so_either_end_counts_the_same(self) -> None:
        """MET-013: 180 degrees from the path is along it, same as 0.

        What matters is along-versus-across, not which end of the path the
        radiant sits beyond.
        """
        assert geometry.angle_between(0.0, 180.0) == pytest.approx(0.0)
        assert geometry.angle_between(0.0, 0.0) == pytest.approx(0.0)
        assert geometry.angle_between(0.0, 90.0) == pytest.approx(90.0)
        assert geometry.angle_between(0.0, 270.0) == pytest.approx(90.0)
        assert geometry.assess(10.0, 40.0, 190.0).offset_deg == \
            pytest.approx(geometry.assess(10.0, 40.0, 10.0).offset_deg)

    def test_path_length_limits_are_stated_not_silent(self) -> None:
        """MET-014: too short and too long each get said out loud."""
        assert "short" in (geometry.path_note(150.0) or "")
        assert "beyond" in (geometry.path_note(3000.0) or "")
        assert geometry.path_note(1200.0) is None          # squarely in the best range
        assert "outside" in (geometry.path_note(2200.0) or "")  # workable, not ideal

    def test_great_circle_against_a_known_pair(self) -> None:
        """MET-015: distance and bearing, checked against a known separation.

        One degree of latitude is 111.2 km along a meridian, due north.
        """
        distance, bearing = geometry.great_circle(43.0, -117.0, 44.0, -117.0)
        assert distance == pytest.approx(111.2, abs=0.5)
        assert bearing == pytest.approx(0.0, abs=0.01)

    def test_the_midpoint_is_between_the_ends(self) -> None:
        """MET-016: the reflection happens near the middle, so it must be there."""
        mid_lat, mid_lon = geometry.midpoint(43.5, -117.0, 33.5, -97.0)
        assert 33.5 < mid_lat < 43.5
        assert -117.0 < mid_lon < -97.0

    def test_the_radiant_is_treated_as_being_at_infinity(self) -> None:
        """MET-017: no parallax, unlike the moon.

        A shower radiant is effectively infinitely far away, so two observers
        at the same sidereal time see it in the same direction. Applying a
        parallax correction meant for the moon would be a quiet error, so the
        absence of one is asserted.
        """
        jd = sun.to_julian_day(sun.from_julian_day(2461000.5))
        here = geometry.radiant_look(jd, 47.77, 57.79, 43.5, -117.0)
        # Same place, an hour of longitude away, an hour earlier in time: the
        # same local sidereal time, so the same look angle.
        there = geometry.radiant_look(jd - 1.0 / 24.0, 47.77, 57.79, 43.5, -102.0)
        assert here[0] == pytest.approx(there[0], abs=0.2)
        assert here[1] == pytest.approx(there[1], abs=0.2)
