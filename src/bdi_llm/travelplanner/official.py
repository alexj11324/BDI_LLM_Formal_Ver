from __future__ import annotations

import ast
import importlib
import os
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datasets import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRAVELPLANNER_HOME = PROJECT_ROOT / "workspaces" / "TravelPlanner_official"


@dataclass
class TravelPlannerEvalResult:
    delivery: bool
    commonsense_pass: bool
    hard_constraint_pass: bool
    final_pass: bool
    commonsense_details: dict[str, tuple[bool | None, str | None]] | None
    hard_constraint_details: dict[str, tuple[bool | None, str | None]] | None

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "delivery": self.delivery,
            "commonsense_pass": self.commonsense_pass,
            "hard_constraint_pass": self.hard_constraint_pass,
            "final_pass": self.final_pass,
            "commonsense_details": self.commonsense_details,
            "hard_constraint_details": self.hard_constraint_details,
        }


class TravelPlannerSetupError(RuntimeError):
    pass


def _normalize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(sample)
    if isinstance(normalized.get("local_constraint"), str):
        normalized["local_constraint"] = ast.literal_eval(normalized["local_constraint"])
    return normalized


def resolve_travelplanner_home(explicit_home: str | None = None) -> Path:
    raw = explicit_home or os.environ.get("TRAVELPLANNER_HOME") or str(DEFAULT_TRAVELPLANNER_HOME)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    home = candidate.resolve()
    if not home.exists():
        raise TravelPlannerSetupError(
            f"TravelPlanner official repo not found at {home}. "
            "Clone OSU-NLP-Group/TravelPlanner there or set TRAVELPLANNER_HOME."
        )
    if not (home / "evaluation" / "eval.py").exists():
        raise TravelPlannerSetupError(
            f"{home} does not look like a TravelPlanner checkout (missing evaluation/eval.py)."
        )
    return home


def check_travelplanner_database(home: Path) -> None:
    required = [
        home / "database" / "background" / "citySet_with_states.txt",
        home / "database" / "flights" / "clean_Flights_2022.csv",
        home / "database" / "accommodations" / "clean_accommodations_2022.csv",
        home / "database" / "restaurants" / "clean_restaurant_2022.csv",
        home / "database" / "attractions" / "attractions.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise TravelPlannerSetupError(
            "TravelPlanner database is incomplete. Missing required files: " + ", ".join(missing)
        )


@contextmanager
def _official_import_context(home: Path):
    """Temporarily add TravelPlanner paths to sys.path for imports.

    NOTE: We intentionally do NOT os.chdir() here because chdir is
    process-global and causes race conditions under ThreadPoolExecutor.
    """
    added = []
    try:
        for path in [str(home), str(home / "evaluation")]:
            if path not in sys.path:
                sys.path.insert(0, path)
                added.append(path)
        yield
    finally:
        for path in added:
            if path in sys.path:
                sys.path.remove(path)


# Thread-safe evaluator cache to avoid repeated importlib + database loads
_evaluator_lock = threading.Lock()
_evaluator_cache: dict[str, tuple] = {}


def load_official_evaluator(home: Path):
    cache_key = str(home)
    cached = _evaluator_cache.get(cache_key)
    if cached is not None:
        return cached

    with _evaluator_lock:
        # Double-check after acquiring lock
        cached = _evaluator_cache.get(cache_key)
        if cached is not None:
            return cached

        check_travelplanner_database(home)
        with _official_import_context(home):
            commonsense_module = importlib.import_module("commonsense_constraint")
            hard_module = importlib.import_module("hard_constraint")
        result = (commonsense_module.evaluation, hard_module.evaluation)
        _evaluator_cache[cache_key] = result
        return result


def load_travelplanner_split(split: str):
    if split not in {"train", "validation", "test"}:
        raise ValueError(f"Unsupported TravelPlanner split: {split}")
    return [row for row in load_dataset("osunlp/TravelPlanner", split)[split]]


def evaluate_travelplanner_plan(
    sample: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    *,
    travelplanner_home: str | None = None,
) -> TravelPlannerEvalResult:
    home = resolve_travelplanner_home(travelplanner_home)
    commonsense_eval, hard_eval = load_official_evaluator(home)
    sample = _normalize_sample(sample)

    if not plan_rows:
        return TravelPlannerEvalResult(
            delivery=False,
            commonsense_pass=False,
            hard_constraint_pass=False,
            final_pass=False,
            commonsense_details=None,
            hard_constraint_details=None,
        )

    commonsense_details = commonsense_eval(sample, plan_rows)
    if not commonsense_details:
        return TravelPlannerEvalResult(
            delivery=True,
            commonsense_pass=False,
            hard_constraint_pass=False,
            final_pass=False,
            commonsense_details=None,
            hard_constraint_details=None,
        )

    commonsense_pass = all(result[0] is None or bool(result[0]) for result in commonsense_details.values())

    hard_constraint_details = None
    hard_constraint_pass = False
    if (
        commonsense_details.get("is_not_absent", (False, None))[0]
        and commonsense_details.get("is_valid_information_in_sandbox", (False, None))[0]
    ):
        hard_constraint_details = hard_eval(sample, plan_rows)
        hard_constraint_pass = all(result[0] is None or bool(result[0]) for result in hard_constraint_details.values())

    return TravelPlannerEvalResult(
        delivery=True,
        commonsense_pass=commonsense_pass,
        hard_constraint_pass=hard_constraint_pass,
        final_pass=commonsense_pass and hard_constraint_pass,
        commonsense_details=commonsense_details,
        hard_constraint_details=hard_constraint_details,
    )


def summarize_travelplanner_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    delivery = sum(1 for row in results if row["metrics"]["delivery"])
    commonsense = sum(1 for row in results if row["metrics"]["commonsense_pass"])
    hard = sum(1 for row in results if row["metrics"]["hard_constraint_pass"])
    final = sum(1 for row in results if row["metrics"]["final_pass"])
    return {
        "total_evaluated": total,
        "delivery_rate": delivery / total if total else 0.0,
        "commonsense_pass_rate": commonsense / total if total else 0.0,
        "hard_constraint_pass_rate": hard / total if total else 0.0,
        "final_pass_rate": final / total if total else 0.0,
        "success_count": final,
        "failed_count": total - final,
    }
