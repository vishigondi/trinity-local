"""Privacy guards for the outbound telemetry + share-card surfaces.

Founder principle: telemetry stays default-ON to close the feedback loop,
but it must be PROVABLY no-PII. These tests assert the contract
structurally rather than by code review:

  #231(a) the council event payload is a strict subset of the disclosed
          categorical params, and no value carries prompt/lens/
          user_substitute text.
  #231(b) the elo_snapshot (provider win-rates) the launchpad transmits is
          disclosed (within DISCLOSED_ELO_KEYS) and carries no free text.
  #231(c) the browser send path is gated on the SAME credentials guarantee
          as Python — absent GA4 creds, no `endpoint` reaches pageData, so
          `maybeSendTelemetry()` can't POST.
  #237   the share-card PNG generators (council/eval) don't bake raw
          prompt / member-output / user_substitute text into the image.

Per CLAUDE.md "Architectural commitments" #2: only categorical routing
labels leave the machine; NO prompt content, NO lens text.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trinity_local import telemetry as t

# #231/#237: this file is the written contract for the telemetry no-PII
# payload API (build_outbound_event_payload / build_elo_snapshot /
# _browser_send_enabled / DISCLOSED_* constants) + the share-card content
# redaction. Implemented in telemetry.py + the card collectors (v1.7.80);
# the TEST-FIRST xfail marker was removed once the contract went green.


# A distinctive sentinel we feed into the corpus / params; if it ever
# shows up in an outbound payload or a card, that's a leak.
SECRET = "ZZZSECRETPROMPTLEAKZZZ"


def _write_council_outcome(home: Path) -> None:
    """A saved council outcome whose member outputs + prompt-ish fields
    carry the SECRET sentinel. The elo snapshot reads these files; the
    guard proves none of that free text reaches the wire payload."""
    payload = {
        "council_run_id": "council_pii_guard",
        "bundle_id": "bundle_pii_guard",
        "primary_provider": "claude",
        "winner_provider": "antigravity",
        "created_at": "2026-05-29T10:00:00+00:00",
        "task_text": f"Decide the launch plan {SECRET}",
        "member_results": [
            {"provider": "claude", "model": "m", "output_text": f"draft {SECRET}"},
            {"provider": "antigravity", "model": "m", "output_text": f"draft {SECRET}"},
            {"provider": "codex", "model": "m", "output_text": f"draft {SECRET}"},
        ],
        "routing_label": {"task_type": "design", "winner": "antigravity"},
    }
    path = home / "council_outcomes" / "council_pii_guard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_ga4_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the GA4 + custom-endpoint env vars OFF for every test here
    so the credentials gate is exercised in its real shipping state.
    Tests that need creds set them explicitly."""
    monkeypatch.delenv("TRINITY_GA4_MEASUREMENT_ID", raising=False)
    monkeypatch.delenv("TRINITY_GA4_API_SECRET", raising=False)
    monkeypatch.delenv("TRINITY_TELEMETRY_ENDPOINT", raising=False)


# ── #231(a) ───────────────────────────────────────────────────────────

class TestTelemetryPayloadIsCategoricalOnly:
    def test_telemetry_payload_is_categorical_only(self) -> None:
        """The outbound council event payload's params are a subset of the
        disclosed categorical set, and no value carries free text."""
        # Build the payload exactly as council_runner does — plus hostile
        # extra keys an over-eager caller might pass. The allowlist must
        # drop them.
        payload = t.build_outbound_event_payload(
            "council_complete",
            {
                "task_type": "design",
                "winner": "claude",
                "member_count": 3,
                "mode": "parallel",
                # Hostile injections — must NOT survive.
                "prompt": f"the user asked {SECRET}",
                "lens": f"tension pole {SECRET}",
                "user_substitute": f"rewrite as {SECRET}",
                "output_text": f"member draft {SECRET}",
            },
        )
        params = payload["events"][0]["params"]
        # Keys are a strict subset of the disclosed categorical contract.
        assert set(params.keys()) <= {"task_type", "winner", "member_count", "mode"}
        assert set(params.keys()) <= t.DISCLOSED_EVENT_PARAMS
        # No value (anywhere in the serialized payload) carries the leak.
        blob = json.dumps(payload)
        assert SECRET not in blob
        # And the disclosed param values are the categorical ones we passed.
        assert params["task_type"] == "design"
        assert params["winner"] == "claude"
        assert params["member_count"] == 3
        assert params["mode"] == "parallel"

    def test_disclosed_param_set_matches_council_runner_emission(self) -> None:
        """The council_runner emits exactly the disclosed param names — if
        that emission grows a new field, this fails until it's disclosed."""
        emitted = {"task_type", "winner", "member_count", "mode"}
        assert emitted == set(t.DISCLOSED_EVENT_PARAMS)


# ── #231(b) ───────────────────────────────────────────────────────────

class TestEloSnapshotIsDisclosed:
    def test_elo_snapshot_keys_are_disclosed(self, patch_trinity_home: Path) -> None:
        _write_council_outcome(patch_trinity_home)
        snapshot = t.build_elo_snapshot()
        assert set(snapshot.keys()) <= t.DISCLOSED_ELO_KEYS
        # Provider sub-dicts carry only numeric/categorical stats.
        for provider, stats in snapshot["providers"].items():
            assert set(stats.keys()) <= t.DISCLOSED_ELO_PROVIDER_KEYS
            # provider key is a slug, values are numbers.
            assert isinstance(provider, str)
            for v in stats.values():
                assert isinstance(v, (int, float))

    def test_launchpad_elo_event_carries_no_free_text(
        self, patch_trinity_home: Path
    ) -> None:
        """The elo_event the browser transmits must not carry the SECRET
        free text that lives in the underlying council outcome."""
        _write_council_outcome(patch_trinity_home)
        t.enable_telemetry()
        state = t.launchpad_telemetry_state()
        blob = json.dumps(state["elo_event"]) + json.dumps(state["view_event"])
        blob += json.dumps(state["snapshot"])
        assert SECRET not in blob
        # elo_event is a disclosed-snapshot superset + the install id +
        # categorical event fields — assert its data keys stay disclosed.
        elo_event = state["elo_event"]
        allowed = t.DISCLOSED_ELO_KEYS | {
            "event", "share_install_id", "app_version", "timestamp",
        }
        assert set(elo_event.keys()) <= allowed


# ── #231(c) ───────────────────────────────────────────────────────────

class TestBrowserSendHonorsCredentialGate:
    def test_endpoint_stripped_from_pagedata_without_creds(
        self, patch_trinity_home: Path
    ) -> None:
        """Absent GA4 creds, the Python path no-ops — the browser must too.
        With no `endpoint` in pageData, maybeSendTelemetry() returns early."""
        t.enable_telemetry()
        state = t.launchpad_telemetry_state()
        assert "endpoint" not in state["settings"]
        assert t._browser_send_enabled() is False

    def test_endpoint_present_with_ga4_creds(
        self, patch_trinity_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRINITY_GA4_MEASUREMENT_ID", "G-TESTXXXX")
        monkeypatch.setenv("TRINITY_GA4_API_SECRET", "test-secret")
        t.enable_telemetry()
        state = t.launchpad_telemetry_state()
        assert state["settings"].get("endpoint")
        assert t._browser_send_enabled() is True

    def test_endpoint_present_with_custom_collector(
        self, patch_trinity_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The explicit-collector escape hatch opts the browser back in."""
        monkeypatch.setenv(
            "TRINITY_TELEMETRY_ENDPOINT", "https://collector.example/collect"
        )
        t.enable_telemetry()
        state = t.launchpad_telemetry_state()
        assert state["settings"].get("endpoint")
        assert t._browser_send_enabled() is True


# ── #237 share-card content leak ──────────────────────────────────────

class TestShareCardsNoRawContentLeak:
    """The card PNGs render text into the image. council/eval cards must
    only carry chairman-extracted claims + scores + categorical labels —
    never the verbatim prompt, member output, or user_substitute. These
    guards assert the COLLECT step (the data-shaping boundary) drops raw
    content; that's where a leak would enter the renderer."""

    def test_council_card_excludes_prompt_and_member_output(self) -> None:
        from trinity_local.council_card import collect_card_data_from_outcome

        class _Member:
            def __init__(self, provider: str) -> None:
                self.provider = provider

        class _Label:
            task_type = "design"
            winner = "claude"
            agreed_claims = ["models converged on clarity"]
            disagreed_claims = [
                {"provider": "codex", "claim": "ship sooner",
                 "why_matters": "speed beats polish here"}
            ]

        class _Outcome:
            member_results = [_Member("claude"), _Member("codex")]
            winner_provider = "claude"
            routing_label = _Label()
            # Fields that MUST NOT cross to the card:
            task_text = f"the user asked {SECRET}"
            responses = [{"output_text": f"member draft {SECRET}"}]

        data = collect_card_data_from_outcome(_Outcome())
        blob = json.dumps(data.to_dict())
        assert SECRET not in blob
        # Only chairman-extracted claims survive.
        assert data.agreed_claims == ["models converged on clarity"]
        assert data.disagreed_claim == "ship sooner"

    def test_eval_card_carries_only_scores_and_labels(self) -> None:
        from trinity_local.eval_card import collect_card_data_from_result

        class _Result:
            target_provider = "claude"
            target_model = "claude-opus-4-8"
            aggregate_score = 0.66
            items_total = 20
            items_completed = 20
            by_rejection_type = {
                "REFRAME": {"mean_score": 0.8, "count": 5},
                "COMPRESSION": {"mean_score": 0.5, "count": 4},
            }

        data = collect_card_data_from_result(_Result())
        blob = json.dumps(data.to_dict())
        assert SECRET not in blob
        # Only categorical axis names + numeric scores cross.
        for axis_name, mean, count in data.by_axis:
            assert axis_name in {"REFRAME", "COMPRESSION"}
            assert isinstance(mean, float)
            assert isinstance(count, int)
