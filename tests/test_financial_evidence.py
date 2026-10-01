"""Synthetic fixtures only: the entity below is deliberately fictitious."""
import copy
import tempfile
import unittest
from pathlib import Path

from research import financial_evidence as f


BASE = '''<html><body><xbrli:context id="quarter"><xbrli:entity><xbrli:identifier scheme="test">FAKE</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="fake:Segment">fake:Widgets</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="ytd"><xbrli:entity><xbrli:identifier scheme="test">FAKE</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
<xbrli:unit id="eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
{facts}</body></html>'''


def fact(value='1,234', context='quarter', **attrs):
    settings = {'name': 'us-gaap:Revenues', 'contextRef': context, 'unitRef': 'usd', 'scale': '6', 'format': 'ixt:num-dot-decimal', **attrs}
    attributes = ' '.join(f'{k}="{v}"' for k, v in settings.items())
    return f'<ix:nonFraction {attributes}>{value}</ix:nonFraction>'


def fixture(facts=None):
    raw = BASE.format(facts=facts or fact() + fact('2,001', 'ytd'))
    source = {'document_id': 'fake-report', 'raw_sha256': f.digest(raw.encode())}
    return raw, source, f.extract_inline_xbrl(raw, source)


class FinancialEvidenceTests(unittest.TestCase):
    def test_quarter_ytd_dimensions_units_and_scale_preserved(self):
        raw, source, artifact = fixture()
        quarter, ytd = artifact['observations']
        self.assertEqual(quarter['value'], '1.234E+9')
        self.assertEqual(quarter['canonical_metric'], 'revenue')
        self.assertEqual(quarter['context']['start_date'], '2026-04-01')
        self.assertEqual(ytd['context']['start_date'], '2026-01-01')
        self.assertEqual(quarter['context']['dimensions'][0]['member'], 'fake:Widgets')
        self.assertEqual(quarter['unit']['numerator'], ['iso4217:USD'])
        support = quarter['support']
        self.assertEqual(f.digest(raw[support['start']:support['end']].encode()), support['raw_span_sha256'])
        self.assertEqual(f.validate_artifact(artifact, {'fake-report': source}), artifact)

    def test_signed_eps_comma_transform_nil_and_exclude(self):
        raw, source, artifact = fixture(fact('1,25', name='us-gaap:EarningsPerShareDiluted', unitRef='eps', format='ixt:num-comma-decimal', scale='0', sign='-') + fact('', **{'xsi:nil': 'true'}) + fact('1<ix:exclude>garbage</ix:exclude>,200'))
        self.assertEqual(artifact['observations'][0]['value'], '-1.25')
        self.assertEqual(artifact['observations'][0]['unit']['denominator'], ['xbrli:shares'])
        self.assertIsNone(artifact['observations'][1]['value'])
        self.assertTrue(artifact['observations'][1]['nil'])
        self.assertEqual(artifact['observations'][2]['value'], '1.200E+9')

    def test_unsupported_transform_fraction_and_nonfinite_are_gaps(self):
        _, _, artifact = fixture(fact('123', format='ixt:unknown') + fact('NaN', format='') + fact('INF', format='') + '<ix:fraction>1/3</ix:fraction>' + fact('1,00'))
        self.assertEqual(len(artifact['observations']), 0)
        self.assertEqual(len(artifact['gaps']), 5)

    def test_repeated_disclosures_preserved_but_context_collision_rejected(self):
        raw, source, artifact = fixture(fact() + fact())
        self.assertEqual(len(artifact['observations']), 2)
        self.assertNotEqual(*[o['observation_id'] for o in artifact['observations']])
        raw = raw.replace('</body>', '<xbrli:context id="quarter"></xbrli:context></body>')
        source['raw_sha256'] = f.digest(raw.encode())
        artifact = f.extract_inline_xbrl(raw, source)
        self.assertFalse(artifact['observations'])
        self.assertTrue(any('Duplicate context' in g['reason'] for g in artifact['gaps']))

    def test_raw_stale_manifest_and_mutated_artifact_rejected(self):
        raw, source, artifact = fixture()
        with self.assertRaisesRegex(ValueError, 'Raw source hash'):
            f.extract_inline_xbrl(raw + 'x', source)
        with self.assertRaisesRegex(ValueError, 'stale source'):
            f.validate_artifact(artifact, {'fake-report': {**source, 'raw_sha256': '0'*64}})
        artifact['observations'][0]['value'] = '999'
        with self.assertRaisesRegex(ValueError, 'artifact hash'):
            f.validate_artifact(artifact, {'fake-report': source})

    def test_resealed_invalid_numbers_duplicate_or_self_approval_rejected(self):
        _, source, artifact = fixture()
        for edit in ('number', 'duplicate', 'approval'):
            bad = copy.deepcopy(artifact)
            if edit == 'number':
                bad['observations'][0]['value'] = 'NaN'
            if edit == 'approval':
                bad['observations'][0]['status'] = 'reviewed'
            bad['observations'][0] = f.seal(bad['observations'][0], 'observation_id')
            if edit == 'duplicate':
                bad['observations'].append(bad['observations'][0])
            bad = f.seal(bad, 'artifact_sha256')
            with self.assertRaises(ValueError):
                f.validate_artifact(bad, {'fake-report': source})

    def test_database_rebuild_parameterized_period_and_context_query(self):
        _, source, artifact = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'facts.db'
            result = f.rebuild_database(path, [artifact], {'fake-report': source})
            self.assertEqual(result['observations'], 2)
            self.assertEqual(len(f.query_facts(path, period_end='2026-06-30')), 2)
            rows = f.query_facts(path, context_id='quarter', concept='us-gaap:Revenues')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['artifact_sha256'], artifact['artifact_sha256'])
            self.assertEqual(f.query_facts(path, concept="' OR 1=1 --"), [])
            with self.assertRaises(ValueError):
                f.query_facts(path, limit=1001)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                f.rebuild_database(path, [artifact], {})
            self.assertEqual(before, path.read_bytes())

    def test_table_row_context_bound_to_source_span(self):
        raw, _, artifact = fixture('<table><tr><th>Fictitious revenue</th><td>' + fact() + '</td></tr></table>')
        support = artifact['observations'][0]['support']['table_row']
        self.assertIn('Fictitious revenue', support['text'])
        self.assertFalse(support['truncated'])
        self.assertEqual(f.digest(raw[support['start']:support['end']].encode()), support['raw_span_sha256'])

    def test_date_entity_file_hash_and_high_precision(self):
        raw, source, artifact = fixture(fact('123456789012345678901234567890', format='', scale='1'))
        self.assertEqual(artifact['observations'][0]['value'], '1.23456789012345678901234567890E+30')
        wrong_entity = f.extract_inline_xbrl(raw, {**source, 'entity_identifier': 'OTHER'})
        self.assertFalse(wrong_entity['observations'])
        raw_bad = raw.replace('2026-04-01', '2026-99-01')
        self.assertFalse(f.extract_inline_xbrl(raw_bad, {**source, 'raw_sha256': f.digest(raw_bad.encode())})['observations'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.html'
            path.write_text(raw, encoding='utf-8')
            self.assertEqual(f.extract_inline_xbrl_file(path, source), artifact)
            path.write_text(raw + 'changed', encoding='utf-8')
            with self.assertRaises(ValueError):
                f.extract_inline_xbrl_file(path, source)

    def test_fallback_requires_exact_support_and_excluded_by_default(self):
        _, source, automatic = fixture()
        text = 'Fictitious example: Revenue was 42 units.'
        source['text_sha256'] = f.digest(text.encode())
        record = f.propose_fact(text, source, concept='fake:Revenue', value='42',
                                context=automatic['observations'][0]['context'], unit={'numerator': ['fake:units'], 'denominator': []}, quote='Revenue was 42 units.', start=20)
        self.assertEqual(record['status'], 'proposed')
        with self.assertRaises(ValueError):
            f.propose_fact(text, source, concept='fake:Revenue', value='42', context={}, unit={}, quote='Revenue was 43 units.', start=20)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'facts.db'
            f.rebuild_database(path, [f.make_artifact(source, [record])], {'fake-report': source})
            self.assertEqual(f.query_facts(path), [])
            self.assertEqual(len(f.query_facts(path, include_proposed=True)), 1)


if __name__ == '__main__':
    unittest.main()
