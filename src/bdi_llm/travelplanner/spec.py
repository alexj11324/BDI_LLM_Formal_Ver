from __future__ import annotations

from pathlib import Path

_SPEC_PATH = Path(__file__).with_name('spec.md')


def load_travelplanner_spec() -> str:
    return _SPEC_PATH.read_text().strip()
