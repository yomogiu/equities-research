"""Fictional metadata remediation; no real sources, models or credentials."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_remediation as m
from research import earnings_experiment as base
from research import earnings_signals as signals


class RemediationTests(PassageFixture, unittest.TestCase):
    def state(self):
        financial = copy.deepcopy(self.financial)
        financial['context'] = [{'text': 'Fictional old comparison.', 'citations': ['D002']}]
        financial['gaps'] = ['Fictional old gap.']
        retrieval = copy.deepcopy(self.retrieval)
        retrieval['document_findings'] = [{'text': 'Fictional attribution.', 'citations': ['D001']}]
        return {'artifacts': {'financial': financial, 'retrieval': retrieval, 'analysis': copy.deepcopy(self.report)},
                'format': copy.deepcopy(m.corrections.EMPTY_FORMAT),
                'findings': [{'id': 'finding-fake', 'finding': {'reason': 'Fictional incorrect metadata'}}]}

    def operation(self, state, path=None, value='Fictional corrected comparison.', kind='text'):
        path = path or ['artifacts', 'financial', 'context', 0, 'text']
        old = m.targets(state, self.bundle)[tuple(path)]['value']
        return {'id': 'change-1', 'path': path, 'kind': kind, 'before_sha256': base.digest(old),
                'after_sha256': base.digest(value), 'value': value, 'reason': 'Fictional original evidence',
                'citations': ['D001'], 'passage_ids': [self.ids[0]]}

    def plan(self, state=None, op=None):
        state = state or self.state()
        return {'snapshot_sha256': base.digest(state), 'operations': [op or self.operation(state)]}

    def review(self, before, plan, candidate, verdict='pass', approve=True):
        claim = {'reason': 'Fictional independent verification', 'citations': ['D001'], 'passage_ids': [self.ids[0]]}
        return {'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan),
                'approve_patch': approve, 'verdict': verdict,
                'criteria': {k: {'status': 'pass' if verdict == 'pass' else 'fail', 'evidence': 'Fictional assessment'} for k in m.legacy.CRITERIA},
                'operations': [{'id': op['id'], 'approve': approve, **claim} for op in plan['operations']],
                'resolutions': [{'id': f['id'], 'status': 'closed' if verdict == 'pass' else 'open', **claim} for f in before['findings']],
                'findings': []}

    def edition(self):
        self.seed = self.root/'seed'; self.seed.mkdir()
        writing = self.root/'writing.txt'; writing.write_text('Fictional concise writing rubric.')
        sp = {'code': [], 'case_path': str(self.casepath), 'case_sha256': base.sha(self.casepath),
              'writing_standard': str(writing), 'writing_sha256': base.sha(writing),
              'evidence_manifest': str(self.root/'evidence/manifest.json'), 'evidence_sha256': base.sha(self.root/'evidence/manifest.json')}
        old = {'version': m.corrections.VERSION, 'code': [], 'source_protocol': sp, 'source_bindings': {}}
        m.repair.write(self.seed/'protocol.json', old)
        state = self.state(); plan = self.plan(state)
        auth = {'kind': 'targeted_remediation', 'enabled': True, 'authorization_id': 'explicit-fake-authority',
                'source_protocol_sha256': base.sha(self.seed/'protocol.json'), 'first_plan_sha256': base.digest(plan),
                'max_review_attempts': 2, 'max_tokens': 10000, 'reason': 'Explicit fictional new edition',
                'output_path': str(self.root/'remediation')}
        exported = {'status': 'blocked', 'snapshot': state, 'source_protocol': sp, 'prior_rounds': 2, 'prior_tokens': 54321}
        output = self.root/'remediation'
        exporter = patch.object(m, 'export_seed', return_value=(old, exported))
        exporter.start(); self.addCleanup(exporter.stop)
        m.initialize(self.seed, output, plan, auth)
        return output

    def complete(self, output, verdict='pass', approve=True, session='fresh-review'):
        p, b, cat, w = m.load(output); progress = m._replay(output, p, b, cat, w)
        job = progress['job']; job.mkdir(parents=True)
        plan = base.read(job.parent/'plan.json'); candidate = base.read(job.parent/'candidate.json')
        m.repair.write(job/'request.json', {'bindings': progress['bindings'], 'model': m.MODEL[0], 'effort': m.MODEL[1]})
        (job/'prompt.txt').write_text(progress['prompt'])
        result = {'content': self.review(progress['state'], plan, candidate, verdict, approve),
                  'receipt': {'session': {'id': session, 'usage': {'totalTokens': 123}}}}
        m.repair.write(job/'output.json', result)
        return result

    def test_metadata_patch_preserves_facts_quotes_membership_and_unrelated_fields(self):
        state = self.state(); original = copy.deepcopy(state)
        candidate = m.apply(state, self.plan(state), self.bundle, self.catalog)
        self.assertEqual(state, original)
        self.assertNotEqual(candidate['artifacts']['financial']['context'], state['artifacts']['financial']['context'])
        for role in ('retrieval', 'analysis'): self.assertEqual(candidate['artifacts'][role], state['artifacts'][role])
        self.assertEqual(candidate['artifacts']['financial']['rows'], state['artifacts']['financial']['rows'])
        self.assertEqual(candidate['findings'], state['findings'])

    def test_all_requested_metadata_paths_and_display_are_bounded(self):
        state = self.state()
        for path in [['artifacts','financial','gaps',0], ['artifacts','retrieval','exchange_coverage',0,'answer'],
                     ['artifacts','retrieval','document_findings',0,'text'], ['artifacts','analysis','opening']]:
            with self.subTest(path=path): m.apply(state, self.plan(state,self.operation(state,path)), self.bundle,self.catalog)
        row = next(iter(m.repair.row_catalog(state['artifacts']['financial'], self.bundle)))
        value = {'label': 'Fictional row', 'dimensions': '', 'citations': ['D001']}
        op = self.operation(state,['format','rows',row],value,'display_row')
        self.assertEqual(op['before_sha256'],base.digest(None))
        self.assertEqual(m.apply(state,self.plan(state,op),self.bundle,self.catalog)['format']['rows'][row],value)

    def test_forbidden_paths_types_hashes_duplicates_and_unknown_ids_fail_atomically(self):
        state = self.state(); op = self.operation(state)
        bad = [{**op,'path':['artifacts','financial','rows',0,'fact_ids']},
               {**op,'path':['artifacts','financial','rows',0,'label']},
               {**op,'path':['artifacts','retrieval','quotes']},
               {**op,'path':['artifacts','retrieval','selected_document_ids']},
               {**op,'path':['artifacts','retrieval','exchange_coverage',0,'exchange_id']},
               {**op,'path':['artifacts','financial','context',True,'text']},
               {**op,'path':['artifacts','financial','context',-1,'text']},
               {**op,'before_sha256':'stale'}, {**op,'after_sha256':'stale'},
               {**op,'kind':'citations'}, {**op,'extra':'forbidden'}, {**op,'passage_ids':['invented']}]
        for item in bad:
            with self.subTest(item=item), self.assertRaises((ValueError,KeyError)):
                m.apply(state,self.plan(state,item),self.bundle,self.catalog)
        plan = self.plan(state); plan['operations'].append({**op,'id':'second'})
        with self.assertRaisesRegex(ValueError,'Duplicate'):m.apply(state,plan,self.bundle,self.catalog)
        self.assertEqual(state,self.state())

    def test_authorization_and_historical_budget_preserved_without_author_calls(self):
        out = self.edition(); p = base.read(out/'protocol.json')
        self.assertEqual(p['history'],{'status':'blocked','prior_rounds':2,'prior_tokens':54321})
        with patch.object(m,'run_role') as run:
            self.assertEqual(m.verify(out)['status'],'pending');run.assert_not_called()
        self.assertFalse((out/'result.json').exists())
        auth=base.read(out/'authorization.json');auth['reason']='changed';(out/'authorization.json').write_text(json.dumps(auth))
        with self.assertRaisesRegex(ValueError,'authorization'):m.load(out)

    def test_full_source_review_includes_original_and_staged_metadata_and_writing(self):
        state=self.state();plan=self.plan(state);candidate=m.apply(state,plan,self.bundle,self.catalog)
        text=m.prompt(state,plan,candidate,self.bundle,self.catalog,'Fictional strict writing standard')
        for word in ('original_evidence','original_artifacts','field_changes','Fictional strict writing standard',
                     'Fictional old comparison.','Fictional corrected comparison.'):
            self.assertIn(word,text)

    def test_passing_fresh_review_is_only_route_to_result_and_signals_export(self):
        out=self.edition();self.complete(out)
        with patch.object(m,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            result=m.verify(out);self.assertEqual(result['status'],'accepted')
            self.assertEqual(m.verify(out),result)
        self.assertTrue((out/'report.html').exists())
        self.assertEqual(base.read(out/'result.json')['state']['findings'],[])
        self.assertIn("p['version']=='targeted-remediation-v1'",signals.EXPORT)

    def test_revise_commits_approved_state_and_requires_changed_second_plan(self):
        out=self.edition();self.complete(out,'revise')
        with patch.object(m,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            result=m.verify(out);self.assertEqual(result['status'],'awaiting_plan');self.assertFalse((out/'result.json').exists())
            after=base.read(out/'attempts/0/decision.json')['after']
            self.assertEqual(after['artifacts']['financial']['context'][0]['text'],'Fictional corrected comparison.')
            op=self.operation(after,['artifacts','analysis','opening'],'Fictional revised opening.')
            m.stage_plan(out,self.plan(after,op));self.complete(out,session='second-fresh-review')
            self.assertEqual(m.verify(out)['status'],'accepted')
            with self.assertRaisesRegex(ValueError,'second plan'):m.stage_plan(out,self.plan(after,op))

    def test_rejected_atomic_patch_preserves_data_and_identical_retry_is_refused(self):
        out=self.edition();self.complete(out,'revise',False)
        with patch.object(m,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            m.verify(out);after=base.read(out/'attempts/0/decision.json')['after']
            self.assertEqual(after,self.state())
            with self.assertRaisesRegex(ValueError,'Unchanged'):m.stage_plan(out,self.plan(after))

    def test_pending_uncertain_and_blocked_cannot_get_second_plan(self):
        out=self.edition()
        with self.assertRaisesRegex(ValueError,'second plan'):m.stage_plan(out,self.plan())
        job=out/'attempts/0/review';job.mkdir();m.repair.write(job/'request.json',{'unobserved':True})
        with patch.object(m,'run_role') as run:
            self.assertEqual(m.advance(out,True)['status'],'launch_uncertain');run.assert_not_called()
        with self.assertRaisesRegex(ValueError,'second plan'):m.stage_plan(out,self.plan())

    def test_review_session_reuse_and_seed_change_are_rejected(self):
        out=self.edition();self.complete(out,'revise')
        with patch.object(m,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            m.verify(out);after=base.read(out/'attempts/0/decision.json')['after']
            m.stage_plan(out,self.plan(after,self.operation(after,['artifacts','analysis','opening'],'Another fictional opening.')))
            self.complete(out,session='fresh-review')
            with self.assertRaisesRegex(ValueError,'fresh independent'):m.verify(out)
        (self.seed/'protocol.json').write_text('{}')
        with self.assertRaises(ValueError):m.load(out)

    def test_two_reviews_are_terminal_and_never_reset_historical_usage(self):
        out=self.edition();self.complete(out,'revise')
        with patch.object(m,'verify_job',side_effect=lambda job:base.read(job/'output.json')):
            m.verify(out);after=base.read(out/'attempts/0/decision.json')['after']
            m.stage_plan(out,self.plan(after,self.operation(after,['artifacts','analysis','opening'],'Another fictional opening.')))
            self.complete(out,'revise',session='second-review')
            result=m.verify(out);self.assertEqual(result['status'],'blocked');self.assertEqual(result['review_attempts'],2)
            self.assertFalse((out/'result.json').exists())
            with self.assertRaises(ValueError):m.stage_plan(out,self.plan(after))
        self.assertEqual(base.read(out/'protocol.json')['history']['prior_tokens'],54321)


if __name__ == '__main__': unittest.main()
