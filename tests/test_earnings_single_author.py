"""Fictional combined author and independent review; no live model calls."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_single_author as single,earnings_sequential as core
from research import earnings_sequential_stages as stages,earnings_file_context as context
from research import earnings_financial_selection as selection,earnings_financial_analysis_report as finance
from research import earnings_compact_evidence as evidence,earnings_sequential_financial_contract as contract
from test_earnings_compact_evidence import fixture

class SingleAuthorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);case,_,_=fixture(self.root)
        writing=self.root/'writing.md';writing.write_text('Fictional concise evidence-based report.')
        self.job=self.root/'job';core.create(self.job,{'case_path':str(case),'writing_standard':str(writing),'financial_analysis':finance.configuration('2040-01-01','2040-03-31')})
        core.bind_execution_code(self.job,'a'*40,single_author=True)
        self.calls=[];self.skip=False;self.revise=False;self.fabricate=False;self.same_session=False
        self.runner=patch.object(stages.runner,'run_role',side_effect=self.fake);self.runner.start();self.addCleanup(self.runner.stop)
        self.delivery=patch.object(context,'delivered_entries',side_effect=lambda root,entries:entries);self.delivery.start();self.addCleanup(self.delivery.stop)
    def fake(self,directory,prompt,model,effort,bindings,index,**settings):
        self.calls.append(bindings['role']);directory.mkdir(parents=True)
        reader=context.Evidence(index,directory/'retrieval.jsonl')
        self.assertTrue(prompt.endswith(reader._report_packet()))
        packet=reader.artifacts['single_report_packet']
        self.assertNotIn('review_findings',packet);self.assertEqual(settings['max_tool_calls'],1);self.assertTrue(settings['direct_input'])
        exchange=reader.index['exchange_ids'][0];ref=[exchange]
        if bindings['role']=='single_report_analysis':
            self.assertNotIn('candidate',packet)
            fid=next(o['id'] for o in stages.read(self.job/'sources/financial.json')['observations'] if o['concept']=='us-gaap:Revenues')
            picked={'rows':[{'metric':'revenue','label':'Fictional revenue','basis':'GAAP','fact_ids':[fid],'citations':['D001'],'definition':'Fictional consolidated revenue.'}],
                    'gaps':[{'metric':m,'reason':'Fictional source gap.','citations':['D001']} for m in sorted(selection.REQUIRED-{'revenue'})],'notes':[]}
            if self.fabricate:picked['rows'][0]['value']='999'
            paragraph={'text':'Fictional evidence has limitations.','citations':ref}
            narrative={'title':'Fictional report','opening':paragraph,'sections':{k:copy.deepcopy(paragraph) for k in stages.SECTIONS},
                       'qa':[{'exchange_id':exchange,'question':'Fictional question?','answer':'Fictional answer.','assessment':'Fictional uncertainty.','citations':ref}], 'next_tests':[paragraph]}
            value={'financial_selection':picked,'analysis':narrative}
        else:
            self.assertIn('candidate',packet);self.assertEqual(packet['financial_verification']['verification'],'reproduced')
            value={'verdict':'pass','criteria':{k:{'status':'pass','evidence':'Fictional source supports report.','citations':ref} for k in stages.CRITERIA},
                   'questions':{k:{'status':'disclosed_gap','evidence':'Fictional limitation stated.','gap':'Fictional gap.','citations':ref} for k in stages.questions.QUESTIONS},'findings':[]}
            if self.revise:
                value['verdict']='revise';value['criteria']['reasoning']['status']='fail'
                value['findings']=[{'location':'cash','problem':'Fictional omission.','fix':'Explain the fictional constraint.','citations':ref}]
        return {'content':value,'receipt':{'session':{'id':'fake-'+str(1 if self.same_session else len(self.calls)),'tool_calls':0,'model_turns':2 if self.skip else 1,'usage':{'totalTokens':100}}}}
    def advance(self):return core.advance(self.job,stages.handlers())
    def test_combined_author_reproduces_tables_then_fresh_review_and_publication(self):
        self.assertEqual(self.advance()['stage'],'analysis')
        raw=(self.job/'sources/financial.json').read_bytes()
        self.assertEqual(self.advance()['stage'],'review')
        self.assertEqual((self.job/'sources/financial.json').read_bytes(),raw)
        self.assertEqual(contract.build(self.job)['verification'],'reproduced')
        self.assertEqual(self.advance()['stage'],'publication')
        result=self.advance();self.assertEqual(result['status'],'completed',result.get('reason'))
        self.assertEqual(result['tokens_used'],200)
        self.assertEqual([a['stage'] for a in result['attempts']],['sources','analysis','review','publication'])
        self.assertEqual(self.calls,['single_report_analysis','single_report_review'])
    def test_review_failure_stops_without_extra_author_or_review(self):
        self.revise=True
        for _ in range(3):result=self.advance()
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['tokens_used'],200)
        self.assertIn('review-r0.json',result['artifacts']);self.advance();self.assertEqual(len(self.calls),2)
        self.assertFalse((self.job/'publication.json').exists())
    def test_invalid_selection_preserves_cost_and_never_reaches_review(self):
        self.fabricate=True;self.advance();result=self.advance()
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['tokens_used'],100)
        self.assertEqual(len(self.calls),1)
    def test_multiturn_response_cannot_be_accepted(self):
        self.skip=True;self.advance();result=self.advance()
        self.assertEqual(result['status'],'blocked');self.assertIn('one direct model output',result['reason'])
    def test_reviewer_cannot_reuse_author_session(self):
        self.same_session=True
        for _ in range(3):result=self.advance()
        self.assertEqual(result['status'],'blocked');self.assertIn('fresh independent',result['reason'])
    def test_packet_retains_every_fact_and_complete_document_text(self):
        self.advance();bundle=evidence.load_bundle(self.job/'sources/manifest.json');p=single.packet(bundle)
        ids=[fid for row in p['financial_inventory']['facts'] for fid in row[0]]
        self.assertEqual(set(ids),{x['id'] for x in bundle['financial']['observations']})
        for identifier,doc,start,end in p['document_scopes']:
            original=next(x for x in bundle['documents']['chunks'] if x['id']==identifier)
            text=Path(original['path']).read_bytes().decode()
            record=p['documents'][doc]
            self.assertEqual(record['text'][start-record['start']:end-record['start']],text[start:end])
        self.assertEqual(p['transcript'],Path(bundle['manifest']['transcript_path']).read_bytes().decode())

    def test_direct_request_binds_full_prompt_and_disables_tools(self):
        self.advance();job=stages.read(self.job/'job.json')
        index,body=single._context(self.job,job,'analysis')
        bindings={'workflow':single.VERSION,'role':'single_report_analysis'}
        request=stages.runner.request(self.root/'role','Instructions\n'+body,'gpt-6.1-sol','medium',bindings,index,1200000,1,1800,direct_input=True)
        self.assertEqual(request['tool_names'],[]);self.assertIsNone(request['execution_policy'])
        with self.assertRaisesRegex(ValueError,'Complete fixed packet'):
            stages.runner.request(self.root/'role','truncated','gpt-6.1-sol','medium',bindings,index,1200000,1,1800,direct_input=True)
        with self.assertRaisesRegex(ValueError,'single-report contract'):
            stages.runner.request(self.root/'role',body,'gpt-6.1-sol','medium',{'role':'other'},index,1200000,1,1800,direct_input=True)
