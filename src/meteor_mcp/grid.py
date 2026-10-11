"""Maidenhead locators, the way operators give their position.

An EME operator says "DN13" or "DN13la", not a latitude. Every tool here takes
a locator and converts once, at the edge.

A locator names a rectangle, not a point, so the centre is used — the honest
reading, and the one that keeps a 4-character locator from being treated as
more precise than it is. A 4-character square is about 1 degree of latitude by
2 of longitude: roughly 110 by 160 km at mid latitudes. For the moon that is
irrelevant to within a tenth of a degree of pointing, which is why 4 characters
are enough for EME; for a mutual window between two stations it is also why
neither station's exact spot in the square matters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Two letters, two digits, then optionally two more letters. Longer locators
# exist (10 and 12 characters); they are accepted and read to the precision
# this understands rather than refused, because a station that sends one is not
# wrong, it is just more precise than EME needs.
_LOCATOR = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2}([0-9]{2})?)?$", re.IGNORECASE)


class GridError(ValueError):
    """The locator could not be read. The message is safe to show a user."""


@dataclass(frozen=True)
class Place:
    """Where a locator puts you: the centre of its square."""
    locator: str
    latitude: float
    longitude: float


def valid_locator(locator: str) -> bool:
    """Whether this looks like a Maidenhead locator."""
    return bool(_LOCATOR.match(str(locator).strip()))


def place(locator: str) -> Place:
    """The centre of a Maidenhead locator's square.

    Raises GridError rather than returning a wrong position: a silently
    mis-read locator points a dish at nothing.
    """
    text = str(locator).strip().upper()
    if not _LOCATOR.match(text):
        raise GridError(
            f"{locator!r} is not a Maidenhead locator. "
            "Expected two letters, two digits, and optionally two more letters "
            "(for example DN13 or DN13la)."
        )

    # Field: 20 degrees of longitude, 10 of latitude.
    longitude = (ord(text[0]) - ord("A")) * 20.0 - 180.0
    latitude = (ord(text[1]) - ord("A")) * 10.0 - 90.0
    # Square: 2 degrees of longitude, 1 of latitude.
    longitude += int(text[2]) * 2.0
    latitude += int(text[3]) * 1.0

    if len(text) >= 6:
        # Subsquare: 5 minutes of longitude, 2.5 of latitude.
        longitude += (ord(text[4]) - ord("A")) * (2.0 / 24.0)
        latitude += (ord(text[5]) - ord("A")) * (1.0 / 24.0)
        if len(text) >= 8:
            longitude += int(text[6]) * (2.0 / 240.0)
            latitude += int(text[7]) * (1.0 / 240.0)
            size_lon, size_lat = 2.0 / 240.0, 1.0 / 240.0
        else:
            size_lon, size_lat = 2.0 / 24.0, 1.0 / 24.0
    else:
        size_lon, size_lat = 2.0, 1.0

    # The centre of the square, not its south-west corner.
    return Place(text, latitude + size_lat / 2.0, longitude + size_lon / 2.0)
