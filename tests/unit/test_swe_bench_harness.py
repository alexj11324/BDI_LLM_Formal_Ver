from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.swe_bench.swe_bench_harness import LocalSWEBenchHarness


class _StubPlanner:
    pass


def _make_harness() -> LocalSWEBenchHarness:
    harness = LocalSWEBenchHarness.__new__(LocalSWEBenchHarness)
    harness.workspace_dir = Path('/tmp/swebench-test-workspace')
    harness.planner = _StubPlanner()
    harness._dataset = None
    harness._dataset_by_id = None
    harness.conda_executable = None
    harness._repo_version_specs = {}
    harness._repo_to_reqs_paths = {}
    harness._repo_to_env_yml_paths = {}
    harness._constants_load_error = None
    return harness


def test_build_test_command_uses_repo_specific_shell_command_with_eval_commands():
    harness = _make_harness()
    harness._repo_version_specs = {
        'django/django': {
            '4.2': {
                'test_cmd': './tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1',
                'eval_commands': ['export LANG=en_US.UTF-8'],
            }
        }
    }

    command = harness.build_test_command(
        {
            'repo': 'django/django',
            'version': '4.2',
            'FAIL_TO_PASS': '["tests/foo.py::test_bug"]',
            'PASS_TO_PASS': '["tests/bar.py::test_regression"]',
        },
        python_executable='/env/bin/python',
    )

    assert isinstance(command, str)
    assert 'export LANG=en_US.UTF-8' in command
    assert 'runtests.py' in command
    assert 'tests/foo.py::test_bug' in command
    assert 'tests/bar.py::test_regression' in command


def test_build_test_command_maps_python_test_cmd_to_pytest_list():
    harness = _make_harness()
    harness._repo_version_specs = {
        'swe-bench/humaneval': {
            '1.0': {
                'test_cmd': 'python',
            }
        }
    }

    command = harness.build_test_command(
        {
            'repo': 'swe-bench/humaneval',
            'version': '1.0',
            'FAIL_TO_PASS': '["tests/test_one.py::test_case"]',
            'PASS_TO_PASS': '[]',
        },
        python_executable='/env/bin/python',
    )

    assert command == ['/env/bin/python', '-m', 'pytest', '-q', 'tests/test_one.py::test_case']


def test_run_tests_accepts_shell_script(monkeypatch, tmp_path):
    observed: dict[str, object] = {}

    def _fake_run_shell_command(script: str, cwd: Path, timeout: int = 600, prepend_path: str | None = None):
        observed['script'] = script
        observed['cwd'] = cwd
        observed['timeout'] = timeout
        return True, 'ok', 0

    monkeypatch.setattr(LocalSWEBenchHarness, '_run_shell_command', staticmethod(_fake_run_shell_command))

    ok, output, returncode = LocalSWEBenchHarness.run_tests(tmp_path, 'pytest -q tests/test_x.py', timeout=77)

    assert ok is True
    assert output == 'ok'
    assert returncode == 0
    assert observed == {'script': 'pytest -q tests/test_x.py', 'cwd': tmp_path, 'timeout': 77}


def test_build_step_test_command_uses_repo_specific_runner_with_selector():
    harness = _make_harness()
    harness._repo_version_specs = {
        'django/django': {
            '4.2': {
                'test_cmd': './tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1',
                'eval_commands': ['export LANG=en_US.UTF-8'],
            }
        }
    }

    command = harness.build_step_test_command(
        {
            'repo': 'django/django',
            'version': '4.2',
        },
        test_selector='tests/forms_tests/tests/test_forms.py::FormsTestCase::test_bug',
        python_executable='/env/bin/python',
    )

    assert isinstance(command, str)
    assert 'export LANG=en_US.UTF-8' in command
    assert 'runtests.py' in command
    assert 'tests/forms_tests/tests/test_forms.py::FormsTestCase::test_bug' in command


def test_setup_repo_checks_out_env_commit_then_restores_base_tree(monkeypatch, tmp_path):
    harness = _make_harness()
    harness.workspace_dir = tmp_path
    calls: list[list[str]] = []

    def _fake_run(args, cwd=None, check=None, capture_output=None, text=None, timeout=None):
        calls.append(list(args))
        return None

    monkeypatch.setattr('scripts.swe_bench.swe_bench_harness.subprocess.run', _fake_run)

    instance_dir = harness.setup_repo(
        {
            'repo': 'astropy/astropy',
            'base_commit': 'base123',
            'environment_setup_commit': 'env456',
            'instance_id': 'astropy__astropy-12907',
        },
        cleanup_existing=False,
    )

    assert instance_dir == tmp_path / 'astropy__astropy-12907'
    assert calls == [
        ['git', 'clone', '--no-checkout', 'https://github.com/astropy/astropy.git', '.'],
        ['git', 'checkout', 'env456'],
        ['git', 'reset', '--hard', 'base123'],
    ]


def test_django_test_selectors_extracts_module_paths():
    selectors = [
        'test_ascii_validator (auth_tests.test_validators.UsernameValidatorsTests)',
        'test_unicode_validator (auth_tests.test_validators.UsernameValidatorsTests)',
        'test_help_text (auth_tests.test_validators.UserAttributeSimilarityValidatorTest)',
    ]
    result = LocalSWEBenchHarness._django_test_selectors(selectors)
    assert result == ['auth_tests.test_validators']


def test_django_test_selectors_preserves_non_django_format():
    selectors = ['tests/test_foo.py::test_bar']
    result = LocalSWEBenchHarness._django_test_selectors(selectors)
    assert result == ['tests/test_foo.py::test_bar']


def test_build_test_command_django_converts_selectors():
    harness = _make_harness()
    harness._repo_version_specs = {}

    command = harness.build_test_command(
        {
            'repo': 'django/django',
            'version': '2.2',
            'FAIL_TO_PASS': '["test_count (aggregation.tests.AggregateTestCase)"]',
            'PASS_TO_PASS': '[]',
        },
        python_executable='/env/bin/python',
    )

    assert isinstance(command, list)
    assert 'aggregation.tests' in command
    # Should NOT contain the raw selector with parentheses
    assert 'test_count (aggregation.tests.AggregateTestCase)' not in command
