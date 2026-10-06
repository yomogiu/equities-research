"""Fictitious authenticated receipts only; these tests never launch models."""
import copy
import unittest
from unittest.mock import patch
import test_earnings_repair_review as review_fixture
import test_earnings_corrections as correction_fixture
from test_earnings_passages import PassageFixture
from research import earnings_budget as budget
from research import earnings_corrections as corrections
from research import earnings_experiment as base


class AdmissionTests(unittest.TestCase):
    def test_utf8_reservation_includes_input_runtime_and_output_without_measured_usage(self):
        text = 'Fictional café 😀'
        reserved = len(text.encode('utf-8')) + budget.FRAMING_ALLOWANCE + budget.OUTPUT_ALLOWANCE
        result = budget.admission(text, reserved)
        self.assertTrue(result['admitted'])
        self.assertEqual(result['reserved_tokens'], reserved)
        self.assertEqual(result['prompt_utf8_bytes'], len(text.encode('utf-8')))
        self.assertFalse(budget.admission(text, reserved - 1)['admitted'])
        self.assertIn('not an exact tokenizer', result['notice'])
        self.assertNotIn('measured_tokens', result)

    def test_27196_remaining_refuses_large_review_without_altering_measured_counter(self):
        result = budget.admission('Fictional review content. ' * 13000, 27196)
        self.assertFalse(result['admitted'])
        self.assertEqual(result['remaining_tokens'], 27196)
        measured = budget.compliance(100, 1000, 50)
        self.assertEqual(measured['total_measured_tokens'], 150)
        self.assertEqual(measured['overrun_tokens'], 0)

    def test_invalid_counter_types_fail_closed(self):
        for value in (True, 1.5, '100000'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.admission('Fictional', value)
        for value in (True, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.compliance(value, 1000)


class BudgetReviewTests(PassageFixture, unittest.TestCase):
    replay = review_fixture.RepairReviewTests.replay
    complete = review_fixture.RepairReviewTests.complete

    def setUp(self):
        super().setUp()
        self.job = self.root/'attempts/0/review'; self.results = {}
        self.candidate, self.plan = base.digest({'fake': 'candidate'}), base.digest({'fake': 'plan'})
        self.requests = [{'scope_id': 'D002', 'reason': 'Read complete fictional context'}]

    def test_insufficient_review_budget_is_terminal_without_creating_job(self):
        result = self.replay(remaining_tokens=27196)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertFalse(result['budget_admission']['admitted'])
        self.assertEqual(result['tokens'], 0)
        self.assertFalse(self.job.exists())
        self.assertEqual(self.replay(remaining_tokens=27196), result)

    def test_evidence_expansion_reserves_again_after_measured_first_receipt(self):
        first = self.replay(); self.complete(first, 'needs_evidence', tokens=100, requests=self.requests)
        second = self.replay()
        self.assertEqual(second['status'], 'pending')
        reserve = second['budget_admission']['reserved_tokens']
        stopped = self.replay(remaining_tokens=reserve + 99)
        self.assertEqual(stopped['status'], 'budget_exhausted')
        self.assertEqual(stopped['tokens'], 100)
        self.assertEqual(stopped['job'].name, 'review-evidence-1')
        self.assertFalse(stopped['job'].exists())
        admitted = self.replay(remaining_tokens=reserve + 100)
        self.assertEqual(admitted['status'], 'pending')

    def test_completed_overbudget_pass_stays_available_for_full_adjudication(self):
        self.complete(self.replay(), tokens=150)
        result = self.replay(remaining_tokens=100)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertTrue(result['requires_adjudication'])
        self.assertEqual(result['review_verdict'], 'pass')
        self.assertEqual(result['result']['content']['verdict'], 'pass')
        self.assertEqual(result['budget_compliance']['overrun_tokens'], 50)
        self.assertEqual(result['tokens'], 150)

    def test_overbudget_saved_evidence_request_is_still_validated(self):
        self.complete(self.replay(), 'needs_evidence', tokens=150,
                      requests=[{'scope_id': 'foreign-fictional', 'reason': 'Invalid source'}])
        with self.assertRaisesRegex(ValueError, 'Unknown requested'):
            self.replay(remaining_tokens=100)

    def test_partial_launch_is_uncertain_even_when_admission_would_refuse(self):
        self.job.mkdir(parents=True); (self.job/'launch.json').write_text('{}')
        result = self.replay(remaining_tokens=0)
        self.assertEqual(result['status'], 'launch_uncertain')
        self.assertFalse(result['budget_admission']['admitted'])


class BudgetCorrectionTests(PassageFixture, unittest.TestCase):
    state = correction_fixture.CorrectionTests.state
    op = correction_fixture.CorrectionTests.op
    plan = correction_fixture.CorrectionTests.plan
    review = correction_fixture.CorrectionTests.review

    def completed_pair(self, invalid=False):
        root = self.root/'corrections'; root.mkdir()
        state = self.state(); plan = self.plan(state)
        candidate = corrections.apply(state, plan, self.bundle, self.catalog)
        review = self.review(state, plan, candidate)
        if invalid: review['resolutions'] = []
        base.save(root/'initial.json', state); base.save(root/'protocol.json', {'fictional': True})
        results = {}
        for role, value in (('propose', plan), ('review', review)):
            job = root/'rounds/0'/role; job.mkdir(parents=True)
            text = corrections.prompt(role, state, self.bundle, self.catalog, 'Fictional',
                                      plan if role == 'review' else None, candidate if role == 'review' else None)
            (job/'prompt.txt').write_text(text)
            bindings = {'protocol_sha256': base.sha(root/'protocol.json'), 'snapshot_sha256': base.digest(state),
                        'round': 0, 'role': role}
            if role == 'review':
                bindings.update(review_context_version=corrections.review_loop.VERSION,
                    candidate_sha256=base.digest(candidate), plan_sha256=base.digest(plan), evidence_expansion=0,
                    evidence_requests_sha256=base.digest([]), extra_scope_ids_sha256=base.digest([]),
                    prior_review_output_sha256=None)
            request = {'model': corrections.MODEL[0], 'effort': corrections.MODEL[1], 'bindings': bindings,
                       'prompt_sha256': base.sha(job/'prompt.txt')}
            base.save(job/'request.json', request)
            base.save(job/'output.json', {'content': value, 'request_sha256': base.digest(request)})
            results[str(job)] = {'content': value, 'receipt': {'session': {'id': 'fake-' + role,
                'usage': {'totalTokens': 50 if role == 'propose' else 150}}}}
        return root, state, results

    def test_saved_pass_has_valid_substantive_metadata_but_cannot_accept_or_apply(self):
        root, state, results = self.completed_pair()
        with patch.object(corrections, 'verify_job', side_effect=lambda job: results[str(job)]):
            result = corrections.replay(root, {'max_rounds': 2, 'max_tokens': 100},
                                        self.bundle, self.catalog, 'Fictional')
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['state'], state)
        self.assertEqual(result['tokens'], 200)
        self.assertEqual(result['substantive_review']['verdict'], 'pass')
        self.assertEqual(result['substantive_review']['validation'], 'valid')
        self.assertEqual(result['substantive_review']['outcome'], 'accepted')
        self.assertEqual(result['budget_compliance']['overrun_tokens'], 100)
        self.assertFalse(base.read(root/'rounds/0/decision.json')['patch_applied'])

    def test_invalid_saved_pass_is_not_hidden_by_budget_failure(self):
        root, _, results = self.completed_pair(invalid=True)
        with patch.object(corrections, 'verify_job', side_effect=lambda job: results[str(job)]):
            result = corrections.replay(root, {'max_rounds': 2, 'max_tokens': 100},
                                        self.bundle, self.catalog, 'Fictional')
        self.assertEqual(result['status'], 'invalid_review')
        self.assertEqual(result['substantive_review']['validation'], 'invalid')
        self.assertFalse(result['budget_compliance']['within_budget'])

    def test_advance_refuses_author_before_model_and_preserves_partial_launch(self):
        root = self.root/'pending'; root.mkdir()
        state = self.state(); base.save(root/'initial.json', state); base.save(root/'protocol.json', {})
        protocol = {'max_rounds': 2, 'max_tokens': 27196}
        with patch.object(corrections, 'load', return_value=(protocol, self.bundle, self.catalog, 'Fictional')), \
                patch.object(corrections, 'run_role') as worker:
            result = corrections.advance(root)
            self.assertEqual(result['status'], 'budget_exhausted')
            worker.assert_not_called()
        job = root/'rounds/0/propose'; job.mkdir(parents=True); (job/'launch.json').write_text('{}')
        progress = corrections.replay(root, protocol, self.bundle, self.catalog, 'Fictional')
        self.assertEqual(progress['status'], 'launch_uncertain')


if __name__ == '__main__':
    unittest.main()
