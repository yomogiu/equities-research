"""Synthetic opt-in evidence reuse, exact expansion and replay tests; no models."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_passage_pipeline as pipe
from research import earnings_efficient_evidence as reuse
from research import earnings_financial_context as financial
from research import earnings_experiment as base


class EvidenceTests(PassageFixture,unittest.TestCase):
    def deps(self):
        return {'financial':financial.bind(self.financial,self.bundle),'retrieval':self.retrieval,'analysis':self.report}

    def test_review_preserves_complete_original_sources_and_quote_offsets(self):
        before=copy.deepcopy(self.bundle)
        value=reuse.build('review',self.bundle,self.catalog,self.deps())
        sources=value['complete_source_navigation']['sources'];blocks=value['source_blocks']['rows']
        for source in self.bundle['manifest']['sources']:
            if source['representation']!='text':continue
            matching=[(a,b,text) for sid,a,b,text in blocks if sources[sid]==[source['document_id'],source['sha256']]]
            text=''.join(t for _,_,t in sorted(matching))
            self.assertEqual(text,Path(source['path']).read_bytes().decode())
        for group in value['passages']['groups']:
            for pid,start,end in group['rows']:
                p=next(p for p in self.catalog['passages'] if p['passage_id']==pid)
                source=sources.index([p['document_id'],p['sha256']])
                block=next((a,b,text) for sid,a,b,text in blocks if sid==source and a<=start<end<=b)
                self.assertEqual(block[2][start-block[0]:end-block[0]],p['text'])
        self.assertEqual(before,self.bundle)
        self.assertTrue(value['coverage']['complete_nontranscript_text'])

    def test_retrieval_reuses_complete_call_and_full_deferred_navigation(self):
        value=reuse.build('retrieval',self.bundle,self.catalog,{'financial':financial.bind(self.financial,self.bundle)})
        sources=value['complete_source_navigation']['sources']
        text=''.join(row[3] for row in value['source_blocks']['rows'] if sources[row[0]][0]=='fictional-call')
        self.assertEqual(text,self.text)
        inventory=value['document_navigation']
        self.assertEqual({row[0] for row in inventory['rows']},{d['id'] for d in self.bundle['documents']['chunks']})
        self.assertFalse(value['coverage']['complete_nontranscript_text'])
        self.assertTrue(value['deferred_document_ids'])
        for key in ('sections','turns','exchanges'):
            restored=[dict(zip(group['columns'],row)) for group in value['transcript_index'][key] for row in group['rows']]
            self.assertEqual(sorted(restored,key=lambda r:r['id']),sorted(self.bundle['transcript_index'][key],key=lambda r:r['id']))

    def test_schema_and_quote_preflight_prevents_expensive_review(self):
        deps=self.deps();deps['retrieval']=copy.deepcopy(deps['retrieval']);deps['retrieval']['quotes'][0]={'passage_id':'invented'}
        with self.assertRaises(ValueError):reuse.prompt('review',self.bundle,'Standard',deps,[],self.catalog)
        deps=self.deps();deps['format']={'rows':{},'basis':{'text':'','citations':[]},'layout':{'version':'invented'}}
        with self.assertRaisesRegex(ValueError,'layout schema'):reuse.prompt('review',self.bundle,'Standard',deps,[],self.catalog)

    def test_request_schema_unknown_ids_and_duplicate_artifacts_fail(self):
        self.assertEqual(reuse.requested_scopes({'title':'ordinary'},self.bundle,self.catalog),None)
        for out in [{'needs_evidence':[]},{'needs_evidence':[{'scope_id':'unknown','reason':'context'}]},
                    {'needs_evidence':[{'scope_id':'D001','reason':'context'}],'verdict':'pass'}]:
            with self.assertRaises(ValueError):reuse.requested_scopes(out,self.bundle,self.catalog)
        scopes=reuse.requested_scopes({'needs_evidence':[{'scope_id':'F002','reason':'source row'}]},self.bundle,self.catalog)
        self.assertIn('F002',scopes)

    def test_benchmark_is_read_only_and_preserves_old_inputs(self):
        deps={'financial':self.financial,'retrieval':self.retrieval,'analysis':self.report};before=copy.deepcopy(deps)
        result=reuse.benchmark_inputs(self.bundle,self.catalog,'Fictional standard',deps)
        self.assertEqual(set(result),set(pipe.MODELS));self.assertEqual(deps,before)
        self.assertGreater(result['financial']['reduction_fraction'],0)

    def test_known_but_unseen_scopes_require_original_expansion(self):
        financial_sheet=copy.deepcopy(self.financial)
        financial_sheet['context']=[{'text':'Fictional unsupported transcript context','citations':[self.bundle['transcript_index']['turns'][0]['id']]}]
        with self.assertRaisesRegex(ValueError,'unavailable scopes'):
            pipe.bind_efficient_financial(financial_sheet,self.bundle)
        deps={'financial':financial.bind(self.financial,self.bundle)}
        with self.assertRaisesRegex(ValueError,'deferred source previews'):
            reuse.validate_support('retrieval',self.retrieval,self.bundle,self.catalog,deps)
        reuse.validate_support('retrieval',self.retrieval,self.bundle,self.catalog,deps,['D001'])


class EfficientPipelineTests(PassageFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.writing=self.root/'writing.txt';self.writing.write_text('Fictional concise standard')
        note=next(d['id'] for d in self.bundle['documents']['chunks'] if d['document_id']=='fictional-note')
        selected=[p['passage_id'] for p in self.catalog['passages'] if p['document_id']=='fictional-call' and p['text'].strip()][:4]
        self.retrieval['selected_document_ids']=[note];self.retrieval['quotes']=[{'passage_id':pid} for pid in selected]
        self.report['opening_citations']=[note]
        for f in self.report['findings']:f['citations']=[note];f['quotes']=[]
        self.report['findings'][0]['quotes']=[{'passage_id':selected[0]}]
        self.output=self.root/'efficient';pipe.freeze(self.casepath,self.output,self.writing,efficient=True)
        self.jobs={};self.calls=[];self.expand_role=None;self.double_expand=False;self.bad_analysis=False
        for name,side in [('run_role',self.call),('verify_job',lambda path:self.jobs[str(path)])]:
            mock=patch.object(pipe,name,side_effect=side);mock.start();self.addCleanup(mock.stop)

    def call(self,path,text,model,effort,bindings,timeout):
        if str(path) in self.jobs:return self.jobs[str(path)]
        path.mkdir(parents=True,exist_ok=True)
        role=bindings['role'];expansion=bindings['evidence_expansion'];self.calls.append((role,bindings['round'],expansion))
        if role==self.expand_role and (expansion==0 or self.double_expand):
            out={'needs_evidence':[{'scope_id':'F002' if expansion==0 else 'D002','reason':'Fictional original context'}]}
        elif role=='financial':out=self.financial
        elif role=='retrieval':out=self.retrieval
        elif role=='analysis':
            out=copy.deepcopy(self.report)
            if self.bad_analysis:out['opening_citations']=['unknown']
        else:out={'verdict':'pass','criteria':{k:{'status':'pass','evidence':'Fictional source audit'} for k in pipe.legacy.CRITERIA},'findings':[]}
        base.save(path/'request.json',{'bindings':bindings,'model':model,'effort':effort});(path/'prompt.txt').write_text(text)
        result={'content':copy.deepcopy(out),'receipt':{'started_at':'2040-01-01T00:00:00+00:00','finished_at':'2040-01-01T00:00:01+00:00',
                 'session':{'id':path.name,'usage':{'totalTokens':100}}}}
        base.save(path/'output.json',{'content':out});self.jobs[str(path)]=result;return result

    def test_opt_in_keeps_models_budget_and_legacy_default(self):
        protocol=base.read(self.output/'protocol.json');self.assertEqual(protocol['version'],pipe.EFFICIENT_VERSION)
        self.assertEqual(protocol['models'],{k:list(v) for k,v in pipe.MODELS.items()});self.assertEqual(protocol['max_correction_rounds'],2)
        old=self.root/'legacy';pipe.freeze(self.casepath,old,self.writing)
        self.assertEqual(base.read(old/'protocol.json')['version'],pipe.VERSION)
        result=pipe.run(self.output);self.assertEqual(result['status'],'accepted');self.assertEqual(result['total_tokens'],400)
        self.assertEqual(len(self.calls),4);pipe.verify(self.output)

    def test_one_expansion_is_bound_measured_and_preserves_round(self):
        self.expand_role='review';result=pipe.run(self.output)
        self.assertEqual(result['status'],'accepted');self.assertEqual(result['correction_rounds'],0)
        self.assertEqual(result['total_tokens'],500);self.assertIn(('review',0,1),self.calls)
        review=result['jobs'][-1];self.assertEqual(len(review['evidence_jobs']),2)
        request=base.read(self.output/'jobs/review-r0-evidence-1/request.json')
        self.assertEqual(request['bindings']['prior_output_sha256'],base.sha(self.output/'jobs/review-r0/output.json'))
        pipe.verify(self.output)

    def test_finite_turn_never_launches_expansion_after_allowance(self):
        self.expand_role='review'
        for _ in range(4):
            with self.assertRaises(pipe.PendingJobs):pipe.run(self.output,max_new_jobs=1)
        self.assertNotIn(('review',0,1),self.calls)
        result=pipe.run(self.output,max_new_jobs=1);self.assertEqual(result['total_tokens'],500)

    def test_second_expansion_cannot_become_acceptance_or_budget_reset(self):
        self.expand_role='review';self.double_expand=True
        with self.assertRaisesRegex(ValueError,'expansion exhausted'):pipe.run(self.output)
        self.assertEqual(self.calls.count(('review',0,1)),1);self.assertFalse((self.output/'result.json').exists())

    def test_invalid_author_schema_stops_before_expensive_reviewer(self):
        self.bad_analysis=True;result=pipe.run(self.output)
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['correction_rounds'],2)
        self.assertFalse(any(r=='review' for r,_,_ in self.calls))

    def test_expansion_prompt_tamper_and_reused_session_fail_replay(self):
        self.expand_role='review';pipe.run(self.output)
        p=self.output/'jobs/review-r0-evidence-1/prompt.txt';original=p.read_text();p.write_text(original+'tampered')
        with self.assertRaisesRegex(ValueError,'exact evidence request'):pipe.verify(self.output)
        p.write_text(original)
        self.jobs[str(p.parent.resolve())]['receipt']['session']['id']='analysis-r0'
        with self.assertRaisesRegex(ValueError,'Fresh independent'):pipe.verify(self.output)

    def test_stripped_financial_marker_cannot_downgrade_frozen_contract(self):
        pipe.run(self.output)
        path=self.output/'artifacts.json';artifacts=base.read(path);artifacts['financial'].pop('_display_contract')
        path.write_text(json.dumps(artifacts))
        result=base.read(self.output/'result.json');result['artifact_digest']=base.digest(artifacts)
        (self.output/'result.json').write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError,'Derived artifacts differ'):pipe.verify(self.output)
