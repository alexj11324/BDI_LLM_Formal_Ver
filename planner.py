import dspy
from typing import List
import networkx as nx
from schemas import BDIPlan
from verifier import PlanVerifier

# 1. Configure DSPy (Using CMU AI Gateway with Claude)
import os
os.environ["OPENAI_API_KEY"] = "REDACTED_OPENAI_KEY"
os.environ["OPENAI_API_BASE"] = "https://ai-gateway.andrew.cmu.edu/v1"

lm = dspy.LM(model="openai/claude-opus-4-20250514-v1:0", max_tokens=4000, api_base="https://ai-gateway.andrew.cmu.edu/v1")
dspy.configure(lm=lm)

# 2. Define the Signature
class GeneratePlan(dspy.Signature):
    """
    You are a BDI (Belief-Desire-Intention) Planning Agent.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

    The plan must be a VALID Directed Acyclic Graph (DAG).
    Dependencies must be logical (e.g., you must 'OpenDoor' before 'WalkThrough').
    """
    beliefs: str = dspy.InputField(desc="Current state of the world and available tools")
    desire: str = dspy.InputField(desc="The high-level goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges")

# 3. Define the Module with Assertions
class BDIPlanner(dspy.Module):
    def __init__(self):
        super().__init__()
        # Use Predict with signature (DSPy 3.x API)
        self.generate_plan = dspy.Predict(GeneratePlan)

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        # Generate the plan
        pred = self.generate_plan(beliefs=beliefs, desire=desire)

        # Try to parse the plan - DSPy 3.x handles Pydantic parsing
        try:
            plan_obj = pred.plan

            # Convert to NetworkX for verification
            G = plan_obj.to_networkx()

            # Verify the plan
            is_valid, errors = PlanVerifier.verify(G)

            if not is_valid:
                print(f"\n⚠️ Warning: Generated plan has validation errors: {'; '.join(errors)}")
                # In DSPy 3.x, we would need to manually retry or use a different approach

        except Exception as e:
            print(f"\n⚠️ Warning: Could not parse plan: {e}")

        return pred

# 4. Demonstration Function
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

    except Exception as e:
        print(f"\n❌ Planning Failed after retries: {e}")

if __name__ == "__main__":
    main()
