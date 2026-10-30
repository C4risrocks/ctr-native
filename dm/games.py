# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Load a game profile from dm/games/<title id>: per-game notes and settings.

Like nxnative's `dm/games`, the folder is the extension point: adding a game
adds a folder (a profile.tsv of defaults and a README.md of notes), not script
changes. Every table value ends up in the generated Azahar configuration, and
only additions the product knows get written — unknown keys are refused with a
message rather than silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

GAMES_DIR = Path(__file__).resolve().parent / "games"
PROFILE_FILE = "profile.tsv"

# Configuration keys a profile may set (the generated qt-config.ini sections).
# Anything outside this table means a new Azahar setting that needs review
# first, not a silent guess.
KNOWN_KEYS = frozenset({
    "Renderer.resolution_factor",
    "Renderer.frame_limit",
    "Renderer.shaders_accurate_mul",
    "Renderer.texture_filter",
    "Renderer.texture_sampling",
    "Renderer.use_vsync",
    "Renderer.use_hw_shader",
    "Renderer.use_shader_jit",
    "Renderer.use_disk_shader_cache",
    "Renderer.async_shader_compilation",
    "Renderer.async_presentation",
    "Renderer.use_integer_scaling",
    "Core.cpu_clock_percentage",
    "Core.use_cpu_jit",
    "System.region_value",
    "System.is_new_3ds",
    "Layout.layout_option",
    "Layout.filter_mode",
    "Layout.small_screen_position",
    "Layout.swap_screen",
    "Layout.upright_screen",
    "UI.fullscreen",
    "UI.hideInactiveMouse",
    "Audio.audio_emulation",
    "Audio.enable_audio_stretching",
    "Audio.volume",
})


@dataclass
class Profile:
    """Per-game defaults; every key maps to a generated qt-config value."""

    title_id: str
    values: dict[str, str] = field(default_factory=dict)
    verified_md5: str = ""
    notes_path: Path | None = None

    def has_key(self, key: str) -> bool:
        return key in self.values


def load_profile(title_id: str, games_dir: Path | None = None) -> Profile:
    """Read dm/games/<title id>/profile.tsv; a game without one gets a provisional profile."""
    folder = (games_dir or GAMES_DIR) / title_id
    profile = Profile(title_id=title_id, notes_path=folder / "README.md")
    table = folder / PROFILE_FILE
    if table.exists():
        for line_number, raw in enumerate(table.read_text().splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("verified_md5="):
                profile.verified_md5 = line.split("=", 1)[1].strip().lower()
                continue
            if "=" not in line:
                raise ValueError(f"{table}:{line_number}: not KEY=VALUE")
            key, value = (part.strip() for part in line.split("=", 1))
            if key not in KNOWN_KEYS:
                raise ValueError(f"{table}:{line_number}: unknown settings key {key!r}")
            profile.values[key] = value
    return profile


def game_notes(title_id: str, games_dir: Path | None = None) -> str | None:
    notes = (games_dir or GAMES_DIR) / title_id / "README.md"
    return notes.read_text() if notes.exists() else None
