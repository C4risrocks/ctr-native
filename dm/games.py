# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Load a game profile from dm/games/<title id>: per-game notes and a MD5 pin.

Like nxnative's `dm/games`, the folder is the extension point: adding a game
adds a folder (a profile.tsv and a README.md of notes), not script changes.
The only value the pipeline consumes is `verified_md5` — the host's own
settings live in the sandbox's `settings.toml`, the app's per-game start of
truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GAMES_DIR = Path(__file__).resolve().parent / "games"
PROFILE_FILE = "profile.tsv"


@dataclass
class Profile:
    """Per-game facts the pipeline reads: the MD5 pin and the bring-up notes."""

    title_id: str
    verified_md5: str = ""
    notes_path: Path | None = None


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
            raise ValueError(f"{table}:{line_number}: only `verified_md5=` is read; the rest is notes")
    return profile


def game_notes(title_id: str, games_dir: Path | None = None) -> str | None:
    notes = (games_dir or GAMES_DIR) / title_id / "README.md"
    return notes.read_text() if notes.exists() else None
