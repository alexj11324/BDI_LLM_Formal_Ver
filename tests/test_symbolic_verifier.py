
import pytest
import os
import subprocess
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
        mock_process.stdout = "Plan executed successfully - checking goal\nPlan valid\nFinal value: 10 \n"
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

    @patch("os.path.exists")
    def test_val_path_configuration(self, mock_exists):
        """Test that VAL path is correctly loaded from Config"""
        mock_exists.return_value = True

        # Test with explicit path
        verifier = PDDLSymbolicVerifier(val_path="/custom/val")
        assert verifier.val_path == "/custom/val"

        # Test with Config (mocking Config.VAL_VALIDATOR_PATH)
        # We need to mock Config in the module where it is used
        with patch("src.bdi_llm.symbolic_verifier.Config") as MockConfig:
            MockConfig.VAL_VALIDATOR_PATH = "/env/val"
            verifier = PDDLSymbolicVerifier()
            assert verifier.val_path == "/env/val"

    @patch("subprocess.run")
    def test_verify_plan_timeout(self, mock_run, verifier):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="val", timeout=30)
        is_valid, errors = verifier.verify_plan("d.pddl", "p.pddl", ["(action)"])
        assert is_valid is False
        assert "VAL validation timeout" in errors[0]

    @patch("subprocess.run")
    def test_verify_plan_file_not_found(self, mock_run, verifier):
        mock_run.side_effect = FileNotFoundError()
        is_valid, errors = verifier.verify_plan("d.pddl", "p.pddl", ["(action)"])
        assert is_valid is False
        assert "VAL executable not found" in errors[0]

    @patch("subprocess.run")
    def test_verify_plan_os_error(self, mock_run, verifier):
        mock_run.side_effect = OSError("Generic OS Error")
        is_valid, errors = verifier.verify_plan("d.pddl", "p.pddl", ["(action)"])
        assert is_valid is False
        assert "VAL execution error (OSError)" in errors[0]

    @patch("subprocess.run")
    def test_verify_plan_exec_format_error(self, mock_run, verifier):
        error = OSError()
        error.errno = 8
        mock_run.side_effect = error
        is_valid, errors = verifier.verify_plan("d.pddl", "p.pddl", ["(action)"])
        assert is_valid is False
        assert "VAL executable incompatible" in errors[0]

    @patch("subprocess.run")
    def test_verify_plan_generic_exception(self, mock_run, verifier):
        mock_run.side_effect = Exception("Unknown error")
        is_valid, errors = verifier.verify_plan("d.pddl", "p.pddl", ["(action)"])
        assert is_valid is False
        assert "VAL execution error" in errors[0]
