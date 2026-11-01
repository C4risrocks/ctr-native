# Copyright (c) 2026 ctr-native contributors — MIT license.
"""The common pipeline module: one entry point for every title.

    from dm.build import BuildRequest, build

    result = build(request, progress=progress, runner=my_runner)  # doctest: SKIP
"""
from dm.build.models import (  # noqa: F401
    AOT_CACHE_FORMAT,
    AotArtifact,
    BuildError,
    BuildRequest,
    BuildResult,
    PreparedGame,
    SmokeResult,
)
from dm.build.pipeline import build  # noqa: F401
