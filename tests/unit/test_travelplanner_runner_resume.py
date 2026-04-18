"""Tests for TravelPlanner runner checkpoint resume (task_id-based alignment)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.bdi_llm.travelplanner.runner import _checkpoint_file, _load_resume_state


def _make_samples(n: int) -> list[dict]:
    return [
        {'idx': i, 'split': 'validation', 'query': f'q{i}', 'days': 3}
        for i in range(1, n + 1)
    ]


def _seed_checkpoint(tmp_path: Path, split: str, mode: str, rows: list[dict]) -> Path:
    mode_dir = tmp_path / split / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    payload = {'split': split, 'execution_mode': mode, 'results': rows, 'summary': {}}
    ckp = _checkpoint_file(mode_dir, split, mode)
    ckp.write_text(json.dumps(payload))
    return mode_dir


def test_no_checkpoint_returns_empty_results(tmp_path: Path) -> None:
    mode_dir = tmp_path / 'validation' / 'bdi-repair'
    mode_dir.mkdir(parents=True)
    samples = _make_samples(5)
    results, completed = _load_resume_state(mode_dir, 'validation', 'bdi-repair', samples)
    assert results == [None] * 5
    assert completed == 0


def test_full_checkpoint_fills_all_positions(tmp_path: Path) -> None:
    samples = _make_samples(3)
    rows = [
        {'task_id': '1', 'success': True, 'metrics': {}},
        {'task_id': '2', 'success': False, 'metrics': {}},
        {'task_id': '3', 'success': True, 'metrics': {}},
    ]
    mode_dir = _seed_checkpoint(tmp_path, 'validation', 'baseline', rows)
    results, completed = _load_resume_state(mode_dir, 'validation', 'baseline', samples)
    assert completed == 3
    assert [r['task_id'] for r in results] == ['1', '2', '3']
    assert results[0]['success'] is True
    assert results[1]['success'] is False


def test_partial_checkpoint_aligns_by_task_id_not_order(tmp_path: Path) -> None:
    """Prior checkpoint completed tasks 2 + 4 in arbitrary order; verify they
    land at positions 1 and 3 (0-based), leaving 0/2/4 unfilled.
    """
    samples = _make_samples(5)
    rows = [
        {'task_id': '4', 'success': True, 'metrics': {}},
        {'task_id': '2', 'success': False, 'metrics': {}},
    ]
    mode_dir = _seed_checkpoint(tmp_path, 'validation', 'bdi', rows)
    results, completed = _load_resume_state(mode_dir, 'validation', 'bdi', samples)
    assert completed == 2
    assert results[0] is None
    assert results[1] is not None and results[1]['task_id'] == '2'
    assert results[2] is None
    assert results[3] is not None and results[3]['task_id'] == '4'
    assert results[4] is None


def test_stale_task_ids_are_ignored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    samples = _make_samples(3)
    rows = [
        {'task_id': '1', 'success': True, 'metrics': {}},
        {'task_id': '999', 'success': True, 'metrics': {}},
    ]
    mode_dir = _seed_checkpoint(tmp_path, 'validation', 'bdi-repair', rows)
    results, completed = _load_resume_state(mode_dir, 'validation', 'bdi-repair', samples)
    assert completed == 1
    assert results[0]['task_id'] == '1'
    assert results[1] is None
    assert results[2] is None
    captured = capsys.readouterr().out
    assert 'not found in current sample set' in captured


def test_corrupt_checkpoint_falls_back_to_fresh(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mode_dir = tmp_path / 'validation' / 'bdi'
    mode_dir.mkdir(parents=True)
    _checkpoint_file(mode_dir, 'validation', 'bdi').write_text('{not valid json')
    samples = _make_samples(2)
    results, completed = _load_resume_state(mode_dir, 'validation', 'bdi', samples)
    assert completed == 0
    assert results == [None, None]
    captured = capsys.readouterr().out
    assert 'unreadable' in captured


def test_sample_without_idx_falls_back_to_position(tmp_path: Path) -> None:
    """Samples lacking explicit 'idx' should fall back to 1-based enumerate position."""
    samples = [{'split': 'validation', 'query': f'q{i}'} for i in range(3)]
    rows = [{'task_id': '2', 'success': True, 'metrics': {}}]
    mode_dir = _seed_checkpoint(tmp_path, 'validation', 'baseline', rows)
    results, completed = _load_resume_state(mode_dir, 'validation', 'baseline', samples)
    assert completed == 1
    assert results[1] is not None and results[1]['task_id'] == '2'
