"""Fake completed receipts for bounded review replay; no model launches."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_repair_review as review
from research import earnings_experiment as base
from research import earnings_repair_context as context


class RepairReviewTests(PassageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.root/'attempts/0/review'
        self.results = {}
        self.candidate, self.plan = base.digest({'fake': 'candidate'}), base.digest({'fake': 'plan'})
        self.requests = [{'scope_id': 'D002', 'reason': 'Read complete fictional context'}]

    def replay(self, **overrides):
        args = dict(job_base=self.job, prompt_factory=lambda extra: 'Complete fictional report; scopes=' + ','.join(extra),
                    bindings={'protocol_sha256': 'fake'}, model=('gpt-6.1-sol', 'medium'), bundle=self.bundle,
                    catalog=self.catalog, candidate_sha256=self.candidate, plan_sha256=self.plan,
                    seen_sessions=set(), remaining_tokens=100000, max_prompt_chars=10000,
                    verifier=lambda job: self.results[str(job)])
        args.update(overrides)
        return review.replay(**args)

    def complete(self, pending, verdict='pass', sid='fake-review-1', tokens=100, **content):
        job = pending['job']; job.mkdir(parents=True, exist_ok=True)
        (job/'prompt.txt').write_text(pending['prompt'])
        request = {'bindings': pending['bindings'], 'model': 'gpt-6.1-sol', 'effort': 'medium',
                   'prompt_sha256': base.sha(job/'prompt.txt')}
        base.save(job/'request.json', request)
        value = {'verdict': verdict, 'candidate_sha256': self.candidate, 'plan_sha256': self.plan, **content}
        output = {'request_sha256': base.digest(request), 'content': value}
        base.save(job/'output.json', output)
        self.results[str(job)] = {'content': value, 'receipt': {'session': {'id': sid, 'usage': {'totalTokens': tokens}}}}

    def test_pending_completed_and_candidate_binding(self):
        p = self.replay()
        self.assertEqual(p['status'], 'pending')
        self.assertEqual(p['bindings']['candidate_sha256'], self.candidate)
        self.complete(p)
        seen = set(); result = self.replay(seen_sessions=seen)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['tokens'], 100)
        self.assertEqual(seen, {'fake-review-1'})

    def test_one_expansion_preserves_candidate_round_and_accounts_both_receipts(self):
        self.complete(self.replay(), 'needs_evidence', requests=self.requests)
        second = self.replay()
        self.assertEqual(second['status'], 'pending')
        self.assertEqual(second['job'].name, 'review-evidence-1')
        self.assertEqual(second['job'].parent, self.job.parent)
        self.assertEqual(second['bindings']['candidate_sha256'], self.candidate)
        self.assertEqual(second['bindings']['evidence_requests_sha256'], base.digest(self.requests))
        self.assertEqual(second['bindings']['prior_review_output_sha256'], base.sha(self.job/'output.json'))
        self.assertIn('D002', second['prompt'])
        self.assertEqual(second['tokens'], 100)
        self.complete(second, sid='fake-review-2', tokens=80)
        final = self.replay()
        self.assertEqual(final['status'], 'completed')
        self.assertEqual(final['tokens'], 180)

    def test_second_evidence_request_stops_without_final_acceptance(self):
        self.complete(self.replay(), 'needs_evidence', requests=self.requests)
        self.complete(self.replay(), 'needs_evidence', sid='fake-review-2', requests=[{'scope_id':'D001','reason':'Need more'}])
        result = self.replay()
        self.assertEqual(result['status'], 'evidence_insufficient')
        self.assertEqual(result['tokens'], 200)

    def test_partial_launch_and_empty_directory(self):
        self.job.mkdir(parents=True)
        self.assertEqual(self.replay()['status'], 'pending')
        (self.job/'launch.json').write_text('{}')
        self.assertEqual(self.replay()['status'], 'launch_uncertain')

    def test_budget_and_prompt_limits_apply_before_and_after_receipts(self):
        self.assertEqual(self.replay(remaining_tokens=0)['status'], 'budget_exhausted')
        self.assertEqual(self.replay(max_prompt_chars=10)['status'], 'prompt_too_large')
        self.complete(self.replay(), tokens=101)
        self.assertEqual(self.replay(remaining_tokens=100)['status'], 'budget_exhausted')
        self.assertEqual(self.replay(max_prompt_chars=10)['status'], 'prompt_too_large')

    def test_context_too_large_becomes_prompt_too_large(self):
        def factory(extra): raise context.ContextTooLarge('too much source')
        self.assertEqual(self.replay(prompt_factory=factory)['status'], 'prompt_too_large')

    def test_duplicate_sessions_invalid_usage_and_candidate_are_rejected(self):
        self.complete(self.replay(), 'needs_evidence', requests=self.requests)
        second = self.replay(); self.complete(second)
        with self.assertRaisesRegex(ValueError, 'fresh review sessions'):
            self.replay()
        self.results[str(second['job'])]['receipt']['session']['id'] = 'different'
        self.results[str(second['job'])]['receipt']['session']['usage']['totalTokens'] = True
        with self.assertRaisesRegex(ValueError, 'token usage'):
            self.replay()
        self.results[str(second['job'])]['receipt']['session']['usage']['totalTokens'] = 10
        value = self.results[str(second['job'])]['content']; value['candidate_sha256'] = 'wrong'
        raw = base.read(second['job']/'output.json'); raw['content'] = value
        (second['job']/'output.json').write_text(__import__('json').dumps(raw))
        with self.assertRaisesRegex(ValueError, 'candidate or plan'):
            self.replay()

    def test_changed_prompt_and_request_hash_fail(self):
        self.complete(self.replay())
        with self.assertRaisesRegex(ValueError, 'immutable request'):
            self.replay(prompt_factory=lambda extra: 'Altered prompt')
        output = base.read(self.job/'output.json'); output['request_sha256'] = 'forged'
        (self.job/'output.json').write_text(__import__('json').dumps(output))
        with self.assertRaisesRegex(ValueError, 'immutable request'):
            self.replay()

    def test_unknown_evidence_scope_and_extra_response_field_fail(self):
        self.complete(self.replay(), 'needs_evidence', requests=[{'scope_id':'unknown','reason':'Need source'}])
        with self.assertRaisesRegex(ValueError, 'Unknown requested'):
            self.replay()
        # This is a separate synthetic completed journal, not a repair of a job.
        self.job = self.root/'other/review'
        self.complete(self.replay(), 'needs_evidence', requests=self.requests, approve_patch=True)
        with self.assertRaisesRegex(ValueError, 'requires only'):
            self.replay()


    def test_evidence_recovery_cannot_open_another_lookup(self):
        self.complete(self.replay(max_expansions=0), 'needs_evidence', requests=self.requests)
        result=self.replay(max_expansions=0)
        self.assertEqual(result['status'],'evidence_insufficient')
        self.assertEqual(result['tokens'],100)
        self.assertFalse(self.job.with_name('review-evidence-1').exists())
