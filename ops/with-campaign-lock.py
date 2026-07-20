#!/usr/bin/env python3
"""Hold the campaign fcntl lock while running a legacy operational command."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "benchy-state" / "campaign.lock"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command or args.command[0] != "--" or len(args.command) == 1:
        parser.error("command required after --")
    command = args.command[1:]
    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_file.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(args.lock_file.read_text(encoding="utf-8"), file=sys.stderr)
            return 1
        handle.seek(0); handle.truncate()
        json.dump({"campaign_id": "nightly-scout", "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(), "command": command}, handle)
        handle.flush(); os.fsync(handle.fileno())
        env = os.environ | {"CAMPAIGN_LOCK_HELD": "1"}
        return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
