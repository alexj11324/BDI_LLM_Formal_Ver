#!/usr/bin/env python3
"""
PlanBench Integration for BDI-LLM Framework
===========================================

Adapts PlanBench (https://github.com/karthikv792/gpt-plan-benchmark) for evaluation
of BDI-LLM planning capabilities.

PlanBench provides 7 task categories with 500 instances each:
- t1: Plan Generation (goal-directed reasoning)
- t2: Optimal Planning (cost-optimal plans)
- t3: Plan Verification (reasoning about plan execution)
- t4: Plan Reuse (can reuse existing plans)
- t5: Plan Generalization (extract procedural patterns)
- t6: Replanning (adapt to unexpected changes)
- t7: Plan Execution Reasoning
- t8: Goal Reformulation (3 variants)

Usage:
    python scripts/run_planbench_eval.py --task t1 --n_instances 20
    python scripts/run_planbench_eval.py --task all --n_instances 10
"""

import sys
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bdi_llm.schemas import ActionNode, DependencyEdge, BDIPlan
from bdi_llm.verifier import PlanVerifier


@dataclass
class PLANBenchResult:
    """Result of evaluating one PlanBench instance"""
    instance_id: int
    task: str
    is_structurally_valid: bool  # DAG verifier passes
    is_goal_achieved: bool       # PDDL validator passes (if available)
    errors: List[str]
    plan: Optional[BDIPlan]
    execution_order: List[str]


class PDDLToBDIConverter:
    """
    Converts PDDL problems to BDI beliefs/desires format.

    PDDL structure:
    (:objects ...)
    (:init ...)     → Beliefs (current state)
    (:goal ...)     → Desire (target state)
    """

    @staticmethod
    def parse_pddl_file(pddl_path: str) -> Dict[str, any]:
        """Parse PDDL problem file"""
        with open(pddl_path, 'r') as f:
            content = f.read()

        # Extract objects
        objects_match = re.search(r'\(:objects\s+(.*?)\)', content, re.DOTALL)
        objects = objects_match.group(1).strip().split() if objects_match else []

        # Extract init state (beliefs)
        init_match = re.search(r'\(:init\s+(.*?)\)\s*\(:goal', content, re.DOTALL)
        init_predicates = []
        if init_match:
            init_text = init_match.group(1).strip()
            init_predicates = re.findall(r'\(([^)]+)\)', init_text)

        # Extract goal state (desire)
        goal_match = re.search(r'\(:goal\s+\(and\s+(.*?)\)\s*\)', content, re.DOTALL)
        goal_predicates = []
        if goal_match:
            goal_text = goal_match.group(1).strip()
            goal_predicates = re.findall(r'\(([^)]+)\)', goal_text)

        return {
            'objects': objects,
            'init': init_predicates,
            'goal': goal_predicates
        }

    @staticmethod
    def pddl_to_natural_language(parsed_pddl: Dict, domain: str = "blocksworld") -> Tuple[str, str]:
        """
        Convert parsed PDDL to natural language beliefs and desires.

        For Blocksworld:
        - (ontable A) → "Block A is on the table"
        - (on A B) → "Block A is on block B"
        - (clear A) → "Block A has nothing on top"
        - (handempty) → "The robotic hand is empty"
        """

        # Blocksworld-specific translations
        if domain == "blocksworld":
            beliefs_nl = []

            # Translate init predicates
            for pred in parsed_pddl['init']:
                parts = pred.split()
                if not parts:
                    continue

                pred_name = parts[0]

                if pred_name == "handempty":
                    beliefs_nl.append("The robotic hand is empty.")
                elif pred_name == "ontable" and len(parts) == 2:
                    beliefs_nl.append(f"Block {parts[1].upper()} is on the table.")
                elif pred_name == "clear" and len(parts) == 2:
                    beliefs_nl.append(f"Block {parts[1].upper()} has nothing on top of it.")
                elif pred_name == "on" and len(parts) == 3:
                    beliefs_nl.append(f"Block {parts[1].upper()} is on block {parts[2].upper()}.")

            beliefs = "\\n".join(beliefs_nl)

            # Translate goal predicates
            desires_nl = []
            for pred in parsed_pddl['goal']:
                parts = pred.split()
                if not parts:
                    continue

                if parts[0] == "on" and len(parts) == 3:
                    desires_nl.append(f"Block {parts[1].upper()} should be on block {parts[2].upper()}.")

            desire = " ".join(desires_nl)

            # Add available actions
            beliefs += "\\n\\nAvailable actions: pickup(block), putdown(block), stack(block_a, block_b), unstack(block_a, block_b)"

            return beliefs, desire

        else:
            # Generic PDDL-to-text (for other domains)
            beliefs = "\\n".join([f"- {pred}" for pred in parsed_pddl['init']])
            desire = " and ".join([f"{pred}" for pred in parsed_pddl['goal']])
            return beliefs, desire


class PlanBenchEvaluator:
    """Evaluates BDI-LLM on PlanBench tasks"""

    def __init__(self, planbench_root: str = "planbench_data/plan-bench"):
        self.planbench_root = Path(planbench_root)
        self.converter = PDDLToBDIConverter()

        # Check if PlanBench repo exists
        if not self.planbench_root.exists():
            raise FileNotFoundError(
                f"PlanBench repository not found at {self.planbench_root}. "
                "Please run: git clone https://github.com/karthikv792/gpt-plan-benchmark.git planbench_data"
            )

    def load_instances(self, domain: str = "blocksworld", n_instances: int = 10) -> List[Dict]:
        """Load PDDL instances from PlanBench"""
        instance_dir = self.planbench_root / "instances" / domain / "generated"

        if not instance_dir.exists():
            raise FileNotFoundError(f"Instance directory not found: {instance_dir}")

        # Get all PDDL files
        pddl_files = sorted(instance_dir.glob("instance-*.pddl"))[:n_instances]

        instances = []
        for pddl_file in pddl_files:
            # Extract instance number
            match = re.search(r'instance-(\d+)', pddl_file.name)
            instance_id = int(match.group(1)) if match else 0

            # Parse PDDL
            parsed = self.converter.parse_pddl_file(str(pddl_file))

            # Convert to NL
            beliefs, desire = self.converter.pddl_to_natural_language(parsed, domain)

            instances.append({
                'id': instance_id,
                'domain': domain,
                'pddl_file': str(pddl_file),
                'parsed_pddl': parsed,
                'beliefs': beliefs,
                'desire': desire
            })

        return instances

    def evaluate_task_t1(self, planner, instances: List[Dict], verbose: bool = False) -> List[PLANBenchResult]:
        """
        Task 1: Plan Generation (Goal-directed reasoning)

        Test if BDI-LLM can generate valid plans to achieve goals.
        """
        results = []

        for instance in instances:
            if verbose:
                print(f"\\n{'='*60}")
                print(f"Evaluating Instance {instance['id']}")
                print(f"{'='*60}")
                print(f"Beliefs:\\n{instance['beliefs'][:200]}...")
                print(f"\\nDesire: {instance['desire'][:100]}...")

            try:
                # Generate plan with BDI-LLM
                response = planner(beliefs=instance['beliefs'], desire=instance['desire'])
                plan = response.plan

                # Verify with DAG verifier
                G = plan.to_networkx()
                is_valid, errors = PlanVerifier.verify(G)

                # Get execution order
                exec_order = PlanVerifier.topological_sort(G) if is_valid else []

                if verbose:
                    print(f"\\nGenerated Plan:")
                    print(f"  Nodes: {[n.id for n in plan.nodes]}")
                    print(f"  Edges: {[(e.source, e.target) for e in plan.edges]}")
                    print(f"  Valid: {is_valid}")
                    if not is_valid:
                        print(f"  Errors: {errors}")
                    else:
                        print(f"  Execution Order: {exec_order}")

                result = PLANBenchResult(
                    instance_id=instance['id'],
                    task="t1_plan_generation",
                    is_structurally_valid=is_valid,
                    is_goal_achieved=False,  # Would need PDDL validator
                    errors=errors,
                    plan=plan,
                    execution_order=exec_order
                )

            except Exception as e:
                if verbose:
                    print(f"\\nERROR: {str(e)}")

                result = PLANBenchResult(
                    instance_id=instance['id'],
                    task="t1_plan_generation",
                    is_structurally_valid=False,
                    is_goal_achieved=False,
                    errors=[str(e)],
                    plan=None,
                    execution_order=[]
                )

            results.append(result)

        return results

    def print_summary(self, results: List[PLANBenchResult], task_name: str):
        """Print evaluation summary"""
        total = len(results)
        structurally_valid = sum(1 for r in results if r.is_structurally_valid)

        print(f"\\n{'='*70}")
        print(f"PLANBENCH EVALUATION SUMMARY - {task_name}")
        print(f"{'='*70}")
        print(f"Total Instances: {total}")
        print(f"Structurally Valid (DAG): {structurally_valid}/{total} ({structurally_valid/total*100:.1f}%)")
        print(f"Failed Instances: {total - structurally_valid}")

        # Error breakdown
        if total > structurally_valid:
            print(f"\\nError Breakdown:")
            error_counts = {}
            for r in results:
                if not r.is_structurally_valid:
                    for error in r.errors:
                        error_key = error.split(':')[0]  # Get error type
                        error_counts[error_key] = error_counts.get(error_key, 0) + 1

            for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                print(f"  - {error_type}: {count}")

        print(f"{'='*70}\\n")

    def save_results(self, results: List[PLANBenchResult], output_file: str):
        """Save evaluation results to JSON"""
        results_dict = {
            'task': results[0].task if results else 'unknown',
            'total_instances': len(results),
            'structurally_valid': sum(1 for r in results if r.is_structurally_valid),
            'instances': [
                {
                    'id': r.instance_id,
                    'structurally_valid': r.is_structurally_valid,
                    'errors': r.errors,
                    'num_nodes': len(r.plan.nodes) if r.plan else 0,
                    'num_edges': len(r.plan.edges) if r.plan else 0,
                    'execution_order': r.execution_order
                }
                for r in results
            ]
        }

        with open(output_file, 'w') as f:
            json.dump(results_dict, f, indent=2)

        print(f"Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Run PlanBench evaluation on BDI-LLM")
    parser.add_argument("--task", default="t1", choices=["t1", "all"],
                       help="PlanBench task to run (currently only t1 supported)")
    parser.add_argument("--n_instances", type=int, default=20,
                       help="Number of instances to evaluate")
    parser.add_argument("--domain", default="blocksworld",
                       help="Planning domain (default: blocksworld)")
    parser.add_argument("--verbose", action="store_true",
                       help="Print detailed output")
    parser.add_argument("--output", default="planbench_results.json",
                       help="Output file for results")

    args = parser.parse_args()

    # Check if API key is available
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set.")
        print("Set it with: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    # Initialize evaluator
    print(f"\\n{'='*70}")
    print("BDI-LLM PlanBench Evaluation")
    print(f"{'='*70}")
    print(f"Task: {args.task}")
    print(f"Domain: {args.domain}")
    print(f"Instances: {args.n_instances}")
    print(f"{'='*70}\\n")

    evaluator = PlanBenchEvaluator()

    # Load instances
    print(f"Loading {args.n_instances} instances from PlanBench...")
    instances = evaluator.load_instances(domain=args.domain, n_instances=args.n_instances)
    print(f"Loaded {len(instances)} instances.\\n")

    # Initialize planner
    from bdi_llm.planner import BDIPlanner
    planner = BDIPlanner()

    # Run evaluation
    if args.task == "t1":
        results = evaluator.evaluate_task_t1(planner, instances, verbose=args.verbose)
    else:
        print(f"Task {args.task} not yet implemented")
        sys.exit(1)

    # Print summary
    evaluator.print_summary(results, args.task.upper())

    # Save results
    evaluator.save_results(results, args.output)


if __name__ == "__main__":
    main()
