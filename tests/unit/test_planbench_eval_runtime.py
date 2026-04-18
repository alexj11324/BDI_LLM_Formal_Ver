"""Tests for deterministic runtime controls and manifest generation."""

from __future__ import annotations

from pathlib import Path

from src.bdi_llm.planbench_eval_runtime import (
    build_run_manifest,
    normalize_eval_runtime,
)


def test_normalize_eval_runtime_forces_serial_deterministic_mode():
    runtime = normalize_eval_runtime(
        deterministic=True,
        disable_repair_cache=False,
        disable_early_exit=False,
        parallel=True,
        max_workers=32,
    )

    assert runtime.parallel is False
    assert runtime.max_workers == 1
    assert runtime.disable_repair_cache is True
    assert runtime.disable_early_exit is True


def test_build_run_manifest_includes_stage_breakdown(tmp_path: Path):
    manifest = build_run_manifest(
        domain="logistics",
        execution_mode="bdi-repair",
        output_dir=str(tmp_path / "runs" / "logistics"),
        checkpoint_file=str(tmp_path / "runs" / "logistics" / "checkpoint_logistics_pipeline.json"),
        deterministic=True,
        disable_repair_cache=True,
        disable_early_exit=True,
        parallel=False,
        max_workers=1,
        results_summary={
            "baseline": {"attempted": 572, "success_count": 0, "success_rate": 0.0},
            "bdi": {"attempted": 572, "success_count": 557, "success_rate": 557 / 572},
            "bdi_repair": {"attempted": 572, "success_count": 572, "success_rate": 1.0},
            "val_repair": {"triggered": 15, "successful": 15, "total_attempts": 18},
        },
        extra_metadata={"server_manifest_path": str(tmp_path / "server_manifest.json")},
    )

    assert manifest["domain"] == "logistics"
    assert manifest["execution_mode"] == "bdi-repair"
    assert manifest["runtime"]["deterministic"] is True
    assert manifest["runtime"]["disable_repair_cache"] is True
    assert manifest["summary"]["baseline"]["success_count"] == 0
    assert manifest["summary"]["bdi"]["success_count"] == 557
    assert manifest["summary"]["bdi_repair"]["success_count"] == 572
    assert manifest["extra_metadata"]["server_manifest_path"] == str(
        tmp_path / "server_manifest.json"
    )
