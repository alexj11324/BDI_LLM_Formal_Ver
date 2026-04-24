#!/usr/bin/env python3
"""Report TravelPlanner validation generalization metrics and gap analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

PUBLIC_COVERABLE_CODES = {
    "is_valid_restaurants",
    "is_valid_transportation",
    "is_valid_accommodation",
    "is_reasonable_visiting_city",
    "is_not_absent",
}


def latest_result_file(root: Path, split: str, mode: str) -> Path:
    mode_dir = root / split / mode
    candidates = sorted(mode_dir.glob("results_travelplanner_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No result JSON found under {mode_dir}")
    return candidates[-1]


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text())


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _failed_codes(metric_dict: dict) -> tuple[list[str], list[str]]:
    commonsense = []
    hard = []
    for key, value in (metric_dict.get("commonsense_details") or {}).items():
        ok, _ = value
        if ok is False:
            commonsense.append(key)
    for key, value in (metric_dict.get("hard_constraint_details") or {}).items():
        ok, _ = value
        if ok is False:
            hard.append(key)
    return commonsense, hard


def _count_failed_codes(rows: list[dict], metric_field: str) -> tuple[Counter, Counter]:
    commonsense = Counter()
    hard = Counter()
    for row in rows:
        metrics = row.get(metric_field) or {}
        cs_codes, hd_codes = _failed_codes(metrics)
        for code in cs_codes:
            commonsense[code] += 1
        for code in hd_codes:
            hard[code] += 1
    return commonsense, hard


def _oracle_gap_stats(rows: list[dict]) -> dict:
    oracle_fixed = []
    oracle_regressed = []
    still_failing = []
    for row in rows:
        pre = bool((row.get("validation_as_test_metrics") or {}).get("final_pass", False))
        post = bool((row.get("metrics") or {}).get("final_pass", False))
        if not pre and post:
            oracle_fixed.append(row)
        if pre and not post:
            oracle_regressed.append(row)
        if not post:
            still_failing.append(row)

    fixed_cs, fixed_hd = _count_failed_codes(oracle_fixed, "validation_as_test_metrics")
    fail_cs, fail_hd = _count_failed_codes(still_failing, "metrics")

    coverable = 0
    mixed = 0
    combos = Counter()
    for row in oracle_fixed:
        fail_codes = set()
        cs_codes, hd_codes = _failed_codes(row.get("validation_as_test_metrics") or {})
        fail_codes.update(cs_codes)
        fail_codes.update(hd_codes)
        combos[tuple(sorted(fail_codes))] += 1
        if fail_codes and fail_codes.issubset(PUBLIC_COVERABLE_CODES):
            coverable += 1
        else:
            mixed += 1

    return {
        "oracle_fixed_count": len(oracle_fixed),
        "oracle_regressed_count": len(oracle_regressed),
        "still_failing_count": len(still_failing),
        "oracle_fixed_commonsense": dict(fixed_cs.most_common()),
        "oracle_fixed_hard": dict(fixed_hd.most_common()),
        "still_failing_commonsense": dict(fail_cs.most_common()),
        "still_failing_hard": dict(fail_hd.most_common()),
        "coverable_gap_summary": {
            "pure_public_rule_cases": coverable,
            "mixed_or_hard_cases": mixed,
        },
        "oracle_fixed_code_combos": {"top": [[list(k), v] for k, v in combos.most_common(15)]},
    }


def _failure_buckets(rows: list[dict], metric_field: str) -> dict[str, int]:
    buckets = Counter()
    for row in rows:
        metrics = row.get(metric_field) or {}
        codes = []
        cs_codes, hd_codes = _failed_codes(metrics)
        codes.extend(cs_codes)
        codes.extend(hd_codes)
        code_set = set(codes)
        if not code_set:
            continue
        if code_set == {"valid_cost"}:
            buckets["cost_only"] += 1
        elif code_set == {"valid_room_type"}:
            buckets["room_type_only"] += 1
        elif code_set == {"valid_room_rule"}:
            buckets["room_rule_only"] += 1
        elif code_set == {"valid_cuisine"}:
            buckets["cuisine_only"] += 1
        elif any(code in code_set for code in ("valid_cost", "valid_room_type", "valid_room_rule", "valid_cuisine")):
            buckets["mixed_hard_plus_other"] += 1
        else:
            buckets["commonsense_only"] += 1
    return dict(buckets)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report TravelPlanner validation generalization metrics")
    parser.add_argument("--results_dir", type=Path, required=True)
    parser.add_argument("--split", default="validation")
    parser.add_argument(
        "--compare-file",
        action="append",
        default=[],
        help="Optional extra row in the form label=/abs/or/rel/path/to/results.json",
    )
    args = parser.parse_args()

    payloads = {}
    for mode in ("baseline", "bdi", "bdi-repair"):
        try:
            payloads[mode] = load_payload(latest_result_file(args.results_dir, args.split, mode))
        except FileNotFoundError:
            continue
    for item in args.compare_file:
        if "=" not in item:
            raise SystemExit(f"Invalid --compare-file: {item}")
        label, raw_path = item.split("=", 1)
        payloads[label] = load_payload(Path(raw_path))

    if not payloads:
        raise SystemExit("No payloads found to report.")

    print(f"TravelPlanner {args.split} summary")
    print("=" * 116)
    print(
        f"{'Mode':<14} {'Official Final':>14} {'Validation-as-test':>20} {'Repair Trigger':>16} {'Avg Day Δ':>12} {'Avg Field Δ':>14}"
    )
    print("-" * 116)

    for mode, payload in payloads.items():
        summary = payload["summary"]
        if mode == "bdi-repair":
            vat = payload.get("validation_as_test_summary", summary)
            diag = payload.get("non_oracle_diagnostics_summary", {})
            trigger = _fmt_pct(diag.get("trigger_rate", 0.0))
            avg_days = f"{diag.get('avg_changed_days_when_triggered', 0.0):.2f}"
            avg_fields = f"{diag.get('avg_changed_fields_when_triggered', 0.0):.2f}"
        else:
            vat = summary
            trigger = "-"
            avg_days = "-"
            avg_fields = "-"

        print(
            f"{mode:<14} "
            f"{_fmt_pct(summary.get('final_pass_rate', 0.0)):>14} "
            f"{_fmt_pct(vat.get('final_pass_rate', 0.0)):>20} "
            f"{trigger:>16} {avg_days:>12} {avg_fields:>14}"
        )

    if "bdi" in payloads:
        bdi_rows = payloads["bdi"].get("results", [])
        bdi_cs, bdi_hd = _count_failed_codes([row for row in bdi_rows if not row.get("success")], "metrics")
        print("\nBdi validation failure histogram")
        print("-" * 116)
        print(
            json.dumps(
                {
                    "commonsense": dict(bdi_cs.most_common()),
                    "hard": dict(bdi_hd.most_common()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print("\nBdi validation failure buckets")
        print("-" * 116)
        print(
            json.dumps(
                _failure_buckets([row for row in bdi_rows if not row.get("success")], "metrics"),
                indent=2,
                ensure_ascii=False,
            )
        )

    if "bdi-repair" in payloads:
        gap_stats = _oracle_gap_stats(payloads["bdi-repair"].get("results", []))
        print("\nBdi-repair gap analysis")
        print("-" * 116)
        print(json.dumps(gap_stats, indent=2, ensure_ascii=False))

        repair_rows = payloads["bdi-repair"].get("results", [])
        print("\nBdi-repair validation-as-test failure buckets")
        print("-" * 116)
        print(
            json.dumps(
                _failure_buckets(
                    [row for row in repair_rows if not (row.get("validation_as_test_metrics") or {}).get("final_pass")],
                    "validation_as_test_metrics",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

        print("\nBdi-repair oracle failure buckets")
        print("-" * 116)
        print(
            json.dumps(
                _failure_buckets(
                    [row for row in repair_rows if not row.get("success")],
                    "metrics",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )

        print("\nDetailed bdi-repair diagnostics")
        print("-" * 116)
        repair_payload = payloads["bdi-repair"]
        print(
            json.dumps(
                {
                    "official_summary": repair_payload.get("summary", {}),
                    "validation_as_test_summary": repair_payload.get("validation_as_test_summary", {}),
                    "non_oracle_diagnostics_summary": repair_payload.get("non_oracle_diagnostics_summary", {}),
                    "oracle_diagnostics_summary": repair_payload.get("oracle_diagnostics_summary", {}),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
