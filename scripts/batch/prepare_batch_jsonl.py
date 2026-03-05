#!/usr/bin/env python3
"""
Phase 1: Prepare JSONL files for Alibaba Cloud Batch Inference.

For each PlanBench instance in {blocksworld, logistics, depots}:
  1. Parse the PDDL problem → beliefs + desire (natural language)
  2. Build the system + user prompt mirroring DSPy GeneratePlan signature
  3. Write one JSONL line per instance

Output: runs/batch_inference/{domain}.jsonl
"""

import json
import os
import argparse
from pathlib import Path

from scripts.evaluation.planbench_utils import (
    parse_pddl_problem,
    pddl_to_natural_language,
    find_all_instances,
)
from bdi_llm.planner import GeneratePlan, GeneratePlanLogistics, GeneratePlanDepots
from bdi_llm.schemas import BDIPlan

# ============================================================================
# Prompt Construction (replicates DSPy's prompt from Signature docstrings)
# ============================================================================

def get_system_prompt(domain: str) -> str:
    """Get the full system prompt from the DSPy Signature docstring."""
    sig_class = {
        "blocksworld": GeneratePlan,
        "logistics": GeneratePlanLogistics,
        "depots": GeneratePlanDepots,
    }[domain]
    return sig_class.__doc__.strip()

def build_user_message(beliefs: str, desire: str) -> str:
    """Build the user message from beliefs and desire."""
    return (
        f"**Beliefs (Current State):**\n{beliefs}\n\n"
        f"**Desire (Goal):**\n{desire}\n\n"
        f"**Instructions:**\n"
        f"Generate a BDI Plan as a structured JSON object with the following schema:\n"
        f"- goal_description: restatement of the goal\n"
        f"- nodes: list of action nodes, each with id, action_type, params, description\n"
        f"- edges: list of dependency edges, each with source, target, relationship\n\n"
        f"Respond with ONLY the JSON object, no markdown code fences, no extra text."
    )

def build_jsonl_line(custom_id: str, model: str, system_prompt: str,
                     user_message: str, max_tokens: int = 16000) -> dict:
    """Build a single JSONL line for the Batch API."""
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
    }

# ============================================================================
# Main
# ============================================================================

def prepare_domain(domain: str, model: str, output_dir: Path,
                   max_instances: int = None) -> str:
    """Prepare JSONL file for a single domain."""
    base_path = PROJECT_ROOT / "planbench_data" / "plan-bench"
    instances = find_all_instances(base_path, domain)
    
    if max_instances:
        instances = instances[:max_instances]
    
    system_prompt = get_system_prompt(domain)
    output_file = output_dir / f"{domain}.jsonl"
    
    count = 0
    errors = 0
    
    with open(output_file, "w", encoding="utf-8") as f:
        for inst_file in instances:
            inst_name = Path(inst_file).stem
            custom_id = f"{domain}_{inst_name}"
            
            try:
                pddl_data = parse_pddl_problem(inst_file)
                beliefs, desire = pddl_to_natural_language(pddl_data, domain)
                user_msg = build_user_message(beliefs, desire)
                
                line = build_jsonl_line(
                    custom_id=custom_id,
                    model=model,
                    system_prompt=system_prompt,
                    user_message=user_msg,
                )
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                count += 1
                
            except Exception as e:
                print(f"  ✗ {custom_id}: {e}")
                errors += 1
    
    print(f"  {domain}: {count} instances → {output_file} ({errors} errors)")
    return str(output_file)

def main():
    parser = argparse.ArgumentParser(description="Prepare JSONL for batch inference")
    parser.add_argument("--domains", nargs="+",
                        default=["blocksworld", "logistics", "depots"],
                        help="Domains to prepare")
    parser.add_argument("--model", default="qwq-plus",
                        help="Model to use (default: qwq-plus)")
    parser.add_argument("--max-instances", type=int, default=None,
                        help="Max instances per domain (for testing)")
    parser.add_argument("--output-dir", default="runs/batch_inference",
                        help="Output directory for JSONL files")
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"  Preparing JSONL for Batch Inference")
    print(f"  Model: {args.model}")
    print(f"  Domains: {', '.join(args.domains)}")
    print(f"{'='*60}\n")
    
    files = {}
    for domain in args.domains:
        files[domain] = prepare_domain(domain, args.model, output_dir,
                                       args.max_instances)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  JSONL files ready:")
    for domain, path in files.items():
        size = os.path.getsize(path)
        lines = sum(1 for _ in open(path))
        print(f"  {domain}: {lines} requests ({size/1024/1024:.1f} MB)")
    print(f"{'='*60}")
    print(f"\nNext step: python scripts/submit_batch.py --domain <domain>")

if __name__ == "__main__":
    main()
