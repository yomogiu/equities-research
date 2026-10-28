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
    def test_recovery_guidance_reaches_author_but_not_independent_reviewer(self):
        self.spec['recovery_guidance']='Fictional recovery marker: verify quarter and cumulative basis.'
        original=self.invoke;seen=[]
        def invoke(directory,prompt,model,effort,bindings,index,**options):
            packet=context.Evidence(index,self.root/'unused.jsonl',_replay=True).artifacts['single_report_packet']
            guided='Fictional recovery marker' in packet['instructions']
            seen.append((bindings['role'],guided))
            return original(directory,prompt,model,effort,bindings,index,**options)
        result=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=invoke)
        self.assertEqual(result['status'],'published',result.get('reason'))
        self.assertEqual(seen,[('single_report_analysis',True),('single_report_review',False)])
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
    def test_scheduled_summary_preserves_explicit_mode(self):
        manifest={'code_commit':'a'*40,'companies':[self.spec],'automation':'ACTIVE'}
        simple.run_batch(self.root/'scheduled',manifest,self.prepare,self.publish,lambda p:None,invoke=self.invoke)
        self.assertEqual(simple.read(self.root/'scheduled/summary.json')['automation'],'ACTIVE')

    def test_source_verifier_shares_budget_and_report_can_continue(self):
        self.spec['fresh_sources']={'fake':True}
        def prepare(root,spec):
            value=spec['_verify_source']({'instructions':'Fictional source decision','_original_files':{str(self.case):simple.storage.sha(self.case)}})
            self.assertEqual(value,{'verdict':'accept'})
            return self.case
        original=self.invoke
        def invoke(directory,prompt,model,effort,bindings,index,**options):
            if directory.name=='0':
                self.assertEqual(options['max_tokens'],220000)
                self.assertTrue(options['direct_input'])
                self.calls.append('source')
                return {'content':{'verdict':'accept'},'receipt':{'session':{'id':'source-only','model_turns':1,'tool_calls':0,'usage':{'totalTokens':123}}}}
            self.assertEqual(options['max_tokens'],1200000-123-(100 if len(self.calls)>=2 else 0))
            return original(directory,prompt,model,effort,bindings,index,**options)
        value=simple.run_company(self.job,self.spec,prepare,self.publish,invoke=invoke)
        self.assertEqual(value['status'],'published',value.get('reason'));self.assertEqual(value['tokens_used'],323)
        self.assertEqual([a['role'] for a in value['attempts']],['source_verification','author','review'])

    def test_source_verifier_rejection_is_charged_without_author_or_retry(self):
        self.spec['fresh_sources']={'fake':True}
        def prepare(root,spec):
            spec['_verify_source']({'instructions':'Fictional decision','_original_files':{str(self.case):simple.storage.sha(self.case)}})
            raise ValueError('Source verifier uncertain')
        calls=[]
        def invoke(*args,**kwargs):
            calls.append(1)
            return {'content':{'verdict':'uncertain'},'receipt':{'session':{'id':'source-only','model_turns':1,'tool_calls':0,'usage':{'totalTokens':321}}}}
        result=simple.run_company(self.job,self.spec,prepare,self.publish,invoke=invoke)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['tokens_used'],321)
        simple.run_company(self.job,self.spec,prepare,self.publish,invoke=invoke)
        self.assertEqual(len(calls),1)

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

    def test_published_html_has_accepted_status_without_changing_reviewed_body(self):
        state=self.run_one();self.assertEqual(state['status'],'published',state.get('reason'))
        candidate=(self.job/'candidate-0.md').read_text()
        page=(self.job/'report.html').read_text()
        self.assertIn('<header>Accepted after independent review</header>',page)
        self.assertEqual(page.replace('<header>Accepted after independent review</header>','<header>Draft — review pending</header>'),simple.finance.preview_html(candidate))

    def citation_invoke(self, author_citation=None, correction_citation=None, review_citation=None):
        original=self.invoke
        def invoke(*args,**kwargs):
            response=original(*args,**kwargs);value=response['content'];role=self.calls[-1]
            bundle=simple.evidence.load_bundle(self.job/'sources/manifest.json')
            table=bundle['packet_inventory']['tables'][0]
            choice={'author':author_citation,'correction':correction_citation,'review':review_citation}.get(role)
            citation={'table':table['id'],'document':table['source_id']}.get(choice,choice)
            if choice is not None:
                target=value['criteria']['source_accuracy'] if role=='review' else value['analysis']['sections']['demand']
                target['citations']=[citation]
                if choice=='table':target['citations'].append(table['source_id'])
            simple.save(Path(args[0])/'output.json',value)
            return response
        return invoke

    def test_exact_table_alias_publishes_without_correction_and_preserves_raw_receipt(self):
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=self.citation_invoke(author_citation='table'))
        self.assertEqual(state['status'],'published',state.get('reason'));self.assertEqual(self.calls,['author','review'])
        raw=simple.read(self.job/'author.json');resolved=simple.read(self.job/'author-resolved.json')
        self.assertEqual(raw,simple.read(self.job/'roles/0/output.json'))
        self.assertTrue(raw['analysis']['sections']['demand']['citations'][0].startswith('T-'))
        self.assertEqual(len(resolved['analysis']['sections']['demand']['citations']),1)
        self.assertEqual(raw['financial_selection'],resolved['financial_selection'])
        self.assertEqual(raw['analysis']['sections']['demand']['text'],resolved['analysis']['sections']['demand']['text'])
        trace=simple.read(self.job/'author-citations.json')
        self.assertEqual(len(trace['changes']),1)
        self.assertEqual(trace['raw_sha256'],simple.storage.sha(self.job/'author.json'))
        self.assertEqual(trace['resolved_sha256'],simple.storage.sha(self.job/'author-resolved.json'))

    def test_unknown_author_citation_uses_one_correction_then_independent_review(self):
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,
            invoke=self.citation_invoke(author_citation='T-fictional-unknown',correction_citation='document'))
        self.assertEqual(state['status'],'published',state.get('reason'));self.assertEqual(self.calls,['author','correction','review'])
        self.assertEqual(state['corrections'],1);self.assertEqual(state['tokens_used'],300)
        payload=simple.read(self.job/'contexts/1/artifacts.json')['single_report_packet']
        self.assertIn('T-fictional-unknown',payload['validation_error'])
        self.assertIn('documents',simple.read(self.job/'contexts/2/artifacts.json')['single_report_packet'])
        self.assertEqual(simple.read(self.job/'author.json')['analysis']['sections']['demand']['citations'],['T-fictional-unknown'])

    def test_unknown_citation_after_correction_stays_terminal_and_charged(self):
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,
            invoke=self.citation_invoke(author_citation='T-fictional-unknown',correction_citation='T-fictional-unknown'))
        self.assertEqual(state['status'],'failed');self.assertEqual(self.calls,['author','correction'])
        self.assertEqual(state['tokens_used'],200);self.assertEqual(state['corrections'],1)
        self.assertFalse((self.job/'report.html').exists());self.assertEqual(self.run_one(),state)
        self.assertEqual(len(self.calls),2)

    def test_malformed_author_citation_gets_correction_without_laundering_invalid_input(self):
        original=self.invoke
        def invoke(*args,**kwargs):
            response=original(*args,**kwargs);value=response['content']
            if self.calls[-1]=='author':value['analysis']['sections']['demand']['citations']=[{'invalid':'Fictional malformed reference'}]
            if self.calls[-1]=='correction':value['analysis']['sections']['demand']['citations']=['D001']
            return response
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=invoke)
        self.assertEqual(state['status'],'published',state.get('reason'));self.assertEqual(self.calls,['author','correction','review'])
        self.assertIsInstance(simple.read(self.job/'author-resolved.json')['analysis']['sections']['demand']['citations'][0],dict)

    def test_review_table_alias_is_bound_to_raw_and_resolved_review(self):
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=self.citation_invoke(review_citation='table'))
        self.assertEqual(state['status'],'published',state.get('reason'))
        self.assertEqual(state['review_sha256'],simple.storage.sha(self.job/'review-resolved.json'))
        self.assertNotEqual(simple.read(self.job/'review.json'),simple.read(self.job/'review-resolved.json'))
        self.assertEqual(len(simple.read(self.job/'review-citations.json')['changes']),1)

    def test_unknown_reviewer_citation_never_authorizes_publication(self):
        state=simple.run_company(self.job,self.spec,self.prepare,self.publish,invoke=self.citation_invoke(review_citation='T-fictional-unknown'))
        self.assertEqual(state['status'],'failed');self.assertEqual(self.calls,['author','review'])
        self.assertFalse((self.job/'publication.json').exists())

    def test_citation_resolution_does_not_rewrite_fact_selection_or_unsupplied_sources(self):
        self.run_one();bundle=simple.evidence.load_bundle(self.job/'sources/manifest.json');table=bundle['packet_inventory']['tables'][0]
        value={'table_id':table['id'],'fact_ids':[table['id']],'text':'Fictional original text.',
               'citations':[table['id'],table['source_id'],'T-fictional-unknown']}
        original=copy.deepcopy(value)
        resolved,trace=simple.resolve_citations(value,bundle,{table['source_id']})
        self.assertEqual(value,original);self.assertEqual(resolved['table_id'],value['table_id']);self.assertEqual(resolved['fact_ids'],value['fact_ids'])
        self.assertEqual(resolved['citations'],[table['source_id'],'T-fictional-unknown']);self.assertEqual(len(trace),1)
        unavailable,trace=simple.resolve_citations(value,bundle,set())
        self.assertEqual(unavailable,value);self.assertEqual(trace,[])
