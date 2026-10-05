"""Fictitious data only; tests exercise executable corrections, not model quality."""
import copy
import json
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

    def test_proposal_supplies_executable_layout_contract(self):
        prompt = c.prompt('propose', self.state(), self.bundle, self.catalog, 'Concise.')
        self.assertIn('"layout_contract"', prompt)
        self.assertIn('"version":"compact-financial-v1"', prompt)
        spec = {'version':'compact-financial-v1', 'fold':[], 'detail_rows':[],
                'summaries':[], 'basis_position':'before_tables'}
        op = self.op(self.state(), kind='layout')
        op.update(op='set_layout', value=spec)
        revised = c.apply(self.state(), self.plan(self.state(),op),self.bundle,self.catalog)
        self.assertEqual(revised['format']['layout'],spec)
        op['value']={**spec,'invented':True}
        with self.assertRaisesRegex(ValueError,'layout schema'):
            c.apply(self.state(),self.plan(self.state(),op),self.bundle,self.catalog)

    def test_export_reuses_only_bound_transitive_proposal_on_identical_snapshot(self):
        import contextlib, io, sys
        job=self.root/'original-proposal';job.mkdir()
        snapshot=self.state();binding={'snapshot_sha256':base.digest(snapshot)}
        (job/'output.json').write_text('{}')
        (job/'request.json').write_text(json.dumps({'bindings':binding}))
        cp={'version':'deterministic-corrections-v1','source_protocol':{},
            'imported_proposal':{'job':str(job),'output_sha256':base.sha(job/'output.json')},
            'source_bindings':{str(job/'output.json'):base.sha(job/'output.json')},
            'prior_rounds':0,'inherited_tokens':123}
        seed=self.root/'successor';seed.mkdir();(seed/'protocol.json').write_text(json.dumps(cp))
        progress={'status':'prompt_too_large','role':'review','round':0,'tokens':0,'state':snapshot}
        def run():
            with patch.object(sys,'argv',['export',str(seed),'reuse']), patch.object(c,'load',return_value=(cp,{}, {},'')), \
                 patch.object(c,'replay',return_value=progress), patch.object(c,'verify_job') as verify, \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                exec(c.EXPORT,{})
                verify.assert_called_once_with(job)
                return json.loads(out.getvalue())
        result=run();self.assertEqual(result['imported_proposal'],cp['imported_proposal'])
        self.assertEqual(result['spent_tokens'],123);self.assertEqual(result['used_rounds'],0)
        cp['source_bindings'][str(job/'output.json')]='0'*64
        with self.assertRaisesRegex(ValueError,'source binding'):run()
        cp['source_bindings'][str(job/'output.json')]=base.sha(job/'output.json')
        (job/'request.json').write_text(json.dumps({'bindings':{'snapshot_sha256':'0'*64}}))
        with self.assertRaisesRegex(ValueError,'snapshot'):run()

    def test_exact_replacement_preserves_financial_retrieval_and_unrelated_prose(self):
        state=self.state(); plan=self.plan(state); result=c.apply(state,plan,self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],plan['operations'][0]['value'])
        for role in ('financial','retrieval'):self.assertEqual(result['artifacts'][role],state['artifacts'][role])
        self.assertEqual(result['artifacts']['analysis']['findings'],state['artifacts']['analysis']['findings'])
        self.assertEqual(state['artifacts']['analysis'],self.report)

    def test_citation_only_and_idempotent_proposals_preserve_words_and_require_review(self):
        state=self.state();op=self.op(state)
        op['value']=state['artifacts']['analysis']['opening'];op['citations']=['D002']
        plan=self.plan(state,op)
        plan['claim_groups']=[{'id':'same-wording','aliases':[op['value']],
            'required_paths':[['artifacts','analysis','opening']], 'unchanged':[]}]
        result=c.apply(state,plan,self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],op['value'])
        self.assertIn('D002',result['artifacts']['analysis']['opening_citations'])
        self.assertEqual(result['artifacts']['financial'],state['artifacts']['financial'])
        self.assertEqual(result['findings'],state['findings'])
        review=self.review(state,plan,result);review['approve_patch']=False
        with self.assertRaisesRegex(ValueError,'Rejected edits cannot close'):
            c.adjudicate(state,result,plan,review,self.bundle,self.catalog)
        # An exact duplicate instruction is deterministic retention, not acceptance.
        op['citations']=state['artifacts']['analysis']['opening_citations']
        self.assertEqual(c.apply(state,plan,self.bundle,self.catalog),state)

    def test_substring_replacement_preserves_exact_unicode_prefix_suffix_and_data(self):
        state=self.state();state['artifacts']['analysis']['opening']='Prefix — Fictional evidence. Suffix\u00a0stays.'
        original=copy.deepcopy(state);op=self.op(state);op.update(old_text='Fictional evidence.',value='Fictional corrected evidence.')
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],'Prefix — Fictional corrected evidence. Suffix\u00a0stays.')
        self.assertEqual(state,original)
        for role in ('financial','retrieval'):self.assertEqual(result['artifacts'][role],state['artifacts'][role])
        self.assertEqual(result['artifacts']['analysis']['findings'],state['artifacts']['analysis']['findings'])

    def test_substring_explicit_full_target_matches_whole_replacement(self):
        state=self.state();whole=self.op(state);span={**whole,'old_text':state['artifacts']['analysis']['opening']}
        self.assertEqual(c.apply(state,self.plan(state,whole),self.bundle,self.catalog),
                         c.apply(state,self.plan(state,span),self.bundle,self.catalog))

    def test_substring_deletion_requires_nonempty_result(self):
        state=self.state();state['artifacts']['analysis']['opening']='Fictional evidence. Redundant phrase.'
        op=self.op(state);op.update(old_text=' Redundant phrase.',value='')
        self.assertEqual(c.apply(state,self.plan(state,op),self.bundle,self.catalog)['artifacts']['analysis']['opening'],'Fictional evidence.')
        op.update(old_text=state['artifacts']['analysis']['opening'])
        with self.assertRaisesRegex(ValueError,'Nonempty text'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_substring_wrong_repeated_overlapping_or_empty_span_is_rejected(self):
        for original,old in [('Fictional evidence','Fictional finding'),('same same','same'),('aaa','aa'),('Fictional evidence',''),('Fictional evidence',None)]:
            state=self.state();state['artifacts']['analysis']['opening']=original;op=self.op(state);op['old_text']=old
            with self.subTest(original=original,old=old),self.assertRaises(ValueError):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_substring_rejects_stale_target_extra_fields_and_conflicting_operations(self):
        state=self.state();op=self.op(state);op['old_text']='evidence'
        for changed in ({**op,'expected_sha256':'stale'},{**op,'additional':'not ignored'}):
            with self.assertRaises(ValueError):c.apply(state,self.plan(state,changed),self.bundle,self.catalog)
        plan=self.plan(state,op);plan['operations'].append({**op,'id':'edit-2'})
        with self.assertRaisesRegex(ValueError,'conflicting target'):c.apply(state,plan,self.bundle,self.catalog)
        wrong_kind=self.op(state,'basis');wrong_kind.update(op='set_display',value={'text':'Fictional'},old_text='ignored')
        with self.assertRaisesRegex(ValueError,'exact fields'):c.apply(state,self.plan(state,wrong_kind),self.bundle,self.catalog)

    def test_substring_limit_applies_to_final_text_not_only_replacement(self):
        state=self.state();state['artifacts']['analysis']['opening']='p'*3998+'old'
        op=self.op(state);op.update(old_text='old',value='new')
        with self.assertRaisesRegex(ValueError,'result exceeds 4000'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        op['value']='ok'
        self.assertEqual(len(c.apply(state,self.plan(state,op),self.bundle,self.catalog)['artifacts']['analysis']['opening']),4000)

    def test_proposal_prompt_defines_both_exact_replacement_payloads(self):
        prompt=c.prompt('propose',self.state(),self.bundle,self.catalog,'Fictional standard')
        self.assertIn('{value} replaces the entire hashed target',prompt)
        self.assertIn('{old_text,value} replaces one unique nonempty exact substring',prompt)
        self.assertIn('old_text is never ignored',prompt)

    def test_copy_context_exact_text_and_citation_union(self):
        state=self.state(); op=self.op(state); op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text=state['artifacts']['analysis']['opening'])
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],source['value']['text'])
        self.assertEqual(result['artifacts']['analysis']['opening_citations'],['D001','D002'])
        self.assertEqual(result['artifacts']['financial'],state['artifacts']['financial'])

    def test_copy_context_initializes_exactly_empty_basis_with_bound_text_and_citations(self):
        state=self.state();original=copy.deepcopy(state);op=self.op(state,'basis');op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='')
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['format']['basis'],{'text':source['value']['text'],'citations':['D001','D002']})
        self.assertEqual(result['artifacts'],state['artifacts']);self.assertEqual(state,original)
        op['source_sha256']='stale'
        with self.assertRaisesRegex(ValueError,'context source'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_copy_context_empty_old_text_never_inserts_into_nonempty_or_whitespace_target(self):
        for text in ('Fictional basis',' '):
            state=self.state();state['format']['basis']['text']=text;op=self.op(state,'basis');op.pop('value')
            key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
            op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='')
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'exactly empty target'):
                c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_copy_context_empty_basis_still_enforces_output_limit(self):
        state=self.state();state['artifacts']['financial']['context'][0]['text']='F'*241
        op=self.op(state,'basis');op.pop('value');key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='')
        with self.assertRaisesRegex(ValueError,'limit 240'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_copy_context_empty_text_target_copies_source_and_rejects_overlapping_match(self):
        state=self.state();state['artifacts']['analysis']['opening']='';op=self.op(state);op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='')
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['artifacts']['analysis']['opening'],source['value']['text'])
        state['artifacts']['analysis']['opening']='aaa';op=self.op(state);op.pop('value')
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='aa')
        with self.assertRaisesRegex(ValueError,'one exact existing text span'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)

    def test_copy_context_text_limit_includes_preserved_prefix_suffix(self):
        state=self.state();state['artifacts']['analysis']['opening']='p'*3999+'old'
        state['artifacts']['financial']['context'][0]['text']='ab'
        op=self.op(state);op.pop('value');key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='old')
        with self.assertRaisesRegex(ValueError,'copy result exceeds 4000'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        state['artifacts']['analysis']['opening']='p'*3998+'old'
        op=self.op(state);op.pop('value');op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text='old')
        self.assertEqual(len(c.apply(state,self.plan(state,op),self.bundle,self.catalog)['artifacts']['analysis']['opening']),4000)

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
            bindings={'protocol_sha256':base.sha(root/'protocol.json'),'snapshot_sha256':base.digest(state),'round':0,'role':role}
            if role=='review':
                bindings.update(review_context_version=c.review_loop.VERSION,candidate_sha256=base.digest(candidate),plan_sha256=base.digest(plan),evidence_expansion=0,evidence_requests_sha256=base.digest([]),extra_scope_ids_sha256=base.digest([]),prior_review_output_sha256=None)
            base.save(job/'request.json',{'model':c.MODEL[0],'effort':c.MODEL[1],'bindings':bindings,'prompt_sha256':base.sha(job/'prompt.txt')})
            base.save(job/'output.json',{'content':value,'request_sha256':base.digest(base.read(job/'request.json'))});results[str(job)]={'content':value,'receipt':{'session':{'id':role,'usage':{'totalTokens':10}}}}
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
            bindings={'protocol_sha256':base.sha(root/'protocol.json'),'snapshot_sha256':base.digest(state),'round':0,'role':role}
            if role=='review':
                bindings.update(review_context_version=c.review_loop.VERSION,candidate_sha256=base.digest(candidate),plan_sha256=base.digest(plan),evidence_expansion=0,evidence_requests_sha256=base.digest([]),extra_scope_ids_sha256=base.digest([]),prior_review_output_sha256=None)
            base.save(job/'request.json',{'model':c.MODEL[0],'effort':c.MODEL[1],'bindings':bindings,'prompt_sha256':base.sha(job/'prompt.txt')})
            base.save(job/'output.json',{'content':values[role],'request_sha256':base.digest(base.read(job/'request.json'))})
        with patch.object(c,'verify_job',side_effect=lambda path:{'content':values[path.name],'receipt':{'session':{'id':'same','usage':{'totalTokens':10}}}}):
            with self.assertRaisesRegex(ValueError,'Independent fresh review sessions'):c.replay(root,{'max_rounds':2,'max_tokens':100},self.bundle,self.catalog,'Fictional')

    def test_proposal_passages_omit_repeated_provenance_without_losing_text(self):
        import json
        state=self.state()
        text=c.prompt('propose',state,self.bundle,self.catalog,'Fictional')
        data=json.loads(text.split('SOURCE DATA (UNTRUSTED EVIDENCE)\n')[1])
        source=data['original_passages']
        self.assertEqual(source['columns'],['passage_id','scope_id','text'])
        catalog={p['passage_id']:p for p in self.catalog['passages']}
        for pid,scope,body in source['rows']:
            self.assertEqual(scope,catalog[pid]['scope_id']);self.assertEqual(body,catalog[pid]['text'])
        self.assertNotIn('sha256',source)

    def test_oversized_prompt_stops_before_any_model_launch(self):
        root=self.root/'corrections';root.mkdir();c.repair.write(root/'initial.json',self.state());c.repair.write(root/'protocol.json',{})
        p={'max_rounds':2,'max_tokens':100,'max_prompt_chars':1}
        self.assertEqual(c.replay(root,p,self.bundle,self.catalog,'Fictional')['status'],'prompt_too_large')

    def test_verified_imported_proposal_proceeds_directly_to_independent_review(self):
        root=self.root/'corrections';root.mkdir();state=self.state()
        c.repair.write(root/'initial.json',state);c.repair.write(root/'protocol.json',{})
        old=self.root/'old-proposal';old.mkdir();plan=self.plan(state)
        base.save(old/'output.json',plan)
        request={'model':c.MODEL[0],'effort':c.MODEL[1],'bindings':{'snapshot_sha256':base.digest(state),'role':'propose'}}
        base.save(old/'request.json',request)
        result={'content':plan,'receipt':{'session':{'id':'old-session','usage':{'totalTokens':75}}}}
        p={'max_rounds':2,'max_tokens':100,'imported_proposal':{'job':str(old),'output_sha256':base.sha(old/'output.json')}}
        with patch.object(c,'verify_job',return_value=result):
            n=c.replay(root,p,self.bundle,self.catalog,'Fictional')
            self.assertEqual(n['role'],'review');self.assertEqual(n['status'],'pending');self.assertEqual(n['tokens'],0)
            self.assertFalse((root/'rounds/0/propose').exists())
            p['inherited_tokens']=100
            self.assertEqual(c.replay(root,p,self.bundle,self.catalog,'Fictional')['status'],'budget_exhausted')
            request['bindings']['snapshot_sha256']='different';(old/'request.json').write_text(json.dumps(request))
            with self.assertRaises(ValueError):c.replay(root,p,self.bundle,self.catalog,'Fictional')

    def test_copy_context_into_basis_is_typed_and_preserves_data(self):
        state=self.state();state['format']['basis']={'text':'Fictional redundant basis.','citations':['D001']}
        op=self.op(state,'basis');op.pop('value')
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(op='copy_context',source_id=key,source_sha256=source['sha256'],old_text=state['format']['basis']['text'])
        result=c.apply(state,self.plan(state,op),self.bundle,self.catalog)
        self.assertEqual(result['format']['basis'],{'text':source['value']['text'],'citations':['D001','D002']})
        self.assertEqual(result['artifacts'],state['artifacts'])
        state['artifacts']['financial']['context'][0]['text']='x'*241
        key,source=next(iter(c.registry(state,self.bundle)['context_sources'].items()))
        op.update(source_id=key,source_sha256=source['sha256'])
        with self.assertRaisesRegex(ValueError,'limit 240'):c.apply(state,self.plan(state,op),self.bundle,self.catalog)
