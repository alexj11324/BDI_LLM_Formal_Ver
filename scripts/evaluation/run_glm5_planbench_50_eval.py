#!/usr/bin/env python3
"""
Run GLM-5 on a fixed number of PlanBench instances and compute:
1) Syntax error rate (malformed/failed structured output)
2) Verifier-driven correction success rate within 3 repair attempts

Outputs are written to a dedicated run directory.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SYNTAX_ERROR_KEYWORDS = (
    "failed to generate a valid plan object",
    "jsondecodeerror",
    "invalid json",
    "expecting value",
    "expecting property name enclosed in double quotes",
    "unterminated string",
    "extra data",
    "parse error",
    "failed to parse",
    "pydantic",
    "validationerror",
    "json",
)


def _collect_text_errors(instance_result: Dict[str, Any]) -> List[str]:
    texts: List[str] = []

    top_error = instance_result.get("error")
    if top_error:
        texts.append(str(top_error))

    metrics = instance_result.get("bdi_metrics", {})
    layers = metrics.get("verification_layers", {})
    structural = layers.get("structural", {})
    for key in ("errors", "hard_errors", "warnings"):
        value = structural.get(key, [])
        if isinstance(value, list):
            texts.extend(str(v) for v in value if v is not None)
        elif value is not None:
            texts.append(str(value))

    return texts


def _classify_syntax_error(instance_result: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    error_texts = _collect_text_errors(instance_result)
    haystack = "\n".join(error_texts).lower()
    matches = [kw for kw in SYNTAX_ERROR_KEYWORDS if kw in haystack]
    return (len(matches) > 0, matches, error_texts)


def _has_reasoning_trace(instance_result: Dict[str, Any]) -> bool:
    metrics = instance_result.get("bdi_metrics", {})
    trace = metrics.get("reasoning_trace", {})
    generation = trace.get("generation")
    if not isinstance(generation, dict):
        return False

    for key in ("lm_reasoning_content", "chain_of_thought_text", "prediction_text_fields"):
        value = generation.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and value:
            return True
    return False


def _build_compact_record(instance_result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = instance_result.get("bdi_metrics", {})
    val_repair = metrics.get("val_repair", {})
    val_attempts = int(val_repair.get("attempts", 0) or 0)
    val_success = bool(val_repair.get("success", False))
    syntax_error, syntax_markers, error_texts = _classify_syntax_error(instance_result)

    return {
        "instance_file": instance_result.get("instance_file"),
        "instance_name": instance_result.get("instance_name"),
        "success": bool(instance_result.get("success", False)),
        "syntax_error": syntax_error,
        "syntax_error_markers": syntax_markers,
        "syntax_error_messages": error_texts[:10],
        "val_repair_triggered": val_attempts > 0,
        "val_repair_attempts": val_attempts,
        "val_repair_success": val_success,
        "fixed_within_3": val_success and val_attempts <= 3,
        "reasoning_trace_present": _has_reasoning_trace(instance_result),
        "generation_time": metrics.get("generation_time"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GLM-5 PlanBench 50-instance evaluator")
    parser.add_argument("--domain", default="blocksworld", choices=["blocksworld", "logistics", "depots"])
    parser.add_argument("--num_instances", type=int, default=50)
    parser.add_argument("--model", default="z-ai/glm5")
    parser.add_argument("--api_base", default="https://integrate.api.nvidia.com/v1")
    parser.add_argument("--output_dir", default=None, help="Dedicated output directory. Auto-generated if omitted.")
    parser.add_argument("--reasoning_trace_max_chars", type=int, default=12000)
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers. Use 1 for serial mode.")
    args = parser.parse_args()

    # Ensure environment is set BEFORE importing run_planbench_full/planner modules.
    os.environ.setdefault("OPENAI_API_BASE", args.api_base)
    os.environ["LLM_MODEL"] = args.model
    os.environ["SAVE_REASONING_TRACE"] = "true"
    os.environ["REASONING_TRACE_MAX_CHARS"] = str(args.reasoning_trace_max_chars)
    os.environ["AGENT_EXECUTION_MODE"] = "FULL_VERIFIED"

    from scripts.evaluation.run_planbench_full import evaluate_single_instance
    from scripts.evaluation.planbench_utils import find_all_instances

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "runs" / f"glm5_planbench_{args.num_instances}_eval_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    base_path = REPO_ROOT / "planbench_data" / "plan-bench"
    all_instances = find_all_instances(str(base_path), args.domain)
    selected_instances = all_instances[: args.num_instances]
    if len(selected_instances) < args.num_instances:
        print(
            f"Warning: requested {args.num_instances} instances, found {len(selected_instances)} in domain '{args.domain}'."
        )

    config_payload = {
        "timestamp": timestamp,
        "domain": args.domain,
        "num_instances_requested": args.num_instances,
        "num_instances_selected": len(selected_instances),
        "model": args.model,
        "api_base": os.environ.get("OPENAI_API_BASE"),
        "save_reasoning_trace": os.environ.get("SAVE_REASONING_TRACE"),
        "reasoning_trace_max_chars": args.reasoning_trace_max_chars,
        "execution_mode": os.environ.get("AGENT_EXECUTION_MODE"),
        "workers": args.workers,
    }
    with open(run_dir / "config.json", "w") as f:
        json.dump(config_payload, f, indent=2)

    raw_results: List[Dict[str, Any]] = []
    compact_records: List[Dict[str, Any]] = []
    jsonl_path = run_dir / "instances.jsonl"

    print("=" * 80)
    print("GLM-5 PLANBENCH EVAL")
    print("=" * 80)
    print(f"Domain: {args.domain}")
    print(f"Instances: {len(selected_instances)}")
    print(f"Model: {args.model}")
    print(f"Output dir: {run_dir}")
    print("=" * 80)

    with open(jsonl_path, "w") as jsonl_f:
        if args.workers <= 1:
            for idx, instance_file in enumerate(selected_instances, start=1):
                print(f"[{idx}/{len(selected_instances)}] {instance_file}")
                result = evaluate_single_instance(instance_file, args.domain)
                raw_results.append(result)

                compact = _build_compact_record(result)
                compact_records.append(compact)
                jsonl_f.write(json.dumps(compact, ensure_ascii=False) + "\n")
                jsonl_f.flush()
        else:
            print(f"Running in parallel mode with workers={args.workers}")
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_to_instance = {
                    executor.submit(evaluate_single_instance, instance_file, args.domain): instance_file
                    for instance_file in selected_instances
                }

                completed = 0
                for future in as_completed(future_to_instance):
                    completed += 1
                    instance_file = future_to_instance[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "instance_file": instance_file,
                            "instance_name": Path(instance_file).stem,
                            "success": False,
                            "error": f"Worker exception: {exc}",
                            "bdi_metrics": {
                                "verification_layers": {"structural": {"errors": [str(exc)], "hard_errors": [str(exc)]}},
                                "val_repair": {"attempts": 0, "success": False},
                            },
                        }

                    print(f"[{completed}/{len(selected_instances)}] {instance_file}")
                    raw_results.append(result)

                    compact = _build_compact_record(result)
                    compact_records.append(compact)
                    jsonl_f.write(json.dumps(compact, ensure_ascii=False) + "\n")
                    jsonl_f.flush()

    with open(run_dir / "raw_results.json", "w") as f:
        json.dump(raw_results, f, indent=2)

    total = len(compact_records)
    syntax_error_count = sum(1 for r in compact_records if r["syntax_error"])
    syntax_error_rate = syntax_error_count / total if total else 0.0

    val_repair_triggered = [r for r in compact_records if r["val_repair_triggered"]]
    val_repair_triggered_count = len(val_repair_triggered)
    fixed_within_3_count = sum(1 for r in val_repair_triggered if r["fixed_within_3"])
    correction_success_rate_triggered = (
        fixed_within_3_count / val_repair_triggered_count if val_repair_triggered_count else 0.0
    )
    correction_success_rate_global = fixed_within_3_count / total if total else 0.0

    overall_success_count = sum(1 for r in compact_records if r["success"])
    reasoning_trace_count = sum(1 for r in compact_records if r["reasoning_trace_present"])

    summary = {
        "timestamp": timestamp,
        "model": args.model,
        "domain": args.domain,
        "total_instances": total,
        "metrics": {
            "syntax_error_count": syntax_error_count,
            "syntax_error_rate": syntax_error_rate,
            "val_repair_triggered_count": val_repair_triggered_count,
            "fixed_within_3_count": fixed_within_3_count,
            "correction_success_rate_triggered": correction_success_rate_triggered,
            "correction_success_rate_global": correction_success_rate_global,
            "overall_success_count": overall_success_count,
            "overall_success_rate": overall_success_count / total if total else 0.0,
            "reasoning_trace_count": reasoning_trace_count,
            "reasoning_trace_rate": reasoning_trace_count / total if total else 0.0,
        },
        "files": {
            "config": str(run_dir / "config.json"),
            "instances_jsonl": str(jsonl_path),
            "raw_results": str(run_dir / "raw_results.json"),
        },
    }

    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Syntax error rate: {syntax_error_count}/{total} = {syntax_error_rate:.2%}")
    print(
        "Correction success rate (within <=3, among verifier-triggered): "
        f"{fixed_within_3_count}/{val_repair_triggered_count} = {correction_success_rate_triggered:.2%}"
    )
    print(
        "Correction success rate (within <=3, global): "
        f"{fixed_within_3_count}/{total} = {correction_success_rate_global:.2%}"
    )
    print(f"Reasoning trace coverage: {reasoning_trace_count}/{total} = {summary['metrics']['reasoning_trace_rate']:.2%}")
    print(f"Output: {run_dir}")


if __name__ == "__main__":
    main()
