"""Tests for the council-first frontend flow."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from trinity_local.adapters import AdapterStatus
from trinity_local.commands.council import handle_council_launch
from trinity_local.commands.telemetry import handle_auto_ingest_disable, handle_auto_ingest_enable
from trinity_local.commands.watch import handle_watch_once
from trinity_local.config import AppConfig, ProviderConfig
from trinity_local.council_feedback import append_council_feedback
from trinity_local.council_runner import run_council
from trinity_local.council_runtime import create_prompt_bundle, save_prompt_bundle
from trinity_local.dispatch_registry import command_for_dispatch, make_dispatch_action
from trinity_local.portal_page import install_launchpad_shortcuts, write_portal_html
from trinity_local.providers import ProviderError, ProviderResult
from trinity_local.shortcut_setup import _render_dispatch_wrapper
from trinity_local.telemetry import (
    build_elo_snapshot,
    disable_telemetry,
    enable_telemetry,
    launchpad_telemetry_state,
    load_telemetry_settings,
    reset_share_install_id,
)


def _write_council_fixture(home: Path) -> tuple[str, str]:
    bundle = create_prompt_bundle(
        task_cluster_id="cluster_marketing_launch",
        task_text="Write a launch announcement for Trinity Local",
        goal="Find the strongest answer.",
        comparison_instructions="Prefer the clearest and most persuasive draft.",
        metadata={"project_hint": "marketing"},
    )
    save_prompt_bundle(bundle)

    council_id = "council_test_launchpad"
    payload = {
        "council_run_id": council_id,
        "bundle_id": bundle.bundle_id,
        "task_cluster_id": bundle.task_cluster_id,
        "primary_provider": "claude",
        "winner_provider": "gemini",
        "created_at": "2026-04-28T10:00:00+00:00",
        "member_results": [
            {
                "provider": "claude",
                "model": "claude-sonnet",
                "output_text": "Launch copy focused on product clarity.",
            },
            {
                "provider": "gemini",
                "model": "gemini-pro",
                "output_text": "Launch copy focused on narrative and social spread.",
            },
            {
                "provider": "codex",
                "model": "o3",
                "output_text": "Launch copy focused on technical builders.",
            },
        ],
        "peer_reviews": [],
    }
    path = home / "council_outcomes" / f"{council_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return bundle.bundle_id, council_id


class TestLaunchpadFlow:
    def test_write_portal_html_renders_primary_flow(self, patch_trinity_home: Path, monkeypatch):
        _write_council_fixture(patch_trinity_home)
        enable_telemetry(endpoint="https://telemetry.example/collect")
        monkeypatch.setattr(
            "trinity_local.portal_page.check_all_adapters",
            lambda: [
                AdapterStatus(provider="claude", cli_name="claude", installed=True, version="1.0.0"),
                AdapterStatus(
                    provider="codex",
                    cli_name="codex",
                    installed=False,
                    error="codex not found in PATH",
                ),
            ],
        )

        path = write_portal_html(title="Launchpad")

        assert path.exists()
        html = path.read_text(encoding="utf-8")
        assert "Run Your First Council" in html
        assert "launch_council" in html
        assert "Launchpad controls" in html
        assert "petite-vue@0.4.1" in html
        assert "chart.umd.min.js" in html
        assert "Write a launch announcement for Trinity Local" in html
        assert "Open previous council reviews" in html
        assert "telemetry-enable" in html
        assert "auto-ingest-enable" in html
        assert "Ingest transcripts once now" in html
        assert "ACTIVE_OPERATION_KEY" in html
        assert "Reference evals" in html
        assert "liveReviewUrl" in html
        assert "View live review" in html
        assert "Stop council" in html
        assert "Codex CLI" in html
        assert "npm install -g @openai/codex && codex --login" in html
        assert "{{ example }}" in html
        assert "{{ telemetry.enabled ? 'On' : 'Off' }}" in html
        assert "{{ operation.label }}" in html
        assert "councilLoadingMessages" in html
        assert "Reticulating splines..." in html
        assert "Queued" in html
        assert "Running" in html
        assert "@{ example }" not in html
        assert "signal_page" not in html
        assert "Open review and choose winner" not in html

    def test_install_launchpad_shortcuts_writes_desktop_and_app_links(self, patch_trinity_home: Path, tmp_path: Path):
        _write_council_fixture(patch_trinity_home)
        launchpad_path = write_portal_html(title="Launchpad")
        desktop_dir = tmp_path / "Desktop"
        applications_dir = tmp_path / "Applications"

        def fake_compile(target: Path, script: str) -> None:
            (target / "Contents" / "Resources").mkdir(parents=True, exist_ok=True)
            (target / "Contents" / "Info.plist").write_text(script, encoding="utf-8")

        import trinity_local.portal_page as portal_page

        original_compile = portal_page._compile_launchpad_app
        original_find_icon = portal_page._find_launchpad_icon_source
        original_apply_icon = portal_page._apply_launchpad_icon
        portal_page._compile_launchpad_app = fake_compile
        portal_page._find_launchpad_icon_source = lambda: None
        portal_page._apply_launchpad_icon = lambda app_path, image_path: None
        try:
            written = install_launchpad_shortcuts(
                launchpad_path=launchpad_path,
                destinations=[desktop_dir, applications_dir],
            )
        finally:
            portal_page._compile_launchpad_app = original_compile
            portal_page._find_launchpad_icon_source = original_find_icon
            portal_page._apply_launchpad_icon = original_apply_icon

        assert len(written) == 2
        app_path = applications_dir / "Trinity.app"
        desktop_path = desktop_dir / "Trinity.app"
        assert app_path.exists()
        assert app_path.is_dir()
        assert desktop_path.exists()
        assert desktop_path.is_dir()


class TestTelemetryFlow:
    def test_enable_disable_and_reset_round_trip(self, patch_trinity_home: Path):
        _write_council_fixture(patch_trinity_home)

        enabled = enable_telemetry(endpoint="https://telemetry.example/collect")
        assert enabled.sharing_enabled is True
        assert enabled.share_usage_events is True
        assert enabled.share_elo_summaries is True
        assert enabled.share_install_id.startswith("share_")

        persisted = load_telemetry_settings()
        assert persisted.endpoint == "https://telemetry.example/collect"
        assert persisted.share_install_id == enabled.share_install_id

        state = launchpad_telemetry_state()
        assert state["settings"]["sharing_enabled"] is True
        assert state["view_event"]["event"] == "launchpad_view"
        assert state["elo_event"]["event"] == "elo_snapshot"
        assert state["snapshot"]["council_count"] == 1
        assert state["snapshot"]["providers"]["gemini"]["elo"] > 1500

        reset = reset_share_install_id()
        assert reset.share_install_id.startswith("share_")
        assert reset.share_install_id != enabled.share_install_id

        disabled = disable_telemetry()
        assert disabled.sharing_enabled is False

    def test_elo_snapshot_prefers_saved_council_feedback(self, patch_trinity_home: Path):
        _write_council_fixture(patch_trinity_home)

        baseline = build_elo_snapshot()
        assert baseline["providers"]["gemini"]["elo"] > baseline["providers"]["claude"]["elo"]

        append_council_feedback(
            council_id="council_test_launchpad",
            provider="claude",
            answer_label="A",
        )
        updated = build_elo_snapshot()
        assert updated["providers"]["claude"]["elo"] > updated["providers"]["gemini"]["elo"]
        assert updated["providers"]["claude"]["wins"] == 1
        assert updated["providers"]["claude"]["total_games"] == 1


class TestDispatchFlow:
    def test_launch_council_dispatch_maps_to_command(self):
        action = make_dispatch_action(
            "launch_council",
            args={
                "task": "Write a launch announcement",
                "goal": "Find the strongest answer.",
                "members": ["claude", "gemini", "codex"],
                "primary_provider": "claude",
                "cwd": "/tmp/project",
                "notify": True,
                "open_browser": True,
            },
        )

        command = command_for_dispatch(action)

        assert command is not None
        assert command.startswith("trinity-local council-launch")
        assert "--task 'Write a launch announcement'" in command
        assert "--members claude gemini codex" in command
        assert "--primary-provider claude" in command
        assert "--cwd /tmp/project" in command
        assert "--notify" in command
        assert "--open-browser" in command

    def test_stop_council_dispatch_maps_to_command(self):
        action = make_dispatch_action(
            "stop_council",
            args={"status_token": "launch_123"},
        )

        command = command_for_dispatch(action)

        assert command == "trinity-local council-stop --status-token launch_123"


class TestCouncilLaunchCommand:
    def test_handle_council_launch_creates_bundle_and_delegates(
        self,
        patch_trinity_home: Path,
        monkeypatch,
    ):
        captured: dict[str, object] = {}

        def fake_start(args):
            captured["bundle"] = args.bundle
            captured["members"] = args.members
            captured["primary_provider"] = args.primary_provider
            captured["cwd"] = args.cwd
            captured["notify"] = args.notify
            captured["open_browser"] = args.open_browser
            captured["without_peer_review"] = args.without_peer_review

        monkeypatch.setattr("trinity_local.commands.council.handle_council_start", fake_start)

        args = SimpleNamespace(
            task="Compare launch announcement drafts",
            goal="Pick the strongest launch copy.",
            instructions="Prefer the clearest and most persuasive draft.",
            context_file=None,
            project_hint="marketing",
            members=["claude", "gemini"],
            primary_provider="claude",
            cwd=".",
            open_browser=True,
            notify=True,
            without_peer_review=False,
            config=None,
            status_token="launch_token_123",
        )

        handle_council_launch(args)

        bundle_id = str(captured["bundle"])
        bundle_path = patch_trinity_home / "prompt_bundles" / f"{bundle_id}.json"
        assert bundle_path.exists()
        raw = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert raw["task_text"] == "Compare launch announcement drafts"
        assert raw["goal"] == "Pick the strongest launch copy."
        assert raw["comparison_instructions"] == "Prefer the clearest and most persuasive draft."
        assert raw["origin_provider"] == "launchpad"
        assert raw["origin_session_id"] == "launch_token_123"
        assert raw["metadata"]["launch_source"] == "launchpad"
        assert raw["metadata"]["project_hint"] == "marketing"
        assert captured["members"] == ["claude", "gemini"]
        assert captured["primary_provider"] == "claude"
        assert captured["notify"] is True
        assert captured["open_browser"] is True
        assert (patch_trinity_home / "review_pages" / "live_council.html").exists()


class TestWatchStatusFlow:
    def test_watch_once_with_status_token_writes_completion_status(self, monkeypatch):
        captured: list[dict] = []

        def fake_write_status(token, **payload):
            captured.append({"token": token, **payload})

        def fake_watch_once(*, sources, notify):
            return SimpleNamespace(
                scanned=3,
                tasks_written=1,
                actions_written=2,
                portal_path="/tmp/launchpad.html",
            )

        monkeypatch.setattr("trinity_local.commands.watch.write_council_status", fake_write_status)
        monkeypatch.setattr("trinity_local.commands.watch.watch_once", fake_watch_once)

        args = SimpleNamespace(
            sources=["claude", "codex"],
            notify=True,
            status_token="ingest_test_token",
        )

        handle_watch_once(args)

        assert captured[0]["status"] == "running"
        assert captured[0]["metadata"]["kind"] == "ingest"
        assert captured[-1]["status"] == "completed"
        assert captured[-1]["review_path"] == "/tmp/launchpad.html"
        assert captured[-1]["metadata"]["actions_written"] == 2


class TestAutoIngestSettings:
    def test_auto_ingest_enable_disable_controls_daemon(self, patch_trinity_home: Path, monkeypatch):
        calls: list[str] = []

        monkeypatch.setattr(
            "trinity_local.commands.telemetry.daemon_install",
            lambda: (calls.append("install") or True, "installed"),
        )
        monkeypatch.setattr(
            "trinity_local.commands.telemetry.daemon_start",
            lambda: (calls.append("start") or True, "started"),
        )
        monkeypatch.setattr(
            "trinity_local.commands.telemetry.daemon_stop",
            lambda: (calls.append("stop") or True, "stopped"),
        )
        monkeypatch.setattr(
            "trinity_local.commands.telemetry.daemon_status",
            lambda: (True, "running"),
        )
        monkeypatch.setattr(
            "trinity_local.commands.telemetry.write_portal_html",
            lambda: Path("/tmp/launchpad.html"),
        )

        handle_auto_ingest_enable(SimpleNamespace())
        assert load_telemetry_settings().auto_ingest_transcript is True
        assert "install" in calls
        assert "start" in calls

        handle_auto_ingest_disable(SimpleNamespace())
        assert load_telemetry_settings().auto_ingest_transcript is False
        assert "stop" in calls


class TestDispatchWrapper:
    def test_render_dispatch_wrapper_includes_common_bin_paths(self):
        script = _render_dispatch_wrapper("/Users/openclaw/projects/trinity-local/.venv/bin/python3")

        assert "/Users/openclaw/.local/bin" in script
        assert "/opt/homebrew/bin" in script
        assert "/usr/local/bin" in script
        assert "EXTRA_PATHS" in script


class TestCouncilFailureMetadata:
    def test_run_council_records_member_and_synthesis_failures(
        self,
        patch_trinity_home: Path,
        monkeypatch,
    ):
        config = AppConfig(
            max_turns=4,
            default_task_kind="general",
            notifications=False,
            providers={
                "claude": ProviderConfig(
                    name="claude",
                    type="cli",
                    enabled=True,
                    label="Claude",
                    command=["claude"],
                    args=[],
                    roles=set(),
                    task_kinds=set(),
                ),
                "gemini": ProviderConfig(
                    name="gemini",
                    type="cli",
                    enabled=True,
                    label="Gemini",
                    command=["gemini"],
                    args=[],
                    roles=set(),
                    task_kinds=set(),
                ),
                "codex": ProviderConfig(
                    name="codex",
                    type="codex",
                    enabled=True,
                    label="Codex",
                    command=["codex"],
                    args=[],
                    roles=set(),
                    task_kinds=set(),
                ),
            },
            role_preferences={},
            task_preferences={},
        )
        bundle = create_prompt_bundle(
            task_cluster_id="cluster_failure_case",
            task_text="Compare answers for this market question.",
            goal="Find the strongest answer.",
            comparison_instructions="Prefer the clearest answer.",
        )
        save_prompt_bundle(bundle)

        class FakeProvider:
            def __init__(self, name: str) -> None:
                self.name = name

            def run(self, prompt: str, cwd: Path) -> ProviderResult:
                if self.name == "gemini":
                    return ProviderResult(
                        provider="gemini",
                        stdout="Gemini answer",
                        stderr="",
                        returncode=0,
                    )
                raise ProviderError(f"Provider binary not found: {self.name}")

        monkeypatch.setattr(
            "trinity_local.council_runner.make_provider",
            lambda provider_config: FakeProvider(provider_config.name),
        )

        result = run_council(
            config=config,
            bundle=bundle,
            member_providers=["claude", "gemini", "codex"],
            primary_provider="claude",
            cwd=patch_trinity_home,
            with_peer_review=False,
        )

        metadata = result.outcome.metadata
        assert metadata["failed_members"] == ["claude", "codex"]
        assert metadata["failed_reviewers"] == []
        assert metadata["synthesis_error"] == "Provider binary not found: claude"
        assert metadata["member_failures"] == [
            {
                "provider": "claude",
                "stage": "member",
                "reason": "exception",
                "error": "Provider binary not found: claude",
            },
            {
                "provider": "codex",
                "stage": "member",
                "reason": "exception",
                "error": "Provider binary not found: codex",
            },
        ]
        assert metadata["reviewer_failures"] == []
        assert metadata["synthesis_failure"] == {
            "provider": "claude",
            "stage": "primary_synthesis",
            "reason": "exception",
            "error": "Provider binary not found: claude",
        }


class TestCouncilStopCommand:
    def test_handle_council_stop_updates_status_and_kills_process(self, patch_trinity_home: Path, monkeypatch, capsys):
        from trinity_local.commands.council import handle_council_stop
        from trinity_local.council_status import write_council_status

        write_council_status(
            "launch_stop_123",
            status="running",
            task_text="Stop this council",
            bundle_id="bundle_123",
            council_id="bundle_123",
            metadata={
                "kind": "council",
                "members": ["claude", "gemini", "codex"],
                "pid": 111,
                "process_group_id": 222,
            },
        )
        monkeypatch.setattr("trinity_local.commands.council.write_portal_html", lambda: Path("/tmp/launchpad.html"))
        killed: list[tuple[int, int]] = []
        monkeypatch.setattr("trinity_local.commands.council.os.killpg", lambda pgid, sig: killed.append((pgid, sig)))

        handle_council_stop(SimpleNamespace(status_token="launch_stop_123"))

        payload = json.loads(capsys.readouterr().out)
        assert payload["stopped"] is True
        assert payload["process_group_id"] == 222
        assert killed

        status_path = patch_trinity_home / "portal_pages" / "status" / "council_status_launch_stop_123.json"
        updated = json.loads(status_path.read_text(encoding="utf-8"))
        assert updated["status"] == "canceled"
        assert updated["error"] == "Council stopped by user."
