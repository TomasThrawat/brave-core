#!/usr/bin/env python3
# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for run_claude.py."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import run_claude


def _assistant(*content, parent=None):
    return {
        'type': 'assistant',
        'message': {'content': list(content)},
        'parent_tool_use_id': parent,
    }


def _tool_result(text, is_error=False):
    return {
        'type': 'user',
        'message': {
            'content': [
                {'type': 'tool_result', 'content': text, 'is_error': is_error}
            ]
        },
    }


class FormatEventTest(unittest.TestCase):
    def test_init(self):
        self.assertEqual(
            run_claude.format_event(
                {
                    'type': 'system',
                    'subtype': 'init',
                    'session_id': 's1',
                    'model': 'opus',
                }
            ),
            ['● Session s1 (opus)'],
        )

    def test_text_and_tool_use(self):
        event = _assistant(
            {'type': 'thinking', 'thinking': 'hidden'},
            {'type': 'text', 'text': 'Rebase finished.\nChecking.'},
            {
                'type': 'tool_use',
                'name': 'Bash',
                'input': {'command': 'git status', 'description': 'Status'},
            },
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/a'}},
            {'type': 'tool_use', 'name': 'TodoWrite', 'input': {}},
        )
        self.assertEqual(
            run_claude.format_event(event),
            [
                'Rebase finished.',
                'Checking.',
                '▶ Bash: Status',
                '▶ Read: /a',
                '▶ TodoWrite',
            ],
        )

    def test_subagent_is_indented(self):
        event = _assistant({'type': 'text', 'text': 'hi'}, parent='toolu_1')
        self.assertEqual(run_claude.format_event(event), ['    hi'])

    def test_tool_result_tail_collapses_progress(self):
        text = '\n'.join(
            ['1', '2', 'Rebasing (1/3)\rRebasing (3/3)', '', '4', '5', '6']
        )
        self.assertEqual(
            run_claude.format_event(_tool_result(text)),
            ['  │ 2', '  │ Rebasing (3/3)', '  │ 4', '  │ 5', '  │ 6'],
        )

    def test_tool_result_blocks_and_errors(self):
        event = _tool_result([{'type': 'text', 'text': 'boom'}], True)
        self.assertEqual(run_claude.format_event(event), ['  ✘ boom'])

    def test_long_lines_are_shortened(self):
        [line] = run_claude.format_event(_tool_result('x' * 500))
        self.assertEqual(len(line), len('  │ ') + run_claude.LINE_WIDTH)
        self.assertTrue(line.endswith('…'))

    def test_result(self):
        event = {
            'type': 'result',
            'subtype': 'success',
            'duration_ms': 3_725_000,
            'num_turns': 12,
            'total_cost_usd': 1.5,
            'result': 'Lift done.',
        }
        self.assertEqual(
            run_claude.format_event(event),
            ['■ success, after 1h02m, 12 turns, $1.50'],
        )

    def test_other_events_print_nothing(self):
        self.assertEqual(
            run_claude.format_event(
                {'type': 'system', 'subtype': 'thinking_tokens'}
            ),
            [],
        )


class RunTest(unittest.TestCase):
    def _run(self, lines, exit_code=0):
        script = (
            'import sys\n'
            f'sys.stdout.write({"".join(lines)!r})\n'
            f'sys.exit({exit_code})\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'cr159' / 'claude.jsonl'
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_claude.run([sys.executable, '-c', script], log)
            return code, stdout.getvalue(), log.read_text(encoding='utf-8')

    def test_logs_raw_stream_and_prints_digest(self):
        lines = [
            'a warning\n',
            json.dumps(_assistant({'type': 'text', 'text': 'Hello'})) + '\n',
            json.dumps({'type': 'result', 'subtype': 'success'}) + '\n',
        ]
        code, stdout, log = self._run(lines)
        self.assertEqual(code, 0)
        self.assertEqual(log, ''.join(lines))
        self.assertEqual(
            stdout.splitlines(),
            ['a warning', 'Hello', '■ success'],
        )

    def test_error_result_fails(self):
        lines = [
            json.dumps({'type': 'result', 'subtype': 'error', 'is_error': True})
            + '\n'
        ]
        code, _, _ = self._run(lines)
        self.assertEqual(code, 1)

    def test_claude_exit_code_is_kept(self):
        code, _, _ = self._run([], exit_code=3)
        self.assertEqual(code, 3)


if __name__ == '__main__':
    unittest.main()
