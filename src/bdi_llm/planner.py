import dspy
from typing import List
import networkx as nx
from .schemas import BDIPlan
from .verifier import PlanVerifier

# 1. Configure DSPy (Using CMU AI Gateway with Claude)
import os

# Load API key from environment variable (never hardcode secrets!)
# Set via: export OPENAI_API_KEY=your-key-here
# Or use a .env file with python-dotenv
API_KEY = os.environ.get("OPENAI_API_KEY")
API_BASE = os.environ.get("OPENAI_API_BASE", "https://ai-gateway.andrew.cmu.edu/v1")

if not API_KEY:
    raise ValueError(
        "OPENAI_API_KEY environment variable is not set. "
        "Please set it before running the planner:\n"
        "  export OPENAI_API_KEY=your-api-key-here"
    )

lm = dspy.LM(model="openai/gpt-4o-2024-05-13", max_tokens=4000, api_base=API_BASE)
dspy.configure(lm=lm)

# 2. Define the Signature
class GeneratePlan(dspy.Signature):
    """
    You are a BDI (Belief-Desire-Intention) Planning Agent.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

    CRITICAL GRAPH STRUCTURE REQUIREMENTS:

    1. **CONNECTIVITY**: The plan graph MUST be weakly connected.
       ALL action nodes must be reachable from each other via edges.
       There should be NO disconnected "islands" or separate subgraphs.

    2. **DAG (Directed Acyclic Graph)**: No cycles allowed.
       If action A depends on B, and B depends on C, then C cannot depend on A.

    3. **Single Goal**: All actions should ultimately contribute to the goal.
       Every action should have a path connecting it to the goal state.

    4. **Fork-Join Pattern for Parallel Actions**:
       If multiple actions can happen in parallel, structure them as:
       ```
       START → [Action A, Action B, Action C] → SYNC_POINT → END
       ```
       NOT as disconnected islands:
       ```
       [Action A → Action A2]  [Action B → Action B2]  (WRONG: disconnected!)
       ```

    5. **Sequential Chain for Sequential Actions**:
       For Blocksworld: To stack A on B, then B on C:
       ```
       pick_up_A → stack_A_on_B → pick_up_B → stack_B_on_C
       ```
       Each action depends on the previous one completing.

    EXAMPLE CORRECT STRUCTURE (Blocksworld, stack 3 blocks):
    Nodes: [pick_a, stack_a_b, pick_c, stack_c_a]
    Edges: [(pick_a, stack_a_b), (stack_a_b, pick_c), (pick_c, stack_c_a)]
    This forms a connected chain: pick_a → stack_a_b → pick_c → stack_c_a

    EXAMPLE WRONG STRUCTURE:
    Nodes: [pick_a, stack_a_b, pick_c, stack_c_d]
    Edges: [(pick_a, stack_a_b), (pick_c, stack_c_d)]
    This is WRONG because {pick_a, stack_a_b} and {pick_c, stack_c_d} are disconnected!

    Always ensure your plan forms ONE connected graph, not multiple fragments.

    ACTION TYPE CONSTRAINTS (Blocksworld domain):

    Each action node's `action_type` MUST be one of:
      pickup | putdown | stack | unstack
      (aliases pick-up / put-down are also accepted)

    Each action node's `params` dict MUST include:
      - "block": the block being manipulated (required for ALL actions)
      - "target": the destination block (required ONLY for stack and unstack)

    Do NOT invent action types outside this set.
    """
    beliefs: str = dspy.InputField(desc="Current state of the world and available tools")
    desire: str = dspy.InputField(desc="The high-level goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges forming a SINGLE CONNECTED DAG")

# 3. Define the Module with Assertions
class BDIPlanner(dspy.Module):
    def __init__(self, auto_repair: bool = True):
        """
        Initialize BDI Planner

        Args:
            auto_repair: If True, automatically repair disconnected plans
        """
        super().__init__()
        # Predict enforces the Pydantic schema (DSPy 3.x)
        self.generate_plan = dspy.Predict(GeneratePlan)
        self.auto_repair = auto_repair

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        # Generate the plan
        pred = self.generate_plan(beliefs=beliefs, desire=desire)

        try:
            plan_obj = pred.plan
            # Convert to NetworkX for verification
            G = plan_obj.to_networkx()

            # Verify the plan
            is_valid, errors = PlanVerifier.verify(G)

            # Try auto-repair if enabled and plan is invalid
            if not is_valid and self.auto_repair:
                from .plan_repair import repair_and_verify
                repaired_plan, repaired_valid, messages = repair_and_verify(plan_obj)

                if repaired_valid:
                    # Update prediction with repaired plan
                    pred.plan = repaired_plan
                    is_valid = True
                    errors = []
                else:
                    # Auto-repair didn't fully fix, but include repair messages
                    errors = errors + [f"Auto-repair attempted: {msg}" for msg in messages]

            # DSPy Assertion: If still invalid, backtrack and retry with the error message
            # This is the "Learning/Optimization" loop in inference time
            dspy.Assert(
                is_valid,
                f"The generated plan is invalid. Errors: {'; '.join(errors)}. Please fix the dependencies to remove cycles or connect the graph. REMEMBER: All nodes must form ONE CONNECTED graph, not separate islands.",
                target_module=self.generate_plan
            )
        except Exception as e:
            # Handle potential pydantic validation errors or parsing issues
            dspy.Assert(
                False,
                f"Failed to generate a valid plan object. Error: {str(e)}",
                target_module=self.generate_plan
            )

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

    except dspy.DSPyAssertionError as e:
        print(f"\n❌ Planning Failed after retries: {e}")

if __name__ == "__main__":
    main()
