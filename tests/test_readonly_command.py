"""STOP inspection and dispatch regression controls; supplied commands never run."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / 'hooks'


def load_policy():
    spec = importlib.util.spec_from_file_location('readonly_policy', HOOKS / 'readonly-command.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CommandPolicyTests(unittest.TestCase):
    def test_known_reads(self):
        policy = load_policy()
        for command in READS:
            with self.subTest(command=command):
                self.assertTrue(policy.allowed(command))

    def test_writes_and_executable_options(self):
        policy = load_policy()
        for command in WRITES:
            with self.subTest(command=command):
                self.assertFalse(policy.allowed(command))

    def test_malformed_commands_fail_closed(self):
        policy = load_policy()
        for command in [None, [], {}, 1, '', ' ', 'cat "unterminated']:
            with self.subTest(command=command):
                self.assertFalse(policy.allowed(command))


class StopHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.sliceworks').mkdir()
        self.config = self.root / '.sliceworks/config.env'
        self.config.write_text('SW_STATE_DIR=state\n')
        (self.root / 'state').mkdir()
        self.stop = self.root / 'state/STOP'
        self.stop.write_text('owner pause; retain this marker\n')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('SW_')}
        self.env['CLAUDE_PROJECT_DIR'] = str(self.root)
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'

    def call(self, hook, payload, deny, hooks=HOOKS):
        marker = self.stop.read_bytes() if self.stop.exists() else None
        result = subprocess.run(['sh', str(hooks / (hook + '.sh'))],
                                input=json.dumps(payload), text=True, capture_output=True,
                                cwd=self.root, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout) if result.stdout else {}
        decision = output.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision == 'deny', deny, result.stdout + result.stderr)
        if marker is not None:
            self.assertEqual(self.stop.read_bytes(), marker)
        return output

    def test_shell_reads_on_both_runtimes(self):
        cases = [
            {'tool_name': 'Bash', 'tool_input': {'command': 'cat README.md'}},
            {'tool_name': 'exec_command', 'tool_input': {'cmd': 'git remote -v'}},
            {'tool_name': 'local_shell', 'tool_input': {'command': ['bash', '-lc', 'pwd']}},
            {'tool_name': 'shell', 'tool_input': {'command': ['cat', 'README.md']}},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.call('kill-switch', payload, False)

    def test_foreign_shell_wrapper_is_not_unwrapped(self):
        self.call('kill-switch', {'tool_name': 'shell', 'tool_input': {'command': ['/tmp/sh', '-c', 'pwd']}}, True)

    def test_writes_edits_and_dispatch_remain_denied(self):
        for command in WRITES:
            with self.subTest(command=command):
                self.call('kill-switch', {'tool_name': 'exec_command', 'tool_input': {'cmd': command}}, True)
        for tool in ['Edit', 'Write', 'MultiEdit', 'apply_patch', 'Agent', 'Task',
                     'spawn_agent', 'followup_task', 'SendMessage', 'send_message',
                     'mcp__codex__send_message_to_thread', 'mcp__codex__create_thread',
                     'mcp__codex__handoff_thread']:
            with self.subTest(tool=tool):
                self.call('kill-switch', {'tool_name': tool, 'tool_input': {'subagent_type': 'Explore'}}, True)

    def test_stop_precedes_budget_and_explorer_exemptions(self):
        for tool, details in [('Agent', {'subagent_type': 'Explore'}),
                              ('Agent', {'subagent_type': 'general-purpose'}),
                              ('SendMessage', {}), ('mcp__codex__send_message_to_thread', {})]:
            with self.subTest(tool=tool, details=details):
                self.call('budget-guard', {'tool_name': tool, 'tool_input': details}, True)
        self.stop.unlink()
        self.call('budget-guard', {'tool_name': 'Agent', 'tool_input': {'subagent_type': 'Explore'}}, False)
        self.call('budget-guard', {'tool_name': 'Agent', 'tool_input': {'subagent_type': 'general-purpose'}}, True)

    def test_unstopped_unadopted_and_disabled_are_inert(self):
        payload = {'tool_name': 'Write', 'tool_input': {'file_path': 'product'}}
        self.stop.unlink()
        self.call('kill-switch', payload, False)
        self.stop.touch()
        self.config.write_text('SW_STATE_DIR=state\nSW_PLUGIN_HOOKS=off\n')
        self.call('kill-switch', payload, False)
        self.call('budget-guard', {'tool_name': 'Agent'}, False)
        self.config.unlink()
        self.call('kill-switch', payload, False)

    def test_missing_classifier_refuses_reads(self):
        hooks = self.root / 'installed-hooks'
        shutil.copytree(HOOKS, hooks)
        (hooks / 'readonly-command.py').unlink(missing_ok=True)
        self.call('kill-switch', {'tool_name': 'Bash', 'tool_input': {'command': 'pwd'}}, True, hooks)

    def test_broken_classifier_refuses_reads(self):
        hooks = self.root / 'installed-hooks'
        shutil.copytree(HOOKS, hooks)
        (hooks / 'readonly-command.py').write_text('raise RuntimeError("broken")\n')
        self.call('kill-switch', {'tool_name': 'Bash', 'tool_input': {'command': 'pwd'}}, True, hooks)

    def test_malformed_payloads_refuse(self):
        for payload in [{}, [], {'tool_name': 'Bash'}, {'tool_name': 'Bash', 'tool_input': []},
                        {'tool_name': 'Bash', 'tool_input': {'command': 1}}]:
            with self.subTest(payload=payload):
                self.call('kill-switch', payload, True)

    def test_classification_never_executes_the_supplied_command(self):
        marker = self.root / 'unexpected-write'
        self.call('kill-switch', {'tool_name': 'Bash', 'tool_input': {'command': 'pwd > ' + str(marker)}}, True)
        self.assertFalse(marker.exists())

    def test_matcher_covers_dispatch_and_mutation_tools(self):
        entries = json.loads((HOOKS / 'hooks.json').read_text())['hooks']['PreToolUse']
        matcher = entries[0]['matcher']
        for tool in ['Agent', 'Task', 'Bash', 'Edit', 'Write', 'MultiEdit', 'SendMessage',
                     'spawn_agent', 'followup_task', 'mcp__codex__send_message_to_thread',
                     'mcp__codex__create_thread', 'mcp__codex__handoff_thread']:
            with self.subTest(tool=tool):
                self.assertIsNotNone(re.fullmatch(matcher, tool))

    def test_copy_install_keeps_bundled_policy_and_stop(self):
        result = subprocess.run(['sh', str(ROOT / 'scripts/install.sh'), str(self.root),
                                 '--tools', 'codex', '--hooks'],
                                text=True, capture_output=True, env=self.env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / '.codex/hooks.json').read_text())
        self.assertIn(str(HOOKS / 'kill-switch.sh'), config['hooks']['PreToolUse'][0]['hooks'][0]['command'])
        self.call('kill-switch', {'tool_name': 'exec_command', 'tool_input': {'cmd': 'pwd'}}, False)
        self.call('kill-switch', {'tool_name': 'Write'}, True)
        self.call('budget-guard', {'tool_name': 'SendMessage'}, True)


READS = ['pwd',
 'cat /tmp/a',
 'head -n 20 /tmp/a',
 'tail -n 5 /tmp/a',
 'ls -la',
 'wc -l /tmp/a',
 "sed -n '10,20p' /tmp/a",
 'rg --no-config --files docs',
 'rg --no-config -n -F "STOP kill switch" hooks',
 'git remote -v',
 'git -C /repo --no-pager -c log.showSignature=false log -n 3 --oneline',
 'git --no-optional-locks -c core.fsmonitor= --no-pager diff --no-ext-diff --no-textconv '
 '--stat',
 'git --no-optional-locks -c core.fsmonitor= --no-pager status --short',
 'gh pr view 13 --repo owner/project --json title,body',
 'gh pr diff 13 --repo owner/project --patch',
 'git --no-optional-locks -c core.fsmonitor= ls-files --cached',
 'rg --no-config -- --pre=literal',
 'git --no-pager -c log.showSignature=false log --max-count=2 --oneline']

WRITES = ['touch /tmp/a',
 'rm /tmp/a',
 'cat a > b',
 'cat a >> b',
 'pwd; touch b',
 'pwd && touch b',
 'cat $(touch b)',
 'cat `touch b`',
 'cat a | sh',
 'bash -c pwd',
 'python3 -c "print(1)"',
 'env cat a',
 'git fetch',
 'git push',
 'git commit -m x',
 'git config a b',
 'git remote add x y',
 'git --no-pager diff --no-ext-diff --no-textconv --output=/tmp/a',
 'git --no-pager diff --ext-diff',
 'git --no-pager log -p',
 'git status',
 'rg --pre touch x',
 'rg --no-config --pre touch x',
 'rg --no-config --hostname-bin touch x',
 'sed -i s/a/b/ a',
 "sed -n '1w /tmp/a' a",
 'gh pr merge 13',
 'gh api repos/a/b -X POST',
 'gh pr view 13 --web',
 '/tmp/cat a',
 'cat *',
 'pwd\ntouch a',
 'git --no-pager log --oneline',
 'git --no-pager diff --no-ext-diff --no-textconv --stat',
 'git ls-files',
 'rg --no-config x --pre=helper',
 'rg --no-config x --hostname-bin=helper',
 'gh pr view 13 --template evil',
 'git -c core.fsmonitor=helper --no-pager status --short',
 'cat a &',
 'cat a < b',
 'cat a \\n b',
 'git --no-pager -c log.showSignature=false log --format --output=/tmp/out',
 'git --no-pager -c log.showSignature=false log --pretty --show-signature',
 'rg --no-config --color --pre=helper',
 'git --no-optional-locks -c core.fsmonitor= --no-pager diff --no-ext-diff --no-textconv '
 '--unified --output=/tmp/out',
 'gh pr view 13 --json --web']


if __name__ == '__main__':
    unittest.main()
