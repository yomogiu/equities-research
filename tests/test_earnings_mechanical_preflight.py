"""Fictional source-bound preflight; no providers or private research."""
import copy
import json
import unittest
import test_earnings_batch_review as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_mechanical_preflight as m
from research import earnings_batch_review as b


class MechanicalTests(PassageFixture, unittest.TestCase):
    state=fixtures.BatchTests.state
    pack=fixtures.BatchTests.pack
    items=fixtures.BatchTests.items
    decision=fixtures.BatchTests.decision
    def test_formatting_preserves_facts_and_compiles_source_identity(self):
        financial=copy.deepcopy(self.financial)
        spec=m.formatting(financial,self.bundle)
        self.assertEqual(financial,self.financial)
        rows=b.remediation.repair.row_catalog(financial,self.bundle)
        for key, entry in rows.items():
            self.assertEqual(spec['rows'][key]['label'],entry['row']['metric'])
            self.assertEqual(spec['rows'][key]['dimensions'],entry['row']['dimensions'])
            self.assertEqual(spec['rows'][key]['citations'],['F002'])
        self.assertEqual(spec['basis']['text'],'')

    def test_preflight_batches_unknown_references_without_guessing(self):
        state=self.state();state['artifacts']['analysis']['opening_citations']=['invented']
        state['artifacts']['retrieval']['quotes'][0]['passage_id']='unknown'
        before=copy.deepcopy(state)
        result=m.check(state,self.bundle,self.catalog)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual({x['stage'] for x in result['issues']},{'analysis','retrieval'})
        self.assertEqual(state,before)

    def test_stale_signal_binding_blocks_preflight(self):
        state=self.state();pack=self.pack(state);pack['report_sha256']='stale'
        result=m.check(state,self.bundle,self.catalog,pack)
        self.assertEqual(result['issues'][0]['stage'],'signals')

    def test_pass_without_redundant_evidence_is_explicit_new_policy_only(self):
        items=self.items();review=self.decision(items,items)
        for d in review['decisions']:d['passage_ids']=[]
        with self.assertRaises(ValueError):b.adjudicate(items,set(items),{},review,self.catalog,'receipt')
        accepted,findings=b.adjudicate(items,set(items),{},review,self.catalog,'receipt',m.POLICY)
        self.assertFalse(findings);self.assertEqual(set(accepted),set(items))
        self.assertEqual(accepted['signal-1']['reviewer_passage_ids'],[])
        self.assertIn(self.ids[0],accepted['signal-1']['source_references'])
        review['decisions'][0]['verdict']='revise'
        with self.assertRaises(ValueError):b.adjudicate(items,set(items),{},review,self.catalog,'receipt',m.POLICY)

    def test_unknown_ids_and_empty_reopen_still_rejected(self):
        items=self.items();review=self.decision(items,{'signal-1'})
        review['decisions'][0]['passage_ids']=['invented']
        with self.assertRaises(ValueError):b.adjudicate(items,{'signal-1'},{},review,self.catalog,'x',m.POLICY)
        review=self.decision(items,{'signal-1'})
        review['reopen']=[{'unit_id':'analysis:0','reason':'Contradiction','passage_ids':[]}]
        with self.assertRaises(ValueError):b.adjudicate(items,{'signal-1'},{},review,self.catalog,'x',m.POLICY)

    def test_only_basis_position_retains_claim_acceptance(self):
        items=self.items()
        items['format']['value']['layout']={'version':'compact-financial-v1','fold':[],
            'detail_rows':[],'summaries':[],'basis_position':'before_tables'}
        value=copy.deepcopy(items['format']['value']);value['layout']['basis_position']='after_tables'
        plan={'before_sha256':b.runner.digest(items),'changes':[{'unit_id':'format',
            'before_sha256':b.runner.digest(items['format']['value']),'value':value,'reason':'Move unchanged note'}]}
        updated,pending=b.apply(items,plan,m.POLICY)
        b.validate(updated,self.bundle,self.catalog)
        self.assertEqual(pending,{'format'})
        self.assertIn('signal-1',b.apply(items,plan)[1])
        value['basis']['text']='New substantive claim'
        value['basis']['citations']=['F002']
        self.assertIn('signal-1',b.apply(items,plan,m.POLICY)[1])

    def test_new_prompt_explicitly_certifies_sources_and_batches_material_findings(self):
        items=self.items()
        text=b.prompt(items,items,set(items),{}, {},self.catalog,'Writing',0,self.bundle,m.POLICY)
        self.assertIn('ONLY for a pass',text)
        self.assertIn('every applicable criterion',text)
        self.assertIn('all material defects together',text)
        data=json.loads(text.split('\nBATCH\n')[1])
        self.assertEqual(data['mechanical_checks']['status'],'passed_before_review')

    def test_delta_omits_unrelated_qa_index_but_keeps_verbatim_source_groups(self):
        items=self.items();pending={'signal-1'}
        legacy=json.loads(b.prompt(items,items,pending,{}, {},self.catalog,'Writing',1,self.bundle).split('\nBATCH\n')[1])
        new=json.loads(b.prompt(items,items,pending,{}, {},self.catalog,'Writing',1,self.bundle,m.POLICY).split('\nBATCH\n')[1])
        self.assertEqual(new['sources']['original_passages'],legacy['sources']['original_passages'])
        self.assertEqual(new['rendered_report'],legacy['rendered_report'])
        index=new['sources']['transcript_index']
        turns={t['id'] for t in index['turns']}
        for exchange in index['exchanges']:
            self.assertTrue(set(exchange['turn_ids'])<=turns)
        self.assertLess(len(json.dumps(index)),len(json.dumps(legacy['sources']['transcript_index'])))
