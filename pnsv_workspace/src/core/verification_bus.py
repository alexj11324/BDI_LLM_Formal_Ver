"""Polymorphic Verification Bus for the BDI reasoning engine.

This module defines the abstract interface that all domain-specific verifiers
must implement.  The :class:`BaseDomainVerifier` provides the Strategy Pattern
contract: the BDI engine depends only on this abstract interface and never on
concrete domain logic.

The Verification Bus concept ensures that:

* Domain-specific verification logic is fully decoupled from the core engine.
* Multiple heterogeneous verifiers (PlanBench / PDDL, SWE-bench / code, etc.)
  can be plugged in without modifying any core module.
* The BDI engine receives a uniform ``(is_valid, formal_error_trace,
  dspy_correction_hint)`` tuple regardless of the domain.

Design notes
------------
* This module MUST NOT import LLM-generation utilities, ``pytest``, ``ast``,
  ``pddl``, or any other domain-specific library.
* Concrete verifiers live under ``src/plugins/`` and are injected at runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

from src.core.schemas import BeliefState, IntentionDAG


class BaseDomainVerifier(ABC):
    """Abstract base class for all domain-specific verifiers.

    Every verifier plugin must subclass ``BaseDomainVerifier`` and implement
    the :meth:`verify_transition` method.  The BDI engine calls this method
    with a **deep copy** of the current belief state so that the verifier can
    freely mutate the copy during simulation without affecting the canonical
    state.

    Returns
    -------
    The method must return a 3-tuple:

    * ``is_valid`` (*bool*) – ``True`` if the proposed intention DAG is a
      valid transition from the current belief state.
    * ``formal_error_trace`` (*str*) – A structured, machine-readable error
      description when ``is_valid`` is ``False``.  Empty string on success.
    * ``dspy_correction_hint`` (*str*) – A human/LLM-readable hint that the
      DSPy pipeline can inject into the next prompt to guide the Teacher LLM
      toward a corrected plan.  Empty string on success.
    """

    @abstractmethod
    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> Tuple[bool, str, str]:
        """Validate an intention DAG against the current belief state.

        Parameters
        ----------
        current_belief : BeliefState
            A **deep copy** of the agent's current belief state.  The
            verifier may freely mutate this copy during forward simulation.
        intention_dag : IntentionDAG
            The candidate plan (DAG of intention nodes) produced by the
            Teacher LLM.

        Returns
        -------
        Tuple[bool, str, str]
            A 3-tuple of ``(is_valid, formal_error_trace,
            dspy_correction_hint)``.

            * ``is_valid``: Whether the transition is valid.
            * ``formal_error_trace``: Machine-readable error description
              (empty string when ``is_valid`` is ``True``).
            * ``dspy_correction_hint``: LLM-readable correction guidance
              (empty string when ``is_valid`` is ``True``).
        """
        ...  # pragma: no cover
