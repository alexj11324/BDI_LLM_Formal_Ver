#!/usr/bin/env python3
"""Local SWE-bench harness for planning, editing, and test verification."""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from datasets import load_dataset

from bdi_llm.coding_planner import CodingBDIPlanner
from bdi_llm.swe_bench.ast_viewport import file_skeleton, file_skeleton_with_context
from bdi_llm.verifier import PlanVerifier

logger = logging.getLogger(__name__)

class LocalSWEBenchHarness:
    """Runner for SWE-bench instances with local repository execution."""

    SWEBENCH_CONSTANTS_URL = (
        "https://raw.githubusercontent.com/SWE-bench/SWE-bench/"
        "fa79f3af3e0f212d4d14b1c858c77fcaae5308ce/swebench/harness/constants/python.py"
    )

    ENV_ERROR_MARKERS = [
        "no module named",
        "modulenotfounderror",
        "importerror while loading conftest",
        "broken installation",
        "from within a source checkout",
        "could not determine",
        "failed building wheel",
        "could not build wheels",
        "error: subprocess-exited-with-error",
        "unsatisfiableerror",
        "condavalueerror",
        "requires-python",
        "requires python",
    ]

    MODULE_PACKAGE_MAP = {
        "yaml": "PyYAML",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "PIL": "Pillow",
        "bs4": "beautifulsoup4",
    }

    def __init__(self, workspace_dir: str = "swe_bench_workspace"):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.planner = CodingBDIPlanner(auto_repair=True)
        self._dataset = None
        self._dataset_by_id: Optional[Dict[str, Dict[str, Any]]] = None
        self.conda_executable = self._detect_conda_executable()
        self._repo_version_specs: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None
        self._repo_to_reqs_paths: Dict[str, List[str]] = {}
        self._repo_to_env_yml_paths: Dict[str, List[str]] = {}
        self._constants_load_error: Optional[str] = None

    @property
    def dataset(self):
        if self._dataset is None:
            print("Loading SWE-bench Verified dataset...")
            self._dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
        return self._dataset

    def _build_index(self) -> None:
        if self._dataset_by_id is not None:
            return
        self._dataset_by_id = {item["instance_id"]: item for item in self.dataset}

    def get_instance(self, instance_id: str) -> Dict[str, Any]:
        """Retrieve a specific instance by ID."""
        self._build_index()
        assert self._dataset_by_id is not None  # for typing
        if instance_id not in self._dataset_by_id:
            raise ValueError(f"Instance {instance_id} not found")
        return self._dataset_by_id[instance_id]

    @staticmethod
    def _detect_conda_executable() -> Optional[str]:
        candidates = [
            os.environ.get("CONDA_EXE"),
            shutil.which("conda"),
            str(Path.home() / "opt" / "anaconda3" / "bin" / "conda"),
            str(Path.home() / "anaconda3" / "bin" / "conda"),
            "/opt/miniconda3/bin/conda",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and path.is_file():
                return str(path)
        return None

    @staticmethod
    def _run_command(
        command: List[str],
        cwd: Path,
        timeout: int = 600,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, int]:
        try:
            # Clean env to avoid PYTHONPATH pollution from parent process
            if env is None:
                env = os.environ.copy()
                env.pop("PYTHONPATH", None)
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
            output = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
            return result.returncode == 0, output, result.returncode
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s: {' '.join(command)}", 124

    @staticmethod
    def _run_shell_command(
        script: str,
        cwd: Path,
        timeout: int = 600,
        prepend_path: Optional[str] = None,
    ) -> Tuple[bool, str, int]:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        if prepend_path:
            env["PATH"] = prepend_path + os.pathsep + env.get("PATH", "")

        # Prepend unset PYTHONPATH to prevent conda env corruption
        # from parent process or profile sourcing
        safe_script = f"unset PYTHONPATH; {script}"

        try:
            result = subprocess.run(
                ["bash", "-c", safe_script],
                cwd=cwd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
            output = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
            return result.returncode == 0, output, result.returncode
        except subprocess.TimeoutExpired:
            return False, f"Shell command timed out after {timeout}s: {script}", 124

    def _load_official_python_constants(self) -> None:
        if self._repo_version_specs is not None:
            return

        specs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        req_paths: Dict[str, List[str]] = {}
        env_paths: Dict[str, List[str]] = {}
        load_error: Optional[str] = None

        try:
            from swebench.harness.constants.python import (
                MAP_REPO_TO_ENV_YML_PATHS,
                MAP_REPO_TO_REQS_PATHS,
                MAP_REPO_VERSION_TO_SPECS_PY,
            )

            specs = MAP_REPO_VERSION_TO_SPECS_PY
            req_paths = MAP_REPO_TO_REQS_PATHS
            env_paths = MAP_REPO_TO_ENV_YML_PATHS
        except Exception:
            try:
                url = os.environ.get("SWEBENCH_CONSTANTS_URL", self.SWEBENCH_CONSTANTS_URL)
                with urllib.request.urlopen(url, timeout=30) as response:
                    source = response.read().decode("utf-8")
                namespace: Dict[str, Any] = {}
                exec(compile(source, "<swebench_python_constants>", "exec"), namespace)
                specs = namespace.get("MAP_REPO_VERSION_TO_SPECS_PY", {})
                req_paths = namespace.get("MAP_REPO_TO_REQS_PATHS", {})
                env_paths = namespace.get("MAP_REPO_TO_ENV_YML_PATHS", {})
            except Exception as exc:
                load_error = str(exc)

        if not isinstance(specs, dict):
            specs = {}
        if not isinstance(req_paths, dict):
            req_paths = {}
        if not isinstance(env_paths, dict):
            env_paths = {}

        self._repo_version_specs = specs
        self._repo_to_reqs_paths = {
            str(k): [str(p) for p in v] for k, v in req_paths.items() if isinstance(v, list)
        }
        self._repo_to_env_yml_paths = {
            str(k): [str(p) for p in v] for k, v in env_paths.items() if isinstance(v, list)
        }
        self._constants_load_error = load_error

    def _lookup_repo_spec(self, instance: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
        self._load_official_python_constants()
        assert self._repo_version_specs is not None

        repo = str(instance.get("repo", ""))
        version = str(instance.get("version", "")).strip()
        version_keys: List[str] = []
        if version:
            version_keys.extend([version, version.lstrip("v"), f"v{version.lstrip('v')}"])

        repo_specs = self._repo_version_specs.get(repo, {})
        selected: Dict[str, Any] = {}
        if isinstance(repo_specs, dict):
            for key in version_keys:
                if key in repo_specs and isinstance(repo_specs[key], dict):
                    selected = dict(repo_specs[key])
                    break

        req_candidates = self._repo_to_reqs_paths.get(repo, [])
        env_yml_candidates = self._repo_to_env_yml_paths.get(repo, [])
        return selected, req_candidates, env_yml_candidates

    @staticmethod
    def _find_existing_path(root: Path, candidates: List[str]) -> Optional[Path]:
        for rel in candidates:
            candidate = (root / rel).resolve()
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _append_step_log(logs: List[Dict[str, Any]], step: str, ok: bool, returncode: int, output: str) -> None:
        logs.append(
            {
                "step": step,
                "ok": ok,
                "returncode": returncode,
                "output_tail": (output or "")[-4000:],
            }
        )

    @classmethod
    def _is_environment_error(cls, output: str) -> bool:
        lower = (output or "").lower()
        return any(marker in lower for marker in cls.ENV_ERROR_MARKERS)

    @staticmethod
    def _run_portable_pre_install(instance_dir: Path, command: str) -> Optional[Tuple[bool, str, int]]:
        """Handle common GNU-sed style pre-install commands on non-GNU systems."""
        cmd = command.strip()
        if (
            (cmd.startswith("'") and cmd.endswith("'"))
            or (cmd.startswith('"') and cmd.endswith('"'))
        ):
            cmd = cmd[1:-1]
        cmd = cmd.replace("\\'", "'").replace('\\"', '"')
        cmd = cmd.replace("\\[", "[").replace("\\]", "]")

        if "pyproject.toml" in cmd and "setuptools==68.0.0" in cmd:
            pyproject = instance_dir / "pyproject.toml"
            if not pyproject.exists():
                return False, f"pyproject.toml not found: {pyproject}", 1

            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            old = 'requires = ["setuptools",'
            new = 'requires = ["setuptools==68.0.0",'
            if old in content:
                pyproject.write_text(content.replace(old, new), encoding="utf-8")
                return True, "Applied portable pre_install replacement in pyproject.toml", 0
            if new in content:
                return True, "Portable pre_install replacement already present", 0
            return False, "Target pattern not found in pyproject.toml", 1
        return None

    def _bootstrap_repo_dependencies(
        self,
        instance: Dict[str, Any],
        instance_dir: Path,
        env_prefix: Path,
        env_python: Path,
        spec: Dict[str, Any],
        req_candidates: List[str],
        env_yml_candidates: List[str],
        timeout: int,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        logs: List[Dict[str, Any]] = []
        env_bin = str(env_python.parent)

        # Some official specs apply small source rewrites before install (e.g., pinned setuptools in pyproject).
        pre_install = spec.get("pre_install", [])
        if isinstance(pre_install, list):
            for idx, cmd in enumerate(pre_install, start=1):
                cmd_text = str(cmd).strip()
                if (
                    (cmd_text.startswith("'") and cmd_text.endswith("'"))
                    or (cmd_text.startswith('"') and cmd_text.endswith('"'))
                ):
                    cmd_text = cmd_text[1:-1]
                cmd_text = cmd_text.replace("\\'", "'").replace('\\"', '"')
                if not cmd_text:
                    continue
                if "apt-get" in cmd_text:
                    self._append_step_log(
                        logs,
                        step=f"pre_install[{idx}]",
                        ok=False,
                        returncode=127,
                        output=f"Skipped unsupported system-level command: {cmd_text}",
                    )
                    continue
                portable = self._run_portable_pre_install(instance_dir, cmd_text)
                if portable is not None:
                    ok, output, returncode = portable
                else:
                    ok, output, returncode = self._run_shell_command(
                        cmd_text,
                        cwd=instance_dir,
                        timeout=timeout,
                        prepend_path=env_bin,
                    )
                self._append_step_log(logs, step=f"pre_install[{idx}]", ok=ok, returncode=returncode, output=output)

        packages_spec = str(spec.get("packages", "")).strip() if isinstance(spec, dict) else ""
        if packages_spec == "requirements.txt":
            req_path = self._find_existing_path(
                instance_dir,
                req_candidates
                + [
                    "requirements.txt",
                    "requirements-dev.txt",
                    "requirements_test.txt",
                    "requirements/dev.txt",
                    "tests/requirements/py3.txt",
                ],
            )
            if req_path is not None:
                ok, output, returncode = self._run_command(
                    [str(env_python), "-m", "pip", "install", "-r", str(req_path)],
                    cwd=instance_dir,
                    timeout=timeout,
                )
                self._append_step_log(logs, "install_requirements_txt", ok, returncode, output)
                if not ok:
                    return False, logs
        elif packages_spec == "environment.yml":
            env_yml_path = self._find_existing_path(
                instance_dir, env_yml_candidates + ["environment.yml", "ci/requirements/environment.yml"]
            )
            if env_yml_path is not None and self.conda_executable:
                ok, output, returncode = self._run_command(
                    [
                        self.conda_executable,
                        "env",
                        "update",
                        "--prefix",
                        str(env_prefix),
                        "-f",
                        str(env_yml_path),
                    ],
                    cwd=instance_dir,
                    timeout=timeout,
                )
                self._append_step_log(logs, "conda_env_update", ok, returncode, output)
                if not ok:
                    return False, logs
        elif packages_spec:
            tokens = shlex.split(packages_spec)
            ok, output, returncode = self._run_command(
                [str(env_python), "-m", "pip", "install", *tokens],
                cwd=instance_dir,
                timeout=timeout,
            )
            self._append_step_log(logs, "install_packages_spec", ok, returncode, output)
            if not ok:
                return False, logs

        pip_packages = spec.get("pip_packages", [])
        if isinstance(pip_packages, list) and pip_packages:
            for start in range(0, len(pip_packages), 30):
                chunk = [str(pkg) for pkg in pip_packages[start : start + 30] if str(pkg).strip()]
                if not chunk:
                    continue
                ok, output, returncode = self._run_command(
                    [str(env_python), "-m", "pip", "install", *chunk],
                    cwd=instance_dir,
                    timeout=timeout,
                )
                self._append_step_log(logs, f"install_pip_packages[{start}:{start + len(chunk)}]", ok, returncode, output)
                if not ok:
                    return False, logs

        install_attempts: List[str] = []
        install_cmd = str(spec.get("install", "")).strip() if isinstance(spec, dict) else ""
        if install_cmd:
            install_attempts.append(install_cmd)

        # Fallback install attempts for repos without precise SWE-bench spec matches.
        install_attempts.extend(
            [
                "python -m pip install -v --no-build-isolation -e .[test]",
                "python -m pip install -e .[test]",
                "python -m pip install -v --no-build-isolation -e .",
                "python -m pip install -e .",
            ]
        )

        install_ok = False
        install_fail_outputs: List[str] = []
        for idx, cmd in enumerate(install_attempts, start=1):
            ok, output, returncode = self._run_shell_command(
                cmd,
                cwd=instance_dir,
                timeout=timeout,
                prepend_path=env_bin,
            )
            self._append_step_log(logs, f"repo_install[{idx}]", ok, returncode, output)
            if ok:
                install_ok = True
                break
            install_fail_outputs.append(output or "")

        if not install_ok:
            combined_fail_output = "\n".join(install_fail_outputs).lower()
            degraded_allowed = any(
                marker in combined_fail_output
                for marker in [
                    "clang",
                    "failed building wheel",
                    "build editable",
                    "metadata-generation-failed",
                    "no module named 'extension_helpers'",
                    "no module named \"extension_helpers\"",
                ]
            )
            if degraded_allowed:
                self._append_step_log(
                    logs,
                    "repo_install_degraded_mode",
                    True,
                    0,
                    "All repository install attempts failed, but proceeding in degraded mode for test execution.",
                )
            else:
                return False, logs

        # Ensure pytest exists even if project install skips test tooling.
        ok, output, returncode = self._run_command(
            [str(env_python), "-m", "pip", "install", "-q", "pytest"],
            cwd=instance_dir,
            timeout=timeout,
        )
        self._append_step_log(logs, "ensure_pytest", ok, returncode, output)
        if not ok:
            return False, logs

        # Pin hypothesis for Python 3.8 envs (newer versions are incompatible)
        ver_ok, ver_out, _ = self._run_command(
            [str(env_python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            cwd=instance_dir,
            timeout=15,
        )
        py_ver = (ver_out or "").strip()
        if py_ver == "3.8":
            self._run_command(
                [str(env_python), "-m", "pip", "install", "-q", "hypothesis<6.80"],
                cwd=instance_dir,
                timeout=timeout,
            )

        return True, logs

    def _prepare_python_environment(
        self,
        instance: Dict[str, Any],
        instance_dir: Path,
        timeout: int = 900,
    ) -> Dict[str, Any]:
        spec, req_candidates, env_yml_candidates = self._lookup_repo_spec(instance)
        preferred_python = str(spec.get("python", "")).strip() if isinstance(spec, dict) else ""
        candidate_versions = [preferred_python, "3.10", "3.11", "3.9", "3.8"]
        candidate_versions = [v for idx, v in enumerate(candidate_versions) if v and v not in candidate_versions[:idx]]

        if not self.conda_executable:
            return {
                "ok": True,
                "used_conda": False,
                "python_executable": sys.executable,
                "python_version": ".".join(map(str, sys.version_info[:3])),
                "spec_found": bool(spec),
                "spec_python": preferred_python or None,
                "setup_steps": [],
                "warning": "conda_not_found",
                "constants_load_error": self._constants_load_error,
            }

        env_prefix = instance_dir / ".swebench_env"
        env_python = env_prefix / ("python.exe" if os.name == "nt" else "bin/python")

        # Reuse existing conda env if valid (saves ~740s)
        # Check both --version AND stdlib import to catch corrupted envs
        # (e.g. git clean -fd removing .py source files while keeping binaries)
        if env_python.exists():
            try:
                ok, output, _ = self._run_command(
                    [str(env_python), "-c", "import encodings; print('ok')"],
                    cwd=instance_dir, timeout=30,
                )
                if ok and "ok" in (output or ""):
                    ver_ok, ver_out, _ = self._run_command(
                        [str(env_python), "--version"], cwd=instance_dir, timeout=30,
                    )
                    return {
                        "ok": True,
                        "used_conda": True,
                        "conda_executable": self.conda_executable,
                        "env_prefix": str(env_prefix),
                        "python_executable": str(env_python),
                        "python_version": (ver_out or "").strip().split()[-1] if ver_out else "unknown",
                        "spec_found": bool(spec),
                        "spec_python": preferred_python or None,
                        "setup_steps": [{"step": "reuse_existing_env", "ok": True}],
                        "constants_load_error": self._constants_load_error,
                    }
            except Exception:
                pass
            shutil.rmtree(env_prefix, ignore_errors=True)

        if env_prefix.exists():
            shutil.rmtree(env_prefix, ignore_errors=True)

        setup_steps: List[Dict[str, Any]] = []
        for version in candidate_versions:
            ok, output, returncode = self._run_command(
                [
                    self.conda_executable,
                    "create",
                    "--prefix",
                    str(env_prefix),
                    f"python={version}",
                    "-y",
                ],
                cwd=instance_dir,
                timeout=timeout,
            )
            self._append_step_log(setup_steps, f"conda_create_python_{version}", ok, returncode, output)
            if not ok:
                if env_prefix.exists():
                    shutil.rmtree(env_prefix, ignore_errors=True)
                continue

            env_python = env_prefix / ("python.exe" if os.name == "nt" else "bin/python")
            if not env_python.exists():
                self._append_step_log(
                    setup_steps,
                    "locate_env_python",
                    False,
                    1,
                    f"Missing python executable: {env_python}",
                )
                if env_prefix.exists():
                    shutil.rmtree(env_prefix, ignore_errors=True)
                continue

            ok, output, returncode = self._run_command(
                [str(env_python), "-m", "pip", "install", "-q", "--upgrade", "pip", "setuptools", "wheel"],
                cwd=instance_dir,
                timeout=timeout,
            )
            self._append_step_log(setup_steps, "bootstrap_pip", ok, returncode, output)
            if not ok:
                if env_prefix.exists():
                    shutil.rmtree(env_prefix, ignore_errors=True)
                continue

            dep_ok, dep_logs = self._bootstrap_repo_dependencies(
                instance=instance,
                instance_dir=instance_dir,
                env_prefix=env_prefix,
                env_python=env_python,
                spec=spec,
                req_candidates=req_candidates,
                env_yml_candidates=env_yml_candidates,
                timeout=timeout,
            )
            setup_steps.extend(dep_logs)
            if dep_ok:
                return {
                    "ok": True,
                    "used_conda": True,
                    "conda_executable": self.conda_executable,
                    "env_prefix": str(env_prefix),
                    "python_executable": str(env_python),
                    "python_version": version,
                    "spec_found": bool(spec),
                    "spec_python": preferred_python or None,
                    "setup_steps": setup_steps,
                    "constants_load_error": self._constants_load_error,
                }

            if env_prefix.exists():
                shutil.rmtree(env_prefix, ignore_errors=True)

        return {
            "ok": False,
            "used_conda": True,
            "conda_executable": self.conda_executable,
            "env_prefix": str(env_prefix),
            "python_executable": None,
            "python_version": None,
            "spec_found": bool(spec),
            "spec_python": preferred_python or None,
            "setup_steps": setup_steps,
            "constants_load_error": self._constants_load_error,
            "error": "failed_to_prepare_python_environment",
        }

    @staticmethod
    def parse_test_field(raw: Any) -> List[str]:
        """Parse FAIL_TO_PASS/PASS_TO_PASS field into a list of test selectors."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str):
            value = raw.strip()
            if not value:
                return []
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
            return [line.strip() for line in value.splitlines() if line.strip()]
        return []

    def _build_repo_aware_test_command(
        self,
        instance: Dict[str, Any],
        tests: List[str],
        python_executable: str,
    ) -> List[str] | str:
        """Core logic for building a repo-spec-aware test command."""
        spec, _, _ = self._lookup_repo_spec(instance)
        test_cmd = str(spec.get("test_cmd", "")).strip() if isinstance(spec, dict) else ""
        eval_commands = spec.get("eval_commands", []) if isinstance(spec, dict) else []

        if test_cmd:
            shell_parts: List[str] = []
            if isinstance(eval_commands, list):
                shell_parts.extend(str(cmd).strip() for cmd in eval_commands if str(cmd).strip())

            if test_cmd == "python":
                pytest_command = [python_executable, "-m", "pytest", "-q", *tests]
                return pytest_command if not shell_parts else " && ".join([*shell_parts, shlex.join(pytest_command)])

            # Replace bare pytest/pytest-style commands with python -m pytest
            # to ensure the conda env's pytest is used
            if test_cmd.startswith("pytest"):
                extra_flags = test_cmd[len("pytest"):].strip()
                pytest_parts = [python_executable, "-m", "pytest"]
                if extra_flags:
                    pytest_parts.extend(extra_flags.split())
                if tests:
                    pytest_parts.extend(tests)
                return pytest_parts if not shell_parts else " && ".join([*shell_parts, shlex.join(pytest_parts)])

            if tests:
                test_cmd = f"{test_cmd} {' '.join(shlex.quote(t) for t in tests)}"

            return " && ".join([*shell_parts, test_cmd]) if shell_parts else test_cmd

        if tests:
            return [python_executable, "-m", "pytest", "-q", *tests]
        return [python_executable, "-m", "pytest", "-q"]

    def build_test_command(
        self,
        instance: Dict[str, Any],
        python_executable: str = "python",
        max_tests: int = 25,
    ) -> List[str] | str:
        """Construct a repo-aware test command for the target instance."""
        fail_to_pass = self.parse_test_field(instance.get("FAIL_TO_PASS"))
        pass_to_pass = self.parse_test_field(instance.get("PASS_TO_PASS"))
        tests = (fail_to_pass + pass_to_pass)[:max_tests]
        return self._build_repo_aware_test_command(instance, tests, python_executable)

    def setup_repo(
        self,
        instance: Dict[str, Any],
        cleanup_existing: bool = True,
        clone_timeout: int = 900,
    ) -> Path:
        """Clone and checkout repository for a SWE-bench instance.

        If the instance directory already exists with a valid git repo,
        resets to base_commit instead of re-cloning (saves ~200s).
        """
        repo_name = instance["repo"]
        base_commit = instance["base_commit"]
        env_setup_commit = str(instance.get("environment_setup_commit") or "").strip()
        instance_id = instance["instance_id"]
        instance_dir = self.workspace_dir / instance_id

        # Reuse existing repo if valid
        if instance_dir.exists() and (instance_dir / ".git").is_dir():
            try:
                subprocess.run(
                    ["git", "checkout", "--", "."],
                    cwd=instance_dir, capture_output=True, check=True, timeout=60,
                )
                subprocess.run(
                    ["git", "clean", "-fd", "-e", ".swebench_env"],
                    cwd=instance_dir, capture_output=True, check=True, timeout=60,
                )
                subprocess.run(
                    ["git", "reset", "--hard", base_commit],
                    cwd=instance_dir, capture_output=True, check=True, timeout=60,
                )
                return instance_dir
            except Exception:
                # Corrupted repo — fall through to re-clone
                shutil.rmtree(instance_dir, ignore_errors=True)

        if cleanup_existing and instance_dir.exists():
            shutil.rmtree(instance_dir)
        instance_dir.mkdir(parents=True, exist_ok=True)

        repo_url = f"https://github.com/{repo_name}.git"
        clone_target = env_setup_commit or base_commit
        subprocess.run(
            ["git", "clone", "--no-checkout", repo_url, "."],
            cwd=instance_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=clone_timeout,
        )
        subprocess.run(
            ["git", "checkout", clone_target],
            cwd=instance_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if env_setup_commit and env_setup_commit != base_commit:
            subprocess.run(
                ["git", "reset", "--hard", base_commit],
                cwd=instance_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        return instance_dir

    @staticmethod
    def run_tests(instance_dir: Path, command: List[str] | str, timeout: int = 600) -> Tuple[bool, str, int]:
        """Run tests and return success, output text, and return code."""
        if isinstance(command, str):
            return LocalSWEBenchHarness._run_shell_command(script=command, cwd=instance_dir, timeout=timeout)
        return LocalSWEBenchHarness._run_command(command=command, cwd=instance_dir, timeout=timeout)

    def build_step_test_command(
        self,
        instance: Dict[str, Any],
        test_selector: str,
        python_executable: str,
    ) -> List[str] | str:
        """Construct a targeted test command for a single planned run-test step."""
        return self._build_repo_aware_test_command(instance, [test_selector], python_executable)

    @staticmethod
    def extract_missing_modules(output: str) -> List[str]:
        """Extract missing python modules from traceback text."""
        modules = re.findall(r"No module named ['\"]([^'\"]+)['\"]", output or "")
        cleaned: List[str] = []
        for name in modules:
            base = name.strip().split(".")[0]
            if not base:
                continue
            if re.match(r"^[A-Za-z0-9_.-]+$", base):
                cleaned.append(base)
        # Preserve order while deduplicating
        seen = set()
        unique: List[str] = []
        for mod in cleaned:
            if mod not in seen:
                seen.add(mod)
                unique.append(mod)
        return unique

    @staticmethod
    def install_python_packages(
        instance_dir: Path,
        packages: List[str],
        python_executable: str = sys.executable,
        timeout: int = 300,
    ) -> Tuple[bool, str]:
        """Install python packages into current environment for this run."""
        if not packages:
            return True, ""

        cmd = [python_executable, "-m", "pip", "install", "-q", *packages]
        ok, output, _ = LocalSWEBenchHarness._run_command(cmd, cwd=instance_dir, timeout=timeout)
        return ok, output

    def run_tests_with_dependency_fix(
        self,
        instance_dir: Path,
        command: List[str] | str,
        auto_installed_packages: List[str],
        python_executable: str = sys.executable,
        timeout: int = 600,
    ) -> Tuple[bool, str, int, List[str]]:
        """Run tests, auto-install missing modules once, and retry."""
        ok, output, returncode = self.run_tests(instance_dir, command, timeout=timeout)
        installed_now: List[str] = []
        if ok:
            return ok, output, returncode, installed_now

        missing_modules = self.extract_missing_modules(output)
        if not missing_modules:
            return ok, output, returncode, installed_now

        candidates: List[str] = []
        for mod in missing_modules:
            pkg = self.MODULE_PACKAGE_MAP.get(mod, mod)
            if pkg not in auto_installed_packages and pkg not in candidates:
                candidates.append(pkg)

        if not candidates:
            return ok, output, returncode, installed_now

        install_ok, install_output = self.install_python_packages(
            instance_dir=instance_dir,
            packages=candidates,
            python_executable=python_executable,
        )
        installed_now = candidates
        if install_ok:
            auto_installed_packages.extend(candidates)
            retry_ok, retry_output, retry_returncode = self.run_tests(
                instance_dir, command, timeout=timeout
            )
            merged_output = (
                (output or "")
                + "\n\n[AUTO-INSTALL]\n"
                + f"Installed packages: {candidates}\n"
                + (install_output or "")
                + "\n\n[RETRY-RESULT]\n"
                + (retry_output or "")
            )
            return retry_ok, merged_output, retry_returncode, installed_now

        merged_output = (
            (output or "")
            + "\n\n[AUTO-INSTALL-FAILED]\n"
            + f"Attempted packages: {candidates}\n"
            + (install_output or "")
        )
        return ok, merged_output, returncode, installed_now

    @staticmethod
    def _safe_repo_path(instance_dir: Path, relative_path: str) -> Path:
        """Resolve and validate path stays within repository root."""
        rel = relative_path.strip().lstrip("./")
        abs_path = (instance_dir / rel).resolve()
        abs_path.relative_to(instance_dir.resolve())
        return abs_path

    @staticmethod
    def _repo_snapshot(instance_dir: Path, max_files: int = 250) -> str:
        """Create compact repository context for planner beliefs."""
        try:
            proc = subprocess.run(
                ["git", "ls-files"],
                cwd=instance_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            files = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
            if files:
                shown = files[:max_files]
                suffix = f"\n... ({len(files) - max_files} files omitted)" if len(files) > max_files else ""
                return "\n".join(shown) + suffix
        except Exception:
            pass

        files: List[str] = []
        for path in sorted(instance_dir.rglob("*")):
            if path.is_file():
                try:
                    rel = str(path.relative_to(instance_dir))
                    if rel.startswith(".git/"):
                        continue
                    files.append(rel)
                except Exception:
                    continue
            if len(files) >= max_files:
                break
        return "\n".join(files)

    def execute_plan(
        self,
        plan,
        instance: Dict[str, Any],
        instance_dir: Path,
        issue_desc: str,
        default_test_command: List[str] | str,
        python_executable: str,
        test_timeout: int = 600,
        max_steps: int = 40,
        auto_installed_packages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute BDI coding plan in dependency order."""
        if auto_installed_packages is None:
            auto_installed_packages = []

        graph = plan.to_networkx()
        is_valid, _ = PlanVerifier.verify(graph)
        if is_valid:
            ordered_ids = PlanVerifier.topological_sort(graph)
            node_lookup = {node.id: node for node in plan.nodes}
            ordered_nodes = [node_lookup[node_id] for node_id in ordered_ids if node_id in node_lookup]
        else:
            ordered_nodes = list(plan.nodes)

        if max_steps > 0:
            ordered_nodes = ordered_nodes[:max_steps]

        file_cache: Dict[str, str] = {}
        skeleton_cache: Dict[str, str] = {}  # AST skeletons for .py files
        test_runs: List[Dict[str, Any]] = []
        step_logs: List[Dict[str, Any]] = []
        execution_error: Optional[str] = None

        for node in ordered_nodes:
            action = node.action_type
            params = node.params or {}
            step_record: Dict[str, Any] = {
                "id": node.id,
                "action_type": action,
                "description": node.description,
                "params": params,
                "status": "ok",
            }

            try:
                if action == "read-file":
                    rel_path = str(params.get("file", "")).strip()
                    if not rel_path:
                        raise ValueError("read-file missing required param: file")
                    abs_path = self._safe_repo_path(instance_dir, rel_path)
                    if not abs_path.exists():
                        raise FileNotFoundError(f"File not found: {rel_path}")
                    content = abs_path.read_text(encoding="utf-8", errors="ignore")
                    file_cache[rel_path] = content
                    step_record["bytes"] = len(content)
                    # Cache AST skeleton for Python files
                    if rel_path.endswith(".py"):
                        skeleton_cache[rel_path] = file_skeleton(content)

                elif action == "edit-file":
                    rel_path = str(params.get("file", "")).strip()
                    if not rel_path:
                        raise ValueError("edit-file missing required param: file")

                    # Block edits to config/build files that should never be modified
                    _EDIT_BLOCKLIST = {
                        "pyproject.toml", "setup.py", "setup.cfg",
                        "tox.ini", "pytest.ini", ".pre-commit-config.yaml",
                        "Makefile", "Dockerfile", ".gitignore",
                    }
                    basename = Path(rel_path).name
                    if basename in _EDIT_BLOCKLIST:
                        step_record["status"] = "skipped"
                        step_record["reason"] = f"edit blocked for config file: {basename}"
                        step_logs.append(step_record)
                        continue

                    # Block edits to test files — SWE-bench test_patch handles
                    # test changes; LLM should only edit source code
                    if "/tests/" in rel_path or basename.startswith("test_") or basename.startswith("tests_"):
                        step_record["status"] = "skipped"
                        step_record["reason"] = f"edit blocked for test file: {rel_path}"
                        step_logs.append(step_record)
                        continue

                    abs_path = self._safe_repo_path(instance_dir, rel_path)
                    if rel_path not in file_cache:
                        if abs_path.exists():
                            file_cache[rel_path] = abs_path.read_text(encoding="utf-8", errors="ignore")
                        else:
                            file_cache[rel_path] = ""
                            abs_path.parent.mkdir(parents=True, exist_ok=True)

                    # AST-aware viewport: show skeleton + target entity instead of
                    # blind truncation, so the model sees relevant code structure
                    target_entity = str(params.get("target", "")).strip()
                    full_content = file_cache[rel_path]
                    if target_entity and rel_path.endswith(".py"):
                        content_for_llm = file_skeleton_with_context(
                            full_content, target_entity
                        )
                        if len(content_for_llm) > 15000:
                            content_for_llm = content_for_llm[:15000]
                    else:
                        # Fallback for non-Python files or no target specified
                        content_for_llm = full_content[:12000]

                    prediction = self.planner.implement_change(
                        file_path=rel_path,
                        current_content=content_for_llm,
                        issue_description=issue_desc[:4000],
                        step_description=node.description,
                    )

                    # Apply search/replace edit instead of full file replacement
                    search_block = getattr(prediction, "search_block", "")
                    replace_block = getattr(prediction, "replace_block", "")
                    if search_block and isinstance(search_block, str):
                        current = file_cache[rel_path]
                        if search_block in current:
                            new_content = current.replace(search_block, replace_block, 1)
                        else:
                            # Fuzzy match: try stripping leading/trailing whitespace per line
                            search_stripped = "\n".join(l.rstrip() for l in search_block.splitlines())
                            current_stripped = "\n".join(l.rstrip() for l in current.splitlines())
                            if search_stripped in current_stripped:
                                # Apply on stripped version then reconstruct
                                new_content = current_stripped.replace(search_stripped, replace_block, 1)
                            else:
                                logger.warning(
                                    f"search_block not found in {rel_path}, "
                                    f"first 80 chars: {search_block[:80]!r}"
                                )
                                new_content = current  # no change, skip this edit
                    else:
                        logger.warning(f"LLM returned empty search_block for {rel_path}")
                        new_content = file_cache[rel_path]  # no change

                    if not isinstance(new_content, str):
                        raise ValueError("LLM returned non-string file content")
                    abs_path.write_text(new_content, encoding="utf-8")
                    file_cache[rel_path] = new_content
                    step_record["bytes"] = len(new_content)

                elif action == "create-file":
                    rel_path = str(params.get("file", "")).strip()
                    if not rel_path:
                        raise ValueError("create-file missing required param: file")
                    abs_path = self._safe_repo_path(instance_dir, rel_path)
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    if not abs_path.exists():
                        abs_path.write_text("", encoding="utf-8")
                    file_cache[rel_path] = abs_path.read_text(encoding="utf-8", errors="ignore")

                elif action == "run-test":
                    test_selector = str(params.get("test", "")).strip()
                    if test_selector:
                        command = self.build_step_test_command(
                            instance=instance,
                            test_selector=test_selector,
                            python_executable=python_executable,
                        )
                    else:
                        command = default_test_command[:] if isinstance(default_test_command, list) else default_test_command
                    ok, output, returncode, installed_now = self.run_tests_with_dependency_fix(
                        instance_dir=instance_dir,
                        command=command,
                        auto_installed_packages=auto_installed_packages,
                        python_executable=python_executable,
                        timeout=test_timeout,
                    )
                    test_runs.append(
                        {
                            "command": command,
                            "success": ok,
                            "returncode": returncode,
                            "output_tail": output[-2000:],
                            "auto_installed_packages": installed_now,
                        }
                    )
                    step_record["test_success"] = ok
                    step_record["test_returncode"] = returncode
                    if installed_now:
                        step_record["auto_installed_packages"] = installed_now

                else:
                    # Unsupported action is non-fatal but recorded.
                    step_record["status"] = "skipped"
                    step_record["reason"] = f"unsupported action_type: {action}"

            except Exception as exc:
                step_record["status"] = "error"
                step_record["error"] = str(exc)
                execution_error = str(exc)
                step_logs.append(step_record)
                break

            step_logs.append(step_record)

        return {
            "executed_steps": len(step_logs),
            "step_logs": step_logs,
            "test_runs": test_runs,
            "execution_error": execution_error,
        }

    @staticmethod
    def _changed_files(instance_dir: Path) -> List[str]:
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=instance_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]

    @staticmethod
    def _full_diff(instance_dir: Path) -> str:
        proc = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=instance_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout or ""

    def run_instance(
        self,
        instance_id: str,
        test_timeout: int = 600,
        max_plan_steps: int = 40,
        setup_timeout: int = 900,
        keep_workspace: bool = True,
    ) -> Dict[str, Any]:
        """Run planning/edit/test loop for one SWE-bench instance."""
        start = time.time()
        instance = self.get_instance(instance_id)
        result: Dict[str, Any] = {
            "instance_id": instance_id,
            "repo": instance.get("repo"),
            "base_commit": instance.get("base_commit"),
            "environment_setup_commit": instance.get("environment_setup_commit"),
            "version": instance.get("version"),
            "status": "error",
            "tests_passed": False,
            "changed_files": [],
            "changed_files_count": 0,
            "plan_steps_total": 0,
            "plan_steps_executed": 0,
            "durations_sec": {},
            "error": None,
            "error_category": None,
        }

        repo_dir: Optional[Path] = None
        setup_start = time.time()
        try:
            repo_dir = self.setup_repo(instance, cleanup_existing=True, clone_timeout=setup_timeout)
            result["durations_sec"]["setup"] = round(time.time() - setup_start, 3)
        except Exception as exc:
            result["status"] = "setup_error"
            result["error"] = str(exc)
            result["error_category"] = "environment_or_dependency_error"
            result["durations_sec"]["total"] = round(time.time() - start, 3)
            return result

        env_start = time.time()
        env_info = self._prepare_python_environment(
            instance=instance,
            instance_dir=repo_dir,
            timeout=setup_timeout,
        )
        result["durations_sec"]["env_setup"] = round(time.time() - env_start, 3)
        result["environment"] = {
            "used_conda": env_info.get("used_conda"),
            "conda_executable": env_info.get("conda_executable"),
            "env_prefix": env_info.get("env_prefix"),
            "python_executable": env_info.get("python_executable"),
            "python_version": env_info.get("python_version"),
            "spec_found": env_info.get("spec_found"),
            "spec_python": env_info.get("spec_python"),
            "constants_load_error": env_info.get("constants_load_error"),
            "setup_steps": env_info.get("setup_steps", []),
        }
        if not env_info.get("ok"):
            result["status"] = "setup_error"
            result["error"] = str(env_info.get("error", "python_environment_setup_failed"))
            result["error_category"] = "environment_or_dependency_error"
            result["durations_sec"]["total"] = round(time.time() - start, 3)
            if not keep_workspace and repo_dir and repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
            return result

        python_executable = str(env_info.get("python_executable") or sys.executable)

        fail_to_pass = self.parse_test_field(instance.get("FAIL_TO_PASS"))
        pass_to_pass = self.parse_test_field(instance.get("PASS_TO_PASS"))
        beliefs = (
            f"Repository: {instance.get('repo')}\n"
            f"Base commit: {instance.get('base_commit')}\n"
            f"Environment setup commit: {instance.get('environment_setup_commit')}\n"
            f"Version: {instance.get('version')}\n"
            f"Known failing tests: {fail_to_pass[:25]}\n"
            f"Regression tests to preserve: {pass_to_pass[:25]}\n\n"
            f"Repository file snapshot:\n{self._repo_snapshot(repo_dir)}"
        )
        desire = (
            "Fix the issue and make failing tests pass without breaking regression tests.\n\n"
            f"Issue:\n{instance.get('problem_statement', '')}"
            + (f"\n\nHints:\n{instance.get('hints_text', '')}" if instance.get("hints_text") else "")
        )

        try:
            plan_start = time.time()
            prediction = self.planner.forward(beliefs=beliefs, desire=desire)
            plan = prediction.plan
            result["durations_sec"]["planning"] = round(time.time() - plan_start, 3)
            result["plan_steps_total"] = len(plan.nodes)
        except Exception as exc:
            result["status"] = "planning_error"
            result["error"] = str(exc)
            result["error_category"] = "planner_error"
            result["durations_sec"]["total"] = round(time.time() - start, 3)
            return result

        default_test_command = self.build_test_command(instance, python_executable=python_executable)
        result["final_test_command"] = default_test_command
        auto_installed_packages: List[str] = []
        execution = self.execute_plan(
            plan=plan,
            instance=instance,
            instance_dir=repo_dir,
            issue_desc=(instance.get("problem_statement", "") or "")
            + (f"\n\nHints:\n{instance.get('hints_text', '')}" if instance.get("hints_text") else ""),
            default_test_command=default_test_command,
            python_executable=python_executable,
            test_timeout=test_timeout,
            max_steps=max_plan_steps,
            auto_installed_packages=auto_installed_packages,
        )
        result["plan_steps_executed"] = execution["executed_steps"]
        result["plan_step_logs"] = execution["step_logs"]
        result["intermediate_test_runs"] = execution["test_runs"]

        if execution.get("execution_error"):
            result["status"] = "execution_error"
            result["error"] = execution["execution_error"]
            if self._is_environment_error(str(execution["execution_error"])):
                result["error_category"] = "environment_or_dependency_error"
            else:
                result["error_category"] = "execution_error"

        final_test_command = default_test_command
        tests_passed, final_test_output, returncode, final_installed_now = self.run_tests_with_dependency_fix(
            instance_dir=repo_dir,
            command=final_test_command,
            auto_installed_packages=auto_installed_packages,
            python_executable=python_executable,
            timeout=test_timeout,
        )
        result["tests_passed"] = tests_passed
        result["final_test_returncode"] = returncode
        result["final_test_output_tail"] = final_test_output[-4000:]
        result["changed_files"] = self._changed_files(repo_dir)
        result["changed_files_count"] = len(result["changed_files"])
        result["git_diff"] = self._full_diff(repo_dir)
        result["auto_installed_packages"] = auto_installed_packages
        if final_installed_now:
            result["final_test_auto_installed_packages"] = final_installed_now

        if result["status"] not in {"execution_error"}:
            if tests_passed:
                result["status"] = "passed"
                result["error_category"] = None
            else:
                result["status"] = "failed_tests"
                if self._is_environment_error(final_test_output):
                    result["error_category"] = "environment_or_dependency_error"
                elif returncode == 124:
                    result["error_category"] = "timeout_or_runtime_error"
                else:
                    result["error_category"] = "test_failure"
        elif not tests_passed and self._is_environment_error(final_test_output):
            result["error_category"] = "environment_or_dependency_error"

        result["durations_sec"]["total"] = round(time.time() - start, 3)

        if not keep_workspace and repo_dir and repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)

        return result

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, required=True, help="Instance ID to run")
    parser.add_argument("--workspace", type=str, default="swe_bench_workspace")
    parser.add_argument("--test_timeout", type=int, default=600)
    parser.add_argument("--setup_timeout", type=int, default=900)
    parser.add_argument("--max_plan_steps", type=int, default=40)
    parser.add_argument("--keep_workspace", action="store_true")
    args = parser.parse_args()

    harness = LocalSWEBenchHarness(workspace_dir=args.workspace)
    output = harness.run_instance(
        instance_id=args.instance,
        test_timeout=args.test_timeout,
        setup_timeout=args.setup_timeout,
        max_plan_steps=args.max_plan_steps,
        keep_workspace=args.keep_workspace,
    )
    print(json.dumps(output, indent=2))
