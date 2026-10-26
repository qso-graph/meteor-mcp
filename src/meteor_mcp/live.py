"""The two things that have to be fetched, because they report right now.

Everything else this server answers is computed from carried data and needs no
network. These two do not have that option: a meteor rate an hour old is not
the meteor rate, and a fireball that fell this morning is not in any file we
ship.

Both sources are public and need no credential. Both are credited in the
answer, not only in the README — for the Global Meteor Network that is a
condition of CC BY 4.0, and for NASA CNEOS it is courtesy.

**On TLS.** Verification is on, and the roots come from `certifi` rather than
whichever store the running Python happens to have been built against. That is
not belt-and-braces: NASA's API chains to a Sectigo root that an older system
OpenSSL store does not carry, so on a machine with a stale store the fireball
tool fails to connect while the GMN one succeeds. Carrying a current root set
is the fix. Verification is never disabled — a meteor count is not worth a
silent downgrade to an unauthenticated connection.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from functools import cache
from typing import Any

import certifi

from . import ratelimit

# Said once, here. A source that cannot identify who is calling it cannot ask
# us to slow down, and a ham radio project should be reachable.
USER_AGENT = "meteor-mcp (+https://github.com/qso-graph/meteor-mcp; maintainers@qso-graph.io)"

CNEOS_FIREBALLS = "https://ssd-api.jpl.nasa.gov/fireball.api"
GMN_HOME = "https://globalmeteornetwork.org/"
GMN_DAILY = ("https://globalmeteornetwork.org/data/traj_summary_data/daily/"
             "traj_summary_latest_daily.txt")

TIMEOUT_SECONDS = 20


class LiveError(RuntimeError):
    """A live source could not be read. The message is safe to show a user."""


@cache
def _context() -> ssl.SSLContext:
    """A verifying context with a current root set. Built once."""
    return ssl.create_default_context(cafile=certifi.where())


def _fetch(url: str) -> str:
    """Text from a URL, or a LiveError whose message gives nothing away."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ratelimit.wait()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS,
                                    context=_context()) as response:
            text: str = response.read().decode("utf-8", errors="replace")
            return text
    except urllib.error.HTTPError as error:
        # The status only. A server's error body can echo the request back, and
        # nothing from it belongs in an answer.
        raise LiveError(f"the source answered {error.code}") from None
    except (urllib.error.URLError, TimeoutError, ssl.SSLError):
        raise LiveError("the source could not be reached") from None


def _fetch_json(url: str) -> Any:
    try:
        return json.loads(_fetch(url))
    except json.JSONDecodeError:
        raise LiveError("the source did not answer with JSON") from None


def fireballs(limit: int = 10) -> dict[str, Any]:
    """Recent bolides recorded by NASA CNEOS.

    These are the big ones — events bright enough to be detected from orbit —
    so this is not a meteor rate. It is what a ham means by "did anyone else
    see that".
    """
    count = max(1, min(int(limit), 100))
    data = _fetch_json(f"{CNEOS_FIREBALLS}?limit={count}")
    fields = data.get("fields") or []
    rows = data.get("data") or []
    events = [dict(zip(fields, row)) for row in rows]
    return {
        "count": len(events),
        "fireballs": events,
        "source": {
            "owner": "NASA/JPL Center for Near-Earth Object Studies (CNEOS)",
            "url": CNEOS_FIREBALLS,
            "note": "Public US government data; no authentication required.",
        },
    }


def activity() -> dict[str, Any]:
    """What the Global Meteor Network has actually seen in the last day.

    **A count, not a flux.** GMN's daily file is one row per confirmed
    trajectory, each tagged with the IAU shower it belongs to or marked
    sporadic. Counting those says what is being seen; a true flux — meteoroids
    per square kilometre per hour, corrected for camera coverage and limiting
    magnitude — is a different quantity GMN computes separately, and calling
    this one that would overstate it.

    The file is generated during the day, so an early read sees a partial day.
    The generation time is returned so a caller can see that for themselves.
    """
    text = _fetch(GMN_DAILY)
    generated = None
    counts: dict[str, int] = {}
    sporadic = 0
    total = 0
    for line in text.splitlines():
        if line.startswith("#"):
            if "Summary generated on" in line:
                generated = line.split("Summary generated on", 1)[1].strip()
            continue
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 5:
            continue
        code = parts[4]
        total += 1
        # GMN marks an unassociated meteor with "..." and IAU number -1.
        if not code or set(code) <= {"."}:
            sporadic += 1
        else:
            counts[code] = counts.get(code, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return {
        "generated_utc": generated,
        "meteors_counted": total,
        "sporadic": sporadic,
        "by_shower": [{"code": c, "count": n} for c, n in ranked],
        "note": (
            "Confirmed trajectories in the Global Meteor Network's latest daily "
            "summary, counted by IAU shower code. This is a count of what was "
            "seen, not a flux density. The file is written during the day, so an "
            "early read covers a partial day — see generated_utc."
        ),
        "source": {
            "owner": "Global Meteor Network",
            "url": GMN_HOME,
            "data": GMN_DAILY,
            "licence": "CC BY 4.0",
            "attribution": (
                "Global Meteor Network, https://globalmeteornetwork.org/, "
                "CC BY 4.0. Attribution is a condition of the licence."
            ),
        },
    }
