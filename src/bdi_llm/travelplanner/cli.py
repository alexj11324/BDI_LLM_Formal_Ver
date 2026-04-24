from __future__ import annotations

import argparse
from pathlib import Path

from .runner import print_run_result, run_split


def build_split_runner_parser(
    description: str,
    *,
    include_execution_mode: bool = False,
    default_execution_mode: str = "bdi-repair",
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--split", choices=["train", "validation", "test"], default="validation")
    if include_execution_mode:
        parser.add_argument(
            "--execution_mode",
            choices=["baseline", "bdi", "bdi-repair"],
            default=default_execution_mode,
        )
    parser.add_argument("--max_instances", type=int, default=None)
    parser.add_argument("--output_dir", type=Path, default=Path("runs/travelplanner"))
    parser.add_argument("--travelplanner_home", type=str, default=None)
    parser.add_argument("--workers", type=int, default=1)
    return parser


def run_split_from_args(args: argparse.Namespace, *, fixed_mode: str | None = None) -> None:
    mode = fixed_mode or args.execution_mode
    result = run_split(
        split=args.split,
        mode=mode,
        max_instances=args.max_instances,
        output_dir=args.output_dir,
        travelplanner_home=args.travelplanner_home,
        workers=args.workers,
    )
    print_run_result(result)
