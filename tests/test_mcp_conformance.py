"""Conformance with the Model Context Protocol, revision 2026-07-28.

We documented how to *publish* an MCP server in detail and never wrote down what makes
one *valid*, which is how missing ``isError`` and missing annotations reached every
server in the fleet.

This is the last repo in the sweep and the only one that needed **two** annotation
blocks for the usual reason rather than an unusual one:

* **Five tools answer from carried data; two read somebody else's live service.**
  ``meteor_activity`` reads the Global Meteor Network and ``meteor_fireballs`` reads
  NASA CNEOS. The other five answer from the IAU Meteor Data Center's shower list
  shipped in the package, plus geometry. One block would have advertised five
  closed-domain tools as open-world — or, far worse, advertised two network calls as
  closed. ``TestOpenWorldIsPerTool`` reads the code and compares it against what is
  published, so the two lists cannot quietly drift apart.

* **The `certifi` requirement is already met here, and that is checked rather than
  assumed.** ``live.py`` builds its context with
  ``ssl.create_default_context(cafile=certifi.where())``. This is the only repo in the
  sweep where qso-graph-devel#73 actually applies, so ``TestTlsIsNotWeakened`` asserts
  both halves: the roots come from ``certifi``, and verification is never turned off.

* **Nine call sites, two kinds of failure.** Bad input (a time that cannot be read, a
  shower not in the MDC list, a limit that is not a whole number) and an upstream source
  failing. The specification treats both as ``isError: true`` — a JSON-RPC protocol
  error is for a request the server cannot route at all. ``TestUpstreamFailureIsFlagged``
  holds the second kind, including that its message still gives nothing away.

Test IDs: MT-C01 onward.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from meteor_mcp import live, server

ANNOTATION_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

READS_CARRIED_DATA = {
    "get_version_info", "meteor_window", "meteor_showers", "meteor_shower_info",
    "meteor_source_info",
}
READS_A_LIVE_SERVICE = {"meteor_activity", "meteor_fireballs"}
ALL_TOOLS = READS_CARRIED_DATA | READS_A_LIVE_SERVICE


def _tools() -> dict[str, object]:
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def _wire(tool: object) -> dict[str, object]:
    annotations = getattr(tool, "annotations", None)
    assert annotations is not None, "tool declares no annotations"
    return annotations.model_dump(by_alias=True, exclude_none=True)


def call(name: str, args: dict | None = None):
    async def go():
        async with Client(server.mcp) as c:
            return (await c.call_tool(name, args or {})).data
    return asyncio.run(go())


def fails(name: str, args: dict | None = None) -> str:
    with pytest.raises(ToolError) as caught:
        call(name, args)
    return str(caught.value)


def _sources():
    import pathlib

    src = pathlib.Path(server.__file__).parent
    for py in src.rglob("*.py"):
        yield py, py.read_text()


class TestToolAnnotations:
    def test_every_tool_declares_all_four_hints(self) -> None:
        """MT-C01: the defaults are pessimistic, so silence is the wrong answer."""
        for name, tool in _tools().items():
            wire = _wire(tool)
            for hint in ANNOTATION_HINTS:
                assert hint in wire, f"{name} omits {hint}; got {sorted(wire)}"

    def test_every_tool_is_read_only_and_idempotent(self) -> None:
        """MT-C02: nothing here writes, and no tool changes anything upstream.

        `idempotentHint` is true for the live pair too, in the sense the specification
        means: the tool changes nothing at the far end. Their *answers* move, because
        GMN rewrites today's file through the day and CNEOS gains fireballs — which is
        why `meteor_activity` returns the generation time.
        """
        for name, tool in _tools().items():
            wire = _wire(tool)
            assert wire["readOnlyHint"] is True, name
            assert wire["destructiveHint"] is False, name
            assert wire["idempotentHint"] is True, name


class TestOpenWorldIsPerTool:
    """The reason this file exists.

    Five of seven answer from the package. A block copied from any owner-list server
    would have told a client that reading NASA CNEOS is a closed-domain operation.
    """

    def test_only_the_two_live_tools_are_open_world(self) -> None:
        """MT-C10: five false, two true — classified by what each tool touches."""
        tools = _tools()
        assert set(tools) == ALL_TOOLS
        for name in READS_A_LIVE_SERVICE:
            assert _wire(tools[name])["openWorldHint"] is True, (
                f"{name} reads somebody else's service and must say so"
            )
        for name in READS_CARRIED_DATA:
            assert _wire(tools[name])["openWorldHint"] is False, (
                f"{name} answers from this machine and must not claim otherwise"
            )

    def test_the_split_is_five_to_two(self) -> None:
        """MT-C11: a guard against the whole set drifting one way.

        A tool added later fails this until somebody decides which side it is on, which
        is the decision the sweep found nobody had made anywhere in the fleet.
        """
        wire = {n: _wire(t)["openWorldHint"] for n, t in _tools().items()}
        assert sum(1 for v in wire.values() if v is True) == 2
        assert sum(1 for v in wire.values() if v is False) == 5

    def test_the_classification_matches_the_code(self) -> None:
        """MT-C12: the hints are checked against the source, not against this file.

        Two lists agreeing proves nothing if both were written from one guess. This
        reads `server.py` and asserts that exactly the tools whose bodies reach
        `live.` are the ones publishing `openWorldHint: true`. Compared against the
        *published annotations* rather than the constants above, so moving a decorator
        cannot leave it green.
        """
        import ast
        import pathlib
        import re

        source = pathlib.Path(server.__file__).read_text()
        lines = source.splitlines()
        network = re.compile(r"\blive\.")
        reaches = set()
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
                for d in node.decorator_list
            ):
                body = "\n".join(lines[node.lineno - 1:node.end_lineno])
                if network.search(body):
                    reaches.add(node.name)

        declared = {n for n, t in _tools().items() if _wire(t)["openWorldHint"] is True}
        assert reaches == declared, (
            f"tools whose code reaches live: {sorted(reaches)}; "
            f"tools declaring openWorldHint true: {sorted(declared)}"
        )


class TestTlsIsNotWeakened:
    """The one repo in this sweep where qso-graph-devel#73 actually applies.

    Everything else in the sweep makes no outbound call at all, so `certifi` was "not
    applicable, verified". This server really does fetch, so the requirement is live and
    is already met — which is worth asserting rather than noting.
    """

    def test_the_root_store_comes_from_certifi(self) -> None:
        """MT-C20: not whichever store the running Python was built against.

        Apple's `/etc/ssl/cert.pem` is a reduced OpenSSL file — 128 roots against the
        system keychain's 158 — so valid certificates fail for Python while `curl`
        succeeds (qso-graph-devel#73).
        """
        import pathlib

        text = pathlib.Path(live.__file__).read_text()
        assert "certifi.where()" in text
        assert "ssl.create_default_context(cafile=certifi.where())" in text

    def test_verification_is_never_turned_off(self) -> None:
        """MT-C21: `CERT_NONE` accepts any certificate from anyone, invisibly."""
        offenders = [
            f"{py.name}:{i}: {line.strip()}"
            for py, text in _sources()
            for i, line in enumerate(text.splitlines(), 1)
            if ("CERT_NONE" in line or "check_hostname = False" in line
                or "check_hostname=False" in line)
        ]
        assert not offenders, "TLS verification is weakened:\n" + "\n".join(offenders)

    def test_only_live_reaches_the_network(self) -> None:
        """MT-C22: one outbound path, so one place to get TLS right.

        `readOnlyHint` and the five `openWorldHint: false` tools all rest on the network
        being confined to `live.py`. A second module opening a socket would need its own
        TLS context and would break the classification in MT-C10 at the same time.
        """
        offenders = [
            f"{py.name}:{i}: {line.strip()}"
            for py, text in _sources()
            for i, line in enumerate(text.splitlines(), 1)
            if py.name != "live.py"
            and not line.strip().startswith("#")
            and any(t in line for t in ("urlopen", "urllib.request", "http.client",
                                        "socket.", "requests.", "httpx."))
        ]
        assert not offenders, (
            "something outside live.py reaches the network:\n" + "\n".join(offenders)
        )


# Every refusal, with a fragment of the message it must carry. The fragment is not
# decoration: it is what distinguishes a deliberate refusal from a crash — see MT-C30.
REFUSALS = (
    ("meteor_shower_info", {"shower": "Hyades"}, "meteor_showers"),
    ("meteor_showers", {"when": "not-a-time"}, "ISO 8601"),
    ("meteor_window", {"their_grid": "EM12"}, "MY_GRIDSQUARE"),
    ("meteor_window", {"my_grid": "DN13"}, "other station"),
    ("meteor_window", {"my_grid": "ZZ99", "their_grid": "EM12"}, "locator"),
    ("meteor_window", {"my_grid": "DN13", "their_grid": "EM12", "when": "whenever"},
     "ISO 8601"),
    ("meteor_window", {"my_lat": 91.0, "my_lon": 0.0, "their_grid": "EM12"}, "latitude"),
)

# What a Python exception looks like when it reaches a caller instead of a refusal.
CRASH = ("NoneType", "AttributeError", "TypeError", "KeyError", "IndexError",
         "object has no attribute", "Traceback", "unsupported operand")


class TestBadInputIsFlagged:
    def test_every_refusal_raises_and_says_what_was_wrong(self) -> None:
        """MT-C30: raising is not enough — a crash raises too.

        The first version of this test only asserted that each bad input raised
        ``ToolError``, and **it could not fail**. Falsifying it showed why: with ``_err``
        returning a payload instead of raising, the call sites are bare ``_err(...)``,
        so execution *continues* and the tool crashes a few lines later —
        ``AttributeError: 'NoneType' object has no attribute 'iau_number'`` — which
        FastMCP delivers as a ``ToolError`` too. Both arrive identically at a client.

        So the message is the test. Each refusal must carry the fragment it was written
        with, which a crash cannot produce.
        """
        for name, args, fragment in REFUSALS:
            message = fails(name, args)
            assert fragment in message, (
                f"{name}{args} raised, but not the deliberate refusal: {message!r}"
            )

    def test_no_refusal_is_really_a_crash(self) -> None:
        """MT-C31: the generalisation, for inputs nobody listed.

        MT-C30 pins the refusals we know about. This one says that *whatever* a tool
        refuses, it must not do it by leaking a Python exception — which is how a
        missing guard shows up, and what the caller would otherwise be handed to
        "self-correct" from.
        """
        for name, args, _ in REFUSALS:
            message = fails(name, args)
            for crash in CRASH:
                assert crash not in message, (
                    f"{name}{args} crashed rather than refused: {message!r}"
                )

    def test_no_error_payload_remains_in_the_source(self) -> None:
        """MT-C32: the conversion is complete, not partial.

        Reads the parse tree for a dict literal with an ``"error"`` key. A text search
        matches ``_err``'s own docstring, which quotes the old shape; stripping string
        literals to fix that deletes the key as well, since the key *is* a literal — the
        version that shipped in cq-zones-mcp 0.2.0 and could never fail.
        """
        import ast

        offenders = [
            f"{py.name}:{node.lineno}"
            for py, text in _sources()
            for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Dict)
            and any(isinstance(k, ast.Constant) and k.value == "error" for k in node.keys)
        ]
        assert not offenders, f"error payloads remain at: {offenders}"


class TestUpstreamFailureIsFlagged:
    """The second kind of failure, which the specification treats the same way."""

    def test_a_source_being_down_is_an_error_from_the_tool(self, monkeypatch) -> None:
        """MT-C40: `isError: true`, not a successful result and not a protocol error.

        A JSON-RPC protocol error is for a request the server cannot route at all. An
        upstream source failing is a *tool* execution error, which is what the
        specification's own list says: "an API request failure".
        """
        def down(*args, **kwargs):
            raise live.LiveError("the source could not be reached")

        monkeypatch.setattr(live, "activity", down)
        monkeypatch.setattr(live, "fireballs", down)
        assert "Global Meteor Network" in fails("meteor_activity")
        assert "CNEOS" in fails("meteor_fireballs", {"limit": 1})

    def test_the_failure_gives_nothing_away(self, monkeypatch) -> None:
        """MT-C41: a failure may say a source is down, not describe our insides.

        `live.LiveError` is deliberately vague — "the source answered 404", "the source
        could not be reached" — and the tool adds only which source it was. Asserted
        because an error path is exactly where a URL, a traceback or a filesystem path
        gets leaked by accident.
        """
        def down(*args, **kwargs):
            raise live.LiveError("the source could not be reached")

        monkeypatch.setattr(live, "activity", down)
        monkeypatch.setattr(live, "fireballs", down)
        for message in (fails("meteor_activity"), fails("meteor_fireballs", {"limit": 1})):
            for leak in ("Traceback", "urllib", "https://", "/Users/", "line ", "ssl."):
                assert leak not in message, f"a failure leaked {leak!r}: {message}"


class TestAVerdictIsNotAnError:
    def test_an_unworkable_path_is_a_successful_call(self) -> None:
        """MT-C50: the distinction the specification draws.

        A 100 km path is too short for meteor scatter. That is an *answer* — the
        geometry is what it is — and the tool says so in `workable_distance` and in the
        summary. Only an unusable request is an error.
        """
        answer = call("meteor_window", {
            "my_grid": "DN13", "their_grid": "DN14", "shower": "PER", "hours": 0,
        })
        assert isinstance(answer, dict)
        assert answer["path"]["workable_distance"] is False
        assert "short" in answer["summary"]


class TestVersionInfoShape:
    def test_it_matches_the_shape_the_fleet_returns(self) -> None:
        """MT-C60: the convention that drifted because nobody asserted it."""
        info = call("get_version_info")
        assert info["service_name"] == "meteor-mcp"
        assert info["service_version"]
        assert info["spec_version"]


class TestRegistration:
    def test_the_seven_tools_a_client_sees(self) -> None:
        """MT-C70: calling a function directly is not proof a client can."""
        assert set(_tools()) == ALL_TOOLS
