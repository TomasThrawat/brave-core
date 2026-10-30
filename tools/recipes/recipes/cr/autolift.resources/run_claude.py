#!/usr/bin/env python3
# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.
"""Run `claude --output-format stream-json` and print a readable digest of it.

The raw stream is kept in full in the `--log` file; the console gets Claude's
messages, one line per tool call, a short tail of each tool's output, and the
final result:

    run_claude.py --log .autolift/cr159/claude.jsonl -- claude --print ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

# How many lines of a tool's output, and how many characters of a line, are
# printed.
TAIL_LINES = 5
LINE_WIDTH = 160

# The tool inputs that best summarise a call, by order of preference.
_SUMMARY_KEYS = (
    'description',
    'file_path',
    'pattern',
    'command',
    'url',
    'query',
    'prompt',
)


def _shorten(text: str, width: int = LINE_WIDTH) -> str:
    text = text.strip()
    return text if len(text) <= width else text[: width - 1] + '…'


def _tool_summary(name: str, tool_input: dict[str, Any]) -> str:
    """One line for a tool call: its name and its most telling input."""
    for key in _SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return _shorten(f'▶ {name}: {value.splitlines()[0]}')
    return f'▶ {name}'


def _result_text(content: Any) -> str:
    """The text of a tool result, which is a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(
            block.get('text', '')
            for block in content
            if isinstance(block, dict) and block.get('type') == 'text'
        )
    return ''


def _tail(text: str) -> list[str]:
    """The last non-empty lines of *text*, as a terminal would show them.

    Progress output rewrites its line with `\\r`, so only what follows the
    last `\\r` of a line is kept.
    """
    # Not `splitlines()`, which also splits on `\r`.
    lines = [line.rsplit('\r', 1)[-1].rstrip() for line in text.split('\n')]
    return [_shorten(line) for line in lines if line.strip()][-TAIL_LINES:]


def _duration(milliseconds: int) -> str:
    minutes, seconds = divmod(round(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h{minutes:02d}m' if hours else f'{minutes}m{seconds:02d}s'


def format_event(event: dict[str, Any]) -> list[str]:
    """The console lines for one event of the stream; none for most."""
    kind = event.get('type')
    message = event.get('message') or {}
    # Events of subagents name the tool call that started them.
    indent = '    ' if event.get('parent_tool_use_id') else ''
    lines: list[str] = []

    if kind == 'system' and event.get('subtype') == 'init':
        lines.append(
            f'● Session {event.get("session_id")} ({event.get("model")})'
        )
    elif kind == 'assistant':
        for block in message.get('content') or []:
            if block.get('type') == 'text' and block.get('text', '').strip():
                lines += block['text'].strip().splitlines()
            elif block.get('type') == 'tool_use':
                lines.append(
                    _tool_summary(
                        block.get('name', '?'), block.get('input') or {}
                    )
                )
    elif kind == 'user':
        for block in message.get('content') or []:
            if not isinstance(block, dict):
                continue
            if block.get('type') != 'tool_result':
                continue
            marker = '✘' if block.get('is_error') else '│'
            lines += [
                f'  {marker} {line}'
                for line in _tail(_result_text(block.get('content')))
            ]
    elif kind == 'result':
        parts = [f'■ {event.get("subtype")}']
        if event.get('duration_ms'):
            parts.append(f'after {_duration(event["duration_ms"])}')
        if event.get('num_turns'):
            parts.append(f'{event["num_turns"]} turns')
        if isinstance(event.get('total_cost_usd'), (int, float)):
            parts.append(f'${event["total_cost_usd"]:.2f}')
        # Not `result`, which repeats Claude's last message.
        lines.append(', '.join(parts))

    return [f'{indent}{line}' for line in lines]


def parse_line(line: str) -> dict[str, Any] | None:
    """The event on one line of the stream, or None for any other line."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def run(cmd: list[str], log: Path) -> int:
    """Runs *cmd*, logging its stream to *log* and printing the digest.

    Returns the exit code: Claude's own, or 1 if it reported an error result
    while exiting 0.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with (
        log.open('w', encoding='utf-8') as log_file,
        subprocess.Popen(
            cmd, stdout=subprocess.PIPE, text=True, encoding='utf-8'
        ) as process,
    ):
        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            event = parse_line(line)
            if event is None:
                # Not an event, e.g. a warning printed before the stream.
                output = [line.rstrip()] if line.strip() else []
            else:
                output = format_event(event)
                if event.get('type') == 'result' and event.get('is_error'):
                    failed = True
            for text in output:
                print(text, flush=True)
    return process.returncode or int(failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--log', type=Path, required=True, help='Where to keep the raw stream.'
    )
    parser.add_argument('cmd', nargs='+', help='The claude command, after --.')
    args = parser.parse_args(argv)
    return run(args.cmd, args.log)


if __name__ == '__main__':
    sys.exit(main())
