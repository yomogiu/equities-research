"""Fictional exception authorization and frozen-replay contracts; no models."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_earnings_corrections as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_acceptance_exception as exception
from research import earnings_corrections as corrections
from research import earnings_experiment as base
from research import earnings_signals as signals


class ExceptionTests(PassageFixture, unittest.TestCase):
    state = fixtures.CorrectionTests.state
    op = fixtures.CorrectionTests.op
    plan = fixtures.CorrectionTests.plan
    review = fixtures.CorrectionTests.review

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.seed = self.root/'seed'; self.seed.mkdir(); self.output = self.root/'exception'
        self.before = self.state(); self.edit = self.plan(self.before)
        self.candidate = corrections.apply(self.before, self.edit, self.bundle, self.catalog)
        self.review_content = self.review(self.before, self.edit, self.candidate)
        self.accepted, _ = corrections.adjudicate(self.before, self.candidate, self.edit,
                                                 self.review_content, self.bundle, self.catalog)
        self.folder = self.seed/'rounds/0'; self.job = self.folder/'review'; self.job.mkdir(parents=True)
        self.old = {'version': corrections.VERSION, 'code': [], 'source_code': [], 'source_protocol': {},
                    'max_tokens': 100, 'inherited_tokens': 0, 'prior_rounds': 0}
        base.save(self.seed/'protocol.json', self.old)
        base.save(self.folder/'plan.json', self.edit); base.save(self.folder/'candidate.json', self.candidate)
        (self.folder/'candidate.html').write_text(corrections.rendered(self.candidate, self.bundle, self.catalog))
        (self.job/'prompt.txt').write_text('Fictional final review prompt')
        base.save(self.job/'request.json', {'fictional': True})
        base.save(self.job/'output.json', {'content': self.review_content})
        self.receipt = {'content': self.review_content,
                        'receipt': {'session': {'id': 'fictional-independent-review', 'usage': {'totalTokens': 150}}}}
        self.progress = {'status': 'budget_exhausted', 'state': self.before, 'tokens': 150,
                         'job': self.job, 'role': 'review', 'round': 0}
        self.exported = self.export_in_process()
        self.auth = {'kind': 'budget_acceptance_exception', 'enabled': True,
                     'authorization_id': 'fictional-user-approval', 'authorization_reference': 'Fictional user message 42',
                     'reason': 'Explicitly accept this exact reviewed historical overrun.',
                     'seed_protocol_sha256': base.sha(self.seed/'protocol.json'),
                     'review_output_sha256': self.exported['review']['output_sha256'],
                     'candidate_sha256': self.exported['review']['candidate_sha256'],
                     'plan_sha256': self.exported['review']['plan_sha256'], 'historical_total_tokens': 150,
                     'original_max_tokens': 100, 'authorized_overrun_tokens': 50, 'output_path': str(self.output)}

    def export_in_process(self):
        # Simulate only the frozen verifier's authenticated result/replay. The
        # real apply, complete adjudication, rendering, filesystem inventory,
        # original hashes and exception checks still run.
        def replay(root, *args):
            corrections.verify_job(self.job)
            return self.progress
        with (patch.object(corrections, 'load', return_value=(self.old, self.bundle, self.catalog, 'Fictional')),
              patch.object(corrections, 'replay', side_effect=replay),
              patch.object(corrections, 'verify_job', return_value=self.receipt),
              patch.object(corrections.repair, 'write', corrections.repair.write),
              patch.object(corrections.legacy, 'immutable_text', corrections.legacy.immutable_text),
              patch.object(sys, 'argv', ['export', str(self.seed)]),
              contextlib.redirect_stdout(io.StringIO()) as out):
            exec(exception.EXPORT, {})
        return json.loads(out.getvalue())

    def mocked_export(self, seed):
        return copy.deepcopy(self.old), copy.deepcopy(self.exported), exception.source_bindings(self.seed, self.old)

    def initialize(self, authorization=None):
        with patch.object(exception, 'export_seed', side_effect=self.mocked_export):
            return exception.initialize(self.seed, self.output, authorization or self.auth)

    def verify(self):
        with patch.object(exception, 'export_seed', side_effect=self.mocked_export):
            return exception.verify(self.output)

    def test_exact_authorization_creates_accepted_edition_with_original_budget_history(self):
        original = {str(p): base.sha(p) for p in self.seed.rglob('*') if p.is_file()}
        result = self.initialize(); verified = self.verify()
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(verified['acceptance_basis'], 'explicit_user_budget_exception')
        self.assertEqual(verified['history']['total_tokens'], 150)
        self.assertEqual(verified['history']['original_max_tokens'], 100)
        self.assertEqual(verified['history']['overrun_tokens'], 50)
        self.assertFalse(verified['budget_reset']); self.assertEqual(verified['new_report_model_calls'], 0)
        self.assertEqual(base.read(self.output/'state.json'), self.accepted)
        self.assertEqual(original, {str(p): base.sha(p) for p in self.seed.rglob('*') if p.is_file()})

    def test_mismatched_authority_review_usage_or_destination_rejected_before_output(self):
        changes = {'enabled': False, 'authorization_reference': '', 'seed_protocol_sha256': '0'*64,
                   'review_output_sha256': '0'*64, 'candidate_sha256': '0'*64, 'plan_sha256': '0'*64,
                   'historical_total_tokens': 151, 'original_max_tokens': 101, 'authorized_overrun_tokens': 51,
                   'output_path': str(self.root/'other')}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.initialize({**self.auth, key: value})
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError): self.initialize({**self.auth, 'extra': True})

    def test_nonbudget_and_incomplete_or_invalid_reviews_cannot_be_excepted(self):
        for status in ('blocked', 'pending', 'launch_uncertain', 'invalid_review', 'prompt_too_large'):
            self.progress['status'] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'conclusive budget'):
                self.export_in_process()
        self.progress['status'] = 'budget_exhausted'
        self.review_content['verdict'] = 'revise'
        with self.assertRaisesRegex(ValueError, 'passing final'): self.export_in_process()
        self.review_content['verdict'] = 'pass'; self.review_content['resolutions'] = []
        with self.assertRaisesRegex(ValueError, 'every pending finding'): self.export_in_process()

    def test_uncertain_launch_only_job_is_rejected(self):
        other = self.seed/'rounds/1/propose'; other.mkdir(parents=True)
        (other/'launch.json').write_text('{"fictional":"uncertain"}')
        with self.assertRaisesRegex(ValueError, 'uncertain extra jobs'):
            self.export_in_process()

    def test_wrong_candidate_and_nonbudget_prompt_hold_are_rejected(self):
        candidate_path = self.folder/'candidate.json'
        saved = candidate_path.read_text(); candidate_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Saved candidate differs'): self.export_in_process()
        candidate_path.write_text(saved)
        (self.job/'prompt.txt').write_text('F'*350001)
        with self.assertRaisesRegex(ValueError, 'prompt-size hold'): self.export_in_process()

    def test_result_state_and_authorization_tampering_fails_replay(self):
        self.initialize()
        for name in ('authorization.json', 'state.json', 'result.json', 'source-export.json'):
            path = self.output/name; saved = path.read_text()
            value = json.loads(saved); value['injected'] = True; path.write_text(json.dumps(value))
            try:
                with self.subTest(name=name), self.assertRaises(ValueError): self.verify()
            finally:
                path.write_text(saved)

    def test_signals_export_uses_exception_verifier_and_excludes_prior_session(self):
        self.initialize()
        with patch.object(exception, 'verify', return_value={'status': 'accepted'}) as verifier, \
                patch.object(sys, 'argv', ['export', str(self.output)]), contextlib.redirect_stdout(io.StringIO()) as out:
            exec(signals.EXPORT, {})
        value = json.loads(out.getvalue())
        self.assertEqual(value['excluded_session_ids'], ['fictional-independent-review'])
        self.assertEqual(value['state']['artifacts'], self.accepted['artifacts'])
        verifier.assert_called_once()

    def test_signals_reject_reusing_the_accepted_report_review_session(self):
        self.initialize()
        job = self.output/'jobs/analysis'; job.mkdir(parents=True)
        base.save(job/'output.json', {'fictional': True})
        bindings = {'protocol_sha256': base.sha(self.output/'protocol.json'),
                    'report_sha256': signals.report_digest(self.accepted), 'role': 'analysis'}
        base.save(job/'request.json', {'bindings': bindings, 'model': signals.MODEL[0],
                                       'effort': signals.MODEL[1]})
        (job/'prompt.txt').write_text('Fictional signal prompt')
        protocol = {'excluded_session_ids': ['fictional-independent-review']}
        with (patch.object(signals, 'load', return_value=(protocol, self.accepted, self.bundle, self.catalog, '')),
              patch.object(signals, 'prompt', return_value='Fictional signal prompt'),
              patch.object(signals, 'verify_job', return_value=self.receipt),
              patch.object(signals, 'run_role') as runner,
              self.assertRaisesRegex(ValueError, 'Fresh independent reviewer')):
            signals.advance(self.output, False)
        runner.assert_not_called()


if __name__ == '__main__': unittest.main()
