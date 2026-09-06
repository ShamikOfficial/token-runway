#!/usr/bin/env python3
"""Full portfolio walkthrough — Stages 1–5 against a running stack."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "demo_stage1.py",
    "demo_stage2.py",
    "demo_stage3.py",
    "demo_stage4.py",
    "demo_stage5.py",
    "verify_floci.py",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stages 1–5 demos end-to-end.")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()
    base = args.base
    for name in SCRIPTS:
        path = ROOT / "scripts" / name
        print("\n====", name, "====")
        cmd = [sys.executable, str(path)]
        if name.startswith("demo_"):
            cmd.extend(["--base", base])
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print("FAILED", name, file=sys.stderr)
            return proc.returncode
    print("\nAll demos green. Dashboard:", base + "/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
