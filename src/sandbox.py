import subprocess
import sys
import shutil
from typing import List
from .constraints import PlanStep

class Sandbox:
    def __init__(self):
        self.has_docker = shutil.which("docker") is not None
        if not self.has_docker:
            print("WARNING: Docker not found. Falling back to local subprocess execution (UNSAFE).", file=sys.stderr)

    def execute_plan(self, steps: List[PlanStep]):
        """
        Executes a sequence of steps.
        If Docker is available, should run inside a container.
        For this prototype, we'll focus on the local fallback since Docker is missing.
        """
        for step in steps:
            self._execute_step(step)

    def _execute_step(self, step: PlanStep):
        print(f"Executing: {step.action} {step.target}")
        
        if step.action.upper() == "EXECUTE":
            # Direct shell command
            # Security Note: In a real system, this MUST run in Docker.
            try:
                subprocess.run(step.target, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error executing command: {e}", file=sys.stderr)
                raise e

        elif step.action.upper() == "DELETE":
            # File system operation
            try:
                subprocess.run(f"rm -rf {step.target}", shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error deleting file: {e}", file=sys.stderr)
                raise e

        elif step.action.upper() == "READ":
            # Read file (for verification or info)
            try:
                subprocess.run(f"cat {step.target}", shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                # Don't raise on read failure, maybe just log
                pass
        
        else:
             print(f"Unknown action: {step.action}", file=sys.stderr)
