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
                '  $ git status',
                '▶ Read: /a',
                '▶ TodoWrite',
            ],
        )

    def test_command_without_description_is_shown_once(self):
        event = _assistant(
            {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}}
        )
        self.assertEqual(run_claude.format_event(event), ['▶ Bash: ls'])

    def test_log_sources_are_stripped(self):
        text = '[12:02:25] * Changes for this bump        terminal.py:358   '
        self.assertEqual(
            run_claude.format_event(_tool_result(text)),
            ['  │ [12:02:25] * Changes for this bump'],
        )

    def test_task_notification(self):
        event = {
            'type': 'system',
            'subtype': 'task_notification',
            'task_id': 'b1',
            'status': 'completed',
            'summary': 'Background command "Build" completed (exit code 0)',
        }
        self.assertEqual(
            run_claude.format_event(event),
            ['  ⏹ Background command "Build" completed (exit code 0)'],
        )

    def test_subagent_is_indented(self):
        event = _assistant({'type': 'text', 'text': 'hi'}, parent='toolu_1')
        self.assertEqual(run_claude.format_event(event), ['    hi'])

    def test_tool_result_tail_collapses_progress(self):
        lines = [str(i) for i in range(run_claude.TAIL_LINES)]
        text = '\n'.join(['Rebasing (1/3)\rRebasing (3/3)', '', *lines])
        # The progress line is the one too many.
        self.assertEqual(
            run_claude.format_event(_tool_result(text)),
            [f'  │ {line}' for line in lines],
        )
        self.assertEqual(
            run_claude.format_event(_tool_result('a\rb\nc')),
            ['  │ b', '  │ c'],
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


def _started_in_background(task_id, path):
    return _tool_result(
        f'Command running in background with ID: {task_id}. Output is being '
        f'written to: {path}. You will be notified when it completes.'
    )


def _notification(task_id):
    return {
        'type': 'system',
        'subtype': 'task_notification',
        'task_id': task_id,
        'summary': f'{task_id} completed',
    }


class BackgroundTest(unittest.TestCase):
    def setUp(self):
        self._poll_interval = run_claude.POLL_INTERVAL
        run_claude.POLL_INTERVAL = 0.01
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / 'b1.output'

    def tearDown(self):
        run_claude.POLL_INTERVAL = self._poll_interval
        self._tmp.cleanup()

    def test_background_commands(self):
        self.assertEqual(
            run_claude.background_commands(
                _started_in_background('b1', '/tmp/tasks/b1.output')
            ),
            [('b1', Path('/tmp/tasks/b1.output'))],
        )
        self.assertEqual(
            run_claude.background_commands(_tool_result('done')), []
        )

    def test_output_is_followed_until_notified(self):
        printed = []
        digest = run_claude.Digest(printed.append)
        digest.handle_line(
            json.dumps(_started_in_background('b1', self.output))
        )
        # Written after the command started, the last line unterminated.
        self.output.write_text(
            '[1/2] CXX a.o\n'
            'step 1\rstep 2\n'
            'error: boom        terminal.py:12\n'
            'FAILED',
            encoding='utf-8',
        )
        digest.handle_line(json.dumps(_notification('b1')))
        digest.close()
        self.assertEqual(
            printed[1:],
            [
                '  ┆ [1/2] CXX a.o',
                '  ┆ step 2',
                '  ┆ error: boom',
                '  ┆ FAILED',
                '  ⏹ b1 completed',
            ],
        )

    def test_followers_stop_when_the_run_ends(self):
        printed = []
        digest = run_claude.Digest(printed.append)
        digest.handle_line(
            json.dumps(_started_in_background('b1', self.output))
        )
        self.output.write_text('still building\n', encoding='utf-8')
        digest.close()
        self.assertEqual(printed[-1], '  ┆ still building')

    def test_missing_output_file_prints_nothing(self):
        printed = []
        digest = run_claude.Digest(printed.append)
        digest.handle_line(
            json.dumps(_started_in_background('b1', self.output))
        )
        digest.handle_line(json.dumps(_notification('b1')))
        self.assertEqual(printed[1:], ['  ⏹ b1 completed'])


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
