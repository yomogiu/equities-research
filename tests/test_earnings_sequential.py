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
        with self.assertRaisesRegex(ValueError, "blocked editorial"):
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


if __name__ == "__main__":
    unittest.main()
