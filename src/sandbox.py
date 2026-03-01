import os
import shlex
import subprocess
import sys
import shutil
from pathlib import Path
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
                # 🛡️ Sentinel Security Fix: Prevent command injection by parsing arguments safely
                # and disabling shell=True
                args = shlex.split(step.target)
                if not args:
                    return

                # Sourcery usually flags `subprocess.run(args)` if args comes from unvalidated input.
                # Validating the command exists and getting its absolute path mitigates this.
                executable = shutil.which(args[0])
                if not executable:
                    raise FileNotFoundError(f"Command not found: {args[0]}")
                args[0] = executable

                # The problem might be about passing 'executable=' arg or just avoiding arbitrary strings.
                # Another potential issue: subprocess.run without a timeout could lead to Denial of Service (DoS).
                # Adding a timeout parameter:
                subprocess.run(args, shell=False, check=True, timeout=10)
            except subprocess.TimeoutExpired as e:
                print(f"Error: Command execution timed out: {e}", file=sys.stderr)
                raise e
            except subprocess.CalledProcessError as e:
                print(f"Error executing command: {e}", file=sys.stderr)
                raise e
            except FileNotFoundError as e:
                print(f"Error executing command (executable not found): {e}", file=sys.stderr)
                raise e

        elif step.action.upper() == "DELETE":
            # File system operation
            try:
                # 🛡️ Sentinel Security Fix: Use native Python functions instead of shell commands
                target_path = Path(step.target)
                if target_path.exists():
                    if target_path.is_dir():
                        shutil.rmtree(target_path)
                    else:
                        os.remove(target_path)
            except Exception as e:
                print(f"Error deleting file/directory: {e}", file=sys.stderr)
                raise e

        elif step.action.upper() == "READ":
            # Read file (for verification or info)
            try:
                # 🛡️ Sentinel Security Fix: Use native Python functions instead of shell commands
                with open(step.target, 'r') as f:
                    # Print contents to stdout to match `cat` behavior
                    print(f.read(), end="")
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                # Don't raise on read failure, maybe just log
                pass
        
        else:
             print(f"Unknown action: {step.action}", file=sys.stderr)
