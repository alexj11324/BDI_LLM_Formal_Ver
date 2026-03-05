
import pytest
from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator

class TestBlocksworldPhysicsValidator:

    def test_valid_sequence(self):
        """Test a valid sequence of actions: pick-up, stack, unstack, put-down."""
        # Initial state: a and b on table, both clear. Hand empty.
        init_state = {
            'on_table': ['a', 'b'],
            'on': [],
            'clear': ['a', 'b'],
            'holding': None
        }

        # Valid plan:
        # 1. pick-up a
        # 2. stack a on b
        # 3. unstack a from b
        # 4. put-down a
        plan_actions = [
            "(pick-up a)",
            "(stack a b)",
            "(unstack a b)",
            "(put-down a)"
        ]

        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(plan_actions, init_state)

        assert is_valid is True
        assert len(errors) == 0

    def test_pickup_failures(self):
        """Test conditions where pick-up should fail."""

        # Case 1: Block not clear (c is on a)
        init_state_1 = {
            'on_table': ['a'],
            'on': [('c', 'a')],
            'clear': ['c'],
            'holding': None
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(pick-up a)"], init_state_1)
        assert is_valid is False
        assert "not clear" in errors[0]

        # Case 2: Hand already holding something
        init_state_2 = {
            'on_table': ['a'],
            'on': [],
            'clear': ['a'],
            'holding': 'b'
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(pick-up a)"], init_state_2)
        assert is_valid is False
        assert "hand already holding" in errors[0]

        # Case 3: Block not on table
        init_state_3 = {
            'on_table': ['b'],
            'on': [('a', 'b')],
            'clear': ['a'],
            'holding': None
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(pick-up a)"], init_state_3)
        assert is_valid is False
        assert "not on table" in errors[0]

    def test_putdown_failures(self):
        """Test conditions where put-down should fail."""

        # Case 1: Not holding the block
        init_state = {
            'on_table': [],
            'on': [],
            'clear': [],
            'holding': 'b'
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(put-down a)"], init_state)
        assert is_valid is False
        assert "not holding it" in errors[0]

    def test_stack_failures(self):
        """Test conditions where stack should fail."""

        # Case 1: Not holding the block to stack
        init_state_1 = {
            'on_table': ['b'],
            'on': [],
            'clear': ['b'],
            'holding': 'c'
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(stack a b)"], init_state_1)
        assert is_valid is False
        assert "not holding it" in errors[0]

        # Case 2: Target block not clear
        init_state_2 = {
            'on_table': ['b'],
            'on': [('c', 'b')],
            'clear': ['c'],
            'holding': 'a'
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(stack a b)"], init_state_2)
        assert is_valid is False
        assert "not clear" in errors[0]

    def test_unstack_failures(self):
        """Test conditions where unstack should fail."""

        # Case 1: Block to unstack is not clear
        init_state_1 = {
            'on_table': ['b'],
            'on': [('a', 'b'), ('c', 'a')],
            'clear': ['c'],
            'holding': None
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(unstack a b)"], init_state_1)
        assert is_valid is False
        assert "not clear" in errors[0]

        # Case 2: Hand not empty
        init_state_2 = {
            'on_table': ['b'],
            'on': [('a', 'b')],
            'clear': ['a'],
            'holding': 'c'
        }
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(unstack a b)"], init_state_2)
        assert is_valid is False
        assert "hand not empty" in errors[0]

    def test_parsing_failures(self):
        """Test invalid action formats."""
        init_state = {'on_table': [], 'on': [], 'clear': [], 'holding': None}

        # Invalid pick-up format
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(pick-up)"], init_state)
        assert is_valid is False
        assert "Cannot parse block" in errors[0]

        # Invalid stack format (needs 2 blocks)
        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(["(stack a)"], init_state)
        assert is_valid is False
        assert "Cannot parse blocks" in errors[0]

    def test_regex_fallback_parsing(self):
        """Test parsing where split fails but regex succeeds (e.g. comma separator)."""
        init_state = {
            'on_table': ['a'],
            'on': [],
            'clear': ['a'],
            'holding': None
        }
        # This format (comma separated) might fail split() but work with regex
        # (pick-up,a) -> cleaned: " pick-up,a " -> parts: ["pick-up,a"] -> len 1 -> Regex fallback
        plan_actions = ["(pick-up,a)"]

        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(plan_actions, init_state)

        # Should succeed picking up 'a'
        assert is_valid is True
        assert len(errors) == 0

    def test_state_persistence(self):
        """Test that state is correctly updated and persisted across steps."""
        init_state = {
            'on_table': ['a'],
            'on': [],
            'clear': ['a'],
            'holding': None
        }

        # First pick-up succeeds, second fails because hand is full / block not on table
        plan_actions = ["(pick-up a)", "(pick-up a)"]

        is_valid, errors = BlocksworldPhysicsValidator.validate_plan(plan_actions, init_state)

        assert is_valid is False
        assert len(errors) > 0
        # The first action should be fine, the error should be on the second action (Step 2)
        assert "Step 2" in errors[0]
