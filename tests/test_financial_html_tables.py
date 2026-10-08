"""Fictitious source-bound HTML finance adapter; no live inputs or calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import financial_html_tables as adapter
from research import financial_evidence as financial
from research import earnings_compact_evidence as compact
from research import earnings_financial_context as context
from research import earnings_financial_display as display
from research import earnings_experiment as base
from test_earnings_passages import PassageFixture


def fixture(raw=None):
    raw = raw or ('<h1>Fictional Example plc</h1>\r\n'
           '<p>IFRS; CAD millions except per-share amounts.</p>'
           '<table><tr><th>Three months ended June 30</th><th>2040</th><th>2039</th></tr>'
           '<tr><th>Revenue</th><td>1,234.50</td><td>(987.25)</td></tr>'
           '<tr><th>Earnings per share</th><td>1.23</td><td>0.98</td></tr></table>')
    parser = financial._Parser(raw); parser.feed(raw); parser.close()
    table = next(parser.root.all('table')); rows = list(table.all('tr'))
    span = lambda node: {'start': node.start, 'end': node.end,
                         'raw_span_sha256': financial.digest(raw[node.start:node.end].encode())}
    source = {'document_id': 'fictional-filing', 'raw_sha256': financial.digest(raw.encode()),
              'text_sha256': financial.digest(b'Fictional text'), 'issuer_id': 'fake:example'}
    evidence = {'period': [span(rows[0])], 'unit': [span(next(parser.root.all('p')))],
                'entity': [span(next(parser.root.all('h1')))], 'basis': [span(next(parser.root.all('p')))]}
    observations = []
    for row, concept, scale, denominator in [(rows[1], 'fake:Revenue', 6, []),
                                            (rows[2], 'fake:EarningsPerShare', 0, ['xbrli:shares'])]:
        cells = list(row.all('td'))
        for i, year in enumerate(('2040', '2039')):
            observations.append({'key': concept + '-' + year, 'concept': concept, 'scale': scale,
                'accounting_basis': 'IFRS', 'context': {'entity': source['issuer_id'], 'entity_scheme': 'qualified_packet_issuer_id',
                'start_date': year+'-04-01', 'end_date': year+'-06-30', 'instant': None, 'dimensions': []},
                'unit': {'numerator': ['iso4217:CAD'], 'denominator': denominator},
                'table': span(table), 'row': span(row), 'label': span(next(row.all('th'))),
                'value_cells': [span(cells[i])], 'evidence': copy.deepcopy(evidence)})
    profile = {'version': adapter.VERSION, 'source': source, 'author_id': 'fake-author', 'observations': observations}
    return raw.encode(), source, profile


def authorize(source, profile):
    profile_bytes = json.dumps(profile, ensure_ascii=False).encode()
    review = {'version': adapter.VERSION, 'source': source, 'profile_sha256': financial.digest(profile_bytes),
              'author_id': 'fake-author', 'reviewer_id': 'fake-reviewer', 'verdict': 'pass_profile_only',
              'decisions': [{'key': o['key'], 'verdict': 'pass', 'observation_sha256': financial.digest(financial.canonical(o))}
                            for o in profile['observations']]}
    review_bytes = json.dumps(review).encode()
    auth = {'version': adapter.VERSION, 'enabled': True, 'source': source, 'author_id': 'fake-author',
            'reviewer_id': 'fake-reviewer', 'profile_sha256': financial.digest(profile_bytes), 'review_sha256': financial.digest(review_bytes)}
    return profile_bytes, review_bytes, auth


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.source, self.profile = fixture()

    def extract(self):
        return adapter.extract(self.raw, self.source, *authorize(self.source, self.profile))

    def test_numbers_units_periods_and_original_inputs_preserved(self):
        original = copy.deepcopy(self.profile)
        rows = self.extract()['observations']
        self.assertEqual([r['value'] for r in rows], ['1234500000.00', '-987250000.00', '1.23', '0.98'])
        self.assertEqual(rows[0]['context']['start_date'], '2040-04-01')
        self.assertEqual(rows[2]['unit']['denominator'], ['xbrli:shares'])
        self.assertTrue(all(r['method'] == adapter.METHOD and r['nil'] is False for r in rows))
        self.assertEqual(self.profile, original)
        self.assertEqual(rows[0]['support']['source_label'], 'Revenue')

    def test_source_review_or_authorization_change_rejected(self):
        profile, review, auth = authorize(self.source, self.profile)
        for args in [(self.raw+b' ', self.source, profile, review, auth),
                     (self.raw, self.source, profile+b' ', review, auth),
                     (self.raw, self.source, profile, review+b' ', auth),
                     (self.raw, self.source, profile, review, {**auth, 'enabled': False}),
                     (self.raw, self.source, profile, review, {**auth, 'reviewer_id': 'fake-author'})]:
            with self.subTest(), self.assertRaises(ValueError): adapter.extract(*args)

    def test_schema_cannot_supply_a_numeric_value_or_unreviewed_metadata(self):
        self.profile['observations'][0]['value'] = '999'
        with self.assertRaisesRegex(ValueError, 'Exact profile observation'): self.extract()
        self.profile['observations'][0].pop('value')
        profile, review, auth = authorize(self.source, self.profile)
        changed = json.loads(profile); changed['observations'][0]['scale'] = 0
        changed = json.dumps(changed).encode(); auth['profile_sha256'] = financial.digest(changed)
        with self.assertRaisesRegex(ValueError, 'exact-profile'): adapter.extract(self.raw, self.source, changed, review, auth)

    def test_wrong_span_duplicate_cell_and_cross_row_rejected_even_if_reviewed(self):
        for mutation in ('hash', 'partial', 'duplicate', 'wrong_row'):
            with self.subTest(mutation=mutation):
                self.raw, self.source, self.profile = fixture()
                row = self.profile['observations'][0]
                if mutation == 'hash': row['value_cells'][0]['raw_span_sha256'] = '0'*64
                elif mutation == 'partial':
                    s = row['value_cells'][0]; s['start'] += 1
                    s['raw_span_sha256'] = financial.digest(self.raw.decode()[s['start']:s['end']].encode())
                elif mutation == 'duplicate': self.profile['observations'][1]['value_cells'] = copy.deepcopy(row['value_cells'])
                else: row['value_cells'] = copy.deepcopy(self.profile['observations'][2]['value_cells'])
                with self.assertRaises(ValueError): self.extract()

    def test_bad_contexts_units_and_missing_semantic_evidence_rejected(self):
        for kind in ('entity', 'dates', 'unit', 'evidence'):
            self.raw, self.source, self.profile = fixture(); row = self.profile['observations'][0]
            if kind == 'entity': row['context']['entity'] = 'fake:other'
            elif kind == 'dates': row['context']['start_date'] = '2041-01-01'
            elif kind == 'unit': row['unit']['numerator'] = []
            else: row['evidence']['unit'] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.extract()

    def test_numeric_ambiguity_is_not_promoted_to_zero_or_nil(self):
        for text in ('', '-', '—', '1 234', '12,34', '1.2%', '1.2¹', 'NaN', '(−2)'):
            with self.subTest(text=text), self.assertRaises(ValueError): adapter._number(text, 0)
        self.assertEqual(adapter._number('−1,234.50', 0), '-1234.50')
        self.assertEqual(adapter._number('$ (12.30)', 6), '-12300000.00')

    def test_mixed_accounting_bases_cannot_share_metric_identity(self):
        row = self.profile['observations'][1]
        row['accounting_basis'] = 'non-IFRS'
        with self.assertRaisesRegex(ValueError, 'Different accounting bases'): self.extract()
        row['context']['dimensions'] = [{'dimension': 'fake:AccountingBasisAxis', 'member': 'non-IFRS', 'type': 'typedmember'}]
        self.assertEqual(len(self.extract()['observations']), 4)

    def test_split_parentheses_cells_are_one_value_but_adjacent_numbers_are_not(self):
        raw = self.raw.decode().replace('<td>(987.25)</td>', '<td>(</td><td>987.25</td><td>)</td>')
        self.raw, self.source, self.profile = fixture(raw)
        parser = financial._Parser(raw); parser.feed(raw); parser.close()
        row = list(parser.root.all('tr'))[1]
        self.profile['observations'][1]['value_cells'] = [
            {'start': n.start, 'end': n.end, 'raw_span_sha256': financial.digest(raw[n.start:n.end].encode())}
            for n in list(row.all('td'))[1:]]
        self.assertEqual(self.extract()['observations'][1]['value'], '-987250000.00')
        self.profile['observations'][1]['value_cells'].insert(0, self.profile['observations'][0]['value_cells'][0])
        with self.assertRaises(ValueError): self.extract()

    def test_validator_requires_exact_authorized_replay_not_resealed_values(self):
        inputs = (self.raw, self.source, *authorize(self.source, self.profile))
        artifact = adapter.extract(*inputs)
        trusted = {self.source['document_id']: self.source}
        with self.assertRaisesRegex(ValueError, 'authorized source replay'): financial.validate_artifact(artifact, trusted)
        financial.validate_artifact(artifact, trusted, html_table_inputs=inputs)
        with self.assertRaisesRegex(ValueError, 'authorized source replay'):
            financial.validate_artifact(artifact, {self.source['document_id']: {**self.source, 'issuer_id': 'fake:other'}}, html_table_inputs=inputs)
        forged = copy.deepcopy(artifact); forged['observations'][0]['value'] = '99'
        forged['observations'][0] = financial.seal(forged['observations'][0], 'observation_id')
        forged = financial.seal(forged, 'artifact_sha256')
        with self.assertRaisesRegex(ValueError, 'authorized source replay'):
            financial.validate_artifact(forged, trusted, html_table_inputs=inputs)


class CompactAdapterTests(PassageFixture, unittest.TestCase):
    def test_exact_raw_support_and_display_semantics_survive_compaction(self):
        raw, source, profile = fixture()
        filing = self.root/'plain-financial.html'; filing.write_bytes(raw)
        text = self.root/'plain-financial.txt'; text.write_text('Fictional text')
        profile_bytes, review_bytes, auth = authorize(source, profile)
        artifact = adapter.extract(raw, source, profile_bytes, review_bytes, auth)
        financial_path = self.root/'reviewed-financial.json'; base.save(financial_path, artifact)
        case = copy.deepcopy(self.case)
        case['issuer_id'] = source['issuer_id']; case['financial_path'] = str(financial_path)
        case['sources'] = [s for s in case['sources'] if s['document_id'] != source['document_id']]
        case['sources'] += [{'document_id': source['document_id'], 'path': str(path), 'sha256': base.sha(path),
                             'kind': 'filing', 'representation': kind}
                            for path, kind in ((filing, 'raw'), (text, 'text'))]
        paths = {}
        for name, content in [('profile', profile_bytes), ('review', review_bytes), ('authorization', json.dumps(auth).encode())]:
            path = self.root/(name+'.json'); path.write_bytes(content); paths[name+'_path'] = str(path)
            case['artifacts'].append({'path': str(path), 'sha256': base.sha(path)})
        case['artifacts'].append({'path': str(financial_path), 'sha256': base.sha(financial_path)})
        case['financial_adapter'] = paths
        case_path = self.root/'html-case.json'; base.save(case_path, case)
        manifest = compact.prepare(case_path, self.root/'html-evidence')
        bundle = compact.load_bundle(manifest)
        observations = bundle['financial']['observations']
        self.assertEqual(len(observations), 4)
        self.assertTrue(all(o['source_path'] == str(filing) for o in observations))
        identities = context.source_identities(bundle)
        self.assertEqual({x['basis'] for x in identities.values()}, {'IFRS'})
        self.assertEqual({x['label'] for x in identities.values()}, {'Revenue', 'Earnings per share'})
        selection = {'rows': [{'label': 'Ignored', 'fact_ids': [o['id'] for o in observations]}], 'context': [], 'gaps': []}
        bound = context.bind(selection, bundle)
        rendered = display.text_table(bound, bundle)
        self.assertIn('CAD/share', rendered); self.assertIn('CAD millions', rendered); self.assertIn('IFRS', rendered)
        paths['profile_path'] = str(self.root/'not-frozen.json')
        with self.assertRaisesRegex(ValueError, 'not frozen'): adapter.case_inputs(case, raw, source)


class PreparedAdapterTests(unittest.TestCase):
    def test_opt_in_preparation_freezes_review_inputs_and_plain_html_never_auto_promotes(self):
        from research import earnings_report_flow as flow
        from research import earnings_passage_pipeline as pipeline
        from test_publisher_transcript import fixture as publisher_fixture
        from research.source_parse import page
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw, source, profile = fixture()
            (root/'filing.html').write_bytes(raw); (root/'filing.txt').write_text('Fictional text')
            call_raw, _, _ = publisher_fixture()
            call_raw = call_raw.replace(b'Fictional Widgets', b'Fictional Example')
            (root/'call.html').write_bytes(call_raw); (root/'call.txt').write_text(page(call_raw, '').text)
            writing = root/'writing.txt'; writing.write_text('Fictional writing standard')
            pb, rb, auth = authorize(source, profile)
            (root/'profile.json').write_bytes(pb); (root/'review.json').write_bytes(rb)
            documents = [{'document_id': 'fictional-'+name, 'kind': kind, 'period': 'FY2040-Q2', 'completeness': 'full',
                          'source_url': 'https://example.invalid/'+name, 'raw_path': name+'.html', 'text_path': name+'.txt',
                          'raw_sha256': base.sha(root/(name+'.html')), 'text_sha256': base.sha(root/(name+'.txt'))}
                         for name, kind in [('filing', 'periodic_filing'), ('call', 'transcript')]]
            packet = {'issuer_id': source['issuer_id'], 'period': 'FY2040-Q2', 'documents': documents}
            catalog = {'catalog_id': 'fake-catalog', 'issuers': {source['issuer_id']: {'issuer': 'Fictional Example'}}}
            selection = {'profile_path': 'profile.json', 'review_path': 'review.json', 'authorization': auth}
            with patch.object(flow, 'validate_packet', return_value=packet), patch.object(flow.library, 'catalog', return_value=catalog):
                with self.assertRaisesRegex(ValueError, 'No structured filing'):
                    flow.prepare(root, 'fake-packet', root/'without-adapter', writing, 'Explicit fake request')
                self.assertFalse((root/'without-adapter').exists())
                prepared = flow.prepare(root, 'fake-packet', root/'prepared', writing, 'Explicit fake request', reviewed_financial=selection)
            case = base.read(prepared)
            frozen = {x['path']: x['sha256'] for x in case['artifacts']}
            self.assertEqual(frozen[str(root/'profile.json')], auth['profile_sha256'])
            self.assertEqual(frozen[str(root/'review.json')], auth['review_sha256'])
            pipeline.freeze(prepared, root/'pipeline', writing, efficient=True)
            protocol, bundle, _ = pipeline.load(root/'pipeline')
            self.assertTrue({'financial_html_tables.py', 'financial_evidence.py', 'reviewed_transcript_index.py'} <=
                            {Path(r['path']).name for r in protocol['code']})
            self.assertEqual(len(bundle['financial']['observations']), 4)
            (root/'profile.json').write_bytes(pb+b' ')
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'): pipeline.load(root/'pipeline')
