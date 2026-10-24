"""Fictitious, offline tests of the five-stage state machine."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research import earnings_sequential as pipeline


class SequentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.handlers = {stage: self.handler(stage) for stage in pipeline.STAGES}
        pipeline.create(self.root, {"company": "Fictional Widgets", "budget_tokens": 100})

    def artifact(self, name, text):
        (self.root / name).write_text(text)
        return hashlib.sha256(text.encode()).hexdigest()

    def handler(self, stage):
        def execute(root, job):
            self.calls.append(stage)
            name = "report.md" if stage == "analysis" else stage + ".json"
            if stage == "review":
                name = f"review-r{job['revision_round']}.json"
            result = {"status": "completed", "tokens": 10 if stage in ("analysis", "review") else 0,
                      "outputs": {name: self.artifact(name, stage + str(job["revision_round"]))}}
            if stage in ("analysis", "review"):
                result["session_id"] = stage + str(job["revision_round"])
            if stage in ("review", "publication"):
                result["input_sha256"] = job["artifacts"]["report.md"]
            return result
        return execute

    def advance(self):
        return pipeline.advance(self.root, self.handlers)

    def through_analysis(self):
        for _ in range(3):
            self.advance()

    def test_exact_order_and_completed_never_reruns(self):
        for _ in range(5):
            result = self.advance()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tokens_used"], 20)
        self.assertEqual(self.calls, list(pipeline.STAGES))
        self.assertEqual(self.advance(), result)
        self.assertEqual(len(self.calls), 5)

    def test_create_cannot_reset_existing_job(self):
        self.advance()
        with self.assertRaises(FileExistsError):
            pipeline.create(self.root, {})
        self.assertEqual(json.loads((self.root / "job.json").read_text())["stage"], "financial_tables")

    def test_running_record_is_durable_before_handler(self):
        def execute(root, job):
            persisted = json.loads((root / "job.json").read_text())
            self.assertEqual(persisted["status"], "running")
            self.assertEqual(len(persisted["attempts"]), 1)
            raise RuntimeError("fake interruption")
        self.handlers["sources"] = execute
        with self.assertRaisesRegex(RuntimeError, "fake interruption"):
            self.advance()
        result = self.advance()
        self.assertEqual(result["status"], "execution_uncertain")
        self.assertEqual(self.advance(), result)

    def test_saved_outcome_reconciles_without_handler_repetition(self):
        def execute(root, job):
            outcome = self.handler("sources")(root, job)
            pipeline.save_outcome(root, outcome)
            raise RuntimeError("interruption after durable result")
        self.handlers["sources"] = execute
        with self.assertRaises(RuntimeError):
            self.advance()
        result = self.advance()
        self.assertEqual(result["stage"], "financial_tables")
        self.assertEqual(self.calls, ["sources"])

    def test_publication_checkpoint_prevents_duplicate_publication(self):
        for _ in range(4):
            self.advance()
        def publish(root, job):
            outcome = self.handler("publication")(root, job)
            pipeline.save_outcome(root, outcome)
            raise RuntimeError("crash after publication")
        self.handlers["publication"] = publish
        with self.assertRaises(RuntimeError):
            self.advance()
        self.assertEqual(self.advance()["status"], "completed")
        self.assertEqual(self.calls.count("publication"), 1)

    def test_reviewer_cannot_be_author(self):
        self.through_analysis()
        def review(root, job):
            result = self.handler("review")(root, job)
            result["session_id"] = "analysis0"
            return result
        self.handlers["review"] = review
        result = self.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("independent", result["reason"])
        self.assertEqual(result["tokens_used"], 20)

    def test_review_binds_exact_candidate(self):
        self.through_analysis()
        def review(root, job):
            result = self.handler("review")(root, job)
            result["input_sha256"] = "0" * 64
            return result
        self.handlers["review"] = review
        self.assertIn("exact candidate", self.advance()["reason"])

    def test_tampering_blocks_before_next_handler(self):
        self.advance()
        (self.root / "sources.json").write_text("modified")
        result = self.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.calls, ["sources"])

    def test_published_candidate_cannot_change_after_acceptance(self):
        for _ in range(4):
            self.advance()
        (self.root / "report.md").write_text("not the reviewed report")
        self.assertEqual(self.advance()["status"], "blocked")
        self.assertNotIn("publication", self.calls)

    def test_corrections_keep_sources_tables_and_all_usage(self):
        self.through_analysis()
        def review(root, job):
            result = self.handler("review")(root, job)
            if job["revision_round"] == 0:
                result["status"] = "revise"
            return result
        self.handlers["review"] = review
        result = self.advance()
        self.assertEqual(result["revision_round"], 1)
        self.assertEqual(set(result["artifacts"]), {"sources.json", "financial_tables.json", "review-r0.json"})
        for _ in range(3):
            result = self.advance()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tokens_used"], 40)
        self.assertEqual(self.calls.count("sources"), 1)
        self.assertEqual(self.calls.count("financial_tables"), 1)
        self.assertEqual(len(result["attempts"]), 7)

    def test_revision_cap_does_not_reset_usage(self):
        self.through_analysis()
        def review(root, job):
            result = self.handler("review")(root, job)
            result["status"] = "revise"
            return result
        self.handlers["review"] = review
        for _ in range(5):
            result = self.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["revision_round"], 2)
        self.assertEqual(result["tokens_used"], 60)
        self.assertIn("revision limit", result["reason"])

    def test_dry_run_does_not_launch_or_modify_job(self):
        before = (self.root / "job.json").read_bytes()
        pipeline.advance(self.root, self.handlers, execute=False)
        self.assertEqual(before, (self.root / "job.json").read_bytes())
        self.assertEqual(self.calls, [])

    def test_budget_overrun_is_accounted_and_blocks(self):
        self.advance()
        self.advance()
        def author(root, job):
            self.assertEqual(job["remaining_tokens"], 100)
            result = self.handler("analysis")(root, job)
            result["tokens"] = 101
            return result
        self.handlers["analysis"] = author
        result = self.advance()
        self.assertEqual(result["tokens_used"], 101)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.advance()["tokens_used"], 101)

    def test_path_escape_rejected(self):
        def source(root, job):
            return {"status": "completed", "outputs": {"../outside": "0" * 64}, "tokens": 0}
        self.handlers["sources"] = source
        self.assertEqual(self.advance()["status"], "blocked")

    def test_explicitly_safe_deterministic_handler_replays_interrupted_work(self):
        invocations = []
        def source(root, job):
            invocations.append(1)
            if len(invocations) == 1:
                raise KeyboardInterrupt("interrupted free local copy")
            return self.handler("sources")(root, job)
        source.replay_safe = True
        self.handlers["sources"] = source
        with self.assertRaises(KeyboardInterrupt):
            self.advance()
        result = self.advance()
        self.assertEqual(result["stage"], "financial_tables")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["replays"], 1)
        self.assertEqual(result["tokens_used"], 0)

    def test_known_deterministic_validation_failure_does_not_retry(self):
        def source(root, job):
            self.calls.append("sources")
            raise ValueError("source hash mismatch")
        source.replay_safe = True
        self.handlers["sources"] = source
        result = self.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("source hash mismatch", result["reason"])
        self.advance()
        self.assertEqual(self.calls, ["sources"])

    def test_model_handler_cannot_opt_into_safe_replay(self):
        self.advance()
        self.advance()
        self.handlers["analysis"].replay_safe = True
        result = self.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("analysis", self.calls)

    def test_lock_prevents_concurrent_advance(self):
        def source(root, job):
            with self.assertRaises(BlockingIOError):
                pipeline.advance(root, self.handlers)
            return self.handler("sources")(root, job)
        self.handlers["sources"] = source
        self.assertEqual(self.advance()["stage"], "financial_tables")

    def test_reserved_artifact_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "reserved"):
            pipeline.create(self.root / "new", {"candidate_artifact": "./job.json"})

    def blocked_author(self, certainty="closed"):
        self.advance(); self.advance()
        def author(root, job):
            return {"status": "blocked", "outputs": {}, "tokens": 7,
                    "execution_certainty": certainty, "reason": "Fictitious closed failure"}
        self.handlers["analysis"] = author
        return self.advance()

    def test_resume_preserves_costs_attempts_revision_and_specification(self):
        before = self.blocked_author()
        result = pipeline.resume(self.root, "Fix fictitious prompt", "a" * 40)
        self.assertEqual(result["status"], "ready")
        for name in ("tokens_used", "attempts", "revision_round", "specification", "budget_tokens"):
            self.assertEqual(result[name], before[name])
        self.assertEqual(result["execution_code_commit"], "a" * 40)
        self.handlers["analysis"] = self.handler("analysis")
        self.assertEqual(self.advance()["tokens_used"], 17)

    def test_resume_is_bounded_to_two_explicit_retries(self):
        self.blocked_author()
        for _ in range(2):
            pipeline.resume(self.root, "Fictitious repair", "a" * 40)
            self.advance()
        with self.assertRaisesRegex(ValueError, "resume limit"):
            pipeline.resume(self.root, "Another repair", "a" * 40)

    def test_resume_rejects_tampering_and_unknown_execution(self):
        self.blocked_author("unknown")
        with self.assertRaisesRegex(ValueError, "closure"):
            pipeline.resume(self.root, "Fictitious repair", "a" * 40)
        (self.root / "sources.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            pipeline.resume(self.root, "Fictitious repair", "a" * 40)

    def test_resume_reconciles_existing_closed_receipts_without_editing_outcome(self):
        before = self.blocked_author("unknown")
        proof = {"execution_certainty": "closed", "tokens": 7,
                 "outputs": {"closed.json": self.artifact("closed.json", "fictional proof")}}
        result = pipeline.resume(self.root, "Verified closed fake execution", "a" * 40,
                                 reconcile=lambda root, job: proof)
        self.assertEqual(result["attempts"], before["attempts"])
        self.assertEqual(result["administrative_history"][-1]["closure"], proof)

    def test_uncertain_status_cannot_resume_even_with_reconciler(self):
        job = self.blocked_author()
        job["status"] = "execution_uncertain"
        (self.root / "job.json").write_text(json.dumps(job))
        with self.assertRaisesRegex(ValueError, "blocked stage"):
            pipeline.resume(self.root, "Fictitious repair", "a" * 40, reconcile=lambda *_: {})

    def test_code_binding_only_before_first_attempt(self):
        initial = pipeline.bind_execution_code(self.root, "a" * 40)
        self.assertEqual(initial["execution_code_commit"], "a" * 40)
        self.advance()
        with self.assertRaisesRegex(ValueError, "unstarted"):
            pipeline.bind_execution_code(self.root, "b" * 40)

    def test_review_rejection_cannot_be_resumed_to_seek_an_approval(self):
        self.through_analysis()
        def review(root, job):
            outcome = self.handler("review")(root, job)
            outcome['status'] = 'revise'
            return outcome
        self.handlers['review'] = review
        for _ in range(5):
            result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        with self.assertRaisesRegex(ValueError, 'substantive review'):
            pipeline.resume(self.root, 'Try another reviewer', 'a' * 40)

    def test_financial_review_block_cannot_be_resumed_as_a_technical_failure(self):
        self.through_analysis()
        def review(root, job):
            outcome = self.handler('review')(root, job)
            outcome.update(status='blocked', execution_certainty='completed', reason='Financial table problem')
            return outcome
        self.handlers['review'] = review
        self.advance()
        with self.assertRaisesRegex(ValueError, 'substantive review'):
            pipeline.resume(self.root, 'Try another reviewer', 'a' * 40)

    def blocked_financial_review(self, location='financial_tables'):
        self.advance()
        def tables(root, job):
            return {'status': 'completed', 'tokens': 0, 'outputs': {
                name: self.artifact(name, f'fictional calculation revision {job["revision_round"]}')
                for name in ('financial-configuration.json', 'financial-analysis.json', 'financial-tables.md')}}
        self.handlers['financial_tables'] = tables
        self.advance(); self.advance()
        def review(root, job):
            name = f'review-r{job["revision_round"]}.json'
            decision = {'verdict': 'revise', 'findings': [{'location': location, 'problem': 'Fictional limitation'}]}
            return {'status': 'blocked', 'tokens': 10, 'session_id': f'reviewer-{job["revision_round"]}',
                    'input_sha256': job['artifacts']['report.md'],
                    'outputs': {name: self.artifact(name, json.dumps(decision))}}
        self.handlers['review'] = review
        return self.advance()

    def test_table_rebuild_archives_originals_without_resetting_job(self):
        before = self.blocked_financial_review()
        result = pipeline.rebuild_tables(self.root, 'Repair fictional table configuration', 'b' * 40)
        self.assertEqual(result['stage'], 'financial_tables')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['revision_round'], 1)
        for name in ('tokens_used', 'attempts', 'specification', 'budget_tokens'):
            self.assertEqual(result[name], before[name])
        self.assertEqual(result['artifacts']['sources.json'], before['artifacts']['sources.json'])
        self.assertIn('review-r0.json', result['artifacts'])
        self.assertEqual(result['revision_input'], {'report.md': before['artifacts']['report.md']})
        for name in ('financial-configuration.json', 'financial-analysis.json', 'financial-tables.md'):
            archive = f'history/financial-r0/{name}'
            self.assertEqual(result['artifacts'][archive], before['artifacts'][name])
            self.assertEqual((self.root / archive).read_bytes(), (self.root / name).read_bytes())
            self.assertNotIn(name, result['artifacts'])
        after_tables = self.advance()
        self.assertEqual(after_tables['stage'], 'analysis')
        self.assertEqual(after_tables['tokens_used'], before['tokens_used'])
        self.assertNotEqual(after_tables['artifacts']['financial-analysis.json'], before['artifacts']['financial-analysis.json'])

    def test_table_rebuild_requires_actual_financial_finding(self):
        with self.assertRaisesRegex(ValueError, 'blocked independent review'):
            pipeline.rebuild_tables(self.root, 'Arbitrary rebuild', 'b' * 40)
        self.blocked_financial_review(location='outlook')
        with self.assertRaisesRegex(ValueError, 'financial_tables finding'):
            pipeline.rebuild_tables(self.root, 'Arbitrary rebuild', 'b' * 40)

    def test_table_rebuild_verifies_current_outputs_and_revision_bound(self):
        before = self.blocked_financial_review()
        (self.root / 'financial-tables.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            pipeline.rebuild_tables(self.root, 'Repair', 'b' * 40)
        before['revision_round'] = before['max_revision_rounds']
        (self.root / 'job.json').write_text(json.dumps(before))
        with self.assertRaisesRegex(ValueError, 'revision limit'):
            pipeline.rebuild_tables(self.root, 'Another repair', 'b' * 40)

    def test_zero_cost_deterministic_failure_can_resume_without_reset(self):
        self.advance()
        def failed_tables(root, job):
            return {'status': 'blocked', 'outputs': {}, 'tokens': 0, 'reason': 'Fictional deterministic failure'}
        failed_tables.replay_safe = True
        self.handlers['financial_tables'] = failed_tables
        before = self.advance()
        result = pipeline.resume(self.root, 'Fix local table writer', 'b' * 40)
        for name in ('attempts', 'artifacts', 'tokens_used', 'revision_round', 'specification'):
            self.assertEqual(result[name], before[name])
        self.assertEqual(result['stage'], 'financial_tables')
        self.assertEqual(result['status'], 'ready')

    def test_deterministic_resume_rejects_stage_without_safe_zero_cost_contract(self):
        self.advance()
        self.handlers['financial_tables'] = lambda root, job: {'status': 'blocked', 'outputs': {}, 'tokens': 0}
        self.advance()
        with self.assertRaisesRegex(ValueError, 'replay-safe'):
            pipeline.resume(self.root, 'Try again', 'b' * 40)

    def test_zero_launch_repair_after_two_model_resumes_preserves_paid_limit(self):
        self.blocked_author()
        pipeline.resume(self.root, 'Repair first closed attempt', 'a' * 40)
        self.advance()
        pipeline.resume(self.root, 'Repair second closed attempt', 'a' * 40)
        self.handlers['analysis'] = lambda root, job: {
            'status': 'blocked', 'outputs': {}, 'tokens': 0,
            'execution_certainty': 'not_started', 'reason': 'Conservative admission forecast'}
        before = self.advance()
        self.assertEqual(len(before['administrative_history']), 2)
        result = pipeline.resume(self.root, 'Fix forecast before launch', 'b' * 40)
        for name in ('tokens_used', 'attempts', 'revision_round', 'artifacts', 'specification'):
            self.assertEqual(result[name], before[name])
        self.assertEqual(len(result['administrative_history']), 3)
        self.handlers['analysis'] = lambda root, job: {
            'status': 'blocked', 'outputs': {}, 'tokens': 7,
            'execution_certainty': 'closed', 'reason': 'Third charged failure'}
        self.advance()
        with self.assertRaisesRegex(ValueError, 'model resume limit'):
            pipeline.resume(self.root, 'Another actual model restart', 'b' * 40)

    def test_resume_history_reason_and_closure_hints_cannot_erase_paid_restarts(self):
        self.blocked_author()
        for _ in range(2):
            pipeline.resume(self.root, 'Technical model restart', 'a' * 40)
            self.advance()
        job = json.loads((self.root/'job.json').read_text())
        for record in job['administrative_history']:
            record.update(reason='Claimed free repair', closure={'execution_certainty': 'not_started'})
        (self.root/'job.json').write_text(json.dumps(job))
        with self.assertRaisesRegex(ValueError, 'model resume limit'):
            pipeline.resume(self.root, 'Claimed free again', 'a' * 40)

    def test_zero_token_claim_with_session_is_still_a_model_restart(self):
        attempt = {'stage': 'analysis', 'usage_recorded': True, 'outcome': {
            'tokens': 0, 'execution_certainty': 'not_started', 'session_id': 'existing-session'}}
        self.assertTrue(pipeline._model_restart(attempt))

    def test_charged_not_started_claim_requires_authenticated_closure(self):
        self.blocked_author(certainty='not_started')
        with self.assertRaisesRegex(ValueError, 'closure'):
            pipeline.resume(self.root, 'Claimed prelaunch repair', 'b' * 40)


if __name__ == "__main__":
    unittest.main()
