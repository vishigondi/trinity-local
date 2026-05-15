from __future__ import annotations

import argparse
import importlib

import pytest

from trinity_local import main


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return subparsers_action.choices


def test_build_parser_registers_core_commands():
    parser = main.build_parser()
    choices = _subparser_choices(parser)
    assert "portal-html" in choices
    assert "council-launch" in choices
    assert "install-app" in choices
    assert "telemetry-show" in choices


def test_build_parser_skips_missing_optional_module(monkeypatch: pytest.MonkeyPatch):
    real_import = importlib.import_module
    optional_path = "trinity_local.commands.install"

    def fake_import(name: str, package: str | None = None):
        if name == optional_path:
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return real_import(name, package)

    monkeypatch.setattr(main.importlib, "import_module", fake_import)

    parser = main.build_parser()
    choices = _subparser_choices(parser)
    assert "install-mcp" not in choices
    assert "portal-html" in choices


def test_load_mcp_runner_errors_cleanly_when_missing(monkeypatch: pytest.MonkeyPatch):
    real_import = importlib.import_module
    module_path = "trinity_local.mcp_server"

    def fake_import(name: str, package: str | None = None):
        if name == module_path:
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return real_import(name, package)

    monkeypatch.setattr(main.importlib, "import_module", fake_import)

    with pytest.raises(SystemExit, match="MCP server support is not available"):
        main._load_mcp_runner()


def test_pin_hf_offline_sets_defaults(monkeypatch: pytest.MonkeyPatch):
    """`_pin_hf_offline` should set HF/transformers offline env vars when
    they are unset, so the running system never makes outbound HF calls."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)

    main._pin_hf_offline()

    import os
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_pin_hf_offline_preserves_user_override(monkeypatch: pytest.MonkeyPatch):
    """A user who explicitly sets HF_HUB_OFFLINE=0 (e.g. to pull a new
    model) should not have it stomped — `setdefault` semantics."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")

    main._pin_hf_offline()

    import os
    assert os.environ["HF_HUB_OFFLINE"] == "0"
