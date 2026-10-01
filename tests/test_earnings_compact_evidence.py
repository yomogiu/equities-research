"""Entirely fictitious evidence; standard library only, no issuer/model calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research import earnings_compact_evidence as compact
from research import earnings_experiment as base
from research import financial_evidence as financial
from research import transcript_evidence as transcript


def write(path, value):
    path.write_bytes(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    return path


def fixture(root):
    raw = ('<html>\r\n<xbrli:context id="c"><xbrli:entity>'
           '<xbrli:identifier scheme="fictional">000FAKE</xbrli:identifier></xbrli:entity>'
           '<xbrli:period><xbrli:startdate>2040-01-01</xbrli:startdate>'
           '<xbrli:enddate>2040-03-31</xbrli:enddate></xbrli:period></xbrli:context>'
           '<xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
           '<table><tr><td>Fictitious café revenue</td><td><ix:nonfraction '
           'name="us-gaap:Revenues" contextref="c" unitref="u" decimals="0">12'
           '</ix:nonfraction></td></tr><tr><td>Fictional widget</td><td>'
           '<ix:nonfraction name="fiction:Widget" contextref="c" unitref="u">3'
           '</ix:nonfraction></td></tr></table></html>')
    filing = root / 'filing.html'
    filing.write_bytes(raw.encode('utf-8'))
    # More than two chunks, Unicode plus unchanged CRLF, repeated quotation.
    filing_text = ('Fictitious café guidance is provisional. Repeated phrase. Repeated phrase.\r\n' +
                   ''.join('Fictitious supporting row %03d.\r\n' % i for i in range(200)))
    plain = root / 'filing.txt'
    plain.write_bytes(filing_text.encode('utf-8'))
    source = {'document_id': 'fictional-filing', 'raw_sha256': base.sha(filing),
              'text_sha256': base.sha(plain)}
    artifact = financial.extract_inline_xbrl(raw, source)
    proposed = financial.propose_fact(filing_text, source, concept='fiction:GrossMargin',
        value='42', context=artifact['observations'][0]['context'],
        unit=artifact['observations'][0]['unit'], quote='guidance is provisional.',
        start=filing_text.index('guidance is provisional.'))
    artifact = financial.make_artifact(source, [*artifact['observations'], proposed],
                                      [{'reason': 'Fictitious unsupported fraction', 'start': 1}])
    fact_path = write(root / 'financial-source.json', artifact)
    text = ('Fictitious café call.\r\nPrepared remarks\r\nChief: Fictional operations.\r\n'
            'Q&A\r\nQuestioner: Is this repeatable?\r\n'
            'Chief: Repeated phrase. Repeated phrase.\r\n'
            'Questioner: What remains uncertain?\r\nChief: Fictitious caveat.\r\n')
    call = root / 'call.txt'
    call.write_bytes(text.encode('utf-8'))
    index = transcript.index_transcript(text, {'document_id': 'fictional-call',
        'text_sha256': base.sha(call),
        'speakers': [{'name': 'Chief', 'role': 'management'}, {'name': 'Questioner', 'role': 'analyst'}]})
    index_path = write(root / 'index-source.json', index)
    sources = [{'document_id': 'fictional-filing', 'kind': 'filing', 'representation': 'raw', 'path': str(filing), 'sha256': base.sha(filing)},
               {'document_id': 'fictional-filing', 'kind': 'filing', 'representation': 'text', 'path': str(plain), 'sha256': base.sha(plain)},
               {'document_id': 'fictional-call', 'kind': 'transcript', 'representation': 'text', 'path': str(call), 'sha256': base.sha(call)}]
    case = {'schema_version': 1, 'scope': 'one_packet_experiment', 'authorization': 'Fictitious tests only',
            'sources': sources, 'artifacts': [{'path': str(p), 'sha256': base.sha(p)} for p in [fact_path, index_path]],
            'financial_path': str(fact_path), 'transcript_path': str(call), 'transcript_index_path': str(index_path),
            'scope_notes': ['All material is fictional.']}
    return write(root / 'case.json', case), case, text


def refreeze(case_path, case, path):
    for source in case['sources'] + case['artifacts']:
        if source['path'] == str(path):
            source['sha256'] = base.sha(path)
    write(case_path, case)


class CompactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case_path, self.case, self.text = fixture(self.root)
        self.output = self.root / 'compact'

    def prepare(self):
        return compact.prepare(self.case_path, self.output)

    def test_deterministic_complete_financial_context_and_explicit_omissions(self):
        original_hashes = {s['path']: base.sha(s['path']) for s in self.case['sources']}
        manifest = self.prepare()
        first_bytes = {p.name: p.read_bytes() for p in self.output.iterdir()}
        self.assertEqual(manifest, self.prepare())
        self.assertEqual(first_bytes, {p.name: p.read_bytes() for p in self.output.iterdir()})
        bundle = compact.load_bundle(self.output / 'manifest.json')
        facts, view = bundle['financial'], bundle['financial_view']
        self.assertEqual(['F001', 'F002', 'F003'], [o['id'] for o in facts['observations']])
        self.assertEqual(3, view['total_observations'])
        self.assertEqual(2, view['selected_count'])
        omitted = next(o for o in facts['observations'] if o['concept'] == 'fiction:Widget')
        self.assertEqual([omitted['id']], view['omitted_ids'])
        self.assertEqual(2, view['unmapped_count'])
        self.assertEqual(1, len(view['gaps']))
        self.assertFalse(view['selection_is_review'])
        for obs in facts['observations']:
            self.assertEqual('2040-03-31', facts['contexts'][obs['context_id']]['end_date'])
            self.assertEqual(['iso4217:USD'], facts['units'][obs['unit_id']]['numerator'])
            self.assertIn('source_sha256', obs)
            self.assertIn('start', obs['support'])
        proposal = next(o for o in facts['observations'] if o['status'] == 'proposed')
        self.assertIn(proposal['id'], [row[0] for row in view['rows']])
        self.assertEqual(original_hashes, {s['path']: base.sha(s['path']) for s in self.case['sources']})
        self.assertEqual({'manifest.json', 'financial.json', 'financial_view.json', 'documents.json', 'transcript_index.json'}, set(first_bytes))

    def test_ids_ignore_input_observation_and_source_order(self):
        manifest = self.prepare()
        before = {o['observation_id']: o['id'] for o in compact.load_bundle(manifest)['financial']['observations']}
        path = Path(self.case['financial_path'])
        artifact = base.read(path)
        artifact['observations'].reverse()
        write(path, financial.seal(artifact, 'artifact_sha256'))
        self.case['sources'].reverse()
        refreeze(self.case_path, self.case, path)
        after_manifest = compact.prepare(self.case_path, self.root / 'other')
        after = {o['observation_id']: o['id'] for o in compact.load_bundle(after_manifest)['financial']['observations']}
        self.assertEqual(before, after)

    def test_documents_cover_original_text_and_full_transcript_has_all_qa(self):
        manifest = self.prepare()
        bundle = compact.load_bundle(manifest)
        chunks = bundle['documents']['chunks']
        self.assertGreater(len(chunks), 1)
        slices = compact.source_slices(manifest, [c['id'] for c in chunks])
        reconstructed = ''.join(s['spans'][0]['text'] for s in slices)
        original = (self.root / 'filing.txt').read_bytes().decode()
        self.assertEqual(original, reconstructed)
        self.assertTrue(any(c['preview_truncated'] for c in chunks))
        self.assertEqual(0, chunks[0]['start'])
        self.assertEqual(len(original), chunks[-1]['end'])
        full = compact.transcript_view(manifest)
        self.assertEqual(self.text, full['text'])
        self.assertIn('\r\n', full['text'])
        self.assertEqual(base.read(self.case['transcript_index_path']), full['index'])
        self.assertEqual(2, len(full['index']['exchanges']))
        self.assertTrue(full['index']['uncertainty'])
        for exchange in full['index']['exchanges']:
            resolved = compact.source_slices(manifest, [exchange['id']])[0]
            self.assertEqual(len(exchange['turn_ids']), len(resolved['spans']))
            for span in resolved['spans']:
                self.assertEqual(self.text[span['start']:span['end']], span['text'])

    def test_financial_source_slices_include_original_table_and_proposal_status(self):
        manifest = self.prepare()
        facts = compact.load_bundle(manifest)['financial']['observations']
        for fact in facts:
            result = compact.source_slices(manifest, [fact['id']])[0]
            self.assertEqual(fact['status'], result['observation']['status'])
            self.assertEqual('000FAKE', result['observation']['context']['entity'])
            if fact['method'] == 'inline_xbrl':
                self.assertIn('<tr>', result['table_row']['text'])
                self.assertIn('<ix:nonfraction', result['spans'][0]['text'])

    def test_unknown_ids_ambiguous_quote_and_scoped_exact_match(self):
        manifest = self.prepare()
        with self.assertRaisesRegex(ValueError, 'Unknown source ID'):
            compact.source_slices(manifest, ['F999'])
        with self.assertRaisesRegex(ValueError, 'Unknown source ID'):
            compact.resolve_quote(manifest, 'D999', 'Fictitious')
        with self.assertRaisesRegex(ValueError, 'Ambiguous quote'):
            compact.resolve_quote(manifest, 'D001', 'Repeated phrase.')
        quote = compact.resolve_quote(manifest, 'D001', 'Repeated phrase.',
                                      start=(self.root / 'filing.txt').read_bytes().decode().index('Repeated phrase.'))
        self.assertEqual(quote, compact.validate_quote(manifest, quote))
        with self.assertRaisesRegex(ValueError, 'differs from source'):
            compact.resolve_quote(manifest, 'D001', 'repeated phrase.')
        for key, value in [('end', quote['end'] + 1), ('sha256', '0' * 64),
                           ('document_id', 'another-document'), ('path', '/somewhere'),
                           ('offset_unit', 'bytes')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                compact.validate_quote(manifest, {**quote, key: value})
        with self.assertRaises(ValueError):
            compact.resolve_quote(manifest, 'D001', 'Repeated phrase.', start=True)

    def test_exchange_quote_cannot_cross_turn_or_use_different_exchange(self):
        manifest = self.prepare()
        index = compact.load_bundle(manifest)['transcript_index']
        first, second = index['exchanges']
        quote = compact.resolve_quote(manifest, second['id'], 'Fictitious caveat.')
        self.assertEqual(quote, compact.validate_quote(manifest, quote))
        with self.assertRaisesRegex(ValueError, 'outside scope'):
            compact.resolve_quote(manifest, first['id'], 'Fictitious caveat.')
        with self.assertRaisesRegex(ValueError, 'Ambiguous quote'):
            compact.resolve_quote(manifest, first['id'], 'Repeated phrase.')
        with self.assertRaisesRegex(ValueError, 'outside scope'):
            compact.resolve_quote(manifest, first['id'], 'repeatable?\r\nChief: Repeated')

    def test_frozen_source_changes_rejected_at_prepare_and_read(self):
        manifest = self.prepare()
        (self.root / 'filing.txt').write_text('Changed fictitious source')
        for call in [self.prepare, lambda: compact.load_bundle(manifest),
                     lambda: compact.source_slices(manifest, ['D001']),
                     lambda: compact.transcript_view(manifest)]:
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
                call()

    def test_compact_file_and_case_tampering_rejected(self):
        manifest = self.prepare()
        facts = Path(manifest['files']['financial'])
        facts.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Compact evidence file changed'):
            compact.load_bundle(manifest)
        with self.assertRaisesRegex(ValueError, 'immutable evidence'):
            self.prepare()
        self.case['authorization'] = 'Changed authorization'
        write(self.case_path, self.case)
        with self.assertRaisesRegex(ValueError, 'Frozen case changed'):
            compact.load_bundle(manifest)

    def test_financial_support_and_table_hash_verified_against_original(self):
        for table in (False, True):
            with self.subTest(table=table):
                path = Path(self.case['financial_path'])
                original = base.read(path)
                artifact = copy.deepcopy(original)
                obs = next(o for o in artifact['observations'] if o['method'] == 'inline_xbrl')
                target = obs['support']['table_row'] if table else obs['support']
                target['raw_span_sha256'] = 'f' * 64
                obs.update(financial.seal(obs, 'observation_id'))
                write(path, financial.seal(artifact, 'artifact_sha256'))
                refreeze(self.case_path, self.case, path)
                with self.assertRaisesRegex(ValueError, 'source span hash mismatch'):
                    self.prepare()
                write(path, original)
                refreeze(self.case_path, self.case, path)

    def test_transcript_index_hash_and_unknown_turns_rejected(self):
        path = Path(self.case['transcript_index_path'])
        original = base.read(path)
        index = copy.deepcopy(original)
        index['source']['text_sha256'] = 'f' * 64
        write(path, index)
        refreeze(self.case_path, self.case, path)
        with self.assertRaisesRegex(ValueError, 'index source hash mismatch'):
            self.prepare()
        index = copy.deepcopy(original)
        index['exchanges'][0]['turn_ids'].append('unknown-turn')
        write(path, index)
        refreeze(self.case_path, self.case, path)
        with self.assertRaisesRegex(ValueError, 'unknown or missing turn'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
