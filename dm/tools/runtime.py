# Copyright (c) 2026 ctr-native contributors — MIT license.
"""How the runtime is invoked: one place, for the launcher, the smoke and the
graphical diagnostic alike (the plan's centralization of Zakuro invocation)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ZakuroRun:
    """One invocation's command and environment, built once, shared anywhere."""
    command: list
    env: dict

    def run(self, runner, timeout: int = 180):
        return runner(self.command, env=self.env, timeout=timeout)


def environment(home: Path, extra: dict | None = None) -> dict:
    """The standard environment: HOME at the sandbox, brew codecs preserved."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib"
    if extra:
        env.update(extra)
    for key in ("DYLD_LIBRARY_PATH",):
        env.pop(key, None)
    return env


def headless_command(host_bin: Path, *, rom: Path, dylib: Path, frames: int = 120,
                     mute: bool = True, language: str | None = None,
                     scale: int | None = None) -> list:
    """The headless smoke arguments, in the launcher's own order."""
    command = [str(host_bin), "--headless", str(frames)]
    if mute:
        command.append("--mute")
    command += ["--recompiled", str(dylib)]
    if language:
        command += ["--language", language]
    if scale:
        command += ["--scale", str(scale)]
    command.append(str(rom))
    return command
