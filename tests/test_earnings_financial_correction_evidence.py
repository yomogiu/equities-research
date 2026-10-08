"""Synthetic financial-only saved-plan recovery; no external/model calls."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import test_earnings_cited_passages as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_corrections as c
from research import earnings_financial_correction_evidence as fe
from research import earnings_experiment as base


class FinancialCorrectionEvidenceTests(PassageFixture, unittest.TestCase):
    save = fixtures.CitedPassagesTests.save

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.writing = self.root/'writing.txt'
        self.writing.write_text('Fictitious concise standard.')
        self.seed = self.root/'seed'
        c.pipe.freeze(self.casepath, self.seed, self.writing)
        self.sp = base.read(self.seed/'protocol.json')
        self.bundle = c.evidence.load_bundle(self.sp['evidence_manifest'])
        self.catalog = c.passages.catalog(self.bundle['manifest'])
        self.state = {'artifacts': {'financial': copy.deepcopy(self.financial),
                                  'retrieval': copy.deepcopy(self.retrieval),
                                  'analysis': copy.deepcopy(self.report)},
                      'format': copy.deepcopy(c.EMPTY_FORMAT),
                      'findings': [{'id': 'fictional-supplemental-finding',
                                    'finding': {'reason': 'Fictitious unresolved audit issue'}}]}
        target, row = next((k, v) for k, v in c.registry(self.state, self.bundle)['targets'].items()
                           if v['path'] == ['artifacts', 'analysis', 'scope'])
        self.plan = {'snapshot_sha256': base.digest(self.state), 'operations': [{
            'id': 'fictional-scope-edit', 'target_id': target, 'expected_sha256': row['expected_sha256'],
            'op': 'replace_text', 'value': 'Fictitious corrected scope.',
            'reason': 'Fictitious proposed scope change, pending independent review.',
            'citations': ['D001', 'D002'], 'passage_ids': []}]}
        self.job = self.seed/'rounds/0/propose'
        self.job.mkdir(parents=True)
        self.save(self.job/'output.json', {'content': self.plan})
        self.save(self.job/'request.json', {'model': c.MODEL[0], 'effort': c.MODEL[1],
                  'bindings': {'snapshot_sha256': base.digest(self.state), 'role': 'propose'}})
        self.imported = {'job': str(self.job), 'output_sha256': base.sha(self.job/'output.json')}
        seed_protocol = copy.deepcopy(self.sp)
        seed_protocol.update(version=c.regression.VERSION, max_tokens=600000)
        self.save(self.seed/'protocol.json', seed_protocol)
        self.exported = {'snapshot': self.state, 'source_protocol': self.sp, 'used_rounds': 1,
                         'spent_tokens': 408615, 'imported_proposal': self.imported}
        # Simulate only authenticated source export and the runner receipt. Actual
        # catalog, code, input/output hashes, derivation, apply and review prompt run.
        process = patch.object(c.subprocess, 'run', side_effect=lambda *a, **k:
                               SimpleNamespace(stdout=json.dumps(self.exported)))
        self.process = process.start(); self.addCleanup(process.stop)
        receipt = patch.object(c, 'verify_saved_proposal', side_effect=lambda imported, records: {
            'content': base.read(Path(imported['job'])/'output.json')['content'],
            'receipt': {'session': {'id': 'fictional-original-author', 'usage': {'totalTokens': 116314}}}})
        self.receipt = receipt.start(); self.addCleanup(receipt.stop)
        self.output = self.root/'resolved-continuation'

        self.ordinary = copy.deepcopy(self.plan['operations'][0])
        target, row = next((k,v) for k,v in c.registry(self.state,self.bundle)['targets'].items() if v['kind']=='row')
        source_row = c.repair.row_catalog(self.state['artifacts']['financial'],self.bundle)[row['path'][-1]]
        self.fids = list(dict.fromkeys(fid for cell in source_row['row']['cells'] for fid in cell['fact_ids']))
        self.plan['operations'] = [{'id':'fake-financial-label','target_id':target,'expected_sha256':row['expected_sha256'],
            'op':'set_display','value':{'label':'Fictional source label','dimensions':''},
            'reason':'Fictional source-bound row label correction.','citations':self.fids,'passage_ids':[]}]
        self.save(self.job/'output.json',{'content':self.plan})
        self.imported['output_sha256']=base.sha(self.job/'output.json')

    def derive(self, plan=None):
        return fe.resolve(plan or self.plan,self.state,self.bundle,self.catalog,self.imported['output_sha256'])

    def test_exact_derived_financial_sources_and_row_membership_without_fake_passages(self):
        before=copy.deepcopy(self.plan); passages=copy.deepcopy(self.catalog['passages'])
        plan,manifest=self.derive();op=plan['operations'][0]
        self.assertEqual(self.plan,before);self.assertEqual(self.catalog['passages'],passages)
        self.assertEqual(op['passage_ids'],[])
        self.assertEqual(set(op)-set(before['operations'][0]),{'financial_evidence_ids'})
        self.assertEqual(manifest['original_plan_sha256'],base.digest(before))
        for value in manifest['financial_evidence'].values():
            source=value['source'];self.assertIn('observation',source)
            self.assertTrue(source['spans'][0]['span_sha256'])
        candidate=c.apply(self.state,plan,self.bundle,self.catalog)
        self.assertEqual(candidate['artifacts'],self.state['artifacts'])
        self.assertEqual(manifest['operations'][0]['source_ids'],self.fids)

    def test_mixed_batch_completes_document_passages_without_modifying_author(self):
        self.plan['operations'].append(self.ordinary)
        plan,manifest=self.derive()
        self.assertTrue(plan['operations'][1]['passage_ids'])
        self.assertNotIn('financial_evidence_ids',plan['operations'][1])
        self.assertTrue(manifest['ordinary_passage_operations'])
        c.apply(self.state,plan,self.bundle,self.catalog)

    def test_typed_evidence_cannot_enable_text_edit_or_uncited_foreign_fact(self):
        plan,_=self.derive();op=plan['operations'][0]
        wrong=copy.deepcopy(plan);wrong['operations'][0]={**self.ordinary,'citations':self.fids,
            'passage_ids':[],'financial_evidence_ids':op['financial_evidence_ids']}
        with self.assertRaisesRegex(ValueError,'limited to display rows'):c.apply(self.state,wrong,self.bundle,self.catalog)
        wrong=copy.deepcopy(plan);wrong['operations'][0]['citations']=['D001']
        with self.assertRaises(ValueError):c.apply(self.state,wrong,self.bundle,self.catalog)
        unbound=copy.deepcopy(self.catalog);del unbound[fe.KEY]
        with self.assertRaisesRegex(ValueError,'Explicit financial'):c.apply(self.state,plan,self.bundle,unbound)

    def test_real_but_unrelated_financial_fact_cannot_support_target_row(self):
        other = next(o['id'] for o in self.bundle['financial']['observations'] if o['id'] not in self.fids)
        self.plan['operations'][0]['citations'] = [other]
        with self.assertRaisesRegex(ValueError, 'do not belong'):
            self.derive()

    def test_typed_claim_rejects_unknown_ids_or_passage_piggyback(self):
        plan, _ = self.derive()
        for field, value in [('financial_evidence_ids', ['FE-invented']),
                             ('passage_ids', [self.catalog['passages'][0]['passage_id']])]:
            bad = copy.deepcopy(plan); bad['operations'][0][field] = value
            with self.assertRaises(ValueError):
                c.apply(self.state, bad, self.bundle, self.catalog)

    def test_source_and_manifest_evidence_tampering_rejected(self):
        plan,_=self.derive();bad=copy.deepcopy(self.catalog)
        first=next(iter(bad[fe.KEY].values()));first['source']['spans'][0]['text']='invented'
        with self.assertRaisesRegex(ValueError,'source evidence changed'):c.apply(self.state,plan,self.bundle,bad)
        source=Path(next(iter(self.catalog[fe.KEY].values()))['source']['spans'][0]['path'])
        source.write_bytes(source.read_bytes()+b'changed')
        with self.assertRaises(ValueError):c.apply(self.state,plan,self.bundle,self.catalog)

    def test_reviewer_typed_decision_required_and_exact_candidate_gate_remains(self):
        plan,_=self.derive();candidate=c.apply(self.state,plan,self.bundle,self.catalog);op=plan['operations'][0]
        support={k:copy.deepcopy(op[k]) for k in ('reason','citations','passage_ids','financial_evidence_ids')}
        review=dict(candidate_sha256=base.digest(candidate),plan_sha256=base.digest(plan),approve_patch=True,verdict='pass',
            criteria={k:{'status':'pass','evidence':'Fictitious reviewed evidence.'} for k in c.legacy.CRITERIA},
            operations=[dict(id=op['id'],approve=True,**support)],resolutions=[dict(id=self.state['findings'][0]['id'],status='closed',**support)],findings=[])
        _,status=c.adjudicate(self.state,candidate,plan,review,self.bundle,self.catalog);self.assertEqual(status,'accepted')
        bad=copy.deepcopy(review);bad['operations'][0].pop('financial_evidence_ids');bad['operations'][0]['passage_ids']=[self.catalog['passages'][0]['passage_id']]
        with self.assertRaisesRegex(ValueError,'requires typed'):c.adjudicate(self.state,candidate,plan,bad,self.bundle,self.catalog)
        bad=copy.deepcopy(review);bad['candidate_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'different candidate'):c.adjudicate(self.state,candidate,plan,bad,self.bundle,self.catalog)

    def test_initialize_replay_preserves_original_budget_and_review_context(self):
        c.initialize(self.seed,self.output,reuse_proposal=True,resolve_financial_evidence=True)
        p,bundle,catalog,writing=c.load(self.output)
        self.assertEqual(p['version'],fe.VERSION);self.assertEqual(p['prior_rounds'],1)
        self.assertEqual(p['max_tokens'],600000);self.assertEqual(p['inherited_tokens'],408615)
        self.assertEqual(p['max_rounds'],1);self.assertEqual(base.sha(self.job/'output.json'),self.imported['output_sha256'])
        plan,_=fe.resolve(self.plan,self.state,bundle,catalog,self.imported['output_sha256'])
        candidate=c.apply(self.state,plan,bundle,catalog)
        prompt=c.prompt('review',self.state,bundle,catalog,writing,plan,candidate,passage_resolution=p['passage_resolution'],financial_context_version=p['financial_context_version'])
        self.assertIn('typed_financial_evidence',prompt);self.assertIn('financial_evidence_ids',prompt)
        with patch.object(c.budget,'admission',return_value={'admitted':True}):
            progress=c.replay(self.output,p,bundle,catalog,writing)
        self.assertEqual(progress['status'],'pending');self.assertEqual(progress['role'],'review')
        self.assertEqual(progress['tokens'],0)
        p['passage_resolution']['operations'][0]['row_sha256']='0'*64;self.save(self.output/'protocol.json',p)
        with self.assertRaisesRegex(ValueError,'manifest changed'):c.load(self.output)

    def test_no_budget_or_round_reset_and_no_unrequested_derivation(self):
        with self.assertRaises(ValueError):c.initialize(self.seed,self.output,reuse_proposal=True,resolve_financial_evidence=True,max_tokens=600001)
        with self.assertRaises(ValueError):c.initialize(self.seed,self.output,reuse_proposal=True,resolve_financial_evidence=True,new_experiment=True)
        self.exported['used_rounds']=2
        with self.assertRaisesRegex(ValueError,'exhausted'):c.initialize(self.seed,self.output,reuse_proposal=True,resolve_financial_evidence=True)
