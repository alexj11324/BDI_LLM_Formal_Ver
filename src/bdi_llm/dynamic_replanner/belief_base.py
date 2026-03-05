"""
BeliefBase: Maintains the symbolic world state during plan execution.

Parses a PDDL problem's (:init ...) block into a set of ground propositions,
and provides `apply_effects` to update state after each successful action.
This gives the DynamicReplanner a human-readable snapshot of the current
world state to include in the recovery prompt.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class BeliefBase:
    """
    Domain-agnostic ground-truth state tracker.
    State is a set of string propositions, e.g. {"(on a b)", "(clear a)", "(handempty)"}.
    """
    propositions: Set[str] = field(default_factory=set)
    objects: List[str] = field(default_factory=list)
    domain_name: str = ""

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    @classmethod
    def from_pddl_problem(cls, pddl_file: str) -> "BeliefBase":
        """Parse a PDDL problem file and extract (:init ...) propositions."""
        with open(pddl_file, "r") as f:
            content = f.read()

        # Domain name
        dm = re.search(r"\(:domain\s+(.*?)\)", content)
        domain_name = dm.group(1).strip() if dm else "unknown"

        # Objects
        objects_match = re.search(r":objects\s+(.*?)\)", content, re.DOTALL)
        objects: List[str] = []
        if objects_match:
            text = objects_match.group(1)
            # Strip type annotations ("obj1 obj2 - Type")
            text = re.sub(r"\s*-\s*\w+", "", text)
            objects = [w.strip() for w in text.split() if w.strip()]

        # Init predicates
        init_match = re.search(r":init\s+(.*?)\(:goal", content, re.DOTALL)
        propositions: Set[str] = set()
        if init_match:
            init_text = init_match.group(1)
            for pred_body in re.findall(r"\(([^()]+)\)", init_text):
                # Normalise whitespace
                prop = "(" + " ".join(pred_body.split()) + ")"
                propositions.add(prop)

        return cls(propositions=propositions, objects=objects, domain_name=domain_name)

    # ------------------------------------------------------------------ #
    # State queries
    # ------------------------------------------------------------------ #

    def holds(self, proposition: str) -> bool:
        """Check if a proposition currently holds."""
        return proposition in self.propositions

    def query(self, predicate_name: str) -> List[str]:
        """Return all propositions matching a predicate name."""
        return [
            p for p in self.propositions
            if p.startswith(f"({predicate_name} ") or p == f"({predicate_name})"
        ]

    # ------------------------------------------------------------------ #
    # State updates
    # ------------------------------------------------------------------ #

    def add(self, proposition: str):
        self.propositions.add(proposition)

    def remove(self, proposition: str):
        self.propositions.discard(proposition)

    def apply_effects(self, add_list: List[str], delete_list: List[str]):
        """Apply STRIPS-style add/delete effects."""
        for prop in delete_list:
            self.propositions.discard(prop)
        for prop in add_list:
            self.propositions.add(prop)

    # ------------------------------------------------------------------ #
    # Serialisation (for LLM prompts)
    # ------------------------------------------------------------------ #

    def to_natural_language(self) -> str:
        """Render current state as a readable string for LLM context."""
        sorted_props = sorted(self.propositions)
        lines = [f"=== CURRENT WORLD STATE ({len(sorted_props)} facts) ==="]
        for p in sorted_props:
            lines.append(f"  {p}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to JSON-safe dict."""
        return {
            "domain_name": self.domain_name,
            "objects": self.objects,
            "propositions": sorted(self.propositions),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BeliefBase":
        return cls(
            propositions=set(d.get("propositions", [])),
            objects=d.get("objects", []),
            domain_name=d.get("domain_name", ""),
        )
