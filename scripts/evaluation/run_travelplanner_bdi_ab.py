#!/usr/bin/env python3
"""Run full-validation A/B for TravelPlanner BDI prompt variants."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.travelplanner.runner import TravelPlannerSetupError, print_run_result, run_split


def main() -> None:
    parser = argparse.ArgumentParser(description="TravelPlanner BDI prompt A/B runner")
    parser.add_argument("--split", choices=["validation"], default="validation")
    parser.add_argument("--variants", nargs="+", default=["legacy", "v3"])
    parser.add_argument("--max_instances", type=int, default=None)
    parser.add_argument("--output_dir", type=Path, default=Path("runs/travelplanner_ab"))
    parser.add_argument("--travelplanner_home", type=str, default=None)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    for variant in args.variants:
        os.environ["TRAVELPLANNER_BDI_PROMPT_VERSION"] = variant
        variant_dir = args.output_dir / variant
        print(f"\n=== Running variant={variant} on split={args.split} ===", flush=True)
        result = run_split(
            split=args.split,
            mode="bdi",
            max_instances=args.max_instances,
            output_dir=variant_dir,
            travelplanner_home=args.travelplanner_home,
            workers=args.workers,
        )
        print_run_result({"variant": variant, **result})


if __name__ == "__main__":
    try:
        main()
    except TravelPlannerSetupError as exc:
        raise SystemExit(str(exc))
