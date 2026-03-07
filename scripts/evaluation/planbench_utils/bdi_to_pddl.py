"""
BDI Plan to PDDL Action Conversion
====================================

Converts BDI action nodes (from BDIPlan) into PDDL action strings
suitable for VAL verification.
"""
from typing import Dict, List

from bdi_llm.schemas import BDIPlan


def bdi_to_pddl_actions(plan: BDIPlan, domain: str = "blocksworld") -> List[str]:
    """
    Convert BDI action nodes to PDDL action strings

    Args:
        plan: BDIPlan with action nodes
        domain: PDDL domain (default: blocksworld)

    Returns:
        List of PDDL action strings, e.g., ["(pick-up a)", "(stack a b)"]
    """
    pddl_actions = []

    # Get topological order of actions
    G = plan.to_networkx()

    # Filter out virtual nodes
    virtual_nodes = {"__START__", "__END__"}

    try:
        import networkx as nx
        ordered_nodes = [n for n in nx.topological_sort(G) if n not in virtual_nodes]
    except:
        # If cycles, use node order as-is
        ordered_nodes = [node.id for node in plan.nodes if node.id not in virtual_nodes]

    # Create node lookup
    node_lookup = {n.id: n for n in plan.nodes}

    # Normalise action_type string to a canonical key
    def _normalise(atype: str) -> str:
        t = atype.lower().replace("-", "").replace("_", "").strip()
        if t == "pickup":
            return "pick-up"
        if t == "putdown":
            return "put-down"
        if t.startswith("unstack"):
            return "unstack"
        if t.startswith("stack"):
            return "stack"

        # Logistics
        if t == "loadtruck": return "load-truck"
        if t == "unloadtruck": return "unload-truck"
        if t == "loadairplane": return "load-airplane"
        if t == "unloadairplane": return "unload-airplane"
        if t == "drivetruck": return "drive-truck"
        if t == "flyairplane": return "fly-airplane"

        return t

    # Normalise parameters
    def _normalise_param(val: str) -> str:
        if not val:
            return ""
        s = str(val).lower().strip()
        # Remove "block " prefix if present (common LLM artifact)
        if s.startswith("block "):
            s = s[6:].strip()
        return s

    def _pick_param(params: Dict, keys: List[str]) -> str:
        for key in keys:
            value = params.get(key)
            if value:
                return _normalise_param(value)
        return ""

    # Convert each action to PDDL format using params deterministically
    for node_id in ordered_nodes:
        action_node = node_lookup.get(node_id)
        if not action_node:
            continue

        raw_action = action_node.action_type.strip()
        if raw_action.startswith("(") and raw_action.endswith(")"):
            pddl_actions.append(" ".join(raw_action.split()))
            continue

        canon = _normalise(action_node.action_type)
        params = action_node.params
        before_len = len(pddl_actions)

        if domain == "blocksworld":
            block = _pick_param(params, ["block", "object", "obj", "x"]) \
                or _normalise_param(next(iter(params.values()), ""))
            target = _pick_param(params, ["target", "y", "to", "on"]) \
                or _normalise_param(next(iter(list(params.values())[1:]), ""))

            if canon == "pick-up" and block:
                pddl_actions.append(f"(pick-up {block})")
            elif canon == "put-down" and block:
                pddl_actions.append(f"(put-down {block})")
            elif canon == "stack" and block and target:
                pddl_actions.append(f"(stack {block} {target})")
            elif canon == "unstack" and block and target:
                pddl_actions.append(f"(unstack {block} {target})")

        elif domain == "logistics":
            # Enhanced parameter extraction with more variations and fallbacks
            # Try multiple parameter name variations
            obj = _pick_param(params, ["obj", "object", "package", "pkg", "p", "item", "package_name", "obj_name"])
            truck = _pick_param(params, ["truck", "vehicle", "t", "truck_name", "veh"])
            airplane = _pick_param(params, ["airplane", "plane", "a", "airplane_name", "aircraft"])
            loc = _pick_param(params, ["loc", "location", "l", "at", "place", "loc_name", "location_name"])
            loc_from = _pick_param(params, ["from", "source", "origin", "loc_from", "from_loc", "start"])
            loc_to = _pick_param(params, ["to", "dest", "destination", "target", "loc_to", "to_loc", "end"])
            city = _pick_param(params, ["city", "c", "city_name"])

            # Fallback: try to extract from description if parameters are missing
            description = action_node.description.lower() if hasattr(action_node, 'description') and action_node.description else ""

            # Fallback: use positional parameters if named parameters fail
            param_values = list(params.values())

            if canon == "load-truck":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not truck and len(param_values) >= 2:
                    truck = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and truck and loc:
                    pddl_actions.append(f"(LOAD-TRUCK {obj} {truck} {loc})")
                else:
                    print(f"    DEBUG: load-truck missing params - obj={obj}, truck={truck}, loc={loc}, params={params}")

            elif canon == "load-airplane":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not airplane and len(param_values) >= 2:
                    airplane = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and airplane and loc:
                    pddl_actions.append(f"(LOAD-AIRPLANE {obj} {airplane} {loc})")
                else:
                    print(f"    DEBUG: load-airplane missing params - obj={obj}, airplane={airplane}, loc={loc}, params={params}")

            elif canon == "unload-truck":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not truck and len(param_values) >= 2:
                    truck = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and truck and loc:
                    pddl_actions.append(f"(UNLOAD-TRUCK {obj} {truck} {loc})")
                else:
                    print(f"    DEBUG: unload-truck missing params - obj={obj}, truck={truck}, loc={loc}, params={params}")

            elif canon == "unload-airplane":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not airplane and len(param_values) >= 2:
                    airplane = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and airplane and loc:
                    pddl_actions.append(f"(UNLOAD-AIRPLANE {obj} {airplane} {loc})")
                else:
                    print(f"    DEBUG: unload-airplane missing params - obj={obj}, airplane={airplane}, loc={loc}, params={params}")

            elif canon == "drive-truck":
                if not truck and len(param_values) >= 1:
                    truck = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])
                if not city and len(param_values) >= 4:
                    city = _normalise_param(param_values[3])

                if truck and loc_from and loc_to and city:
                    pddl_actions.append(f"(DRIVE-TRUCK {truck} {loc_from} {loc_to} {city})")
                else:
                    print(f"    DEBUG: drive-truck missing params - truck={truck}, from={loc_from}, to={loc_to}, city={city}, params={params}")

            elif canon == "fly-airplane":
                if not airplane and len(param_values) >= 1:
                    airplane = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])

                if airplane and loc_from and loc_to:
                    pddl_actions.append(f"(FLY-AIRPLANE {airplane} {loc_from} {loc_to})")
                else:
                    print(f"    DEBUG: fly-airplane missing params - airplane={airplane}, from={loc_from}, to={loc_to}, params={params}")

        elif domain == "depots":
            # Depots combines logistics and blocksworld
            # Actions: Drive, Lift, Drop, Load, Unload
            # Domain PDDL signature reference:
            #   Drive(?x - truck ?y - place ?z - place)
            #   Lift(?x - hoist ?y - crate ?z - surface ?p - place)
            #   Drop(?x - hoist ?y - crate ?z - surface ?p - place)
            #   Load(?x - hoist ?y - crate ?z - truck ?p - place)
            #   Unload(?x - hoist ?y - crate ?z - truck ?p - place)
            hoist = _pick_param(params, [
                "hoist", "h", "x", "hoist_name", "lifter",
            ])
            crate = _pick_param(params, [
                "crate", "c", "obj", "object", "y", "item", "package",
                "crate_name", "cargo", "box",
            ])
            truck = _pick_param(params, [
                "truck", "t", "vehicle", "z", "truck_name", "veh",
            ])
            surface = _pick_param(params, [
                "surface", "s", "pallet", "z", "on", "target", "dest",
                "surface_name", "onto", "below", "under",
            ])
            loc = _pick_param(params, [
                "loc", "location", "place", "p", "at", "depot",
                "loc_name", "location_name", "position", "area",
            ])
            loc_from = _pick_param(params, [
                "from", "loc_from", "from_loc", "from_location",
                "source", "origin", "start", "y",
            ])
            loc_to = _pick_param(params, [
                "to", "loc_to", "to_loc", "to_location",
                "dest", "destination", "target", "end", "z",
            ])

            # Positional fallback using param_values
            param_values = list(params.values())

            if canon == "drive":
                # Drive(?x - truck ?y - place ?z - place)
                if not truck and len(param_values) >= 1:
                    truck = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])

                if truck and loc_from and loc_to:
                    pddl_actions.append(f"(Drive {truck} {loc_from} {loc_to})")
                else:
                    print(f"    DEBUG: drive missing params - truck={truck}, from={loc_from}, to={loc_to}, params={params}")

            elif canon == "lift":
                # Lift(?x - hoist ?y - crate ?z - surface ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not surface and len(param_values) >= 3:
                    surface = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                if hoist and crate and surface and loc:
                    pddl_actions.append(f"(Lift {hoist} {crate} {surface} {loc})")
                else:
                    print(f"    DEBUG: lift missing params - hoist={hoist}, crate={crate}, surface={surface}, loc={loc}, params={params}")

            elif canon == "drop":
                # Drop(?x - hoist ?y - crate ?z - surface ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not surface and len(param_values) >= 3:
                    surface = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                if hoist and crate and surface and loc:
                    pddl_actions.append(f"(Drop {hoist} {crate} {surface} {loc})")
                else:
                    print(f"    DEBUG: drop missing params - hoist={hoist}, crate={crate}, surface={surface}, loc={loc}, params={params}")

            elif canon == "load":
                # Load(?x - hoist ?y - crate ?z - truck ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not truck and len(param_values) >= 3:
                    truck = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                if hoist and crate and truck and loc:
                    pddl_actions.append(f"(Load {hoist} {crate} {truck} {loc})")
                else:
                    print(f"    DEBUG: load missing params - hoist={hoist}, crate={crate}, truck={truck}, loc={loc}, params={params}")

            elif canon == "unload":
                # Unload(?x - hoist ?y - crate ?z - truck ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not truck and len(param_values) >= 3:
                    truck = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                if hoist and crate and truck and loc:
                    pddl_actions.append(f"(Unload {hoist} {crate} {truck} {loc})")
                else:
                    print(f"    DEBUG: unload missing params - hoist={hoist}, crate={crate}, truck={truck}, loc={loc}, params={params}")

        if len(pddl_actions) == before_len:
            print(
                f"    ⚠️  WARNING: Skipped action '{action_node.action_type}' (canon: {canon}) with params {params} for domain '{domain}'"
            )

    return pddl_actions
