"""Domain specification layer for BDI planning.

Encapsulates domain-specific configuration (action types, required params,
DSPy Signature selection, few-shot demos, optional PDDL context) so that
``BDIPlanner`` no longer hardcodes domain behaviour in its constructor.

Built-in specs are provided for ``blocksworld``, ``logistics``, and ``depots``.
A generic PDDL spec can be constructed from raw domain PDDL text via
``DomainSpec.from_pddl()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


# ---------------------------------------------------------------------------
# PDDL parsing helpers
# ---------------------------------------------------------------------------

def extract_actions_from_pddl(pddl_text: str) -> list[dict[str, Any]]:
    """Extract action names and parameter lists from raw PDDL domain text.

    Returns a list of dicts, each with keys ``name`` and ``parameters``.
    Parameters are returned as a list of ``(name, type)`` tuples.  If no
    type is given the type string is ``"object"``.

    >>> actions = extract_actions_from_pddl("(:action pick-up :parameters (?x - block) ...)")
    >>> actions[0]["name"]
    'pick-up'
    """
    actions: list[dict[str, Any]] = []

    # Match (:action <name> :parameters (<params>) ...)
    action_pattern = re.compile(
        r"\(:action\s+([\w-]+)\s+:parameters\s*\(([^)]*)\)",
        re.IGNORECASE,
    )

    for match in action_pattern.finditer(pddl_text):
        action_name = match.group(1).strip()
        raw_params = match.group(2).strip()

        parameters: list[tuple[str, str]] = []
        if raw_params:
            # Split by "- type" groups
            # Handle: ?x - block ?y - block  OR  ?x ?y - block
            tokens = raw_params.split()
            pending_names: list[str] = []
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok.startswith("?"):
                    pending_names.append(tok.lstrip("?"))
                elif tok == "-":
                    # Next token is the type
                    if i + 1 < len(tokens):
                        ptype = tokens[i + 1]
                        for pname in pending_names:
                            parameters.append((pname, ptype))
                        pending_names = []
                        i += 1  # skip the type token
                i += 1
            # Any remaining names without explicit type
            for pname in pending_names:
                parameters.append((pname, "object"))

        actions.append({"name": action_name, "parameters": parameters})

    return actions


def build_domain_context(domain_name: str, actions: list[dict[str, Any]]) -> str:
    """Build a human-readable action schema summary for LLM prompts.

    The output is intended for the ``domain_context`` input field of
    ``GeneratePlanGeneric``.
    """
    lines = [f"Domain: {domain_name}", "", "Available actions:"]
    for act in actions:
        param_strs = [f"?{name} - {ptype}" for name, ptype in act["parameters"]]
        lines.append(f"  ({act['name']} {' '.join(param_strs)})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DomainSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainSpec:
    """Immutable specification for a planning domain.

    Bundles all domain-specific configuration that ``BDIPlanner`` needs:
    - which DSPy Signature to use,
    - valid action types and required parameters (for ``dspy.Assert``),
    - optional few-shot demo loader,
    - optional raw PDDL text and derived domain context.
    """

    name: str
    valid_action_types: frozenset[str]
    required_params: dict[str, frozenset[str]]
    signature_class: type  # DSPy Signature subclass
    demos_loader: Callable[[], list] | None = None
    pddl_domain_text: str | None = None
    domain_context: str | None = None

    # ------------------------------------------------------------------
    # Factory: built-in domains
    # ------------------------------------------------------------------

    @classmethod
    def from_name(cls, domain: str) -> DomainSpec:
        """Look up a built-in domain spec by name (backward-compatible)."""
        factories = {
            "blocksworld": cls.blocksworld,
            "logistics": cls.logistics,
            "depots": cls.depots,
            "testing": cls.testing,
        }
        factory = factories.get(domain)
        if factory is not None:
            return factory()
        raise ValueError(
            f"Unknown built-in domain '{domain}'. "
            f"Use one of {sorted(factories)} or DomainSpec.from_pddl()."
        )

    @classmethod
    def blocksworld(cls) -> DomainSpec:
        from .signatures import GeneratePlan

        return cls(
            name="blocksworld",
            valid_action_types=frozenset({"pick-up", "put-down", "stack", "unstack"}),
            required_params={
                "pick-up": frozenset({"block"}),
                "put-down": frozenset({"block"}),
                "stack": frozenset({"block", "target"}),
                "unstack": frozenset({"block", "target"}),
            },
            signature_class=GeneratePlan,
        )

    @classmethod
    def logistics(cls) -> DomainSpec:
        from .signatures import GeneratePlanLogistics

        return cls(
            name="logistics",
            valid_action_types=frozenset({
                "load-truck", "unload-truck", "load-airplane",
                "unload-airplane", "drive-truck", "fly-airplane",
            }),
            required_params={
                "load-truck": frozenset({"obj", "truck", "loc"}),
                "unload-truck": frozenset({"obj", "truck", "loc"}),
                "load-airplane": frozenset({"obj", "airplane", "loc"}),
                "unload-airplane": frozenset({"obj", "airplane", "loc"}),
                "drive-truck": frozenset({"truck", "from", "to", "city"}),
                "fly-airplane": frozenset({"airplane", "from", "to"}),
            },
            signature_class=GeneratePlanLogistics,
            demos_loader=_build_logistics_demos,
        )

    @classmethod
    def depots(cls) -> DomainSpec:
        from .signatures import GeneratePlanDepots

        return cls(
            name="depots",
            valid_action_types=frozenset({"drive", "lift", "drop", "load", "unload"}),
            required_params={
                "drive": frozenset({"truck", "from", "to"}),
                "lift": frozenset({"hoist", "crate", "surface", "place"}),
                "drop": frozenset({"hoist", "crate", "surface", "place"}),
                "load": frozenset({"hoist", "crate", "truck", "place"}),
                "unload": frozenset({"hoist", "crate", "truck", "place"}),
            },
            signature_class=GeneratePlanDepots,
        )

    @classmethod
    def testing(cls) -> DomainSpec:
        """Minimal spec for unit tests — no action-type validation."""
        from .signatures import GeneratePlan

        return cls(
            name="testing",
            valid_action_types=frozenset(),
            required_params={},
            signature_class=GeneratePlan,
        )

    # ------------------------------------------------------------------
    # Factory: generic PDDL
    # ------------------------------------------------------------------

    @classmethod
    def from_pddl(cls, domain_name: str, pddl_text: str) -> DomainSpec:
        """Build a DomainSpec from raw PDDL domain text.

        Action types and a human-readable ``domain_context`` are extracted
        automatically.  No action-type validation is enforced at the planner
        level (VAL handles that).
        """
        from .signatures import GeneratePlanGeneric

        actions = extract_actions_from_pddl(pddl_text)
        action_names = frozenset(a["name"] for a in actions)
        context = build_domain_context(domain_name, actions)

        return cls(
            name=domain_name,
            valid_action_types=action_names,
            required_params={},  # rely on VAL for param validation
            signature_class=GeneratePlanGeneric,
            pddl_domain_text=pddl_text,
            domain_context=context,
        )


# ---------------------------------------------------------------------------
# Demo loader (extracted from BDIPlanner._build_logistics_demos)
# ---------------------------------------------------------------------------

def _build_logistics_demos() -> list:
    """Build few-shot demonstrations for the Logistics domain.

    Loads demonstrations from ``src/bdi_llm/data/logistics_demos.yaml``.
    """
    from ..schemas import ActionNode, BDIPlan, DependencyEdge

    try:
        import dspy
    except ImportError:
        return []

    data_path = Path(__file__).parent.parent / "data" / "logistics_demos.yaml"

    if not data_path.exists():
        return []

    with open(data_path) as f:
        data = yaml.safe_load(f)

    demos = []
    for demo_data in data.get("demos", []):
        nodes_data = demo_data["plan"]["nodes"]
        edges_data = demo_data["plan"]["edges"]

        nodes = [ActionNode(**n) for n in nodes_data]
        edges = [DependencyEdge(**e) for e in edges_data]

        plan = BDIPlan(
            goal_description=demo_data["plan"]["goal_description"],
            nodes=nodes,
            edges=edges,
        )

        demos.append(
            dspy.Example(
                beliefs=demo_data["beliefs"],
                desire=demo_data["desire"],
                plan=plan,
            ).with_inputs("beliefs", "desire")
        )

    return demos
