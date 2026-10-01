"""Audit regression tests with mocked provider receipts and fictitious data."""
from unittest.mock import patch
import unittest
import test_earnings_mixed_continuation as fixtures
from research import earnings_mixed_continuation as continuation
from research import earnings_mixed_audit as audit
from research import earnings_experiment as base
from research import earnings_mixed_pipeline as pipeline


class MixedAuditTests(fixtures.ContinuationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for role in ('financial','retrieval'):
            self.jobs[str(self.parent/'jobs'/f'{role}-r0')]['receipt']['session']={'id':role+'-fake'}
        original_call=self.call
        def call(path,prompt,model,effort,bindings,timeout):
            value=original_call(path,prompt,model,effort,bindings,timeout)
            value['receipt']['session']={'id':bindings['role']+'-fake'}
            request=base.read(path/'request.json');request.update(model=model,effort=effort)
            (path/'request.json').write_text(__import__('json').dumps(request))
            (path/'prompt.txt').write_text(prompt)
            return value
        patcher=patch.object(continuation,'run_role',side_effect=call);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(audit,'verify_job',side_effect=lambda p:self.jobs[str(p)]);patcher.start();self.addCleanup(patcher.stop)

    def test_empty_downstream_jobs_cannot_bypass_verification(self):
        result=continuation.run(self.parent,self.output)
        self.assertEqual('accepted',audit.audit_continuation(self.output)['status'])
        result['jobs']=[];(self.output/'result.json').write_text(__import__('json').dumps(result))
        with self.assertRaisesRegex(ValueError,'Exactly ordered'):audit.audit_continuation(self.output)

    def test_forged_timing_rejected(self):
        result=continuation.run(self.parent,self.output)
        result['downstream_wall_seconds']=0;(self.output/'result.json').write_text(__import__('json').dumps(result))
        with self.assertRaisesRegex(ValueError,'Timing'):audit.audit_continuation(self.output)

    def test_wrong_role_model_rejected(self):
        continuation.run(self.parent,self.output)
        p=self.output/'jobs/review/request.json';q=base.read(p);q.update(model='gpt-5.6-luna',effort='max');p.write_text(__import__('json').dumps(q))
        with self.assertRaisesRegex(ValueError,'model/effort'):audit.audit_continuation(self.output)
