"""Higher-level planning abstractions for benchmark integration.

Defines:

* ``PlanningTask`` — a normalised planning input that any planner can consume.
* ``TaskAdapter``  — converts benchmark-native data into ``PlanningTask``.
* ``PlanSerializer`` — converts ``BDIPlan`` back into benchmark-native output.

Built-in implementations are provided for **PDDL** domains:

* ``PDDLTaskAdapter``   — builds a ``PlanningTask`` from PDDL problem text.
* ``PDDLPlanSerializer`` — extracts a PDDL action sequence from a ``BDIPlan``.

Non-PDDL benchmarks (e.g. TravelPlanner) only need to supply their own
``TaskAdapter`` and ``PlanSerializer`` in a future branch.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .schemas import BDIPlan


# ---------------------------------------------------------------------------
# Core abstractions
# ---------------------------------------------------------------------------

@dataclass
class PlanningTask:
    """Normalised planner input — decoupled from any specific benchmark."""

    task_id: str
    domain_name: str
    beliefs: str
    desire: str
    domain_context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskAdapter(ABC):
    """Transforms benchmark-native data into a ``PlanningTask``."""

    @abstractmethod
    def to_planning_task(self, raw_input: Any) -> PlanningTask:
        ...


class PlanSerializer(ABC):
    """Converts planner output (``BDIPlan``) into benchmark-native format."""

    @abstractmethod
    def from_bdi_plan(self, plan: BDIPlan, task: PlanningTask) -> Any:
        ...


# ---------------------------------------------------------------------------
# PDDL implementations
# ---------------------------------------------------------------------------

def _parse_pddl_objects(text: str) -> str:
    """Extract and format :objects block into human-readable list.

    Handles typed objects like ``blockA blockB - block`` and untyped objects.
    """
    match = re.search(
        r"\(:objects\s+(.*?)\)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""

    raw = match.group(1).strip()
    if not raw:
        return ""

    lines: list[str] = []
    tokens = raw.split()
    pending: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "-":
            if i + 1 < len(tokens):
                obj_type = tokens[i + 1]
                for obj in pending:
                    lines.append(f"  {obj} (type: {obj_type})")
                pending = []
                i += 1  # skip type token
        else:
            pending.append(tok)
        i += 1
    # Remaining untyped objects
    for obj in pending:
        lines.append(f"  {obj}")

    return "Objects:\n" + "\n".join(lines)


def _parse_pddl_init(text: str) -> str:
    """Extract :init predicates into a structured beliefs string."""
    match = re.search(
        r"\(:init\s+(.*?)\)\s*(?:\(:goal|\(:objects|\(:metric|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return text.strip()

    raw = match.group(1).strip()
    # Extract individual predicates: (pred arg1 arg2 ...)
    predicates = re.findall(r"\(([^()]+)\)", raw)
    lines = [f"  ({p.strip()})" for p in predicates if p.strip()]
    return "Initial state:\n" + "\n".join(lines)


def _parse_pddl_goal(text: str) -> str:
    """Extract :goal content into a desire string.

    Handles ``(and ...)`` wrapped goals and bare single-predicate goals.
    """
    # Match :goal block — greedy up to the last closing paren
    match = re.search(
        r"\(:goal\s+(.*)\)\s*\)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""

    raw = match.group(1).strip()

    # Unwrap (and ...) if present
    and_match = re.match(r"^\(and\s+(.*)\)$", raw, re.DOTALL | re.IGNORECASE)
    if and_match:
        raw = and_match.group(1).strip()

    predicates = re.findall(r"\(([^()]+)\)", raw)
    if not predicates:
        return raw

    lines = [f"  ({p.strip()})" for p in predicates if p.strip()]
    return "Goal conditions:\n" + "\n".join(lines)


def _extract_pddl_predicates(text: str, section: str) -> list[str]:
    """Extract predicate strings from a PDDL section block."""
    if section == "init":
        match = re.search(
            r"\(:init\s+(.*?)\)\s*(?:\(:goal|\(:objects|\(:metric|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return []
        raw = match.group(1).strip()
    elif section == "goal":
        match = re.search(r"\(:goal\s+(.*)\)\s*\)", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return []
        raw = match.group(1).strip()
        and_match = re.match(r"^\(and\s+(.*)\)$", raw, re.DOTALL | re.IGNORECASE)
        if and_match:
            raw = and_match.group(1).strip()
    else:
        raise ValueError(f"Unsupported section: {section}")

    return [p.strip() for p in re.findall(r"\(([^()]+)\)", raw) if p.strip()]


def _natural_predicate_list(predicates: list[str]) -> str:
    """Join predicate strings into a sentence fragment."""
    if not predicates:
        return "nothing"
    if len(predicates) == 1:
        return predicates[0]
    if len(predicates) == 2:
        return f"{predicates[0]} and {predicates[1]}"
    return ", ".join(predicates[:-1]) + f" and {predicates[-1]}"


class PDDLTaskAdapter(TaskAdapter):
    """Convert a PDDL problem file (+ optional domain context) into a ``PlanningTask``.

    This adapter performs a **generic** PDDL-to-prompt conversion:

    * ``:objects`` → typed object listing in beliefs
    * ``:init``    → structured predicate listing in beliefs
    * ``:goal``    → structured goal conditions as desire
    * ``domain_context`` → action schema summary (from ``DomainSpec``)

    Parameters
    ----------
    domain_name : str
        Human-readable domain name (e.g. ``"gripper"``).
    domain_context : str | None
        Action-schema summary string (from ``build_domain_context``).
    """

    def __init__(
        self,
        domain_name: str,
        domain_context: str | None = None,
        domain_intro: str | None = None,
    ):
        self.domain_name = domain_name
        self.domain_context = domain_context
        if domain_intro is None:
            try:
                from .planner.domain_spec import load_planbench_domain_intro

                domain_intro = load_planbench_domain_intro(domain_name)
            except Exception:
                domain_intro = None
        self.domain_intro = domain_intro

    def to_planning_task(self, raw_input: Any) -> PlanningTask:
        """Build a ``PlanningTask`` from a PDDL problem dict or file path.

        *raw_input* may be:

        * ``str`` — path to a ``.pddl`` problem file.
        * ``dict`` with key ``problem_text`` and optional ``task_id``.
        """
        if isinstance(raw_input, str):
            from pathlib import Path

            path = Path(raw_input)
            if not path.exists():
                raise FileNotFoundError(f"Problem file not found: {path}")
            problem_text = path.read_text()
            task_id = path.stem
        elif isinstance(raw_input, dict):
            problem_text = raw_input["problem_text"]
            task_id = raw_input.get("task_id", str(uuid.uuid4())[:8])
        else:
            raise TypeError(f"Unsupported raw_input type: {type(raw_input)}")

        beliefs = self._build_beliefs(problem_text)
        desire = self._build_desire(problem_text)

        return PlanningTask(
            task_id=task_id,
            domain_name=self.domain_name,
            beliefs=beliefs,
            desire=desire,
            domain_context=self.domain_context,
            metadata={"problem_text": problem_text},
        )

    def _build_beliefs(self, problem_text: str) -> str:
        """Assemble beliefs from :objects + :init blocks."""
        if self.domain_intro:
            from .planner.domain_spec import decode_planbench_literals

            init_preds = _extract_pddl_predicates(problem_text, "init")
            init_preds = decode_planbench_literals(self.domain_name, init_preds)
            init_text = _natural_predicate_list(init_preds)
            return (
                f"{self.domain_intro.strip()}\n\n"
                f"As initial conditions I have that, {init_text}."
            )

        parts: list[str] = []

        objects_str = _parse_pddl_objects(problem_text)
        if objects_str:
            parts.append(objects_str)

        init_str = _parse_pddl_init(problem_text)
        if init_str:
            parts.append(init_str)

        return "\n\n".join(parts) if parts else problem_text.strip()

    def _build_desire(self, problem_text: str) -> str:
        """Assemble desire from :goal block."""
        if self.domain_intro:
            from .planner.domain_spec import decode_planbench_literals

            goal_preds = _extract_pddl_predicates(problem_text, "goal")
            goal_preds = decode_planbench_literals(self.domain_name, goal_preds)
            goal_text = _natural_predicate_list(goal_preds)
            return (
                f"My goal is to have that {goal_text}.\n\n"
                "Generate a sequential connected plan using only the available actions."
            )

        desire = _parse_pddl_goal(problem_text)
        return desire if desire else "Achieve the goal state."


class PDDLPlanSerializer(PlanSerializer):
    """Extract a list of PDDL action strings from a ``BDIPlan``.

    Parameters
    ----------
    param_order_map : dict[str, list[str]] | None
        Maps action name → ordered list of parameter names as defined in
        the PDDL domain schema.  When provided, parameters are emitted in
        schema order; when ``None``, falls back to dict insertion order.
    """

    def __init__(self, param_order_map: dict[str, list[str]] | None = None):
        self._param_order_map = param_order_map or {}
        self._schema_by_action = {
            self._normalise_symbol(action_name): (action_name, params)
            for action_name, params in self._param_order_map.items()
        }

    @staticmethod
    def _normalise_symbol(value: str) -> str:
        """Normalise PDDL-ish identifiers for schema lookup.

        Generic PDDL plans often round-trip through structured output parsers
        that rewrite ``loc-from`` to ``loc_from``. We treat hyphens and
        underscores as equivalent for action / parameter matching.
        """
        return str(value).strip().lower().lstrip("?").replace("_", "-")

    def _ordered_param_values(
        self,
        params: dict[str, object] | None,
        schema_order: list[str],
    ) -> list[str]:
        """Resolve parameter values in schema order with alias + positional fallback."""
        if not params:
            return [""] * len(schema_order)

        items = list(params.items())
        used_indices: set[int] = set()
        normalised_indices: dict[str, list[int]] = {}
        for idx, (key, _value) in enumerate(items):
            normalised_indices.setdefault(self._normalise_symbol(key), []).append(idx)

        resolved: list[str] = []
        for expected in schema_order:
            expected_key = self._normalise_symbol(expected)
            match_idx: int | None = None

            for idx in normalised_indices.get(expected_key, []):
                if idx in used_indices:
                    continue
                value = items[idx][1]
                if value is None or value == "":
                    continue
                match_idx = idx
                break

            if match_idx is None:
                # Fall back to the next unused positional parameter. This keeps
                # generic domains usable when the LLM chooses semantically
                # different names than the PDDL schema.
                for idx, (_key, value) in enumerate(items):
                    if idx in used_indices:
                        continue
                    if value is None or value == "":
                        continue
                    match_idx = idx
                    break

            if match_idx is None:
                resolved.append("")
                continue

            used_indices.add(match_idx)
            resolved.append(str(items[match_idx][1]))

        return resolved

    @staticmethod
    def _encode_planbench_values(domain_name: str, values: list[str]) -> list[str]:
        """Map prompt-side PlanBench object names back to raw PDDL aliases."""
        try:
            from .planner.domain_spec import encode_planbench_symbol

            return [encode_planbench_symbol(domain_name, value) for value in values]
        except Exception:
            return values

    def from_bdi_plan(self, plan: BDIPlan, task: PlanningTask) -> list[str]:
        """Return ordered PDDL actions, e.g. ``["(pick-up a)", "(stack a b)"]``.

        Actions are topologically sorted using the plan's dependency edges.
        Virtual nodes (``__START__`` / ``__END__``) are excluded.
        """
        import networkx as nx

        G = plan.to_networkx()

        try:
            order = list(nx.topological_sort(G))
        except nx.NetworkXUnfeasible:
            # Fallback to node insertion order if DAG has cycles
            order = [n.id for n in plan.nodes]

        node_map = {n.id: n for n in plan.nodes}
        actions: list[str] = []
        for node_id in order:
            node = node_map.get(node_id)
            if node is None or node.action_type == "Virtual":
                continue

            schema = self._schema_by_action.get(
                self._normalise_symbol(node.action_type)
            )
            if schema:
                action_name, schema_order = schema
                resolved_values = self._ordered_param_values(node.params, schema_order)
            else:
                action_name = node.action_type
                resolved_values = [str(v) for v in node.params.values()]

            resolved_values = self._encode_planbench_values(task.domain_name, resolved_values)
            param_values = " ".join(resolved_values)

            if not param_values and str(action_name).strip().startswith("(") and str(action_name).strip().endswith(")"):
                actions.append(str(action_name).strip())
                continue

            action_str = (
                f"({action_name} {param_values})".strip()
                if param_values
                else f"({action_name})"
            )
            actions.append(action_str)

        return actions
