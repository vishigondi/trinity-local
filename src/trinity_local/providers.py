from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ProviderConfig


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

    def _run_command(self, command: list[str], cwd: Path, *, timeout: float | None = None) -> ProviderResult:
        self._ensure_binary()
        t0 = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
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


class CLIProvider(BaseProvider):
    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        command = [*self.config.command, prompt, *self.config.args]
        return self._run_command(command, cwd)


class CodexProvider(BaseProvider):
    def run(self, prompt: str, cwd: Path) -> ProviderResult:
        command = [*self.config.command]
        args = list(self.config.args)
        if "--skip-git-repo-check" not in args:
            args.append("--skip-git-repo-check")
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


def make_provider(config: ProviderConfig) -> BaseProvider:
    if config.type == "cli":
        return CLIProvider(config)
    if config.type == "codex":
        return CodexProvider(config)
    if config.type == "mlx":
        return MLXProvider(config)
    raise ProviderError(f"Unsupported provider type: {config.type}")
