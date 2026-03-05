"""Shared prompt constants used across DSPy Signatures for BDI planning."""

_GRAPH_STRUCTURE_COMMON = """    CRITICAL GRAPH STRUCTURE REQUIREMENTS:

    1. **CONNECTIVITY**: The plan graph MUST be weakly connected.
       ALL action nodes must be reachable from each other via edges.
       There should be NO disconnected "islands" or separate subgraphs.

    2. **DAG (Directed Acyclic Graph)**: No cycles allowed.
       If action A → B → C, then C cannot have an edge back to A or B.
       After generating your plan, VERIFY: "Does any action appear twice in the execution order?" If YES, remove the duplicate.

    3. **Sequential Chain**: Each action depends on the previous one completing.
       All actions form one connected chain/path.

    4. **EXACTLY ONCE EXECUTION**: Each action appears EXACTLY ONCE in the plan.
       Before finalizing, COUNT: "How many times does each action appear?" Every action must have count = 1.

    5. **NO RETURN TO PREVIOUS STATES**: Once a state change occurs (e.g., block moved, truck driven),
       you CANNOT return to the exact previous configuration. This prevents cycles."""

_STATE_TRACKING_HEADER = """    ═══════════════════════════════════════════════════════════════════════════
    CRITICAL: STATE TRACKING AND LOGICAL VERIFICATION (P0 Requirements)
    ═══════════════════════════════════════════════════════════════════════════

    You MUST use explicit state tracking and logical verification to avoid common
    planning errors. This is MANDATORY.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ P0-1: EXPLICIT STATE TRACKING                                           │
    └─────────────────────────────────────────────────────────────────────────┘

    Maintain a STATE TABLE throughout planning. Update it after EVERY action."""

_COS_REPRESENTATION_HEADER = """    ┌─────────────────────────────────────────────────────────────────────────┐
    │ P0-2: CHAIN-OF-SYMBOL (CoS) REPRESENTATION                             │
    └─────────────────────────────────────────────────────────────────────────┘

    Use symbolic notation for clarity:"""

_LOGICOT_HEADER = """    ┌─────────────────────────────────────────────────────────────────────────┐
    │ P0-3: LOGICAL CHAIN-OF-THOUGHT (LogiCoT) PROTOCOL                      │
    └─────────────────────────────────────────────────────────────────────────┘

    For EVERY action, follow this 4-step verification protocol:"""

_LOGICOT_PROTOCOL_DETAILED = """    **Step 1: Identify Goal**
    What are you trying to achieve with this action?

    **Step 2: List Preconditions**
    What conditions MUST be true for this action to be valid?

    **Step 3: Check Current State**
    For each precondition, check against your state table:
    - ✓ Condition satisfied
    - ✗ Condition NOT satisfied → explain why

    **Step 4: Decision**
    - If ALL preconditions satisfied → Select this action
    - If ANY precondition NOT satisfied → Find prerequisite actions first"""

_REMINDER = "    REMEMBER: State tracking is NOT optional. It is MANDATORY for correct planning."
