"""DSPy Signature definitions for BDI plan generation and repair."""

import dspy
from ..schemas import BDIPlan
from .prompts import (
    _GRAPH_STRUCTURE_COMMON,
    _STATE_TRACKING_HEADER,
    _COS_REPRESENTATION_HEADER,
    _LOGICOT_HEADER,
    _LOGICOT_PROTOCOL_DETAILED,
    _REMINDER,
)


class GeneratePlan(dspy.Signature):
    __doc__ = f"""
    You are a BDI (Belief-Desire-Intention) Planning Agent.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

    ═══════════════════════════════════════════════════════════════════════════
    STEP 1: LIST ALL ACTIONS IN EXECUTION ORDER (Chain-of-Thought)
    ═══════════════════════════════════════════════════════════════════════════

    Before generating the graph, write down ALL actions in the exact order they
    must execute. This is your "linearization" of the plan.

    Format:
    ```
    EXECUTION ORDER:
    1. <action_1>
    2. <action_2>
    3. <action_3>
    ...
    N. <action_N>
    ```

    Then VERIFY:
    - [ ] No action appears more than once (check for duplicates)
    - [ ] Each action advances toward the goal
    - [ ] No action returns to a previously visited state
    - [ ] The last action achieves the goal

    ═══════════════════════════════════════════════════════════════════════════
    STEP 2: CONVERT TO GRAPH (Nodes + Edges)
    ═══════════════════════════════════════════════════════════════════════════

    Convert your linear order into a graph:
    - Each action becomes a node with a unique ID (s1, s2, ..., sN)
    - Add edges: (s1→s2), (s2→s3), ..., (sN-1→sN)
    - This guarantees acyclicity by construction

    ═══════════════════════════════════════════════════════════════════════════
    FINAL CHECK (Mandatory)
    ═══════════════════════════════════════════════════════════════════════════

    Count occurrences of each UNIQUE action (by action_type + params):
    - If any action appears 2+ times → YOU HAVE A CYCLE. Remove duplicates.
    - If graph is not connected → ADD MISSING EDGES to connect all nodes.

    CRITICAL GRAPH STRUCTURE REQUIREMENTS:

    1. **CONNECTIVITY**: The plan graph MUST be weakly connected.
       ALL action nodes must be reachable from each other via edges.
       There should be NO disconnected "islands" or separate subgraphs.

    2. **DAG (Directed Acyclic Graph)**: No cycles allowed.
       If action A → B → C, then C cannot have an edge back to A or B.
       After generating your plan, VERIFY: "Does any action appear twice in the execution order?" If YES, remove the duplicate.

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

    ═══════════════════════════════════════════════════════════════════════════
    STEP 1: LIST ALL ACTIONS IN EXECUTION ORDER (Chain-of-Thought)
    ═══════════════════════════════════════════════════════════════════════════

    Before generating the graph, write down ALL actions in the exact order they
    must execute. This is your "linearization" of the plan.

    Format:
    ```
    EXECUTION ORDER:
    1. <action_1>
    2. <action_2>
    3. <action_3>
    ...
    N. <action_N>
    ```

    Then VERIFY:
    - [ ] No action appears more than once (check for duplicates)
    - [ ] Each action advances toward the goal
    - [ ] No action returns to a previously visited state
    - [ ] The last action achieves the goal
    - [ ] AFTER EVERY vehicle movement (drive/fly), the vehicle is at the NEW location

    ═══════════════════════════════════════════════════════════════════════════
    STEP 2: CONVERT TO GRAPH (Nodes + Edges)
    ═══════════════════════════════════════════════════════════════════════════

    Convert your linear order into a graph:
    - Each action becomes a node with a unique ID (s1, s2, ..., sN)
    - Add edges: (s1→s2), (s2→s3), ..., (sN-1→sN)
    - This guarantees acyclicity by construction

    ═══════════════════════════════════════════════════════════════════════════
    FINAL CHECK (Mandatory)
    ═══════════════════════════════════════════════════════════════════════════

    Count occurrences of each UNIQUE action (by action_type + params):
    - If any action appears 2+ times → YOU HAVE A CYCLE. Remove duplicates.
    - If graph is not connected → ADD MISSING EDGES to connect all nodes.

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

    ═══════════════════════════════════════════════════════════════════════════
    STEP 1: LIST ALL ACTIONS IN EXECUTION ORDER (Chain-of-Thought)
    ═══════════════════════════════════════════════════════════════════════════

    Before generating the graph, write down ALL actions in the exact order they
    must execute. This is your "linearization" of the plan.

    Format:
    ```
    EXECUTION ORDER:
    1. <action_1>
    2. <action_2>
    3. <action_3>
    ...
    N. <action_N>
    ```

    Then VERIFY:
    - [ ] No action appears more than once (check for duplicates)
    - [ ] Each action advances toward the goal
    - [ ] No action returns to a previously visited state
    - [ ] The last action achieves the goal
    - [ ] AFTER EVERY truck drive, the truck is at the NEW location (not the old one)
    - [ ] AFTER EVERY hoist lift, the hoist is BUSY (cannot lift another crate)

    ═══════════════════════════════════════════════════════════════════════════
    STEP 2: CONVERT TO GRAPH (Nodes + Edges)
    ═══════════════════════════════════════════════════════════════════════════

    Convert your linear order into a graph:
    - Each action becomes a node with a unique ID (s1, s2, ..., sN)
    - Add edges: (s1→s2), (s2→s3), ..., (sN-1→sN)
    - This guarantees acyclicity by construction

    ═══════════════════════════════════════════════════════════════════════════
    FINAL CHECK (Mandatory)
    ═══════════════════════════════════════════════════════════════════════════

    Count occurrences of each UNIQUE action (by action_type + params):
    - If any action appears 2+ times → YOU HAVE A CYCLE. Remove duplicates.
    - If graph is not connected → ADD MISSING EDGES to connect all nodes.

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

    VERIFIER FEEDBACK:
    - If verification_feedback is provided, it summarizes multi-layer verifier failures.
    - Prioritize fixes based on failed_layers and repair_focus before proposing new actions.
    - Use val_repair_advice as hard guidance when present.
    """
    beliefs: str = dspy.InputField(desc="Current state of the world")
    desire: str = dspy.InputField(desc="The goal to achieve")
    previous_plan: str = dspy.InputField(desc="The plan that failed validation (as PDDL action sequence)")
    val_errors: str = dspy.InputField(desc="Specific validation errors from the PDDL validator (VAL), including which action failed, why, and repair advice")
    repair_history: str = dspy.InputField(desc="History of ALL previous repair attempts and their errors. Empty string if this is the first attempt. Study this to avoid repeating the same mistakes.", default="")
    verification_feedback: str = dspy.InputField(desc="Structured multi-layer verifier feedback (failed layers, key errors, and suggested repair focus). Empty string if unavailable.", default="")
    plan: BDIPlan = dspy.OutputField(desc="Corrected plan fixing the validation errors, as a SINGLE CONNECTED DAG")
