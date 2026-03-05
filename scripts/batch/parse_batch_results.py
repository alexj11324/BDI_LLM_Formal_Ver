#!/usr/bin/env python3
"""
Phase 3: Parse Batch Inference Results and Run Verification.

Reads the JSONL result file from Alibaba Cloud Batch API,
parses each LLM response into a BDIPlan, then runs:
  - Structural verification (PlanVerifier)
  - Symbolic verification (VAL / PDDLSymbolicVerifier)

Output: runs/batch_inference/{domain}_verified.json
  (same format as run_verification_only.py checkpoint files)
"""

import json
import os
import sys
import argparse
import re
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.verifier import PlanVerifier
from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier
from scripts.evaluation.run_planbench_full import (
    parse_pddl_problem,
    pddl_to_natural_language,
    resolve_domain_file,
    bdi_to_pddl_actions,
    find_all_instances,
)


def extract_json_from_response(text: str) -> Optional[dict]:
    """Extract JSON object from LLM response text.
    
    Handles:
    - Pure JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON embedded in reasoning text
    """
    text = text.strip()
    
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from code blocks
    patterns = [
        r'```json\s*\n(.*?)\n\s*```',
        r'```\s*\n(.*?)\n\s*```',
        r'\{[^{}]*"nodes"\s*:\s*\[.*?\]\s*,\s*"edges"\s*:\s*\[.*?\]\s*[^{}]*\}',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if match.lastindex else match.group(0))
            except (json.JSONDecodeError, IndexError):
                continue
    
    # Last resort: find first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass
    
    return None


def parse_plan_from_response(response_text: str) -> Optional[BDIPlan]:
    """Parse a BDIPlan from LLM response text."""
    data = extract_json_from_response(response_text)
    if data is None:
        return None
    
    try:
        return BDIPlan(**data)
    except Exception:
        # Try nested structures
        if 'plan' in data:
            try:
                return BDIPlan(**data['plan'])
            except Exception:
                pass
        return None


def verify_plan(plan: BDIPlan, pddl_problem_path: str, pddl_domain_path: str,
                domain: str) -> dict:
    """Run structural + symbolic verification on a parsed plan."""
    result = {
        'structural': {
            'valid': False,
            'errors': [],
            'hard_errors': [],
            'warnings': [],
        },
        'symbolic': {
            'valid': False,
            'errors': [],
            'ran': False,
        },
        'agreement': None,
    }
    
    # Structural verification
    try:
        G = plan.to_networkx()
        struct_result = PlanVerifier.verify(G)
        result['structural']['valid'] = struct_result.is_valid
        result['structural']['errors'] = struct_result.errors
        result['structural']['hard_errors'] = struct_result.hard_errors
        result['structural']['warnings'] = struct_result.warnings
    except Exception as e:
        result['structural']['errors'] = [f"Structural error: {str(e)[:200]}"]
    
    # Symbolic verification (VAL)
    try:
        pddl_actions = bdi_to_pddl_actions(plan, domain=domain)
        val_verifier = PDDLSymbolicVerifier()
        symbolic_valid, symbolic_errors = val_verifier.verify_plan(
            domain_file=pddl_domain_path,
            problem_file=pddl_problem_path,
            plan_actions=pddl_actions,
        )
        result['symbolic']['valid'] = symbolic_valid
        result['symbolic']['errors'] = symbolic_errors
        result['symbolic']['ran'] = True
    except Exception as e:
        result['symbolic']['errors'] = [f"Symbolic error: {str(e)[:200]}"]
        result['symbolic']['ran'] = True
    
    result['agreement'] = result['structural']['valid'] == result['symbolic']['valid']
    return result


def main():
    parser = argparse.ArgumentParser(description="Parse batch results and verify plans")
    parser.add_argument("--domain", required=True,
                        help="Domain (blocksworld/logistics/depots)")
    parser.add_argument("--results-file", type=str,
                        help="Custom results JSONL file path")
    parser.add_argument("--output-dir", default="runs/batch_inference",
                        help="Output directory")
    args = parser.parse_args()
    
    results_file = args.results_file or f"runs/batch_inference/{args.domain}_results.jsonl"
    if not os.path.exists(results_file):
        print(f"ERROR: Results file not found: {results_file}")
        sys.exit(1)
    
    output_dir = Path(args.output_dir)
    base_path = PROJECT_ROOT / "planbench_data" / "plan-bench"
    
    # Build instance map: custom_id → instance_file
    instances = find_all_instances(base_path, args.domain)
    instance_map = {}
    for inst_file in instances:
        inst_name = Path(inst_file).stem
        custom_id = f"{args.domain}_{inst_name}"
        instance_map[custom_id] = inst_file
    
    # Checkpoint support
    checkpoint_file = output_dir / f"{args.domain}_verified_checkpoint.json"
    completed_ids = set()
    verified_results = []
    stats = {'total': 0, 'parsed': 0, 'struct_valid': 0, 'val_valid': 0, 'errors': 0}
    
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as cf:
            checkpoint_data = json.load(cf)
            verified_results = checkpoint_data.get('results', [])
            stats = checkpoint_data.get('stats', stats)
            completed_ids = {r['custom_id'] for r in verified_results if 'custom_id' in r}
        print(f"  Resuming from checkpoint: {len(completed_ids)} already verified")
    
    print(f"\n{'='*60}")
    print(f"  Parsing Batch Results: {args.domain}")
    print(f"  Results file: {results_file}")
    print(f"  Known instances: {len(instance_map)}")
    print(f"  Already verified: {len(completed_ids)}")
    print(f"{'='*60}\n")
    
    with open(results_file, 'r') as f:
        for line in f:
            stats['total'] += 1
            batch_result = json.loads(line.strip())
            custom_id = batch_result.get('custom_id', '')
            
            # Skip already verified
            if custom_id in completed_ids:
                continue
            
            # Get instance file
            inst_file = instance_map.get(custom_id)
            if not inst_file:
                print(f"  ✗ Unknown custom_id: {custom_id}")
                stats['errors'] += 1
                continue
            
            # Extract LLM response
            response = batch_result.get('response', {})
            if response.get('status_code') != 200:
                error_msg = response.get('body', {}).get('error', {}).get('message', 'Unknown error')
                verified_results.append({
                    'instance_file': inst_file,
                    'custom_id': custom_id,
                    'generation': {
                        'success': False,
                        'error': f"API error: {error_msg}",
                    },
                })
                stats['errors'] += 1
                continue
            
            # Get content from response
            choices = response.get('body', {}).get('choices', [])
            if not choices:
                verified_results.append({
                    'instance_file': inst_file,
                    'custom_id': custom_id,
                    'generation': {'success': False, 'error': 'No choices in response'},
                })
                stats['errors'] += 1
                continue
            
            content = choices[0].get('message', {}).get('content', '')
            
            # Parse plan
            plan = parse_plan_from_response(content)
            if plan is None:
                verified_results.append({
                    'instance_file': inst_file,
                    'custom_id': custom_id,
                    'generation': {'success': False, 'error': 'Failed to parse JSON plan'},
                })
                stats['errors'] += 1
                continue
            
            stats['parsed'] += 1
            
            # Get domain file for VAL
            try:
                pddl_data = parse_pddl_problem(inst_file)
                domain_name = pddl_data.get('domain_name', args.domain)
                domain_file = resolve_domain_file(domain_name)
            except Exception as e:
                verified_results.append({
                    'instance_file': inst_file,
                    'custom_id': custom_id,
                    'generation': {
                        'success': True,
                        'num_nodes': len(plan.nodes),
                        'num_edges': len(plan.edges),
                    },
                    'structural': {'valid': False, 'errors': [f"PDDL parse error: {e}"]},
                    'symbolic': {'valid': False, 'ran': False},
                })
                stats['errors'] += 1
                continue
            
            # Verify
            verify_result = verify_plan(plan, inst_file, domain_file, args.domain)
            
            result_entry = {
                'instance_file': inst_file,
                'custom_id': custom_id,
                'generation': {
                    'success': True,
                    'num_nodes': len(plan.nodes),
                    'num_edges': len(plan.edges),
                },
                **verify_result,
            }
            verified_results.append(result_entry)
            
            if verify_result['structural']['valid']:
                stats['struct_valid'] += 1
            if verify_result['symbolic']['valid']:
                stats['val_valid'] += 1
            
            # Checkpoint every 20 items
            if len(verified_results) % 20 == 0 and len(verified_results) > 0:
                with open(checkpoint_file, 'w') as cf:
                    json.dump({'domain': args.domain, 'stats': stats,
                               'results': verified_results}, cf)
            
            if stats['total'] % 50 == 0:
                print(f"  Processed {stats['total']}...")
    
    # Save final results
    output_file = output_dir / f"{args.domain}_verified.json"
    with open(output_file, 'w') as f:
        json.dump({
            'domain': args.domain,
            'model': 'qwen-plus',
            'stats': stats,
            'results': verified_results,
        }, f, indent=2)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  Results: {args.domain}")
    print(f"  Total:           {stats['total']}")
    print(f"  Parsed:          {stats['parsed']}")
    print(f"  Struct valid:    {stats['struct_valid']}")
    print(f"  VAL valid:       {stats['val_valid']}")
    print(f"  Errors:          {stats['errors']}")
    if stats['parsed'] > 0:
        print(f"  Struct rate:     {stats['struct_valid']/stats['parsed']*100:.1f}%")
        print(f"  VAL rate:        {stats['val_valid']/stats['parsed']*100:.1f}%")
    print(f"  Output: {output_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
