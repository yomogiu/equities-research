"""Entirely fictitious transcript fixtures; no issuer data."""
import copy
import hashlib
import unittest

from research.transcript_evidence import index_transcript, validate_findings


TEXT = ('Prepared remarks\nExecutive A: Fictional €10 revenue.\n'
        'Questions and Answers\nOperator: First question.\n'
        'Analyst A: Is utilization rising?\nAnalyst A: And when?\n'
        'Executive A: It rose to 80%.\nExecutive B: In July.\n'
        'Operator: Please continue.\nAnalyst A: What is the denominator?\n'
        'Executive A: Installed capacity.\nAnalyst B: Is this audited?\n'
        'Executive B: Not independently.\n')
SPEAKERS = [{'name': 'Executive A', 'role': 'management'},
            {'name': 'Executive B', 'role': 'management'},
            {'name': 'Analyst A', 'role': 'analyst'},
            {'name': 'Analyst B', 'role': 'analyst'}]


def source(text=TEXT):
    return {'document_id': 'fictional-source',
            'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'speakers': SPEAKERS}


def fixture():
    index = index_transcript(TEXT, source())
    exchange = index['exchanges'][0]
    quote = 'It rose to 80%.'
    start = TEXT.index(quote)
    finding = {'id': 'fictitious-finding', 'exchange_ids': [exchange['id']],
               'answer_classification': 'partial', 'question_assessed': 'Utilization and timing.',
               'answer_assessed': 'Gives a level and month.',
               'technical_mechanism': 'Installed capacity utilization.',
               'financial_implication': 'Insufficient evidence of margin consequences.',
               'counterevidence': 'No comparable historical denominator supplied.',
               'uncertainty': 'Reported figure is not independently verified.',
               'next_test': 'Compare utilization denominator with next report.',
               'fact_ids': ['fictional-fact'],
               'quotes': [{'exchange_id': exchange['id'], 'document_id': 'fictional-source',
                           'start': start, 'end': start + len(quote), 'text': quote}]}
    return index, [finding]


class TranscriptEvidenceTests(unittest.TestCase):
    def test_multipart_questions_multiple_answers_and_followup(self):
        index = index_transcript(TEXT, source())
        self.assertEqual(len(index['exchanges']), 3)
        first, followup, other = index['exchanges']
        self.assertEqual(len(first['question_turn_ids']), 2)
        self.assertEqual(len(first['answer_turn_ids']), 2)
        self.assertEqual(len(first['operator_turn_ids']), 1)
        self.assertEqual(followup['followup_of'], first['id'])
        self.assertIsNone(other['followup_of'])
        self.assertTrue(index['needs_review'])
        self.assertEqual(len(index['coverage']['unassigned_qa_turn_ids']), 1)

    def test_unicode_offsets_are_not_byte_offsets(self):
        index, findings = fixture()
        q = findings[0]['quotes'][0]
        self.assertNotEqual(q['start'], len(TEXT[:q['start']].encode()))
        result = validate_findings(findings, index, TEXT, ['fictional-fact'])
        self.assertEqual(result['status'], 'structurally_valid')
        self.assertEqual(result['semantic_review'], 'required')

    def test_changed_source_rejected(self):
        index, findings = fixture()
        with self.assertRaisesRegex(ValueError, 'Source hash'):
            validate_findings(findings, index, TEXT.replace('80%', '90%'), ['fictional-fact'])
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            index_transcript(TEXT + 'Changed', source())

    def test_invented_quote_or_wrong_exchange_or_document_rejected(self):
        for mutation in ('text', 'exchange', 'document'):
            index, findings = fixture()
            q = findings[0]['quotes'][0]
            if mutation == 'text':
                q['text'] = 'It rose to 99%.'
            elif mutation == 'exchange':
                eid = index['exchanges'][1]['id']
                findings[0]['exchange_ids'] = [eid]
                q['exchange_id'] = eid
            else:
                q['document_id'] = 'wrong-source'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_findings(findings, index, TEXT, ['fictional-fact'])

    def test_fake_fact_or_missing_evaluation_fields_rejected(self):
        index, findings = fixture()
        with self.assertRaisesRegex(ValueError, 'fact references'):
            validate_findings(findings, index, TEXT, [])
        for field in ('technical_mechanism', 'counterevidence', 'uncertainty', 'next_test'):
            damaged = copy.deepcopy(findings)
            damaged[0][field] = ''
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_findings(damaged, index, TEXT, ['fictional-fact'])

    def test_ids_are_stable_and_change_with_source(self):
        a = index_transcript(TEXT, source())
        b = index_transcript(TEXT, source())
        self.assertEqual(a, b)
        changed = TEXT.replace('80%', '90%')
        c = index_transcript(changed, source(changed))
        self.assertNotEqual(a['turns'][0]['id'], c['turns'][0]['id'])
        self.assertEqual(len(a['parser_sha256']), 64)

    def test_reviewed_annotations_and_no_duplicate_source_text(self):
        provisional = index_transcript(TEXT, source())
        boundaries = {'reviewed': True, 'review_id': 'fixture-reviewed-1',
                      'sections': provisional['sections'], 'turns': provisional['turns']}
        reviewed = index_transcript(TEXT, source(), boundaries)
        self.assertFalse(reviewed['needs_review'])
        self.assertEqual(reviewed['boundary_review'], 'reviewed')
        self.assertFalse(any('text' in t for t in reviewed['turns']))
        self.assertFalse(any('text' in t for t in reviewed['sections']))

    def test_overlap_invalid_offset_and_unknown_layout(self):
        index = index_transcript(TEXT, source())
        boundaries = {'reviewed': True, 'sections': index['sections'], 'turns': copy.deepcopy(index['turns'])}
        boundaries['turns'][1]['start'] = boundaries['turns'][0]['start']
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            index_transcript(TEXT, source(), boundaries)
        boundaries['turns'][1]['start'] = True
        with self.assertRaises(ValueError):
            index_transcript(TEXT, source(), boundaries)
        opaque = 'Opaque unlabelled transcript content.'
        result = index_transcript(opaque, source(opaque))
        self.assertEqual(result['exchanges'], [])
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['coverage']['assigned_characters'], 0)
        self.assertEqual(result['coverage']['unassigned_spans'], [{'start': 0, 'end': len(opaque)}])

    def test_reviewed_boundaries_reject_different_source(self):
        index = index_transcript(TEXT, source())
        boundaries = {'reviewed': True, 'source_sha256': '0' * 64,
                      'sections': index['sections'], 'turns': index['turns']}
        with self.assertRaisesRegex(ValueError, 'different source'):
            index_transcript(TEXT, source(), boundaries)

    def test_unanswered_question_explicit(self):
        text = 'Q&A\nAnalyst A: What happened?\n'
        index = index_transcript(text, source(text))
        self.assertEqual(index['exchanges'][0]['status'], 'no_identified_answer')


if __name__ == '__main__':
    unittest.main()
