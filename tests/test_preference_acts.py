"""EXTRACT-unification Stage 1 — the unified PreferenceAct evidence type.

Pins the adapters (RejectionSignal/Decision → PreferenceAct), the unified
reader over both on-disk stores, and round-trip. The writers + eval
harness are unchanged at this stage; later stages merge extraction and
migrate storage.
"""
from __future__ import annotations

import pytest

from trinity_local.me.decisions import Decision, save_decisions
from trinity_local.me.preference_acts import (
    MODEL_MISS,
    SELF_EXPRESSED,
    PreferenceAct,
    from_decision,
    from_rejection,
    iter_preference_acts,
)
from trinity_local.me.turn_pairs import RejectionSignal, save_rejections


class TestAdapters:
    def test_rejection_maps_to_model_miss(self):
        r = RejectionSignal(
            id="r1", type="REFRAME", model_quote="do X the elaborate way",
            user_substitute="just do Y", why_signal="user reframed", prompt_id="p1",
            basin="b0", next_user_turn="and then Z",
        )
        a = from_rejection(r)
        assert a.trigger == MODEL_MISS
        assert a.privileged == "just do Y"        # user's substitute
        assert a.sacrificed == "do X the elaborate way"  # model's offering
        assert a.kind == "REFRAME"
        assert a.why == "user reframed"
        assert a.context == "and then Z"
        assert (a.prompt_id, a.basin, a.id) == ("p1", "b0", "r1")

    def test_decision_maps_to_self_expressed(self):
        d = Decision(
            id="d1", privileged="ship velocity", sacrificed="polish",
            valence="satisfaction", basin="b2", verbatim="just get it out",
            prompt_id="p2", would_flip_if="if it were user-facing", weight=2.0,
            source="user_logged",
        )
        a = from_decision(d)
        assert a.trigger == SELF_EXPRESSED
        assert a.privileged == "ship velocity"
        assert a.sacrificed == "polish"
        assert a.kind == "satisfaction"      # valence becomes kind
        assert a.why == "if it were user-facing"
        assert a.context == "just get it out"
        assert a.weight == 2.0
        assert a.source == "user_logged"


class TestRoundTrip:
    def test_to_from_dict_full(self):
        a = PreferenceAct(
            id="pa1", trigger=MODEL_MISS, privileged="P", sacrificed="S",
            kind="REDIRECT", why="W", prompt_id="p1", basin="b0",
            context="C", source="lens-build", weight=2.0,
        )
        assert PreferenceAct.from_dict(a.to_dict()) == a

    def test_to_dict_filters_defaults(self):
        a = PreferenceAct(id="pa1", trigger=SELF_EXPRESSED, privileged="P", sacrificed="S")
        d = a.to_dict()
        # Only the required fields survive when everything else is default.
        assert set(d) == {"id", "trigger", "privileged", "sacrificed"}

    def test_from_dict_tolerates_extra_keys(self):
        a = PreferenceAct.from_dict({
            "id": "pa1", "trigger": MODEL_MISS, "privileged": "P", "sacrificed": "S",
            "future_field": "ignored",
        })
        assert a.id == "pa1" and a.privileged == "P"


@pytest.mark.usefixtures("patch_trinity_home")
class TestUnifiedReader:
    """EXTRACT Stage 4a: iter_preference_acts reads the unified ledger and
    self-heals from the legacy stores (merge-forward) so a cold/stale ledger
    can never lose data while the legacy writers are still live."""

    def test_iter_merges_legacy_when_ledger_cold(self):
        # Legacy stores populated, ledger empty → iter content-merges them in.
        save_rejections([
            RejectionSignal(id="r1", type="REFRAME", model_quote="m", user_substitute="u"),
        ])
        save_decisions([
            Decision(id="d1", privileged="a", sacrificed="b", valence="regret",
                     basin=None, verbatim="v"),
        ])
        acts = iter_preference_acts()
        triggers = {a.trigger for a in acts}
        assert triggers == {MODEL_MISS, SELF_EXPRESSED}
        assert len(acts) == 2
        # Order: model_miss first, then self_expressed.
        assert acts[0].trigger == MODEL_MISS
        assert acts[1].trigger == SELF_EXPRESSED

    def test_iter_is_a_pure_read(self):
        # A read must NOT mutate the ledger on disk (no write-on-read footgun
        # for callers like eval-build). Cold ledger stays cold after a read.
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            preference_acts_path,
        )
        save_rejections([
            RejectionSignal(id="r1", type="REFRAME", model_quote="m", user_substitute="u"),
        ])
        assert iter_preference_acts()  # non-empty merged view
        # ...but the ledger file was never written by the read.
        assert not preference_acts_path().exists()
        assert load_preference_acts() == []

    def test_iter_collapses_distinct_records_sharing_a_bad_id(self):
        # The real-data bug: legacy rejections share id "r_001" but have
        # DISTINCT content. Content-keyed merge must preserve all of them
        # (id-keyed merge would have collapsed 8 → 1, losing taste signal).
        save_rejections([
            RejectionSignal(id="r_001", type="REFRAME", model_quote="m1", user_substitute="u1"),
            RejectionSignal(id="r_001", type="REDIRECT", model_quote="m2", user_substitute="u2"),
            RejectionSignal(id="r_001", type="REFRAME", model_quote="m1", user_substitute="u1"),  # true dup
        ])
        acts = iter_preference_acts()
        # 2 distinct contents survive; the exact duplicate collapses.
        assert len(acts) == 2

    def test_iter_empty_when_no_stores(self):
        assert iter_preference_acts() == []

    def test_iter_handles_only_rejections(self):
        save_rejections([
            RejectionSignal(id="r1", type="COMPRESSION", model_quote="long", user_substitute="short"),
        ])
        acts = iter_preference_acts()
        assert len(acts) == 1 and acts[0].trigger == MODEL_MISS

    def test_iter_reads_ledger_as_source_of_truth(self):
        # A record present ONLY in the ledger (not in the legacy stores —
        # e.g. a provider-import dual-write) is returned. This is the flip:
        # pre-4a, iter unioned the legacy stores and would miss it.
        from trinity_local.me.preference_acts import save_preference_acts
        save_preference_acts([
            PreferenceAct(id="ledger_only", trigger=MODEL_MISS, privileged="p",
                          sacrificed="s", kind="REDIRECT"),
        ])
        acts = iter_preference_acts()
        assert any(a.id == "ledger_only" for a in acts)

    def test_iter_ledger_wins_on_content_collision(self):
        # Same CONTENT in both stores → one act, the ledger copy wins (it
        # carries the canonical id + enrichment like source/weight).
        from trinity_local.me.preference_acts import save_preference_acts
        save_rejections([
            RejectionSignal(id="legacy_id", type="REFRAME", model_quote="m",
                            user_substitute="u"),
        ])
        save_preference_acts([
            PreferenceAct(id="ledger_id", trigger=MODEL_MISS, privileged="u",
                          sacrificed="m", kind="REFRAME", source="lens-build", weight=2.0),
        ])
        acts = iter_preference_acts()
        # Same content (REFRAME, u over m) → collapsed to one, ledger copy.
        match = [a for a in acts if a.privileged == "u" and a.sacrificed == "m"]
        assert len(match) == 1
        assert match[0].id == "ledger_id"  # ledger copy wins
        assert match[0].weight == 2.0


@pytest.mark.usefixtures("patch_trinity_home")
class TestUnifiedLedgerFile:
    def test_save_then_load_round_trips(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            save_preference_acts,
        )
        acts = [
            PreferenceAct(id="r1", trigger=MODEL_MISS, privileged="u", sacrificed="m", kind="REFRAME"),
            PreferenceAct(id="d1", trigger=SELF_EXPRESSED, privileged="a", sacrificed="b", kind="regret"),
        ]
        save_preference_acts(acts)
        back = load_preference_acts()
        assert [a.id for a in back] == ["r1", "d1"]
        assert [a.trigger for a in back] == [MODEL_MISS, SELF_EXPRESSED]

    def test_load_missing_file_is_empty(self):
        from trinity_local.me.preference_acts import load_preference_acts
        assert load_preference_acts() == []

    def test_save_empty_then_load_empty(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            save_preference_acts,
        )
        save_preference_acts([])
        assert load_preference_acts() == []

    def test_load_skips_malformed_and_underspecified(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            preference_acts_path,
        )
        p = preference_acts_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            '{"id":"r1","trigger":"model_miss","privileged":"u","sacrificed":"m"}\n'
            '{"trigger":"model_miss"}\n'   # no id → skip
            'not json\n',
            encoding="utf-8",
        )
        back = load_preference_acts()
        assert [a.id for a in back] == ["r1"]

    def test_load_skips_line_missing_required_fields(self):
        # #205: a line with id+trigger but missing privileged/sacrificed must
        # not crash from_dict's positional construction — skip it, keep the
        # valid one.
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            preference_acts_path,
        )
        p = preference_acts_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            '{"id":"r1","trigger":"model_miss","privileged":"u","sacrificed":"m"}\n'
            '{"id":"bad","trigger":"model_miss"}\n'   # no privileged/sacrificed -> skip, no crash
            ,
            encoding="utf-8",
        )
        back = load_preference_acts()
        assert [a.id for a in back] == ["r1"]


@pytest.mark.usefixtures("patch_trinity_home")
class TestLedgerClobberGuard:
    """The unified ledger is on its way to being the source of truth, so
    it carries the #194 clobber guard — a degenerate (empty / cliff-drop)
    overwrite of a populated ledger is refused."""

    def _acts(self, n):
        return [PreferenceAct(id=f"a{i}", trigger=MODEL_MISS, privileged="p", sacrificed="s")
                for i in range(n)]

    def test_cliff_drop_refused_and_ledger_preserved(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            preference_acts_path,
            save_preference_acts,
        )
        from trinity_local.me.turn_pairs import DegenerateExtractionError
        save_preference_acts(self._acts(6))
        with pytest.raises(DegenerateExtractionError):
            save_preference_acts([])  # 0 vs 6 existing → cliff-drop
        assert len(load_preference_acts()) == 6  # live ledger preserved
        assert (preference_acts_path().parent / "preference_acts.jsonl.degenerate").exists()

    def test_allow_shrink_escape_hatch(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            save_preference_acts,
        )
        save_preference_acts(self._acts(6))
        save_preference_acts([], allow_shrink=True)  # explicit genuine shrink
        assert load_preference_acts() == []

    def test_cold_start_empty_is_fine(self):
        from trinity_local.me.preference_acts import save_preference_acts
        save_preference_acts([])  # no existing → no guard

    def test_growth_unaffected(self):
        from trinity_local.me.preference_acts import (
            load_preference_acts,
            save_preference_acts,
        )
        save_preference_acts(self._acts(6))
        save_preference_acts(self._acts(8))  # growth → fine
        assert len(load_preference_acts()) == 8


class TestRenderUnifiedSection:
    def test_preference_acts_render_both_triggers(self):
        from trinity_local.me.pipeline import render_me_markdown
        from trinity_local.me.pair_mining import LensPair
        acts = [
            PreferenceAct(id="r1", trigger=MODEL_MISS, privileged="just do Y",
                          sacrificed="do X elaborately", kind="REFRAME", why="reframed"),
            PreferenceAct(id="d1", trigger=SELF_EXPRESSED, privileged="velocity",
                          sacrificed="polish", kind="satisfaction"),
        ]
        out = render_me_markdown(
            [LensPair(pole_a="a", pole_b="b", failure_a="", failure_b="", verdict="accepted")],
            [], None, None, acts,
        )
        assert "## Preference acts" in out
        assert "Model-miss" in out and "REFRAME" in out
        assert "Self-expressed" in out
        assert "**velocity** > polish" in out
        # The legacy heading is replaced when preference_acts are present.
        assert "## Implicit rejections" not in out

    def test_legacy_rejections_path_still_works(self):
        # Back-compat: no preference_acts → old section renders.
        from trinity_local.me.pipeline import render_me_markdown
        from trinity_local.me.pair_mining import LensPair
        rej = [RejectionSignal(id="r1", type="REFRAME", model_quote="m", user_substitute="u", why_signal="w")]
        out = render_me_markdown(
            [LensPair(pole_a="a", pole_b="b", failure_a="", failure_b="", verdict="accepted")],
            [], rej,
        )
        assert "## Implicit rejections" in out
        assert "## Preference acts" not in out
