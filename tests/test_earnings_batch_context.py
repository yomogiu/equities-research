"""Fictitious complete-inventory/context-selection transport regressions."""
import copy
import unittest
from unittest.mock import patch
from research import earnings_batch_context as c,earnings_repair_context as t

class ContextTests(unittest.TestCase):
    def fixture(self):
        data={'sources':{'passage_groups':[{'scope_id':'turn-1','rows':[['P1','Whole original call turn']]},{'scope_id':'F1','rows':[['P2','Cited original financial row']]},{'scope_id':'D2','rows':[['P3','Unrelated filing chunk']]}], 'transcript_index':{'turns':[{'id':'turn-1'}]},'unassigned_transcript_spans':[{'text':'Complete call gap'}]},'financial_source_context':{'original':True},'rendered_report':{'text':'Complete rendered report'},'review_units':{'analysis':{'text':'Claim','citations':['F1']}}}
        bundle={'transcript_index':{'turns':[{'id':'turn-1'}]},'financial':{'observations':[{'id':'F1'},{'id':'F2'}]}}
        inventory={'financial_observations':{'rows':[['F1',4],['F2',7]],'omitted_observation_ids':[]},'deferred_document_ids':['D2']}
        return data,bundle,inventory
    def test_complete_call_cited_scopes_inventory_and_report_retained(self):
        data,bundle,inventory=self.fixture();before=copy.deepcopy(data)
        with patch.object(c.financial,'financial_role_payload',return_value=inventory):result=t.expand_context(c.build(data,bundle,{'F1'}))
        self.assertEqual(data,before)
        self.assertEqual(result['report'],data['rendered_report'])
        self.assertEqual(result['sources']['passage_groups'],data['sources']['passage_groups'][:2])
        self.assertEqual(result['sources']['unassigned_transcript_spans'],data['sources']['unassigned_transcript_spans'])
        self.assertEqual(result['financial_source_context'],inventory)
        self.assertEqual(result['sources']['scope_selection']['deferred_financial_scope_ids'],['D2'])
    def test_missing_fact_cannot_be_hidden_by_inventory(self):
        data,bundle,inventory=self.fixture();inventory['financial_observations']['rows'].pop()
        with patch.object(c.financial,'financial_role_payload',return_value=inventory),self.assertRaises(AssertionError):c.build(data,bundle,{'F1'})
