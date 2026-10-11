"""Synthetic failures only. A terminal receipt is classification, not permission to retry."""
import unittest
from test_earnings_mixed_runner import RunnerTests
from research import earnings_mixed_runner as r, earnings_execution_state as state


class FailureTests(RunnerTests):
    def failed(self):
        self.entries[-1]['message'].update(stopReason='error',
            diagnostics=[{'type':'provider_stream_failure'}],
            usage={'input':0,'output':0,'cacheRead':0,'cacheWrite':0,'totalTokens':0})
        self.write_journal()
        launch={'id':'failed-launch','request_sha256':r.digest(self.request)}
        r.save(self.job/'launch.json',launch)
        r.save(self.job/'runtime-start.json',{'launch_id':'failed-launch','session_id':'fake-session',
            'model':'gpt-6.1-sol','effort':'medium','oauth':True})
        r.save(self.job/'execution.json',{'status':'returned','exit_code':1,
            'request_sha256':r.digest(self.request),'launch_sha256':r.sha(self.job/'launch.json')})
        r.save(self.job/'wire.json',[{'model':'gpt-6.1-sol','effort':'medium','tools':0}])

    def test_terminal_stream_is_not_unknown_or_zero_cost_and_never_retried(self):
        self.failed();before={p:r.sha(p) for p in self.job.rglob('*') if p.is_file()}
        result=state.classify(self.job)
        self.assertEqual(result['status'],'execution_failed')
        self.assertEqual(result['failure_kind'],'provider_stream_failure')
        self.assertGreater(result['partial_text_chars'],0)
        self.assertFalse(result['actual_usage_known']);self.assertFalse(result['retry_allowed'])
        self.assertEqual(before,{p:r.sha(p) for p in self.job.rglob('*') if p.is_file()})

    def test_absent_or_changed_execution_remains_uncertain(self):
        self.assertEqual(state.classify(self.job)['status'],'execution_uncertain')
        self.failed();execution=r.read(self.job/'execution.json');execution['request_sha256']='wrong'
        (self.job/'execution.json').write_text(__import__('json').dumps(execution))
        self.assertEqual(state.classify(self.job)['status'],'execution_uncertain')

    def test_timeout_or_wrong_session_cannot_clear_uncertainty(self):
        self.failed();self.entries[0]['id']='different';self.write_journal()
        self.assertEqual(state.classify(self.job)['status'],'execution_uncertain')

    def test_completed_output_still_requires_full_verification(self):
        self.complete();result=state.classify(self.job)
        self.assertEqual(result['status'],'completed');self.assertTrue(result['actual_usage_known'])
        (self.job/'stdout.txt').write_text('changed')
        self.assertEqual(state.classify(self.job)['status'],'execution_uncertain')
