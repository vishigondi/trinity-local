from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ProviderConfig
from .runtime_env import run_with_runtime_env


# Defense-in-depth ceiling for any single provider invocation. The real bug
# we hit was inherited-stdin causing codex to block forever; that's fixed by
# `input=""` in `_run_command`. This timeout catches anything else that goes
# wrong (network, model server hang, etc.) without holding up the council.
# 8 minutes is comfortable headroom for codex on xhigh on a hard prompt; a
# single member taking longer is almost certainly stuck.
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 8 * 60


@dataclass
class ProviderResult:
    provider: str
    stdout: str
    stderr: str
    returncode: int
    elapsed_seconds: float = 0.0


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        raise NotImplementedError

    def _ensure_binary(self) -> None:
        binary = self.config.command[0]
        if shutil.which(binary) is None:
            raise ProviderError(f"Provider binary not found: {binary}")

    def _run_command(
        self,
        command: list[str],
        cwd: Path,
        *,
        timeout: float | None = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ) -> ProviderResult:
        self._ensure_binary()
        t0 = time.monotonic()
        try:
            # Provider CLIs are one-shot non-interactive invocations. Codex on
            # `xhigh` reasoning blocks for 30+ minutes reading from inherited
            # stdin (it treats non-TTY stdin as "additional prompt input").
            # Pass empty stdin so codex sees stdin closed immediately. Claude
            # and Gemini are unaffected — both ignore stdin in -p mode — but
            # closing stdin is correct universally for "run this CLI, capture
            # output" semantics.
            completed = run_with_runtime_env(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                input="",
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - t0
            return ProviderResult(
                provider=self.config.name,
                stdout=(exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                stderr=f"Timed out after {elapsed:.1f}s",
                returncode=-1,
                elapsed_seconds=elapsed,
            )
        elapsed = time.monotonic() - t0
        return ProviderResult(
            provider=self.config.name,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            returncode=completed.returncode,
            elapsed_seconds=elapsed,
        )


def _effective_model(config: ProviderConfig) -> str | None:
    """Return the configured model for this provider. Use CLI aliases
    like Claude's `'opus'` in config.json to track latest."""
    return config.model


def _effective_effort(config: ProviderConfig) -> str | None:
    """Return the configured reasoning/thinking effort level.

    Per-provider valid values (we pass through verbatim — the CLI itself
    validates):
      - claude:       low / medium / high / xhigh / max (CLI flag --effort)
      - codex:        none / low / medium / high / xhigh
                      (-c model_reasoning_effort=<level>; xhigh added with
                      GPT-5.5 in Codex CLI 0.124+; "minimal" deprecated in
                      favor of "none"/"low" depending on the CLI version)
      - antigravity:  NONE at CLI invocation time — agy CLI exposes no flag.
                      The user picks via agy's `/model` slash command, which
                      persists to ~/.gemini/antigravity-cli/settings.json and
                      sticks across sessions. Trinity reads that file to
                      display the active model+effort, but can't set it
                      programmatically per-council (no CLI flag).

    Trinity stores this on ProviderConfig.effort. agy users set it via
    `/model` inside agy; the live council card reads back the persisted
    selection so the chip shows the actual model+effort, not a guess.
    """
    return config.effort


def read_agy_active_model_raw() -> str | None:
    """The raw model SKU agy will ACTUALLY dispatch (e.g. ``"Gemini 3.5 Flash
    (High)"``), read from agy's own ``~/.gemini/antigravity-cli/settings.json``.

    This is the single honest source for antigravity's model: agy has no
    ``--model`` flag, so ``config.model`` is *ignored* by the CLI — the user's
    ``/model`` slash-command selection in that file is what runs. Returns
    ``None`` on any miss (file absent, unknown key, parse error) so callers
    degrade quietly to ``config.model``. The schema isn't public, so we probe a
    few likely keys.
    """
    try:
        import json as _json

        path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
        if not path.exists():
            return None
        settings = _json.loads(path.read_text())
        model = (
            settings.get("defaultReasoningModel")
            or settings.get("reasoningModel")
            or settings.get("model")
        )
        return model if isinstance(model, str) and model else None
    except Exception:
        return None


def dispatched_model(config: ProviderConfig) -> str | None:
    """The model that will ACTUALLY run for this provider — what eval/council
    must RECORD (the recorded == dispatched invariant). For antigravity this is
    agy's settings.json selection (``config.model`` is a dead value the CLI
    ignores); for every other provider it's ``config.model``.
    """
    if config.name == "antigravity":
        agy_model = read_agy_active_model_raw()
        if agy_model:
            return agy_model
    return config.model


class CLIProvider(BaseProvider):
    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        # MCP host sampling — preferred path for the Claude voice when
        # Trinity-MCP is loaded inside a chat client (Claude Desktop)
        # that advertised the `sampling` capability. Counts against
        # the user's regular Claude plan, NOT the post-2026-06-15 Agent
        # SDK credit pool.
        #
        # Other CLI-shaped providers (agy/Antigravity, etc.) don't go through
        # sampling — they don't have the billing problem `claude -p`
        # has, and the host can't promise to route to a non-Claude
        # model anyway. Gate on the provider name.
        if self.config.name == "claude":
            sampled = self._try_sampling(prompt)
            if sampled is not None:
                return sampled

        command = [*self.config.command]
        # Inject --model BEFORE the prompt-consuming flag (e.g. -p, --prompt).
        # If the last token of `command` is a flag, --model goes in front of it
        # so the prompt sits immediately after -p. Putting --model between -p
        # and the prompt makes Gemini fail with "Not enough arguments following: p".
        model = _effective_model(self.config)
        effort = _effective_effort(self.config)
        # Inject claude's --effort flag too (low/medium/high/xhigh/max).
        # Only Claude's CLI supports this — agy CLI has no equivalent
        # (Antigravity bakes the level into the model SKU and only
        # exposes selection via the IDE dropdown). Skip for non-claude
        # CLIProvider instances.
        inject_effort = (
            effort
            and self.config.name == "claude"
            and "--effort" not in command
            and "--effort" not in self.config.args
        )
        # Compute the tail-flag once so both --model and --effort can
        # land BEFORE it. Walk-through:
        #   command = ["claude", "-p"]  →  tail = "-p"
        #   command = ["claude"]        →  tail = None
        tail: str | None = None
        if len(command) > 1 and command[-1].startswith("-"):
            tail = command.pop()
        # --model is claude-only among CLIProvider configs (claude + agy).
        # agy has no --model flag — model is its `/model` slash-command — and
        # exits 2 if given one. Allowlist claude, mirroring the --effort gate.
        inject_model = (
            model
            and self.config.name == "claude"
            and "--model" not in command
            and "--model" not in self.config.args
        )
        if inject_model:
            command.extend(["--model", model])
        if inject_effort:
            command.extend(["--effort", effort])
        if tail is not None:
            command.append(tail)
        command.append(prompt)
        command.extend(self.config.args)
        return self._run_command(command, cwd)

    def _try_sampling(self, prompt: str) -> ProviderResult | None:
        """Attempt MCP host sampling for this Claude invocation.

        Returns a ProviderResult wrapping the sampled text on success,
        or None to signal the caller to fall through to the
        subprocess path. Never raises — the contract is "quietly
        degrade if sampling isn't available."
        """
        try:
            from .mcp_sampling import request_claude_sample
        except ImportError:
            return None
        t0 = time.monotonic()
        text = request_claude_sample(prompt)
        if text is None:
            return None
        return ProviderResult(
            provider=self.config.name,
            stdout=text.strip(),
            stderr="",
            returncode=0,
            elapsed_seconds=time.monotonic() - t0,
        )


class CodexProvider(BaseProvider):
    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        command = [*self.config.command]
        args = list(self.config.args)
        if "--skip-git-repo-check" not in args:
            args.append("--skip-git-repo-check")
        model = _effective_model(self.config)
        if model and "--model" not in args:
            args.extend(["--model", model])
        # Codex reasoning effort takes a TOML config override:
        #   codex exec -c model_reasoning_effort=xhigh
        # Valid values per Codex CLI 0.124+ docs:
        #   none / low / medium (default) / high / xhigh.
        # "xhigh" landed with GPT-5.5 in April 2026 — use it on hard
        # tasks where latency matters less ("the hardest asynchronous
        # agentic tasks or evals that test the bounds of model
        # intelligence" per OpenAI's release notes). Skip if the user
        # already passed -c model_reasoning_effort=... explicitly in
        # args; we don't want to layer two overrides.
        effort = _effective_effort(self.config)
        if effort:
            already_set = any(
                a == "-c" and i + 1 < len(args)
                and "model_reasoning_effort" in args[i + 1]
                for i, a in enumerate(args)
            )
            if not already_set:
                args.extend(["-c", f"model_reasoning_effort={effort}"])
        command.extend(args)
        command.append(prompt)
        return self._run_command(command, cwd)


class MLXProvider(BaseProvider):
    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        if not self.config.model:
            raise ProviderError("MLX provider requires a model name in config.")
        command = [
            *self.config.command,
            "--model",
            self.config.model,
            "--prompt",
            prompt,
            *self.config.args,
        ]
        return self._run_command(command, cwd)


class OllamaProvider(BaseProvider):
    """Local model dispatch via Ollama. Each model the user has pulled (via
    `ollama pull <name>`) is a candidate worker; the chosen model goes through
    `ollama run <model> "<prompt>"` and returns stdout.

    Cost: $0 (runs on user hardware). Latency depends on the model + hardware.
    Per spec-v1.5.md: when this works reliably at ship, the "and local models"
    line stays in the pitch; if dispatch is wobbly, cut it from the pitch.
    """

    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        if not self.config.model:
            raise ProviderError("Ollama provider requires a model name in config.")
        # Ollama CLI: `ollama run <model> "<prompt>"` reads prompt as argv,
        # outputs to stdout. The --hidethinking flag suppresses thinking
        # blocks from reasoning models; not all models support it so we
        # add it via config.args (configurable).
        command = [
            *self.config.command,
            "run",
            self.config.model,
            prompt,
            *self.config.args,
        ]
        return self._run_command(command, cwd)


def make_provider(config: ProviderConfig) -> BaseProvider:
    if config.type == "cli":
        return CLIProvider(config)
    if config.type == "codex":
        return CodexProvider(config)
    if config.type == "mlx":
        return MLXProvider(config)
    if config.type == "ollama":
        return OllamaProvider(config)
    raise ProviderError(f"Unsupported provider type: {config.type}")
