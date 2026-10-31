# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Progress reporting for the build: per-stage bars, or one JSON event per line.

nxnative-style: a stage list with [k/n] prefixes, a bar when the work can be
counted (ETA from the rate so far), and stage summaries. `--progress json`
emits `stage`, `step`, `progress`, `stage_end` and `say` events for GUI
frontends; `auto` picks a bar on a terminal, plain lines otherwise; `off`
prints only stage starts and ends. Rendering failures fall back to quiet
lines: progress never crashes a build.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Any

BAR_WIDTH = 20


@dataclass
class StageState:
    index: int  # k: the caller numbers stages, so [k/n] stays true
    of: int  # n
    stage_name: str
    started: float = 0.0
    current_step: str = ""
    done: float = 0.0
    total: float | None = None
    unit: str = ""
    est: bool | None = None


class Progress:
    """Tracks k/n stages; prints in place or emits JSON; never crashes a build."""

    def __init__(self, mode: str = "auto") -> None:
        automatic = "bar" if sys.stdout.isatty() else "lines"
        self.mode = automatic if not mode or mode == "auto" else mode
        self.stream = self.mode == "json"
        self._last_frame_len = 0
        self._last_beat = 0.0

    def stage(self, index: int, of: int, name: str, hint: str = "") -> StageState:
        state = StageState(index=index, of=of, stage_name=name, started=time.monotonic())
        if self.stream:
            self._write({"ev": "stage", "t": round(time.monotonic(), 3), "k": index, "n": of, "name": name})
        elif self.mode != "off":
            hint_text = f" · {hint}" if hint else ""
            self._line(f"[{clock()}] ·  [{index}/{of}] {name}{hint_text}")
        return state

    def step(self, state: StageState, text: str) -> None:
        state.current_step = text
        if self.stream:
            self._write({
                "ev": "step", "t": round(time.monotonic(), 3),
                "k": state.index, "n": state.of, "name": state.stage_name, "step": text,
            })
        elif self.mode == "bar":
            self._frame(state)

    def count(
        self, state: StageState, done: float, total: float | None, unit: str = "", est: bool | None = None
    ) -> None:
        state.done, state.total, state.unit = done, total, unit
        if est is not None:
            state.est = est
        if self.stream:
            self._write({
                "ev": "progress", "t": round(time.monotonic(), 3),
                "k": state.index, "n": state.of, "name": state.stage_name,
                "done": done, "total": total, "unit": unit,
                "frac": round(done / total, 4) if total else None,
                "eta": self._eta(state),
            })
            return
        if self.mode == "bar":
            self._frame(state)
        elif self.mode == "lines":
            now = time.monotonic()
            if now - self._last_beat > 30:
                self._last_beat = now
                self._line(f"[{clock()}]   {self._progress_text(state)}")

    def stage_end(self, state: StageState, summary: str, ok: bool = True) -> None:
        elapsed = time.monotonic() - state.started
        if self.stream:
            self._write({
                "ev": "stage_end", "t": round(time.monotonic(), 3),
                "k": state.index, "n": state.of, "name": state.stage_name,
                "ok": ok, "summary": summary, "elapsed": round(elapsed, 1),
            })
        else:
            self._clear_frame()
            mark = "✓" if ok else "✗"
            notes = " · ".join(part for part in (summary, self._progress_text(state)) if part)
            self._line(f"[{clock()}] {mark} [{state.index}/{state.of}] {state.stage_name}"
                       f" ({int(elapsed)}s){' · ' + notes if notes else ''}")
        state.done = state.total = 0.0
        state.current_step = ""

    def say(self, message: str, error: bool = False) -> None:
        if self.stream:
            self._write({"ev": "say", "t": round(time.monotonic(), 3), "msg": message, "error": error})
        elif self.mode != "off":
            self._line(f"[{clock()}] {'ERROR: ' if error else ''}{message}")

    # -- internals -----------------------------------------------------------

    def _eta(self, state: StageState) -> float | None:
        elapsed = time.monotonic() - state.started
        if state.total and state.done > 0 and elapsed > 1.5:
            return round(max(elapsed * state.total / state.done - elapsed, 0), 1)
        return None

    def _progress_text(self, state: StageState) -> str:
        if not state.total:
            return state.current_step
        frac = min(max(state.done / state.total, 0), 1)
        fill = round(frac * BAR_WIDTH)
        if fill:
            bar = "█" * (fill - 1) + "▍" if fill < BAR_WIDTH else "█" * BAR_WIDTH
            bar += "░" * (BAR_WIDTH - fill)
        else:
            bar = "░" * BAR_WIDTH
        eta = self._eta(state)
        eta_text = f" ETA {int(eta)}s" if eta else ""
        est_text = "~" if state.est else ""
        unit_text = f" {state.unit}" if state.unit else ""
        return (f"{state.current_step}  {bar} {frac * 100:4.0f}% · {est_text}"
                f"{fmt(state.done)}/{fmt(state.total)}{unit_text}{eta_text}")

    def _frame(self, state: StageState) -> None:
        try:
            width = shutil.get_terminal_size((100, 24)).columns - 2
        except (OSError, ValueError):
            width = 98
        text = self._progress_text(state)
        if len(text) > width:
            text += "…"
        frame = f"  {text}"
        if len(frame) < self._last_frame_len:
            frame = frame + " " * (self._last_frame_len - len(frame))
        self._clear_frame()
        self._raw("\r" + frame)
        self._last_frame_len = len(frame)

    def _clear_frame(self) -> None:
        if self._last_frame_len:
            self._raw("\r" + " " * self._last_frame_len + "\r")
            self._last_frame_len = 0

    def _line(self, text: str) -> None:
        self._clear_frame()
        self._raw(text + "\n")

    def _write(self, event: dict[str, Any]) -> None:
        self._raw(json.dumps(event) + "\n")

    def _raw(self, text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (OSError, ValueError):  # a pipe vanished: keep building, never crash progress
            pass


def fmt(number: float | None) -> str:
    return f"{int(number):,}" if number is not None else "?"


def clock() -> str:
    return time.strftime("%H:%M:%S")
