"""Runtime helpers for PlanBench evaluation jobs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalRuntimeConfig:
    """Normalized runtime settings for one PlanBench evaluation run."""

    deterministic: bool
    disable_repair_cache: bool
    disable_early_exit: bool
    parallel: bool
    max_workers: int


def normalize_eval_runtime(
    *,
    deterministic: bool,
    disable_repair_cache: bool,
    disable_early_exit: bool,
    parallel: bool,
    max_workers: int,
) -> EvalRuntimeConfig:
    """Normalize runtime flags for one evaluation run."""
    max_workers = max(int(max_workers), 1)

    if deterministic:
        return EvalRuntimeConfig(
            deterministic=True,
            disable_repair_cache=True,
            disable_early_exit=True,
            parallel=False,
            max_workers=1,
        )

    normalized_parallel = bool(parallel and max_workers > 1)
    return EvalRuntimeConfig(
        deterministic=False,
        disable_repair_cache=bool(disable_repair_cache),
        disable_early_exit=bool(disable_early_exit),
        parallel=normalized_parallel,
        max_workers=max_workers,
    )


def build_run_manifest(
    *,
    domain: str,
    execution_mode: str,
    output_dir: str,
    checkpoint_file: str,
    deterministic: bool,
    disable_repair_cache: bool,
    disable_early_exit: bool,
    parallel: bool,
    max_workers: int,
    results_summary: dict[str, Any],
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a provenance manifest for one domain run."""
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "execution_mode": execution_mode,
        "output_dir": output_dir,
        "checkpoint_file": checkpoint_file,
        "runtime": asdict(
            normalize_eval_runtime(
                deterministic=deterministic,
                disable_repair_cache=disable_repair_cache,
                disable_early_exit=disable_early_exit,
                parallel=parallel,
                max_workers=max_workers,
            )
        ),
        "summary": results_summary,
    }
    if extra_metadata:
        manifest["extra_metadata"] = extra_metadata
    return manifest


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    """Persist a JSON payload atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n")
        tmp_path.replace(target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
