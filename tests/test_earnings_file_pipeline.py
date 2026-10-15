"""Fictional file/Markdown pipeline and real receipt verification; no providers."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
import test_earnings_signals as fixture_signals
from research import earnings_file_context as c, earnings_file_pipeline as p
from research import earnings_file_runner as r, earnings_markdown as md
from research import earnings_mixed_runner as base, earnings_signals as signals


class FilePipelineTests(PassageFixture,unittest.TestCase):
    pack=fixture_signals.SignalTests.pack

    def assemble(self):return c.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/'context',artifacts={'report':self.report},markdown='# Fictional report\n',metadata={'batch_sha256':'fake'})

    def drain(self,reader,method,name):
        at=0
        while True:
            value=getattr(reader,method)(name,at)
            if value['next_start'] is None:return
            at=value['next_start']

    def test_context_pages_hashes_unknown_ids_and_search_coverage(self):
        index=self.assemble();log=self.root/'read.jsonl';reader=c.Evidence(index,log)
        preview=reader.search('Fictitious');self.assertTrue(preview)
        entries=c.audit(index,log);self.assertFalse(c.complete_ranges(entries,'scope','id'))
        self.drain(reader,'scope','D001');self.assertIn('D001',c.complete_ranges(c.audit(index,log),'scope','id'))
        with self.assertRaises(ValueError):reader.scope('../../secrets')
        with self.assertRaises(ValueError):reader.file('../../secrets')
        with self.assertRaises(ValueError):reader.scope('D001',0,100000)
        (self.root/'context/sources.json').write_text('{}')
        with self.assertRaises(ValueError):c.Evidence(index,log)

    def test_call_batch_deduplicates_exact_text_and_projects_only_call_scopes(self):
        index=self.assemble();reader=c.Evidence(index,self.root/'batch.jsonl')
        text=(Path(index).parent/'transcript.md').read_bytes().decode()
        packet=reader.call_batch()
        self.assertEqual(packet.count(text),1)
        self.assertNotIn('"text":',packet.split('## Original transcript characters')[0])
        entries=c.audit(index,self.root/'batch.jsonl')
        scopes,files=c.inspected_call(index,entries)
        self.assertEqual(files,{'transcript.md'})
        self.assertTrue(set(reader.index['exchange_ids'])<=scopes)
        self.assertTrue(set(reader.index['section_ids'])<=scopes)
        self.assertNotIn('D001',scopes)
        self.assertFalse(c.inspected_call(index,[{**entries[0],'end':1}])[0])
        # Separate pages compose the original source, never overlapping Q&A dumps.
        log=self.root/'pages.jsonl';reader=c.Evidence(index,log)
        for start in range(0,len(text),100):reader.call_batch(start,100)
        self.assertEqual(c.inspected_call(index,c.audit(index,log))[0],scopes)
        with self.assertRaises(ValueError):reader.call_batch(0,48001)

    def test_call_batch_respects_runtime_character_boundary_and_continuation(self):
        index=self.assemble();reader=c.Evidence(index,self.root/'bounded-call.jsonl')
        text='Fictional Unicode \u00a0 passage.\r\n'*4000
        with patch.object(reader,'_call_scopes',return_value=(text,{})):
            first=reader._call_batch(0,48000);meta=json.loads(first.splitlines()[2])
            self.assertLessEqual(len(first),60000)
            self.assertEqual(meta['next_start'],meta['end'])
            second=reader._call_batch(meta['next_start'],48000)
            self.assertIn(text[meta['end']:min(len(text),meta['end']+48000)],second)
            self.assertLessEqual(len(second),60000)

    def test_unprinted_call_batch_does_not_gain_delivery_coverage(self):
        index=self.assemble();job=self.root/'packet-job';job.mkdir()
        base.save(job/'request.json',{'context_index':str(index)})
        reader=c.Evidence(index,job/'retrieval.jsonl');packet=reader.call_batch()
        identifier='a'*24;(job/'tool-output').mkdir();path=job/'tool-output'/(identifier+'.txt')
        def deliver(text):
            path.write_text(text)
            record={'id':identifier,'retrieval_start':0,'retrieval_end':1,'limit':None,
                    'delivered_bytes':len(text.encode()),'unsupported':False,'sha256':base.sha(path),
                    'original_bytes':len(text.encode()),'complete':True}
            (job/'delivery.jsonl').write_text(json.dumps(record)+'\n')
            return c.delivered_entries(job,c.audit(index,job/'retrieval.jsonl'))
        self.assertEqual(deliver('Loaded into kernel; not printed'),[])
        self.assertEqual(len(deliver(packet)),1)
        self.assertEqual(deliver(packet[:100]),[])

    def test_filing_batch_replays_and_requires_visible_complete_delivery(self):
        index=self.assemble();job=self.root/'filing-batch-job';job.mkdir()
        base.save(job/'request.json',{'context_index':str(index)})
        reader=c.Evidence(index,job/'retrieval.jsonl');packet=reader.filing_batch('Fictitious revenue growth')
        entries=c.audit(index,job/'retrieval.jsonl');ids=entries[0]['ids']
        self.assertTrue(ids);self.assertTrue(all(i.startswith('D') for i in ids))
        self.assertLessEqual(len(packet),60000)
        for identifier in ids:
            self.assertIn('\n'.join(s['text'] for s in reader.records[identifier]['spans']),packet)
        identifier='b'*24;(job/'tool-output').mkdir();path=job/'tool-output'/(identifier+'.txt')
        def deliver(text):
            path.write_bytes(text.encode())
            record={'id':identifier,'retrieval_start':0,'retrieval_end':1,'limit':None,'delivered_bytes':len(text.encode()),
                    'unsupported':False,'sha256':base.sha(path),'original_bytes':len(text.encode()),'complete':True}
            (job/'delivery.jsonl').write_text(json.dumps(record)+'\n')
            return c.delivered_entries(job,c.audit(index,job/'retrieval.jsonl'))
        self.assertEqual(deliver('Loaded; not printed'),[])
        self.assertEqual(deliver(packet[:100]),[])
        self.assertEqual(len(deliver(packet)),1)
        proof=p.coverage('financial',index,job,{'selected_document_ids':ids},self.catalog,{})
        self.assertEqual(set(proof['source_ids']),set(ids))
        deliver(packet[:100])
        with self.assertRaises(ValueError):p.coverage('financial',index,job,{'selected_document_ids':ids},self.catalog,{})
        with self.assertRaises(ValueError):reader.filing_batch('revenue',5)

    def test_filing_batch_ranks_terms_and_marks_unknown_query_fallback(self):
        index=self.assemble();reader=c.Evidence(index,self.root/'unused.jsonl')
        def record(text,start=0,document='fictional-filing'):
            return {'spans':[{'text':text,'path':'/fictional/'+document,'sha256':'fake','document_id':document,'start':start,'end':start+len(text)}]}
        reader.records={'D001':record('Other material.'),'D002':record('Revenue increased; cash improved.'),
                        'D003':record('Debt commitments.',document='fictional-second')}
        packet,ids=reader._filing_batch('What happened to revenue and cash this quarter?',1)
        self.assertEqual(ids,['D002']);self.assertFalse(json.loads(packet.splitlines()[1])['fallback_used'])
        packet,ids=reader._filing_batch('unmatchedxyz unmatchedabc',2)
        self.assertEqual(ids,['D002','D003']);self.assertTrue(json.loads(packet.splitlines()[1])['fallback_used'])
        self.assertIn('verify_relevance',packet)
        self.assertNotIn('turn-',ids)

    def test_filing_batch_omits_duplicate_overlap_and_transcript_sources(self):
        index=self.assemble();reader=c.Evidence(index,self.root/'unused.jsonl')
        def record(text,start=0):
            return {'spans':[{'text':text,'path':'/fictional/filing','sha256':'fake','document_id':'fictional-filing','start':start,'end':start+len(text)}]}
        reader.records={'D001':record('Cash revenue grew.'),'D002':record('Cash revenue grew.',100),
                        'D003':record('Revenue and debt.',5),'D004':record('Debt outlook.',200),
                        'turn-fake':record('Cash revenue debt commitments.')}
        _,ids=reader._filing_batch('cash revenue debt',4)
        self.assertEqual(ids,['D001','D004'])
        reader.records={}
        packet,ids=reader._filing_batch('cash revenue',4)
        self.assertEqual(ids,[]);self.assertIn('source-access gap',packet)

    def test_active_job_binds_log_and_context_without_model_paths(self):
        index=self.assemble();job=(self.root/'active-job').resolve();job.mkdir()
        base.save(job/'request.json',{'version':r.VERSION,'job_path':str(job),'context_index':str(index)})
        with patch.object(Path,'cwd',return_value=job):
            reader=c.Evidence.for_job();reader.filing_batch('revenue cash')
            other=c.Evidence(index,self.root/'wrong'/'retrieval.jsonl')
            self.assertEqual(other.log,job/'retrieval.jsonl')
            self.assertTrue((job/'retrieval.jsonl').exists());self.assertFalse((self.root/'wrong').exists())
            before=(job/'retrieval.jsonl').read_bytes();c.audit(index,job/'retrieval.jsonl')
            self.assertEqual((job/'retrieval.jsonl').read_bytes(),before)
            with self.assertRaises(FileNotFoundError):c.Evidence(self.root/'nonexistent/index.json',job/'retrieval.jsonl')
        with patch.object(Path,'cwd',return_value=self.root):
            with self.assertRaises(FileNotFoundError):c.Evidence.for_job()

    def test_original_source_and_forged_retrieval_receipt_rejected(self):
        index=self.assemble();log=self.root/'read.jsonl';reader=c.Evidence(index,log);reader.scope('D001')
        events=[json.loads(x) for x in log.read_text().splitlines()];events[0]['result_sha256']='forged';log.write_text(json.dumps(events[0])+'\n')
        with self.assertRaises(ValueError):c.audit(index,log)
        (self.root/'filing.txt').write_text('changed original')
        with self.assertRaises(ValueError):c.Evidence(index,self.root/'other.jsonl')

    def test_partial_source_page_does_not_satisfy_inspection(self):
        index=self.assemble();log=self.root/'read.jsonl';reader=c.Evidence(index,log);reader.scope('D001',0,1)
        self.assertNotIn('D001',c.complete_ranges(c.audit(index,log),'scope','id'))

    def test_financial_lookup_is_paged_and_replayable(self):
        index=self.assemble();log=self.root/'facts-read.jsonl';reader=c.Evidence(index,log)
        metrics=reader.financial_metrics(limit=1)
        self.assertLessEqual(len(metrics['metrics']),1)
        financial=base.read(Path(index).parent/'financial.json')
        query=financial['observations'][0]['concept']
        facts=reader.financial_facts(query,limit=1)
        self.assertEqual(len(facts['facts']),1)
        self.assertNotIn('support',facts['facts'][0])
        self.assertEqual(facts['facts'][0]['id'],financial['observations'][0]['id'])
        self.assertEqual(len(c.audit(index,log)),2)
        with self.assertRaises(ValueError):reader.financial_facts(query,limit=100)

    def test_markdown_uses_exact_compiler_numbers_and_escapes_html(self):
        state={'artifacts':{'financial':self.financial,'retrieval':self.retrieval,'analysis':copy.deepcopy(self.report)},'format':{'rows':{},'basis':{'text':'','citations':[]}}}
        state['artifacts']['analysis']['findings'][0]['text']='<script>danger()</script>'
        state['artifacts']['analysis']['findings'][0]['heading']='Fictional | finding'
        text=md.report(state,self.bundle,self.catalog,self.pack(state));page=md.render(text,status='accepted')
        self.assertIn('F002',text);self.assertIn('<table>',page);self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
        for line in text.splitlines():
            if line.startswith('| '):self.assertIn(' |',line)
        with self.assertRaises(ValueError):md.render('# Bad\n\nMissing [^D999]\n')
        target=self.root/'render.md';md.write(target,state,self.bundle,self.catalog,self.pack(state),status='accepted')
        self.assertEqual((self.root/'render.html').read_text(),md.render(target.read_text(),status='accepted'))

    def fake_run(self,job,prompt,model,effort,bindings,index,*,max_tokens,max_tool_calls,timeout=1200,resume=None):
        job=Path(job);q=r.request(job,prompt,model,effort,bindings,index,max_tokens,max_tool_calls,timeout,resume=resume);job.mkdir(parents=True)
        base.save(job/'request.json',q);(job/'prompt.md').write_text(prompt)
        if resume:base.save(job/'resume.json',resume)
        reader=c.Evidence(index,job/'retrieval.jsonl')
        if resume:reader.restore()
        reader.inventory()
        # Fake provider inspects the complete frozen inventory using the same API.
        for identifier in reader.index['source_ids']:self.drain(reader,'scope',identifier)
        if 'report.md' in reader.index['files']:self.drain(reader,'file','report.md')
        self.drain(reader,'file','transcript.md')
        role=bindings['role'];meta=base.read(Path(index).parent/'metadata.json');art=base.read(Path(index).parent/'artifacts.json')
        if role=='financial':content=copy.deepcopy(self.financial)
        elif role=='retrieval':content=copy.deepcopy(self.retrieval)
        elif role=='analysis':content=copy.deepcopy(self.report)
        elif role=='signal_author':content=self.pack(art['state'])
        elif role=='correction':
            items=art['units'];key='analysis:0';value=copy.deepcopy(items[key]['value']);value['text']='Fictional corrected distinct finding '+str(meta['round'])
            content={'before_sha256':meta['before_sha256'],'changes':[{'unit_id':key,'before_sha256':base.digest(items[key]['value']),'value':value,'reason':'Fictional supported correction'}]}
        else:
            fail=getattr(self,'fail_reviews',0)>0
            if fail:self.fail_reviews-=1
            content={'batch_sha256':meta['batch_sha256'],'report_sha256':meta['report_sha256'],
                'report_criteria':{k:{'status':'pass','evidence':'Fictional exact source check'} for k in p.legacy.CRITERIA},
                'signal_criteria':{k:{'status':'pass','evidence':'Fictional exact source check'} for k in signals.CRITERIA},
                'decisions':[], 'reopen':[]}
            for key in art['units']:
                failed=fail and key=='analysis:0'
                content['decisions'].append({'unit_id':key,'verdict':'revise' if failed else 'pass','reason':'Fictional source check',
                    'passage_ids':[self.ids[0]],'review_kind':'factual' if failed else 'none','editorial_repairs':[]})
        response='# Role result\n\n```json\n'+json.dumps(content)+'\n```\n';(job/'response.md').write_text(response)
        sid='fictional-'+job.name;launch={'id':'fictional-launch','request_sha256':base.digest(q)};base.save(job/'launch.json',launch)
        for name in ('runtime-start.json','runtime-finish.json'):base.save(job/name,{'launch_id':launch['id'],'session_id':sid,'model':model,'effort':effort,'oauth':True})
        base.save(job/'wire.json',[{'model':model,'effort':effort,'tools':['ipython']}]*2)
        usage={'input':10,'output':10,'cacheRead':0,'cacheWrite':0,'totalTokens':20}
        assistant={'role':'assistant','provider':'openai-codex','api':'openai-codex-responses','model':model,'usage':usage}
        messages=[{'role':'user','content':prompt},{**assistant,'stopReason':'toolUse','content':[{'type':'toolCall','id':'inspect','name':'ipython','arguments':{'code':'# Fictional complete API inspection'}}]},
                  {'role':'toolResult','toolName':'ipython','toolCallId':'inspect','content':[{'type':'text','text':'Fictional source inspection'}],'details':{'delivery_id':'a'*24},'isError':False},
                  {**assistant,'stopReason':'stop','content':[{'type':'text','text':response}]}]
        events=[{'type':'session','id':sid,'cwd':str(job)},{'type':'model_change','provider':'openai-codex','modelId':model},{'type':'thinking_level_change','thinkingLevel':effort}]+[{'type':'message','message':x} for x in messages]
        (job/'sessions').mkdir();(job/'sessions/fake.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
        import hashlib
        delivered={k:messages[2][k] for k in ('content','details','isError')}
        raw=json.dumps(delivered,ensure_ascii=False,separators=(',',':')).encode()
        (job/'tool-output').mkdir();(job/'tool-output'/('a'*24+'.txt')).write_text('Fictional source inspection')
        entry={'id':'a'*24,'tool_call_id':'inspect','sha256':base.sha(job/'tool-output'/('a'*24+'.txt')),'original_bytes':len('Fictional source inspection'.encode()),'unsupported':False,'complete':True,'retrieval_start':0,'retrieval_end':len((job/'retrieval.jsonl').read_text().splitlines()),'delivered_sha256':hashlib.sha256(raw).hexdigest(),'delivered_bytes':len(raw),'limit':8192}
        (job/'delivery.jsonl').write_text(json.dumps(entry)+'\n')
        execution={'request_sha256':base.digest(q),'launch_sha256':base.sha(job/'launch.json'),'exit_code':0,'status':'completed',
            'session':r.receipt(job,q),'artifact_sha256':{n:base.sha(job/n) for n in ('runtime-start.json','runtime-finish.json','wire.json','response.md','retrieval.jsonl','delivery.jsonl')}}
        base.save(job/'execution.json',execution);base.save(job/'output.json',{'request_sha256':base.digest(q),'execution_sha256':base.sha(job/'execution.json'),'content':content})
        return r.verify_job(job)

    def lifecycle(self,fail=0):
        root=self.root/'pipeline';writing=self.root/'writing.md';writing.write_text('Fictional concise source-grounded prose.\n')
        p.initialize(self.casepath,root,writing,financial_mode="model-original-selector-v1");self.fail_reviews=fail
        with patch.object(r,'run_role',side_effect=self.fake_run) as run:
            pending=p.advance(root,False);self.assertEqual(pending['status'],'pending');run.assert_not_called()
            for _ in range(12):
                before=run.call_count;value=p.advance(root,True);self.assertLessEqual(run.call_count-before,1)
                if value['status'] in ('accepted','blocked'):break
            else:self.fail('Lifecycle did not stop')
        return root,value

    def test_compiled_financial_draft_requires_no_financial_model_call(self):
        from research import earnings_financial_outline
        root=self.root/'compiled-pipeline';writing=self.root/'writing.md';writing.write_text('Fictional source-bound writing.\n')
        p.initialize(self.casepath,root,writing)
        with patch.object(earnings_financial_outline,'artifact',return_value=copy.deepcopy(self.financial)), patch.object(r,'run_role',side_effect=self.fake_run) as run:
            value=p.advance(root,True)
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[4]['role'],'retrieval')
        self.assertFalse((root/'jobs/financial').exists())
        self.assertEqual(base.read(root/'financial-compiled.json')['status'],'source_bound_draft_pending_independent_review')
        self.assertEqual(value['status'],'pending')

    def test_complete_lifecycle_short_markdown_prompts_replay_and_mutation(self):
        root,value=self.lifecycle();self.assertEqual(value['status'],'accepted');self.assertEqual(value['tokens'],200)
        self.assertEqual(p.verify(root),value)
        for prompt in root.glob('jobs/*/prompt.md'):
            self.assertLess(len(prompt.read_text()),12000);self.assertNotIn('<html',prompt.read_text());self.assertNotIn(self.text,prompt.read_text())
        self.assertTrue((root/'report.md').exists());self.assertEqual((root/'report.html').read_text(),md.render((root/'report.md').read_text(),status='accepted'))
        with patch.object(r,'run_role') as launch:p.verify(root);launch.assert_not_called()
        (root/'jobs/review-0/retrieval.jsonl').write_text('')
        with self.assertRaises(ValueError):p.verify(root)

    def test_two_round_limit_and_edited_candidate_needs_fresh_review(self):
        root,value=self.lifecycle(fail=1);self.assertEqual(value['status'],'accepted');self.assertEqual(value['correction_rounds'],1)
        self.assertIn('fictional-review-1',value['session_ids']);self.assertIn('fictional-correction-1',value['session_ids'])
        self.assertNotEqual(base.read(root/'contexts/review-0/metadata.json')['batch_sha256'],base.read(root/'contexts/review-1/metadata.json')['batch_sha256'])

    def test_exhausted_two_rounds_do_not_get_a_third_author(self):
        root,value=self.lifecycle(fail=3);self.assertEqual(value['status'],'blocked');self.assertEqual(value['correction_rounds'],2)
        self.assertFalse((root/'jobs/correction-3').exists());self.assertFalse((root/'report.html').exists())

    def test_review_needs_full_markdown_and_call_not_search_previews(self):
        index=self.assemble();job=self.root/'job';job.mkdir();reader=c.Evidence(index,job/'retrieval.jsonl');reader.search('Fictitious')
        with self.assertRaises((ValueError,FileNotFoundError)):p.coverage('review',index,job,{},self.catalog,{})

    def test_markdown_result_requires_one_metadata_block(self):
        self.assertEqual(r.parse('# Role result\n```json\n{"x":1}\n```\n'),{'x':1})
        for text in ('{"x":1}','```json\n{"x":1}\n```\n```json\n{"x":2}\n```'):
            with self.assertRaises(ValueError):r.parse(text)



    def test_explicit_cap_removal_preserves_prior_usage_role_limits_and_review(self):
        case=base.read(self.casepath);case.update(issuer_id='fictional:issuer',period='FICTIONAL-Q1');self.casepath.write_text(json.dumps(case))
        writing=self.root/'authorized-writing.md';writing.write_text('Fictional source-grounded writing.')
        proof=self.root/'prior-usage.json';proof.write_text(json.dumps({'cumulative_company_tokens':1800000}))
        approval=self.root/'approval.json';approval.write_text(json.dumps({'scope':'one_company_trial','user_request':'Lift the cap and retry this fictional company.',
          'issuer_id':case['issuer_id'],'period':case['period'],'max_tokens':None,'prior_usage_tokens':1800000,'prior_usage_proof':{'path':str(proof),'sha256':base.sha(proof)}}))
        root=self.root/'uncapped';p.initialize(self.casepath,root,writing,max_tokens=None,budget_authorization=approval,financial_mode='model-original-selector-v1')
        with patch.object(r,'run_role',side_effect=self.fake_run) as run:
            for _ in range(8):
                value=p.advance(root,True)
                if value.get('status')=='accepted':break
            self.assertEqual(value['status'],'accepted');self.assertEqual(value['tokens'],1800200)
            self.assertEqual(run.call_count,5)
            self.assertTrue(all(x.kwargs['max_tokens']==1200000 for x in run.call_args_list))
        proof.write_text(json.dumps({'cumulative_company_tokens':0}))
        with self.assertRaisesRegex(ValueError,'Prior usage proof changed'):p.verify(root)

    def test_cap_removal_requires_explicit_matching_authorization(self):
        writing=self.root/'budget-writing.md';writing.write_text('Fictional writing.')
        with self.assertRaises(ValueError):p.initialize(self.casepath,self.root/'no-approval',writing,max_tokens=None)
        proof=self.root/'proof.json';proof.write_text(json.dumps({'cumulative_company_tokens':30}))
        approval=self.root/'bad-approval.json';approval.write_text(json.dumps({'scope':'one_company_trial','user_request':'Remove cap','max_tokens':None,
            'issuer_id':'another-issuer','period':self.case.get('period'),'prior_usage_tokens':30,'prior_usage_proof':{'path':str(proof),'sha256':base.sha(proof)}}))
        with self.assertRaisesRegex(ValueError,'issuer or period'):p.initialize(self.casepath,self.root/'wrong-scope',writing,max_tokens=None,budget_authorization=approval)

    def test_large_structured_sources_load_into_kernel_without_raw_html_output(self):
        index=self.assemble();log=self.root/'structured.jsonl';reader=c.Evidence(index,log)
        for name,attribute in [('financial.json','financial_data'),('transcript-index.json','transcript_index')]:
            with self.assertRaisesRegex(ValueError,'kernel memory'):reader.file(name)
            summary=reader.load_structured(name)
            self.assertEqual(getattr(reader,attribute),base.read(Path(index).parent/name))
            self.assertLess(len(json.dumps(summary)),1500)
            self.assertNotIn('observations',summary)
        self.assertEqual(len(c.audit(index,log)),2)
        self.assertFalse(c.complete_ranges(c.audit(index,log),'scope','id'))
        self.assertIn('facts',reader.financial_facts('revenue'))

if __name__=='__main__':unittest.main()
