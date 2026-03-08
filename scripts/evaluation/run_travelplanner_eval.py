#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.travelplanner import (
    TravelPlannerGenerator,
    TravelPlannerPlanSerializer,
    TravelPlannerTaskAdapter,
    TravelPlannerSetupError,
    evaluate_travelplanner_plan,
    load_travelplanner_split,
    summarize_travelplanner_results,
)


def _build_evaluator_feedback(metrics: dict[str, Any]) -> str:
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


def evaluate_sample(sample: dict[str, Any], *, mode: str, travelplanner_home: str | None) -> dict[str, Any]:
    adapter = TravelPlannerTaskAdapter()
    generator = TravelPlannerGenerator()
    serializer = TravelPlannerPlanSerializer()
    task = adapter.to_planning_task(sample)

    if mode == 'baseline':
        generated = generator.generate_baseline(task.beliefs, task.desire, task.domain_context or '')
    else:
        generated = generator.generate_bdi(task.beliefs, task.desire, task.domain_context or '')

    submission = serializer.to_submission_record(generated.itinerary, task)
    metrics = evaluate_travelplanner_plan(sample, submission['plan'], travelplanner_home=travelplanner_home)

    if mode == 'bdi-repair' and not metrics.final_pass:
        feedback = _build_evaluator_feedback(metrics.to_summary_dict())
        repaired = generator.repair(
            task.beliefs,
            task.desire,
            task.domain_context or '',
            generated.itinerary,
            feedback,
        )
        submission = serializer.to_submission_record(repaired.itinerary, task)
        metrics = evaluate_travelplanner_plan(sample, submission['plan'], travelplanner_home=travelplanner_home)
        generated = repaired

    return {
        'task_id': task.task_id,
        'query': sample.get('query', ''),
        'mode': mode,
        'submission': submission,
        'metrics': metrics.to_summary_dict(),
        'success': metrics.final_pass,
        'itinerary': generated.itinerary.model_dump(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='TravelPlanner validation runner')
    parser.add_argument('--split', choices=['train', 'validation', 'test'], default='validation')
    parser.add_argument('--execution_mode', choices=['baseline', 'bdi', 'bdi-repair'], default='bdi-repair')
    parser.add_argument('--max_instances', type=int, default=None)
    parser.add_argument('--output_dir', type=Path, default=Path('runs/travelplanner'))
    parser.add_argument('--travelplanner_home', type=str, default=None)
    args = parser.parse_args()

    data = load_travelplanner_split(args.split)
    if args.max_instances is not None:
        data = data[: args.max_instances]

    results = []
    for idx, sample in enumerate(data, start=1):
        enriched = dict(sample)
        enriched['idx'] = idx
        enriched['split'] = args.split
        results.append(evaluate_sample(enriched, mode=args.execution_mode, travelplanner_home=args.travelplanner_home))

    summary = summarize_travelplanner_results(results)
    output_dir = args.output_dir / args.split / args.execution_mode
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_path = output_dir / f'results_travelplanner_{args.split}_{args.execution_mode}_{stamp}.json'
    submission_path = output_dir / f'submission_travelplanner_{args.split}_{args.execution_mode}_{stamp}.jsonl'
    results_path.write_text(json.dumps({'split': args.split, 'execution_mode': args.execution_mode, 'results': results, 'summary': summary}, indent=2, ensure_ascii=False))
    with submission_path.open('w', encoding='utf-8') as f:
        for row in results:
            f.write(json.dumps(row['submission'], ensure_ascii=False) + '\n')

    print(json.dumps({'results_path': str(results_path), 'submission_path': str(submission_path), 'summary': summary}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except TravelPlannerSetupError as exc:
        raise SystemExit(str(exc))
