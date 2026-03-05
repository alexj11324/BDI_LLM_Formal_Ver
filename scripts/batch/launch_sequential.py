#!/usr/bin/env python3
"""
Sequential Background Launcher
================================
Runs all three domains ONE AT A TIME with 1 worker each.
Avoids API rate limits from concurrent requests.

Usage:
    python scripts/launch_sequential.py
    python scripts/launch_sequential.py --status
"""

import subprocess
import sys
import os
import json
import time
import signal
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
CHECKPOINT_DIR = PROJECT_ROOT / "runs" / "verification_results"
PID_FILE = LOG_DIR / "sequential_pid.json"


DOMAINS = ["depots", "blocksworld", "logistics"]  # Order: fastest first
TOTALS = {"blocksworld": 1103, "logistics": 572, "depots": 501}


def run_all():
    """Run all domains sequentially in this process."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save our PID
    with open(PID_FILE, "w") as f:
        json.dump({"pid": os.getpid(), "start": datetime.now().isoformat()}, f)
    
    script = str(PROJECT_ROOT / "scripts" / "run_verification_only.py")
    
    for domain in DOMAINS:
        log_file = LOG_DIR / f"verify_{domain}.log"
        print(f"\n{'='*50}")
        print(f"  Starting {domain} (1 worker)")
        print(f"  Log: {log_file}")
        print(f"{'='*50}\n")
        
        with open(log_file, "w") as log:
            proc = subprocess.run(
                [sys.executable, "-u", script,
                 "--domain", domain, "--workers", "1"],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )
        
        # Check checkpoint
        cp = CHECKPOINT_DIR / f"checkpoint_verifyonly_{domain}.json"
        if cp.exists():
            data = json.load(open(cp))
            n = len(data.get("results", []))
            print(f"  ✓ {domain}: {n}/{TOTALS[domain]} completed")
        else:
            print(f"  ✗ {domain}: no checkpoint")
    
    print(f"\n{'='*50}")
    print(f"  ALL DOMAINS COMPLETE")
    print(f"{'='*50}")
    show_status()


def show_status():
    """Show progress for all domains."""
    print(f"\n{'='*50}")
    print(f"  STATUS @ {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}\n")
    
    for domain in DOMAINS:
        cp = CHECKPOINT_DIR / f"checkpoint_verifyonly_{domain}.json"
        total = TOTALS[domain]
        if cp.exists():
            data = json.load(open(cp))
            results = data.get("results", [])
            n = len(results)
            v = sum(1 for r in results if r.get("symbolic", {}).get("valid", False))
            s = sum(1 for r in results if r.get("structural", {}).get("valid", False))
            agree = sum(1 for r in results if r.get("agreement", False))
            pct = n / total * 100
            print(f"  {domain:15s} {n:4d}/{total} ({pct:5.1f}%)")
            print(f"    VAL valid: {v}/{n}  Struct valid: {s}/{n}  Agreement: {agree}/{n}")
        else:
            print(f"  {domain:15s}    0/{total} (  0.0%)")
        print()
    
    # Check if running
    if PID_FILE.exists():
        data = json.load(open(PID_FILE))
        pid = data.get("pid")
        try:
            os.kill(pid, 0)
            print(f"  Process running: PID {pid}")
        except (ProcessLookupError, OSError):
            print(f"  Process not running")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.stop:
        if PID_FILE.exists():
            data = json.load(open(PID_FILE))
            try:
                os.kill(data["pid"], signal.SIGTERM)
                print(f"Stopped PID {data['pid']}")
            except OSError:
                print("Already stopped")
    else:
        run_all()
