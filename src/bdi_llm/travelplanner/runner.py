from __future__ import annotations

import json
import os
import sys
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

# Optional MLflow tracking
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

from .adapter import TravelPlannerTaskAdapter
from .engine import TravelPlannerGenerator
from .official import (
    TravelPlannerSetupError,
    evaluate_travelplanner_plan,
    load_travelplanner_split,
    summarize_travelplanner_results,
)
from .serializer import TravelPlannerPlanSerializer


MAX_NON_ORACLE_REPAIR_PASSES = 2


EMPTY_METRICS = {
    'delivery': False,
    'commonsense_pass': False,
    'hard_constraint_pass': False,
    'final_pass': False,
}


def _empty_diagnostics() -> dict[str, Any]:
    return {
        'triggered': False,
        'passes_used': 0,
        'changed_days': 0,
        'changed_fields': 0,
        'issue_categories': {},
        'issues': [],
    }


def _failed_result(sample: dict[str, Any], idx: int, mode: str, error: Exception) -> dict[str, Any]:
    task_idx = int(sample.get('idx', idx + 1))
    return {
        'task_id': str(task_idx),
        'query': sample.get('query', ''),
        'mode': mode,
        'submission': {'idx': task_idx, 'query': sample.get('query', ''), 'plan': []},
        'metrics': dict(EMPTY_METRICS),
        'non_oracle_metrics': dict(EMPTY_METRICS),
        'validation_as_test_metrics': dict(EMPTY_METRICS),
        'non_oracle_diagnostics': _empty_diagnostics(),
        'oracle_repair_diagnostics': _empty_diagnostics(),
        'success': False,
        'itinerary': {},
        'error': str(error),
    }


def _summarize_metric_dicts(metric_dicts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [{'metrics': metrics} for metrics in metric_dicts]
    return summarize_travelplanner_results(rows)


def _summarize_diagnostics(results: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    triggered_rows = [row[field_name] for row in results if row.get(field_name, {}).get('triggered')]
    total = len(results)
    if not triggered_rows:
        return {
            'triggered_count': 0,
            'trigger_rate': 0.0,
            'avg_changed_days_when_triggered': 0.0,
            'avg_changed_fields_when_triggered': 0.0,
            'issue_categories': {},
        }

    category_counter: Counter[str] = Counter()
    for diag in triggered_rows:
        for code, count in (diag.get('issue_categories') or {}).items():
            category_counter[code] += int(count)

    return {
        'triggered_count': len(triggered_rows),
        'trigger_rate': len(triggered_rows) / total if total else 0.0,
        'avg_changed_days_when_triggered': (
            sum(diag.get('changed_days', 0) for diag in triggered_rows) / len(triggered_rows)
        ),
        'avg_changed_fields_when_triggered': (
            sum(diag.get('changed_fields', 0) for diag in triggered_rows) / len(triggered_rows)
        ),
        'issue_categories': dict(category_counter.most_common()),
    }


def build_evaluator_feedback(metrics: dict[str, Any]) -> str:
    parts: list[str] = []
    commonsense = metrics.get('commonsense_details') or {}
    hard = metrics.get('hard_constraint_details') or {}
    for group_name, group in [('Commonsense', commonsense), ('HardConstraint', hard)]:
        for key, value in group.items():
            ok, message = value
            if ok is None or ok:
                continue
            parts.append(f'[{group_name}] {key}: {message}')
    return '\n'.join(parts)


def generate_submission(sample: dict[str, Any], mode: str) -> dict[str, Any]:
    """Shared sole-planning inference path used by both validation and test submission.

    This keeps non-oracle generation and patch repair identical across splits.
    """
    adapter = TravelPlannerTaskAdapter()
    generator = TravelPlannerGenerator()
    serializer = TravelPlannerPlanSerializer()
    task = adapter.to_planning_task(sample)

    if mode == 'baseline':
        generated = generator.generate_baseline(task.beliefs, task.desire, task.domain_context or '')
        final_itinerary = generated.itinerary
        non_oracle_diagnostics = _empty_diagnostics()
    else:
        generated = generator.generate_bdi(task.beliefs, task.desire, task.domain_context or '')
        final_itinerary = generated.itinerary
        non_oracle_diagnostics = _empty_diagnostics()
        if mode == 'bdi-repair':
            refinement = generator.run_non_oracle_repair(
                task,
                generated.itinerary,
                max_passes=MAX_NON_ORACLE_REPAIR_PASSES,
            )
            final_itinerary = refinement.final_itinerary
            non_oracle_diagnostics = refinement.diagnostics

    submission = serializer.to_submission_record(final_itinerary, task)
    return {
        'task': task,
        'generator': generator,
        'serializer': serializer,
        'initial_itinerary': generated.itinerary,
        'final_itinerary': final_itinerary,
        'submission': submission,
        'prompt_version': getattr(generator, 'prompt_version', 'baseline'),
        'non_oracle_diagnostics': non_oracle_diagnostics,
    }


def evaluate_sample(sample: dict[str, Any], *, mode: str, travelplanner_home: str | None) -> dict[str, Any]:
    workflow = generate_submission(sample, mode)
    task = workflow['task']
    generator = workflow['generator']
    serializer = workflow['serializer']
    final_itinerary = workflow['final_itinerary']
    submission = workflow['submission']

    metrics_obj = evaluate_travelplanner_plan(sample, submission['plan'], travelplanner_home=travelplanner_home)
    metrics = metrics_obj.to_summary_dict()

    oracle_feedback = None
    oracle_repair_diagnostics = _empty_diagnostics()
    oracle_metrics = None

    if mode == 'bdi-repair':
        oracle_metrics = metrics
        if not metrics_obj.final_pass:
            oracle_feedback = build_evaluator_feedback(metrics)
            if oracle_feedback:
                oracle_refinement = generator.run_oracle_repair(
                    task,
                    final_itinerary,
                    oracle_feedback,
                )
                oracle_repair_diagnostics = oracle_refinement.diagnostics
                final_itinerary = oracle_refinement.final_itinerary
                submission = serializer.to_submission_record(final_itinerary, task)
                metrics_obj = evaluate_travelplanner_plan(
                    sample,
                    submission['plan'],
                    travelplanner_home=travelplanner_home,
                )
                oracle_metrics = metrics_obj.to_summary_dict()

    return {
        'task_id': task.task_id,
        'query': sample.get('query', ''),
        'mode': mode,
        'prompt_version': workflow['prompt_version'],
        'submission': submission,
        'metrics': metrics_obj.to_summary_dict(),
        'success': metrics_obj.final_pass,
        'itinerary': final_itinerary.model_dump(),
        'non_oracle_metrics': metrics,
        'validation_as_test_metrics': metrics,
        'non_oracle_diagnostics': workflow['non_oracle_diagnostics'],
        'oracle_feedback': oracle_feedback,
        'oracle_metrics': oracle_metrics,
        'oracle_repair_diagnostics': oracle_repair_diagnostics,
    }


def _checkpoint_file(mode_dir: Path, split: str, mode: str) -> Path:
    return mode_dir / f"checkpoint_travelplanner_{split}_{mode}.json"


def _write_checkpoint(mode_dir: Path, split: str, mode: str, results: list[dict[str, Any] | None]) -> None:
    completed = [row for row in results if row is not None]
    payload = {
        'split': split,
        'execution_mode': mode,
        'results': completed,
        'summary': summarize_travelplanner_results(completed),
    }
    if mode == 'bdi-repair' and completed:
        payload['validation_as_test_summary'] = _summarize_metric_dicts(
            [row.get('validation_as_test_metrics', row.get('metrics', {})) for row in completed]
        )
        payload['non_oracle_diagnostics_summary'] = _summarize_diagnostics(
            completed,
            'non_oracle_diagnostics',
        )
        payload['oracle_diagnostics_summary'] = _summarize_diagnostics(
            completed,
            'oracle_repair_diagnostics',
        )
    _checkpoint_file(mode_dir, split, mode).write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def _log_progress(mode: str, split: str, completed: int, total: int, results: list[dict[str, Any] | None]) -> None:
    done = [row for row in results if row is not None]
    success = sum(1 for row in done if row.get('success'))
    print(f"[{split}/{mode}] {completed}/{total} complete, success={success}", flush=True)


def _load_resume_state(
    mode_dir: Path,
    split: str,
    mode: str,
    enriched_samples: list[dict[str, Any]],
) -> tuple[list[dict[str, Any] | None], int]:
    """Reload prior checkpoint and align rows back to enriched_samples positions by task_id.

    Returns (results_with_prior_filled, completed_count). Stale or unmatched
    task_ids are warned about and ignored. Missing/unreadable checkpoint
    yields an empty result list.
    """
    total = len(enriched_samples)
    results: list[dict[str, Any] | None] = [None] * total
    ckp = _checkpoint_file(mode_dir, split, mode)
    if not ckp.exists():
        return results, 0
    try:
        prior = json.loads(ckp.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[resume] checkpoint unreadable ({exc}); starting fresh", flush=True)
        return results, 0
    by_task: dict[str, dict[str, Any]] = {}
    for row in prior.get('results') or []:
        tid = row.get('task_id')
        if tid is not None:
            by_task[str(tid)] = row
    matched = 0
    for i, sample in enumerate(enriched_samples):
        expected_tid = str(int(sample.get('idx', i + 1)))
        if expected_tid in by_task:
            results[i] = by_task[expected_tid]
            matched += 1
    stale = len(by_task) - matched
    if stale:
        print(f"[resume] {stale} prior task_id(s) not found in current sample set (ignored)", flush=True)
    if matched:
        print(f"[resume] loaded {matched}/{total} prior results from {ckp.name}", flush=True)
    return results, matched


def run_split(
    *,
    split: str,
    mode: str,
    max_instances: int | None,
    output_dir: Path,
    travelplanner_home: str | None,
    workers: int = 1,
) -> dict[str, Any]:
    try:
        return _run_split_inner(
            split=split,
            mode=mode,
            max_instances=max_instances,
            output_dir=output_dir,
            travelplanner_home=travelplanner_home,
            workers=workers,
        )
    except Exception:
        print(f"[FATAL] run_split crashed: {split}/{mode}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise


def _run_split_inner(
    *,
    split: str,
    mode: str,
    max_instances: int | None,
    output_dir: Path,
    travelplanner_home: str | None,
    workers: int = 1,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    data = load_travelplanner_split(split)
    if max_instances is not None:
        data = data[: max_instances]

    enriched_samples = []
    for idx, sample in enumerate(data, start=1):
        enriched = dict(sample)
        enriched['idx'] = idx
        enriched['split'] = split
        enriched_samples.append(enriched)

    total = len(enriched_samples)
    report_every = 1 if total <= 20 else 10
    mode_dir = output_dir / split / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    mlflow_run_id = None
    if MLFLOW_AVAILABLE:
        try:
            mlflow.set_experiment(f"travelplanner-{split}")
            run_name = f"{split}_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            mlflow.start_run(run_name=run_name)
            mlflow_run_id = mlflow.active_run().info.run_id
            mlflow.log_param("split", split)
            mlflow.log_param("mode", mode)
            mlflow.log_param("total_instances", total)
            mlflow.log_param("max_instances", max_instances if max_instances else "all")
            mlflow.log_param("workers", workers)
            mlflow.log_param("model", os.environ.get("LLM_MODEL", "unknown"))
            mlflow.log_param(
                "travelplanner_bdi_prompt_version",
                os.environ.get('TRAVELPLANNER_BDI_PROMPT_VERSION', 'v3'),
            )
            mlflow.log_param("max_non_oracle_repair_passes", MAX_NON_ORACLE_REPAIR_PASSES)
            print(f"✓ MLflow tracking enabled (Run ID: {mlflow_run_id})")
        except Exception as e:
            print(f"⚠️  MLflow init failed: {e}, continuing without tracking")
            mlflow_run_id = None

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] START split={split} mode={mode} "
        f"total={total} workers={workers} output_dir={mode_dir}",
        flush=True,
    )

    results, completed = _load_resume_state(mode_dir, split, mode, enriched_samples)
    if completed > 0:
        _log_progress(mode, split, completed, total, results)
    if workers <= 1:
        for idx, sample in enumerate(enriched_samples):
            if results[idx] is not None:
                continue
            try:
                results[idx] = evaluate_sample(sample, mode=mode, travelplanner_home=travelplanner_home)
            except Exception as exc:
                results[idx] = _failed_result(sample, idx, mode, exc)
            completed += 1
            if completed % report_every == 0 or completed == total:
                _write_checkpoint(mode_dir, split, mode, results)
                _log_progress(mode, split, completed, total, results)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(evaluate_sample, sample, mode=mode, travelplanner_home=travelplanner_home): idx
                for idx, sample in enumerate(enriched_samples)
                if results[idx] is None
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                sample = enriched_samples[idx]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    results[idx] = _failed_result(sample, idx, mode, exc)
                completed += 1
                if completed % report_every == 0 or completed == total:
                    _write_checkpoint(mode_dir, split, mode, results)
                    _log_progress(mode, split, completed, total, results)

    completed_results = [row for row in results if row is not None]
    summary = summarize_travelplanner_results(completed_results)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_path = mode_dir / f'results_travelplanner_{split}_{mode}_{stamp}.json'
    submission_path = mode_dir / f'submission_travelplanner_{split}_{mode}_{stamp}.jsonl'

    results_payload: dict[str, Any] = {
        'split': split,
        'execution_mode': mode,
        'results': completed_results,
        'summary': summary,
    }
    if mode == 'bdi-repair':
        results_payload['validation_as_test_summary'] = _summarize_metric_dicts(
            [row.get('validation_as_test_metrics', row.get('metrics', {})) for row in completed_results]
        )
        results_payload['non_oracle_diagnostics_summary'] = _summarize_diagnostics(
            completed_results,
            'non_oracle_diagnostics',
        )
        results_payload['oracle_diagnostics_summary'] = _summarize_diagnostics(
            completed_results,
            'oracle_repair_diagnostics',
        )

    results_path.write_text(json.dumps(results_payload, indent=2, ensure_ascii=False))
    with submission_path.open('w', encoding='utf-8') as f:
        for row in completed_results:
            f.write(json.dumps(row['submission'], ensure_ascii=False) + '\n')

    if MLFLOW_AVAILABLE and mlflow_run_id:
        try:
            mlflow.log_metric("delivery_rate", summary.get('delivery_rate', 0))
            mlflow.log_metric("commonsense_pass_rate", summary.get('commonsense_pass_rate', 0))
            mlflow.log_metric("hard_constraint_pass_rate", summary.get('hard_constraint_pass_rate', 0))
            mlflow.log_metric("final_pass_rate", summary.get('final_pass_rate', 0))
            mlflow.log_metric("success_count", summary.get('success_count', 0))
            mlflow.log_metric("total_evaluated", summary.get('total_evaluated', 0))
            if mode == 'bdi-repair':
                validation_as_test = results_payload['validation_as_test_summary']
                mlflow.log_metric(
                    "validation_as_test_final_pass_rate",
                    validation_as_test.get('final_pass_rate', 0),
                )
                mlflow.log_metric(
                    "non_oracle_trigger_rate",
                    results_payload['non_oracle_diagnostics_summary'].get('trigger_rate', 0),
                )
                mlflow.log_metric(
                    "avg_changed_days_when_triggered",
                    results_payload['non_oracle_diagnostics_summary'].get('avg_changed_days_when_triggered', 0),
                )
                mlflow.log_metric(
                    "avg_changed_fields_when_triggered",
                    results_payload['non_oracle_diagnostics_summary'].get('avg_changed_fields_when_triggered', 0),
                )
            mlflow.log_artifact(str(results_path))
            mlflow.log_artifact(str(submission_path))
            print("✓ MLflow: metrics and artifacts logged")
            print(
                "  View at: http://localhost:5000/#/experiments/"
                f"{mlflow.active_run().info.experiment_id}/runs/{mlflow_run_id}"
            )
        except Exception as e:
            print(f"⚠️  MLflow logging failed: {e}")
        finally:
            mlflow.end_run()

    return {
        'results_path': str(results_path),
        'submission_path': str(submission_path),
        'summary': summary,
        **(
            {
                'validation_as_test_summary': results_payload['validation_as_test_summary'],
                'non_oracle_diagnostics_summary': results_payload['non_oracle_diagnostics_summary'],
                'oracle_diagnostics_summary': results_payload['oracle_diagnostics_summary'],
            }
            if mode == 'bdi-repair'
            else {}
        ),
    }


def print_run_result(result: dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))


__all__ = [
    'TravelPlannerSetupError',
    'build_evaluator_feedback',
    'generate_submission',
    'evaluate_sample',
    'run_split',
    'print_run_result',
]
