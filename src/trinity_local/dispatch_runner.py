from __future__ import annotations

import json
import subprocess
import sys

from .dispatch_registry import command_for_dispatch, make_dispatch_action
from .runtime_env import build_runtime_env, runtime_path_prefix


def _load_payload(argv: list[str]) -> str:
    if argv:
        return argv[0]
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    payload_text = _load_payload(list(argv if argv is not None else sys.argv[1:]))
    if not payload_text.strip():
        print("trinity-dispatch: empty payload", file=sys.stderr)
        return 1

    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        print(f"trinity-dispatch: invalid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        action = make_dispatch_action(
            raw["name"],
            args=raw.get("args", {}),
            task_id=raw.get("task_id"),
            metadata=raw.get("metadata", {}),
        )
    except Exception as exc:
        print(f"trinity-dispatch: invalid action: {exc}", file=sys.stderr)
        return 1

    command = command_for_dispatch(action)
    if not command:
        print(f"trinity-dispatch: no command mapping for action {action.name}", file=sys.stderr)
        return 1

    # Suppress stdout so the macOS Shortcut runner doesn't pick up paths
    # from JSON output and auto-open them (which caused the launchpad to
    # spawn in a new tab seconds after a council was launched). Stderr is
    # preserved so failures still surface via the Shortcut's error path.
    wrapped = f'export PATH="{runtime_path_prefix()}:$PATH"; {command}'
    completed = subprocess.run(
        ["/bin/zsh", "-lc", wrapped],
        check=False,
        env=build_runtime_env(),
        stdout=subprocess.DEVNULL,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
