"""Unit tests for the R1 Distillation Formatter.

Covers:
- format_trajectory_for_r1 output structure compliance
- <think> tag presence and correct ordering of sections
- No Markdown code fences around the final JSON DAG
- Strict JSON DAG output validity
- Error correction history formatting (empty and non-empty)
- write_trajectories_to_jsonl file writing and JSONL format
- format_and_write_trajectories convenience function
- Empty trajectory list rejection
- Append mode for JSONL writing
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.core.bdi_engine import GoldenTrajectory
from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.dspy_pipeline.r1_formatter import (
    THINK_CLOSE,
    THINK_OPEN,
    format_and_write_trajectories,
    format_trajectory_for_r1,
    write_trajectories_to_jsonl,
)


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------


def _make_trajectory(
    desire: Dict[str, Any] | None = None,
    reasoning: str = "Test BDI reasoning chain",
    error_history: List[Dict[str, Any]] | None = None,
) -> GoldenTrajectory:
    """Create a minimal GoldenTrajectory for testing."""
    if desire is None:
        desire = {"goal": "stack(A, B)"}
    if error_history is None:
        error_history = []

    dag = IntentionDAG(
        dag_id="test-dag-r1",
        nodes=[
            IntentionNode(
                node_id="n1",
                action_type="pick-up",
                parameters={"block": "A"},
            ),
        ],
        metadata={"source": "test"},
    )

    belief_before = BeliefState(
        environment_context={"pddl_state": ["clear(A)", "ontable(A)", "arm-empty"]},
    )
    belief_after = BeliefState(
        environment_context={"pddl_state": ["holding(A)"]},
    )

    return GoldenTrajectory(
        desire=desire,
        intention_dag=dag,
        belief_before=belief_before,
        belief_after=belief_after,
        reasoning=reasoning,
        error_correction_history=error_history,
    )


# ---------------------------------------------------------------------------
# format_trajectory_for_r1 — Structure
# ---------------------------------------------------------------------------


class TestFormatTrajectoryStructure:
    """Tests for the output structure of format_trajectory_for_r1."""

    def test_returns_prompt_and_response_keys(self) -> None:
        """Output dict must have exactly 'prompt' and 'response' keys."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        assert "prompt" in result
        assert "response" in result
        assert len(result) == 2

    def test_prompt_is_string(self) -> None:
        """The 'prompt' value must be a string."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        assert isinstance(result["prompt"], str)

    def test_response_is_string(self) -> None:
        """The 'response' value must be a string."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        assert isinstance(result["response"], str)


# ---------------------------------------------------------------------------
# format_trajectory_for_r1 — <think> Tag Compliance
# ---------------------------------------------------------------------------


class TestThinkTagCompliance:
    """Tests for correct <think> tag format in the response."""

    def test_think_open_tag_present(self) -> None:
        """Response must start with <think>."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        assert result["response"].startswith(THINK_OPEN)

    def test_think_close_tag_present(self) -> None:
        """Response must contain </think>."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        assert THINK_CLOSE in result["response"]

    def test_sections_present_in_order(self) -> None:
        """Response must contain the three sections in the correct order."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        belief_idx = response.index("[Belief Updates]:")
        error_idx = response.index("[Verifier Error Correction Analysis]:")
        bdi_idx = response.index("[BDI Reasoning]:")

        assert belief_idx < error_idx < bdi_idx

    def test_json_after_think_close(self) -> None:
        """The strict JSON DAG must appear AFTER </think>."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        close_idx = response.index(THINK_CLOSE)
        json_part = response[close_idx + len(THINK_CLOSE):].strip()

        # Should be valid JSON.
        parsed = json.loads(json_part)
        assert isinstance(parsed, dict)
        assert "dag_id" in parsed

    def test_no_markdown_code_fences(self) -> None:
        """The response must NOT contain Markdown code fences (``` or ```json)."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        assert "```" not in response
        assert "~~~" not in response


# ---------------------------------------------------------------------------
# format_trajectory_for_r1 — JSON DAG Validity
# ---------------------------------------------------------------------------


class TestJsonDagOutput:
    """Tests for the strict JSON DAG output correctness."""

    def test_dag_is_valid_json(self) -> None:
        """The JSON DAG portion must parse as valid JSON."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        # Extract JSON after </think>.
        close_idx = response.index(THINK_CLOSE)
        json_str = response[close_idx + len(THINK_CLOSE):].strip()
        parsed = json.loads(json_str)

        assert parsed["dag_id"] == "test-dag-r1"
        assert len(parsed["nodes"]) == 1
        assert parsed["nodes"][0]["action_type"] == "pick-up"

    def test_dag_json_is_compact(self) -> None:
        """The DAG JSON should be compact (no pretty-printing)."""
        traj = _make_trajectory()
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        close_idx = response.index(THINK_CLOSE)
        json_str = response[close_idx + len(THINK_CLOSE):].strip()

        # Compact JSON should be a single line.
        assert "\n" not in json_str


# ---------------------------------------------------------------------------
# format_trajectory_for_r1 — Error Correction History
# ---------------------------------------------------------------------------


class TestErrorCorrectionHistory:
    """Tests for error correction history formatting."""

    def test_empty_history(self) -> None:
        """No failed attempts should produce 'No errors' message."""
        traj = _make_trajectory(error_history=[])
        result = format_trajectory_for_r1(traj)
        assert "No errors" in result["response"]

    def test_non_empty_history(self) -> None:
        """Failed attempts should be listed with attempt numbers."""
        history = [
            {
                "attempt": 1,
                "error_trace": "PreconditionViolation: clear(A) is False",
                "correction_hint": "Block A has another block on top",
            },
            {
                "attempt": 2,
                "error_trace": "PreconditionViolation: arm-empty is False",
                "correction_hint": "Put down the block first",
            },
        ]
        traj = _make_trajectory(error_history=history)
        result = format_trajectory_for_r1(traj)
        response = result["response"]

        assert "Attempt 1" in response
        assert "Attempt 2" in response
        assert "PreconditionViolation" in response
        assert "clear(A)" in response

    def test_reasoning_included(self) -> None:
        """The BDI reasoning should be included in the response."""
        traj = _make_trajectory(reasoning="I analyzed the Blocksworld state")
        result = format_trajectory_for_r1(traj)
        assert "I analyzed the Blocksworld state" in result["response"]


# ---------------------------------------------------------------------------
# write_trajectories_to_jsonl
# ---------------------------------------------------------------------------


class TestWriteTrajectoriesToJsonl:
    """Tests for the JSONL writing function."""

    def test_write_single_record(self) -> None:
        """Writing a single record produces a valid JSONL file."""
        record = {"prompt": "test prompt", "response": "test response"}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.jsonl"
            result_path = write_trajectories_to_jsonl([record], output_path)

            assert result_path.exists()
            lines = result_path.read_text().strip().split("\n")
            assert len(lines) == 1

            parsed = json.loads(lines[0])
            assert parsed["prompt"] == "test prompt"
            assert parsed["response"] == "test response"

    def test_write_multiple_records(self) -> None:
        """Multiple records produce one JSON line each."""
        records = [
            {"prompt": f"p{i}", "response": f"r{i}"}
            for i in range(5)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "multi.jsonl"
            write_trajectories_to_jsonl(records, output_path)

            lines = output_path.read_text().strip().split("\n")
            assert len(lines) == 5

    def test_empty_records_raises(self) -> None:
        """Empty record list should raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty.jsonl"
            with pytest.raises(ValueError, match="empty"):
                write_trajectories_to_jsonl([], output_path)

    def test_append_mode(self) -> None:
        """Append mode should add to existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "append.jsonl"

            # First write.
            write_trajectories_to_jsonl(
                [{"prompt": "p1", "response": "r1"}],
                output_path,
            )
            # Append.
            write_trajectories_to_jsonl(
                [{"prompt": "p2", "response": "r2"}],
                output_path,
                append=True,
            )

            lines = output_path.read_text().strip().split("\n")
            assert len(lines) == 2

    def test_creates_parent_directories(self) -> None:
        """Should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "output.jsonl"
            write_trajectories_to_jsonl(
                [{"prompt": "p", "response": "r"}],
                output_path,
            )
            assert output_path.exists()

    def test_each_line_is_valid_json(self) -> None:
        """Every line in the JSONL file must be independently parseable JSON."""
        records = [
            {"prompt": "p1", "response": "r1"},
            {"prompt": "p2", "response": "包含Unicode字符"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "unicode.jsonl"
            write_trajectories_to_jsonl(records, output_path)

            for line in output_path.read_text().strip().split("\n"):
                parsed = json.loads(line)
                assert "prompt" in parsed
                assert "response" in parsed


# ---------------------------------------------------------------------------
# format_and_write_trajectories (end-to-end convenience)
# ---------------------------------------------------------------------------


class TestFormatAndWriteTrajectories:
    """Tests for the convenience batch function."""

    def test_end_to_end(self) -> None:
        """Full pipeline: trajectory → format → write → read back."""
        trajectories = [
            _make_trajectory(desire={"goal": f"goal-{i}"})
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"
            result_path = format_and_write_trajectories(trajectories, output_path)

            assert result_path.exists()
            lines = result_path.read_text().strip().split("\n")
            assert len(lines) == 3

            for line in lines:
                record = json.loads(line)
                assert "prompt" in record
                assert "response" in record
                assert THINK_OPEN in record["response"]
                assert THINK_CLOSE in record["response"]
                assert "```" not in record["response"]

    def test_empty_trajectories_raises(self) -> None:
        """Empty trajectory list should raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty.jsonl"
            with pytest.raises(ValueError, match="empty"):
                format_and_write_trajectories([], output_path)

    def test_output_contains_belief_updates(self) -> None:
        """Each formatted trajectory should contain belief state info."""
        traj = _make_trajectory()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "beliefs.jsonl"
            format_and_write_trajectories([traj], output_path)

            line = output_path.read_text().strip()
            record = json.loads(line)
            assert "[Belief Updates]:" in record["response"]
            assert "Before:" in record["response"]
            assert "After:" in record["response"]
