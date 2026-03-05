"""
PDDL to Natural Language Conversion
====================================

Domain-specific converters that transform PDDL problem data into
natural-language beliefs and desires for the BDI planner.
"""
from typing import Tuple


def pddl_to_natural_language(pddl_data: dict, domain: str = "blocksworld") -> Tuple[str, str]:
    """Convert PDDL to natural language (domain-specific)"""

    if domain == "blocksworld":
        return pddl_to_nl_blocksworld(pddl_data)
    elif domain == "logistics":
        return pddl_to_nl_logistics(pddl_data)
    elif domain == "depots":
        return pddl_to_nl_depots(pddl_data)
    else:
        # Generic fallback
        return pddl_to_nl_generic(pddl_data)


def pddl_to_nl_blocksworld(pddl_data: dict) -> Tuple[str, str]:
    """Enhanced Blocksworld-specific conversion with clearer state description"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse init state in detail
    on_table = []
    clear_blocks = []
    stacks = {}  # block -> block it's on
    hand_empty = True

    # Track goal pairs
    goal_pairs = set()
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'on' and len(parts) >= 3:
            goal_pairs.add((parts[1], parts[2]))

    # Identify goal tops (any block that is a 'top' in a goal pair)
    # If a block is NOT in this set, it should be on the table in the goal state.
    goal_tops = {t for t, b in goal_pairs}

    for pred in init:
        parts = pred.split()
        if parts[0] == 'ontable':
            on_table.append(parts[1])
        elif parts[0] == 'clear':
            clear_blocks.append(parts[1])
        elif parts[0] == 'on' and len(parts) >= 3:
            stacks[parts[1]] = parts[2]
        elif parts[0] == 'handempty':
            hand_empty = True
        elif parts[0] == 'holding':
            hand_empty = False

    # Build beliefs with detailed state description
    beliefs_parts = []
    beliefs_parts.append(f"BLOCKSWORLD DOMAIN")
    beliefs_parts.append(f"\n=== CURRENT STATE ===")
    beliefs_parts.append(f"Available blocks ({len(objects)}): {', '.join(sorted(objects))}")

    # Describe stacks (what's on what) - ENHANCED
    if stacks:
        stack_descs = []
        for top, bottom in sorted(stacks.items()):
            stack_descs.append(f"{top} is on top of {bottom}")
        beliefs_parts.append(f"Current stacks: {'; '.join(stack_descs)}")
        beliefs_parts.append(f"⚠️  IMPORTANT: These blocks are STACKED. To move them, you MUST unstack first!")
    else:
        beliefs_parts.append(f"Current stacks: None (all blocks are on table)")

    # Describe blocks on table
    if on_table:
        beliefs_parts.append(f"Blocks on table: {', '.join(sorted(on_table))}")

    # Describe clear blocks (can be picked up)
    beliefs_parts.append(f"Clear blocks (nothing on top): {', '.join(sorted(clear_blocks))}")

    # Hand state
    beliefs_parts.append(f"Hand: {'empty' if hand_empty else 'holding something'}")

    beliefs_parts.append(f"\n=== CRITICAL RULES FOR INITIAL STACKS ===")
    beliefs_parts.append("⚠️  If a block is ON another block in the initial state:")
    beliefs_parts.append("   1. You CANNOT pick-up that block directly")
    beliefs_parts.append("   2. You MUST use 'unstack X Y' to remove X from Y first")
    beliefs_parts.append("   3. After unstacking, you are HOLDING the block")
    beliefs_parts.append("   4. Then you can put-down or stack it elsewhere")
    beliefs_parts.append("")
    beliefs_parts.append("Example: If initial state has '(on B A)' and you want to move B:")
    beliefs_parts.append("   ✓ Correct: unstack B A → put-down B (or stack B somewhere)")
    beliefs_parts.append("   ✗ Wrong: pick-up B (this will FAIL - B is not on table!)")

    beliefs_parts.append(f"\n=== PHYSICS CONSTRAINTS ===")
    beliefs_parts.append("1. You can only hold ONE block at a time")
    beliefs_parts.append("2. You can only pick up blocks that are CLEAR (nothing on top)")
    beliefs_parts.append("3. You can only stack on blocks that are CLEAR")
    beliefs_parts.append("4. pick-up ONLY works for blocks ON TABLE")
    beliefs_parts.append("5. unstack ONLY works for blocks ON OTHER BLOCKS")

    beliefs_parts.append(f"\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("- pick-up X: Pick up block X from TABLE (X must be clear and ON TABLE)")
    beliefs_parts.append("- put-down X: Put block X on table (you must be holding X)")
    beliefs_parts.append("- stack X Y: Put block X on top of block Y (you hold X, Y must be clear)")
    beliefs_parts.append("- unstack X Y: Take block X off block Y (X must be clear, hand empty)")

    beliefs_parts.append(f"\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan where each action depends on the previous one.")
    beliefs_parts.append("The plan graph must be CONNECTED - all actions form one chain/path.")

    beliefs = "\n".join(beliefs_parts)

    # --- TEARDOWN PHASE ---

    step_num = 1
    teardown_text = ""

    # Identify initial on-pairs that are NOT in the goal
    initial_pairs = [
        (top, bottom)
        for top, bottom in stacks.items()
        if (top, bottom) not in goal_pairs
    ]

    if initial_pairs:
        # Order by height (top-first) for safer unstacking
        heights = {}

        def get_height(b):
            if b in heights:
                return heights[b]
            if b in on_table:
                heights[b] = 0
                return 0
            if b in stacks:
                h = 1 + get_height(stacks[b])
                heights[b] = h
                return h
            return 0

        initial_pairs.sort(key=lambda pair: get_height(pair[0]), reverse=True)

        teardown_text += "Teardown steps (clearing mismatches):\n"
        for top, bottom in initial_pairs:
            teardown_text += (
                f"    Step {step_num}: unstack {top} from {bottom}, then put-down {top}\n"
            )
            step_num += 1
        teardown_text += "\n  "

    # --- END TEARDOWN PHASE ---

    # Build goal with bottom-up tower ordering and explicit construction steps

    # Build bottom-up ordering: find tower bases and walk upward
    # on_map: bottom_block -> block_that_goes_on_top
    on_map = {}
    top_set = set()
    bottom_set = set()
    for top_blk, bot_blk in list(goal_pairs):
        on_map[bot_blk] = top_blk
        top_set.add(top_blk)
        bottom_set.add(bot_blk)

    # Base blocks: appear as a support but are never placed on something else
    bases = sorted(b for b in bottom_set if b not in top_set)

    # Walk each tower chain from base upward
    towers = []
    for base in bases:
        tower = [base]
        cur = base
        while cur in on_map:
            cur = on_map[cur]
            tower.append(cur)
        towers.append(tower)

    goal_desc = "Build the following tower(s) from BOTTOM to TOP:\n"

    if teardown_text:
        goal_desc += f"\n  {teardown_text}"

    for tower in towers:
        goal_desc += f"\n  Tower (base={tower[0]}): {' -> '.join(tower)}  (bottom to top)\n"
        goal_desc += f"  Construction steps:\n"
        for i in range(1, len(tower)):
            blk = tower[i]
            tgt = tower[i - 1]
            goal_desc += f"    Step {step_num}: pick-up {blk}, then stack {blk} on {tgt}\n"
            step_num += 1

    goal_desc += "\n=== EXAMPLES ===\n"
    goal_desc += "\nExample 1 — Simple case (all blocks on table):\n"
    goal_desc += "  Initial: A, B, C all on table\n"
    goal_desc += "  Goal: Build tower C -> B -> A (C on table, B on C, A on B)\n"
    goal_desc += "  Plan: 1. pick-up B   2. stack B C   3. pick-up A   4. stack A B\n"

    goal_desc += "\nExample 2 — Complex case (initial stacks exist):\n"
    goal_desc += "  Initial: (on C B), (on B A), A on table  [tower: C-B-A]\n"
    goal_desc += "  Goal: (on A B), (on C A)  [tower: B-A-C]\n"
    goal_desc += "  Analysis: Need to dismantle C-B-A, then rebuild as B-A-C\n"
    goal_desc += "  Plan:\n"
    goal_desc += "    1. unstack C B  (now holding C)\n"
    goal_desc += "    2. put-down C   (C on table, hand empty)\n"
    goal_desc += "    3. unstack B A  (now holding B)\n"
    goal_desc += "    4. put-down B   (B on table, hand empty)\n"
    goal_desc += "    5. pick-up A    (now holding A)\n"
    goal_desc += "    6. stack A B    (A on B, hand empty)\n"
    goal_desc += "    7. pick-up C    (now holding C)\n"
    goal_desc += "    8. stack C A    (C on A, done!)\n"

    goal_desc += "\n⚠️  KEY INSIGHT: When blocks are already stacked, you MUST unstack them first!\n"
    goal_desc += "Work step-by-step, one action at a time. Each action depends on completing the previous action."

    desire = goal_desc

    return beliefs, desire


def pddl_to_nl_generic(pddl_data: dict) -> Tuple[str, str]:
    """Generic PDDL to NL conversion"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    beliefs = f"Domain objects: {', '.join(objects)}. Initial state: {'; '.join(init[:10])}..."
    desire = f"Achieve goal: {'; '.join(goal[:5])}..."

    return beliefs, desire


def pddl_to_nl_logistics(pddl_data: dict) -> Tuple[str, str]:
    """Logistics domain conversion with enhanced airport/city awareness"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse logistics state comprehensively
    packages = []
    trucks = []
    airplanes = []
    airports = set()       # locations that are airports
    cities = []
    city_locations = {}    # city -> [locations]
    location_city = {}     # location -> city

    at_locations = {}  # object -> location
    in_vehicle = {}    # package -> vehicle

    for pred in init:
        parts = pred.split()
        if not parts:
            continue
        pred_name = parts[0].lower()

        if pred_name == 'at' and len(parts) >= 3:
            at_locations[parts[1]] = parts[2]
        elif pred_name == 'in' and len(parts) >= 3:
            in_vehicle[parts[1]] = parts[2]
        elif pred_name == 'airport' and len(parts) >= 2:
            airports.add(parts[1])
        elif pred_name == 'in-city' and len(parts) >= 3:
            loc, city = parts[1], parts[2]
            city_locations.setdefault(city, []).append(loc)
            location_city[loc] = city
        elif pred_name == 'obj' and len(parts) >= 2:
            packages.append(parts[1])
        elif pred_name == 'truck' and len(parts) >= 2:
            trucks.append(parts[1])
        elif pred_name == 'airplane' and len(parts) >= 2:
            airplanes.append(parts[1])
        elif pred_name == 'city' and len(parts) >= 2:
            cities.append(parts[1])

    # Build beliefs
    beliefs_parts = []
    beliefs_parts.append("LOGISTICS DOMAIN")

    # === WORLD STRUCTURE: Cities, Locations, Airports ===
    beliefs_parts.append("\n=== WORLD STRUCTURE ===")
    beliefs_parts.append(f"Cities: {', '.join(sorted(cities))}")
    for city in sorted(city_locations.keys()):
        locs = city_locations[city]
        airport_locs = sorted([l for l in locs if l in airports])
        non_airport_locs = sorted([l for l in locs if l not in airports])
        beliefs_parts.append(f"  {city}: AIRPORT(s)={airport_locs}, other locations={non_airport_locs}")

    beliefs_parts.append("")
    beliefs_parts.append(f"⚠️  AIRPORTS (airplanes can ONLY fly between these): {sorted(airports)}")
    beliefs_parts.append("   Non-airport locations CANNOT be used with fly-airplane!")

    # === VEHICLE POSITIONS ===
    beliefs_parts.append("\n=== VEHICLE POSITIONS ===")
    beliefs_parts.append("Airplanes (fly between AIRPORTS only):")
    for ap in sorted(airplanes):
        loc = at_locations.get(ap, "unknown")
        city = location_city.get(loc, "?")
        is_airport = "✓ AIRPORT" if loc in airports else "✗ NOT airport"
        beliefs_parts.append(f"  {ap} is at {loc} ({is_airport}, {city})")

    beliefs_parts.append("Trucks (drive within ONE city only):")
    for tr in sorted(trucks):
        loc = at_locations.get(tr, "unknown")
        city = location_city.get(loc, "?")
        beliefs_parts.append(f"  {tr} is at {loc} ({city})")

    # === PACKAGE POSITIONS ===
    beliefs_parts.append("\n=== PACKAGE POSITIONS ===")
    for pkg in sorted(packages):
        if pkg in in_vehicle:
            beliefs_parts.append(f"  {pkg} is IN {in_vehicle[pkg]}")
        elif pkg in at_locations:
            loc = at_locations[pkg]
            city = location_city.get(loc, "?")
            beliefs_parts.append(f"  {pkg} is at {loc} ({city})")

    # === ACTIONS ===
    beliefs_parts.append("\n=== AVAILABLE ACTIONS WITH EXACT PARAMETER FORMAT ===")
    beliefs_parts.append('1. load-truck: {"obj": "<package>", "truck": "<truck>", "loc": "<location>"}')
    beliefs_parts.append('2. unload-truck: {"obj": "<package>", "truck": "<truck>", "loc": "<location>"}')
    beliefs_parts.append('3. load-airplane: {"obj": "<package>", "airplane": "<airplane>", "loc": "<AIRPORT>"}')
    beliefs_parts.append('4. unload-airplane: {"obj": "<package>", "airplane": "<airplane>", "loc": "<AIRPORT>"}')
    beliefs_parts.append('5. drive-truck: {"truck": "<truck>", "from": "<loc>", "to": "<loc>", "city": "<city>"}')
    beliefs_parts.append('6. fly-airplane: {"airplane": "<airplane>", "from": "<AIRPORT>", "to": "<AIRPORT>"}')

    # === CRITICAL RULES ===
    beliefs_parts.append("\n=== CRITICAL RULES ===")
    beliefs_parts.append(f"⚠️  AIRPORTS in this problem: {sorted(airports)}")
    beliefs_parts.append("1. fly-airplane: BOTH 'from' and 'to' MUST be AIRPORT locations")
    beliefs_parts.append("   ❌ WRONG: fly-airplane with non-airport location")
    beliefs_parts.append("2. drive-truck: 'from' and 'to' MUST be in the SAME city")
    beliefs_parts.append("   ❌ WRONG: drive-truck between different cities")
    beliefs_parts.append("3. load/unload: vehicle and package MUST be at the SAME location")
    beliefs_parts.append("4. Inter-city transport pattern:")
    beliefs_parts.append("   truck→airport(load)→fly→airport(unload)→truck→destination")

    # === STATE TRACKING ===
    beliefs_parts.append("\n=== STATE TRACKING (MANDATORY) ===")
    beliefs_parts.append("After EVERY action, update your mental state table:")
    beliefs_parts.append("  - fly-airplane: airplane moves to destination AIRPORT")
    beliefs_parts.append("  - drive-truck: truck moves to destination location")
    beliefs_parts.append("  - load-*: package is IN vehicle, no longer at location")
    beliefs_parts.append("  - unload-*: package is AT location, no longer in vehicle")
    beliefs_parts.append("")
    beliefs_parts.append("BEFORE each action, verify:")
    beliefs_parts.append("  - Is the vehicle at the correct location RIGHT NOW?")
    beliefs_parts.append("  - Is the package at the correct location (for load)?")
    beliefs_parts.append("  - Is the package in the vehicle (for unload)?")
    beliefs_parts.append(f"  - For fly-airplane: is the location an AIRPORT? (only {sorted(airports)})")

    beliefs = "\n".join(beliefs_parts)

    # Build goal
    goal_descs = []
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            pkg, loc = parts[1], parts[2]
            city = location_city.get(loc, "?")
            # Determine if inter-city transport is needed
            pkg_loc = at_locations.get(pkg, "")
            pkg_city = location_city.get(pkg_loc, "?")
            if pkg_city != city and pkg_city != "?":
                goal_descs.append(f"{pkg} → {loc} ({city}) [currently in {pkg_city}, needs AIRPLANE]")
            else:
                goal_descs.append(f"{pkg} → {loc} ({city}) [same city, truck only]")

    desire_parts = []
    desire_parts.append(f"Goal: deliver {len(goal_descs)} package(s):")
    for gd in goal_descs:
        desire_parts.append(f"  - {gd}")

    desire_parts.append(f"\n⚠️  AIRPORTS: {sorted(airports)} — fly-airplane ONLY between these!")
    desire_parts.append("Track vehicle positions after EVERY action.")
    desire_parts.append("Generate a SEQUENTIAL plan with CONNECTED actions.")

    desire = "\n".join(desire_parts)

    return beliefs, desire


def pddl_to_nl_depots(pddl_data: dict) -> Tuple[str, str]:
    """Enhanced Depots domain conversion with clear action specifications"""
    objects = pddl_data['objects']
    typed_objects = pddl_data.get('typed_objects', {})
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse depots state
    crates = []
    trucks = []
    hoists = []
    pallets = []
    locations = []

    at_locations = {}  # object -> location
    on_surface = {}    # crate -> surface (pallet or crate)
    in_truck = {}      # crate -> truck
    lifting = {}       # hoist -> crate (if any)
    available = set()  # available hoists
    clear = set()      # clear surfaces

    for pred in init:
        parts = pred.split()
        if not parts:
            continue

        pred_name = parts[0]

        if pred_name == 'at' and len(parts) >= 3:
            at_locations[parts[1]] = parts[2]
        elif pred_name == 'on' and len(parts) >= 3:
            on_surface[parts[1]] = parts[2]
        elif pred_name == 'in' and len(parts) >= 3:
            in_truck[parts[1]] = parts[2]
        elif pred_name == 'lifting' and len(parts) >= 3:
            lifting[parts[1]] = parts[2]
        elif pred_name == 'available' and len(parts) >= 2:
            available.add(parts[1])
        elif pred_name == 'clear' and len(parts) >= 2:
            clear.add(parts[1])

    # Classify objects by type using typed_objects mapping
    for obj in objects:
        obj_type = typed_objects.get(obj, '').lower()
        if 'crate' in obj or obj_type == 'crate':
            crates.append(obj)
        elif 'truck' in obj or obj_type == 'truck':
            trucks.append(obj)
        elif 'hoist' in obj or obj_type == 'hoist':
            hoists.append(obj)
        elif 'pallet' in obj or obj_type == 'pallet':
            pallets.append(obj)
        elif 'depot' in obj or 'distributor' in obj or obj_type in ('depot', 'distributor', 'place'):
            locations.append(obj)

    # Build beliefs with detailed state description
    beliefs_parts = []
    beliefs_parts.append("DEPOTS DOMAIN")

    # List objects with types
    beliefs_parts.append("\n=== OBJECTS AND TYPES ===")
    if typed_objects:
        type_groups = {}
        for obj_name, obj_type in typed_objects.items():
            type_groups.setdefault(obj_type, []).append(obj_name)
        for type_name, obj_names in sorted(type_groups.items()):
            beliefs_parts.append(f"  {type_name}: {', '.join(sorted(obj_names))}")
    else:
        beliefs_parts.append(f"  Objects: {', '.join(objects[:30])}")

    beliefs_parts.append("\n=== CURRENT STATE ===")

    if at_locations:
        loc_descs = [f"{obj} is at {loc}" for obj, loc in list(at_locations.items())[:15]]
        beliefs_parts.append(f"\nLocations: {'; '.join(loc_descs)}")

    if on_surface:
        surface_descs = [f"{crate} is on {surf}" for crate, surf in list(on_surface.items())[:10]]
        beliefs_parts.append(f"On surfaces: {'; '.join(surface_descs)}")

    if in_truck:
        truck_descs = [f"{crate} is in {truck}" for crate, truck in list(in_truck.items())[:10]]
        beliefs_parts.append(f"In trucks: {'; '.join(truck_descs)}")

    if available:
        beliefs_parts.append(f"Available hoists: {', '.join(sorted(available))}")

    if clear:
        beliefs_parts.append(f"Clear surfaces: {', '.join(sorted(clear))}")

    beliefs_parts.append("\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("⚠️  CRITICAL: Use ONLY these Depots actions. DO NOT use blocksworld actions!")
    beliefs_parts.append("⚠️  Parameter names MUST use the EXACT object names listed above (e.g., hoist0, crate0, pallet0, depot0)")
    beliefs_parts.append("")
    beliefs_parts.append("1. Lift <hoist> <crate> <surface> <place>")
    beliefs_parts.append("   - hoist: a Hoist object (e.g., hoist0)")
    beliefs_parts.append("   - crate: a Crate object (e.g., crate0)")
    beliefs_parts.append("   - surface: a Pallet or Crate the crate is ON (e.g., pallet0)")
    beliefs_parts.append("   - place: a Depot or Distributor location (e.g., depot0)")
    beliefs_parts.append("   - Preconditions: hoist available, crate on surface, crate clear, all at place")
    beliefs_parts.append("   - Effects: hoist lifting crate, crate no longer on surface, surface becomes clear")
    beliefs_parts.append("")
    beliefs_parts.append("2. Drop <hoist> <crate> <surface> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate")
    beliefs_parts.append("   - surface: a Pallet or Crate to drop ONTO | place: a Depot or Distributor")
    beliefs_parts.append("   - Preconditions: hoist lifting crate, surface clear, all at place")
    beliefs_parts.append("   - Effects: crate on surface, hoist available, crate becomes clear")
    beliefs_parts.append("")
    beliefs_parts.append("3. Load <hoist> <crate> <truck> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate | truck: a Truck | place: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: hoist lifting crate, truck at place, hoist at place")
    beliefs_parts.append("   - Effects: crate in truck, hoist available")
    beliefs_parts.append("")
    beliefs_parts.append("4. Unload <hoist> <crate> <truck> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate | truck: a Truck | place: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: hoist available, crate in truck, truck at place, hoist at place")
    beliefs_parts.append("   - Effects: hoist lifting crate, crate no longer in truck")
    beliefs_parts.append("")
    beliefs_parts.append("5. Drive <truck> <from> <to>")
    beliefs_parts.append("   - truck: a Truck | from: a Depot/Distributor | to: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: truck at from location")
    beliefs_parts.append("   - Effects: truck at to location, no longer at from")

    beliefs_parts.append("\n=== CRITICAL RULES ===")
    beliefs_parts.append("❌ DO NOT use blocksworld actions: pick-up, put-down, stack, unstack")
    beliefs_parts.append("✓ ONLY use depots actions: Lift, Drop, Load, Unload, Drive")
    beliefs_parts.append("- Hoists are used to manipulate crates (like robotic arms)")
    beliefs_parts.append("- Crates can be on pallets or on other crates")
    beliefs_parts.append("- Trucks transport crates between locations")
    beliefs_parts.append("- All manipulation requires a hoist at the same location")
    beliefs_parts.append("- To move a crate to a different location: Lift -> Load -> Drive -> Unload -> Drop")
    beliefs_parts.append("- To rearrange crates at the SAME location: just Lift and Drop (no truck needed)")

    beliefs_parts.append("\n=== CRITICAL: HOIST STATE MACHINE ===")
    beliefs_parts.append("⚠️  A hoist has TWO states - you MUST track this:")
    beliefs_parts.append("")
    beliefs_parts.append("1. AVAILABLE: Can lift a crate")
    beliefs_parts.append("2. LIFTING <crate>: Holding a crate, CANNOT lift another crate")
    beliefs_parts.append("")
    beliefs_parts.append("State transitions:")
    beliefs_parts.append("  - Lift: available → lifting <crate>")
    beliefs_parts.append("  - Drop: lifting <crate> → available")
    beliefs_parts.append("  - Load: lifting <crate> → available (crate goes into truck)")
    beliefs_parts.append("  - Unload: available → lifting <crate> (crate comes out of truck)")
    beliefs_parts.append("")
    beliefs_parts.append("❌ WRONG: (Lift hoist0 crate1 ...) then (Lift hoist0 crate2 ...)")
    beliefs_parts.append("   → hoist0 is LIFTING crate1, cannot lift crate2!")
    beliefs_parts.append("")
    beliefs_parts.append("✓ RIGHT: (Lift hoist0 crate1 ...) then (Drop hoist0 crate1 ...) then (Lift hoist0 crate2 ...)")
    beliefs_parts.append("   → hoist0 becomes available after Drop")
    beliefs_parts.append("")
    beliefs_parts.append("✓ ALSO RIGHT: (Lift hoist0 crate1 ...) then (Load hoist0 crate1 truck0 ...)")
    beliefs_parts.append("   → hoist0 becomes available after Load")

    beliefs_parts.append("\n=== CRITICAL: TRUCK POSITION & CONTENTS TRACKING ===")
    beliefs_parts.append("⚠️  You MUST track truck positions and contents:")
    beliefs_parts.append("")
    beliefs_parts.append("1. TRUCK POSITION:")
    beliefs_parts.append("   - After Drive: truck is NOW at destination, NOT at origin")
    beliefs_parts.append("   - Example: (Drive truck0 depot0 depot1) → truck0 is now AT depot1")
    beliefs_parts.append("   - ❌ WRONG: Unload at old location after driving away")
    beliefs_parts.append("   - ✓ RIGHT: Only Load/Unload at truck's CURRENT location")
    beliefs_parts.append("")
    beliefs_parts.append("2. TRUCK CONTENTS:")
    beliefs_parts.append("   - After Load: crate is IN truck, NOT at location")
    beliefs_parts.append("   - After Unload: crate is being LIFTED by hoist, NOT in truck")
    beliefs_parts.append("   - Example: (Load hoist0 crate0 truck0 depot0) → crate0 is now IN truck0")
    beliefs_parts.append("   - ❌ WRONG: Unload a crate that was never loaded")
    beliefs_parts.append("   - ✓ RIGHT: Only unload crates that are IN the truck")

    beliefs_parts.append("\n=== BEFORE EACH ACTION, CHECK ===")
    beliefs_parts.append("1. Is the hoist AVAILABLE? (not lifting another crate)")
    beliefs_parts.append("2. Is the truck at the right location?")
    beliefs_parts.append("3. Is the crate at the expected location/surface?")
    beliefs_parts.append("4. For Unload: Is the crate IN the truck?")
    beliefs_parts.append("5. For Lift: Is the crate CLEAR (nothing on top)?")


    beliefs_parts.append("\n=== WORKED EXAMPLE WITH STATE TRACKING ===")
    beliefs_parts.append("Scenario: crate0 on pallet0 at depot0, crate1 on pallet1 at depot1")
    beliefs_parts.append("          truck0 at depot0, hoist0 at depot0, hoist1 at depot1")
    beliefs_parts.append("Goal: crate0 on crate1 at depot1")
    beliefs_parts.append("")
    beliefs_parts.append("Initial state:")
    beliefs_parts.append("  - hoist0: AVAILABLE at depot0")
    beliefs_parts.append("  - hoist1: AVAILABLE at depot1")
    beliefs_parts.append("  - truck0: at depot0, EMPTY")
    beliefs_parts.append("  - crate0: on pallet0 at depot0")
    beliefs_parts.append("")
    beliefs_parts.append("Step-by-step with state changes:")
    beliefs_parts.append("  1. Lift hoist0 crate0 pallet0 depot0")
    beliefs_parts.append("     → State: hoist0 is now LIFTING crate0 (not available!)")
    beliefs_parts.append("     → State: crate0 is now held by hoist0 (not on pallet0)")
    beliefs_parts.append("")
    beliefs_parts.append("  2. Load hoist0 crate0 truck0 depot0")
    beliefs_parts.append("     → State: hoist0 is now AVAILABLE (released crate0)")
    beliefs_parts.append("     → State: crate0 is now IN truck0 (not held by hoist)")
    beliefs_parts.append("     → State: truck0 contains crate0")
    beliefs_parts.append("")
    beliefs_parts.append("  3. Drive truck0 depot0 depot1")
    beliefs_parts.append("     → State: truck0 is now AT depot1 (not at depot0!)")
    beliefs_parts.append("     → State: truck0 still contains crate0")
    beliefs_parts.append("")
    beliefs_parts.append("  4. Unload hoist1 crate0 truck0 depot1")
    beliefs_parts.append("     → State: hoist1 is now LIFTING crate0 (not available!)")
    beliefs_parts.append("     → State: crate0 is now held by hoist1 (not in truck)")
    beliefs_parts.append("     → State: truck0 is now EMPTY")
    beliefs_parts.append("")
    beliefs_parts.append("  5. Drop hoist1 crate0 crate1 depot1")
    beliefs_parts.append("     → State: hoist1 is now AVAILABLE (released crate0)")
    beliefs_parts.append("     → State: crate0 is now ON crate1 at depot1 ✓ GOAL ACHIEVED")
    beliefs_parts.append("")
    beliefs_parts.append("⚠️  CRITICAL: Track hoist state! After Lift/Unload, hoist is LIFTING (not available).")
    beliefs_parts.append("⚠️  CRITICAL: Track truck position! After Drive, truck is at NEW location.")
    beliefs_parts.append("⚠️  CRITICAL: Track crate location! After Load, crate is IN truck (not at depot).")

    beliefs_parts.append("\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan where each action depends on the previous one.")
    beliefs_parts.append("The plan graph must be CONNECTED - all actions form one chain/path.")
    beliefs_parts.append("Work step-by-step, one action at a time.")

    beliefs = "\n".join(beliefs_parts)

    # Build goal description
    goal_descs = []
    for pred in goal[:15]:
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            goal_descs.append(f"{parts[1]} should be at {parts[2]}")
        elif parts[0] == 'on' and len(parts) >= 3:
            goal_descs.append(f"{parts[1]} should be on {parts[2]}")

    desire = f"Goal: {'; '.join(goal_descs)}. Use Depots actions (Lift/Drop/Load/Unload/Drive) to achieve this goal."

    return beliefs, desire
