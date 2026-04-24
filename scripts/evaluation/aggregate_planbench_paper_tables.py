#!/usr/bin/env python3
"""Aggregate PlanBench domain results into paper-ready tables."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bdi_llm.planbench_eval_runtime import write_json_atomic
from bdi_llm.planbench_reporting import (
    DOMAIN_ORDER,
    aggregate_planbench_results,
    render_latex_tables,
)


def _latest_result_file(results_root: Path, domain: str) -> Path:
    domain_dir = results_root / domain
    candidates = list(domain_dir.rglob("results_*_bdi-repair_*.json"))
    if not candidates:
        candidates = list(domain_dir.rglob("results_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No result JSON found for domain={domain} under {domain_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate PlanBench paper tables")
    parser.add_argument(
        "--results_root",
        required=True,
        help="Root directory containing per-domain PlanBench results",
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Directory where aggregated JSON and LaTeX tables should be written",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    results_root = Path(args.results_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, dict] = {}
    sources: dict[str, str] = {}
    for domain in DOMAIN_ORDER:
        path = _latest_result_file(results_root, domain)
        payloads[domain] = json.loads(path.read_text())
        sources[domain] = str(path)

    aggregate = aggregate_planbench_results(payloads)
    tables = render_latex_tables(aggregate)

    bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "aggregate": aggregate,
        "latex": tables,
    }
    write_json_atomic(output_dir / "pddl_results_glm47flash_table.json", bundle)
    write_json_atomic(output_dir / "aggregate_manifest.json", bundle)
    (output_dir / "pddl_results_glm47flash_table.tex").write_text(tables["main"])
    (output_dir / "pddl_appendix_glm47flash_table.tex").write_text(tables["appendix"])

    print(f"Wrote aggregate JSON to {output_dir / 'pddl_results_glm47flash_table.json'}")
    print(f"Wrote aggregate manifest to {output_dir / 'aggregate_manifest.json'}")
    print(f"Wrote main table to {output_dir / 'pddl_results_glm47flash_table.tex'}")
    print(f"Wrote appendix table to {output_dir / 'pddl_appendix_glm47flash_table.tex'}")


if __name__ == "__main__":
    main()
