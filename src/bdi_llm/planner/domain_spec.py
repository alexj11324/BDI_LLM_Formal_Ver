"""Domain specification layer for BDI planning.

Encapsulates domain-specific configuration (action types, required params,
DSPy Signature selection, few-shot demos, optional PDDL context) so that
``BDIPlanner`` no longer hardcodes domain behaviour in its constructor.

Built-in specs are provided for ``blocksworld``, ``logistics``, and ``depots``.
A generic PDDL spec can be constructed from raw domain PDDL text via
``DomainSpec.from_pddl()``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


# ---------------------------------------------------------------------------
# PDDL parsing helpers
# ---------------------------------------------------------------------------

def extract_domain_name_from_pddl(pddl_text: str) -> str | None:
    """Extract the domain name from a PDDL ``(define (domain ...))`` header.

    Returns ``None`` if no match is found.
    """
    match = re.search(
        r"\(\s*define\s+\(\s*domain\s+([\w-]+)\s*\)",
        pddl_text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _find_matching_paren(text: str, open_idx: int) -> int | None:
    """Return the index of the closing paren matching *open_idx*."""
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _extract_parenthesized_expr(block_text: str, keyword: str) -> str:
    """Extract the balanced parenthesized expression after a PDDL keyword."""
    match = re.search(rf":{keyword}\b", block_text, re.IGNORECASE)
    if not match:
        return ""

    open_idx = block_text.find("(", match.end())
    if open_idx == -1:
        return ""

    close_idx = _find_matching_paren(block_text, open_idx)
    if close_idx is None:
        return ""
    return block_text[open_idx:close_idx + 1]


def _parse_typed_parameters(raw_params: str) -> list[tuple[str, str]]:
    """Parse PDDL parameter declarations into ``(name, type)`` tuples."""
    parameters: list[tuple[str, str]] = []
    if not raw_params:
        return parameters

    tokens = raw_params.split()
    pending_names: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("?"):
            pending_names.append(tok.lstrip("?"))
        elif tok == "-":
            if i + 1 < len(tokens):
                ptype = tokens[i + 1]
                for pname in pending_names:
                    parameters.append((pname, ptype))
                pending_names = []
                i += 1
        i += 1

    for pname in pending_names:
        parameters.append((pname, "object"))

    return parameters


def _normalise_literal(literal: str) -> str:
    """Collapse whitespace inside a PDDL literal."""
    return re.sub(r"\s+", " ", literal).strip()


def _extract_literals(expr: str) -> list[str]:
    """Extract positive literals from a parenthesized PDDL expression."""
    if not expr:
        return []

    literals = [
        _normalise_literal(lit)
        for lit in re.findall(r"\(([^()]+)\)", expr)
    ]
    return [lit for lit in literals if lit and lit.lower() != "and"]


def _extract_effect_literals(expr: str) -> tuple[list[str], list[str]]:
    """Extract add and delete effect literals from a PDDL effect expression."""
    if not expr:
        return [], []

    delete_literals = [
        _normalise_literal(lit)
        for lit in re.findall(r"\(not\s+\(([^()]+)\)\)", expr, re.IGNORECASE)
    ]
    positive_expr = re.sub(r"\(not\s+\([^()]+\)\)", "", expr, flags=re.IGNORECASE)
    add_literals = _extract_literals(positive_expr)
    return add_literals, delete_literals

def extract_actions_from_pddl(pddl_text: str) -> list[dict[str, Any]]:
    """Extract action schema details from raw PDDL domain text.

    Returns a list of dicts, each with keys:

    - ``name``
    - ``parameters``
    - ``preconditions``
    - ``effects_add``
    - ``effects_del``

    Parameters are returned as a list of ``(name, type)`` tuples. If no type
    is given the type string is ``"object"``.

    >>> actions = extract_actions_from_pddl("(:action pick-up :parameters (?x - block) ...)")
    >>> actions[0]["name"]
    'pick-up'
    """
    actions: list[dict[str, Any]] = []

    for match in re.finditer(r"\(:action\s+([\w-]+)", pddl_text, re.IGNORECASE):
        action_name = match.group(1).strip()
        block_start = match.start()
        block_end = _find_matching_paren(pddl_text, block_start)
        if block_end is None:
            continue

        block_text = pddl_text[block_start:block_end + 1]
        params_expr = _extract_parenthesized_expr(block_text, "parameters")
        precond_expr = _extract_parenthesized_expr(block_text, "precondition")
        effect_expr = _extract_parenthesized_expr(block_text, "effect")

        raw_params = params_expr[1:-1].strip() if params_expr else ""
        parameters = _parse_typed_parameters(raw_params)
        preconditions = _extract_literals(precond_expr)
        effects_add, effects_del = _extract_effect_literals(effect_expr)

        actions.append(
            {
                "name": action_name,
                "parameters": parameters,
                "preconditions": preconditions,
                "effects_add": effects_add,
                "effects_del": effects_del,
            }
        )

    return actions


def build_domain_context(domain_name: str, actions: list[dict[str, Any]]) -> str:
    """Build a human-readable action schema summary for LLM prompts.

    The output is intended for the ``domain_context`` input field of
    ``GeneratePlanGeneric``.
    """
    lines = [
        f"Domain: {domain_name}",
        "",
        "Available actions and transitions:",
    ]
    for act in actions:
        param_strs = [f"?{name} - {ptype}" for name, ptype in act["parameters"]]
        signature = f"({act['name']} {' '.join(param_strs)})".strip()
        lines.append(f"  {signature}")

        preconditions = act.get("preconditions", [])
        effects_add = act.get("effects_add", [])
        effects_del = act.get("effects_del", [])

        lines.append("    Preconditions:")
        if preconditions:
            lines.extend(f"      - ({literal})" for literal in preconditions)
        else:
            lines.append("      - (none)")

        lines.append("    Effects (add):")
        if effects_add:
            lines.extend(f"      - ({literal})" for literal in effects_add)
        else:
            lines.append("      - (none)")

        lines.append("    Effects (delete):")
        if effects_del:
            lines.extend(f"      - ({literal})" for literal in effects_del)
        else:
            lines.append("      - (none)")

    return "\n".join(lines)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _planbench_root() -> Path:
    return _project_root() / "workspaces" / "planbench_data" / "plan-bench"


def load_planbench_domain_config(domain_name: str) -> dict[str, Any] | None:
    """Load a PlanBench domain config YAML when present."""
    config_path = _planbench_root() / "configs" / f"{domain_name}.yaml"
    if not config_path.exists():
        return None
    return yaml.safe_load(config_path.read_text())


def load_planbench_domain_intro(domain_name: str) -> str | None:
    """Return PlanBench ``domain_intro`` text for a domain when available."""
    config = load_planbench_domain_config(domain_name)
    if not config:
        return None
    intro = config.get("domain_intro")
    return intro.strip() if isinstance(intro, str) and intro.strip() else None


def _resolve_planbench_prompt_file(domain_name: str) -> Path | None:
    prompt_path = _planbench_root() / "prompts" / domain_name / "task_1_plan_generation.json"
    return prompt_path if prompt_path.exists() else None


def _decode_planbench_symbol(token: str, config: dict[str, Any] | None) -> str:
    """Decode compact PlanBench object aliases like ``o8`` to ``object_8``."""
    if config:
        encoded = config.get("encoded_objects") or {}
        for prefix, template in encoded.items():
            if not isinstance(prefix, str) or not isinstance(template, str):
                continue
            match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", token)
            if match:
                return template.format(match.group(1))

    fallback_match = re.fullmatch(r"o(\d+)", token)
    if fallback_match:
        return f"object_{fallback_match.group(1)}"
    return token


def _encode_planbench_symbol(token: str, config: dict[str, Any] | None) -> str:
    """Encode prompt-friendly symbols like ``object_8`` back to ``o8``."""
    if config:
        encoded = config.get("encoded_objects") or {}
        for prefix, template in encoded.items():
            if not isinstance(prefix, str) or not isinstance(template, str):
                continue
            if "{}" in template:
                pattern = re.escape(template).replace(re.escape("{}"), r"(\d+)")
                match = re.fullmatch(pattern, token)
                if match:
                    return f"{prefix}{match.group(1)}"
            elif token == template:
                return prefix

    fallback_match = re.fullmatch(r"object_(\d+)", token)
    if fallback_match:
        return f"o{fallback_match.group(1)}"
    return token


def _map_planbench_predicate_symbols(
    predicates: list[str],
    config: dict[str, Any] | None,
    symbol_mapper,
) -> list[str]:
    """Rewrite object symbols inside predicate strings via *symbol_mapper*."""
    mapped: list[str] = []
    for predicate in predicates:
        parts = predicate.split()
        if not parts:
            continue
        head, *args = parts
        mapped_args = [symbol_mapper(arg, config) for arg in args]
        mapped.append(" ".join([head, *mapped_args]))
    return mapped


def promptify_planbench_predicates(domain_name: str, predicates: list[str]) -> list[str]:
    """Convert raw PDDL object aliases to prompt-friendly PlanBench symbols."""
    config = load_planbench_domain_config(domain_name)
    return _map_planbench_predicate_symbols(predicates, config, _decode_planbench_symbol)


def pddlify_planbench_symbol(domain_name: str, token: str) -> str:
    """Convert prompt-friendly PlanBench symbols back to raw PDDL aliases."""
    config = load_planbench_domain_config(domain_name)
    return _encode_planbench_symbol(token, config)


def decode_planbench_literals(domain_name: str, predicates: list[str]) -> list[str]:
    """Backward-compatible alias: raw PDDL aliases → prompt-friendly symbols."""
    return promptify_planbench_predicates(domain_name, predicates)


def encode_planbench_symbol(domain_name: str, token: str) -> str:
    """Backward-compatible alias: prompt-friendly symbol → raw PDDL alias."""
    return pddlify_planbench_symbol(domain_name, token)


def _parse_planbench_statement(statement_text: str, domain_intro: str) -> tuple[str, str] | None:
    """Split a PlanBench ``[STATEMENT]`` block into beliefs and desire."""
    match = re.search(
        r"As initial conditions I have that,\s*(.*?)\.\s*My goal is to have that\s*(.*?)\.",
        statement_text,
        re.DOTALL,
    )
    if not match:
        return None

    initial_conditions = match.group(1).strip()
    goal_conditions = match.group(2).strip()
    beliefs = f"{domain_intro.strip()}\n\nAs initial conditions I have that, {initial_conditions}."
    desire = f"My goal is to have that {goal_conditions}."
    return beliefs, desire


def _build_sequential_demo_plan(
    plan_text: str,
    action_param_order: dict[str, list[str]],
    goal_description: str,
    config: dict[str, Any] | None = None,
):
    """Convert a linear PlanBench ground-truth plan into a simple ``BDIPlan``."""
    from ..schemas import ActionNode, BDIPlan, DependencyEdge

    schema_by_action = {name.lower(): params for name, params in action_param_order.items()}
    nodes: list[ActionNode] = []
    edges: list[DependencyEdge] = []

    for idx, raw_line in enumerate(plan_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        line = line.strip("()")
        parts = line.split()
        if not parts:
            continue

        action_name = parts[0]
        args = [_decode_planbench_symbol(arg, config) for arg in parts[1:]]
        param_names = schema_by_action.get(action_name.lower(), [])
        params = {
            param_names[pos] if pos < len(param_names) else f"arg{pos + 1}": value
            for pos, value in enumerate(args)
        }
        node_id = f"s{len(nodes) + 1}"
        nodes.append(
            ActionNode(
                id=node_id,
                action_type=action_name,
                description=line,
                params=params,
            )
        )
        if len(nodes) >= 2:
            edges.append(
                DependencyEdge(
                    source=nodes[-2].id,
                    target=node_id,
                    relationship="sequential",
                )
            )

    return BDIPlan(goal_description=goal_description, nodes=nodes, edges=edges)


def _build_planbench_obfuscated_demos(
    domain_name: str,
    actions: list[dict[str, Any]],
    domain_context: str,
) -> list:
    """Load one-shot PlanBench examples for obfuscated domains when available."""
    try:
        import dspy
    except ImportError:
        return []

    prompt_file = _resolve_planbench_prompt_file(domain_name)
    if prompt_file is None:
        return []

    payload = json.loads(prompt_file.read_text())
    instances = payload.get("instances") or []
    if not instances:
        return []

    config = load_planbench_domain_config(domain_name)
    domain_intro = load_planbench_domain_intro(domain_name)
    if not domain_intro:
        return []

    action_param_order = {
        action["name"]: [param_name for param_name, _ptype in action["parameters"]]
        for action in actions
    }

    demos = []
    for instance in instances[:1]:
        query = instance.get("query", "")
        parts = re.split(r"\[STATEMENT\]|\[PLAN\]|\[PLAN END\]", query)
        if len(parts) < 3:
            continue

        statement_text = parts[1].strip()
        beliefs_desire = _parse_planbench_statement(statement_text, domain_intro)
        if not beliefs_desire:
            continue
        beliefs, desire = beliefs_desire

        plan = _build_sequential_demo_plan(
            instance.get("ground_truth_plan", ""),
            action_param_order=action_param_order,
            goal_description=desire,
            config=config,
        )
        if not plan.nodes:
            continue

        demos.append(
            dspy.Example(
                beliefs=beliefs,
                desire=desire,
                domain_context=domain_context,
                plan=plan,
            ).with_inputs("beliefs", "desire", "domain_context")
        )

    return demos


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

        demos_loader = None
        if domain_name.startswith("obfuscated_") and _resolve_planbench_prompt_file(domain_name):
            demos_loader = lambda: _build_planbench_obfuscated_demos(
                domain_name=domain_name,
                actions=actions,
                domain_context=context,
            )

        return cls(
            name=domain_name,
            valid_action_types=action_names,
            required_params={},  # rely on VAL for param validation
            signature_class=GeneratePlanGeneric,
            demos_loader=demos_loader,
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
