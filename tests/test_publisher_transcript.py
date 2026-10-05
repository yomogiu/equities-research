"""Fictional timed transcript layouts and exact archived offset checks."""
import hashlib
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from research import transcript_evidence as transcript, earnings_passages as passages
from research.source_parse import page


def block(name, role, speech):
    label = f'<div class="text-sm italic text-muted">{role}</div>' if role else ''
    return (f'<div class="border-t border-sharp first:border-t-0"><div class="text-lg font-bold">{name}</div>'
            f'{label}<p><span class="transcript-sentence" data-start-sec="1">{speech}</span></p></div>')


def fixture():
    raw = ('<html><body><div>Provider Summary: invented comparison.</div>'
           + block('Operator', '', 'Welcome to the fictional call.')
           + block('Jane Example', 'CEO, Fictional Widgets', 'Revenue grew €5 million.')
           + block('Alex Sample', 'Analyst, Fictional Research', 'Why did revenue grow?')
           + block('Jane Example', 'CEO, Fictional Widgets', 'We shipped more widgets.')
           + block('Alex Sample', 'Analyst, Fictional Research', 'Why did revenue grow?')
           + block('Pat Example', 'Guest, Fictional Supplier', 'Our orders increased.')
           + block('Operator', '', 'The call is concluded.')
           + '<div>Publisher footer: Subscribe.</div></body></html>').encode()
    text = page(raw, '').text
    source = {'document_id': 'fictional-call', 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'raw_sha256': hashlib.sha256(raw).hexdigest(), 'issuer_names': ['Fictional Widgets, Inc.']}
    return raw, text, source


class PublisherTranscriptTests(unittest.TestCase):
    def test_original_offsets_provisional_roles_and_repeated_turns(self):
        raw, text, source = fixture()
        index = transcript.index_publisher_transcript(text, source, raw)
        self.assertEqual(len(index['exchanges']), 2)
        self.assertEqual(len(index['turns']), 7)
        self.assertEqual(index['boundary_review'], 'provisional')
        self.assertTrue(index['needs_review'])
        self.assertEqual(index['turns'][5]['role'], 'unknown')
        questions = [t for t in index['turns'] if t['role'] == 'analyst']
        self.assertNotEqual(questions[0]['start'], questions[1]['start'])
        for t in index['turns']:
            self.assertTrue(text[t['start']:t['end']].startswith(t['speaker']+'\n'))
        self.assertEqual(index['call_span']['start'], text.index('Operator'))
        self.assertEqual(text[index['call_span']['end']:].strip(), 'Publisher footer: Subscribe.')
        self.assertNotIn('invented comparison', ''.join(text[t['start']:t['end']] for t in index['turns']))
        self.assertEqual(index['raw_sha256'], source['raw_sha256'])

    def test_management_or_unknown_opening_is_preserved_before_first_operator(self):
        raw = ('<html><div>Provider summary</div>'
               + block('Speaker 1', '', 'Our CEO will join this fictional event.')
               + block('Jane Example', 'CEO, Fictional Widgets', 'Opening prepared remarks.')
               + block('Operator', '', 'Our first question follows.')
               + block('Alex Sample', 'Analyst, Fictional Research', 'What changed?')
               + block('Jane Example', 'CEO, Fictional Widgets', 'Fictional shipments grew.')
               + '<div>Footer</div></html>').encode()
        text = page(raw, '').text
        source = {'document_id': 'fictional-call', 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                  'raw_sha256': hashlib.sha256(raw).hexdigest(), 'issuer_names': ['Fictional Widgets, Inc.']}
        index = transcript.index_publisher_transcript(text, source, raw)
        self.assertEqual(index['turns'][0]['speaker'], 'Speaker 1')
        self.assertEqual(index['turns'][0]['role'], 'unknown')
        self.assertEqual(index['call_span']['start'], text.index('Speaker 1'))
        self.assertEqual(len(index['exchanges']), 1)
        self.assertIn('Opening prepared remarks.', text[index['sections'][0]['start']:index['sections'][0]['end']])

    def test_external_leadership_is_not_issuer_management(self):
        raw = ('<html>'
               + block('Jane Example', 'CEO, Fictional Widgets, Inc.', 'Welcome.')
               + block('External Leader', 'Chairman and CEO, Fictional Research', 'What drives growth?')
               + block('External Analyst', 'Institutional Research Analyst, Fictional Research', 'What changed?')
               + block('Independent Person', 'Independent Analyst', 'What about margins?')
               + block('Unknown Executive', 'CFO', 'Unattributed company role.')
               + block('Jane Example', 'CEO, Fictional Widgets', 'More shipments.')
               + '</html>').encode()
        text = page(raw, '').text
        source = {'document_id': 'fictional-call', 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                  'raw_sha256': hashlib.sha256(raw).hexdigest(), 'issuer_names': ['FICTIONAL WIDGETS INC']}
        index = transcript.index_publisher_transcript(text, source, raw)
        self.assertEqual([t['role'] for t in index['turns']],
                         ['management', 'unknown', 'analyst', 'analyst', 'unknown', 'management'])
        self.assertEqual(index['issuer_affiliation']['names'], ['FICTIONAL WIDGETS INC'])
        self.assertEqual(index['boundary_review'], 'provisional')
        no_identity = transcript.index_publisher_transcript(text, dict(source, issuer_names=[]), raw)
        self.assertEqual(no_identity['turns'][0]['role'], 'unknown')
        self.assertEqual(no_identity['turns'][-1]['role'], 'unknown')
        wrong_identity = transcript.index_publisher_transcript(text, dict(source, issuer_names=['Fictional Widgets Research']), raw)
        self.assertEqual(wrong_identity['turns'][0]['role'], 'unknown')

    def test_mutated_raw_or_text_rejected_and_missing_interior_block_fails(self):
        raw, text, source = fixture()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            transcript.index_publisher_transcript(text, source, raw+b'x')
        changed = text.replace('We shipped more widgets.', 'Different words.')
        with self.assertRaises(ValueError):
            transcript.index_publisher_transcript(changed, source, raw)
        changed = raw.replace(b'<div class="border-t border-sharp first:border-t-0"><div class="text-lg font-bold">Jane Example</div><div class="text-sm italic text-muted">CEO, Fictional Widgets</div><p><span class="transcript-sentence" data-start-sec="1">We shipped more widgets.</span></p></div>', b'')
        with self.assertRaisesRegex(ValueError, 'exactly cover'):
            transcript.index_publisher_transcript(text, dict(source, raw_sha256=hashlib.sha256(changed).hexdigest()), changed)

    def test_unrecognized_first_block_cannot_silently_drop_opening_speech(self):
        raw, text, source = fixture()
        changed = raw.replace(b'border-t border-sharp first:border-t-0', b'changed-layout', 1)
        with self.assertRaisesRegex(ValueError, 'outside recognized'):
            transcript.index_publisher_transcript(text, dict(source, raw_sha256=hashlib.sha256(changed).hexdigest()), changed)

    def test_unsupported_layout_retains_conservative_fallback(self):
        raw = b'<p>Unstructured fictional text.</p>'
        text = page(raw, '').text
        source = {'document_id': 'fictional', 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                  'raw_sha256': hashlib.sha256(raw).hexdigest(), 'issuer_names': ['Fictional Widgets, Inc.']}
        index = transcript.index_publisher_transcript(text, source, raw)
        self.assertEqual(index['exchanges'], [])
        self.assertNotIn('call_span', index)

    def test_call_only_model_view_preserves_interior_gaps_and_excluded_receipt(self):
        raw, text, source = fixture()
        index = transcript.index_publisher_transcript(text, source, raw)
        with patch.object(passages.evidence, 'transcript_view', return_value={'text': text, 'index': index}):
            view = passages.input_view(None, {'passages': []})
        self.assertEqual(view['excluded_transcript_spans'], index['excluded_spans'])
        context = ''.join(g['text'] for g in view['unassigned_transcript_spans'])
        self.assertNotIn('Provider', context)
        self.assertNotIn('Subscribe', context)
        self.assertTrue(all(index['call_span']['start'] <= g['start'] < g['end'] <= index['call_span']['end']
                            for g in view['unassigned_transcript_spans']))

    def test_provisional_cannot_impersonate_reviewed_annotation(self):
        raw, text, source = fixture()
        with self.assertRaisesRegex(ValueError, 'not both'):
            transcript.index_transcript(text, source, {}, provisional_boundaries={})


class PreparePublisherTranscriptTests(unittest.TestCase):
    def test_report_preparation_reads_raw_layout_and_retains_original_text(self):
        from research import earnings_report_flow as flow
        raw, text, source = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'call.html').write_bytes(raw)
            (root/'call.txt').write_text(text)
            (root/'filing.html').write_bytes(b'<html>Fictional filing</html>')
            (root/'filing.txt').write_text('Fictional filing')
            (root/'writing.md').write_text('Fictional standard')
            def document(name, kind):
                return {'document_id': 'fictional-'+name, 'kind': kind, 'period': 'FY2040-Q1',
                        'completeness': 'full', 'source_url': 'https://example.invalid/'+name,
                        'raw_path': name+'.html', 'text_path': name+'.txt',
                        'raw_sha256': hashlib.sha256((root/(name+'.html')).read_bytes()).hexdigest(),
                        'text_sha256': hashlib.sha256((root/(name+'.txt')).read_bytes()).hexdigest()}
            packet = {'documents': [document('filing', 'periodic_filing'), document('call', 'transcript')],
                      'period': 'FY2040-Q1', 'issuer_id': 'fictional:widgets'}
            with patch.object(flow, 'validate_packet', return_value=packet), \
                 patch.object(flow.financial, 'extract_inline_xbrl', return_value={'observations': [{}]}), \
                 patch.object(flow.library, 'catalog', return_value={'catalog_id': 'fictional-catalog', 'issuers': {'fictional:widgets': {'issuer': 'Fictional Widgets, Inc.'}}}), \
                 patch.object(flow.base, 'validate_case'):
                flow.prepare(root, 'fictional-packet', root/'prepared', root/'writing.md', 'Fictional test')
            index = json.loads((root/'prepared/transcript-index.json').read_text())
            self.assertEqual(len(index['exchanges']), 2)
            self.assertEqual(index['boundary_review'], 'provisional')
            self.assertEqual((root/'call.txt').read_text(), text)
            self.assertEqual(index['source']['text_sha256'], source['text_sha256'])
