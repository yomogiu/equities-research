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
