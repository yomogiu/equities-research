"""Fictional end-to-end contracts for the finite runner; no paid calls."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_simple_runner as simple
from research import earnings_file_context as context,earnings_report_contract as contract
from test_earnings_compact_evidence import fixture

class SimpleRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        case,_,_=fixture(self.root);v=simple.read(case);v['financial_inventory_version']='packet-financial-inventory-v1';simple.save(case,v);self.case=case
        self.writing=self.root/'writing.md';self.writing.write_text('Fictional concise report.')
        self.spec={'job_key':'fake','symbol':'FAKE','writing_standard':str(self.writing),'financial_analysis':simple.finance.configuration('2040-01-01','2040-03-31')}
        self.job=self.root/'job';self.calls=[];self.finding=None;self.repeated=False;self.invalid=False
        self.patcher=patch.object(context,'delivered_entries',side_effect=lambda root,entries:entries);self.patcher.start();self.addCleanup(self.patcher.stop)
    def prepare(self,root,spec):return self.case
    def publish(self,root,state):return {'verification':'exact_remote_bytes','candidate_sha256':simple.storage.sha(root/'report.md'),'html_sha256':simple.storage.sha(root/'report.html')}
    def invoke(self,directory,prompt,model,effort,bindings,index,**options):
        role='review' if bindings['role']=='single_report_review' else 'correction' if bindings['revision'] else 'author'
        self.calls.append(role);packet=context.Evidence(index,self.root/'unused.jsonl',_replay=True).artifacts['single_report_packet']
        self.assertTrue(prompt.endswith(json.dumps(packet,ensure_ascii=False,separators=(',',':'))))
        self.assertTrue(options['direct_input']);self.assertEqual(options['max_tool_calls'],1)
        b=simple.evidence.load_bundle(directory.parents[1]/'sources/manifest.json');exchange=b['transcript_index']['exchanges'][0]['id'];refs=[exchange]
        if role=='author':
            fid=next(o['id'] for o in b['financial']['observations'] if o['concept']=='us-gaap:Revenues')
            paragraph={'text':'Fictional evidence has limitations.','citations':refs}
            analysis={'title':'Fictional report','opening':paragraph,'sections':{k:copy.deepcopy(paragraph) for k in simple.content.SECTIONS},
                'qa':[{'exchange_id':exchange,'question':'Fictional question?','answer':'Fictional answer.','assessment':'Fictional uncertainty.','citations':refs}], 'next_tests':[paragraph]}
            analysis['report_support']={'coverage':{k:{'status':'unavailable','report_excerpt':paragraph['text'],'reason':'Fictional missing input.','citations':refs} for k in contract.COVERAGE},'valuation':{'rows':[],'gap':'Fictional price unavailable.','citations':refs}}
            selected={'rows':[{'metric':'revenue','label':'Fictional revenue','basis':'GAAP','fact_ids':[fid],'citations':['D001'],'definition':'Fictional consolidated revenue.'}],
                'gaps':[{'metric':m,'reason':'Fictional source gap.','citations':['D001']} for m in sorted(simple.selection.REQUIRED-{'revenue'})],'notes':[]}
            value={'financial_selection':selected,'analysis':analysis}
            if self.invalid:value['financial_selection']['rows'][0]['fact_ids']=['Fmissing']
        elif role=='correction':
            self.assertEqual((model,effort),('gpt-6-luna','max'))
            value=copy.deepcopy(packet['current_output'])
            if self.invalid:
                value['financial_selection']['rows'][0]['fact_ids']=[next(o['id'] for o in b['financial']['observations'] if o['concept']=='us-gaap:Revenues')]
            else:
                value['analysis']['sections']['cash']['text']='Corrected fictional evidence has limitations.'
                for k,(location,_) in contract.COVERAGE.items():
                    if location=='cash':value['analysis']['report_support']['coverage'][k]['report_excerpt']=value['analysis']['sections']['cash']['text']
        else:
            value={'verdict':'pass','criteria':{k:{'status':'pass','evidence':'Fictional support verified.','citations':refs} for k in simple.content.CRITERIA},
                'questions':{k:{'status':'disclosed_gap','evidence':'Fictional limitation disclosed.','gap':'Fictional gap.','citations':refs} for k in simple.questions.QUESTIONS},'findings':[]}
            if self.finding and (self.calls.count('review')==1 or self.repeated):
                value['findings']=[{'severity':self.finding,'location':'cash','problem':'Fictional error.','fix':'Correct the fictional explanation.','citations':refs}]
                value['verdict']='revise' if self.finding=='blocking' else 'pass'
                value['criteria']['reasoning']['status']='fail' if self.finding=='blocking' else 'warning'
        directory.mkdir(parents=True,exist_ok=True);simple.save(directory/'output.json',value)
        return {'content':value,'receipt':{'session':{'id':'session-'+str(len(self.calls)),'model_turns':1,'tool_calls':0,'usage':{'totalTokens':100}}}}
    def run_one(self):return simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=self.invoke)
    def test_publish_without_correction_and_terminal_reentry(self):
        value=self.run_one();self.assertEqual(value['status'],'published',value.get('reason'));self.assertEqual(value['tokens_used'],200)
        self.assertEqual(self.calls,['author','review']);self.assertEqual(self.run_one(),value);self.assertEqual(len(self.calls),2)
    def test_advisory_does_not_trigger_correction(self):
        self.finding='advisory';value=self.run_one();self.assertEqual(value['status'],'published',value.get('reason'));self.assertEqual(len(self.calls),2)
    def test_one_correction_and_fresh_check(self):
        self.finding='blocking';value=self.run_one();self.assertEqual(value['status'],'published',value.get('reason'))
        self.assertEqual(self.calls,['author','review','correction','review']);self.assertEqual(value['tokens_used'],400)
    def test_repeated_failure_terminates(self):
        self.finding='blocking';self.repeated=True;value=self.run_one();self.assertEqual(value['status'],'failed');self.assertEqual(len(self.calls),4)
        self.assertFalse((self.job/'report.html').exists());self.run_one();self.assertEqual(len(self.calls),4)
    def test_invalid_selection_gets_same_single_correction_allowance(self):
        self.invalid=True;value=self.run_one();self.assertEqual(value['status'],'published',value.get('reason'));self.assertEqual(self.calls,['author','correction','review'])
    def test_unknown_execution_is_terminal_and_not_free(self):
        def failed(*a,**k):raise RuntimeError('Fictional transport failure')
        value=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=failed)
        self.assertEqual(value['status'],'failed');self.assertFalse(value['usage_complete']);self.assertIsNone(value['attempts'][0]['tokens'])
        self.run_one();self.assertFalse(self.calls)
    def test_interruption_does_not_repeat_a_paid_stage(self):
        self.job.mkdir();simple.save(self.job/'result.json',{'specification':self.spec,'status':'running','tokens_used':100})
        value=self.run_one();self.assertEqual(value['status'],'failed');self.assertFalse(self.calls)
    def test_changed_source_blocks_publication(self):
        original=self.invoke
        def tamper(*a,**k):
            result=original(*a,**k)
            if self.calls[-1]=='review':
                b=simple.evidence.load_bundle(self.job/'sources/manifest.json');Path(b['manifest']['sources'][0]['path']).write_text('Changed fictional evidence')
            return result
        value=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=tamper)
        self.assertEqual(value['status'],'failed');self.assertFalse((self.job/'publication.json').exists())
    def test_publication_requires_exact_receipt(self):
        value=simple.run_company(self.job,self.spec,self.prepare,lambda *a:{},invoke=self.invoke)
        self.assertEqual(value['status'],'failed');self.assertNotIn('publication',value)
    def test_failed_company_does_not_stop_ordered_batch(self):
        specs=[{**self.spec,'job_key':str(i)} for i in range(3)]
        def prepare(root,spec):
            if spec['job_key']=='1':raise ValueError('Fictional missing packet')
            return self.case
        result=simple.run_batch(self.root/'batch',{'code_commit':'a'*40,'companies':specs},prepare,self.publish,lambda p:None,invoke=self.invoke)
        self.assertEqual([r['status'] for r in result],['published','failed','published'])
        self.assertEqual(len(self.calls),4)
        simple.run_batch(self.root/'batch',{'code_commit':'a'*40,'companies':specs},prepare,self.publish,lambda p:None,invoke=self.invoke)
        self.assertEqual(len(self.calls),4)
    def test_no_old_control_modules_imported(self):
        import subprocess,sys
        code="import sys;from research import earnings_simple_runner;assert not any(n.startswith(('research.earnings_sequential','research.earnings_single_author')) for n in sys.modules)"
        subprocess.run([sys.executable,'-c',code],check=True)
    def test_style_cannot_be_a_failed_criterion(self):
        self.run_one();review=simple.read(self.job/'review.json');review['criteria']['concise_writing']['status']='fail'
        with self.assertRaisesRegex(ValueError,'Style alone'):simple.validate_review(review,set(simple.content.cited(review)))

    def test_simple_context_accepts_funded_large_packet_without_changing_legacy_limit(self):
        from types import SimpleNamespace
        root=self.root/'context';root.mkdir()
        reader=SimpleNamespace(root=root,artifacts={'single_report_packet':{'version':simple.VERSION,'text':'x'*950000}})
        simple.save(root/'metadata.json',{'single_report_version':simple.VERSION})
        self.assertGreater(len(context.Evidence._report_packet(reader)),900000)
        reader.artifacts['single_report_packet']['text']='x'*1050000
        with self.assertRaisesRegex(ValueError,'context bound'):context.Evidence._report_packet(reader)
        reader.artifacts['single_report_packet'].update(version='single-author-report-v2',text='x'*950000)
        simple.save(root/'metadata.json',{'single_report_version':'single-author-report-v2'})
        with self.assertRaisesRegex(ValueError,'context bound'):context.Evidence._report_packet(reader)

    def test_fixed_budget_still_stops_before_any_call(self):
        with patch.object(simple,'BUDGET',100):value=self.run_one()
        self.assertEqual(value['status'],'failed');self.assertFalse(self.calls);self.assertEqual(value['tokens_used'],0)

    def test_call_index_compaction_preserves_every_field_and_value(self):
        self.run_one();bundle=simple.evidence.load_bundle(self.job/'sources/manifest.json')
        original=simple.content.packet(bundle)['transcript_index'];compact=simple.packet(bundle)['transcript_index']
        for name,rows in original.items():
            value=compact[name]
            rebuilt=[dict(zip(value['columns'],row)) for row in value['rows']] if isinstance(value,dict) else value
            self.assertEqual(rows,rebuilt)

    def test_serialization_expansion_is_budgeted_before_launch(self):
        self.writing.write_text('"'*300000)
        value=self.run_one()
        self.assertEqual(value['status'],'failed');self.assertFalse(self.calls)
        self.assertIn('serialized context',value['reason'])

    def test_correction_can_clarify_financial_note_for_narrative_finding(self):
        self.finding='blocking';original=self.invoke
        def clarify(*args,**kwargs):
            result=original(*args,**kwargs)
            if self.calls[-1]=='correction':
                result['content']['financial_selection']['notes']=[{'text':'Fictional unit clarification.','citations':['D001']}]
            return result
        value=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=clarify)
        self.assertEqual(value['status'],'published',value.get('reason'));self.assertEqual(len(self.calls),4)

    def test_revision_sources_actual_changes_without_resending_old_claims(self):
        self.run_one();bundle=simple.evidence.load_bundle(self.job/'sources/manifest.json');original=simple.packet(bundle)
        value=simple.read(self.job/'author.json');after=copy.deepcopy(value)
        after['financial_selection']['notes']=[{'text':'Fictional revised basis.','citations':['D001']}]
        review=simple.read(self.job/'review.json');review['findings']=[{'severity':'blocking','location':'cash','citations':[]}]
        result=simple.revision_packet(bundle,original,after,review,before=value)
        self.assertEqual([row['id'] for row in result['original_support']],['D001'])
        self.assertNotIn('financial_inventory',result)
        review['findings'][0]['location']='financial_tables'
        correction=simple.revision_packet(bundle,original,value,review,True)
        self.assertEqual(correction['original_support'],[])
        self.assertEqual(correction['financial_inventory'],original['financial_inventory'])
        self.assertEqual(simple.changed_claims({'a':1,'b':2},{'a':1}),{'b':{'removed':2}})

    def test_changed_text_keeps_unchanged_citations_for_independent_check(self):
        before={'sections':{'cash':{'text':'Old fictional claim.','citations':['D002']}}}
        after=copy.deepcopy(before);after['sections']['cash']['text']='New fictional claim.'
        self.assertEqual(simple.changed_claims(before,after),after)
