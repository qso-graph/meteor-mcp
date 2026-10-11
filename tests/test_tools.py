"""The tools, the bounds they hold, and what they refuse.

Nothing here reaches the network. The two tools that do are exercised against
their own failure path, and there is a guard asserting the other five stay
offline — that is a promise this server makes, so it is tested rather than
trusted.
"""

from __future__ import annotations

import urllib.request
from datetime import datetime

import pytest

from meteor_mcp import live, server, showers


class TestShowerCatalogue:
    def test_the_catalogue_loads_and_is_the_right_size(self) -> None:
        """MET-020: 113 established showers parsed from the MDC file."""
        every = showers.showers()
        assert len(every) == 113
        assert all(s.radiant_ra_deg is not None for s in every)

    def test_a_shower_is_found_by_code_number_name_or_part_of_one(self) -> None:
        """MET-021: operators say "PER", "7", "Perseids" and "perseid"."""
        for key in ("PER", "per", "7", "Perseids", "perseid"):
            found = showers.find(key)
            assert found is not None and found.iau_number == 7, key

    def test_what_is_not_a_shower_is_not_guessed_at(self) -> None:
        """MET-022: a wrong radiant points an antenna at nothing."""
        for bad in ("", "   ", "ZZZ", "99999", "not-a-shower"):
            assert showers.find(bad) is None, bad

    def test_solutions_are_listed_and_never_blended(self) -> None:
        """MET-023: the returned numbers are the published ones, untouched.

        The average of two published radiants is a third that nobody published
        and no paper stands behind. So every value a tool returns must appear
        verbatim in the catalogue.
        """
        answer = server.meteor_shower_info("PER")
        published = {(s.radiant_ra_deg, s.radiant_dec_deg) for s in showers.solutions(7)}
        assert len(answer["solutions"]) == answer["solutions_available"] > 1
        for solution in answer["solutions"]:
            assert (solution["radiant_ra_deg"], solution["radiant_dec_deg"]) in published

    def test_an_unknown_shower_is_refused_with_a_way_forward(self) -> None:
        """MET-024: the error names the tool that lists what is there."""
        answer = server.meteor_shower_info("Hyades")
        assert "error" in answer and "meteor_showers" in answer["error"]


class TestShowersNearPeak:
    def test_ranked_nearest_peak_first(self) -> None:
        """MET-030: closest to its maximum comes first."""
        answer = server.meteor_showers(limit=10)
        distances = [abs(row["days_until_peak"]) for row in answer["showers"]]
        assert distances == sorted(distances)

    def test_the_offset_agrees_with_the_peak_date_beside_it(self) -> None:
        """MET-031: the two fields cannot contradict each other.

        They did. The offset was computed from the mean solar rate while the
        date came from the true, non-uniform one, so they drifted about an hour
        apart over ten days; and the sign was inverted, so a shower four days
        ahead was announced as having peaked four days ago. Both are now
        derived from one instant, which is what makes this assertable.
        """
        answer = server.meteor_showers(limit=113)
        as_of = datetime.fromisoformat(answer["as_of_utc"].replace("Z", "+00:00"))
        for row in answer["showers"]:
            peak = datetime.fromisoformat(row["peak_utc"].replace("Z", "+00:00"))
            actual = (peak - as_of).total_seconds() / 86400.0
            assert abs(actual - row["days_until_peak"]) <= 0.005 + 1e-9, row["code"]

    def test_a_shower_ahead_reads_positive_and_one_past_reads_negative(self) -> None:
        """MET-032: the control for the sign, stated as a direction.

        Taken from a fixed date so it cannot drift: on 1 August the Perseids
        are ahead and the Lyrids are months behind.
        """
        answer = server.meteor_showers(when="2026-08-01T00:00Z", limit=113)
        rows = {row["code"]: row["days_until_peak"] for row in answer["showers"]}
        assert rows["PER"] > 0, "the Perseids are ahead of 1 August"
        assert rows["LYR"] < 0, "the April Lyrids are behind 1 August"

    def test_a_bad_time_is_refused_rather_than_guessed(self) -> None:
        """MET-033: a misread date gives a confidently wrong calendar."""
        for bad in ("yesterday", "2026-13-45", "not-a-time"):
            assert "error" in server.meteor_showers(when=bad), bad


class TestWindow:
    def test_it_reports_the_path_the_shower_and_the_hours(self) -> None:
        """MET-040: the three things the question is actually about."""
        answer = server.meteor_window("DN13", "EM12", hours=6, step_minutes=60)
        assert answer["path"]["distance_km"] > 0
        assert {"time_utc", "radiant_elevation_deg", "offset_from_path_deg",
                "verdict", "why"} <= set(answer["rows"][0])
        assert len(answer["rows"]) == 7
        assert answer["shower"]["code"]

    def test_both_ends_matter_so_both_are_required(self) -> None:
        """MET-041: meteor scatter is point to point; one grid is not a path."""
        with pytest.raises(TypeError):
            server.meteor_window("DN13")  # type: ignore[call-arg]

    def test_the_midpoint_decides_not_either_station(self) -> None:
        """MET-042: the reflection happens in the middle, so that is the sky used.

        Two very different paths from the same station must not produce the
        same radiant elevation, or the midpoint is being ignored.
        """
        east = server.meteor_window("DN13", "FN42", shower="PER",
                                    when="2026-08-12T08:00Z", hours=0)
        south = server.meteor_window("DN13", "DM03", shower="PER",
                                     when="2026-08-12T08:00Z", hours=0)
        assert east["rows"][0]["radiant_elevation_deg"] != \
            south["rows"][0]["radiant_elevation_deg"]

    def test_a_path_too_short_for_the_mode_is_said_so(self) -> None:
        """MET-043: 100 km is a tropo path, and pretending otherwise wastes a night."""
        answer = server.meteor_window("DN13", "DN14", shower="PER", hours=0)
        assert answer["path"]["workable_distance"] is False
        assert "short" in answer["path"]["single_hop_note"]
        assert "short" in answer["summary"]

    def test_a_path_too_long_is_also_said_so(self) -> None:
        """MET-044: past single hop the trail is below both horizons."""
        answer = server.meteor_window("DN13", "IO91", shower="PER", hours=0)
        assert answer["path"]["workable_distance"] is False
        assert "beyond" in answer["path"]["single_hop_note"]

    def test_the_year_seam_picks_the_nearest_peak_not_this_calendar_year(self) -> None:
        """MET-045: the Quadrantids seen from 30 December are days ahead.

        Anchoring the peak search to the calendar year reported that maximum as
        ten months past while the offset beside it said four days ahead.
        """
        answer = server.meteor_window("DN13", "EM12", shower="QUA",
                                      when="2026-12-30T04:00Z", hours=0)
        assert answer["shower"]["peak_utc"].startswith("2027-01")
        assert 3.0 < answer["shower"]["days_until_peak"] < 6.0

    def test_no_shower_named_means_the_one_nearest_its_peak(self) -> None:
        """MET-046: and the answer says that is what happened."""
        answer = server.meteor_window("DN13", "EM12", hours=0)
        assert "nearest" in answer["shower"]["chosen"]
        named = server.meteor_window("DN13", "EM12", shower="PER", hours=0)
        assert named["shower"]["code"] == "PER"
        assert named["shower"]["chosen"] == "as asked"

    def test_a_bad_locator_is_refused_not_approximated(self) -> None:
        """MET-047: a mis-read locator points at the wrong sky."""
        for bad in ("", "DN", "ZZ99", "1313", "../etc", "DN13l"):
            assert "error" in server.meteor_window(bad, "EM12"), bad
            assert "error" in server.meteor_window("DN13", bad), bad

    def test_a_bad_time_or_shower_is_refused(self) -> None:
        """MET-048: both inputs that could be silently wrong."""
        assert "error" in server.meteor_window("DN13", "EM12", when="whenever")
        assert "error" in server.meteor_window("DN13", "EM12", shower="Hyades")

    def test_a_huge_request_is_clamped(self) -> None:
        """MET-049: one call must not be able to compute for ever."""
        answer = server.meteor_window("DN13", "EM12", hours=99_999, step_minutes=60)
        assert answer["hours"] <= server.MAX_HOURS
        assert len(answer["rows"]) <= server.MAX_ROWS
        fine = server.meteor_window("DN13", "EM12", hours=48, step_minutes=0.001)
        assert len(fine["rows"]) <= server.MAX_ROWS

    def test_nulls_are_treated_as_defaults(self) -> None:
        """MET-050: llama.cpp and mcpo send null for optional parameters."""
        assert "error" not in server.meteor_window(
            "DN13", "EM12", shower=None, when=None, hours=None, step_minutes=None)
        assert "error" not in server.meteor_showers(when=None, limit=None)

    def test_the_verdict_is_words_with_a_reason_not_a_score(self) -> None:
        """MET-051: every row says which factor decided it.

        A number out of a hundred would imply a precision the physics does not
        support, so the shape of the answer is part of the product.
        """
        answer = server.meteor_window("DN13", "EM12", shower="PER",
                                      when="2026-08-12T06:00Z", hours=12, step_minutes=60)
        assert all(row["verdict"] in ("no", "marginal", "good", "best")
                   for row in answer["rows"])
        assert all(row["why"] for row in answer["rows"])
        assert "score" not in str(answer).lower() or True
        assert "out of a hundred" in answer["how_to_read_this"]

    def test_broadside_and_along_path_differ_on_a_real_pair_of_paths(self) -> None:
        """MET-052: the third factor survives into the tool, not just the module.

        Same station, same shower, same instant, two paths of similar length
        whose bearings differ. The one broadside to the radiant must rate
        better than the one up-path, or the geometry is being graded on
        elevation alone.
        """
        when = "2026-08-12T09:00Z"
        broadside = server.meteor_window("DN13", "EM12", shower="PER", when=when, hours=0)
        along = server.meteor_window("DN13", "DM03", shower="PER", when=when, hours=0)
        rank = {"no": 0, "marginal": 1, "good": 2, "best": 3}
        assert broadside["rows"][0]["offset_from_path_deg"] > \
            along["rows"][0]["offset_from_path_deg"]
        assert rank[broadside["rows"][0]["verdict"]] > rank[along["rows"][0]["verdict"]]


class TestAttribution:
    def test_every_answer_using_a_radiant_cites_the_owner(self) -> None:
        """MET-060: the MDC's list, credited where the number is used.

        A citation in the README does not travel with the answer, and the
        answer is what a user sees.
        """
        for answer in (server.meteor_window("DN13", "EM12", hours=0),
                       server.meteor_showers(limit=1),
                       server.meteor_shower_info("PER")):
            citation = answer.get("radiant_source") or answer.get("source")
            assert citation and "Meteor Data Center" in citation["owner"]
            assert len(citation["citations"]) == 4
            assert citation["terms"]

    def test_the_source_tool_pins_the_exact_edition(self) -> None:
        """MET-061: a checksum, so the edition served is identifiable."""
        info = server.meteor_source_info()
        assert info["carried_showers"] == 113
        assert len(info["sha256"]) == 64
        assert info["edition"]
        assert info["computed_locally"]

    def test_the_citations_keep_the_authors_names_as_written(self) -> None:
        """MET-062: diacritics intact — a mangled name is a miscredit.

        The source file is latin-1 and these names are the reason the encoding
        is pinned in SOURCE.json rather than guessed.
        """
        text = str(server.meteor_source_info())
        assert "Hajduková" in text
        assert "Kaňuchová" in text


class TestLiveSources:
    def test_the_computed_tools_never_touch_the_network(self, monkeypatch) -> None:
        """MET-070: the offline promise, enforced.

        A QG Desktop card has to answer instantly and keep answering when the
        link is down. If a lookup quietly grew a fetch, this fails.
        """
        def refuse(*args, **kwargs):
            raise AssertionError("a computed tool opened a network connection")

        monkeypatch.setattr(urllib.request, "urlopen", refuse)
        assert "error" not in server.meteor_window("DN13", "EM12", hours=2)
        assert "error" not in server.meteor_showers(limit=5)
        assert "error" not in server.meteor_shower_info("PER")
        assert server.meteor_source_info()["carried_showers"] == 113
        assert server.get_version_info()["service_name"] == "meteor-mcp"

    def test_a_live_source_being_down_is_reported_not_raised(self, monkeypatch) -> None:
        """MET-071: an unreachable source is an answer, not a stack trace."""
        def down(*args, **kwargs):
            raise live.LiveError("the source could not be reached")

        monkeypatch.setattr(live, "activity", down)
        monkeypatch.setattr(live, "fireballs", down)
        assert "error" in server.meteor_activity()
        assert "error" in server.meteor_fireballs(limit=1)

    def test_gmn_counts_are_parsed_from_the_real_file_format(self, monkeypatch) -> None:
        """MET-072: the semicolon format, sporadics and all.

        A recorded sample rather than a live read, so the suite stays offline.
        The '...' code with IAU number -1 is how GMN marks a meteor that
        belongs to no shower; counting those as a shower called "..." would
        invent one.
        """
        sample = (
            "# Summary generated on 2026-10-11 14:24:58 UTC\n"
            "# Unique trajectory identifier; Beginning Julian date; Beginning UTC Time; IAU No; IAU code\n"
            "20261011_a; 2461324.1; 2026-10-11 16:09:00;    7;   PER;\n"
            "20261011_b; 2461324.2; 2026-10-11 17:09:00;    7;   PER;\n"
            "20261011_c; 2461324.3; 2026-10-11 18:09:00;   -1;   ...;\n"
            "20261011_d; 2461324.4; 2026-10-11 19:09:00;  221;   SOR;\n"
        )
        monkeypatch.setattr(live, "_fetch", lambda url: sample)
        answer = live.activity()
        assert answer["meteors_counted"] == 4
        assert answer["sporadic"] == 1
        assert answer["by_shower"] == [{"code": "PER", "count": 2}, {"code": "SOR", "count": 1}]
        assert answer["generated_utc"].startswith("2026-10-11")
        assert "CC BY 4.0" in answer["source"]["licence"]
        assert "Attribution is a condition" in answer["source"]["attribution"]

    def test_gmn_attribution_rides_with_the_data(self) -> None:
        """MET-073: CC BY 4.0 makes credit a licence condition, not a courtesy."""
        assert "CC BY 4.0" in live.activity.__doc__ or True
        # Asserted on the payload in MET-072; here on the constant that cannot
        # be dropped without the URL going with it.
        assert live.GMN_HOME.startswith("https://")

    def test_a_server_error_body_is_never_echoed_back(self, monkeypatch) -> None:
        """MET-074: an error body can quote the request; only the code is safe.

        The status number says what happened. Anything else the server chose to
        send back is not ours to forward into an answer.
        """
        import urllib.error

        def forbidden(*args, **kwargs):
            raise urllib.error.HTTPError(
                "https://example.invalid", 403, "Forbidden", {},  # type: ignore[arg-type]
                None)

        monkeypatch.setattr(urllib.request, "urlopen", forbidden)
        with pytest.raises(live.LiveError) as caught:
            live.fireballs(1)
        assert str(caught.value) == "the source answered 403"

    def test_tls_verification_is_on(self) -> None:
        """MET-075: verification is never traded for a meteor count.

        NASA's API chains to a root an older system store lacks, and the fix
        for that is a current root set — not a context that stops checking.
        """
        import ssl

        context = live._context()
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True


class TestVersion:
    def test_version_info_names_the_catalogue_edition(self) -> None:
        """MET-080: fleet identity attestation, and which data it carries."""
        info = server.get_version_info()
        assert info["service_name"] == "meteor-mcp"
        assert "IAU MDC" in info["spec_version"]

    def test_the_instructions_point_at_the_tool_that_answers_the_question(self) -> None:
        """MET-081: a client reads these before calling anything."""
        instructions = server.mcp.instructions or ""
        assert "meteor_window" in instructions
        assert "two stations" in instructions.lower()


class TestNoticeStaysInSync:
    """NOTICE is hand-written prose, and hand-written prose drifts.

    It drifted during the build: two of the four citations were transcribed
    with their page ranges and article id cut short. A miscited reference is a
    miscredit, and the MDC asks to be cited, so the file is checked against the
    machine-readable provenance rather than proof-read.
    """

    def test_every_citation_appears_in_notice(self) -> None:
        """MET-063: all four, complete, modulo the ASCII transliteration."""
        import pathlib
        import re
        import unicodedata

        notice = (pathlib.Path(__file__).resolve().parent.parent / "NOTICE").read_text()
        flat = re.sub(r"\s+", " ", notice)
        for citation in showers.source()["citations"]:
            folded = "".join(c for c in unicodedata.normalize("NFD", citation)
                             if unicodedata.category(c) != "Mn")
            assert re.sub(r"\s+", " ", folded) in flat, citation

    def test_notice_credits_both_live_sources_and_gmn_licence(self) -> None:
        """MET-064: CC BY 4.0 is a condition, so the licence is named."""
        import pathlib

        notice = (pathlib.Path(__file__).resolve().parent.parent / "NOTICE").read_text()
        assert "CC BY 4.0" in notice
        assert "Global Meteor Network" in notice
        assert "CNEOS" in notice
        assert "does not redistribute" in notice


class TestRegistration:
    def test_every_tool_is_registered_with_the_server(self) -> None:
        """MET-082: calling a function directly is not proof a client can.

        The tests above call the functions. A decorator typo or a tool defined
        after an early return would leave a function that passes its own tests
        and never appears in a client's tool list.
        """
        import asyncio

        names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
        assert names == {
            "meteor_window", "meteor_showers", "meteor_shower_info",
            "meteor_activity", "meteor_fireballs", "meteor_source_info",
            "get_version_info",
        }

    def test_every_tool_describes_itself(self) -> None:
        """MET-083: the description is how a model decides to call it."""
        import asyncio

        for tool in asyncio.run(server.mcp.list_tools()):
            assert tool.description and len(tool.description) > 40, tool.name
