from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SPEC_PATH = Path(__file__).with_name("spec.md")


@lru_cache(maxsize=1)
def load_travelplanner_spec() -> str:
    return _SPEC_PATH.read_text(encoding="utf-8").strip()
