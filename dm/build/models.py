# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Explicit inputs of one build; no argparse types leak in."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dm.tools.ncch import PartitionInfo

from dm.games import Profile

TOOLKIT_VERSION = "ctr-native 0.2.0"

#: display language codes the SMDH titles may answer, with the table position.
LANGUAGE_REGION = {
    "ja": 0, "en": 1, "fr": 2, "de": 3, "it": 4, "es": 5,
    "zh-Hans": 6, "ko": 7, "nl": 8, "pt": 9, "ru": 10, "zh-Hant": 11,
}

#: bumped whenever the on-disk AOT cache layout changes meaning.
AOT_CACHE_FORMAT = "aot-cache-v1"


@dataclass(frozen=True)
class BuildRequest:
    """Everything one run decides; identity and options, explicitly."""
    game: Path
    output: Path | None = None
    app_name: str | None = None
    language: str = "en"
    scale: int = 3
    no_icon: bool = False
    allow_damaged: bool = False
    no_verify: bool = False
    boot9: Path | None = None
    keys: Path | None = None
    zakuro_bin: Path | None = None
    recompiler_bin: Path | None = None
    rebuild_aot: bool = False
    launch: bool = False
    toolkit_version: str = TOOLKIT_VERSION
    root: Path = field(default_factory=lambda: Path.cwd())


@dataclass(frozen=True)
class PreparedGame:
    """Identity, original ROM, prepared ROM, hashes, profile and metadata."""
    source: Path
    title_id: str
    product_code: str
    version: int
    media_units: int
    partition_flags: int
    partition: PartitionInfo
    profile: Profile
    build_dir: Path
    working_source: Path
    prepared: bool  # True when a decryption pass produced the working copy


@dataclass(frozen=True)
class AotArtifact:
    """The library the app runs, its fingerprint and provenance."""
    title_id: str
    dylib: Path          # the installed place the packer reads
    hints_path: Path | None
    fingerprint: str
    reused: bool
    compiled: bool = False

    @property
    def provenance(self) -> dict:
        return {"title_id": self.title_id, "fingerprint": self.fingerprint,
                "reused": self.reused, "compiled": self.compiled,
                "dylib": str(self.dylib)}


@dataclass(frozen=True)
class SmokeResult:
    """What the headless verification says; paths arrive as data."""
    passed: bool
    opened: bool
    note: str


@dataclass(frozen=True)
class BuildResult:
    """Identity, the published app, and how reuse and validation went."""
    title_id: str
    app: Path
    sandbox_home: Path
    rom: Path
    reused_package: bool
    aot: AotArtifact
    smoke: SmokeResult | None


class BuildError(Exception):
    """A failed stage and its useful message, without any key material."""
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message
