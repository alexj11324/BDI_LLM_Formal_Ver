import dspy
from typing import List
import networkx as nx
from .schemas import BDIPlan
from .verifier import PlanVerifier

from .config import Config

# 1. Configure DSPy
# Ensure configuration is valid before proceeding
Config.validate()

lm = dspy.LM(
    model=Config.MODEL_NAME,
    max_tokens=Config.MAX_TOKENS,
    api_key=Config.OPENAI_API_KEY,  # Explicitly pass key if needed by dspy adapter
    api_base=Config.OPENAI_API_BASE  # Can be None, DSPy handles it
)
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

    6. **Explicit Teardown**:
       If the beliefs say a block is stacked but the goal requires moving it, you MUST explicitly unstack it first.
       Do NOT skip unstack/put-down steps.
       Example: If A is on B, and you need A on C:
         1. unstack A B
         2. put-down A
         3. pick-up A
         4. stack A C

    EXAMPLE CORRECT STRUCTURE (Blocksworld, stack 3 blocks):
    Nodes: [pick_a, stack_a_b, pick_c, stack_c_a]
    Edges: [(pick_a, stack_a_b), (stack_a_b, pick_c), (pick_c, stack_c_a)]
    This forms a connected chain: pick_a → stack_a_b → pick_c → stack_c_a

    EXAMPLE WRONG STRUCTURE:
    Nodes: [pick_a, stack_a_b, pick_c, stack_c_d]
    Edges: [(pick_a, stack_a_b), (pick_c, stack_c_d)]
    This is WRONG because {pick_a, stack_a_b} and {pick_c, stack_c_d} are disconnected!

    Always ensure your plan forms ONE connected graph, not multiple fragments.

    DOMAIN-SPECIFIC ACTION TYPE CONSTRAINTS:

    **BLOCKSWORLD** (blocksworld-4ops):
      action_type must be one of: pick-up | put-down | stack | unstack
      params:
        pick-up / put-down : {"block": <block>}
        stack / unstack    : {"block": <block>, "target": <block>}
      check-before-act preconditions (MUST be true before choosing an action):
        pick-up : block is clear, block is on the table, and hand is empty
        put-down: hand is holding the block
        unstack : block is clear, block is on target, and hand is empty
        stack   : hand is holding the block, and target is clear
      worked example (initial stacks exist):
        beliefs: on(a,b), on(b,table), clear(a), clear(c), on(c,table), handempty
        goal: on(a,c)
        valid action chain:
          unstack(a,b) → put-down(a) → pick-up(a) → stack(a,c)

    **LOGISTICS** (logistics-strips):
      action_type must be one of:
        load-truck | unload-truck | load-airplane | unload-airplane |
        drive-truck | fly-airplane
      params:
        load-truck / unload-truck       : {"obj": <obj>, "truck": <truck>, "location": <loc>}
        load-airplane / unload-airplane : {"obj": <obj>, "airplane": <airplane>, "location": <loc>}
        drive-truck                     : {"truck": <truck>, "from": <loc>, "to": <loc>, "city": <city>}
        fly-airplane                    : {"airplane": <airplane>, "from": <airport>, "to": <airport>}

    **DEPOTS** (depots):
      action_type must be one of: drive | lift | drop | load | unload
      params:
        drive  : {"truck": <truck>, "from": <place>, "to": <place>}
        lift   : {"hoist": <hoist>, "crate": <crate>, "surface": <surface>, "place": <place>}
        drop   : {"hoist": <hoist>, "crate": <crate>, "surface": <surface>, "place": <place>}
        load   : {"hoist": <hoist>, "crate": <crate>, "truck": <truck>, "place": <place>}
        unload : {"hoist": <hoist>, "crate": <crate>, "truck": <truck>, "place": <place>}

    Do NOT invent action types outside the set for the relevant domain.
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
