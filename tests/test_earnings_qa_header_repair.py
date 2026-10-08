"""Fictitious exact source/header regression fixtures; no issuer data."""
import copy
import unittest
from research import earnings_qa_grounding as q


def fixture(question='Great. Thank you.', chief='Thank you.', role='management', routing_extra=''):
    lines = [('Q', 'Alex Example', 'analyst', 'Alex Example\nAnalyst, Example Bank\n' + question + '\n'),
             ('A', 'Chief Example', role, 'Chief Example\nPresident and CEO, Example Corp\n' + chief + '\n'),
             ('O', 'Operator', 'operator', 'Operator\nYour next question comes from the line of Bea Example from Fiction Bank. Your line is open. Please go ahead.' + routing_extra + '\n'),
             ('Q2', 'Bea Example', 'analyst', 'Bea Example\nAnalyst, Fiction Bank\nWhy did demand change?\n'),
             ('A2', 'Chief Example', 'management', 'Chief Example\nPresident and CEO, Example Corp\nFictional demand rose.\n')]
    turns, passages, cursor = [], [], 0
    for tid, speaker, kind, text in lines:
        turns.append(dict(id=tid,speaker=speaker,role=kind,start=cursor,end=cursor+len(text),section_kind='qa'))
        passages.append(dict(passage_id='P'+tid, scope_id=tid, text=text, start=cursor,end=cursor+len(text),sha256='fake-sha',span_sha256='fake-span', document_id='fake-source'))
        cursor += len(text)
    source=dict(document_id='fake-source',text_sha256='fake-sha')
    exchanges=[dict(id='E1',turn_ids=['Q','A','O'],question_turn_ids=['Q'],answer_turn_ids=['A']),
               dict(id='E2',turn_ids=['Q2','A2'],question_turn_ids=['Q2'],answer_turn_ids=['A2'])]
    return dict(transcript_index=dict(source=source,turns=turns,exchanges=exchanges)), dict(passages=passages)


class HeaderRepairTests(unittest.TestCase):
    def test_v1_default_is_preserved_and_v2_retains_header_source_offsets(self):
        bundle,catalog=fixture();original=copy.deepcopy((bundle,catalog))
        old=q.build(bundle,catalog);new=q.build(bundle,catalog,q.HEADER_VERSION)
        self.assertEqual(old['version'],q.VERSION)
        self.assertIsNone(old['exchanges'][0]['mechanical_disposition'])
        self.assertEqual(new['exchanges'][0]['mechanical_disposition'],'courtesy_only')
        self.assertEqual(new['exchanges'][0]['turns'][0]['passage_offsets'][0]['start'],0)
        self.assertEqual((bundle,catalog),original)

    def test_substantive_greeting_and_unknown_role_never_disappear(self):
        for options in [dict(question='Thank you. What changed?'),dict(role='unknown'),dict(routing_extra=' Revenue fell.')]:
            bundle,catalog=fixture(**options)
            self.assertIsNone(q.build(bundle,catalog,q.HEADER_VERSION)['exchanges'][0]['mechanical_disposition'])
        bundle,catalog=fixture(role='unknown')
        self.assertIn('unknown_speaker_role',q.build(bundle,catalog,q.HEADER_VERSION)['exchanges'][0]['flags'])

    def test_normalizer_binds_changes_and_keeps_substantive_rows(self):
        bundle,catalog=fixture();bundle['qa_grounding']=q.build(bundle,catalog,q.HEADER_VERSION)
        out={'exchange_coverage':[dict(exchange_id='E1',question='Old text',answer='Old text',consequence='Old text',question_passage_ids=[],answer_passage_ids=[],continuation_exchange_ids=[],grounding_status='unresolved',grounding_notes='Header blocked.'),dict(exchange_id='E2',question='Why?',answer='Rose',question_passage_ids=['PQ2'],answer_passage_ids=['PA2'],continuation_exchange_ids=[],grounding_status='bound',grounding_notes='Source supported.') ]}
        original=copy.deepcopy(out);derived,receipt=q.normalize_courtesy(out,bundle,catalog)
        self.assertEqual(out,original)
        self.assertEqual(derived['exchange_coverage'][1],out['exchange_coverage'][1])
        self.assertEqual(len(receipt),1)
        q.require_analysis_ready(derived,bundle,catalog)
        self.assertNotEqual(receipt[0]['before_sha256'],receipt[0]['after_sha256'])
        bundle['qa_grounding']['exchanges'][1]['mechanical_disposition']='courtesy_only'
        with self.assertRaisesRegex(ValueError,'replayable'):
            q.normalize_courtesy(out,bundle,catalog)

    def test_header_stripping_requires_exact_known_role_title(self):
        bundle,catalog=fixture()
        turn=bundle['transcript_index']['turns'][0]
        for raw in ['Alex Example\nAnalyst, Example Bank\nThank you.\nWhat changed?', 'Alex Example\nWe are grateful.\nThank you.', 'Analyst, Example Bank\nThank you.']:
            self.assertFalse(q._greeting(turn,[{'text':raw}],q.HEADER_VERSION))
        self.assertFalse(q._routing({'speaker':'Operator','role':'operator'},[{'text':'Operator\nYour next question comes from the line of Evil Revenue Fell from Fiction Bank. Your line is open. Please go ahead.'}],[('Bea Example','Fiction Bank')]))
