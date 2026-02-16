import sys
import os

# Add src to python path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.verifier import PlanVerifier

def main():
    print("Initializing BDI Planner with DSPy...")

    # Define a scenario
    beliefs = """
    Location: Living Room.
    Inventory: None.
    Environment:
    - Door to Kitchen is closed.
    - Keys are on the Table in the Living Room.
    - Robot is at coordinate (0,0).
    Available Skills: [PickUp, MoveTo, OpenDoor, UnlockDoor]
    """
    desire = "Go to the Kitchen."

    planner = BDIPlanner()

    print(f"\nGoal: {desire}")
    print("Generating Plan...")

    try:
        # Run the planner
        # dspy.Suggest/Assert will automatically retry if validation fails
        response = planner(beliefs=beliefs, desire=desire)
        final_plan = response.plan

        print("\n✅ Plan Generated Successfully!")
        print(f"Goal Description: {final_plan.goal_description}")

        print("\n--- Actions (Nodes) ---")
        for node in final_plan.nodes:
            print(f"[{node.id}] {node.action_type}: {node.description}")

        print("\n--- Dependencies (Edges) ---")
        for edge in final_plan.edges:
            print(f"{edge.source} -> {edge.target}")

        # Verify final result
        G = final_plan.to_networkx()
        print(f"\nFinal Graph Valid? {PlanVerifier.verify(G)[0]}")

        if PlanVerifier.verify(G)[0]:
            print("\nExecution Order:")
            print(" -> ".join(PlanVerifier.topological_sort(G)))

    except ValueError as e:
        print(f"\n❌ Planning Failed: {e}")

if __name__ == "__main__":
    main()
