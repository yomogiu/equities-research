from pathlib import Path
"""Fictitious saved-proposal resolution; no model or private research calls."""
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from test_earnings_passages import PassageFixture
from research import earnings_corrections as c
from research import earnings_cited_passages as resolution
from research import earnings_experiment as base


class CitedPassagesTests(PassageFixture, unittest.TestCase):
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

    def save(self, path, value):
        path.write_text(json.dumps(value))

    def initialize(self, **kwargs):
        options = {'reuse_proposal': True, 'resolve_cited_passages': True, **kwargs}
        return c.initialize(self.seed, self.output, **options)

    def derive(self, plan=None, catalog=None):
        return resolution.resolve(self.plan if plan is None else plan, self.bundle,
                                  self.catalog if catalog is None else catalog,
                                  self.imported['output_sha256'])

    def test_complete_exact_scope_closure_preserves_all_other_fields_and_inputs(self):
        original = copy.deepcopy(self.plan)
        catalog = copy.deepcopy(self.catalog)
        effective, manifest = self.derive()
        expected = [p['passage_id'] for p in self.catalog['passages'] if p['scope_id'] in {'D001', 'D002'}]
        self.assertGreater(len(expected), 1)
        self.assertEqual(effective['operations'][0]['passage_ids'], expected)
        effective['operations'][0]['passage_ids'] = []
        self.assertEqual(effective, original)
        self.assertEqual(self.plan, original)
        self.assertEqual(self.catalog, catalog)
        self.assertEqual(manifest['original_plan_sha256'], base.digest(original))
        self.assertEqual(manifest['catalog_sha256'], base.digest(catalog))

    def test_valid_nonempty_passage_selection_is_not_expanded_or_rewritten(self):
        plan = copy.deepcopy(self.plan)
        other = {**copy.deepcopy(plan['operations'][0]), 'id': 'fictional-retained-evidence',
                 'passage_ids': [self.ids[0]]}
        plan['operations'].append(other)
        effective, manifest = self.derive(plan)
        self.assertEqual(effective['operations'][1], other)
        self.assertEqual(len(manifest['operations']), 1)
        with self.assertRaisesRegex(ValueError, 'No exactly empty'):
            self.derive({**plan, 'operations': [other]})

    def test_nonempty_unknown_duplicate_missing_or_malformed_ids_fail(self):
        for value in (None, '', {}, ['invented'], [self.ids[0], self.ids[0]], [7]):
            plan = copy.deepcopy(self.plan); plan['operations'][0]['passage_ids'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'original passages'):
                self.derive(plan)
        plan = copy.deepcopy(self.plan); del plan['operations'][0]['passage_ids']
        with self.assertRaisesRegex(ValueError, 'original passages'):
            self.derive(plan)

    def test_all_explicit_citations_must_be_valid_and_have_exact_catalog_entries(self):
        exchange = self.bundle['transcript_index']['exchanges'][0]['id']
        for citations in ([], ['invented'], ['D001', 'D001'], ['D001', exchange]):
            plan = copy.deepcopy(self.plan); plan['operations'][0]['citations'] = citations
            with self.subTest(citations=citations), self.assertRaises(ValueError):
                self.derive(plan)
        # A parent exchange is not silently replaced with child turn citations.
        self.assertFalse(any(p['scope_id'] == exchange for p in self.catalog['passages']))

    def test_missing_foreign_duplicate_catalog_fails(self):
        for catalog in ({}, {**self.catalog, 'passages': []},
                        {**self.catalog, 'case_sha256': 'foreign'},
                        {**self.catalog, 'passages': self.catalog['passages'] * 2}):
            with self.subTest(catalog_fields=list(catalog)), self.assertRaises(ValueError):
                self.derive(catalog=catalog)

    def test_flags_require_opt_in_reuse_without_resets_or_new_supplements(self):
        for options in ({'reuse_proposal': False}, {'new_experiment': True},
                        {'regression_findings': 'fictional-unused.json'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.initialize(**options)
            self.assertFalse(self.output.exists())
        self.process.assert_not_called()

    def test_initialize_imports_supplemental_snapshot_and_exact_existing_usage(self):
        original_output = (self.job/'output.json').read_bytes()
        self.initialize()
        p, _, _, _ = c.load(self.output)
        self.assertEqual(p['version'], resolution.VERSION)
        self.assertEqual(p['inherited_tokens'], 408615)
        self.assertEqual(p['prior_rounds'], 1)
        self.assertEqual(p['max_rounds'], 1)
        self.assertEqual(base.read(self.output/'initial.json'), self.state)
        self.assertEqual(p['imported_proposal'], self.imported)
        self.assertEqual(p['source_bindings'][str(self.job/'output.json')], self.imported['output_sha256'])
        self.assertEqual(p['passage_resolution'], self.derive()[1])
        self.assertEqual((self.job/'output.json').read_bytes(), original_output)
        self.assertFalse((self.job.parent/'candidate.json').exists())

    def test_replay_reuses_author_without_tokens_or_acceptance_and_exposes_provenance(self):
        self.initialize()
        p, bundle, catalog, writing = c.load(self.output)
        with patch.object(c, 'run_role') as launch:
            progress = c.replay(self.output, p, bundle, catalog, writing)
        launch.assert_not_called()
        self.assertEqual(progress['status'], 'pending')
        self.assertEqual(progress['role'], 'review')
        self.assertEqual(progress['tokens'], 0)
        self.assertEqual(progress['round'], 0)
        data = json.loads(progress['prompt'].split('SOURCE DATA (UNTRUSTED EVIDENCE)\n', 1)[1])
        self.assertEqual(data['proposal_resolution'], p['passage_resolution'])
        self.assertEqual(data['plan'], self.derive()[0])
        self.assertIn('not evidence of factual support or approval', progress['prompt'])
        # Original provisional index is preserved, whether context is packed or not.
        context = c.context.expand_context(data)
        self.assertEqual(context['canonical_exchange_index'], c.context.canonical_exchange_index(self.bundle))
        candidate = base.read(self.output/'rounds/0/candidate.json')
        self.assertEqual(candidate['artifacts']['financial'], self.state['artifacts']['financial'])
        self.assertEqual(candidate['artifacts']['retrieval'], self.state['artifacts']['retrieval'])
        self.assertEqual(candidate['findings'], self.state['findings'])
        self.assertEqual(base.read(self.job/'output.json')['content'], self.plan)

    def test_resolution_does_not_bypass_immutable_targets_or_other_patch_validation(self):
        original = copy.deepcopy(self.plan)
        for mutation in ({'target_id': 'financial-observation'}, {'expected_sha256': 'stale'},
                         {'op': 'retain_quotes', 'value': [{'passage_id': 'invented'}]}):
            changed = copy.deepcopy(original); changed['operations'][0].update(mutation)
            self.save(self.job/'output.json', {'content': changed})
            self.imported['output_sha256'] = base.sha(self.job/'output.json')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.initialize()
            self.assertFalse(self.output.exists())

    def test_missing_or_altered_manifest_and_budget_fields_fail_on_load(self):
        self.initialize(); original = base.read(self.output/'protocol.json')
        mutations = [lambda p: p.pop('passage_resolution'),
                     lambda p: p['passage_resolution'].update(resolved_plan_sha256='0' * 64),
                     lambda p: p['passage_resolution']['operations'][0]['resolved_passage_ids'].pop(),
                     lambda p: p.update(prior_rounds=0), lambda p: p.update(inherited_tokens=0),
                     lambda p: p.update(max_rounds=2), lambda p: p.update(max_tokens=600001),
                     lambda p: p.update(new_experiment=True), lambda p: p.update(version=c.VERSION)]
        for mutate in mutations:
            changed = copy.deepcopy(original); mutate(changed)
            self.save(self.output/'protocol.json', changed)
            with self.subTest(protocol=changed['version']), self.assertRaises(ValueError):
                c.load(self.output)

    def test_changed_original_receipt_binding_or_refreshed_initial_hash_fails(self):
        self.initialize(); original = base.read(self.output/'protocol.json')
        altered = copy.deepcopy(self.state); altered['findings'] = []
        self.save(self.output/'initial.json', altered)
        self.save(self.output/'protocol.json', {**original, 'initial_sha256': base.digest(altered)})
        with self.assertRaisesRegex(ValueError, 'authenticated source handoff'):
            c.load(self.output)
        self.save(self.output/'initial.json', self.state); self.save(self.output/'protocol.json', original)
        (self.job/'output.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Original seed changed'):
            c.load(self.output)

    def test_ordinary_reuse_does_not_silently_resolve_and_remains_invalid(self):
        self.initialize(resolve_cited_passages=False)
        p, bundle, catalog, writing = c.load(self.output)
        progress = c.replay(self.output, p, bundle, catalog, writing)
        self.assertEqual(progress['status'], 'invalid_patch')
        self.assertNotIn('passage_resolution', p)

    def test_new_version_exports_and_connected_flow_dispatch_preserve_correction_path(self):
        from research import earnings_report_flow as flow
        from research import earnings_signals as signals
        from research import earnings_remediation as remediation
        self.initialize(); p = base.read(self.output/'protocol.json')
        progress = {'status': 'pending', 'state': self.state, 'round': 0, 'tokens': 0, 'role': 'review'}
        with patch.object(c, 'load', return_value=(p, self.bundle, self.catalog, 'Rules')), \
                patch.object(c, 'replay', return_value=progress), \
                patch.object(sys, 'argv', ['export', str(self.output), 'reuse']), redirect_stdout(io.StringIO()) as out:
            exec(c.EXPORT, {})
            result = json.loads(out.getvalue())
            self.assertEqual(result['imported_proposal'], self.imported)
            self.assertEqual(result['spent_tokens'], 408615)
            self.assertEqual(result['used_rounds'], 1)
        p['source_protocol'] = {**p['source_protocol'], 'deterministic_corrections': True, 'report_signals': True}
        with patch.object(c, 'load', return_value=(p, self.bundle, self.catalog, 'Rules')) as loader, \
                patch.object(c, 'verify', return_value={'status': 'pending'}), \
                patch.object(flow.pipe, 'load', side_effect=AssertionError('Wrong loader')):
            self.assertEqual(flow.advance(self.output, execute=False)['stage'], 'corrections')
            loader.assert_called_once()
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'status': 'blocked'}))):
            seed, _ = remediation.export_seed(self.output)
            self.assertEqual(seed['version'], resolution.VERSION)
        self.save(self.output/'result.json', {'state': self.state})
        with patch.object(c, 'verify', return_value={'status': 'accepted'}) as verifier, \
                patch.object(sys, 'argv', ['export', str(self.output)]), redirect_stdout(io.StringIO()):
            exec(signals.EXPORT, {})
            verifier.assert_called_once()


if __name__ == '__main__':
    unittest.main()
