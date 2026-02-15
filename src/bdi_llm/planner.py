import dspy
from typing import List
import networkx as nx
from .schemas import BDIPlan, ActionNode, DependencyEdge
from .verifier import PlanVerifier

from .config import Config

# 1. Configure DSPy
# Ensure configuration is valid before proceeding
Config.validate()

# Check if model is a reasoning model (gpt-5, o1, etc.)
is_reasoning_model = any(model_type in Config.MODEL_NAME.lower()
                         for model_type in ['gpt-5', 'o1', 'o3'])

# Check if model is a Gemini model
is_gemini_model = 'gemini' in Config.MODEL_NAME.lower()

# Check if model uses Vertex AI (vertex_ai/ prefix)
is_vertex_ai = Config.MODEL_NAME.lower().startswith('vertex_ai/')

# Prepare LM configuration based on model type
lm_config = {
    'model': Config.MODEL_NAME,
}

# Add API key based on model type
# Vertex AI models use service account credentials via env vars (no api_key needed)
if is_vertex_ai:
    pass  # litellm reads GOOGLE_APPLICATION_CREDENTIALS, VERTEXAI_PROJECT, VERTEXAI_LOCATION from env
elif is_gemini_model and Config.GOOGLE_API_KEY:
    lm_config['api_key'] = Config.GOOGLE_API_KEY
elif Config.OPENAI_API_KEY:
    lm_config['api_key'] = Config.OPENAI_API_KEY
    if Config.OPENAI_API_BASE:
        lm_config['api_base'] = Config.OPENAI_API_BASE

# Add model-specific parameters
if is_reasoning_model:
    # Reasoning models require temperature=1.0 and max_tokens >= 16000
    lm_config['temperature'] = 1.0
    lm_config['max_tokens'] = 16000
else:
    # Standard models use configured temperature for deterministic output
    lm_config['temperature'] = Config.TEMPERATURE
    lm_config['max_tokens'] = Config.MAX_TOKENS

# Add max_tokens for gemini models
if 'gemini' in Config.MODEL_NAME.lower() or 'vertex_ai' in Config.MODEL_NAME.lower():
    lm_config['max_tokens'] = 16000

# Add timeout and retry settings for rate limiting and reliability
lm_config['timeout'] = 120  # 2 minute timeout per API call
lm_config['num_retries'] = 5  # more retries for rate limiting

lm = dspy.LM(**lm_config)
dspy.configure(lm=lm)

# 2. Define the Signature

_GRAPH_STRUCTURE_COMMON = """    CRITICAL GRAPH STRUCTURE REQUIREMENTS:

    1. **CONNECTIVITY**: The plan graph MUST be weakly connected.
       ALL action nodes must be reachable from each other via edges.
       There should be NO disconnected "islands" or separate subgraphs.

    2. **DAG (Directed Acyclic Graph)**: No cycles allowed.

    3. **Sequential Chain**: Each action depends on the previous one completing.
       All actions form one connected chain/path."""

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

class GeneratePlan(dspy.Signature):
    __doc__ = f"""
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
    This is WRONG because {{pick_a, stack_a_b}} and {{pick_c, stack_c_d}} are disconnected!

    Always ensure your plan forms ONE connected graph, not multiple fragments.

    BLOCKSWORLD ACTION TYPE CONSTRAINTS:

    action_type must be one of: pick-up | put-down | stack | unstack
    params:
      pick-up / put-down : {{"block": <block>}}
      stack / unstack    : {{"block": <block>, "target": <block>}}
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

    Do NOT invent action types outside this set.

{_STATE_TRACKING_HEADER}

    **BLOCKSWORLD State Table Format:**
    ```
    | Block | Position | Clear? | Hand |
    |-------|----------|--------|------|
    | a | on(b) | yes | empty |
    | b | table | no | empty |
    | c | table | yes | empty |
    ```

    **State Update Rules:**
    1. Initialize state table from problem description
    2. Before each action: Check current state, verify preconditions
    3. After each action: Update affected blocks, mark with [UPDATED]
    4. Track: block positions, clear status, hand state

{_COS_REPRESENTATION_HEADER}

    **Symbolic State Format:**
    - on(X,Y): block X is on block Y
    - ontable(X): block X is on the table
    - clear(X): nothing is on top of X
    - holding(X): hand is holding X
    - handempty: hand is empty

    **Example:**
    - Initial: on(a,b), ontable(b), ontable(c), clear(a), clear(c), handempty
    - After unstack(a,b): holding(a), clear(b), ontable(b), ontable(c), clear(c)
    - After put-down(a): ontable(a), clear(a), ontable(b), clear(b), ontable(c), clear(c), handempty

{_LOGICOT_HEADER}

{_LOGICOT_PROTOCOL_DETAILED}

    ═══════════════════════════════════════════════════════════════════════════
    WORKED EXAMPLE WITH STATE TRACKING
    ═══════════════════════════════════════════════════════════════════════════

    **Problem:**
    - on(a,b), ontable(b), ontable(c), clear(a), clear(c), handempty
    - Goal: on(a,c)

    **Initial State Table:**
    ```
    | Block | Position | Clear? | Hand |
    |-------|----------|--------|------|
    | a | on(b) | yes | empty |
    | b | table | no | empty |
    | c | table | yes | empty |
    ```

    **Action 1:** unstack(a, b)
    - Preconditions: (1) a clear? ✓ (2) a on b? ✓ (3) handempty? ✓
    - Decision: Valid.
    - State Update:
    ```
    | Block | Position | Clear? | Hand |
    |-------|----------|--------|------|
    | a | holding [UPDATED] | - | holding(a) |
    | b | table | yes [UPDATED] | holding(a) |
    | c | table | yes | holding(a) |
    ```

    **Action 2:** put-down(a)
    - Preconditions: holding(a)? ✓
    - State Update: a on table, clear, handempty

    **Action 3:** pick-up(a)
    - Preconditions: (1) a clear? ✓ (2) a on table? ✓ (3) handempty? ✓
    - State Update: holding(a)

    **Action 4:** stack(a, c)
    - Preconditions: (1) holding(a)? ✓ (2) c clear? ✓
    - State Update: on(a,c), handempty ✓ GOAL ACHIEVED

    ═══════════════════════════════════════════════════════════════════════════

{_REMINDER}
    """
    beliefs: str = dspy.InputField(desc="Current state of the world and available tools")
    desire: str = dspy.InputField(desc="The high-level goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges forming a SINGLE CONNECTED DAG")


class GeneratePlanLogistics(dspy.Signature):
    __doc__ = f"""
    You are a BDI (Belief-Desire-Intention) Planning Agent for the LOGISTICS domain.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

{_GRAPH_STRUCTURE_COMMON}

    LOGISTICS ACTION TYPE CONSTRAINTS:

    action_type must be one of:
      load-truck | unload-truck | load-airplane | unload-airplane |
      drive-truck | fly-airplane

    params:
      load-truck       : {{"obj": <package>, "truck": <truck>, "loc": <location>}}
      unload-truck     : {{"obj": <package>, "truck": <truck>, "loc": <location>}}
      load-airplane    : {{"obj": <package>, "airplane": <airplane>, "loc": <airport>}}
      unload-airplane  : {{"obj": <package>, "airplane": <airplane>, "loc": <airport>}}
      drive-truck      : {{"truck": <truck>, "from": <location>, "to": <location>, "city": <city>}}
      fly-airplane     : {{"airplane": <airplane>, "from": <airport>, "to": <airport>}}

    ═══════════════════════════════════════════════════════════════════════════
    ⚠️⚠️⚠️ #1 FAILURE CAUSE: AIRPORT IDENTIFICATION ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════════════════════════

    NOT all locations are airports! The beliefs will list which locations are
    AIRPORTS. fly-airplane and load/unload-airplane can ONLY use AIRPORT
    locations. Using a non-airport location will FAIL.

    BEFORE every fly-airplane or load/unload-airplane action, CHECK:
      "Is this location listed as an AIRPORT in the beliefs?"
      If NO → you CANNOT use it. Find the correct airport for that city.

    ═══════════════════════════════════════════════════════════════════════════
    CHECK-BEFORE-ACT PRECONDITIONS (MUST be true before choosing an action):
    ═══════════════════════════════════════════════════════════════════════════

    load-truck(obj, truck, loc):
      - obj is at loc (package and truck must be at the SAME location)
      - truck is at loc
      → Effect: obj is IN truck, obj is no longer at loc

    unload-truck(obj, truck, loc):
      - obj is IN truck
      - truck is at loc
      → Effect: obj is at loc, obj is no longer in truck

    load-airplane(obj, airplane, loc):
      - loc MUST be an AIRPORT
      - obj is at loc (package and airplane must be at the SAME airport)
      - airplane is at loc
      → Effect: obj is IN airplane, obj is no longer at loc

    unload-airplane(obj, airplane, loc):
      - loc MUST be an AIRPORT
      - obj is IN airplane
      - airplane is at loc
      → Effect: obj is at loc, obj is no longer in airplane

    drive-truck(truck, from, to, city):
      - truck is at 'from' location
      - 'from' and 'to' are both in the SAME city
      → Effect: truck is at 'to', truck is no longer at 'from'

    fly-airplane(airplane, from, to):
      - BOTH 'from' and 'to' MUST be AIRPORTS
      - airplane is at 'from' airport
      → Effect: airplane is at 'to', airplane is no longer at 'from'

    Do NOT invent action types outside this set.

    ═══════════════════════════════════════════════════════════════════════════
    CRITICAL: AIRPLANE POSITION TRACKING (#2 FAILURE CAUSE)
    ═══════════════════════════════════════════════════════════════════════════

    After EVERY fly-airplane action, the airplane is at the DESTINATION airport
    and NO LONGER at the origin. You MUST update your state table immediately.

    RULE: Before ANY load-airplane or unload-airplane, ASK YOURSELF:
      "Where is this airplane RIGHT NOW?" — check your state table!

    Example of CORRECT tracking:
      State: a0 at l0-0 (airport)
      Action: fly-airplane(a0, l0-0, l1-0)
      State: a0 at l1-0 ← a0 MOVED!
      Action: unload-airplane(p1, a0, l1-0) ← CORRECT: uses a0's current location
      ❌ WRONG: load-airplane(p2, a0, l0-0) ← WRONG: a0 is no longer at l0-0!

{_STATE_TRACKING_HEADER}

    **LOGISTICS State Table Format:**
    ```
    | Object | Type | Location | In/Carrying | IsAirport? |
    |--------|------|----------|-------------|------------|
    | p1 | package | l0-1 | - | - |
    | t0 | truck | l0-2 | [] | - |
    | a0 | airplane | l0-0 | [] | YES |
    ```

{_LOGICOT_HEADER}

    **Step 1: Identify Goal** — What are you trying to achieve?
    **Step 2: List Preconditions** — What MUST be true?
    **Step 3: Check Current State** — ✓ satisfied / ✗ NOT satisfied
      - For fly/load/unload-airplane: Is the location an AIRPORT? ✓/✗
    **Step 4: Decision** — ALL satisfied → proceed; ANY failed → fix first

    ═══════════════════════════════════════════════════════════════════════════
    COMMON ERROR PATTERNS TO AVOID
    ═══════════════════════════════════════════════════════════════════════════

    ❌ ERROR 1: Flying to non-airport location (MOST COMMON!)
    - Wrong: fly-airplane(a0, l0-0, l1-2) when l1-2 is NOT an airport
    - Right: Check beliefs for AIRPORT list. Only fly between airports.

    ❌ ERROR 2: Forgetting airplane position after flying
    - Wrong: fly-airplane(a0, l0-0, l1-0) then load-airplane(p2, a0, l0-0)
    - Right: After fly, a0 is at l1-0, NOT l0-0.

    ❌ ERROR 3: Forgetting truck position after driving
    - Wrong: drive-truck(t1, l0-0, l0-1, c0) then load-truck(p1, t1, l0-0)
    - Right: After drive, t1 is at l0-1, NOT l0-0.

    ❌ ERROR 4: Loading at wrong location
    - Wrong: load-truck(p1, t1, l0-1) when t1 is at l0-2
    - Right: Vehicle and package must be at SAME location.

    ❌ ERROR 5: Driving truck between cities
    - Wrong: drive-truck(t1, l0-1, l1-2, c0)
    - Right: Trucks can only drive within ONE city. Use airplane for inter-city.

    ═══════════════════════════════════════════════════════════════════════════

{_REMINDER}
    """
    beliefs: str = dspy.InputField(desc="Current state of the logistics world")
    desire: str = dspy.InputField(desc="The logistics goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges forming a SINGLE CONNECTED DAG")


class GeneratePlanDepots(dspy.Signature):
    __doc__ = f"""
    You are a BDI (Belief-Desire-Intention) Planning Agent for the DEPOTS domain.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

{_GRAPH_STRUCTURE_COMMON}

    DEPOTS ACTION TYPE CONSTRAINTS:

    action_type must be one of: drive | lift | drop | load | unload

    params:
      drive  : {{"truck": <truck>, "from": <place>, "to": <place>}}
      lift   : {{"hoist": <hoist>, "crate": <crate>, "surface": <surface>, "place": <place>}}
      drop   : {{"hoist": <hoist>, "crate": <crate>, "surface": <surface>, "place": <place>}}
      load   : {{"hoist": <hoist>, "crate": <crate>, "truck": <truck>, "place": <place>}}
      unload : {{"hoist": <hoist>, "crate": <crate>, "truck": <truck>, "place": <place>}}

    ═══════════════════════════════════════════════════════════════════════════
    CHECK-BEFORE-ACT PRECONDITIONS (MUST be true before choosing an action):
    ═══════════════════════════════════════════════════════════════════════════

    drive(truck, from, to):
      - truck is at 'from' place
      → Effect: truck is at 'to', truck is no longer at 'from'

    lift(hoist, crate, surface, place):
      - hoist is AVAILABLE (not lifting anything)
      - crate is ON surface (pallet or another crate)
      - crate is CLEAR (nothing on top of it)
      - hoist is at place, crate is at place, surface is at place (all at SAME place)
      → Effect: hoist is LIFTING crate (no longer available), crate is no longer on surface, surface becomes CLEAR

    drop(hoist, crate, surface, place):
      - hoist is LIFTING crate
      - surface is CLEAR (nothing on top of it)
      - hoist is at place, surface is at place (all at SAME place)
      → Effect: crate is ON surface, hoist is AVAILABLE, crate becomes CLEAR, surface is no longer clear

    load(hoist, crate, truck, place):
      - hoist is LIFTING crate
      - truck is at place
      - hoist is at place (all at SAME place)
      → Effect: crate is IN truck, hoist is AVAILABLE

    unload(hoist, crate, truck, place):
      - hoist is AVAILABLE (not lifting anything)
      - crate is IN truck
      - truck is at place
      - hoist is at place (all at SAME place)
      → Effect: hoist is LIFTING crate, crate is no longer in truck

    Do NOT invent action types outside this set.
    ❌ DO NOT use blocksworld actions: pick-up, put-down, stack, unstack

{_STATE_TRACKING_HEADER}

    **DEPOTS State Table Format:**
    ```
    | Object | Type | Location | On/In | Carrying | Available |
    |--------|------|----------|-------|----------|-----------|
    | h1 | hoist | depot1 | - | - | available |
    | c1 | crate | depot1 | pallet1 | - | - |
    | t1 | truck | depot1 | - | [] | empty |
    | pallet1 | pallet | depot1 | - | - | occupied |
    ```

    **State Update Rules:**
    1. Initialize state table from problem description
    2. Before each action: Check current state, verify ALL preconditions
    3. After each action: Update affected objects, mark with [UPDATED]
    4. Track: hoist state (available/lifting), crate positions, truck contents, surface clear status

{_COS_REPRESENTATION_HEADER}

    - [hoist, available] or [hoist, lifting=crate1]
    - [crate@surface] means "crate is on surface"
    - [crate@truck] means "crate is in truck"
    - [surface, clear] or [surface, occupied]

    **Example:**
    - Initial: [h1, available], [c1@pallet1], [pallet1, occupied]
    - After lift(h1, c1, pallet1, depot1): [h1, lifting=c1], [pallet1, clear]
    - After load(h1, c1, t1, depot1): [h1, available], [c1@t1]

{_LOGICOT_HEADER}

{_LOGICOT_PROTOCOL_DETAILED}

    ═══════════════════════════════════════════════════════════════════════════
    WORKED EXAMPLE WITH STATE TRACKING
    ═══════════════════════════════════════════════════════════════════════════

    **Problem:**
    - crate0 on pallet0 at depot0, crate1 on pallet1 at distributor0
    - hoist0 available at depot0, hoist1 available at distributor0
    - truck0 at depot0
    - Goal: crate0 on crate1 at distributor0

    **Initial State Table:**
    ```
    | Object | Type | Location | On/In | Carrying | Available |
    |--------|------|----------|-------|----------|-----------|
    | c0 | crate | depot0 | pallet0 | - | clear |
    | c1 | crate | distributor0 | pallet1 | - | clear |
    | h0 | hoist | depot0 | - | - | available |
    | h1 | hoist | distributor0 | - | - | available |
    | t0 | truck | depot0 | - | [] | empty |
    | pallet0 | pallet | depot0 | - | - | occupied |
    | pallet1 | pallet | distributor0 | - | - | occupied |
    ```

    **Action 1:** lift(h0, c0, pallet0, depot0)
    - Preconditions: (1) h0 available? ✓ (2) c0 on pallet0? ✓ (3) c0 clear? ✓ (4) all at depot0? ✓
    - State Update: h0 LIFTING c0 [UPDATED], pallet0 CLEAR [UPDATED]
    - ⚠️ h0 is now BUSY — cannot lift another crate!

    **Action 2:** load(h0, c0, t0, depot0)
    - Preconditions: (1) h0 lifting c0? ✓ (2) t0 at depot0? ✓ (3) h0 at depot0? ✓
    - State Update: c0 IN t0 [UPDATED], h0 AVAILABLE [UPDATED]
    - ⚠️ h0 is now AVAILABLE again (released c0 into truck)

    **Action 3:** drive(t0, depot0, distributor0)
    - Preconditions: (1) t0 at depot0? ✓
    - State Update: t0 at distributor0 [UPDATED]
    - ⚠️ t0 is now at distributor0, NOT depot0!

    **Action 4:** unload(h1, c0, t0, distributor0)
    - Preconditions: (1) h1 available? ✓ (2) c0 in t0? ✓ (3) t0 at distributor0? ✓ (4) h1 at distributor0? ✓
    - State Update: h1 LIFTING c0 [UPDATED], c0 no longer in t0 [UPDATED]
    - ⚠️ h1 is now BUSY (lifting c0)

    **Action 5:** drop(h1, c0, c1, distributor0)
    - Preconditions: (1) h1 lifting c0? ✓ (2) c1 clear? ✓ (3) h1 at distributor0? ✓ (4) c1 at distributor0? ✓
    - State Update: c0 ON c1 [UPDATED], h1 AVAILABLE [UPDATED], c0 CLEAR, c1 NOT clear
    - ✓ GOAL ACHIEVED: crate0 on crate1 at distributor0

    ═══════════════════════════════════════════════════════════════════════════
    ⚠️⚠️⚠️ TRUCK LOCATION TRACKING (CRITICAL — #1 CAUSE OF FAILURES) ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════════════════════════

    After EVERY drive(truck, from, to) action, the truck is at 'to' and NO
    LONGER at 'from'. You MUST update your state table immediately.

    RULE: Before ANY load or unload action involving a truck, ASK YOURSELF:
      "Where is this truck RIGHT NOW?" — check your state table!

    Example of CORRECT tracking:
      State: t0 at depot0, t2 at depot1
      Action: drive(t2, depot1, distributor0)
      State: t0 at depot0, t2 at distributor0 ← t2 MOVED!
      Action: load(h1, c1, t2, distributor0) ← CORRECT: uses t2's current location
      ❌ WRONG: load(h1, c1, t2, depot1) ← WRONG: t2 is no longer at depot1!

    If you need to load/unload at a place where the truck is NOT currently
    located, you MUST drive the truck there FIRST.

    ═══════════════════════════════════════════════════════════════════════════
    COMMON ERROR PATTERNS TO AVOID
    ═══════════════════════════════════════════════════════════════════════════

    ❌ ERROR 1: Double-lifting with same hoist
    - Wrong: lift(h0, c0, ...) then lift(h0, c1, ...) immediately
    - Right: After lift, h0 is BUSY. Must drop/load first to make h0 available.

    ❌ ERROR 2: Forgetting truck location after driving (MOST COMMON ERROR!)
    - Wrong: drive(t0, depot0, dist0) then load(h0, c1, t0, depot0)
    - Right: After drive, t0 is at dist0, NOT depot0!
    - Wrong: drive(t2, depot1, dist0) ... later ... load(h1, c1, t2, depot1)
    - Right: t2 is at dist0 after the drive. You CANNOT use t2 at depot1 anymore.
    - ⚠️ EVERY load/unload MUST use the truck's CURRENT location, not its original location.
    - ⚠️ After drive(truck, A, B): truck is at B. ALL subsequent load/unload with this truck must use B.

    ❌ ERROR 3: Dropping onto occupied surface
    - Wrong: drop(h0, c0, pallet0, ...) when pallet0 already has c1 on it
    - Right: Can only drop onto CLEAR surfaces. Lift c1 off first.

    ❌ ERROR 4: Loading without lifting first
    - Wrong: load(h0, c0, t0, depot0) when h0 is available (not lifting c0)
    - Right: Must lift(h0, c0, ...) first, THEN load(h0, c0, t0, ...).

    ❌ ERROR 5: Unloading when hoist is busy
    - Wrong: unload(h0, c0, t0, ...) when h0 is already lifting another crate
    - Right: Hoist must be AVAILABLE to unload. Drop/load current crate first.

    ❌ ERROR 6: Using wrong hoist for location
    - Wrong: unload(h0, c0, t0, dist0) when h0 is at depot0
    - Right: Hoist must be at the SAME place as the truck.

    ═══════════════════════════════════════════════════════════════════════════

{_REMINDER}
    """
    beliefs: str = dspy.InputField(desc="Current state of the depots world")
    desire: str = dspy.InputField(desc="The depots goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges forming a SINGLE CONNECTED DAG")


class RepairPlan(dspy.Signature):
    """You previously generated a plan that failed PDDL validation (VAL).
    The validator found specific errors in your plan.

    Fix the plan by addressing EACH error reported by the validator.

    HOW TO READ VAL ERROR MESSAGES:

    1. **Unsatisfied precondition in action: (action-name args)**
       This means the action cannot execute because required conditions are not met.
       The "VAL Repair Advice" tells you exactly which predicates need to be true.
       Fix: Add prerequisite actions BEFORE this action to establish the missing predicates.

       Example error:
         "Unsatisfied precondition in action: (load-truck p1 t1 loc1)"
         "VAL Repair Advice: (Set (at t1 loc1) to true) and (Set (at p1 loc1) to true)"
       Fix: Add drive-truck to move t1 to loc1 before loading.

    2. **Plan executed but goal not satisfied**
       All actions executed correctly, but the final state doesn't match the goal.
       The "VAL Repair Advice" lists which goal predicates are still missing.
       Fix: Add more actions at the end to achieve the remaining goals.

    3. **Type-checking error**
       Action parameters have wrong types (e.g., using a location where a truck is expected).
       Fix: Check the domain definition and use correct object names for each parameter.

    CRITICAL RULES:
    - Follow ALL the same domain rules and constraints as the original planning task.
    - Generate a COMPLETE corrected plan, not just the changed parts.
    - Ensure the plan forms a SINGLE CONNECTED DAG (no disconnected islands).
    - Use explicit state tracking to verify each action's preconditions are met.
    - Pay close attention to the VAL Repair Advice — it tells you exactly what predicates
      need to be true. Work backwards from those predicates to determine which actions to add.

    REPAIR HISTORY:
    - If repair_history is provided, it contains ALL previous repair attempts and their errors.
    - DO NOT repeat the same mistakes. Each previous attempt failed for specific reasons.
    - Analyze the pattern of failures across attempts to identify the root cause.
    - If the same error keeps recurring, try a fundamentally different approach rather than
      making incremental fixes.
    """
    beliefs: str = dspy.InputField(desc="Current state of the world")
    desire: str = dspy.InputField(desc="The goal to achieve")
    previous_plan: str = dspy.InputField(desc="The plan that failed validation (as PDDL action sequence)")
    val_errors: str = dspy.InputField(desc="Specific validation errors from the PDDL validator (VAL), including which action failed, why, and repair advice")
    repair_history: str = dspy.InputField(desc="History of ALL previous repair attempts and their errors. Empty string if this is the first attempt. Study this to avoid repeating the same mistakes.", default="")
    plan: BDIPlan = dspy.OutputField(desc="Corrected plan fixing the validation errors, as a SINGLE CONNECTED DAG")


# 3. Define the Module with Assertions
class BDIPlanner(dspy.Module):
    def __init__(self, auto_repair: bool = True, domain: str = "blocksworld"):
        """
        Initialize BDI Planner

        Args:
            auto_repair: If True, automatically repair disconnected plans
            domain: Planning domain - selects domain-specific Signature
                    ("blocksworld", "logistics", or "depots")
        """
        super().__init__()
        self.domain = domain

        # Select domain-specific Signature
        if domain == "logistics":
            sig_class = GeneratePlanLogistics
        elif domain == "depots":
            sig_class = GeneratePlanDepots
        else:
            sig_class = GeneratePlan

        self.generate_plan = dspy.ChainOfThought(sig_class)
        self.repair_plan = dspy.ChainOfThought(RepairPlan)
        self.auto_repair = auto_repair

        # Add few-shot demonstrations for Logistics domain
        if domain == "logistics":
            self.generate_plan.demos = self._build_logistics_demos()

        # Domain-specific action constraints for dspy.Assert validation
        self._valid_action_types = {
            "blocksworld": {"pick-up", "put-down", "stack", "unstack"},
            "logistics": {"load-truck", "unload-truck", "load-airplane",
                          "unload-airplane", "drive-truck", "fly-airplane"},
            "depots": {"drive", "lift", "drop", "load", "unload"},
        }
        self._required_params = {
            "blocksworld": {
                "pick-up": {"block"}, "put-down": {"block"},
                "stack": {"block", "target"}, "unstack": {"block", "target"},
            },
            "logistics": {
                "load-truck": {"obj", "truck", "loc"},
                "unload-truck": {"obj", "truck", "loc"},
                "load-airplane": {"obj", "airplane", "loc"},
                "unload-airplane": {"obj", "airplane", "loc"},
                "drive-truck": {"truck", "from", "to", "city"},
                "fly-airplane": {"airplane", "from", "to"},
            },
            "depots": {
                "drive": {"truck", "from", "to"},
                "lift": {"hoist", "crate", "surface", "place"},
                "drop": {"hoist", "crate", "surface", "place"},
                "load": {"hoist", "crate", "truck", "place"},
                "unload": {"hoist", "crate", "truck", "place"},
            },
        }

    @staticmethod
    def _build_logistics_demos():
        """Build few-shot demonstrations for the Logistics domain.

        Uses VAL-verified gold-standard plans from real PlanBench instances:
        - Instance-10: 3 goals, single city (basic truck routing)
        - Instance-116: 6 goals, 2 cities (cross-city transport with airplanes)

        These demonstrate:
        1. Correct sequential truck routing within a city
        2. AIRPORT identification (only airports for fly/load/unload-airplane)
        3. Airplane position tracking after fly-airplane
        4. Multi-vehicle coordination across cities
        """
        # ── Demo 1: PlanBench instance-10 (3 goals, single city c0) ──
        # VAL-verified: 9-step plan, all intra-city truck deliveries
        demo1_beliefs = (
            "LOGISTICS DOMAIN\n"
            "\n=== WORLD STRUCTURE ===\n"
            "Cities: c0\n"
            "  c0: AIRPORT(s)=['l0-3'], other locations=['l0-0', 'l0-1', 'l0-2']\n"
            "\n"
            "⚠️  AIRPORTS (airplanes can ONLY fly between these): ['l0-3']\n"
            "   Non-airport locations CANNOT be used with fly-airplane!\n"
            "\n=== VEHICLE POSITIONS ===\n"
            "Airplanes (fly between AIRPORTS only):\n"
            "  a0 is at l0-3 (✓ AIRPORT, c0)\n"
            "Trucks (drive within ONE city only):\n"
            "  t0 is at l0-2 (c0)\n"
            "\n=== PACKAGE POSITIONS ===\n"
            "  p0 is at l0-2 (c0)\n"
            "  p1 is at l0-0 (c0)\n"
            "  p2 is at l0-1 (c0)\n"
            "  p3 is at l0-3 (c0)"
        )
        demo1_desire = (
            "Goal: deliver 3 package(s):\n"
            "  - p0 → l0-0 (c0) [same city, truck only]\n"
            "  - p1 → l0-1 (c0) [same city, truck only]\n"
            "  - p2 → l0-3 (c0) [same city, truck only]\n"
            "\n⚠️  AIRPORTS: ['l0-3'] — fly-airplane ONLY between these!\n"
            "Track vehicle positions after EVERY action.\n"
            "Generate a SEQUENTIAL plan with CONNECTED actions."
        )
        demo1_plan = BDIPlan(
            goal_description="Deliver p0→l0-0, p1→l0-1, p2→l0-3 (all in city c0)",
            nodes=[
                ActionNode(id="s1", action_type="load-truck",
                           params={"obj": "p0", "truck": "t0", "loc": "l0-2"},
                           description="Load p0 onto t0 at l0-2 (both start here)"),
                ActionNode(id="s2", action_type="drive-truck",
                           params={"truck": "t0", "from": "l0-2", "to": "l0-0", "city": "c0"},
                           description="Drive t0 to l0-0. t0 is now at l0-0"),
                ActionNode(id="s3", action_type="unload-truck",
                           params={"obj": "p0", "truck": "t0", "loc": "l0-0"},
                           description="Unload p0 at l0-0 — p0 goal achieved"),
                ActionNode(id="s4", action_type="load-truck",
                           params={"obj": "p1", "truck": "t0", "loc": "l0-0"},
                           description="Load p1 onto t0 at l0-0 (p1 is here, t0 is here after s2)"),
                ActionNode(id="s5", action_type="drive-truck",
                           params={"truck": "t0", "from": "l0-0", "to": "l0-1", "city": "c0"},
                           description="Drive t0 to l0-1. t0 is now at l0-1"),
                ActionNode(id="s6", action_type="unload-truck",
                           params={"obj": "p1", "truck": "t0", "loc": "l0-1"},
                           description="Unload p1 at l0-1 — p1 goal achieved"),
                ActionNode(id="s7", action_type="load-truck",
                           params={"obj": "p2", "truck": "t0", "loc": "l0-1"},
                           description="Load p2 onto t0 at l0-1 (p2 is here, t0 is here after s5)"),
                ActionNode(id="s8", action_type="drive-truck",
                           params={"truck": "t0", "from": "l0-1", "to": "l0-3", "city": "c0"},
                           description="Drive t0 to l0-3. t0 is now at l0-3"),
                ActionNode(id="s9", action_type="unload-truck",
                           params={"obj": "p2", "truck": "t0", "loc": "l0-3"},
                           description="Unload p2 at l0-3 — p2 goal achieved"),
            ],
            edges=[
                DependencyEdge(source="s1", target="s2"),
                DependencyEdge(source="s2", target="s3"),
                DependencyEdge(source="s3", target="s4"),
                DependencyEdge(source="s4", target="s5"),
                DependencyEdge(source="s5", target="s6"),
                DependencyEdge(source="s6", target="s7"),
                DependencyEdge(source="s7", target="s8"),
                DependencyEdge(source="s8", target="s9"),
            ],
        )

        # ── Demo 2: PlanBench instance-116 (6 goals, 2 cities c0+c1) ──
        # VAL-verified: 18-step plan, cross-city transport with airplanes
        demo2_beliefs = (
            "LOGISTICS DOMAIN\n"
            "\n=== WORLD STRUCTURE ===\n"
            "Cities: c0, c1\n"
            "  c0: AIRPORT(s)=['l0-0'], other locations=['l0-1', 'l0-2']\n"
            "  c1: AIRPORT(s)=['l1-0'], other locations=['l1-1', 'l1-2']\n"
            "\n"
            "⚠️  AIRPORTS (airplanes can ONLY fly between these): ['l0-0', 'l1-0']\n"
            "   Non-airport locations CANNOT be used with fly-airplane!\n"
            "\n=== VEHICLE POSITIONS ===\n"
            "Airplanes (fly between AIRPORTS only):\n"
            "  a0 is at l0-0 (✓ AIRPORT, c0)\n"
            "  a1 is at l1-0 (✓ AIRPORT, c1)\n"
            "Trucks (drive within ONE city only):\n"
            "  t0 is at l0-2 (c0)\n"
            "  t1 is at l1-2 (c1)\n"
            "\n=== PACKAGE POSITIONS ===\n"
            "  p0 is at l0-2 (c0)\n"
            "  p1 is at l0-0 (c0)\n"
            "  p2 is at l0-1 (c0)\n"
            "  p3 is at l1-2 (c1)\n"
            "  p4 is at l1-0 (c1)\n"
            "  p5 is at l1-1 (c1)"
        )
        demo2_desire = (
            "Goal: deliver 6 package(s):\n"
            "  - p3 → l1-1 (c1) [same city, truck only]\n"
            "  - p5 → l1-0 (c1) [same city, truck only]\n"
            "  - p0 → l0-1 (c0) [same city, truck only]\n"
            "  - p2 → l0-0 (c0) [same city, truck only]\n"
            "  - p4 → l0-0 (c0) [CROSS-CITY c1→c0, needs airplane]\n"
            "  - p1 → l1-0 (c1) [CROSS-CITY c0→c1, needs airplane]\n"
            "\n⚠️  AIRPORTS: ['l0-0', 'l1-0'] — fly-airplane ONLY between these!\n"
            "Track vehicle positions after EVERY action.\n"
            "Generate a SEQUENTIAL plan with CONNECTED actions."
        )
        demo2_plan = BDIPlan(
            goal_description="Deliver 6 packages across 2 cities (c0, c1) with truck+airplane",
            nodes=[
                # c1 local deliveries: t1 delivers p3, p5
                ActionNode(id="a1", action_type="load-truck",
                           params={"obj": "p3", "truck": "t1", "loc": "l1-2"},
                           description="Load p3 onto t1 at l1-2 (both start here)"),
                ActionNode(id="a2", action_type="drive-truck",
                           params={"truck": "t1", "from": "l1-2", "to": "l1-1", "city": "c1"},
                           description="Drive t1 to l1-1. t1 is now at l1-1"),
                ActionNode(id="a3", action_type="unload-truck",
                           params={"obj": "p3", "truck": "t1", "loc": "l1-1"},
                           description="Unload p3 at l1-1 — p3 goal achieved"),
                ActionNode(id="a4", action_type="load-truck",
                           params={"obj": "p5", "truck": "t1", "loc": "l1-1"},
                           description="Load p5 onto t1 at l1-1 (p5 is here, t1 is here after a2)"),
                ActionNode(id="a5", action_type="drive-truck",
                           params={"truck": "t1", "from": "l1-1", "to": "l1-0", "city": "c1"},
                           description="Drive t1 to airport l1-0. t1 is now at l1-0"),
                ActionNode(id="a6", action_type="unload-truck",
                           params={"obj": "p5", "truck": "t1", "loc": "l1-0"},
                           description="Unload p5 at l1-0 — p5 goal achieved"),
                # Cross-city prep: load p4 onto airplane a1
                ActionNode(id="a7", action_type="load-airplane",
                           params={"obj": "p4", "airplane": "a1", "loc": "l1-0"},
                           description="Load p4 onto a1 at airport l1-0 (a1 starts here)"),
                # c0 local deliveries: t0 delivers p0, p2
                ActionNode(id="a8", action_type="load-truck",
                           params={"obj": "p0", "truck": "t0", "loc": "l0-2"},
                           description="Load p0 onto t0 at l0-2 (both start here)"),
                ActionNode(id="a9", action_type="drive-truck",
                           params={"truck": "t0", "from": "l0-2", "to": "l0-1", "city": "c0"},
                           description="Drive t0 to l0-1. t0 is now at l0-1"),
                ActionNode(id="a10", action_type="unload-truck",
                           params={"obj": "p0", "truck": "t0", "loc": "l0-1"},
                           description="Unload p0 at l0-1 — p0 goal achieved"),
                ActionNode(id="a11", action_type="load-truck",
                           params={"obj": "p2", "truck": "t0", "loc": "l0-1"},
                           description="Load p2 onto t0 at l0-1 (p2 is here, t0 is here after a9)"),
                ActionNode(id="a12", action_type="drive-truck",
                           params={"truck": "t0", "from": "l0-1", "to": "l0-0", "city": "c0"},
                           description="Drive t0 to airport l0-0. t0 is now at l0-0"),
                ActionNode(id="a13", action_type="unload-truck",
                           params={"obj": "p2", "truck": "t0", "loc": "l0-0"},
                           description="Unload p2 at l0-0 — p2 goal achieved"),
                # Cross-city prep: load p1 onto airplane a0
                ActionNode(id="a14", action_type="load-airplane",
                           params={"obj": "p1", "airplane": "a0", "loc": "l0-0"},
                           description="Load p1 onto a0 at airport l0-0 (a0 starts here)"),
                # Cross-city flights
                ActionNode(id="a15", action_type="fly-airplane",
                           params={"airplane": "a1", "from": "l1-0", "to": "l0-0"},
                           description="Fly a1 from l1-0 to l0-0 (both AIRPORTS). a1 is now at l0-0"),
                ActionNode(id="a16", action_type="unload-airplane",
                           params={"obj": "p4", "airplane": "a1", "loc": "l0-0"},
                           description="Unload p4 at l0-0 (a1 is NOW at l0-0) — p4 goal achieved"),
                ActionNode(id="a17", action_type="fly-airplane",
                           params={"airplane": "a0", "from": "l0-0", "to": "l1-0"},
                           description="Fly a0 from l0-0 to l1-0 (both AIRPORTS). a0 is now at l1-0"),
                ActionNode(id="a18", action_type="unload-airplane",
                           params={"obj": "p1", "airplane": "a0", "loc": "l1-0"},
                           description="Unload p1 at l1-0 (a0 is NOW at l1-0) — p1 goal achieved"),
            ],
            edges=[
                DependencyEdge(source="a1", target="a2"),
                DependencyEdge(source="a2", target="a3"),
                DependencyEdge(source="a3", target="a4"),
                DependencyEdge(source="a4", target="a5"),
                DependencyEdge(source="a5", target="a6"),
                DependencyEdge(source="a6", target="a7"),
                DependencyEdge(source="a7", target="a8"),
                DependencyEdge(source="a8", target="a9"),
                DependencyEdge(source="a9", target="a10"),
                DependencyEdge(source="a10", target="a11"),
                DependencyEdge(source="a11", target="a12"),
                DependencyEdge(source="a12", target="a13"),
                DependencyEdge(source="a13", target="a14"),
                DependencyEdge(source="a14", target="a15"),
                DependencyEdge(source="a15", target="a16"),
                DependencyEdge(source="a16", target="a17"),
                DependencyEdge(source="a17", target="a18"),
            ],
        )

        return [
            dspy.Example(
                beliefs=demo1_beliefs,
                desire=demo1_desire,
                plan=demo1_plan,
            ).with_inputs("beliefs", "desire"),
            dspy.Example(
                beliefs=demo2_beliefs,
                desire=demo2_desire,
                plan=demo2_plan,
            ).with_inputs("beliefs", "desire"),
        ]

    def _validate_action_constraints(self, plan_obj) -> tuple:
        """Validate action_type and params against domain constraints.

        Returns:
            (all_valid, error_message) — error_message is empty when valid.
        """
        valid_types = self._valid_action_types.get(self.domain, set())
        required_params = self._required_params.get(self.domain, {})

        if not valid_types:
            return True, ""

        invalid_actions = []
        missing_params = []

        for node in plan_obj.nodes:
            # Skip virtual nodes injected by auto-repair
            if node.action_type == "Virtual":
                continue

            at = node.action_type.lower()

            if at not in valid_types:
                invalid_actions.append(
                    f"Node '{node.id}' has invalid action_type '{node.action_type}'. "
                    f"Must be one of: {sorted(valid_types)}"
                )

            elif at in required_params:
                present = set(node.params.keys()) if node.params else set()
                missing = required_params[at] - present
                if missing:
                    missing_params.append(
                        f"Node '{node.id}' ({node.action_type}) missing params: "
                        f"{sorted(missing)}. Required: {sorted(required_params[at])}"
                    )

        errors = invalid_actions + missing_params
        if errors:
            return False, "; ".join(errors)
        return True, ""

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        # Generate the plan
        pred = self.generate_plan(beliefs=beliefs, desire=desire)

        try:
            plan_obj = pred.plan

            # --- Validate action_type validity & param completeness ---
            constraints_ok, constraint_msg = self._validate_action_constraints(plan_obj)
            if not constraints_ok:
                raise ValueError(
                    f"Action constraint violation: {constraint_msg}. "
                    f"Re-generate the plan using ONLY valid action types for the {self.domain} domain "
                    f"and include ALL required parameters for each action."
                )

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

            # If still invalid, raise an error with detailed feedback
            if not is_valid:
                raise ValueError(
                    f"The generated plan is invalid. Errors: {'; '.join(errors)}. Please fix the dependencies to remove cycles or connect the graph. REMEMBER: All nodes must form ONE CONNECTED graph, not separate islands."
                )
        except Exception as e:
            # Handle potential pydantic validation errors or parsing issues
            raise ValueError(
                f"Failed to generate a valid plan object. Error: {str(e)}"
            ) from e

        return pred

    def _format_repair_history(
        self,
        repair_history: List[dict] | None = None,
    ) -> str:
        """Format cumulative repair history for the dedicated repair_history field.

        Returns an empty string for the first attempt, or a structured history
        showing all previous failed attempts with their plans and errors.
        """
        if not repair_history:
            return ""

        parts = []
        parts.append("=== CUMULATIVE REPAIR HISTORY ===")
        parts.append(f"Total previous attempts: {len(repair_history)}")
        parts.append("")

        for entry in repair_history:
            attempt_num = entry["attempt"]
            actions = entry.get("plan_actions", [])
            errors = entry.get("val_errors", [])
            parts.append(f"--- Attempt {attempt_num} (FAILED) ---")
            parts.append(f"Plan ({len(actions)} actions):")
            for a in actions[:15]:
                parts.append(f"  {a}")
            if len(actions) > 15:
                parts.append(f"  ... ({len(actions) - 15} more actions)")
            parts.append("VAL Errors:")
            for e in errors[:5]:
                parts.append(f"  - {e}")
            parts.append("")

        parts.append("=== END HISTORY ===")
        parts.append(
            f"You have failed {len(repair_history)} time(s). "
            "DO NOT repeat any of the plans above. "
            "Analyze the error patterns and try a fundamentally different approach."
        )
        return "\n".join(parts)

    def repair_from_val_errors(
        self,
        beliefs: str,
        desire: str,
        previous_plan_actions: List[str],
        val_errors: List[str],
        repair_history: List[dict] | None = None,
    ) -> dspy.Prediction:
        """
        Generate a repaired plan based on VAL validation errors.

        Args:
            beliefs: Original beliefs (natural language)
            desire: Original desire (natural language)
            previous_plan_actions: PDDL action strings that failed validation
            val_errors: Error messages from VAL validator
            repair_history: Cumulative list of all previous repair attempts,
                each dict has keys: attempt, plan_actions, val_errors

        Returns:
            dspy.Prediction with repaired plan

        Raises:
            ValueError: If the repaired plan is structurally invalid
        """
        # Build repair history string for the dedicated field
        history_str = self._format_repair_history(repair_history)

        pred = self.repair_plan(
            beliefs=beliefs,
            desire=desire,
            previous_plan="\n".join(previous_plan_actions),
            val_errors="\n".join(val_errors),
            repair_history=history_str,
        )

        try:
            plan_obj = pred.plan

            # Validate action constraints on repaired plan
            constraints_ok, constraint_msg = self._validate_action_constraints(plan_obj)
            if not constraints_ok:
                raise ValueError(
                    f"Repaired plan has action constraint violations: {constraint_msg}"
                )

            G = plan_obj.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            # Try structural auto-repair if needed
            if not is_valid and self.auto_repair:
                from .plan_repair import repair_and_verify

                repaired_plan, repaired_valid, messages = repair_and_verify(plan_obj)
                if repaired_valid:
                    pred.plan = repaired_plan
                    is_valid = True
                    errors = []

            if not is_valid:
                raise ValueError(
                    f"Repaired plan is structurally invalid. Errors: {'; '.join(errors)}"
                )
        except Exception as e:
            raise ValueError(
                f"Failed to generate repaired plan. Error: {str(e)}"
            ) from e

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

    except ValueError as e:
        print(f"\n❌ Planning Failed: {e}")

if __name__ == "__main__":
    main()
