"""Fictitious repair-loop cases; all model sessions below are explicit test doubles."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from test_earnings_passages import PassageFixture
from research import earnings_report_repair as repair
from research import earnings_passage_pipeline as pipe
from research import earnings_experiment as base


class RepairTests(PassageFixture, unittest.TestCase):
    def state(self, target='analysis'):
        s={'status':'pending','round':1,'artifacts':{'financial':copy.deepcopy(self.financial),'retrieval':copy.deepcopy(self.retrieval),'analysis':copy.deepcopy(self.report)},'format':{'rows':{},'basis':{'text':'','citations':[]}},'ledger':[],'responses':{},'needs_analysis':False,'last_review':None,'reviewed_digest':None}
        repair.add_findings(s,[{'target':target,'passage':'Fictional attributed claim','reason':'Claim describes the rival, not the issuer','required_change':'Check speaker and subject','citations':['D001']}])
        return s

    def claim(self):
        return {'explanation':'Fictitious original context refers to Rival Ltd.', 'citations':['D001'],'passage_ids':[self.ids[0]],'speaker':'Fictional CEO','subject':'Rival Ltd.'}

    def response(self,state,action='rebut',artifact=None):
        return {'responses':[dict(self.claim(),finding_id=f['id'],action=action) for f in repair.open_findings(state,repair.next_role(state))],'artifact':artifact}

    def review(self,state,status='withdrawn',verdict='pass'):
        return {'verdict':verdict,'criteria':{k:{'status':'pass' if verdict=='pass' else 'fail','evidence':'Fictional evidence'} for k in repair.legacy.CRITERIA},'resolutions':[dict(self.claim(),finding_id=f['id'],status=status) for f in repair.open_findings(state)],'findings':[]}

    def test_author_rebuttal_does_not_accept_then_reviewer_withdraws(self):
        s=self.state();after=repair.transition(s,'analysis',self.response(s),self.bundle,self.catalog)
        self.assertEqual(after['status'],'pending');self.assertEqual(after['artifacts'],s['artifacts'])
        final=repair.transition(after,'review',self.review(after),self.bundle,self.catalog)
        self.assertEqual(final['status'],'accepted');self.assertEqual(final['ledger'][0]['status'],'withdrawn')
        self.assertEqual(final['reviewed_digest'],base.digest({'artifacts':final['artifacts'],'format':final['format']}))

    def test_reviewer_cannot_pass_with_open_finding_or_close_a_rebuttal(self):
        s=self.state();s=repair.transition(s,'analysis',self.response(s),self.bundle,self.catalog)
        for status in ('open','closed'):
            with self.subTest(status=status),self.assertRaises(ValueError):repair.transition(s,'review',self.review(s,status),self.bundle,self.catalog)

    def test_reviewer_must_adjudicate_every_finding_and_use_original_ids(self):
        s=self.state();s=repair.transition(s,'analysis',self.response(s),self.bundle,self.catalog)
        for mutate in (lambda x:x.update(resolutions=[]),lambda x:x['resolutions'][0].update(passage_ids=['invented'])):
            r=self.review(s);mutate(r)
            with self.assertRaises(ValueError):repair.transition(s,'review',r,self.bundle,self.catalog)

    def test_formatter_repair_preserves_values_periods_and_acceptance_requires_review(self):
        s=self.state('formatter');rows=repair.row_catalog(self.financial,self.bundle);key=next(iter(rows))
        spec={'rows':{key:{'label':'Fictional revenue','dimensions':'','citations':['D001']}},'basis':{'text':'Fictitious GAAP basis','citations':['D001']}}
        after=repair.transition(s,'formatter',self.response(s,'repair',spec),self.bundle,self.catalog)
        self.assertEqual(after['artifacts'],s['artifacts']);self.assertEqual(after['status'],'pending')
        self.assertIn('Fictitious GAAP basis',repair.table(self.financial,self.bundle,spec))
        final=repair.transition(after,'review',self.review(after,'closed'),self.bundle,self.catalog)
        self.assertEqual(final['status'],'accepted')
        repair.render(self.root/'report.html',final,self.bundle,self.catalog)
        self.assertIn('Fictitious GAAP basis',(self.root/'report.html').read_text())

    def test_open_finding_can_continue_without_duplicate_finding(self):
        s=self.state();s=repair.transition(s,'analysis',self.response(s,'unresolved'),self.bundle,self.catalog)
        after=repair.transition(s,'review',self.review(s,'open','revise'),self.bundle,self.catalog)
        self.assertEqual(after['round'],2);self.assertEqual(len(after['ledger']),1)
        self.assertEqual(repair.next_role(after),'analysis')

    def test_formatter_rejects_values_code_and_unknown_rows(self):
        s=self.state('formatter')
        for spec in ({'rows':{},'basis':{'text':'','citations':[]},'code':'execute()'}, {'rows':{'bad':{'label':'x','dimensions':'','citations':['D001']}},'basis':{'text':'','citations':[]}}):
            with self.assertRaises(ValueError):repair.transition(s,'formatter',self.response(s,'repair',spec),self.bundle,self.catalog)

    def test_review_excerpt_reports_actual_appendix_anchors_and_broken_targets(self):
        content='<main><a href="#e-F001">F001</a><a href="#missing">bad</a><h2>Original evidence</h2><details id="e-F001">Original source</details></main>'
        view=repair.rendered_review_view(content)
        self.assertNotIn('<details',view['report_body_html_excerpt'])
        self.assertEqual(view['actual_anchor_ids'],['e-F001'])
        self.assertEqual(view['missing_fragment_targets'],['missing'])
        self.assertIn('COMPLETE',view['notice'])

    def test_upstream_repair_refreshes_analysis_without_repeating_other_preparers(self):
        s=self.state('financial');artifact=copy.deepcopy(self.financial);artifact['context']=[{'text':'Fictional correction','citations':['D001']}]
        after=repair.transition(s,'financial',self.response(s,'repair',artifact),self.bundle,self.catalog)
        self.assertEqual(repair.next_role(after),'analysis')
        after=repair.transition(after,'analysis',{'responses':[],'artifact':None},self.bundle,self.catalog)
        self.assertEqual(repair.next_role(after),'review');self.assertEqual(after['artifacts']['retrieval'],s['artifacts']['retrieval'])

    def test_exhausted_rounds_keep_unresolved_finding(self):
        s=self.state();s['round']=2;s=repair.transition(s,'analysis',self.response(s,'unresolved'),self.bundle,self.catalog)
        final=repair.transition(s,'review',self.review(s,'open','blocked'),self.bundle,self.catalog)
        self.assertEqual(final['status'],'blocked');self.assertEqual(final['ledger'][0]['status'],'open')

    def test_invalid_response_has_one_durable_retry_then_stops(self):
        s=self.state();one=repair.apply_response(s,'analysis',{},self.bundle,self.catalog)
        self.assertEqual(repair.next_role(one),'analysis');self.assertIn('retry',one)
        two=repair.apply_response(one,'analysis',{},self.bundle,self.catalog)
        self.assertEqual(two['status'],'blocked');self.assertEqual(two['artifacts'],s['artifacts'])

    def test_valid_retry_clears_retry_and_proceeds(self):
        s=repair.apply_response(self.state(),'analysis',{},self.bundle,self.catalog)
        s=repair.apply_response(s,'analysis',self.response(s),self.bundle,self.catalog)
        self.assertNotIn('retry',s);self.assertEqual(repair.next_role(s),'review')

    def test_missing_response_evidence_gets_narrow_selection_patch(self):
        s=self.state();prior=self.response(s);prior['responses'][0]['passage_ids']=[]
        pending=repair.apply_response(s,'analysis',prior,self.bundle,self.catalog)
        self.assertTrue(repair.passage_retry(pending,'analysis'))
        windows=repair.response_passage_windows(pending,self.bundle,self.catalog)
        candidate=windows[0]['candidate_passages'][0]['passage_id']
        patch_value={'response_passages':[{'finding_id':windows[0]['finding_id'],'passage_ids':[candidate]}]}
        updated=repair.patch_response_passages(pending,patch_value,self.bundle,self.catalog)
        self.assertEqual(updated['artifact'],prior['artifact'])
        self.assertEqual(updated['responses'][0]['explanation'],prior['responses'][0]['explanation'])
        after=repair.apply_response(pending,'analysis',patch_value,self.bundle,self.catalog)
        self.assertEqual(repair.next_role(after),'review')
        prompt=repair.prompt(pending,'analysis',self.bundle,self.catalog,'Fictional standard')
        self.assertIn('EVIDENCE-ID REPAIR ONLY',prompt)
        self.assertNotIn('upstream_artifacts',prompt)

    def test_evidence_patch_cannot_mutate_artifact_or_choose_outside_candidates(self):
        s=self.state();prior=self.response(s);prior['responses'][0]['passage_ids']=[]
        pending=repair.apply_response(s,'analysis',prior,self.bundle,self.catalog)
        windows=repair.response_passage_windows(pending,self.bundle,self.catalog)
        invalid={'response_passages':[{'finding_id':windows[0]['finding_id'],'passage_ids':['invented']}]}
        with self.assertRaises(ValueError):repair.patch_response_passages(pending,invalid,self.bundle,self.catalog)
        invalid['artifact']=self.report
        with self.assertRaises(ValueError):repair.patch_response_passages(pending,invalid,self.bundle,self.catalog)
        self.assertEqual(repair.apply_response(pending,'analysis',invalid,self.bundle,self.catalog)['status'],'blocked')

    def make_run(self, max_jobs=12):
        seed=self.root/'seed';writing=self.root/'standard.txt';writing.write_text('Fictitious writing standard')
        pipe.freeze(self.casepath,seed,writing)
        s=self.state();base.save(seed/'artifacts.json',s['artifacts']);base.save(seed/'review.json',{'findings':[x['finding'] for x in s['ledger']]})
        base.save(seed/'result.json',{'status':'blocked','correction_rounds':0})
        root=self.root/'repair'
        with patch.object(repair.subprocess,'run'):repair.initialize(seed,root,max_jobs=max_jobs)
        return root

    def fake_run(self,job,text,model,effort,bindings,timeout):
        job.mkdir(parents=True,exist_ok=True)
        state=base.read(self.active/'initial.json')
        if bindings['role']=='analysis':value=self.response(state)
        else:
            state=repair.transition(state,'analysis',self.response(state),self.bundle,self.catalog);value=self.review(state)
        (job/'prompt.txt').write_text(text);base.save(job/'request.json',{'bindings':bindings,'model':model,'effort':effort})
        result={'content':value,'receipt':{'session':{'id':job.name,'usage':{'totalTokens':10}}}}
        base.save(job/'output.json',result)
        return result

    def test_resume_reuses_completed_jobs_and_detects_event_tampering(self):
        root=self.make_run();self.active=root
        with patch.object(repair,'run_role',side_effect=self.fake_run) as runner,patch.object(repair,'verify_job',side_effect=lambda p:base.read(p/'output.json')):
            self.assertEqual(repair.advance(root)['status'],'pending')
            self.assertEqual(repair.verify(root)['next_role'],'review')
            self.assertEqual(repair.advance(root)['status'],'accepted')
            self.assertEqual(repair.advance(root)['status'],'accepted');self.assertEqual(runner.call_count,2)
            event=base.read(root/'events/000.json');event['after']['artifacts']['analysis']['opening']='tampered';(root/'events/000.json').write_text(json.dumps(event))
            with self.assertRaises(ValueError):repair.verify(root)

    def test_initial_state_tamper_and_uncertain_launch_refuse_work(self):
        root=self.make_run();job=root/'jobs/000-analysis';job.mkdir(parents=True);base.save(job/'request.json',{})
        with patch.object(repair,'run_role') as runner:
            self.assertEqual(repair.advance(root)['status'],'launch_uncertain');runner.assert_not_called()
        state=base.read(root/'initial.json');state['status']='accepted';(root/'initial.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'Initial state'):repair.verify(root)

    def test_budget_stops_new_dispatch(self):
        root=self.make_run(max_jobs=1);self.active=root
        with patch.object(repair,'run_role',side_effect=self.fake_run) as runner,patch.object(repair,'verify_job',side_effect=lambda p:base.read(p/'output.json')):
            repair.advance(root)
            self.assertEqual(repair.advance(root)['status'],'budget_exhausted')
            self.assertEqual(runner.call_count,1)

    def test_protocol_change_invalidates_previous_calls(self):
        root=self.make_run();self.active=root
        with patch.object(repair,'run_role',side_effect=self.fake_run),patch.object(repair,'verify_job',side_effect=lambda p:base.read(p/'output.json')):
            repair.advance(root)
            p=base.read(root/'protocol.json');p['max_jobs']=1;(root/'protocol.json').write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError,'binding'):repair.advance(root)

    def test_passage_windows_do_not_mix_raw_and_normalized_offsets(self):
        p=self.catalog['passages'][0]
        wrong={'spans':[{'document_id':p['document_id'],'sha256':'different-representation','start':0,'end':9999999}]}
        self.assertEqual(repair.passages_for_sources(self.catalog,set(),[wrong]),[])
        correct=copy.deepcopy(wrong);correct['spans'][0]['sha256']=p['sha256']
        self.assertIn(p,repair.passages_for_sources(self.catalog,set(),[correct]))

    def test_cli_verify_follows_existing_continuation(self):
        import io
        import sys
        root=(self.root/'cli-seed').resolve();root.mkdir()
        base.save(root/'protocol.json',{'repair_loop':True})
        continuation=root.with_name(root.name+'-repair');continuation.mkdir()
        base.save(continuation/'protocol.json',{'seed':str(root)})
        with patch.object(sys,'argv',['pipeline','verify',str(root)]),patch.object(pipe,'verify',return_value={'status':'blocked','correction_rounds':0,'wall_seconds':1}),patch.object(repair,'verify',return_value={'status':'accepted'}) as verify,patch('sys.stdout',new_callable=io.StringIO) as output:
            pipe.main()
            verify.assert_called_once_with(continuation)
            self.assertEqual(json.loads(output.getvalue())['status'],'accepted')

    def test_cli_preserves_source_preparation_block_without_launching_report_repair(self):
        import io
        import sys
        root=(self.root/'incomplete').resolve();root.mkdir()
        base.save(root/'protocol.json',{'repair_loop':True})
        base.save(root/'artifacts.json',{'financial':self.financial})
        base.save(root/'review.json',None)
        with patch.object(sys,'argv',['pipeline','run',str(root)]),patch.object(pipe,'run',return_value={'status':'blocked','correction_rounds':1,'wall_seconds':1}),patch.object(repair,'initialize') as initialize,patch('sys.stdout',new_callable=io.StringIO) as output:
            pipe.main()
            initialize.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['status'],'blocked')
            self.assertIn('complete candidate',json.loads(output.getvalue())['repair_not_started'])

if __name__=='__main__':unittest.main()
