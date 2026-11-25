#!/usr/bin/env python3
"""Run each incident twice on an existing dedicated lab cluster.

This is an integration command for the maintainer to run deliberately; it was
not run while authoring this repository. It mutates only the dedicated lab,
checks order and log-history persistence across repeated up/reset, and performs
a baseline replay between learner-repair and reset checks.
"""
import os, signal, subprocess, sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
IDS = [f"{i:02d}" for i in range(1, 13)]

def run(*args, expected=0):
    p = subprocess.Popen(args, cwd=ROOT, start_new_session=True)
    try:
        returncode = p.wait(timeout=900)
    except subprocess.TimeoutExpired as e:
        try: os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait()
        raise SystemExit(f"timed out after 900 seconds: {' '.join(args)}; inspect make lab-status and recover with make lab-reset") from e
    if returncode != expected:
        raise SystemExit(f"unexpected exit {returncode} from {' '.join(args)}; expected {expected}")

def repair(lab):
    run(sys.executable, "scripts/lab.py", "suite-repair", lab)

def create_order(sku):
    request_id = str(uuid4())
    run(sys.executable, "scripts/lab.py", "suite-order-create", sku, request_id)
    return request_id

def require_recent_order(sku):
    run(sys.executable, "scripts/lab.py", "suite-order-check", sku)

def main():
    if not (ROOT / ".lab/kubeconfig").is_file(): raise SystemExit("dedicated lab missing; run make up first")
    run("make", "doctor")
    # Exercise repeat-up persistence with a uniquely named synthetic order.
    run("make", "up")
    run("make", "doctor")
    up_sentinel = f"SUITE-UP-{uuid4().hex[:8]}"
    history_request_id = create_order(up_sentinel)
    run("make", "up")
    require_recent_order(up_sentinel)
    for attempt in (1, 2):
        for lab in IDS:
            print(f"Trial {attempt}/2 · lab {lab}", flush=True)
            run("make", "lab-start", f"LAB={lab}")
            # Verify must fail while the known fault remains unrepaired.
            run("make", "lab-verify", f"LAB={lab}", expected=1)
            repair(lab)
            run("make", "lab-verify", f"LAB={lab}")
            reset_sentinel = f"SUITE-{attempt}-{lab}-{uuid4().hex[:6]}"
            create_order(reset_sentinel)
            run("make", "lab-reset")
            require_recent_order(reset_sentinel)
            run("make", "doctor")
    run(sys.executable, "scripts/lab.py", "suite-check-log", history_request_id)
    print("All 24 scenario trials passed.")

if __name__ == "__main__": main()
