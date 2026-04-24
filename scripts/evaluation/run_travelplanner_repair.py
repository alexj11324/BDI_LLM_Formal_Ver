#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.travelplanner.cli import build_split_runner_parser, run_split_from_args
from src.bdi_llm.travelplanner.runner import TravelPlannerSetupError


def main() -> None:
    parser = build_split_runner_parser("TravelPlanner BDI-repair runner")
    args = parser.parse_args()
    run_split_from_args(args, fixed_mode="bdi-repair")


if __name__ == "__main__":
    try:
        main()
    except TravelPlannerSetupError as exc:
        raise SystemExit(str(exc))
