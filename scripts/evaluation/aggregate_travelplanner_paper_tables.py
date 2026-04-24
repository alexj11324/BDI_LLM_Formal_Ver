#!/usr/bin/env python3
"""Aggregate TravelPlanner validation results into paper-ready tables (Table 3 format).

Reads per-mode result JSON files under:
    ${results_root}/validation/{baseline,bdi,bdi-repair}/results_travelplanner_validation_*.json

Writes to output_dir:
    tp_validation_table.tex
    tp_validation_table.json
    tp_aggregate_manifest.json

Reducer contract (v1):
    - Non-oracle section:
        baseline / bdi  -> use row["metrics"]          (no oracle repair triggered)
        bdi-repair      -> use row["non_oracle_metrics"] (pre-oracle version)
    - Oracle section:
        baseline / bdi  -> reuse non-oracle rows (identical; no oracle repair)
        bdi-repair      -> use row["metrics"]          (post-oracle version per runner.py:167)

    Pass rates are in [0,1] scale, 3 decimal places, NOT percentages.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional micro-stat helpers — imported lazily so missing dep doesn't crash
# ---------------------------------------------------------------------------
try:
    from scripts.evaluation.compute_travelplanner_metrics import (  # noqa: F401
        COMMONSENSE_KEYS,
        HARD_KEYS,
        OFFICIAL_DENOMINATORS,
    )

    _HAS_METRICS_MODULE = True
except ImportError:
    COMMONSENSE_KEYS = [
        "is_valid_information_in_current_city",
        "is_valid_information_in_sandbox",
        "is_reasonable_visiting_city",
        "is_valid_restaurants",
        "is_valid_transportation",
        "is_valid_attractions",
        "is_valid_accommodation",
        "is_not_absent",
    ]
    HARD_KEYS = [
        "valid_cost",
        "valid_room_rule",
        "valid_cuisine",
        "valid_room_type",
        "valid_transportation",
    ]
    OFFICIAL_DENOMINATORS = {  # type: ignore[assignment]
        "validation": {"commonsense": 1440, "hard": 420, "samples": 180},
        "test": {"commonsense": 8000, "hard": 2290, "samples": 1000},
    }
    _HAS_METRICS_MODULE = False

MODES = ("baseline", "bdi", "bdi-repair")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _locate_latest_results(results_root: Path, mode: str) -> Path:
    """Return the most-recently-modified results JSON for the given mode."""
    mode_dir = results_root / "validation" / mode
    candidates = list(mode_dir.glob("results_travelplanner_validation_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No results file found for mode='{mode}' under {mode_dir}. "
            "Expected files matching 'results_travelplanner_validation_*.json'."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Reducer (v1)
# ---------------------------------------------------------------------------


def _reduce_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute macro pass rates from a list of per-instance metric dicts.

    Args:
        rows: Each element is a metrics dict with boolean fields
              ``delivery``, ``commonsense_pass``, ``hard_constraint_pass``, ``final_pass``.

    Returns:
        Dict with keys:
            commonsense_pass_rate, hard_constraint_pass_rate, final_pass_rate,
            delivery_rate, N
    """
    n = len(rows)
    if n == 0:
        return {
            "commonsense_pass_rate": 0.0,
            "hard_constraint_pass_rate": 0.0,
            "final_pass_rate": 0.0,
            "delivery_rate": 0.0,
            "N": 0,
        }

    commonsense_pass_rate = sum(bool(r.get("commonsense_pass", False)) for r in rows) / n
    hard_constraint_pass_rate = sum(bool(r.get("hard_constraint_pass", False)) for r in rows) / n
    final_pass_rate = sum(bool(r.get("final_pass", False)) for r in rows) / n
    delivery_rate = sum(bool(r.get("delivery", False)) for r in rows) / n

    return {
        "commonsense_pass_rate": commonsense_pass_rate,
        "hard_constraint_pass_rate": hard_constraint_pass_rate,
        "final_pass_rate": final_pass_rate,
        "delivery_rate": delivery_rate,
        "N": n,
    }


def _compute_micro_stats(result_rows: list[dict[str, Any]], metrics_key: str) -> dict[str, Any]:
    """Compute micro (per-constraint) stats as auxiliary JSON-only fields.

    Uses commonsense_details / hard_constraint_details if present in the
    metrics dict. Falls back to empty dict if the compute module is unavailable.
    """
    if not _HAS_METRICS_MODULE:
        return {}

    cs_pass = cs_total = hd_pass = hd_total = 0
    for row in result_rows:
        m = row.get(metrics_key, {})
        cd = m.get("commonsense_details") or {}
        for key in COMMONSENSE_KEYS:
            if key in cd:
                val = cd[key]
                passed = val[0] if isinstance(val, (list, tuple)) else val
                if passed is None:
                    continue
                cs_total += 1
                if passed:
                    cs_pass += 1
            else:
                cs_total += 1

        hd = m.get("hard_constraint_details") or {}
        for key in HARD_KEYS:
            if key in hd:
                val = hd[key]
                passed = val[0] if isinstance(val, (list, tuple)) else val
                if passed is None:
                    continue
                hd_total += 1
                if passed:
                    hd_pass += 1

    denom = OFFICIAL_DENOMINATORS.get("validation", {})
    cs_official = denom.get("commonsense") or cs_total or 1
    hd_official = denom.get("hard") or hd_total or 1

    return {
        "commonsense_micro": cs_pass / cs_official if cs_official else 0.0,
        "hard_constraint_micro": hd_pass / hd_official if hd_official else 0.0,
        "_cs_pass": cs_pass,
        "_cs_total": cs_total,
        "_cs_official_denom": cs_official,
        "_hd_pass": hd_pass,
        "_hd_total": hd_total,
        "_hd_official_denom": hd_official,
    }


def _build_mode_stats(
    result_rows: list[dict[str, Any]],
    metrics_key: str,
) -> dict[str, Any]:
    """Extract metric dicts from result rows using the given key, then reduce."""
    metric_dicts = [row.get(metrics_key, {}) for row in result_rows]
    stats = _reduce_rows(metric_dicts)
    stats["micro"] = _compute_micro_stats(result_rows, metrics_key)
    return stats


def _assert_expected_samples(all_rows: dict[str, list[dict[str, Any]]]) -> None:
    """Fail fast if any mode is missing rows or the count deviates from the official validation N."""
    expected = OFFICIAL_DENOMINATORS.get("validation", {}).get("samples")
    if expected is None:
        return

    for mode, rows in all_rows.items():
        if len(rows) != expected:
            raise ValueError(
                f"Expected {expected} rows for mode='{mode}' but found {len(rows)}. "
                "Validation aggregation requires a complete run (180 samples per mode)."
            )


# ---------------------------------------------------------------------------
# LaTeX rendering
# ---------------------------------------------------------------------------


def _fmt(value: float) -> str:
    """Format a [0,1] pass rate to 3 decimal places."""
    return f"{value:.3f}"


def _render_latex(
    non_oracle: dict[str, dict[str, Any]],
    oracle: dict[str, dict[str, Any]],
    sample_count: int,
) -> str:
    """Render the two-section Table 3 LaTeX fragment."""

    def _fmt_boldmax(values: list[float], value: float) -> str:
        max_v = max(values)
        return f"\\textbf{{{_fmt(value)}}}" if value == max_v else _fmt(value)

    b_no = non_oracle["baseline"]
    d_no = non_oracle["bdi"]
    r_no = non_oracle["bdi-repair"]

    b_or = oracle["baseline"]
    d_or = oracle["bdi"]
    r_or = oracle["bdi-repair"]

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{TravelPlanner validation results ($N{{=}}{sample_count}$). "
        r"Non-oracle path is deployment-aligned; oracle path provides a diagnostic ceiling.}",
        r"\label{tab:tp_val}",
        r"\begin{tabular}{@{}lccc@{}}",
        r"\toprule",
        r"\multicolumn{4}{@{}l}{\textit{Non-oracle (deployment-aligned)}} \\",
        r"\midrule",
        r"Metric & Baseline & BDI & BDI-Repair \\",
        r"\midrule",
        f"Commonsense Pass & "
        f"{_fmt_boldmax([b_no['commonsense_pass_rate'], d_no['commonsense_pass_rate'], r_no['commonsense_pass_rate']], b_no['commonsense_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['commonsense_pass_rate'], d_no['commonsense_pass_rate'], r_no['commonsense_pass_rate']], d_no['commonsense_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['commonsense_pass_rate'], d_no['commonsense_pass_rate'], r_no['commonsense_pass_rate']], r_no['commonsense_pass_rate'])} \\\\",
        f"Hard Constr.\\ Pass & "
        f"{_fmt_boldmax([b_no['hard_constraint_pass_rate'], d_no['hard_constraint_pass_rate'], r_no['hard_constraint_pass_rate']], b_no['hard_constraint_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['hard_constraint_pass_rate'], d_no['hard_constraint_pass_rate'], r_no['hard_constraint_pass_rate']], d_no['hard_constraint_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['hard_constraint_pass_rate'], d_no['hard_constraint_pass_rate'], r_no['hard_constraint_pass_rate']], r_no['hard_constraint_pass_rate'])} \\\\",
        f"Final Pass Rate & "
        f"{_fmt_boldmax([b_no['final_pass_rate'], d_no['final_pass_rate'], r_no['final_pass_rate']], b_no['final_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['final_pass_rate'], d_no['final_pass_rate'], r_no['final_pass_rate']], d_no['final_pass_rate'])} & "
        f"{_fmt_boldmax([b_no['final_pass_rate'], d_no['final_pass_rate'], r_no['final_pass_rate']], r_no['final_pass_rate'])} \\\\",
        r"\midrule",
        r"\multicolumn{4}{@{}l}{\textit{Oracle (diagnostic upper bound)}} \\",
        r"\midrule",
        r"Metric & Baseline & BDI & BDI-Repair \\",
        r"\midrule",
        f"Commonsense Pass & "
        f"{_fmt_boldmax([b_or['commonsense_pass_rate'], d_or['commonsense_pass_rate'], r_or['commonsense_pass_rate']], b_or['commonsense_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['commonsense_pass_rate'], d_or['commonsense_pass_rate'], r_or['commonsense_pass_rate']], d_or['commonsense_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['commonsense_pass_rate'], d_or['commonsense_pass_rate'], r_or['commonsense_pass_rate']], r_or['commonsense_pass_rate'])} \\\\",
        f"Hard Constr.\\ Pass & "
        f"{_fmt_boldmax([b_or['hard_constraint_pass_rate'], d_or['hard_constraint_pass_rate'], r_or['hard_constraint_pass_rate']], b_or['hard_constraint_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['hard_constraint_pass_rate'], d_or['hard_constraint_pass_rate'], r_or['hard_constraint_pass_rate']], d_or['hard_constraint_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['hard_constraint_pass_rate'], d_or['hard_constraint_pass_rate'], r_or['hard_constraint_pass_rate']], r_or['hard_constraint_pass_rate'])} \\\\",
        f"Final Pass Rate & "
        f"{_fmt_boldmax([b_or['final_pass_rate'], d_or['final_pass_rate'], r_or['final_pass_rate']], b_or['final_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['final_pass_rate'], d_or['final_pass_rate'], r_or['final_pass_rate']], d_or['final_pass_rate'])} & "
        f"{_fmt_boldmax([b_or['final_pass_rate'], d_or['final_pass_rate'], r_or['final_pass_rate']], r_or['final_pass_rate'])} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main aggregation logic
# ---------------------------------------------------------------------------


def aggregate(results_root: Path, output_dir: Path, run_tag: str | None) -> None:
    """Discover result files, compute stats, and write all three output files."""
    # 1. Discover and load
    output_dir.mkdir(parents=True, exist_ok=True)

    input_meta: list[dict[str, Any]] = []
    all_rows: dict[str, list[dict[str, Any]]] = {}

    for mode in MODES:
        path = _locate_latest_results(results_root, mode)
        payload = json.loads(path.read_text())
        result_rows = payload.get("results", [])
        all_rows[mode] = result_rows
        input_meta.append(
            {
                "mode": mode,
                "path": str(path),
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
        print(f"[{mode}] Loaded {len(result_rows)} rows from {path.name}")

    _assert_expected_samples(all_rows)
    sample_count = len(next(iter(all_rows.values()))) if all_rows else 0

    # 2. Compute per-section stats
    #    Non-oracle: baseline/bdi use "metrics"; bdi-repair uses "non_oracle_metrics"
    #    Oracle:     baseline/bdi reuse "metrics"; bdi-repair uses "metrics" (post-oracle)
    non_oracle: dict[str, dict[str, Any]] = {
        "baseline": _build_mode_stats(all_rows["baseline"], "metrics"),
        "bdi": _build_mode_stats(all_rows["bdi"], "metrics"),
        "bdi-repair": _build_mode_stats(all_rows["bdi-repair"], "non_oracle_metrics"),
    }
    oracle: dict[str, dict[str, Any]] = {
        "baseline": _build_mode_stats(all_rows["baseline"], "metrics"),
        "bdi": _build_mode_stats(all_rows["bdi"], "metrics"),
        "bdi-repair": _build_mode_stats(all_rows["bdi-repair"], "metrics"),
    }

    # 3. Render LaTeX
    latex_str = _render_latex(non_oracle, oracle, sample_count)

    # 4. Write outputs
    now_iso = datetime.now(timezone.utc).isoformat()

    table_json: dict[str, Any] = {
        "non_oracle": non_oracle,
        "oracle": oracle,
    }
    manifest: dict[str, Any] = {
        "run_tag": run_tag,
        "aggregation_timestamp": now_iso,
        "inputs": input_meta,
        "reducer_version": "v1",
        "sample_count": sample_count,
    }

    tex_path = output_dir / "tp_validation_table.tex"
    json_path = output_dir / "tp_validation_table.json"
    manifest_path = output_dir / "tp_aggregate_manifest.json"

    tex_path.write_text(latex_str, encoding="utf-8")
    json_path.write_text(json.dumps(table_json, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote LaTeX table to   {tex_path}")
    print(f"Wrote JSON table to    {json_path}")
    print(f"Wrote manifest to      {manifest_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate TravelPlanner validation results into paper-ready tables.")
    parser.add_argument(
        "--results_root",
        required=True,
        help=(
            "Parent directory of validation/{baseline,bdi,bdi-repair}/ subdirs "
            "containing results_travelplanner_validation_*.json files."
        ),
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Directory to write tp_validation_table.tex / .json and tp_aggregate_manifest.json.",
    )
    parser.add_argument(
        "--run-tag",
        default=None,
        dest="run_tag",
        help="Optional label stored in the manifest for traceability.",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    aggregate(
        results_root=Path(args.results_root),
        output_dir=Path(args.output_dir),
        run_tag=args.run_tag,
    )


if __name__ == "__main__":
    main()
