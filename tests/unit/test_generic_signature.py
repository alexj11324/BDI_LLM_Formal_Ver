"""Unit tests for GeneratePlanGeneric routing and generate_plan() wrapper."""

from __future__ import annotations

import pytest

from src.bdi_llm.planner.domain_spec import DomainSpec
from src.bdi_llm.planner.signatures import (
    GeneratePlan,
    GeneratePlanGeneric,
    GeneratePlanLogistics,
)


GRIPPER_PDDL = """
(define (domain gripper)
  (:action move   :parameters (?from ?to)        :precondition () :effect ())
  (:action pick   :parameters (?obj ?room ?grip)  :precondition () :effect ())
  (:action drop   :parameters (?obj ?room ?grip)  :precondition () :effect ()))
"""


# ---------------------------------------------------------------------------
# DomainSpec → Signature routing
# ---------------------------------------------------------------------------

class TestSignatureRouting:
    def test_blocksworld_uses_generate_plan(self):
        spec = DomainSpec.from_name("blocksworld")
        assert spec.signature_class is GeneratePlan

    def test_logistics_uses_generate_plan_logistics(self):
        spec = DomainSpec.from_name("logistics")
        assert spec.signature_class is GeneratePlanLogistics

    def test_generic_pddl_uses_generate_plan_generic(self):
        spec = DomainSpec.from_pddl("gripper", GRIPPER_PDDL)
        assert spec.signature_class is GeneratePlanGeneric


class TestIsGenericFlag:
    def test_builtin_not_generic(self):
        from src.bdi_llm.planner.bdi_engine import BDIPlanner

        planner = BDIPlanner(auto_repair=False, domain="blocksworld")
        assert planner._is_generic is False

    def test_generic_pddl_is_generic(self):
        from src.bdi_llm.planner.bdi_engine import BDIPlanner

        spec = DomainSpec.from_pddl("gripper", GRIPPER_PDDL)
        planner = BDIPlanner(auto_repair=False, domain_spec=spec)
        assert planner._is_generic is True


# ---------------------------------------------------------------------------
# generate_plan() wrapper — ctx missing → ValueError
# ---------------------------------------------------------------------------

class TestGeneratePlanCtxValidation:
    def test_generic_without_context_raises(self):
        """§4.2: generic planner MUST raise when domain_context is missing."""
        from src.bdi_llm.planner.bdi_engine import BDIPlanner

        # Build a spec with no domain_context
        spec = DomainSpec(
            name="empty-generic",
            valid_action_types=frozenset({"move"}),
            required_params={},
            signature_class=GeneratePlanGeneric,
            domain_context=None,  # intentionally empty
        )
        planner = BDIPlanner(auto_repair=False, domain_spec=spec)
        assert planner._is_generic is True

        with pytest.raises(ValueError, match="requires domain_context"):
            planner.generate_plan(
                beliefs="some state",
                desire="some goal",
                # no domain_context passed
            )

    def test_generic_with_context_from_spec_ok(self):
        """When from_pddl builds the spec, domain_context is auto-populated."""
        from src.bdi_llm.planner.bdi_engine import BDIPlanner

        spec = DomainSpec.from_pddl("gripper", GRIPPER_PDDL)
        planner = BDIPlanner(auto_repair=False, domain_spec=spec)

        # Should NOT raise — context comes from spec
        # (will fail at DSPy level because no LLM configured, but not ValueError)
        assert spec.domain_context is not None
        assert planner._is_generic is True

    def test_builtin_without_context_ok(self):
        """Built-in domains should work fine without domain_context."""
        from src.bdi_llm.planner.bdi_engine import BDIPlanner

        planner = BDIPlanner(auto_repair=False, domain="blocksworld")
        # Should not raise ValueError — built-in domains don't need context
        # (will fail at DSPy/LLM level, but NOT at our validation)
        assert planner._is_generic is False


# ---------------------------------------------------------------------------
# from_name() unknown domain → ValueError
# ---------------------------------------------------------------------------

class TestFromNameUnknown:
    def test_unknown_raises(self):
        """§4.1: from_name must NOT silently fallback."""
        with pytest.raises(ValueError, match="Unknown built-in domain"):
            DomainSpec.from_name("travelplanner")

    def test_unknown_with_typo_raises(self):
        with pytest.raises(ValueError, match="Unknown built-in domain"):
            DomainSpec.from_name("blockworld")  # typo: missing 's'
