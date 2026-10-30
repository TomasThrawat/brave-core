# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.
"""Rebase and lift a `cr<N>` branch with Claude Code, following
`tools/cr/autolift/SKILL.md`."""

from __future__ import annotations

from dataclasses import dataclass
import re

import post_process
from PB.recipes.brave.cr.autolift import InputProperties
from recipe_api import RecipeScriptApi
from recipe_modules import (
    brave_core_checkout,
    chromium_checkout,
    context,
    depot_tools,
    file,
    git,
    raw_io,
    step,
)
from recipe_test_api import RecipeTestApi

BRAVE_CORE_URL = 'https://github.com/brave/brave-core.git'

SKILL = 'tools/cr/autolift/SKILL.md'

_CR_BRANCH_RE = re.compile(r'refs/heads/cr(\d+)')

_PROMPT = """\
Lift cr{milestone} by following {skill} from step 1 to the end. Read the whole \
file before starting. The milestone N is {milestone}.

This is an unattended CI run: there is no human to ask, so make the calls the \
document describes and record them in the report."""


@dataclass
class DEPS(RecipeScriptApi):
    brave_core_checkout: brave_core_checkout.API
    context: context.API
    depot_tools: depot_tools.API
    file: file.API
    git: git.API
    raw_io: raw_io.API
    step: step.API


@dataclass
class TEST_DEPS(RecipeTestApi):
    brave_core_checkout: brave_core_checkout.TEST_API
    chromium_checkout: chromium_checkout.TEST_API
    raw_io: raw_io.TEST_API


PROPERTIES = InputProperties


def _latest_milestone(api: DEPS) -> int:
    """The milestone of the newest `cr<N>` branch on brave-core."""
    result = api.git(
        'ls-remote',
        '--heads',
        BRAVE_CORE_URL,
        'refs/heads/cr*',
        name='find latest cr branch',
        stdout=api.raw_io.output_text(),
    )
    milestones = []
    for line in result.stdout.splitlines():
        _, _, ref = line.partition('\t')
        if match := _CR_BRANCH_RE.fullmatch(ref):
            milestones.append(int(match[1]))
    if not milestones:
        raise RuntimeError(f'no cr<N> branch on {BRAVE_CORE_URL}')
    return max(milestones)


def RunSteps(api: DEPS, properties: InputProperties) -> None:
    milestone = properties.milestone or _latest_milestone(api)
    api.brave_core_checkout.set_brave_core_ref(f'refs/heads/cr{milestone}')
    root = api.brave_core_checkout.ensure_checkout()
    # The run's logs and report start empty, so that the agent only reads its
    # own run's. Those of earlier runs are kept with the job that ran them.
    run_dir = root / '.autolift' / f'cr{milestone}'
    api.file.rmtree('clear earlier run', run_dir)
    with (
        api.brave_core_checkout.brave_core_layout(),
        api.context(cwd=root),
    ):
        # The console gets a digest of Claude's stream, and the log all of it.
        api.step(
            'autolift',
            [
                api.depot_tools.vpython3(),
                api.resource('run_claude.py'),
                '--log',
                run_dir / 'claude.jsonl',
                '--',
                'claude',
                '--print',
                _PROMPT.format(milestone=milestone, skill=SKILL),
                '--permission-mode',
                'auto',
                '--output-format',
                'stream-json',
                '--verbose',
            ],
        )


def _autolift_cmd(milestone: int) -> list[str]:
    """The patterns `StepCommandRE` matches the `autolift` step against."""
    return [
        r'.*/vpython3',
        r'RECIPE\[cr/autolift\]\.resources/run_claude\.py',
        '--log',
        rf'.*/b/src/brave/\.autolift/cr{milestone}/claude\.jsonl',
        '--',
        'claude',
        '--print',
        rf'(?s)Lift cr{milestone} by following tools/cr/autolift/SKILL\.md.*',
        '--permission-mode',
        'auto',
        '--output-format',
        'stream-json',
        '--verbose',
    ]


def GenTests(api: TEST_DEPS):
    _ls_remote = '\n'.join(
        [
            'aaaa\trefs/heads/cr158',
            'bbbb\trefs/heads/cr159',
            'cccc\trefs/heads/cr159_fix',
            'dddd\trefs/heads/cr99',
        ]
    )

    # The newest cr<N> branch is found, checked out, and lifted.
    yield api.test(
        'latest',
        api.brave_core_checkout.with_git_cache(),
        api.brave_core_checkout.git_cache_populated(),
        api.chromium_checkout.existing_checkout(),
        api.step_data(
            'find latest cr branch',
            stdout=api.raw_io.output_text(_ls_remote),
        ),
        api.post_process(
            post_process.StepCommandRE, 'autolift', _autolift_cmd(159)
        ),
        api.post_process(post_process.StatusSuccess),
    )

    # An explicit milestone skips the lookup.
    yield api.test(
        'explicit milestone',
        api.brave_core_checkout.with_git_cache(),
        api.brave_core_checkout.git_cache_populated(),
        api.chromium_checkout.existing_checkout(),
        api.properties(milestone=158),
        api.post_process(post_process.DoesNotRun, 'find latest cr branch'),
        api.post_process(
            post_process.StepCommandContains,
            'brave-core checkout branch',
            ['checkout', '--force', '-B', 'cr158'],
        ),
        api.post_process(
            post_process.StepCommandRE, 'autolift', _autolift_cmd(158)
        ),
        api.post_process(post_process.StatusSuccess),
        api.post_process(post_process.DropExpectation),
    )

    # No cr<N> branch to lift.
    yield api.test(
        'no cr branch',
        api.brave_core_checkout.with_git_cache(),
        api.step_data(
            'find latest cr branch',
            stdout=api.raw_io.output_text('eeee\trefs/heads/master'),
        ),
        api.post_process(post_process.DoesNotRun, 'autolift'),
        api.post_process(post_process.StatusException),
        api.post_process(post_process.DropExpectation),
        status='EXCEPTION',
    )
