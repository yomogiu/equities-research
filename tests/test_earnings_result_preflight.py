"""Fictional completed-role failure prevention. No provider calls."""
import copy
import json
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_file_context as context
from research import earnings_file_pipeline as pipeline
from research import earnings_file_runner as runner


class ResultPreflightTests(PassageFixture, unittest.TestCase):
    def test_invalid_authored_checkpoint_does_not_abort_result_preflight(self):
        reader=self.reader()
        for draft,pending in [({},[]),({'large':'x'*13000},['unfinished'])]:
            result=reader.checkpoint(draft,pending)
            self.assertFalse(result['saved']);self.assertFalse(result['acceptance'])
            self.assertFalse((reader.log.parent/'checkpoints').exists())
        feedback=reader.validate_result(self.retrieval)
        self.assertFalse(feedback['valid'])
        self.assertIn('delivery log',feedback['error'])

    def test_checkpoint_integrity_errors_remain_blocking(self):
        reader=self.reader()
        with patch('research.earnings_file_checkpoint.save',side_effect=ValueError('Original source changed')):
            with self.assertRaisesRegex(ValueError,'Original source changed'):
                reader.checkpoint({},['unfinished'])

    def test_source_reads_leave_a_call_for_result_validation(self):
        index=self.reader().root/'index.json'
        plan=runner.work_plan('retrieval',index)
        original_reads=plan['call_pages']+plan['filing_checks']+1  # metadata
        self.assertGreater(plan['work_tool_limit'],original_reads)
        self.assertLessEqual(plan['work_tool_limit'],8)

    def test_handoff_metadata_does_not_consume_validation_slot(self):
        index=self.reader().root/'index.json'
        for role in ('analysis','review','correction','signal_author'):
            plan=runner.work_plan(role,index)
            self.assertEqual(plan['metadata_allowance'],0)
            self.assertEqual(plan['validation_checks'],1)

    def reader(self):
        index=context.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/'context',artifacts={},metadata={})
        job=self.root/'job'
        request=runner.request(job,'Fictional retrieval','gpt-6-luna','max',{'role':'retrieval'},index,200000,48,1200)
        job.mkdir()
        (job/'request.json').write_text(json.dumps(request))
        (job/'retrieval.jsonl').write_text('')
        return context.Evidence(index,job/'retrieval.jsonl',_replay=True)

    def test_missing_document_selection_gets_actionable_feedback(self):
        reader=self.reader();draft=copy.deepcopy(self.retrieval);del draft['selected_document_ids']
        result=reader.validate_result(draft)
        self.assertFalse(result['valid']);self.assertFalse(result['acceptance'])
        self.assertIn('document selection',result['error'])
        self.assertFalse((reader.log.parent/'output.json').exists())

    def test_mistyped_exchange_is_rejected_without_editing_draft(self):
        reader=self.reader();draft=copy.deepcopy(self.retrieval)
        draft['exchange_coverage'][0]['exchange_id']+='typo';before=copy.deepcopy(draft)
        result=reader.validate_result(draft)
        self.assertFalse(result['valid']);self.assertIn('coverage entry',result['error'])
        self.assertEqual(draft,before)

    def test_schema_valid_draft_still_requires_delivered_originals(self):
        reader=self.reader();result=reader.validate_result(self.retrieval)
        self.assertFalse(result['valid']);self.assertFalse(result['acceptance'])
        self.assertIn('delivery log',result['error'])

    def test_success_never_grants_acceptance_or_writes_output(self):
        reader=self.reader();draft=copy.deepcopy(self.retrieval)
        with patch.object(pipeline,'coverage',return_value={'status':'passed'}) as check:
            result=reader.validate_result(draft)
        check.assert_called_once();self.assertTrue(result['valid']);self.assertFalse(result['acceptance'])
        self.assertEqual(draft,self.retrieval);self.assertFalse((reader.log.parent/'output.json').exists())

    def test_multiple_exchange_errors_return_exact_ids_without_mutation(self):
        reader=self.reader();draft=copy.deepcopy(self.retrieval)
        draft['exchange_coverage']=[{'exchange_id':'wrong-one'},{'exchange_id':'wrong-two'}]
        before=copy.deepcopy(draft)
        feedback=reader.validate_result(draft)
        self.assertEqual(feedback['invalid_exchange_ids'],['wrong-one','wrong-two'])
        self.assertEqual(feedback['valid_exchange_ids'],sorted(reader.index['exchange_ids']))
        self.assertFalse(feedback['acceptance']);self.assertEqual(draft,before)

    def test_fresh_launch_initializes_empty_audit_and_cannot_relaunch(self):
        reader=self.reader();job=self.root/'fresh-launch'
        def launch(*args,**kwargs):
            self.assertEqual((job/'retrieval.jsonl').read_text(),'')
            from unittest.mock import Mock
            process=Mock();process.wait.return_value=1
            return process
        from pathlib import Path
        with patch.object(runner.runtime,'_runtime_paths',return_value=(Path('/fake/node'),Path('/fake/sdk'))), patch.object(runner.subprocess,'Popen',side_effect=launch) as process:
            with self.assertRaisesRegex(RuntimeError,'no retry'):
                runner.run_role(job,'Fictional role','gpt-6-luna','max',{'role':'retrieval'},reader.root/'index.json',max_tokens=200000)
            with self.assertRaisesRegex(RuntimeError,'cannot be launched again'):
                runner.run_role(job,'Fictional role','gpt-6-luna','max',{'role':'retrieval'},reader.root/'index.json',max_tokens=200000)
            self.assertEqual(process.call_count,1)

    def test_timeout_is_explicit_and_never_authorizes_retry(self):
        reader=self.reader();job=self.root/'timeout-launch'
        from pathlib import Path
        from unittest.mock import Mock
        process=Mock();process.pid=123;process.returncode=-15
        process.wait.side_effect=[runner.subprocess.TimeoutExpired('fictional-worker',1),-15]
        with patch.object(runner.runtime,'_runtime_paths',return_value=(Path('/fake/node'),Path('/fake/sdk'))), patch.object(runner.subprocess,'Popen',return_value=process), patch.object(runner.os,'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError,'no retry'):
                runner.run_role(job,'Fictional role','gpt-6-luna','max',{'role':'retrieval'},reader.root/'index.json',max_tokens=200000)
            kill.assert_called_once_with(123,runner.signal.SIGTERM)
        receipt=json.loads((job/'execution.json').read_text())
        self.assertEqual(receipt['failure_kind'],'worker_timeout')
        self.assertEqual(receipt['execution_certainty'],'unknown')
        self.assertFalse(receipt['retry_authorized'])
