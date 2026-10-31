#!/usr/bin/env python3
"""Run one bounded Brave build slice while preserving incremental Ninja state."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys


def signal_process_group(process: subprocess.Popen, signal_number: int) -> None:
    """Send a signal to the complete build process group if it still exists."""
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a build command is required")
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")

    print(
        f"BUILD_SLICE_STARTED: timeout={args.timeout_seconds}s command={command[0]}",
        flush=True,
    )
    process = subprocess.Popen(command, start_new_session=True)

    try:
        exit_code = process.wait(timeout=args.timeout_seconds)
        print(f"BUILD_COMMAND_FINISHED: exit_code={exit_code}", flush=True)
        return exit_code
    except subprocess.TimeoutExpired:
        print(
            "BUILD_SLICE_CHECKPOINT_REACHED: sending SIGINT to stop this slice "
            "and retain Ninja outputs for the next job",
            flush=True,
        )

    signal_process_group(process, signal.SIGINT)
    try:
        exit_code = process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        print("BUILD_SLICE_GRACE_PERIOD_EXPIRED: sending SIGTERM", flush=True)
        signal_process_group(process, signal.SIGTERM)
        try:
            exit_code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            print("BUILD_SLICE_FORCE_STOP: sending SIGKILL", flush=True)
            signal_process_group(process, signal.SIGKILL)
            exit_code = process.wait()

    print(
        f"BUILD_SLICE_CHECKPOINT_STOPPED: child_exit_code={exit_code}; "
        "the job continues so it can save incremental Ninja state",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
