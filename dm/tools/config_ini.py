# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Write the two Qt configuration files a per-game app needs, from one template.

The template holds the defaults we ship (fast, modern, quiet on macOS:
Vulkan through MoltenVK, async shader compilation, no Discord presence, no
update prompts); a profile's KEY=VALUE table overlays exactly the keys it
names, and the INI parser of Azahar reads the result. `\\default` bookkeeping
keys are set consistently so the "use the default?" marks never lie.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "qt-config.ini"


def render_template(profile_values: dict[str, str], overrides: dict[str, str] | None = None) -> str:
    """Template + profile + caller overrides -> the final qt-config.ini text."""
    ini = Template(TEMPLATE.read_text())
    merged = dict(profile_values)
    merged.update(overrides or {})
    for key, value in merged.items():
        section, _, dot_key = key.partition(".")
        ini.set(section, dot_key, value)
    return ini.text()


class Template:
    """A two-level INI that keeps Qt's key\\default=false marks in step."""

    def __init__(self, text: str) -> None:
        self.sections: list[tuple[str, dict[str, str]]] = []
        current = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.startswith("[") and line.endswith("]"):
                current = {}
                self.sections.append((line[1:-1].strip(), current))
            elif line and current is not None:
                key, _, value = line.partition("=")
                current[key] = value
        if not self.sections:
            raise ValueError("empty configuration template")

    def set(self, section: str, key: str, value: str) -> None:
        mapping = next((data for name, data in self.sections if name == section), None)
        if mapping is None:
            self.sections.append((section, {}))
            mapping = self.sections[-1][1]
        # An explicit value is a chosen value: the paired "default?" mark the UI
        # writes always goes to false, whatever the value (4, true, "Auto").
        mapping[key] = value
        mapping[f"{key}\\default"] = "false"

    @staticmethod
    def _is_default_key(value: str) -> bool:
        return value in {"true", "false", "0", "1"} and value != ""

    def text(self) -> str:
        chunks = []
        for name, data in self.sections:
            chunks.append(f"[{name}]")
            for key, value in data.items():
                chunks.append(f"{key}={value}")
            chunks.append("")
        return "\n".join(chunks).rstrip("\n") + "\n"
