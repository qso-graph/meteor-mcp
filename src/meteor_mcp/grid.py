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

# ADIF's MY_GRIDSQUARE permits 2, 4, 6 or 8 characters, with 10 and 12
# character locators split across MY_GRIDSQUARE and MY_GRIDSQUARE_EXT. All of
# those are read here, to the precision each actually carries — a station that
# sends a longer locator is not wrong, just more precise than this needs, and
# one that sends a 2-character field is not wrong either, only very coarse.
# Whether a given precision is good enough is the caller's judgement, not this
# module's, so `Place` reports it rather than this refusing it.
_LOCATOR = re.compile(r"^[A-R]{2}([0-9]{2}([A-X]{2}([0-9]{2})?)?)?$", re.IGNORECASE)


class GridError(ValueError):
    """The locator could not be read. The message is safe to show a user."""


@dataclass(frozen=True)
class Place:
    """Where a locator puts you: the centre of its square.

    `precision_chars` is how many characters the locator carried, because how
    coarse it is decides what it can be used for. A 2-character field is 10 by
    20 degrees — around 1100 km across, wider than the whole usable
    meteor-scatter path range — so a caller computing a path has to be able to
    tell that apart from a 4-character square.
    """
    locator: str
    latitude: float
    longitude: float
    precision_chars: int = 4


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
            f"{locator!r} is not a Maidenhead locator. Expected two letters, "
            "then optionally two digits, two more letters and two more digits "
            "(for example DN, DN13, DN13la or DN13la12)."
        )

    # Field: 20 degrees of longitude, 10 of latitude.
    longitude = (ord(text[0]) - ord("A")) * 20.0 - 180.0
    latitude = (ord(text[1]) - ord("A")) * 10.0 - 90.0

    if len(text) == 2:
        # A bare field, which ADIF permits. Nothing further to add, and the
        # centre of a 10-by-20-degree box is all it can honestly give.
        return Place(text, latitude + 5.0, longitude + 10.0, 2)

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
    return Place(text, latitude + size_lat / 2.0, longitude + size_lon / 2.0,
                 len(text))
