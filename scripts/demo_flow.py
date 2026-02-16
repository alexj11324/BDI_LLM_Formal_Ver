import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

from src.mcp_server import apply_verified_changes, PlanInput, PlanStepModel

def run_demo():
    print("=== BDI Verification System Demo ===\n")

    # Scenario 1: Unsafe Plan (Deleting Critical File)
    print("--- Scenario 1: Attempting to DELETE src/core/main.py ---")
    unsafe_plan = PlanInput(
        steps=[PlanStepModel(action="DELETE", target="src/core/main.py")],
        rationale="I want to destroy the core."
    )
    result_1 = apply_verified_changes(unsafe_plan)
    print(f"Result:\n{result_1}\n")

    # Scenario 2: Safe Plan (Reading README)
    print("--- Scenario 2: Attempting to READ README.md ---")
    safe_plan = PlanInput(
        steps=[PlanStepModel(action="READ", target="README.md")],
        rationale="Checking documentation."
    )
    result_2 = apply_verified_changes(safe_plan)
    print(f"Result:\n{result_2}\n")

if __name__ == "__main__":
    run_demo()
