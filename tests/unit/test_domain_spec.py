"""Unit tests for DomainSpec and PDDL parsing utilities."""

import pytest
from pathlib import Path

from src.bdi_llm.planner.domain_spec import (
    DomainSpec,
    build_domain_context,
    decode_planbench_literals,
    extract_actions_from_pddl,
)
from src.bdi_llm.planner.signatures import (
    GeneratePlan,
    GeneratePlanDepots,
    GeneratePlanGeneric,
    GeneratePlanLogistics,
)


# ---- PDDL text fixtures ----

GRIPPER_DOMAIN = """
(define (domain gripper)
  (:predicates (room ?r) (ball ?b) (gripper ?g)
               (at-robby ?r) (at ?b ?r) (free ?g) (carry ?o ?g))

  (:action move
    :parameters (?from ?to)
    :precondition (and (room ?from) (room ?to) (at-robby ?from))
    :effect (and (at-robby ?to) (not (at-robby ?from))))

  (:action pick
    :parameters (?obj ?room ?gripper)
    :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                       (at ?obj ?room) (at-robby ?room) (free ?gripper))
    :effect (and (carry ?obj ?gripper) (not (at ?obj ?room)) (not (free ?gripper))))

  (:action drop
    :parameters (?obj ?room ?gripper)
    :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                       (carry ?obj ?gripper) (at-robby ?room))
    :effect (and (at ?obj ?room) (free ?gripper) (not (carry ?obj ?gripper)))))
"""

TYPED_DOMAIN = """
(define (domain typed)
  (:action drive
    :parameters (?truck - vehicle ?from - location ?to - location)
    :precondition (at ?truck ?from)
    :effect (and (at ?truck ?to) (not (at ?truck ?from)))))
"""

OBFUSCATED_DOMAIN = """
(define (domain obfuscated_randomized_logistics)
  (:action v1pjso2krv6sk1wj
    :parameters (?obj - object ?truck - object ?loc - object)
    :precondition (and
      (zwcd0caosqrvypn9 ?obj)
      (qg9duf682li1kpbe ?truck)
      (cbaj1n1wo5bq3ezl ?loc)
      (uiat7ywwr0i6j87c ?truck ?loc)
      (uiat7ywwr0i6j87c ?obj ?loc))
    :effect (and
      (hdqlgp6pqzse6p2n ?obj ?truck)
      (not (uiat7ywwr0i6j87c ?obj ?loc))))
)
"""

PLANBENCH_DECEPTIVE_PROMPT = Path(
    "workspaces/planbench_data/plan-bench/prompts/obfuscated_deceptive_logistics/"
    "task_1_plan_generation.json"
)


# ---- extract_actions_from_pddl ----

class TestExtractActionsFromPDDL:
    def test_gripper_actions(self):
        actions = extract_actions_from_pddl(GRIPPER_DOMAIN)
        names = [a["name"] for a in actions]
        assert "move" in names
        assert "pick" in names
        assert "drop" in names
        assert len(actions) == 3

    def test_gripper_move_params(self):
        actions = extract_actions_from_pddl(GRIPPER_DOMAIN)
        move = next(a for a in actions if a["name"] == "move")
        # Untyped params get type "object"
        assert len(move["parameters"]) == 2
        assert move["parameters"][0][0] == "from"
        assert move["parameters"][1][0] == "to"

    def test_typed_params(self):
        actions = extract_actions_from_pddl(TYPED_DOMAIN)
        assert len(actions) == 1
        drive = actions[0]
        assert drive["name"] == "drive"
        assert ("truck", "vehicle") in drive["parameters"]
        assert ("from", "location") in drive["parameters"]
        assert ("to", "location") in drive["parameters"]

    def test_empty_text(self):
        assert extract_actions_from_pddl("") == []

    def test_no_actions(self):
        assert extract_actions_from_pddl("(define (domain empty))") == []

    def test_extracts_preconditions_and_effects(self):
        actions = extract_actions_from_pddl(GRIPPER_DOMAIN)

        pick = next(a for a in actions if a["name"] == "pick")

        assert "preconditions" in pick
        assert "effects_add" in pick
        assert "effects_del" in pick
        assert "ball ?obj" in pick["preconditions"]
        assert "carry ?obj ?gripper" in pick["effects_add"]
        assert "at ?obj ?room" in pick["effects_del"]


# ---- build_domain_context ----

class TestBuildDomainContext:
    def test_produces_string(self):
        actions = extract_actions_from_pddl(GRIPPER_DOMAIN)
        ctx = build_domain_context("gripper", actions)
        assert isinstance(ctx, str)
        assert "gripper" in ctx.lower() or "Domain: gripper" in ctx
        assert "move" in ctx
        assert "pick" in ctx
        assert "drop" in ctx

    def test_includes_preconditions_and_effects(self):
        actions = extract_actions_from_pddl(GRIPPER_DOMAIN)

        ctx = build_domain_context("gripper", actions)

        assert "Preconditions" in ctx
        assert "Effects (add)" in ctx
        assert "Effects (delete)" in ctx
        assert "(ball ?obj)" in ctx
        assert "(carry ?obj ?gripper)" in ctx
        assert "(at ?obj ?room)" in ctx

    def test_obfuscated_domains_get_dynamics_not_just_names(self):
        actions = extract_actions_from_pddl(OBFUSCATED_DOMAIN)

        ctx = build_domain_context("obfuscated_randomized_logistics", actions)

        assert "v1pjso2krv6sk1wj" in ctx
        assert "(zwcd0caosqrvypn9 ?obj)" in ctx
        assert "(hdqlgp6pqzse6p2n ?obj ?truck)" in ctx
        assert "(uiat7ywwr0i6j87c ?obj ?loc)" in ctx


class TestPlanBenchLiteralDecoding:
    def test_decodes_encoded_object_aliases(self):
        decoded = decode_planbench_literals(
            "obfuscated_deceptive_logistics",
            ["next o6 o7", "stupendous o0"],
        )

        assert decoded == ["next object_6 object_7", "stupendous object_0"]


# ---- DomainSpec factory methods ----

class TestDomainSpecBuiltIn:
    def test_blocksworld(self):
        spec = DomainSpec.blocksworld()
        assert spec.name == "blocksworld"
        assert "pick-up" in spec.valid_action_types
        assert spec.signature_class is GeneratePlan
        assert spec.pddl_domain_text is None
        assert spec.domain_context is None

    def test_logistics(self):
        spec = DomainSpec.logistics()
        assert spec.name == "logistics"
        assert "fly-airplane" in spec.valid_action_types
        assert spec.signature_class is GeneratePlanLogistics
        assert spec.demos_loader is not None

    def test_depots(self):
        spec = DomainSpec.depots()
        assert spec.name == "depots"
        assert "lift" in spec.valid_action_types
        assert spec.signature_class is GeneratePlanDepots

    def test_testing(self):
        spec = DomainSpec.testing()
        assert spec.name == "testing"
        assert len(spec.valid_action_types) == 0

    def test_from_name_blocksworld(self):
        spec = DomainSpec.from_name("blocksworld")
        assert spec.name == "blocksworld"
        assert spec.signature_class is GeneratePlan

    def test_from_name_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown built-in domain"):
            DomainSpec.from_name("nonexistent")


class TestDomainSpecFromPDDL:
    def test_from_pddl_gripper(self):
        spec = DomainSpec.from_pddl("gripper", GRIPPER_DOMAIN)
        assert spec.name == "gripper"
        assert spec.signature_class is GeneratePlanGeneric
        assert "move" in spec.valid_action_types
        assert "pick" in spec.valid_action_types
        assert "drop" in spec.valid_action_types
        assert spec.pddl_domain_text == GRIPPER_DOMAIN
        assert spec.domain_context is not None
        assert "move" in spec.domain_context

    def test_from_pddl_context_contains_action_dynamics(self):
        spec = DomainSpec.from_pddl("obfuscated_randomized_logistics", OBFUSCATED_DOMAIN)

        assert spec.domain_context is not None
        assert "Preconditions" in spec.domain_context
        assert "Effects (add)" in spec.domain_context
        assert "Effects (delete)" in spec.domain_context
        assert "(zwcd0caosqrvypn9 ?obj)" in spec.domain_context

    def test_from_pddl_empty_required_params(self):
        """Generic PDDL relies on VAL for param validation, not dspy.Assert."""
        spec = DomainSpec.from_pddl("gripper", GRIPPER_DOMAIN)
        assert spec.required_params == {}

    def test_obfuscated_deceptive_attaches_planbench_demo_loader(self):
        if not PLANBENCH_DECEPTIVE_PROMPT.exists():
            pytest.skip(f"Prompt fixture not found: {PLANBENCH_DECEPTIVE_PROMPT}")

        spec = DomainSpec.from_pddl("obfuscated_deceptive_logistics", OBFUSCATED_DOMAIN)

        assert spec.demos_loader is not None

        demos = spec.demos_loader()

        assert len(demos) >= 1

    def test_frozen(self):
        """DomainSpec should be immutable."""
        spec = DomainSpec.from_pddl("gripper", GRIPPER_DOMAIN)
        with pytest.raises(AttributeError):
            spec.name = "changed"  # type: ignore[misc]
