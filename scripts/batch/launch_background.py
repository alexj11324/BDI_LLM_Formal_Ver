#!/usr/bin/env python3
"""
Background Launcher for Verification Evaluation
=================================================

Solves the 'suspended (tty output)' problem by spawning evaluation
processes in a NEW SESSION (os.setsid) with no controlling terminal.

Usage:
    # Launch all three domains
    python scripts/launch_background.py

    # Launch specific domain(s)
    python scripts/launch_background.py --domains blocksworld logistics

    # Custom workers
    python scripts/launch_background.py --workers 10

    # Check progress
    python scripts/launch_background.py --status
"""

import subprocess
import sys
import os
import json
import time
import argparse
import signal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
CHECKPOINT_DIR = PROJECT_ROOT / "runs" / "verification_results"
PID_FILE = PROJECT_ROOT / "logs" / "eval_pids.json"

DOMAINS = {
    "blocksworld": 1103,
    "logistics": 572,
    "depots": 501,
}


def launch_domain(domain: str, workers: int) -> int:
    """Launch evaluation for a domain in a fully detached process."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"verify_{domain}.log"

    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            [
                sys.executable, "-u",
                str(PROJECT_ROOT / "scripts" / "run_verification_only.py"),
                "--domain", domain,
                "--workers", str(workers),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # KEY: creates new session, no controlling tty
            cwd=str(PROJECT_ROOT),
        )
    return proc.pid


def launch_all(domains: list, workers: int):
    """Launch evaluations for all specified domains."""
    pids = {}
    for domain in domains:
        pid = launch_domain(domain, workers)
        pids[domain] = pid
        print(f"  ✓ {domain}: PID {pid} (log: logs/verify_{domain}.log)")

    # Save PIDs for status checking
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w") as f:
        json.dump({"pids": pids, "workers": workers, "start_time": time.time()}, f)

    print(f"\nAll {len(domains)} domains launched. PIDs saved to {PID_FILE}")
    print(f"\nMonitor progress:")
    print(f"  python scripts/launch_background.py --status")
    print(f"  tail -f logs/verify_blocksworld.log")


def check_status():
    """Check evaluation progress across all domains."""
    print(f"\n{'='*60}")
    print(f"  VERIFICATION EVALUATION STATUS")
    print(f"{'='*60}\n")

    # Check running processes
    pids = {}
    if PID_FILE.exists():
        data = json.load(open(PID_FILE))
        pids = data.get("pids", {})
        start_time = data.get("start_time", 0)
        elapsed = time.time() - start_time if start_time else 0
        print(f"  Elapsed: {elapsed/60:.0f} min\n")

    for domain, total in DOMAINS.items():
        # Check checkpoint
        cp_file = CHECKPOINT_DIR / f"checkpoint_verifyonly_{domain}.json"
        done = 0
        val_valid = 0
        if cp_file.exists():
            cp_data = json.load(open(cp_file))
            results = cp_data.get("results", [])
            done = len(results)
            val_valid = sum(
                1 for r in results
                if r.get("symbolic", {}).get("valid", False)
            )

        # Check if process still running
        pid = pids.get(domain)
        running = False
        if pid:
            try:
                os.kill(pid, 0)  # Signal 0 = check existence
                running = True
            except ProcessLookupError:
                pass
            except OSError:
                pass

        status = "🟢 Running" if running else ("✅ Done" if done >= total else "⏹️ Stopped")
        pct = done / total * 100 if total else 0
        accuracy = val_valid / done * 100 if done else 0

        print(f"  {domain:15s} {status}")
        print(f"    Progress: {done}/{total} ({pct:.1f}%)")
        if done > 0:
            print(f"    VAL valid: {val_valid}/{done} ({accuracy:.1f}%)")
        if pid:
            print(f"    PID: {pid}")
        print()


def stop_all():
    """Stop all running evaluations."""
    if not PID_FILE.exists():
        print("No PID file found.")
        return

    data = json.load(open(PID_FILE))
    for domain, pid in data.get("pids", {}).items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Stopped {domain} (PID {pid})")
        except OSError:
            print(f"  {domain} (PID {pid}) already stopped")


def main():
    parser = argparse.ArgumentParser(description="Background evaluation launcher")
    parser.add_argument("--domains", nargs="+",
                        choices=list(DOMAINS.keys()),
                        default=list(DOMAINS.keys()),
                        help="Domains to evaluate")
    parser.add_argument("--workers", type=int, default=5,
                        help="Parallel workers per domain")
    parser.add_argument("--status", action="store_true",
                        help="Check evaluation progress")
    parser.add_argument("--stop", action="store_true",
                        help="Stop all running evaluations")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.stop:
        stop_all()
    else:
        print(f"\n  Launching verification evaluation")
        print(f"  Workers per domain: {args.workers}")
        print(f"  Domains: {', '.join(args.domains)}\n")
        launch_all(args.domains, args.workers)


if __name__ == "__main__":
    main()
