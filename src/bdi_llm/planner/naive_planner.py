"""Naive baseline planner — direct LLM PDDL action generation without BDI structure.

This module provides a minimal planner that asks the LLM to directly produce
a list of PDDL action strings, bypassing the BDI (Belief-Desire-Intention)
framework entirely.  It is used as a baseline to measure the value added by
the BDI pipeline and multi-layer verification/repair loop.
"""

import json
import logging
import time
from typing import Optional

import dspy

from .dspy_config import configure_dspy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DSPy Signatures — one per domain
# ---------------------------------------------------------------------------

class NaiveGeneratePlanBlocksworld(dspy.Signature):
    """You are a PDDL planning assistant for the BLOCKSWORLD domain.

    Given a problem description (initial state and goal), output a valid
    sequence of PDDL actions that transforms the initial state into the
    goal state.

    Available actions and their PDDL syntax:
      (pick-up <block>)       — pick up a block from the table
      (put-down <block>)      — put a held block on the table
      (stack <block> <target>) — stack a held block onto another block
      (unstack <block> <target>) — unstack a block from another block

    Preconditions:
      pick-up(X):  X is clear, X is on the table, hand is empty
      put-down(X): hand is holding X
      unstack(X,Y): X is clear, X is on Y, hand is empty
      stack(X,Y):  hand is holding X, Y is clear

    Output a JSON array of PDDL action strings. Example:
      ["(unstack a b)", "(put-down a)", "(pick-up a)", "(stack a c)"]
    """
    problem_description: str = dspy.InputField(
        desc="Natural language description of the initial state and goal"
    )
    plan_actions: str = dspy.OutputField(
        desc='JSON array of PDDL action strings, e.g. ["(pick-up a)", "(stack a b)"]'
    )


class NaiveGeneratePlanLogistics(dspy.Signature):
    """You are a PDDL planning assistant for the LOGISTICS domain.

    Given a problem description (initial state and goal), output a valid
    sequence of PDDL actions.

    Available actions:
      (LOAD-TRUCK <obj> <truck> <loc>)
      (UNLOAD-TRUCK <obj> <truck> <loc>)
      (LOAD-AIRPLANE <obj> <airplane> <loc>)
      (UNLOAD-AIRPLANE <obj> <airplane> <loc>)
      (DRIVE-TRUCK <truck> <from> <to> <city>)
      (FLY-AIRPLANE <airplane> <from> <to>)

    Key rules:
      - Trucks can only drive within the SAME city
      - Airplanes can only fly between AIRPORT locations
      - load/unload requires vehicle and object at SAME location

    Output a JSON array of PDDL action strings. Example:
      ["(DRIVE-TRUCK t0 l0-0 l0-1 c0)", "(LOAD-TRUCK p0 t0 l0-1)"]
    """
    problem_description: str = dspy.InputField(
        desc="Natural language description of the initial state and goal"
    )
    plan_actions: str = dspy.OutputField(
        desc='JSON array of PDDL action strings, e.g. ["(DRIVE-TRUCK t0 l0-0 l0-1 c0)"]'
    )


class NaiveGeneratePlanDepots(dspy.Signature):
    """You are a PDDL planning assistant for the DEPOTS domain.

    Given a problem description (initial state and goal), output a valid
    sequence of PDDL actions.

    Available actions:
      (Drive <truck> <from-place> <to-place>)
      (Lift <hoist> <crate> <surface> <place>)
      (Drop <hoist> <crate> <surface> <place>)
      (Load <hoist> <crate> <truck> <place>)
      (Unload <hoist> <crate> <truck> <place>)

    Key rules:
      - Hoist must be AVAILABLE to lift or unload; LIFTING to load or drop
      - All objects in an action must be at the SAME place
      - Surface must be CLEAR for drop

    Output a JSON array of PDDL action strings. Example:
      ["(Lift hoist0 crate0 pallet0 depot0)", "(Load hoist0 crate0 truck0 depot0)"]
    """
    problem_description: str = dspy.InputField(
        desc="Natural language description of the initial state and goal"
    )
    plan_actions: str = dspy.OutputField(
        desc='JSON array of PDDL action strings, e.g. ["(Lift hoist0 crate0 pallet0 depot0)"]'
    )


class NaiveGeneratePlanGeneric(dspy.Signature):
    """You are a PDDL planning assistant for an arbitrary symbolic planning domain.

    You are given:
      1. The domain PDDL, which defines the valid action names, parameters,
         preconditions, and effects.
      2. A problem description with the objects, initial predicates, and goal
         predicates.

    Requirements:
      - Use ONLY action names that appear in the provided domain PDDL.
      - Copy action names and object identifiers EXACTLY as written.
      - Treat all predicate and action names as symbolic tokens, even if they
        are obfuscated or misleading English words.
      - Reason from preconditions/effects and the initial/goal predicates.

    Output a JSON array of grounded PDDL action strings. Example:
      ["(action-name o1 o2)", "(other-action o3 o4)"]
    """
    domain_pddl: str = dspy.InputField(
        desc="Raw domain PDDL defining the available actions"
    )
    problem_description: str = dspy.InputField(
        desc="Objects, initial predicates, and goal predicates for the problem"
    )
    plan_actions: str = dspy.OutputField(
        desc='JSON array of grounded PDDL action strings, e.g. ["(action-name o1 o2)"]'
    )


# ---------------------------------------------------------------------------
# NaivePlanner
# ---------------------------------------------------------------------------

_SIGNATURE_MAP = {
    "blocksworld": NaiveGeneratePlanBlocksworld,
    "logistics": NaiveGeneratePlanLogistics,
    "depots": NaiveGeneratePlanDepots,
}


class NaivePlanner:
    """Baseline planner that directly asks the LLM for PDDL actions.

    No BDI decomposition, no structured output, no repair loop.
    """

    def __init__(self, domain: str = "blocksworld"):
        self.domain = domain
        configure_dspy()
        sig_cls = _SIGNATURE_MAP.get(domain)
        self._uses_generic_signature = sig_cls is None
        if sig_cls is None:
            sig_cls = NaiveGeneratePlanGeneric
        self._predictor = dspy.ChainOfThought(sig_cls)

    def generate_plan(
        self,
        beliefs: str,
        desire: str,
        max_retries: int = 3,
        domain_context: Optional[str] = None,
    ) -> list[str]:
        """Generate a list of PDDL action strings.

        Args:
            beliefs: Natural language initial state description.
            desire: Natural language goal description.
            max_retries: Number of retries on transient API errors.
            domain_context: Raw domain specification for generic domains.

        Returns:
            List of PDDL action strings, e.g. ["(pick-up a)", "(stack a b)"].
            Returns empty list on failure.
        """
        problem_description = (
            f"Initial State:\n{beliefs}\n\nGoal:\n{desire}"
        )

        last_error: Optional[str] = None
        for attempt in range(max_retries):
            try:
                if self._uses_generic_signature:
                    pred = self._predictor(
                        domain_pddl=domain_context or "",
                        problem_description=problem_description,
                    )
                else:
                    pred = self._predictor(
                        problem_description=problem_description
                    )
                raw = pred.plan_actions
                actions = self._parse_actions(raw)
                return actions
            except Exception as e:
                last_error = str(e)
                error_lower = last_error.lower()
                retryable = any(
                    kw in error_lower
                    for kw in (
                        "connection", "timeout", "internal",
                        "resourceexhausted", "429", "rate", "quota",
                    )
                )
                if retryable and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "NaivePlanner API error, retrying in %ds (%d/%d): %s",
                        wait, attempt + 1, max_retries, last_error,
                    )
                    time.sleep(wait)
                    continue
                logger.error("NaivePlanner failed: %s", last_error)
                return []

        logger.error("NaivePlanner exhausted retries: %s", last_error)
        return []

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_actions(raw: str) -> list[str]:
        """Parse LLM output into a list of PDDL action strings."""
        text = raw.strip()

        # Strip markdown fences
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(a).strip() for a in parsed if a]
        except json.JSONDecodeError:
            pass

        # Fallback: line-by-line extraction of parenthesised actions
        actions = []
        for line in text.splitlines():
            line = line.strip().strip(",").strip('"').strip("'")
            if line.startswith("(") and line.endswith(")"):
                actions.append(line)
        return actions
