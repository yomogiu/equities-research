"""Fictional compact financial evidence, rendering and tamper regressions."""
import copy
import hashlib
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_earnings_compact_evidence import fixture
from research import earnings_compact_evidence as evidence
from research import earnings_financial_context as context
from research import earnings_financial_display as display
from research import financial_evidence


class FinancialContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        case, _, _ = fixture(self.root)
        self.manifest = evidence.prepare(case, self.root / 'evidence')
        self.bundle = evidence.load_bundle(self.manifest)
        self.sheet = {'rows': [{'label': 'Invented GAAP net income', 'fact_ids': ['F002', 'F003']}],
                      'context': [], 'gaps': []}

    def test_all_observations_units_contexts_and_gaps_survive(self):
        before = copy.deepcopy(self.bundle)
        result = context.financial_role_payload(self.bundle)
        facts = result['financial_observations']
        self.assertEqual(facts['rows'], context.financial_role_payload(self.bundle)['financial_observations']['rows'])
        self.assertEqual([r[0] for r in facts['rows']], ['F001', 'F002', 'F003'])
        reconstructed = {}
        for cid, ctx in facts['contexts'].items():
            reconstructed[cid] = {k: v for k, v in ctx.items() if k not in ('dimensions_id', 'entity_id')}
            reconstructed[cid].update(facts['entities'][ctx['entity_id']], dimensions=facts['dimension_sets'][ctx['dimensions_id']])
        self.assertEqual(reconstructed, self.bundle['financial']['contexts'])
        for row, obs in zip(facts['rows'], self.bundle['financial']['observations']):
            item = dict(zip(facts['columns'], row))
            item.update(facts['concepts'][item.pop('concept_id')]); item.pop('source_row_id')
            self.assertEqual(item, {k: obs.get(k) for k in item})
        self.assertEqual(facts['units'], self.bundle['financial']['units'])
        self.assertEqual(facts['gaps'], self.bundle['financial']['gaps'])
        self.assertEqual(facts['omitted_observation_ids'], [])
        self.assertEqual(facts['rows'][0][5], 'proposed')
        self.assertEqual(self.bundle, before)
        self.assertEqual(context.source_identities(self.bundle)['F002']['label'], 'Fictitious café revenue')

    def test_document_selection_is_explicit_and_complete_not_preview_claim(self):
        result = context.financial_role_payload(self.bundle)
        full = {c['id']: c for c in result['complete_context_chunks']}
        inventory = {row[0]: dict(zip(result['document_inventory']['columns'], row))
                     for row in result['document_inventory']['rows']}
        self.assertEqual(set(inventory), set(full) | set(result['deferred_document_ids']))
        self.assertTrue(all(c['preview_truncated'] for c in inventory.values()))
        self.assertTrue(all(len(c['preview']) <= context.PREVIEW_CHARACTERS for c in inventory.values()))
        for identifier, chunk in full.items():
            original = next(d for d in self.bundle['documents']['chunks'] if d['id'] == identifier)
            self.assertEqual(chunk['text'], Path(original['path']).read_bytes().decode()[original['start']:original['end']])
        self.assertIn('not complete evidence', result['notice'])

    def test_topic_round_robin_and_overflow_are_deterministic(self):
        docs = [{'id': 'D%03d' % i, 'cues': ['basis'] if i < 20 else ['subsequent_events'],
                 'document_id': 'fake', 'sha256': '0'*64, 'kind': 'filing', 'start': i*10, 'end': (i+1)*10,
                 'preview': 'fake', 'preview_end': i*10+4, 'preview_truncated': True}
                for i in range(30)]
        text = {d['id']: 'Complete fictional source ' + d['id'] for d in docs}
        with patch.object(context, '_documents', return_value=(docs, text)):
            result = context.financial_role_payload(self.bundle)
        full = [c['id'] for c in result['complete_context_chunks']]
        self.assertEqual(full[:2], ['D000', 'D020'])
        self.assertEqual(len(full), 12)
        self.assertEqual(len(result['deferred_document_ids']), 18)
        self.assertEqual(set(full) | set(result['deferred_document_ids']), set(text))

    def test_source_rows_deduplicate_without_merging_observations(self):
        duplicate = copy.deepcopy(self.bundle['financial']['observations'][1])
        duplicate['id'] = 'F004'
        self.bundle['financial']['observations'].append(duplicate)
        result = context.financial_role_payload(self.bundle)['financial_observations']
        self.assertEqual(len(result['rows']), 4)
        self.assertEqual(result['rows'][1][-1], result['rows'][-1][-1])

    def test_expansion_complete_known_ids_only_and_hard_bound(self):
        result = context.expand(self.bundle, ['F002', 'D001'])
        self.assertEqual([r['id'] for r in result], ['F002', 'D001'])
        self.assertIn('table_row', result[0])
        self.assertGreater(len(result[1]['spans'][0]['text']), context.PREVIEW_CHARACTERS)
        for ids in [[], ['F001', 'F001'], ['absent'], [None], ['F001'] * 13]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                context.expand(self.bundle, ids)
        with patch.object(context, 'MAX_EXPANSION_CHARACTERS', 10), self.assertRaisesRegex(ValueError, 'budget'):
            context.expand(self.bundle, ['D001'])

    def test_exact_source_labels_and_no_author_gaap_basis(self):
        before = copy.deepcopy(self.sheet)
        bound = context.bind(self.sheet, self.bundle)
        rendered = context.preflight(bound, self.bundle)
        rows = [r for g in rendered['groups'] for r in g['rows']]
        self.assertEqual([r['metric'] for r in rows], ['Fictitious café revenue', 'Fictional widget'])
        self.assertTrue(all(r['accounting_basis'] == 'not_stated_in_source_row' for r in rows))
        self.assertEqual(before, self.sheet)
        self.assertEqual(rendered['version'], context.DISPLAY_CONTRACT)
        self.assertNotIn('Invented', display.text_table(bound, self.bundle))
        bound['rows'][0]['label'] = 'Non-GAAP guess'
        self.assertEqual(rendered, context.preflight(bound, self.bundle))

    def test_unknown_contract_and_unresolved_selected_label_fail_before_review(self):
        bad = copy.deepcopy(self.sheet); bad['_display_contract'] = 'made-up'
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            context.bind(bad, self.bundle)
        self.bundle['financial']['observations'][1]['support'].pop('table_row')
        with self.assertRaisesRegex(ValueError, 'Unresolved source financial label: F002'):
            context.bind(self.sheet, self.bundle)

    def test_cited_accounting_context_remains_visible_without_overriding_row_basis(self):
        self.sheet['context'] = [{'text': 'Fictional consolidated statements are unaudited U.S. GAAP.', 'citations': ['D001']}]
        bound = context.bind(self.sheet, self.bundle)
        result = context.preflight(bound, self.bundle)
        self.assertEqual(result['source_context_notes'], self.sheet['context'])
        self.assertEqual(result['basis_notes'], [])
        self.assertEqual(result['groups'][0]['rows'][0]['accounting_basis'], 'not_stated_in_source_row')
        self.assertIn('Source context: Fictional consolidated statements', display.text_table(bound, self.bundle))
        self.assertIn('financial-source-context', display.html_table(bound, self.bundle, lambda ids: ', '.join(ids)))

    def test_source_row_cached_preview_cannot_forge_label_or_basis(self):
        row = self.bundle['financial']['observations'][1]['support']['table_row']
        row.update(text='Invented non-GAAP EBITDA120', truncated=True)
        identity = context.source_identities(self.bundle)['F002']
        self.assertEqual(identity['label'], 'Fictitious café revenue')
        self.assertIsNone(identity['basis'])

    def test_raw_tamper_row_span_tamper_and_unbound_source_fail(self):
        for mutate, message in [
            (lambda o: o['support']['table_row'].update(raw_span_sha256='0'*64), 'row changed'),
            (lambda o: o['support'].update(raw_span_sha256='0'*64), 'observation span changed'),
            (lambda o: o.update(source_document_id='not-bound'), 'not bound'),
            (lambda o: o['support']['table_row'].update(start=o['support']['start']+1), 'outside'),
        ]:
            bundle = copy.deepcopy(self.bundle); mutate(bundle['financial']['observations'][1])
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                context.source_identities(bundle)
        (self.root / 'filing.html').write_text('tampered source')
        with self.assertRaisesRegex(ValueError, 'raw source changed'):
            context.bind(self.sheet, self.bundle)

    def test_document_tamper_fails_before_prompt(self):
        (self.root / 'filing.txt').write_text('changed document')
        with self.assertRaisesRegex(ValueError, 'document changed'):
            context.financial_role_payload(self.bundle)

    def test_unit_period_and_value_preflight(self):
        for change, message in [
            (lambda b: b['financial']['units']['U001'].update(numerator=[]), 'unit'),
            (lambda b: b['financial']['contexts']['C001'].update(instant='2040-03-31'), 'period'),
            (lambda b: b['financial']['observations'][1].update(value='NaN'), 'Finite'),
        ]:
            bundle = copy.deepcopy(self.bundle); change(bundle)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                context.bind(self.sheet, bundle)

    def test_legacy_renderer_remains_unchanged_without_marker(self):
        legacy = display.build(self.sheet, self.bundle)
        self.assertEqual(legacy['version'], display.VERSION)
        self.assertEqual(legacy['groups'][0]['rows'][0]['metric'], 'Revenue (GAAP)')

    def narrative(self, tail=' million available under the Fictional Credit Agreement.', extra=''):
        original = (self.root / 'filing.html').read_bytes().decode()
        tag = '<ix:nonfraction name="us-gaap:LineOfCreditFacilityRemainingBorrowingCapacity" contextref="c" unitref="u">12</ix:nonfraction>'
        raw = re.sub(r'<table>.*?</table>', '<p>Fictitious company has $' + tag + tail + extra + '</p>', original)
        path = self.root / 'narrative.html'; path.write_bytes(raw.encode())
        sha = hashlib.sha256(raw.encode()).hexdigest()
        artifact = financial_evidence.extract_inline_xbrl(raw, {'document_id': 'fictional-narrative', 'raw_sha256': sha})
        obs = artifact['observations'][0]
        obs.update(id='F100', context_id='C001', unit_id='U001', source_path=str(path), source_sha256=sha)
        bundle = copy.deepcopy(self.bundle)
        bundle['manifest']['sources'].append({'path': str(path), 'sha256': sha, 'document_id': 'fictional-narrative'})
        bundle['financial']['observations'] = [obs]
        return bundle, tag

    def test_direct_narrative_availability_keeps_exact_phrase_and_complete_source(self):
        bundle, _ = self.narrative()
        identity = context.source_identities(bundle)['F100']
        self.assertEqual(identity['label'], 'available under the Fictional Credit Agreement')
        self.assertEqual(identity['label_origin'], 'exact_source_phrase')
        sheet = {'rows': [{'label': 'GAAP invented title', 'fact_ids': ['F100']}], 'context': []}
        table = context.preflight(context.bind(sheet, bundle), bundle)
        self.assertEqual(table['groups'][0]['rows'][0]['metric'], identity['label'])
        with patch.object(context.evidence, 'source_slices', return_value=[{'id': 'F100'}]):
            expanded = context.expand(bundle, ['F100'])
        self.assertTrue(expanded[0]['label_source']['text'].startswith('<p>Fictitious'))
        self.assertTrue(expanded[0]['label_source']['text'].endswith('</p>'))

    def test_narrative_ambiguity_and_unqualified_phrasing_fail_closed(self):
        bundle, tag = self.narrative()
        for tail, extra in [(' million allegedly available.', ''),
                            (' million available under the Credit Agreement.', tag),
                            (' million unavailable under the Credit Agreement.', '')]:
            bundle, _ = self.narrative(tail, extra)
            self.assertEqual(context.source_identities(bundle)['F100']['label_origin'], 'unresolved')


class SourceLabelParserTests(unittest.TestCase):
    def test_basis_requires_one_explicit_source_declaration(self):
        for label, expected in [('Segment EBITDA', None), ('Non-GAAP EBITDA', 'non-GAAP'),
                                ('Non-IFRS earnings', 'non-IFRS'), ('non‑GAAP earnings', 'non-GAAP'),
                                ('U.S. GAAP earnings', 'GAAP'), ('GAAP and non-GAAP earnings', None),
                                ('IFRS and U.S. GAAP earnings', None)]:
            with self.subTest(label=label):
                self.assertEqual(context._explicit_basis(label), expected)

    def label(self, raw):
        parser = context._Row(); parser.feed(raw); parser.close()
        return parser.label()

    def test_cell_structure_preserves_digits_attribution_and_source_qualifiers(self):
        for name in ['Net income attributable to Fictitious 3M', 'Non-GAAP segment EBITDA As Defined',
                     'Commercial and non-aerospace aftermarket', 'Fictitious café & widgets']:
            raw = '<tr><td>' + name.replace('&', '&amp;') + '</td><td>$</td><td><ix:nonfraction>20</ix:nonfraction></td></tr>'
            self.assertEqual(self.label(raw), name)

    def test_truncated_preview_does_not_limit_complete_source_label(self):
        name = 'Fictitious ' + 'complete ' * 200 + 'label'
        self.assertEqual(self.label('<tr><td>' + name + '</td><td><ix:nonfraction>2</ix:nonfraction></td></tr>'), name)

    def test_ambiguous_or_malformed_markup_is_never_silently_named(self):
        for raw in ['<tr><td><ix:nonfraction>2</ix:nonfraction></td></tr>',
                    '<tr><td>Label</td><td>10</td><td><ix:nonfraction>2</ix:nonfraction></td></tr>',
                    '<tr><td>Label<td><ix:nonfraction>2</ix:nonfraction></td></tr>',
                    '<tr><td>Label</td></tr>']:
            with self.subTest(raw=raw):
                self.assertEqual(self.label(raw), '')
