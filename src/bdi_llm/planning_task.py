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

    def __init__(self, domain_name: str, domain_context: str | None = None):
        self.domain_name = domain_name
        self.domain_context = domain_context

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
        parts: list[str] = []

        objects_str = _parse_pddl_objects(problem_text)
        if objects_str:
            parts.append(objects_str)

        init_str = _parse_pddl_init(problem_text)
        if init_str:
            parts.append(init_str)

        return "\n\n".join(parts) if parts else problem_text.strip()

    @staticmethod
    def _build_desire(problem_text: str) -> str:
        """Assemble desire from :goal block."""
        desire = _parse_pddl_goal(problem_text)
        return desire if desire else "Achieve the goal state."


class PDDLPlanSerializer(PlanSerializer):
    """Extract a list of PDDL action strings from a ``BDIPlan``."""

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
            param_values = " ".join(str(v) for v in node.params.values())
            action_str = f"({node.action_type} {param_values})".strip()
            actions.append(action_str)

        return actions
