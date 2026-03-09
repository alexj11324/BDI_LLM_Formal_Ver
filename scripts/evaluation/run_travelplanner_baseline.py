#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.travelplanner.runner import TravelPlannerSetupError, print_run_result, run_split


def main() -> None:
    parser = argparse.ArgumentParser(description='TravelPlanner baseline runner')
    parser.add_argument('--split', choices=['train', 'validation', 'test'], default='validation')
    parser.add_argument('--max_instances', type=int, default=None)
    parser.add_argument('--output_dir', type=Path, default=Path('runs/travelplanner'))
    parser.add_argument('--travelplanner_home', type=str, default=None)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    result = run_split(split=args.split, mode='baseline', max_instances=args.max_instances, output_dir=args.output_dir, travelplanner_home=args.travelplanner_home, workers=args.workers)
    print_run_result(result)


if __name__ == '__main__':
    import traceback
    try:
        main()
    except TravelPlannerSetupError as exc:
        raise SystemExit(str(exc))
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
