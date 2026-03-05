#!/usr/bin/env python3
"""
Multi-agent scientist orchestration for end-to-end experiments.

This script implements a role-based "scientist team" workflow without
external orchestration dependencies. It covers:
1) protocol audit
2) reproducibility audit
3) baseline benchmark
4) ablation benchmark
5) failure mining
6) error taxonomy
7) hypothesis generation
8) SWE-bench benchmark
9) SWE-bench error taxonomy
10) regression gate
11) final report

Features:
- Stage-level checkpoint/resume
- Atomic checkpoint writes
- Per-stage logs and machine-readable artifacts
- Fail-fast by default (can continue on error)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOMAINS = ["blocksworld", "logistics", "depots"]
DEFAULT_MODES = ["NAIVE", "BDI_ONLY", "FULL_VERIFIED"]
DEFAULT_SWE_LIMIT = 50

AGENTS: List[Dict[str, str]] = [
    {
        "id": "protocol_auditor",
        "role": "Protocol Auditor",
        "responsibility": "Freeze run context, environment, and guardrails before execution.",
    },
    {
        "id": "reproducibility_guard",
        "role": "Reproducibility Guard",
        "responsibility": "Run deterministic offline checks and reject unstable setup.",
    },
    {
        "id": "benchmark_executor",
        "role": "Benchmark Executor",
        "responsibility": "Run PlanBench baseline with checkpoint/resume and strict logs.",
    },
    {
        "id": "swe_bench_executor",
        "role": "SWE-bench Executor",
        "responsibility": "Run SWE-bench local harness with checkpoint/resume and per-instance artifacts.",
    },
    {
        "id": "ablation_scientist",
        "role": "Ablation Scientist",
        "responsibility": "Execute NAIVE/BDI_ONLY/FULL_VERIFIED comparative runs.",
    },
    {
        "id": "failure_miner",
        "role": "Failure Miner",
        "responsibility": "Extract failed instances and attach structured diagnostics.",
    },
    {
        "id": "taxonomy_analyst",
        "role": "Taxonomy Analyst",
        "responsibility": "Cluster errors into interpretable categories with counts.",
    },
    {
        "id": "hypothesis_designer",
        "role": "Hypothesis Designer",
        "responsibility": "Generate prioritized improvement hypotheses from taxonomy.",
    },
    {
        "id": "regression_gatekeeper",
        "role": "Regression Gatekeeper",
        "responsibility": "Re-run targeted regression set and report pass/fail deltas.",
    },
    {
        "id": "report_editor",
        "role": "Report Editor",
        "responsibility": "Assemble an end-to-end final report and machine-readable summary.",
    },
]

STAGE_ORDER: List[str] = [
    "protocol_audit",
    "reproducibility_audit",
    "baseline_benchmark",
    "ablation_benchmark",
    "failure_mining",
    "error_taxonomy",
    "hypothesis_generation",
    "swe_bench_benchmark",
    "swe_bench_error_taxonomy",
    "regression_gate",
    "final_report",
]

STAGE_OWNER: Dict[str, str] = {
    "protocol_audit": "protocol_auditor",
    "reproducibility_audit": "reproducibility_guard",
    "baseline_benchmark": "benchmark_executor",
    "ablation_benchmark": "ablation_scientist",
    "failure_mining": "failure_miner",
    "error_taxonomy": "taxonomy_analyst",
    "hypothesis_generation": "hypothesis_designer",
    "swe_bench_benchmark": "swe_bench_executor",
    "swe_bench_error_taxonomy": "taxonomy_analyst",
    "regression_gate": "regression_gatekeeper",
    "final_report": "report_editor",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp_path, path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        return str(path.resolve())


def run_capture(cmd: List[str], cwd: Path = PROJECT_ROOT) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip()


def find_latest_result_file(root: Path, domain: str) -> Optional[Path]:
    files = sorted(root.glob(f"results_{domain}_*.json"))
    return files[-1] if files else None


def parse_planbench_summary(result_file: Path) -> Dict[str, Any]:
    data = load_json(result_file)
    rows = data.get("results", [])
    summary = data.get("summary", {})

    success_count = summary.get("success_count")
    if success_count is None:
        success_count = sum(1 for row in rows if row.get("success") is True)

    failed_count = summary.get("failed_count")
    if failed_count is None:
        failed_count = len(rows) - success_count

    total = summary.get("total_evaluated", len(rows))
    success_rate = summary.get("success_rate")
    if success_rate is None:
        success_rate = (success_count / total) if total else 0.0

    return {
        "result_file": relpath(result_file),
        "total_evaluated": total,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": success_rate,
        "structural_only_success": summary.get("structural_only_success"),
        "symbolic_caught_errors": summary.get("symbolic_caught_errors"),
        "physics_caught_errors": summary.get("physics_caught_errors"),
        "auto_repair": summary.get("auto_repair", {}),
        "val_repair": summary.get("val_repair", {}),
    }


def parse_ablation_summary(result_file: Path) -> Dict[str, Any]:
    data = load_json(result_file)
    rows = data.get("results", [])

    def row_success(row: Dict[str, Any]) -> bool:
        if "is_valid" in row:
            return bool(row.get("is_valid"))
        if "generated" in row:
            return bool(row.get("generated"))
        return False

    success_count = sum(1 for row in rows if row_success(row))
    total = len(rows)
    success_rate = (success_count / total) if total else 0.0

    summary: Dict[str, Any] = {
        "result_file": relpath(result_file),
        "total": total,
        "success_count": success_count,
        "success_rate": success_rate,
    }

    if "metrics" in data and isinstance(data["metrics"], dict):
        summary["metrics"] = data["metrics"]
    if "mode" in data:
        summary["mode"] = data["mode"]

    return summary


def parse_swe_summary(summary_file: Path) -> Dict[str, Any]:
    data = load_json(summary_file)
    return {
        "summary_file": relpath(summary_file),
        "run_id": data.get("run_id"),
        "total_instances": data.get("total_instances", 0),
        "passed": data.get("passed", 0),
        "failed": data.get("failed", 0),
        "pass_rate": data.get("pass_rate", 0.0),
        "status_counts": data.get("status_counts", {}),
        "error_taxonomy": data.get("error_taxonomy", {}),
        "avg_duration_sec": data.get("avg_duration_sec", 0.0),
    }


def has_api_credentials() -> bool:
    return bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )


class ScientistTeamRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        out_dir = Path(args.output_dir)
        self.run_root = out_dir if out_dir.is_absolute() else (PROJECT_ROOT / out_dir)
        self.logs_dir = self.run_root / "logs"
        self.artifacts_dir = self.run_root / "artifacts"
        self.reports_dir = self.run_root / "reports"
        self.checkpoint_file = self.run_root / "checkpoint.json"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.stage_funcs: Dict[str, Callable[[], Dict[str, Any]]] = {
            "protocol_audit": self.stage_protocol_audit,
            "reproducibility_audit": self.stage_reproducibility_audit,
            "baseline_benchmark": self.stage_baseline_benchmark,
            "ablation_benchmark": self.stage_ablation_benchmark,
            "failure_mining": self.stage_failure_mining,
            "error_taxonomy": self.stage_error_taxonomy,
            "hypothesis_generation": self.stage_hypothesis_generation,
            "swe_bench_benchmark": self.stage_swe_bench_benchmark,
            "swe_bench_error_taxonomy": self.stage_swe_bench_error_taxonomy,
            "regression_gate": self.stage_regression_gate,
            "final_report": self.stage_final_report,
        }

        if args.resume and self.checkpoint_file.exists():
            self.state = load_json(self.checkpoint_file)
            self.state["updated_at"] = now_utc()
            self.state["config"] = vars(args)
        else:
            self.state = {
                "schema_version": 1,
                "run_id": f"scientist_team_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "created_at": now_utc(),
                "updated_at": now_utc(),
                "project_root": str(PROJECT_ROOT.resolve()),
                "config": vars(args),
                "agents": AGENTS,
                "stages": {},
            }
        self.save_state()

    def save_state(self) -> None:
        self.state["updated_at"] = now_utc()
        write_json_atomic(self.checkpoint_file, self.state)

    def run_command(
        self,
        command: List[str],
        log_file: Path,
        env_overrides: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        cmd_str = " ".join(shlex.quote(c) for c in command)
        started_ts = now_utc()
        start = time.time()

        if self.args.dry_run:
            write_text_atomic(
                log_file,
                f"[DRY-RUN] {cmd_str}\nstarted_at={started_ts}\n",
            )
            return {
                "command": cmd_str,
                "log_file": relpath(log_file),
                "returncode": 0,
                "duration_sec": 0.0,
                "dry_run": True,
            }

        try:
            with log_file.open("w", encoding="utf-8") as f:
                f.write(f"$ {cmd_str}\n")
                f.write(f"started_at={started_ts}\n\n")
                f.flush()
                proc = subprocess.run(
                    command,
                    cwd=str(PROJECT_ROOT),
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            return {
                "command": cmd_str,
                "log_file": relpath(log_file),
                "returncode": proc.returncode,
                "duration_sec": round(time.time() - start, 3),
            }
        except subprocess.TimeoutExpired:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"\n[ERROR] Timeout after {timeout}s\n")
            return {
                "command": cmd_str,
                "log_file": relpath(log_file),
                "returncode": 124,
                "duration_sec": round(time.time() - start, 3),
                "timeout": timeout,
            }

    def selected_stages(self) -> List[str]:
        if not self.args.stages:
            return STAGE_ORDER
        requested = [s.strip() for s in self.args.stages.split(",") if s.strip()]
        invalid = [s for s in requested if s not in STAGE_ORDER]
        if invalid:
            raise ValueError(f"Unknown stage(s): {invalid}. Valid: {STAGE_ORDER}")
        return requested

    def run(self) -> int:
        stages = self.selected_stages()
        for stage_name in stages:
            owner = STAGE_OWNER.get(stage_name, "unknown")
            current = self.state["stages"].get(stage_name, {})

            if current.get("status") == "completed" and not self.args.force:
                print(f"[SKIP] {stage_name}: already completed")
                continue

            print(f"[RUN ] {stage_name} (owner={owner})")
            started_at = now_utc()
            started = time.time()
            self.state["stages"][stage_name] = {
                "owner": owner,
                "status": "running",
                "started_at": started_at,
            }
            self.save_state()

            try:
                payload = self.stage_funcs[stage_name]()
                ended_at = now_utc()
                self.state["stages"][stage_name] = {
                    "owner": owner,
                    "status": "completed",
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_sec": round(time.time() - started, 3),
                    "summary": payload.get("summary", {}),
                    "artifacts": payload.get("artifacts", []),
                    "logs": payload.get("logs", []),
                }
                self.save_state()
                print(f"[DONE] {stage_name}")
            except Exception as exc:
                ended_at = now_utc()
                self.state["stages"][stage_name] = {
                    "owner": owner,
                    "status": "failed",
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_sec": round(time.time() - started, 3),
                    "error": str(exc),
                }
                self.save_state()
                print(f"[FAIL] {stage_name}: {exc}")
                if not self.args.continue_on_error:
                    return 1
        return 0

    def stage_protocol_audit(self) -> Dict[str, Any]:
        env_summary = {
            "LLM_MODEL": os.environ.get("LLM_MODEL"),
            "OPENAI_API_BASE": os.environ.get("OPENAI_API_BASE"),
            "OPENAI_API_KEY_set": bool(os.environ.get("OPENAI_API_KEY")),
            "ANTHROPIC_API_KEY_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "GOOGLE_API_KEY_set": bool(os.environ.get("GOOGLE_API_KEY")),
            "GOOGLE_APPLICATION_CREDENTIALS_set": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        }
        payload = {
            "timestamp": now_utc(),
            "project_root": str(PROJECT_ROOT.resolve()),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "git_branch": run_capture(["git", "branch", "--show-current"]),
            "git_commit": run_capture(["git", "rev-parse", "HEAD"]),
            "git_status_short": run_capture(["git", "status", "--short"]),
            "environment": env_summary,
            "agents": AGENTS,
            "stage_order": STAGE_ORDER,
        }
        json_path = self.reports_dir / "protocol_audit.json"
        md_path = self.reports_dir / "protocol_audit.md"
        write_json_atomic(json_path, payload)

        lines = [
            "# Protocol Audit",
            "",
            f"- Timestamp: {payload['timestamp']}",
            f"- Python: `{payload['python_version']}`",
            f"- Platform: `{payload['platform']}`",
            f"- Branch: `{payload['git_branch']}`",
            f"- Commit: `{payload['git_commit']}`",
            "",
            "## Environment",
            f"- `LLM_MODEL`: `{env_summary['LLM_MODEL']}`",
            f"- `OPENAI_API_BASE`: `{env_summary['OPENAI_API_BASE']}`",
            f"- `OPENAI_API_KEY_set`: `{env_summary['OPENAI_API_KEY_set']}`",
            f"- `ANTHROPIC_API_KEY_set`: `{env_summary['ANTHROPIC_API_KEY_set']}`",
            f"- `GOOGLE_API_KEY_set`: `{env_summary['GOOGLE_API_KEY_set']}`",
            f"- `GOOGLE_APPLICATION_CREDENTIALS_set`: `{env_summary['GOOGLE_APPLICATION_CREDENTIALS_set']}`",
            "",
            "## Git Status",
            "```text",
            payload["git_status_short"] or "(clean)",
            "```",
        ]
        write_text_atomic(md_path, "\n".join(lines) + "\n")
        return {
            "summary": {"git_commit": payload["git_commit"], "git_branch": payload["git_branch"]},
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": [],
        }

    def stage_reproducibility_audit(self) -> Dict[str, Any]:
        commands = [
            (
                "compile_check",
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    "scripts/run_evaluation.py",
                    "scripts/run_planbench_full.py",
                    "scripts/run_scientist_team.py",
                    "scripts/swe_bench_harness.py",
                    "scripts/run_swe_bench_batch.py",
                ],
            ),
            ("unit_suite", [sys.executable, "scripts/run_evaluation.py", "--mode", "unit"]),
            (
                "verification_suite",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_symbolic_verifier.py",
                    "tests/test_symbolic_verifier_integration.py",
                    "tests/test_blocksworld_physics_validator.py",
                    "tests/test_plan_repair.py",
                    "-q",
                ],
            ),
        ]

        run_results: Dict[str, Any] = {}
        logs: List[str] = []
        for name, cmd in commands:
            log_file = self.logs_dir / f"repro_{name}.log"
            result = self.run_command(cmd, log_file)
            run_results[name] = result
            logs.append(result["log_file"])
            if result["returncode"] != 0:
                raise RuntimeError(f"Reproducibility command failed: {name} (rc={result['returncode']})")

        summary_path = self.reports_dir / "reproducibility_audit.json"
        write_json_atomic(summary_path, {"timestamp": now_utc(), "commands": run_results})
        return {
            "summary": {"commands": {k: v["returncode"] for k, v in run_results.items()}},
            "artifacts": [relpath(summary_path)],
            "logs": logs,
        }

    def stage_baseline_benchmark(self) -> Dict[str, Any]:
        if not self.args.dry_run and not has_api_credentials():
            raise RuntimeError("No API credential found for baseline benchmark.")

        baseline_root = self.artifacts_dir / "baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        domain_summaries: Dict[str, Any] = {}
        logs: List[str] = []

        for domain in self.args.domains:
            domain_out = baseline_root / domain
            domain_out.mkdir(parents=True, exist_ok=True)
            cmd = [
                sys.executable,
                "scripts/run_planbench_full.py",
                "--domain",
                domain,
                "--output_dir",
                str(domain_out),
                "--parallel",
                "--workers",
                str(self.args.workers),
                "--checkpoint_every",
                str(self.args.checkpoint_every),
            ]
            if self.args.max_instances is not None:
                cmd += ["--max_instances", str(self.args.max_instances)]

            log_file = self.logs_dir / f"baseline_{domain}.log"
            result = self.run_command(cmd, log_file)
            logs.append(result["log_file"])
            if result["returncode"] != 0:
                raise RuntimeError(f"Baseline benchmark failed for {domain} (rc={result['returncode']})")

            if self.args.dry_run:
                domain_summaries[domain] = {"result_file": None, "planned": True}
                continue

            result_file = find_latest_result_file(domain_out, domain)
            if not result_file:
                raise RuntimeError(f"No result file produced for domain '{domain}' in {relpath(domain_out)}")
            domain_summaries[domain] = parse_planbench_summary(result_file)

        json_path = self.reports_dir / "baseline_summary.json"
        md_path = self.reports_dir / "baseline_summary.md"
        write_json_atomic(json_path, {"timestamp": now_utc(), "domains": domain_summaries})

        lines = ["# Baseline Benchmark Summary", ""]
        lines.append("| Domain | Success/Total | Success Rate | Result File |")
        lines.append("|---|---:|---:|---|")
        for domain in self.args.domains:
            s = domain_summaries.get(domain, {})
            if s.get("planned"):
                lines.append(f"| {domain} | planned | planned | - |")
            else:
                lines.append(
                    f"| {domain} | {s.get('success_count', 0)}/{s.get('total_evaluated', 0)} "
                    f"| {s.get('success_rate', 0.0):.2%} | `{s.get('result_file')}` |"
                )
        write_text_atomic(md_path, "\n".join(lines) + "\n")

        return {
            "summary": {"domains": domain_summaries},
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": logs,
        }

    def stage_ablation_benchmark(self) -> Dict[str, Any]:
        if not self.args.dry_run and not has_api_credentials():
            raise RuntimeError("No API credential found for ablation benchmark.")

        ablation_out = self.artifacts_dir / "ablation"
        ablation_out.mkdir(parents=True, exist_ok=True)
        mode_summaries: Dict[str, Any] = {}
        logs: List[str] = []

        for mode in DEFAULT_MODES:
            cmd = [sys.executable, "scripts/run_evaluation.py", "--mode", "benchmark"]
            log_file = self.logs_dir / f"ablation_{mode}.log"
            result = self.run_command(cmd, log_file, env_overrides={"AGENT_EXECUTION_MODE": mode})
            logs.append(result["log_file"])
            if result["returncode"] != 0:
                raise RuntimeError(f"Ablation benchmark failed for mode={mode} (rc={result['returncode']})")

            source_file = PROJECT_ROOT / "runs" / f"ablation_{mode}" / "benchmark_results.json"
            copied_file = ablation_out / f"benchmark_{mode}.json"

            if self.args.dry_run:
                mode_summaries[mode] = {"planned": True}
                continue

            if not source_file.exists():
                raise RuntimeError(f"Missing ablation output for mode={mode}: {relpath(source_file)}")
            shutil.copy2(source_file, copied_file)
            mode_summaries[mode] = parse_ablation_summary(copied_file)

        json_path = self.reports_dir / "ablation_summary.json"
        md_path = self.reports_dir / "ablation_summary.md"
        write_json_atomic(json_path, {"timestamp": now_utc(), "modes": mode_summaries})

        lines = ["# Ablation Summary", ""]
        lines.append("| Mode | Success/Total | Success Rate | Result File |")
        lines.append("|---|---:|---:|---|")
        for mode in DEFAULT_MODES:
            s = mode_summaries.get(mode, {})
            if s.get("planned"):
                lines.append(f"| {mode} | planned | planned | - |")
            else:
                lines.append(
                    f"| {mode} | {s.get('success_count', 0)}/{s.get('total', 0)} "
                    f"| {s.get('success_rate', 0.0):.2%} | `{s.get('result_file')}` |"
                )
        write_text_atomic(md_path, "\n".join(lines) + "\n")

        return {
            "summary": {"modes": mode_summaries},
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": logs,
        }

    def _discover_baseline_results(self) -> Dict[str, Path]:
        found: Dict[str, Path] = {}
        baseline_root = self.artifacts_dir / "baseline"
        for domain in self.args.domains:
            latest = find_latest_result_file(baseline_root / domain, domain)
            if latest:
                found[domain] = latest
        return found

    @staticmethod
    def _extract_failure_messages(row: Dict[str, Any]) -> List[str]:
        messages: List[str] = []
        if row.get("error"):
            messages.append(str(row["error"]))

        layers = row.get("bdi_metrics", {}).get("verification_layers", {})
        for layer_name in ["structural", "symbolic", "physics"]:
            layer = layers.get(layer_name, {})
            for err in layer.get("errors", []) or []:
                msg = str(err).strip()
                if msg:
                    messages.append(f"{layer_name}: {msg}")

        if not messages:
            messages.append("unknown_failure")
        return messages

    def stage_failure_mining(self) -> Dict[str, Any]:
        baseline_results = self._discover_baseline_results()
        if not baseline_results and not self.args.dry_run:
            raise RuntimeError("No baseline result files found. Run baseline_benchmark first.")

        failure_records: List[Dict[str, Any]] = []
        per_domain_counts: Dict[str, int] = {}

        for domain, result_file in baseline_results.items():
            data = load_json(result_file)
            rows = data.get("results", [])
            failed = [row for row in rows if row.get("success") is not True]
            per_domain_counts[domain] = len(failed)
            for row in failed:
                failure_records.append(
                    {
                        "domain": domain,
                        "instance_file": row.get("instance_file"),
                        "instance_name": row.get("instance_name"),
                        "messages": self._extract_failure_messages(row),
                        "val_repair_attempts": row.get("bdi_metrics", {}).get("val_repair", {}).get("attempts", 0),
                        "auto_repair_triggered": row.get("bdi_metrics", {}).get("auto_repair", {}).get("triggered", False),
                    }
                )

        if self.args.dry_run:
            per_domain_counts = {domain: 0 for domain in self.args.domains}
            failure_records = []

        json_path = self.reports_dir / "failure_cases.json"
        md_path = self.reports_dir / "failure_cases.md"
        alias_json_path = self.reports_dir / "failure_mining.json"
        alias_md_path = self.reports_dir / "failure_mining.md"
        payload = {
            "timestamp": now_utc(),
            "total_failures": len(failure_records),
            "per_domain": per_domain_counts,
            "failures": failure_records,
        }
        write_json_atomic(json_path, payload)
        write_json_atomic(alias_json_path, payload)

        lines = ["# Failure Mining", ""]
        lines.append(f"- Total failures: {len(failure_records)}")
        for domain in self.args.domains:
            lines.append(f"- {domain}: {per_domain_counts.get(domain, 0)}")
        if failure_records:
            lines.append("")
            lines.append("## First 20 Failures")
            for row in failure_records[:20]:
                lines.append(
                    f"- [{row['domain']}] `{row.get('instance_name')}` "
                    f"`{row.get('instance_file')}` :: {row['messages'][0]}"
                )
        write_text_atomic(md_path, "\n".join(lines) + "\n")
        write_text_atomic(alias_md_path, "\n".join(lines) + "\n")

        return {
            "summary": {"total_failures": len(failure_records), "per_domain": per_domain_counts},
            "artifacts": [
                relpath(json_path),
                relpath(md_path),
                relpath(alias_json_path),
                relpath(alias_md_path),
            ],
            "logs": [],
        }

    @staticmethod
    def _categorize_message(message: str) -> str:
        m = message.lower()
        if "disconnected" in m:
            return "structural_disconnected"
        if "cycle" in m:
            return "structural_cycle"
        if "precondition" in m or "goal not satisfied" in m:
            return "symbolic_precondition"
        if "invalid action" in m:
            return "symbolic_invalid_action"
        if "type-checking" in m or "type error" in m:
            return "symbolic_type_error"
        if "timeout" in m:
            return "infra_timeout"
        if "429" in m or "quota" in m or "rate" in m or "resourceexhausted" in m:
            return "infra_rate_limit"
        if "exec format error" in m or "incompatible with current os" in m:
            return "env_val_binary"
        if "parse" in m:
            return "parser_issue"
        if "empty plan" in m:
            return "generation_empty_plan"
        return "unknown"

    def stage_error_taxonomy(self) -> Dict[str, Any]:
        failures_path = self.reports_dir / "failure_cases.json"
        if not failures_path.exists():
            raise RuntimeError("Missing failure_cases.json. Run failure_mining first.")
        failure_data = load_json(failures_path)
        failures = failure_data.get("failures", [])

        global_counter: Counter[str] = Counter()
        by_domain: Dict[str, Counter[str]] = defaultdict(Counter)

        for record in failures:
            domain = record.get("domain", "unknown")
            messages = record.get("messages", [])
            for msg in messages:
                category = self._categorize_message(str(msg))
                global_counter[category] += 1
                by_domain[domain][category] += 1

        payload = {
            "timestamp": now_utc(),
            "global_counts": dict(global_counter),
            "per_domain_counts": {d: dict(c) for d, c in by_domain.items()},
        }

        json_path = self.reports_dir / "error_taxonomy.json"
        md_path = self.reports_dir / "error_taxonomy.md"
        write_json_atomic(json_path, payload)

        lines = ["# Error Taxonomy", ""]
        if not global_counter:
            lines.append("- No failures recorded in current run.")
        else:
            lines.append("## Global")
            for category, count in global_counter.most_common():
                lines.append(f"- {category}: {count}")
            lines.append("")
            lines.append("## Per Domain")
            for domain in sorted(by_domain.keys()):
                lines.append(f"- {domain}:")
                for category, count in by_domain[domain].most_common():
                    lines.append(f"  - {category}: {count}")
        write_text_atomic(md_path, "\n".join(lines) + "\n")

        return {
            "summary": {"global_counts": dict(global_counter)},
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": [],
        }

    def stage_hypothesis_generation(self) -> Dict[str, Any]:
        taxonomy_path = self.reports_dir / "error_taxonomy.json"
        if not taxonomy_path.exists():
            raise RuntimeError("Missing error_taxonomy.json. Run error_taxonomy first.")
        taxonomy = load_json(taxonomy_path).get("global_counts", {})

        action_map = {
            "structural_disconnected": (
                "Add graph-connectivity canonicalization pre-verifier and enforce START/END bridge.",
                "Targets disconnected subgraph generation.",
            ),
            "structural_cycle": (
                "Inject cycle-avoidance constraints into planner and add cycle-specific repair prompts.",
                "Targets deadlock dependencies.",
            ),
            "symbolic_precondition": (
                "Implement explicit precondition simulator before VAL and pass unsatisfied predicates to repair loop.",
                "Targets logically invalid action ordering.",
            ),
            "symbolic_invalid_action": (
                "Add domain action schema canonicalization and strict action-type whitelist checks.",
                "Targets invalid/hallucinated action names.",
            ),
            "symbolic_type_error": (
                "Add object typing checks before symbolic verification.",
                "Targets parameter type mismatches in PDDL actions.",
            ),
            "infra_rate_limit": (
                "Switch to adaptive worker throttle based on recent API error ratio.",
                "Targets high-concurrency API saturation failures.",
            ),
            "infra_timeout": (
                "Introduce per-instance timeout budget and retry budget with checkpoint-safe retries.",
                "Targets long-tail runtime stalls.",
            ),
            "parser_issue": (
                "Harden PDDL parsing with stricter fallbacks and explicit parse diagnostics.",
                "Targets malformed/problematic parse paths.",
            ),
            "generation_empty_plan": (
                "Add empty-plan guardrail and forced minimum-action regeneration path.",
                "Targets null or collapsed generations.",
            ),
            "unknown": (
                "Log richer verifier diagnostics and retain full failed payload for triage.",
                "Targets currently uncategorized failures.",
            ),
        }

        ranked = sorted(taxonomy.items(), key=lambda x: x[1], reverse=True)
        hypotheses: List[Dict[str, Any]] = []
        priority = 1
        for category, count in ranked:
            action, rationale = action_map.get(
                category,
                (
                    "Add targeted instrumentation and retry policy.",
                    "Fallback for uncategorized errors.",
                ),
            )
            hypotheses.append(
                {
                    "priority": priority,
                    "category": category,
                    "observed_count": count,
                    "proposed_change": action,
                    "rationale": rationale,
                }
            )
            priority += 1

        if not hypotheses:
            hypotheses.append(
                {
                    "priority": 1,
                    "category": "no_failure_signal",
                    "observed_count": 0,
                    "proposed_change": "Run larger benchmark slice to surface hard cases before changing core logic.",
                    "rationale": "No evidence of failure in the current sample.",
                }
            )

        json_path = self.reports_dir / "hypotheses.json"
        md_path = self.reports_dir / "hypotheses.md"
        write_json_atomic(json_path, {"timestamp": now_utc(), "hypotheses": hypotheses})

        lines = ["# Improvement Hypotheses", ""]
        for h in hypotheses:
            lines.append(f"{h['priority']}. [{h['category']}] count={h['observed_count']}")
            lines.append(f"   - change: {h['proposed_change']}")
            lines.append(f"   - why: {h['rationale']}")
        write_text_atomic(md_path, "\n".join(lines) + "\n")

        return {
            "summary": {"num_hypotheses": len(hypotheses)},
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": [],
        }

    def stage_swe_bench_benchmark(self) -> Dict[str, Any]:
        if not self.args.dry_run and not has_api_credentials():
            raise RuntimeError("No API credential found for SWE-bench benchmark.")

        swe_root = self.artifacts_dir / "swe_bench"
        swe_root.mkdir(parents=True, exist_ok=True)
        log_file = self.logs_dir / "swe_bench_benchmark.log"

        cmd = [
            sys.executable,
            "scripts/run_swe_bench_batch.py",
            "--output_dir",
            str(swe_root),
            "--workspace",
            self.args.swe_workspace,
            "--limit",
            str(self.args.swe_limit),
            "--checkpoint_every",
            str(self.args.checkpoint_every),
            "--test_timeout",
            str(self.args.swe_test_timeout),
            "--setup_timeout",
            str(self.args.swe_setup_timeout),
            "--max_plan_steps",
            str(self.args.swe_max_plan_steps),
        ]
        if self.args.swe_instances_file:
            cmd += ["--instances_file", self.args.swe_instances_file]
        if self.args.swe_keep_workspace:
            cmd.append("--keep_workspace")
        if self.args.resume or (swe_root / "checkpoint.json").exists():
            cmd.append("--resume")

        result = self.run_command(cmd, log_file)
        if result["returncode"] != 0:
            raise RuntimeError(f"SWE-bench benchmark failed (rc={result['returncode']})")

        summary: Dict[str, Any]
        artifacts = [result["log_file"]]
        if self.args.dry_run:
            summary = {"planned": True}
        else:
            summary_file = swe_root / "summary.json"
            results_file = swe_root / "results.json"
            taxonomy_file = swe_root / "error_taxonomy.json"
            if not summary_file.exists():
                raise RuntimeError(f"Missing SWE summary file: {relpath(summary_file)}")
            if not results_file.exists():
                raise RuntimeError(f"Missing SWE results file: {relpath(results_file)}")
            summary = parse_swe_summary(summary_file)
            summary["results_file"] = relpath(results_file)
            if taxonomy_file.exists():
                summary["taxonomy_file"] = relpath(taxonomy_file)
            artifacts.extend([relpath(summary_file), relpath(results_file)])
            if taxonomy_file.exists():
                artifacts.append(relpath(taxonomy_file))

        report_json = self.reports_dir / "swe_bench_summary.json"
        report_md = self.reports_dir / "swe_bench_summary.md"
        write_json_atomic(report_json, {"timestamp": now_utc(), "summary": summary})

        lines = ["# SWE-bench Summary", ""]
        if summary.get("planned"):
            lines.append("- planned: true")
        else:
            lines.append(f"- run_id: `{summary.get('run_id')}`")
            lines.append(f"- total_instances: {summary.get('total_instances', 0)}")
            lines.append(f"- passed: {summary.get('passed', 0)}")
            lines.append(f"- failed: {summary.get('failed', 0)}")
            lines.append(f"- pass_rate: {summary.get('pass_rate', 0.0):.2%}")
            lines.append(f"- avg_duration_sec: {summary.get('avg_duration_sec', 0.0):.2f}")
            lines.append(f"- results_file: `{summary.get('results_file')}`")
            if summary.get("taxonomy_file"):
                lines.append(f"- taxonomy_file: `{summary.get('taxonomy_file')}`")
        write_text_atomic(report_md, "\n".join(lines) + "\n")

        return {
            "summary": summary,
            "artifacts": [relpath(report_json), relpath(report_md), *artifacts],
            "logs": [result["log_file"]],
        }

    def stage_swe_bench_error_taxonomy(self) -> Dict[str, Any]:
        swe_summary_path = self.reports_dir / "swe_bench_summary.json"
        if not swe_summary_path.exists():
            raise RuntimeError("Missing swe_bench_summary.json. Run swe_bench_benchmark first.")

        swe_summary = load_json(swe_summary_path).get("summary", {})
        taxonomy_counts = swe_summary.get("error_taxonomy", {})
        if not taxonomy_counts and not self.args.dry_run:
            taxonomy_file = swe_summary.get("taxonomy_file")
            if taxonomy_file and (PROJECT_ROOT / taxonomy_file).exists():
                taxonomy_counts = load_json(PROJECT_ROOT / taxonomy_file).get("error_taxonomy", {})

        report_json = self.reports_dir / "swe_bench_error_taxonomy.json"
        report_md = self.reports_dir / "swe_bench_error_taxonomy.md"
        payload = {
            "timestamp": now_utc(),
            "error_taxonomy": taxonomy_counts,
        }
        write_json_atomic(report_json, payload)

        lines = ["# SWE-bench Error Taxonomy", ""]
        if not taxonomy_counts:
            lines.append("- No SWE-bench errors recorded.")
        else:
            for category, count in sorted(taxonomy_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {category}: {count}")
        write_text_atomic(report_md, "\n".join(lines) + "\n")

        return {
            "summary": {"error_taxonomy": taxonomy_counts},
            "artifacts": [relpath(report_json), relpath(report_md)],
            "logs": [],
        }

    def stage_regression_gate(self) -> Dict[str, Any]:
        failures_path = self.reports_dir / "failure_cases.json"
        if not failures_path.exists():
            raise RuntimeError("Missing failure_cases.json. Run failure_mining first.")
        failures = load_json(failures_path).get("failures", [])

        grouped: Dict[str, List[str]] = defaultdict(list)
        for row in failures:
            domain = row.get("domain")
            instance_file = row.get("instance_file")
            if domain and instance_file and Path(instance_file).exists():
                grouped[domain].append(instance_file)

        regression_root = self.artifacts_dir / "regression"
        regression_root.mkdir(parents=True, exist_ok=True)
        logs: List[str] = []
        summary: Dict[str, Any] = {"domains": {}}

        if not grouped:
            cmd = [sys.executable, "scripts/run_evaluation.py", "--mode", "unit"]
            log_file = self.logs_dir / "regression_unit.log"
            result = self.run_command(cmd, log_file)
            logs.append(result["log_file"])
            if result["returncode"] != 0:
                raise RuntimeError("Regression gate fallback unit suite failed.")
            summary["fallback"] = "no_failed_instances_detected"
        else:
            if not self.args.dry_run and not has_api_credentials():
                raise RuntimeError("No API credential found for regression gate.")

            for domain, instances in grouped.items():
                unique_instances = sorted(set(instances))
                instances_file = regression_root / f"instances_{domain}.txt"
                write_text_atomic(instances_file, "\n".join(unique_instances) + "\n")

                domain_out = regression_root / domain
                domain_out.mkdir(parents=True, exist_ok=True)
                cmd = [
                    sys.executable,
                    "scripts/run_planbench_full.py",
                    "--domain",
                    domain,
                    "--instances",
                    str(instances_file),
                    "--output_dir",
                    str(domain_out),
                    "--parallel",
                    "--workers",
                    str(self.args.workers),
                    "--checkpoint_every",
                    str(self.args.checkpoint_every),
                ]
                log_file = self.logs_dir / f"regression_{domain}.log"
                result = self.run_command(cmd, log_file)
                logs.append(result["log_file"])
                if result["returncode"] != 0:
                    raise RuntimeError(f"Regression run failed for {domain} (rc={result['returncode']})")

                if self.args.dry_run:
                    summary["domains"][domain] = {
                        "planned": True,
                        "baseline_failed_instances": len(unique_instances),
                    }
                    continue

                result_file = find_latest_result_file(domain_out, domain)
                if not result_file:
                    raise RuntimeError(f"Missing regression result file for {domain}")
                parsed = parse_planbench_summary(result_file)
                resolved = len(unique_instances) - parsed["failed_count"]
                parsed["baseline_failed_instances"] = len(unique_instances)
                parsed["resolved_count"] = resolved
                summary["domains"][domain] = parsed

        json_path = self.reports_dir / "regression_gate.json"
        md_path = self.reports_dir / "regression_gate.md"
        write_json_atomic(json_path, {"timestamp": now_utc(), **summary})

        lines = ["# Regression Gate", ""]
        if "fallback" in summary:
            lines.append(f"- fallback: {summary['fallback']}")
        else:
            lines.append("| Domain | Baseline Failed | Regression Failed | Resolved |")
            lines.append("|---|---:|---:|---:|")
            for domain, s in summary["domains"].items():
                if s.get("planned"):
                    lines.append(
                        f"| {domain} | {s.get('baseline_failed_instances', 0)} | planned | planned |"
                    )
                else:
                    lines.append(
                        f"| {domain} | {s.get('baseline_failed_instances', 0)} | "
                        f"{s.get('failed_count', 0)} | {s.get('resolved_count', 0)} |"
                    )
        write_text_atomic(md_path, "\n".join(lines) + "\n")

        return {
            "summary": summary,
            "artifacts": [relpath(json_path), relpath(md_path)],
            "logs": logs,
        }

    def stage_final_report(self) -> Dict[str, Any]:
        stage_rows = []
        for stage in STAGE_ORDER:
            rec = self.state["stages"].get(stage, {})
            status = rec.get("status", "not_run")
            if stage == "final_report" and status == "running":
                # final_report is assembling this document right now; present it as completed.
                status = "completed"
            stage_rows.append(
                {
                    "stage": stage,
                    "owner": rec.get("owner", STAGE_OWNER.get(stage)),
                    "status": status,
                    "duration_sec": rec.get("duration_sec"),
                }
            )

        baseline_summary = {}
        ablation_summary = {}
        taxonomy_summary = {}
        swe_summary = {}
        swe_taxonomy_summary = {}
        regression_summary = {}

        baseline_json = self.reports_dir / "baseline_summary.json"
        if baseline_json.exists():
            baseline_summary = load_json(baseline_json)
        ablation_json = self.reports_dir / "ablation_summary.json"
        if ablation_json.exists():
            ablation_summary = load_json(ablation_json)
        taxonomy_json = self.reports_dir / "error_taxonomy.json"
        if taxonomy_json.exists():
            taxonomy_summary = load_json(taxonomy_json)
        swe_summary_json = self.reports_dir / "swe_bench_summary.json"
        if swe_summary_json.exists():
            swe_summary = load_json(swe_summary_json)
        swe_taxonomy_json = self.reports_dir / "swe_bench_error_taxonomy.json"
        if swe_taxonomy_json.exists():
            swe_taxonomy_summary = load_json(swe_taxonomy_json)
        regression_json = self.reports_dir / "regression_gate.json"
        if regression_json.exists():
            regression_summary = load_json(regression_json)

        report_payload = {
            "run_id": self.state.get("run_id"),
            "timestamp": now_utc(),
            "config": self.state.get("config", {}),
            "stages": stage_rows,
            "baseline_summary": baseline_summary,
            "ablation_summary": ablation_summary,
            "taxonomy_summary": taxonomy_summary,
            "swe_bench_summary": swe_summary,
            "swe_bench_taxonomy_summary": swe_taxonomy_summary,
            "regression_summary": regression_summary,
        }

        json_path = self.reports_dir / "final_report.json"
        summary_json_path = self.reports_dir / "final_summary.json"
        md_path = self.reports_dir / "final_report.md"
        write_json_atomic(json_path, report_payload)

        baseline_domains = baseline_summary.get("domains", {})
        baseline_compact = {
            domain: {
                "success_count": data.get("success_count", 0),
                "total_evaluated": data.get("total_evaluated", 0),
                "success_rate": data.get("success_rate", 0.0),
            }
            for domain, data in baseline_domains.items()
        }
        ablation_modes = ablation_summary.get("modes", {})
        ablation_compact = {
            mode: {
                "success_count": data.get("success_count", 0),
                "total": data.get("total", 0),
                "success_rate": data.get("success_rate", 0.0),
            }
            for mode, data in ablation_modes.items()
            if not data.get("planned")
        }
        final_summary_payload = {
            "run_id": self.state.get("run_id"),
            "timestamp": report_payload["timestamp"],
            "stage_status": {row["stage"]: row["status"] for row in stage_rows},
            "planbench_baseline": baseline_compact,
            "planbench_ablation": ablation_compact,
            "planbench_error_taxonomy": taxonomy_summary.get("global_counts", {}),
            "swe_bench": swe_summary.get("summary", {}),
            "swe_bench_error_taxonomy": swe_taxonomy_summary.get("error_taxonomy", {}),
            "regression": regression_summary,
        }
        write_json_atomic(summary_json_path, final_summary_payload)

        lines: List[str] = []
        lines.append("# Scientist Team Final Report")
        lines.append("")
        lines.append(f"- Run ID: `{self.state.get('run_id')}`")
        lines.append(f"- Generated At (UTC): `{report_payload['timestamp']}`")
        lines.append(f"- Project Root: `{PROJECT_ROOT}`")
        lines.append("")
        lines.append("## Scientist Agents")
        for agent in AGENTS:
            lines.append(f"- `{agent['id']}` ({agent['role']}): {agent['responsibility']}")
        lines.append("")
        lines.append("## Stage Status")
        lines.append("| Stage | Owner | Status | Duration(s) |")
        lines.append("|---|---|---|---:|")
        for row in stage_rows:
            duration = row["duration_sec"] if row["duration_sec"] is not None else "-"
            lines.append(f"| {row['stage']} | {row['owner']} | {row['status']} | {duration} |")
        lines.append("")

        domains = baseline_summary.get("domains", {})
        if domains:
            lines.append("## Baseline")
            lines.append("| Domain | Success/Total | Success Rate |")
            lines.append("|---|---:|---:|")
            for domain, s in domains.items():
                lines.append(
                    f"| {domain} | {s.get('success_count', 0)}/{s.get('total_evaluated', 0)} | "
                    f"{s.get('success_rate', 0.0):.2%} |"
                )
            lines.append("")

        modes = ablation_summary.get("modes", {})
        if modes:
            lines.append("## Ablation")
            lines.append("| Mode | Success/Total | Success Rate |")
            lines.append("|---|---:|---:|")
            for mode, s in modes.items():
                if s.get("planned"):
                    lines.append(f"| {mode} | planned | planned |")
                else:
                    lines.append(
                        f"| {mode} | {s.get('success_count', 0)}/{s.get('total', 0)} | "
                        f"{s.get('success_rate', 0.0):.2%} |"
                    )
            lines.append("")

        global_counts = taxonomy_summary.get("global_counts", {})
        if global_counts:
            lines.append("## Error Taxonomy (Top)")
            for category, count in sorted(global_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {category}: {count}")
            lines.append("")

        swe = swe_summary.get("summary", {})
        if swe:
            lines.append("## SWE-bench")
            if swe.get("planned"):
                lines.append("- status: planned")
            else:
                lines.append(
                    f"- pass: {swe.get('passed', 0)}/{swe.get('total_instances', 0)} "
                    f"({swe.get('pass_rate', 0.0):.2%})"
                )
                lines.append(f"- avg_duration_sec: {swe.get('avg_duration_sec', 0.0):.2f}")
                lines.append(f"- results_file: `{swe.get('results_file')}`")
            lines.append("")

        swe_error_counts = swe_taxonomy_summary.get("error_taxonomy", {})
        if swe_error_counts:
            lines.append("## SWE-bench Error Taxonomy")
            for category, count in sorted(swe_error_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {category}: {count}")
            lines.append("")

        if regression_summary:
            lines.append("## Regression Gate")
            if "fallback" in regression_summary:
                lines.append(f"- fallback: {regression_summary['fallback']}")
            else:
                for domain, s in regression_summary.get("domains", {}).items():
                    if s.get("planned"):
                        lines.append(f"- {domain}: planned")
                    else:
                        lines.append(
                            f"- {domain}: resolved {s.get('resolved_count', 0)} / "
                            f"{s.get('baseline_failed_instances', 0)} baseline failures"
                        )

        write_text_atomic(md_path, "\n".join(lines) + "\n")
        return {
            "summary": {
                "report_json": relpath(json_path),
                "summary_json": relpath(summary_json_path),
                "report_md": relpath(md_path),
            },
            "artifacts": [relpath(json_path), relpath(summary_json_path), relpath(md_path)],
            "logs": [],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Role-based scientist team orchestration for full experiment lifecycle."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="runs/scientist_team",
        help="Output directory for checkpoint, logs, artifacts, and reports.",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=DEFAULT_DOMAINS,
        help=f"PlanBench domains to evaluate (default: {' '.join(DEFAULT_DOMAINS)}).",
    )
    parser.add_argument(
        "--max_instances",
        type=int,
        default=None,
        help="Optional max instances per domain for baseline/regression runs.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=200,
        help="Parallel workers for benchmark commands (default: 200).",
    )
    parser.add_argument(
        "--checkpoint_every",
        type=int,
        default=1,
        help="Checkpoint interval passed to benchmark scripts (default: 1).",
    )
    parser.add_argument(
        "--swe_limit",
        type=int,
        default=DEFAULT_SWE_LIMIT,
        help=f"SWE-bench instance limit when no --swe_instances_file is provided (default: {DEFAULT_SWE_LIMIT}).",
    )
    parser.add_argument(
        "--swe_instances_file",
        type=str,
        default=None,
        help="Optional file containing SWE-bench instance IDs (one per line).",
    )
    parser.add_argument(
        "--swe_workspace",
        type=str,
        default="swe_bench_workspace",
        help="Workspace directory for SWE-bench repository checkouts.",
    )
    parser.add_argument(
        "--swe_test_timeout",
        type=int,
        default=600,
        help="SWE-bench test timeout per command in seconds (default: 600).",
    )
    parser.add_argument(
        "--swe_setup_timeout",
        type=int,
        default=900,
        help="SWE-bench repository setup timeout in seconds (default: 900).",
    )
    parser.add_argument(
        "--swe_max_plan_steps",
        type=int,
        default=40,
        help="Maximum executed plan steps per SWE-bench instance (default: 40).",
    )
    parser.add_argument(
        "--swe_keep_workspace",
        action="store_true",
        help="Keep SWE-bench instance workspace directories after each run.",
    )
    parser.add_argument(
        "--stages",
        type=str,
        default=None,
        help="Comma-separated subset of stages to run (default: all).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing checkpoint in output_dir.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rerun even if stage already completed in checkpoint.",
    )
    parser.add_argument(
        "--continue_on_error",
        action="store_true",
        help="Continue remaining stages after a stage failure.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Plan commands and write checkpoint/report skeleton without execution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner = ScientistTeamRunner(args)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
