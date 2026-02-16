
import sys
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

import dspy
from datasets import load_dataset
from bdi_llm.coding_planner import CodingBDIPlanner
from bdi_llm.schemas import BDIPlan, ActionNode

class LocalSWEBenchHarness:
    def __init__(self, workspace_dir: str = "swe_bench_workspace"):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(exist_ok=True)
        self.planner = CodingBDIPlanner(auto_repair=True)
        
        # Load dataset (lazy load)
        self._dataset = None

    @property
    def dataset(self):
        if self._dataset is None:
            print("Loading SWE-bench Verified dataset...")
            self._dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
        return self._dataset

    def get_instance(self, instance_id: str) -> Dict[str, Any]:
        """Retrieve a specific instance by ID"""
        # Linear search for now (dataset is small enough)
        for item in self.dataset:
            if item['instance_id'] == instance_id:
                return item
        raise ValueError(f"Instance {instance_id} not found")

    def setup_repo(self, instance: Dict[str, Any]) -> Path:
        """Clone and checkout the repository for the instance"""
        repo_name = instance['repo']
        base_commit = instance['base_commit']
        instance_id = instance['instance_id']
        
        # Create a specific directory for this instance
        instance_dir = self.workspace_dir / instance_id
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
        instance_dir.mkdir()
        
        print(f"Setting up repo {repo_name} at {instance_dir}...")
        
        # Clone (using shallow clone if possible, but we need specific commit)
        # We might need to clone from the official GitHub URL
        repo_url = f"https://github.com/{repo_name}.git"
        
        subprocess.run(
            ["git", "clone", repo_url, "."],
            cwd=instance_dir,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            ["git", "checkout", base_commit],
            cwd=instance_dir,
            check=True,
            capture_output=True
        )
        
        return instance_dir

    def run_tests(self, instance_dir: Path, test_cmd: str) -> tuple[bool, str]:
        """Run the test command locally"""
        print(f"Running tests: {test_cmd}")
        try:
            # We run with shell=True because test_cmd is often a complex shell string
            # Warning: This is risky, but necessary for SWE-bench
            result = subprocess.run(
                test_cmd,
                cwd=instance_dir,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300 # 5 minute timeout
            )
            return result.returncode == 0, result.stdout + "\n" + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Test execution timed out"

    def execute_plan(self, plan: BDIPlan, instance_dir: Path, issue_desc: str):
        """Execute the generated plan actions"""
        # Topologically sort nodes to ensure dependencies are met
        # BDIPlanner supposedly guarantees a DAG, but we should traverse it correctly.
        # For simplicity, we assume the nodes list is somewhat ordered or we just iterate
        # and execute executable actions.
        # Actually, BDIPlan nodes are a list. We should execute them in dependency order.
        
        # Simple execution: assume linear or iterate until consistent
        # Better: Build a graph and traverse
        
        node_map = {n.id: n for n in plan.nodes}
        executed = set()
        
        # Context for the LLM during execution
        file_contents = {} # path -> content
        
        # Naive execution loop (improve this later)
        sorted_nodes = plan.nodes # BDIPlanner typically outputs topological order
        
        for node in sorted_nodes:
            print(f"Executing step {node.id}: {node.action_type} - {node.description}")
            
            if node.action_type == "read-file":
                fpath = node.params.get('file')
                abs_path = instance_dir / fpath
                if abs_path.exists():
                    try:
                        content = abs_path.read_text()
                        file_contents[fpath] = content
                        print(f"Read {fpath} ({len(content)} bytes)")
                    except Exception as e:
                        print(f"Failed to read {fpath}: {e}")
                else:
                    print(f"File not found: {fpath}")

            elif node.action_type == "edit-file":
                fpath = node.params.get('file')
                if fpath not in file_contents:
                    # Try to read if not already read (implicit dependency)
                    abs_path = instance_dir / fpath
                    if abs_path.exists():
                        file_contents[fpath] = abs_path.read_text()
                
                if fpath in file_contents:
                    current_content = file_contents[fpath]
                    
                    # Call LLM to implement the change
                    print(f"Generating code change for {fpath}...")
                    prediction = self.planner.implement_change(
                        file_path=fpath,
                        current_content=current_content,
                        issue_description=issue_desc,
                        step_description=node.description
                    )
                    
                    new_content = prediction.new_content
                    
                    # Write back to file
                    (instance_dir / fpath).write_text(new_content)
                    print(f"Applied changes to {fpath}")
                    
                    # Update cache
                    file_contents[fpath] = new_content
                else:
                    print(f"Cannot edit {fpath}: content not available")

            elif node.action_type == "run-test":
                # In this harness, we might want to run the test immediately or wait?
                # The PDDL says run-test is an action.
                # Use the test command from the instance, or a specific test if provided?
                # node.params.get('test') might be a specific test ID.
                # SWE-bench usually provides a global test script.
                # We can try to run `pytest <id>` if possible, otherwise run the global script.
                test_id = node.params.get('test')
                print(f"Running test verification: {test_id}")
                # For now, just logging. Real test run happens at the end of loop.

            elif node.action_type == "create-file":
                 fpath = node.params.get('file')
                 # For now, create empty or ask LLM?
                 # BDIPlan doesn't have content. 
                 # We skip for now or make empty.
                 (instance_dir / fpath).touch()
                 print(f"Created file {fpath}")

    def run_instance(self, instance_id: str):
        print(f"=== Running Instance {instance_id} ===")
        instance = self.get_instance(instance_id)
        
        # 1. Setup
        repo_dir = self.setup_repo(instance)
        
        # 2. Planning
        issue_desc = instance['problem_statement']
        repo_structure = subprocess.check_output(["find", ".", "-maxdepth", "2", "-not", "-path", "'*/.*'"], cwd=repo_dir, text=True)
        
        params = {
            "beliefs": f"Repo Structure:\n{repo_structure}\n\nCurrent Test Status: Unknown (assumed failing)",
            "desire": f"Fix the following issue:\n{issue_desc}\n\nThe fix should pass the tests."
        }
        
        print("Generating Plan...")
        prediction = self.planner.forward(beliefs=params['beliefs'], desire=params['desire'])
        plan = prediction.plan
        
        print(f"Plan generated with {len(plan.nodes)} steps.")
        
        # 3. Execution
        self.execute_plan(plan, repo_dir, issue_desc)
        
        # 4. Final Verification
        # Construct test command.
        # SWE-bench instance has 'test_patch' which is the test file.
        # And 'test_cmd' is not always explicit in the dataset object, sometimes it calls a script.
        # But 'FAIL_TO_PASS' field lists the failing tests.
        
        # We try to run the testing script provided or just pytest
        # The environment setup is the trickiest part locally.
        
        print("Final Verification...")
        # Placeholder for test command - assumes local environment is compatible-ish
        # We simply list the files changed as a "result"
        changed_files = subprocess.check_output(["git", "diff", "--name-only"], cwd=repo_dir, text=True)
        print(f"Changed files:\n{changed_files}")
        
        return {
            "instance_id": instance_id,
            "plan_steps": len(plan.nodes),
            "changed_files": changed_files.splitlines()
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, required=True, help="Instance ID to run")
    args = parser.parse_args()
    
    harness = LocalSWEBenchHarness()
    result = harness.run_instance(args.instance)
    print(result)
