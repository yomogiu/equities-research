"""Fictitious journals only: no provider calls or credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_mixed_runner as runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name) / 'fake-role'
        self.job.mkdir()
        self.prompt = 'Fictitious evidence: output {"ok":true}'
        self.request = runner._request(self.job, self.prompt, 'gpt-6.1-sol', 'medium', {'fake': 'hash'}, 900)
        runner.save(self.job / 'request.json', self.request)
        (self.job / 'prompt.txt').write_text(self.prompt)
        (self.job / 'stdout.txt').write_text('{"ok":true}')
        (self.job / 'sessions').mkdir()
        self.entries = [
            {'type': 'session', 'id': 'fake-session', 'cwd': str(self.job)},
            {'type': 'model_change', 'provider': runner.PROVIDER, 'modelId': 'gpt-6.1-sol'},
            {'type': 'thinking_level_change', 'thinkingLevel': 'medium'},
            {'type': 'message', 'message': {'role': 'user', 'content': self.prompt}},
            {'type': 'message', 'message': {'role': 'assistant', 'provider': runner.PROVIDER,
                'model': 'gpt-6.1-sol', 'api': 'openai-codex-responses', 'stopReason': 'stop',
                'content': [{'type': 'text', 'text': '{"ok":true}'}],
                'usage': {'input': 80, 'cacheRead': 20, 'cacheWrite': 0, 'output': 10, 'totalTokens': 110}}}]
        self.write_journal()

    def write_journal(self):
        (self.job / 'sessions' / 'fake.jsonl').write_text('\n'.join(json.dumps(e) for e in self.entries)+'\n')

    def complete(self):
        launch = {'id': 'fake-launch', 'request_sha256': runner.digest(self.request)}
        runner.save(self.job / 'launch.json', launch)
        identity = {'session_id': 'fake-session', 'model': 'gpt-6.1-sol', 'effort': 'medium', 'oauth': True}
        runner.save(self.job / 'runtime-start.json', {**identity, 'launch_id': 'fake-launch'})
        runner.save(self.job / 'runtime-finish.json', identity)
        runner.save(self.job / 'wire.json', [{'model': 'gpt-6.1-sol', 'effort': 'medium', 'tools': 0}])
        execution = {'status': 'completed', 'exit_code': 0, 'elapsed_seconds': 1.5,
            'launch_sha256': runner.sha(self.job / 'launch.json'),
            'request_sha256': runner.digest(self.request), 'session': runner.session_receipt(self.job),
            'artifact_sha256': {name: runner.sha(self.job / name) for name in
                ('runtime-start.json', 'runtime-finish.json', 'wire.json', 'stdout.txt')}}
        runner.save(self.job / 'execution.json', execution)
        runner.save(self.job / 'output.json', {'content': {'ok': True},
            'request_sha256': runner.digest(self.request), 'execution_sha256': runner.sha(self.job / 'execution.json')})

    def test_measured_uncached_input_not_double_subtracted(self):
        receipt = runner.session_receipt(self.job)
        self.assertEqual(receipt['usage']['input'], 80)
        self.assertEqual(receipt['usage']['totalTokens'], 110)

    def test_unknown_model_rejected_before_launch(self):
        with self.assertRaises(ValueError):
            runner.run_role(self.job, self.prompt, 'gpt-6.1-anything', 'medium', {})

    def test_mismatched_model_or_effort_in_journal(self):
        for index, field, value in ((1, 'modelId', 'fallback'), (1, 'provider', 'other'), (2, 'thinkingLevel', 'high')):
            with self.subTest(field=field):
                original = self.entries[index][field]
                self.entries[index][field] = value
                self.write_journal()
                with self.assertRaises(ValueError):
                    runner.session_receipt(self.job)
                self.entries[index][field] = original

    def test_missing_model_or_thinking_is_not_inferred(self):
        self.entries.pop(2)
        self.write_journal()
        with self.assertRaises(ValueError):
            runner.session_receipt(self.job)

    def test_assistant_fallback_rejected(self):
        self.entries[-1]['message']['model'] = 'gpt-5.6-sol'
        self.write_journal()
        with self.assertRaises(ValueError):
            runner.session_receipt(self.job)

    def test_prompt_mismatch(self):
        self.entries[3]['message']['content'] += ' other prompt'
        self.write_journal()
        with self.assertRaises(ValueError):
            runner.session_receipt(self.job)

    def test_output_limit_not_completed(self):
        self.entries[-1]['message']['stopReason'] = 'length'
        self.write_journal()
        with self.assertRaises(ValueError):
            runner.session_receipt(self.job)

    def test_invalid_token_accounting(self):
        self.entries[-1]['message']['usage']['totalTokens'] = 90
        self.write_journal()
        with self.assertRaises(ValueError):
            runner.session_receipt(self.job)

    def test_resume_does_not_launch(self):
        self.complete()
        with patch.object(runner.subprocess, 'Popen') as popen:
            result = runner.run_role(self.job, self.prompt, 'gpt-6.1-sol', 'medium', {'fake': 'hash'})
            self.assertEqual(result['content'], {'ok': True})
            popen.assert_not_called()

    def test_uncertain_launch_does_not_launch(self):
        with patch.object(runner.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'duplicate'):
                runner.run_role(self.job, self.prompt, 'gpt-6.1-sol', 'medium', {'fake': 'hash'})
            popen.assert_not_called()

    def test_dependency_tampering_does_not_resume(self):
        self.complete()
        with self.assertRaisesRegex(ValueError, 'request differs'):
            runner.run_role(self.job, self.prompt, 'gpt-6.1-sol', 'medium', {'fake': 'changed'})

    def test_session_tampering(self):
        self.complete()
        self.entries[0]['id'] = 'different-session'
        self.write_journal()
        with self.assertRaisesRegex(ValueError, 'Session evidence changed'):
            runner.verify_job(self.job)

    def test_output_tampering(self):
        self.complete()
        value = runner.read(self.job / 'output.json')
        value['content'] = {'ok': False}
        (self.job / 'output.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Output content changed'):
            runner.verify_job(self.job)

    def test_execution_tampering(self):
        self.complete()
        value = runner.read(self.job / 'execution.json')
        value['elapsed_seconds'] = 0
        (self.job / 'execution.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Execution changed'):
            runner.verify_job(self.job)

    def test_two_sessions_rejected(self):
        (self.job / 'sessions' / 'other.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Exactly one session'):
            runner.session_receipt(self.job)

    def test_timeout_terminates_group_and_prevents_duplicate(self):
        fresh = self.job.parent / 'timeout-role'
        with patch.object(runner, '_runtime_paths', return_value=(Path('/fake/node'), Path('/fake/sdk'))), \
             patch.object(runner.subprocess, 'Popen') as popen, \
             patch.object(runner.os, 'killpg') as killpg:
            process = popen.return_value
            process.pid = 12345
            process.returncode = -15
            process.wait.side_effect = [runner.subprocess.TimeoutExpired('fake', 1), None]
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                runner.run_role(fresh, self.prompt, 'gpt-6.1-sol', 'medium', {}, timeout=1)
            self.assertEqual(runner.read(fresh / 'execution.json')['status'], 'timeout')
            killpg.assert_called_once_with(12345, runner.signal.SIGTERM)
            with self.assertRaisesRegex(RuntimeError, 'duplicate'):
                runner.run_role(fresh, self.prompt, 'gpt-6.1-sol', 'medium', {}, timeout=1)
            self.assertEqual(popen.call_count, 1)

    def test_exclusive_artifacts(self):
        with self.assertRaises(FileExistsError):
            runner.save(self.job / 'request.json', self.request)


if __name__ == '__main__':
    unittest.main()
