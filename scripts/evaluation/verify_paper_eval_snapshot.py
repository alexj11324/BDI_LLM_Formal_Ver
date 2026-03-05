#!/usr/bin/env python3
"""Verify frozen paper evaluation snapshot integrity and metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


EXPECTED_FILES = [
    "results_blocksworld_20260212_214230.json",
    "results_logistics_20260213_025757.json",
    "results_depots_20260213_014014.json",
    "checkpoint_blocksworld.json",
    "checkpoint_logistics.json",
    "checkpoint_depots.json",
]

EXPECTED_COUNTS = {
    "blocksworld": (200, 200, [""], 0),  # (passed, total, failed_ids_placeholder, failed_count)
    "logistics": (568, 570, ["instance-166.pddl", "instance-228.pddl"], 2),
    "depots": (497, 500, ["instance-173.pddl", "instance-179.pddl", "instance-187.pddl"], 3),
}

EXPECTED_OVERALL = (1265, 1270, 5, "1265/1270 = 99.6%")

EXPECTED_RELATION = {
    "logistics_delta": {"instance-259.pddl": 1, "instance-264.pddl": 1},
    "depots_extra": ["instance-183.pddl"],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def instance_id(row: dict) -> str:
    p = row.get("instance_file") or row.get("instance_name") or ""
    return p.split("/")[-1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def stats_for(path: Path) -> dict:
    data = load_json(path)
    rows = data.get("results", [])
    passed = [r for r in rows if r.get("success") is True]
    failed = [r for r in rows if r.get("success") is not True]
    return {
        "rows": len(rows),
        "passed": len(passed),
        "failed": len(failed),
        "failed_ids": [instance_id(r) for r in failed],
        "counts": Counter(instance_id(r) for r in rows),
    }


def require(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify paper_eval_20260213 snapshot")
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "artifacts" / "paper_eval_20260213",
        help="Path to snapshot directory",
    )
    args = parser.parse_args()

    base = args.snapshot_dir
    manifest_path = base / "MANIFEST.json"
    failures: list[str] = []

    require(base.exists(), f"Snapshot dir missing: {base}", failures)
    require(manifest_path.exists(), f"MANIFEST missing: {manifest_path}", failures)
    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    manifest = load_json(manifest_path)

    # 1) File existence
    for name in EXPECTED_FILES:
        p = base / name
        require(p.exists(), f"Missing expected file: {p}", failures)

    # 2) Hash checks
    for name in EXPECTED_FILES:
        p = base / name
        if not p.exists():
            continue
        expected_hash = manifest.get("files", {}).get(name, {}).get("sha256")
        actual_hash = sha256(p)
        require(expected_hash is not None, f"MANIFEST missing sha256 for {name}", failures)
        require(actual_hash == expected_hash, f"sha256 mismatch for {name}", failures)

    # 3) Recompute checkpoint primary counts
    ckb = stats_for(base / "checkpoint_blocksworld.json") if (base / "checkpoint_blocksworld.json").exists() else None
    ckl = stats_for(base / "checkpoint_logistics.json") if (base / "checkpoint_logistics.json").exists() else None
    ckd = stats_for(base / "checkpoint_depots.json") if (base / "checkpoint_depots.json").exists() else None

    if ckb and ckl and ckd:
        # blocksworld
        require(ckb["passed"] == EXPECTED_COUNTS["blocksworld"][0], "Blocksworld passed mismatch", failures)
        require(ckb["rows"] == EXPECTED_COUNTS["blocksworld"][1], "Blocksworld total mismatch", failures)
        require(ckb["failed"] == EXPECTED_COUNTS["blocksworld"][3], "Blocksworld failed count mismatch", failures)

        # logistics
        require(ckl["passed"] == EXPECTED_COUNTS["logistics"][0], "Logistics passed mismatch", failures)
        require(ckl["rows"] == EXPECTED_COUNTS["logistics"][1], "Logistics total mismatch", failures)
        require(ckl["failed"] == EXPECTED_COUNTS["logistics"][3], "Logistics failed count mismatch", failures)
        require(sorted(ckl["failed_ids"]) == sorted(EXPECTED_COUNTS["logistics"][2]), "Logistics failed IDs mismatch", failures)

        # depots
        require(ckd["passed"] == EXPECTED_COUNTS["depots"][0], "Depots passed mismatch", failures)
        require(ckd["rows"] == EXPECTED_COUNTS["depots"][1], "Depots total mismatch", failures)
        require(ckd["failed"] == EXPECTED_COUNTS["depots"][3], "Depots failed count mismatch", failures)
        require(sorted(ckd["failed_ids"]) == sorted(EXPECTED_COUNTS["depots"][2]), "Depots failed IDs mismatch", failures)

        overall_passed = ckb["passed"] + ckl["passed"] + ckd["passed"]
        overall_total = ckb["rows"] + ckl["rows"] + ckd["rows"]
        overall_failed = ckb["failed"] + ckl["failed"] + ckd["failed"]
        overall_formatted = f"{overall_passed}/{overall_total} = {overall_passed / overall_total * 100:.1f}%"

        require(overall_passed == EXPECTED_OVERALL[0], "Overall passed mismatch", failures)
        require(overall_total == EXPECTED_OVERALL[1], "Overall total mismatch", failures)
        require(overall_failed == EXPECTED_OVERALL[2], "Overall failed mismatch", failures)
        require(overall_formatted == EXPECTED_OVERALL[3], "Overall formatted mismatch", failures)

    # 4) Validate upstream relationship
    rl = stats_for(base / "results_logistics_20260213_025757.json") if (base / "results_logistics_20260213_025757.json").exists() else None
    rd = stats_for(base / "results_depots_20260213_014014.json") if (base / "results_depots_20260213_014014.json").exists() else None
    if rl and ckl:
        all_ids = set(rl["counts"]) | set(ckl["counts"])
        delta = {k: rl["counts"].get(k, 0) - ckl["counts"].get(k, 0) for k in sorted(all_ids) if rl["counts"].get(k, 0) != ckl["counts"].get(k, 0)}
        require(delta == EXPECTED_RELATION["logistics_delta"], f"Logistics delta mismatch: {delta}", failures)

    if rd and ckd:
        extra = sorted(set(rd["counts"]) - set(ckd["counts"]))
        require(extra == EXPECTED_RELATION["depots_extra"], f"Depots extra-instance mismatch: {extra}", failures)

    # 5) Compare with MANIFEST claims for primary counts
    mp = manifest.get("paper_primary_counts", {})
    require(mp.get("overall", {}).get("formatted") == EXPECTED_OVERALL[3], "MANIFEST overall formatted mismatch", failures)
    require(mp.get("logistics", {}).get("failed_instances") == EXPECTED_COUNTS["logistics"][2], "MANIFEST logistics failed IDs mismatch", failures)
    require(mp.get("depots", {}).get("failed_instances") == EXPECTED_COUNTS["depots"][2], "MANIFEST depots failed IDs mismatch", failures)

    if failures:
        print("Verification FAILED:")
        for f in failures:
            print(f" - {f}")
        return 1

    print("Verification PASSED")
    print(f"Snapshot: {base}")
    print(f"Overall: {EXPECTED_OVERALL[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
