"""Fictional combined author and independent review; no live model calls."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_single_author as single,earnings_sequential as core
from research import earnings_sequential_stages as stages,earnings_file_context as context
from research import earnings_financial_selection as selection,earnings_financial_analysis_report as finance
from research import earnings_compact_evidence as evidence,earnings_sequential_financial_contract as contract
from test_earnings_compact_evidence import fixture
from research import earnings_report_contract as report_contract

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
        if bindings['role']=='single_report_analysis' and bindings['revision']:
            self.assertEqual((model,effort),('gpt-6-luna','max'))
            self.assertNotIn('financial_inventory',packet)
            value={'patches':{k:{'edits':[{'old_text':row['text'][:20],'new_text':'Corrected fictional constraint. '+row['text'][:20]}],'citations':ref} for k,row in packet['current_components'].items()}}
        elif bindings['role']=='single_report_analysis':
            self.assertNotIn('candidate',packet)
            fid=next(o['id'] for o in stages.read(self.job/'sources/financial.json')['observations'] if o['concept']=='us-gaap:Revenues')
            picked={'rows':[{'metric':'revenue','label':'Fictional revenue','basis':'GAAP','fact_ids':[fid],'citations':['D001'],'definition':'Fictional consolidated revenue.'}],
                    'gaps':[{'metric':m,'reason':'Fictional source gap.','citations':['D001']} for m in sorted(selection.REQUIRED-{'revenue'})],'notes':[]}
            if getattr(self,'pick_table',False):
                table=stages.read(self.job/'sources/packet_inventory.json')['tables'][0]
                picked['reported_tables']=[{'table_id':table['id'],'row_ids':['R1'],'section':'earnings'}]
            if self.fabricate:picked['rows'][0]['value']='999'
            paragraph={'text':'Fictional evidence has limitations.','citations':ref}
            narrative={'title':'Fictional report','opening':paragraph,'sections':{k:copy.deepcopy(paragraph) for k in stages.SECTIONS},
                       'qa':[{'exchange_id':exchange,'question':'Fictional question?','answer':'Fictional answer.','assessment':'Fictional uncertainty.','citations':ref}], 'next_tests':[paragraph]}
            narrative['report_support']={'coverage':{k:{'status':'unavailable','report_excerpt':paragraph['text'],'reason':'Fictional missing disclosure.','citations':ref} for k in report_contract.COVERAGE},'valuation':{'rows':[],'gap':'Fictional dated price unavailable.','citations':ref}}
            value={'financial_selection':picked,'analysis':narrative}
        else:
            self.assertIn('candidate',packet);self.assertEqual(packet['financial_verification']['verification'],'reproduced')
            value={'verdict':'pass','criteria':{k:{'status':'pass','evidence':'Fictional source supports report.','citations':ref} for k in stages.CRITERIA},
                   'questions':{k:{'status':'disclosed_gap','evidence':'Fictional limitation stated.','gap':'Fictional gap.','citations':ref} for k in stages.questions.QUESTIONS},'findings':[]}
            if self.revise:
                value['verdict']='revise';value['criteria']['reasoning']['status']='fail'
                value['findings']=[{'location':'cash','problem':'Fictional omission.','fix':'Explain the fictional constraint.','citations':ref}]
            if self.revise and getattr(self,'table_finding',False):
                value['findings'].append({'location':'financial_tables','problem':'Original grid has empty columns.','fix':'Compact the original source columns.','citations':['D001']})
        self.last_response = {'content':value,'receipt':{'session':{'id':'fake-'+str(1 if self.same_session else len(self.calls)),'tool_calls':0,'model_turns':2 if self.skip else 1,'usage':{'totalTokens':100}}}}
        stages.write(directory/'output.json',value)
        return self.last_response
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
    def test_review_failure_stops_without_allowance(self):
        job=stages.read(self.job/'job.json');job['max_revision_rounds']=0;core._write(self.job,job)
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

    def test_full_transcript_scope_covers_header_outside_call_boundaries(self):
        self.advance();bundle=evidence.load_bundle(self.job/'sources/manifest.json')
        text=Path(bundle['manifest']['transcript_path']).read_bytes().decode()
        record=evidence.source_slices(self.job/'sources/manifest.json',['transcript-source'])[0]
        self.assertEqual(record['spans'][0]['text'],text)
        index,body=single._context(self.job,stages.read(self.job/'job.json'),'analysis')
        self.assertIn('Never put human labels',json.loads(body)['citation_rules'])

    def test_shared_contract_is_the_same_for_author_and_reviewer(self):
        self.advance();self.advance()
        job=stages.read(self.job/'job.json')
        packets=[json.loads(single._context(self.job,job,role)[1]) for role in ('analysis','review')]
        self.assertEqual(packets[0]['shared_report_requirements'],packets[1]['shared_report_requirements'])
        self.assertIn('coverage_map',packets[1])

    def test_coverage_must_exist_in_reader_report(self):
        self.advance();self.advance();a=stages.read(self.job/'analysis-r0.json')
        a['report_support']['coverage']['funding_needs']['report_excerpt']='An assertion absent from the reader report'
        with self.assertRaisesRegex(ValueError,'actual report text'):
            report_contract.validate(a['report_support'],a,self.job/'sources/manifest.json')

    def test_renderer_owns_one_legend_without_internal_artifact_notes(self):
        self.advance();self.advance();text=(self.job/'report.md').read_text()
        self.assertEqual(text.count('Δ / change: absolute change'),1)
        self.assertNotIn('financial-analysis.json',text)
        self.assertNotIn('No substitute period or zero',text)

    def test_recompile_saved_author_preserves_tokens_and_uses_no_new_author(self):
        self.advance()
        with patch.object(report_contract,'validate',side_effect=ValueError('Fictional compiler failure')):
            stopped=self.advance()
        self.assertEqual(stopped['tokens_used'],100)
        old_attempt=copy.deepcopy(stopped['attempts'][-1])
        with patch.object(single.runner,'verify_job',return_value=self.last_response):
            recovered=core.adopt_single_author(self.job,'Fix the fictional compiler','b'*40,single.recover)
        self.assertEqual(recovered['tokens_used'],100);self.assertEqual(recovered['stage'],'review')
        self.assertEqual(recovered['attempts'][-2],old_attempt)
        self.assertEqual(self.calls,['single_report_analysis'])
        final=self.advance();self.assertEqual(final['stage'],'publication');self.assertEqual(final['tokens_used'],200)

    def test_automatic_correction_reuses_tables_and_reaches_publication(self):
        self.revise=True
        self.advance();self.advance()
        frozen={n:(self.job/n).read_bytes() for n in ('sources/financial.json','financial-selection-r0.json','financial-analysis.json','financial-tables.md')}
        original=stages.read(self.job/'analysis-r0.json')
        job=self.advance();self.assertEqual((job['stage'],job['revision_round']),('analysis',1))
        job=self.advance();self.assertEqual(job['stage'],'review',job.get('reason'))
        corrected=stages.read(self.job/'analysis-r1.json')
        self.assertEqual(corrected['sections']['earnings'],original['sections']['earnings'])
        self.assertEqual(corrected['report_support']['valuation'],original['report_support']['valuation'])
        self.revise=False;job=self.advance();self.assertEqual(job['stage'],'publication',job.get('reason'))
        job=self.advance();self.assertEqual(job['status'],'completed',job.get('reason'));self.assertEqual(job['tokens_used'],400)
        for name,data in frozen.items():self.assertEqual((self.job/name).read_bytes(),data)
        self.assertEqual(self.calls,['single_report_analysis','single_report_review','single_report_analysis','single_report_review'])

    def test_repeated_finding_stops_automatic_loop(self):
        self.revise=True
        for _ in range(5):job=self.advance()
        self.assertEqual(job['status'],'blocked',job.get('reason'))
        self.assertIn('Repeated unchanged',job['reason']);self.assertEqual(job['tokens_used'],400)
        self.assertFalse((self.job/'publication.json').exists())

    def test_migration_keeps_old_attempt_cost_and_budget(self):
        job=stages.read(self.job/'job.json');job['max_revision_rounds']=0;core._write(self.job,job)
        self.revise=True
        for _ in range(3):job=self.advance()
        before=copy.deepcopy(job)
        job=core.repair_single_author(self.job,'Authorized fictional repair','b'*40)
        self.assertEqual(job['attempts'],before['attempts']);self.assertEqual(job['budget_tokens'],before['budget_tokens'])
        self.assertEqual(job['tokens_used'],200);self.assertEqual(job['revision_round'],1)
        job=self.advance();self.assertEqual(job['stage'],'review',job.get('reason'))
        self.revise=False;self.advance();self.assertEqual(self.advance()['status'],'completed')

    def test_layout_upgrade_reuses_extract_and_selection_then_corrects_and_reviews(self):
        case_path=self.root/'case.json';case=stages.read(case_path)
        case['financial_inventory_version']='packet-financial-inventory-v1';case_path.write_text(json.dumps(case))
        job=stages.read(self.job/'job.json');job['max_revision_rounds']=0;core._write(self.job,job)
        self.pick_table=True;self.table_finding=True;self.revise=True
        original_build=finance.analysis.build
        def old_layout(*args,**kwargs):
            value=original_build(*args,**kwargs);value.pop('reported_table_layout',None);return value
        with patch.object(finance.analysis,'build',side_effect=old_layout):
            for _ in range(3):job=self.advance()
        self.assertEqual(job['status'],'blocked');before=copy.deepcopy(job)
        financial_before=stages.read(self.job/'financial-analysis.json')
        raw=(self.job/'sources/financial.json').read_bytes();picked=(self.job/'financial-selection-r0.json').read_bytes()
        job=core.repair_single_author(self.job,'Fix source-table presentation and reviewed prose','b'*40)
        self.assertEqual(job['tokens_used'],before['tokens_used']);self.assertEqual(job['attempts'],before['attempts'])
        after=stages.read(self.job/'financial-analysis.json');after.pop('reported_table_layout')
        self.assertEqual(after,financial_before)
        self.assertEqual(self.advance()['stage'],'review')
        self.revise=False;self.assertEqual(self.advance()['stage'],'publication')
        self.assertEqual(self.advance()['status'],'completed')
        self.assertEqual((self.job/'sources/financial.json').read_bytes(),raw)
        self.assertEqual((self.job/'financial-selection-r0.json').read_bytes(),picked)
        self.assertEqual(self.calls,['single_report_analysis','single_report_review','single_report_analysis','single_report_review'])

    def test_correction_cannot_change_frozen_valuation_or_unlisted_coverage(self):
        from research import earnings_sequential_revisions as revisions
        self.revise=True
        for _ in range(3):job=self.advance()
        plan=revisions.plan(self.job,job,stages.render_candidate)
        response={'replacements':{'cash':{'text':'Corrected fictional constraint.','citations':plan['citations']}},
                  'coverage_replacements':{k:plan['previous_analysis']['report_support']['coverage'][k] for k in plan['coverage_keys']}}
        response['coverage_replacements']['comparison_basis']=copy.deepcopy(next(iter(response['coverage_replacements'].values())))
        with self.assertRaisesRegex(ValueError,'Only affected coverage'):revisions.apply(plan,response)
        (self.job/'financial-tables.md').write_text('Tampered fictional tables')
        job=self.advance();self.assertEqual(job['status'],'blocked');self.assertEqual(len(self.calls),2)

    def test_surgical_edits_preserve_all_text_outside_anchor(self):
        from research import earnings_sequential_revisions as revisions
        self.revise=True
        for _ in range(3):job=self.advance()
        plan=revisions.plan(self.job,job,stages.render_candidate)
        old=plan['previous_analysis']['sections']['cash']['text'];anchor=old[:15]
        value={'patches':{'cash':{'edits':[{'old_text':anchor,'new_text':anchor+' Added fictional qualification.'}],'citations':plan['citations']}}}
        response=single.correction_response(plan,value);merged=revisions.apply(plan,response)
        self.assertEqual(merged['sections']['cash']['text'].replace(' Added fictional qualification.',''),old)
        report_contract.validate(merged['report_support'],merged,self.job/'sources/manifest.json')
        value['patches']['cash']['edits'].append(value['patches']['cash']['edits'][0])
        with self.assertRaisesRegex(ValueError,'not overlap'):single.correction_response(plan,value)

    def test_interning_reconstructs_complete_original_sources(self):
        self.advance();original=evidence.source_slices(self.job/'sources/manifest.json',['D001','D001'])
        scopes,records=single.intern_sources(original)
        def expand(value):
            if isinstance(value,dict):
                if set(value)=={'original_record'}:return expand(records[value['original_record']])
                return {k:expand(v) for k,v in value.items()}
            if isinstance(value,list):return [expand(v) for v in value]
            return value
        self.assertEqual(expand(scopes),original);self.assertEqual(len(records),1)
