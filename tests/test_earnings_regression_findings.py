"""Fictitious audit handoffs only; no model calls or private research fixtures."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_corrections as c
from research import earnings_experiment as base
from research import earnings_regression_findings as regression


class RegressionFindingsTests(PassageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.writing = self.root / 'writing.txt'
        self.writing.write_text('Fictitious concise standard.')
        self.seed = self.root / 'seed'
        c.pipe.freeze(self.casepath, self.seed, self.writing)
        self.sp = base.read(self.seed / 'protocol.json')
        self.bundle = c.evidence.load_bundle(self.sp['evidence_manifest'])
        self.catalog = c.passages.catalog(self.bundle['manifest'])
        self.original = {'artifacts': {'financial': self.financial, 'retrieval': self.retrieval,
                                      'analysis': self.report},
                         'format': copy.deepcopy(c.EMPTY_FORMAT),
                         'findings': [{'id': 'finding-original-fictional',
                                       'finding': {'reason': 'Fictitious original unresolved issue'}}]}
        self.exported = {'snapshot': self.original, 'source_protocol': self.sp,
                         'used_rounds': 1, 'spent_tokens': 123, 'imported_proposal': None}
        # Only the frozen seed verifier process is simulated. Actual source-code,
        # case, manifest, evidence, audit, and snapshot hashes are exercised.
        mocked = patch.object(c.subprocess, 'run', side_effect=lambda *a, **kw:
                              SimpleNamespace(stdout=json.dumps(self.exported)))
        self.process = mocked.start(); self.addCleanup(mocked.stop)
        self.audit = self.root / 'fictional-audit.json'
        self.audit.write_text('{"notice":"Fictitious fallible audit, not approval"}')
        self.finding = {'target': 'analysis', 'passage': 'Fictitious omitted comparison',
                        'reason': 'The fictional comparison could change the conclusion.',
                        'required_change': 'Check the fictional comparison against the original source.',
                        'citations': ['D001'], 'passage_ids': [self.ids[0]]}
        self.supplement = self.root / 'fictional-regressions.json'
        self.value = {'version': 1, 'case_sha256': self.sp['case_sha256'],
                      'evidence_sha256': self.sp['evidence_sha256'],
                      'audit': {'path': str(self.audit), 'sha256': base.sha(self.audit)},
                      'findings': [self.finding]}
        self.save(self.supplement, self.value)
        self.output = self.root / 'continuation'

    def save(self, path, value):
        path.write_text(json.dumps(value))

    def initialize(self, **kwargs):
        return c.initialize(self.seed, self.output, regression_findings=self.supplement, **kwargs)

    def test_appends_stable_pending_ids_binds_both_files_and_preserves_budget(self):
        before = copy.deepcopy(self.original)
        result = self.initialize()
        p, _, _, _ = c.load(self.output)
        initial = base.read(self.output / 'initial.json')
        self.assertEqual(initial['findings'][0], before['findings'][0])
        self.assertEqual(initial['findings'][1],
                         {'id': c.repair.finding_id(self.finding), 'finding': self.finding})
        self.assertEqual(initial['artifacts'], before['artifacts'])
        self.assertEqual(initial['format'], before['format'])
        self.assertEqual(self.original, before)
        self.assertEqual(result, {'status': 'pending', 'max_rounds': 1, 'findings': 2})
        self.assertEqual(p['inherited_tokens'], 123)
        self.assertEqual(p['prior_rounds'], 1)
        self.assertEqual(p['version'], regression.VERSION)
        self.assertIsNone(p['max_tokens'])
        self.assertFalse(p['new_experiment'])
        self.assertIsNone(p['imported_proposal'])
        for path in (self.audit, self.supplement):
            self.assertEqual(p['source_bindings'][str(path.resolve())], base.sha(path))
        self.assertTrue(any(row['path'].endswith('/earnings_regression_findings.py') for row in p['code']))

    def test_rejects_schema_hash_id_text_and_count_errors_before_output_creation(self):
        mutations = [lambda v: v.update(extra=True), lambda v: v.update(version=True),
                     lambda v: v.update(case_sha256='0' * 64),
                     lambda v: v.update(evidence_sha256='0' * 64),
                     lambda v: v['audit'].update(extra=True),
                     lambda v: v['audit'].update(sha256='0' * 64),
                     lambda v: v['audit'].update(path='relative.json'),
                     lambda v: v.update(findings=[]),
                     lambda v: v.update(findings=v['findings'] * 13),
                     lambda v: v.update(findings=v['findings'] * 2),
                     lambda v: v['findings'][0].update(target='unbounded'),
                     lambda v: v['findings'][0].update(reason=' '),
                     lambda v: v['findings'][0].update(passage='x' * 4001),
                     lambda v: v['findings'][0].update(required_change=None),
                     lambda v: v['findings'][0].update(citations=['foreign-case']),
                     lambda v: v['findings'][0].update(citations=[]),
                     lambda v: v['findings'][0].update(passage_ids=['Pforeign-case']),
                     lambda v: v['findings'][0].update(passage_ids=[]),
                     lambda v: v['findings'][0].update(approved=True)]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(self.value); mutate(value)
            self.save(self.supplement, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.initialize()
            self.assertFalse(self.output.exists())

    def test_rejects_changed_case_and_manifest_files_before_output_creation(self):
        for key in ('case_path', 'evidence_manifest'):
            from pathlib import Path
            path = Path(self.sp[key]); original = path.read_bytes()
            path.write_bytes(original + b' ')
            try:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    self.initialize()
                self.assertFalse(self.output.exists())
            finally:
                path.write_bytes(original)

    def test_cannot_reuse_proposal_reset_rounds_or_escape_exhausted_budget(self):
        for flag in ('reuse_proposal', 'new_experiment'):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'cannot reuse'):
                self.initialize(**{flag: True})
            self.assertFalse(self.output.exists())
        self.exported['used_rounds'] = 2
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.initialize()
        self.assertFalse(self.output.exists())

    def test_changed_supplement_or_audit_is_rejected_on_load(self):
        self.initialize()
        for path in (self.audit, self.supplement):
            original = path.read_bytes(); path.write_bytes(original + b' ')
            try:
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'seed changed'):
                    c.load(self.output)
            finally:
                path.write_bytes(original)

    def test_findings_cannot_be_removed_injected_or_rewritten_with_new_snapshot_hash(self):
        self.initialize()
        initial = base.read(self.output / 'initial.json')
        protocol = base.read(self.output / 'protocol.json')
        mutations = [lambda v: v['findings'].pop(), lambda v: v['findings'].pop(0),
                     lambda v: v['findings'].append({'id': 'injected', 'finding': self.finding}),
                     lambda v: v['findings'][1]['finding'].update(reason='Changed fictional claim'),
                     lambda v: v['artifacts']['analysis'].update(opening='Injected prose')]
        for index, mutate in enumerate(mutations):
            altered = copy.deepcopy(initial); mutate(altered)
            self.save(self.output / 'initial.json', altered)
            self.save(self.output / 'protocol.json', {**protocol, 'initial_sha256': base.digest(altered)})
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'source plus additions'):
                c.load(self.output)

    def test_missing_supplemental_or_audit_binding_is_rejected(self):
        self.initialize(); protocol = base.read(self.output / 'protocol.json')
        for path in (self.audit, self.supplement):
            altered = copy.deepcopy(protocol); altered['source_bindings'].pop(str(path.resolve()))
            self.save(self.output / 'protocol.json', altered)
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'source binding changed'):
                c.load(self.output)

    def test_missing_supplemental_record_cannot_remove_added_findings(self):
        self.initialize()
        protocol = base.read(self.output / 'protocol.json')
        protocol.pop('regression_findings')
        protocol['initial_sha256'] = base.digest(self.original)
        self.save(self.output / 'initial.json', self.original)
        self.save(self.output / 'protocol.json', protocol)
        with self.assertRaisesRegex(ValueError, 'Regression findings binding'):
            c.load(self.output)

    def test_load_rejects_changed_inherited_usage_and_expanded_budgets(self):
        self.initialize(); protocol = base.read(self.output / 'protocol.json')
        for key, value in (('prior_rounds', 0), ('inherited_tokens', 0), ('max_rounds', 2),
                           ('max_tokens', 600001), ('prior_rounds', True), ('inherited_tokens', '123')):
            altered = {**protocol, key: value}
            self.save(self.output / 'protocol.json', altered)
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'budget'):
                c.load(self.output)

    def test_seed_token_ceiling_cannot_expand_at_initialization(self):
        seed_protocol = base.read(self.seed / 'protocol.json')
        seed_protocol['max_tokens'] = 300000
        self.save(self.seed / 'protocol.json', seed_protocol)
        with self.assertRaisesRegex(ValueError, 'token budget expanded'):
            self.initialize(max_tokens=300001)
        self.assertFalse(self.output.exists())
        self.initialize(max_tokens=300000)
        protocol, _, _, _ = c.load(self.output)
        self.assertEqual(protocol['max_tokens'], 300000)

    def test_exporters_dispatch_supplemental_protocol_through_correction_verifier(self):
        import contextlib
        import io
        import sys
        from research import earnings_remediation as remediation
        from research import earnings_signals as signals
        self.initialize()
        protocol = base.read(self.output / 'protocol.json')
        initial = base.read(self.output / 'initial.json')
        progress = {'status': 'blocked', 'state': initial, 'round': 0, 'tokens': 0}
        with patch.object(c, 'load', return_value=(protocol, self.bundle, self.catalog, 'Fictional')) as loader, \
                patch.object(c, 'replay', return_value=progress), \
                patch.object(sys, 'argv', ['export', str(self.output)]), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            exec(c.EXPORT, {})
            self.assertEqual(json.loads(stdout.getvalue())['snapshot'], initial)
            loader.assert_called_once()
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({
                'status': 'blocked', 'snapshot': initial, 'source_protocol': self.sp,
                'prior_rounds': 1, 'prior_tokens': 123}))):
            inherited, _ = remediation.export_seed(self.output)
            self.assertEqual(inherited['version'], regression.VERSION)
        self.save(self.output / 'result.json', {'state': initial})
        with patch.object(c, 'verify', return_value={'status': 'accepted'}) as verifier, \
                patch.object(sys, 'argv', ['export', str(self.output)]), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            exec(signals.EXPORT, {})
            self.assertEqual(json.loads(stdout.getvalue())['state']['artifacts'], initial['artifacts'])
            verifier.assert_called_once()

    def test_report_coordinator_routes_supplemental_protocol_to_corrections(self):
        from research import earnings_report_flow as flow
        self.initialize()
        protocol, bundle, catalog, writing = c.load(self.output)
        protocol['source_protocol'].update(deterministic_corrections=True, report_signals=True)
        with patch.object(c, 'load', return_value=(protocol, bundle, catalog, writing)) as loader, \
                patch.object(c, 'verify', return_value={'status': 'pending'}) as verifier, \
                patch.object(c, 'advance') as worker, \
                patch.object(c.pipe, 'load', side_effect=AssertionError('Wrong pipeline dispatch')):
            result = flow.advance(self.output, execute=False)
        self.assertEqual(result['stage'], 'corrections')
        self.assertEqual(result['status'], 'pending')
        loader.assert_called_once_with(self.output.resolve())
        verifier.assert_called_once_with(self.output.resolve())
        worker.assert_not_called()

    def test_duplicate_original_finding_is_retained_once_and_inputs_are_immutable(self):
        existing = {'id': c.repair.finding_id(self.finding), 'finding': self.finding}
        snapshot = {**self.original, 'findings': [existing]}
        self.assertEqual(regression.append(snapshot, [self.finding]), snapshot)
        self.assertEqual(regression.append(snapshot, [self.finding]), regression.append(snapshot, [self.finding]))

    def test_ordinary_protocol_still_loads_without_new_record(self):
        c.initialize(self.seed, self.output)
        protocol, _, _, _ = c.load(self.output)
        self.assertEqual(protocol['version'], c.VERSION)
        self.assertNotIn('regression_findings', protocol)
        self.assertEqual(base.read(self.output / 'initial.json'), self.original)

    def test_audit_additions_alone_can_create_pending_work_without_acceptance(self):
        self.original['findings'] = []
        self.initialize()
        initial = base.read(self.output / 'initial.json')
        progress = c.replay(self.output, *c.load(self.output))
        self.assertEqual(progress['status'], 'pending')
        self.assertEqual(progress['role'], 'propose')
        self.assertEqual(initial['findings'][0]['finding'], self.finding)
        self.assertIn('Prior findings can be mistaken', progress['prompt'])


if __name__ == '__main__':
    unittest.main()
