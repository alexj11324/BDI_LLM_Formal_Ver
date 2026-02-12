
import pytest
import os
from unittest.mock import patch, MagicMock
from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier

class TestPDDLSymbolicVerifier:

    @pytest.fixture
    def verifier(self):
        # Mock the path so we don't need actual VAL installed for unit tests
        with patch("os.path.exists", return_value=True):
            return PDDLSymbolicVerifier(val_path="/mock/path/to/validate")

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_verify_plan_valid(self, mock_exists, mock_run, verifier):
        # Setup
        mock_exists.return_value = True

        # Mock successful VAL output
        mock_process = MagicMock()
        mock_process.stdout = "Plan valid\nFinal value: 10 \n"
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        # Execute
        is_valid, errors = verifier.verify_plan(
            domain_file="domain.pddl",
            problem_file="problem.pddl",
            plan_actions=["(pick-up a)", "(stack a b)"]
        )

        # Assert
        assert is_valid is True
        assert len(errors) == 0

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_verify_plan_invalid(self, mock_exists, mock_run, verifier):
        # Setup
        mock_exists.return_value = True

        # Mock failed VAL output
        mock_process = MagicMock()
        mock_process.stdout = "Plan failed to execute\n"
        mock_process.stderr = "Error: Precondition not satisfied: (clear b)\n"
        mock_run.return_value = mock_process

        # Execute
        is_valid, errors = verifier.verify_plan(
            domain_file="domain.pddl",
            problem_file="problem.pddl",
            plan_actions=["(pick-up a)", "(stack a b)"]
        )

        # Assert
        assert is_valid is False
        assert len(errors) > 0
        assert "Precondition violation" in errors[0] or "Precondition not satisfied" in str(errors)

    def test_empty_plan(self, verifier):
        is_valid, errors = verifier.verify_plan(
            domain_file="domain.pddl",
            problem_file="problem.pddl",
            plan_actions=[]
        )
        assert is_valid is False
        assert "Empty plan" in errors[0]
