"""Fictitious data only; tests exercise executable corrections, not model quality."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_corrections as c
from research import earnings_experiment as base
from research import earnings_passage_pipeline as pipe


class CorrectionTests(PassageFixture, unittest.TestCase):
    def state(self):
        financial = copy.deepcopy(self.financial)
        financial['context'] = [{'text': 'Fictional same-period margin comparison.', 'citations': ['D002']}]
        return {'artifacts': {'financial': financial, 'retrieval': copy.deepcopy(self.retrieval), 'analysis': copy.deepcopy(self.report)},
                'format': copy.deepcopy(c.EMPTY_FORMAT), 'findings': [{'id': 'finding-fake', 'finding': {'reason': 'Fictional omission'}}]}

    def op(self, state, kind='text', path=None):
        key, target = next((k,t) for k,t in c.registry(state,self.bundle)['targets'].items() if t['kind']==kind and (not path or t['path']==path))
        return {'id': 'edit-1', 'target_id': key, 'expected_sha256': target['expected_sha256'], 'op': 'replace_text',
                'value': 'Fictional corrected evidence.', 'reason': 'Fictional source support', 'citations': ['D001'], 'passage_ids': [self.ids[0]]}

    def plan(self, state, op=None):
        return {'snapshot_sha256': base.digest(state), 'operations': [op or self.op(state)]}

    def review(self, state, plan, candidate):
        claim = {'reason': 'Fictitious source verification', 'citations': ['D001'], 'passage_ids': [self.ids[0]]}
        return {'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan), 'approve_patch': True, 'verdict': 'pass',
                'criteria': {k: {'status': 'pass', 'evidence': 'Fictitious assessment'} for k in c.legacy.CRITERIA},
                'operations': [{'id': o['id'], 'approve': True, **claim} for o in plan['operations']],
                'resolutions': [{'id': f['id'], 'status': 'closed', **claim} for f in state['findings']], 'findings': []}

    def test_exact_replacement_preserves_financial_retrieval_and_unrelated_prose(self):
        state=self.state(); plan=self.plan(state); result=c.apply(state,plan,self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],plan['operations'][0]['value'])
        for role in ('financial','retrieval'):self.assertEqual(result['artifacts'][role],state['artifacts'][role])
        self.assertEqual(result['artifacts']['analysis']['findings'],state['artifacts']['analysis']['findings'])
        self.assertEqual(state['artifacts']['analysis'],self.report)

    def test_copy_context_exact_text_and_citation_union(self):
        state=self.state(); op=self.op(state); op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text=state['artifacts']['analysis']['opening'])
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],source['value']['text'])
        self.assertEqual(result['artifacts']['analysis']['opening_citations'],['D001','D002'])
        self.assertEqual(result['artifacts']['financial'],state['artifacts']['financial'])

    def test_atomic_failure_does_not_mutate_input(self):
        state=self.state(); original=copy.deepcopy(state); plan=self.plan(state)
        bad=self.op(state,'row');bad.update(id='bad',op='set_display',value={'label':'Fictional','dimensions':'','execute':'bad'})
        plan['operations'].append(bad)
        with self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)
        self.assertEqual(state,original)

    def test_stale_snapshot_target_and_unknown_target_rejected(self):
        state=self.state()
        for key in ('snapshot_sha256','expected_sha256','target_id'):
            plan=self.plan(state)
            (plan if key=='snapshot_sha256' else plan['operations'][0])[key]='wrong'
            with self.subTest(key=key),self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)

    def test_context_source_must_match_and_span_be_unique(self):
        state=self.state(); op=self.op(state);op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='absent')
        with self.assertRaises(ValueError):c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        op.update(old_text=state['artifacts']['analysis']['opening'],source_sha256='stale')
        with self.assertRaises(ValueError):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_no_arbitrary_data_paths_or_code_fields(self):
        state=self.state(); plan=self.plan(state);plan['operations'][0]['path']=['artifacts','financial']
        with self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)
        for field in ('code','status','scope','financial'):
            plan=self.plan(state);plan[field]='arbitrary'
            with self.subTest(field=field),self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)

    def test_display_semantics_preserve_numeric_cells(self):
        state=self.state();op=self.op(state,'row');op.update(op='set_display',value={'label':'Fictional GAAP revenue','dimensions':''})
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts'],state['artifacts'])
        self.assertIn('Fictional GAAP revenue',c.rendered(result,self.bundle,self.catalog))

    def test_display_limit_reports_actual_length(self):
        state=self.state();op=self.op(state,'basis');op.update(op='set_display',value={'text':'x'*241})
        with self.assertRaisesRegex(ValueError,'limit 240 characters; received 241'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_quote_removal_preserves_remaining_source_selections(self):
        state=self.state();op=self.op(state,'quotes');op.update(op='retain_quotes',value=[])
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['findings'][0]['quotes'],[])
        op['value']=[{'passage_id':self.ids[1]}]
        with self.assertRaises(ValueError):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_duplicate_conflicting_edits_and_unknown_evidence_rejected(self):
        state=self.state();plan=self.plan(state);plan['operations']*=2
        with self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)
        for field in ('citations','passage_ids'):
            plan=self.plan(state);plan['operations'][0][field]=['fake']
            with self.subTest(field=field),self.assertRaises(ValueError):c.apply(state,plan,self.bundle,self.catalog)

    def test_only_bound_passing_review_accepts(self):
        state=self.state();plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog)
        review=self.review(state,plan,candidate);after,status=c.adjudicate(state,candidate,plan,review,self.bundle,self.catalog)
        self.assertEqual(status,'accepted');self.assertEqual(after['findings'],[])
        for field in ('candidate_sha256','plan_sha256'):
            invalid=copy.deepcopy(review);invalid[field]='different'
            with self.subTest(field=field),self.assertRaises(ValueError):c.adjudicate(state,candidate,plan,invalid,self.bundle,self.catalog)

    def test_rejected_patch_never_persists(self):
        state=self.state();plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog);review=self.review(state,plan,candidate)
        review.update(approve_patch=False,verdict='revise');review['operations'][0]['approve']=False;review['resolutions'][0]['status']='open'
        after,status=c.adjudicate(state,candidate,plan,review,self.bundle,self.catalog)
        self.assertEqual(after,state);self.assertEqual(status,'revise')

    def test_approved_patch_can_persist_with_blocked_report(self):
        state=self.state();plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog);review=self.review(state,plan,candidate)
        review['verdict']='blocked';review['resolutions'][0]['status']='open'
        after,status=c.adjudicate(state,candidate,plan,review,self.bundle,self.catalog)
        self.assertEqual(after['artifacts'],candidate['artifacts']);self.assertEqual(status,'blocked')

    def test_cannot_accept_open_findings_failing_rubric_or_rejected_operation(self):
        state=self.state();plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog)
        for mutate in (lambda r:r['resolutions'][0].update(status='open'),lambda r:r['operations'][0].update(approve=False),lambda r:r['criteria']['source_fidelity'].update(status='fail')):
            review=self.review(state,plan,candidate);mutate(review)
            with self.assertRaises(ValueError):c.adjudicate(state,candidate,plan,review,self.bundle,self.catalog)

    def test_noop_plan_can_withdraw_mistaken_review(self):
        state=self.state();plan={'snapshot_sha256':base.digest(state),'operations':[]};candidate=c.apply(state,plan,self.bundle,self.catalog)
        review=self.review(state,plan,candidate);review['resolutions'][0]['status']='withdrawn'
        after,status=c.adjudicate(state,candidate,plan,review,self.bundle,self.catalog)
        self.assertEqual(after['artifacts'],state['artifacts']);self.assertEqual(status,'accepted')

    def test_freeze_strategy_is_explicit_and_mutually_exclusive(self):
        writing=self.root/'writing.txt';writing.write_text('Fictional standard')
        protocol=pipe.freeze(self.casepath,self.root/'run',writing,deterministic_corrections=True)
        self.assertTrue(protocol['deterministic_corrections']);self.assertFalse(protocol['repair_loop'])
        with self.assertRaises(ValueError):pipe.freeze(self.casepath,self.root/'other',writing,True,True)

    def test_resume_replays_exact_approved_candidate_and_detects_tamper(self):
        root=self.root/'corrections';root.mkdir();state=self.state();c.repair.write(root/'initial.json',state)
        c.repair.write(root/'protocol.json',{'test':'fake'});p={'max_rounds':2,'max_tokens':100}
        plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog);review=self.review(state,plan,candidate)
        folder=root/'rounds/0';results={}
        for role,value in [('propose',plan),('review',review)]:
            job=folder/role;job.mkdir(parents=True)
            text=c.prompt(role,state,self.bundle,self.catalog,'Fictional',plan if role=='review' else None,candidate if role=='review' else None)
            (job/'prompt.txt').write_text(text)
            base.save(job/'request.json',{'model':c.MODEL[0],'effort':c.MODEL[1],'bindings':{'protocol_sha256':base.sha(root/'protocol.json'),'snapshot_sha256':base.digest(state),'round':0,'role':role}})
            base.save(job/'output.json',value);results[str(job)]={'content':value,'receipt':{'session':{'id':role,'usage':{'totalTokens':10}}}}
        with patch.object(c,'verify_job',side_effect=lambda path:results[str(path)]):
            result=c.replay(root,p,self.bundle,self.catalog,'Fictional')
            self.assertEqual(result['status'],'accepted');self.assertEqual(result['tokens'],20)
            self.assertEqual(c.replay(root,p,self.bundle,self.catalog,'Fictional'),result)
            (folder/'candidate.html').write_text('tampered')
            with self.assertRaises(ValueError):c.replay(root,p,self.bundle,self.catalog,'Fictional')

    def test_no_duplicate_launch_and_budget_gate(self):
        root=self.root/'corrections';root.mkdir();c.repair.write(root/'initial.json',self.state());c.repair.write(root/'protocol.json',{})
        p={'max_rounds':2,'max_tokens':0}
        self.assertEqual(c.replay(root,p,self.bundle,self.catalog,'Fictional')['status'],'budget_exhausted')
        job=root/'rounds/0/propose';job.mkdir(parents=True);(job/'request.json').write_text('{}')
        self.assertEqual(c.replay(root,p,self.bundle,self.catalog,'Fictional')['status'],'launch_uncertain')

    def test_sentence_context_sources_copy_original_offsets(self):
        state=self.state();note=state['artifacts']['financial']['context'][0]
        note['text']='Fictional basis note. Fictional margin was 12.5% versus 10.0%. Fictional last note.'
        sources=c.registry(state,self.bundle)['context_sources']
        for source in sources.values():
            self.assertEqual(source['value']['text'],note['text'][source['start']:source['end']])
            self.assertEqual(source['parent_sha256'],base.digest(note))
        selected=next(v for v in sources.values() if v['value']['text'].startswith('Fictional margin'))
        self.assertEqual(selected['value']['text'],'Fictional margin was 12.5% versus 10.0%.')

    def test_independent_review_cannot_reuse_proposal_session(self):
        # The receipt identity check precedes consuming any review decision.
        root=self.root/'corrections';root.mkdir();state=self.state()
        c.repair.write(root/'initial.json',state);c.repair.write(root/'protocol.json',{})
        plan=self.plan(state);candidate=c.apply(state,plan,self.bundle,self.catalog)
        values={'propose':plan,'review':self.review(state,plan,candidate)}
        for role in values:
            job=root/'rounds/0'/role;job.mkdir(parents=True)
            (job/'prompt.txt').write_text(c.prompt(role,state,self.bundle,self.catalog,'Fictional',plan if role=='review' else None,candidate if role=='review' else None))
            base.save(job/'request.json',{'model':c.MODEL[0],'effort':c.MODEL[1],'bindings':{'protocol_sha256':base.sha(root/'protocol.json'),'snapshot_sha256':base.digest(state),'round':0,'role':role}})
            base.save(job/'output.json',values[role])
        with patch.object(c,'verify_job',side_effect=lambda path:{'content':values[path.name],'receipt':{'session':{'id':'same','usage':{'totalTokens':10}}}}):
            with self.assertRaisesRegex(ValueError,'Independent fresh sessions'):c.replay(root,{'max_rounds':2,'max_tokens':100},self.bundle,self.catalog,'Fictional')
