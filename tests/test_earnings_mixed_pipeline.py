"""Synthetic validation tests; no provider calls."""
import copy
from pathlib import Path
import tempfile
import unittest
from test_earnings_compact_evidence import fixture
from research import earnings_compact_evidence as evidence
from research import earnings_mixed_pipeline as pipe
from research import earnings_experiment as base


class MixedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.case,_,_=fixture(self.root)
        self.bundle=evidence.load_bundle(evidence.prepare(self.case,self.root/'evidence'))
        self.financial={'rows':[{'label':'Fictitious metric '+str(i),'fact_ids':['F002']} for i in range(4)],'context':[],'gaps':[]}
        self.report={'title':'Fictional earnings','opening':'Revenue was reported.','opening_citations':['F001'],
            'findings':[{'heading':'Fictional finding','text':'Fictitious operational evidence.','citations':['D001'],'quotes':[]} for _ in range(4)],
            'next_tests':[{'text':'Check fictional demand.','citations':['D001']}],'scope':'Fictitious historical test only.'}

    def test_period_value_and_units_are_copied_not_model_supplied(self):
        pipe.validate_output('financial',self.financial,self.bundle)
        cells=pipe.fact_cells(self.financial,self.bundle)
        self.assertEqual(cells[0]['values'][0]['value'],'12')
        self.assertEqual(cells[0]['values'][0]['period'],'2040-01-01 to 2040-03-31')
        self.assertEqual(cells[0]['values'][0]['unit'],'iso4217:USD')
        self.financial['rows'][0]['fact_ids']=['F999']
        with self.assertRaises(ValueError):pipe.validate_output('financial',self.financial,self.bundle)

    def test_proposed_financial_fact_is_not_accepted_as_table_value(self):
        proposed=next(o['id'] for o in self.bundle['financial']['observations'] if o['status']=='proposed')
        self.financial['rows'][0]['fact_ids']=[proposed]
        with self.assertRaisesRegex(ValueError,'Unresolved'):pipe.validate_output('financial',self.financial,self.bundle)

    def test_missing_exchange_and_fake_quote_are_rejected(self):
        retrieval={'selected_document_ids':['D001'],'exchange_coverage':[], 'document_findings':[], 'quotes':[]}
        with self.assertRaisesRegex(ValueError,'Every Q&A'):pipe.validate_output('retrieval',retrieval,self.bundle)
        self.report['findings'][0]['quotes']=[{'scope_id':'D001','text':'Fabricated quote'}]
        with self.assertRaisesRegex(ValueError,'differs'):pipe.validate_output('analysis',self.report,self.bundle)

    def test_review_cannot_pass_with_unresolved_writing_or_source_failure(self):
        out={'verdict':'pass','criteria':{c:{'status':'pass','evidence':'Fictitious checked evidence D001'} for c in pipe.CRITERIA},'findings':[]}
        pipe.validate_output('review',out,self.bundle)
        out['criteria']['concise_specific_writing']['status']='fail'
        with self.assertRaises(ValueError):pipe.validate_output('review',out,self.bundle)
        out['criteria']['concise_specific_writing']['status']='pass'
        out['findings']=[{'target':'analysis','passage':'Fictional finding','reason':'Redundant','required_change':'Delete','citations':['D001']}]
        with self.assertRaises(ValueError):pipe.validate_output('review',out,self.bundle)

    def test_review_binding_changes_with_same_prose_different_financial_selection(self):
        deps={'financial':self.financial,'retrieval':{},'analysis':self.report}
        before=pipe.review_binding(deps)
        deps['financial']['rows'][0]['fact_ids']=['F003']
        self.assertNotEqual(before,pipe.review_binding(deps))

    def test_all_observations_included_even_unmapped_and_full_documents(self):
        facts=pipe.all_facts(self.bundle)
        self.assertEqual(len(facts['rows']),len(self.bundle['financial']['observations']))
        chunks=pipe.full_documents(self.bundle)
        self.assertEqual(''.join(x['text'] for x in chunks),(self.root/'filing.txt').read_bytes().decode())
        self.assertIn('Fictitious caveat.',pipe.transcript(self.bundle)['text'])

    def test_html_is_escaped_and_evidence_linked(self):
        self.report['title']='<script>attack</script>'
        pipe.render(self.root,self.report,self.financial,self.bundle,'DRAFT')
        html=(self.root/'report.html').read_text()
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('id="e-F002"',html)
        self.assertIn('id="e-D001"',html)
        self.assertIn('DRAFT',html)

    def test_protocol_detects_input_tampering(self):
        writing=self.root/'writing.txt';writing.write_text('Fictional concise standard')
        output=self.root/'run';pipe.freeze(self.case,output,writing)
        pipe.verify_protocol(output)
        writing.write_text('Changed')
        with self.assertRaisesRegex(ValueError,'Frozen input changed'):pipe.verify_protocol(output)

if __name__=='__main__':unittest.main()
