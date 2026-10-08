"""Fictitious source-bound Q&A tests; no provider calls or private company data."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture, PipelineTests
from test_earnings_compact_evidence import refreeze, write
from research import earnings_qa_grounding as grounding
from research import earnings_passage_pipeline as pipe
from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base
from research import earnings_passages as passages
from research import transcript_evidence as transcript


class GroundingTests(PassageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.bundle['qa_grounding'] = grounding.build(self.bundle, self.catalog)

    def test_explicit_identity_join_survives_shuffled_coverage_turns_and_passages(self):
        expected = self.bundle['qa_grounding']
        bundle, catalog = copy.deepcopy(self.bundle), copy.deepcopy(self.catalog)
        bundle['transcript_index']['turns'].reverse()
        bundle['transcript_index']['exchanges'].reverse()
        for e in bundle['transcript_index']['exchanges']:
            e['turn_ids'].reverse()
        catalog['passages'].reverse()
        self.assertEqual(expected, grounding.build(bundle, catalog))
        value = copy.deepcopy(self.retrieval)
        value['exchange_coverage'].reverse()
        grounding.require_analysis_ready(value, bundle, catalog)
        for e in expected['exchanges']:
            for turn in e['turns']:
                for pid in turn['passage_ids']:
                    p = next(p for p in catalog['passages'] if p['passage_id'] == pid)
                    self.assertTrue(turn['start'] <= p['start'] < p['end'] <= turn['end'])
                    self.assertEqual(self.text[p['start']:p['end']], p['text'])
        self.assertIn('not whether', expected['notice'])
        self.assertEqual(expected['annotation_status'], 'provisional')

    def test_neighbor_support_without_explicit_followup_is_rejected(self):
        out = copy.deepcopy(self.retrieval)
        out['exchange_coverage'][0]['answer_passage_ids'] = out['exchange_coverage'][1]['answer_passage_ids']
        with self.assertRaisesRegex(ValueError, 'outside the indexed'):
            grounding.validate_retrieval(out, self.bundle, self.catalog)
        out['exchange_coverage'][0]['continuation_exchange_ids'] = [out['exchange_coverage'][1]['exchange_id']]
        grounding.require_analysis_ready(out, self.bundle, self.catalog)
        # Reverse borrowing has no source-declared followup link.
        out = copy.deepcopy(self.retrieval)
        out['exchange_coverage'][1]['continuation_exchange_ids'] = [out['exchange_coverage'][0]['exchange_id']]
        with self.assertRaisesRegex(ValueError, 'explicit indexed followup'):
            grounding.validate_retrieval(out, self.bundle, self.catalog)

    def test_question_and_answer_role_support_cannot_be_swapped(self):
        out = copy.deepcopy(self.retrieval)
        row = out['exchange_coverage'][0]
        row['question_passage_ids'], row['answer_passage_ids'] = row['answer_passage_ids'], row['question_passage_ids']
        with self.assertRaisesRegex(ValueError, 'outside the indexed'):
            grounding.validate_retrieval(out, self.bundle, self.catalog)

    def test_unresolved_is_inspectable_but_cannot_reach_analysis(self):
        out = copy.deepcopy(self.retrieval)
        out['exchange_coverage'][0].update(grounding_status='unresolved', answer_passage_ids=[],
                                         grounding_notes='Fictitious answer attribution needs review.')
        grounding.validate_retrieval(out, self.bundle, self.catalog)
        with self.assertRaisesRegex(ValueError, 'unresolved; repair source attribution'):
            pipe.validate('retrieval', out, self.bundle, self.catalog)
        with self.assertRaisesRegex(ValueError, 'unresolved; repair source attribution'):
            pipe.prompt('analysis', self.bundle, 'Fictitious standard',
                        {'financial': self.financial, 'retrieval': out}, [], self.catalog)

    def _replace_call(self, text):
        path = self.root / 'call.txt'; path.write_bytes(text.encode())
        index = transcript.index_transcript(text, {'document_id': 'fictional-call', 'text_sha256': base.sha(path),
            'speakers': [{'name': 'Chief', 'role': 'management'}, {'name': 'Questioner', 'role': 'analyst'}]})
        write(self.root / 'index-source.json', index)
        refreeze(self.casepath, self.case, path)
        refreeze(self.casepath, self.case, self.root / 'index-source.json')
        manifest = evidence.prepare(self.casepath, self.root / 'changed-evidence')
        bundle = evidence.load_bundle(manifest); catalog = passages.catalog(manifest)
        bundle['qa_grounding'] = grounding.build(bundle, catalog)
        return bundle, catalog

    def test_greeting_only_question_remains_a_flagged_source_turn(self):
        bundle, catalog = self._replace_call('Fictitious call.\nQ&A\nQuestioner: Hello.\nChief: Fictional revenue rose.\n')
        e = bundle['qa_grounding']['exchanges'][0]
        self.assertIn('courtesy_only_question_turn', e['flags'])
        self.assertTrue(e['turns'][0]['courtesy_only'])
        qpid = e['turns'][0]['passage_ids'][0]
        row = {'exchange_id': e['exchange_id'], 'question_passage_ids': [qpid], 'answer_passage_ids': [],
               'continuation_exchange_ids': [], 'grounding_status': 'unresolved', 'grounding_notes': 'Greeting only.'}
        with self.assertRaisesRegex(ValueError, 'outside the indexed'):
            grounding.validate_retrieval({'exchange_coverage': [row]}, bundle, catalog)
        row['question_passage_ids'] = []
        grounding.validate_retrieval({'exchange_coverage': [row]}, bundle, catalog)
        self.assertIn('Hello.', next(p for p in catalog['passages'] if p['passage_id'] == qpid)['text'])

    def test_exact_courtesy_only_exchange_is_audited_without_blocking(self):
        bundle, catalog = self._replace_call('Fictitious call.\nQ&A\nQuestioner: Hello.\nChief: Thank you.\n')
        e = bundle['qa_grounding']['exchanges'][0]
        self.assertEqual(e['mechanical_disposition'], 'courtesy_only')
        row = {'exchange_id': e['exchange_id'], 'question_passage_ids': [], 'answer_passage_ids': [],
               'continuation_exchange_ids': [], 'grounding_status': 'courtesy_only',
               'grounding_notes': 'Exact courtesy-only turns retained in original source.'}
        grounding.require_analysis_ready({'exchange_coverage': [row]}, bundle, catalog)
        self.assertTrue(e['flags'])  # Keep the audit trail rather than deleting a row.
        substantive = copy.deepcopy(self.retrieval)
        substantive['exchange_coverage'][0].update(grounding_status='courtesy_only',
            question_passage_ids=[], answer_passage_ids=[])
        with self.assertRaisesRegex(ValueError, 'Courtesy disposition'):
            grounding.require_analysis_ready(substantive, self.bundle, self.catalog)

    def test_greeting_then_real_question_is_retained(self):
        bundle, _ = self._replace_call('Fictitious call.\nQ&A\nQuestioner: Hello. What changed?\nChief: Fictional demand rose.\n')
        e = bundle['qa_grounding']['exchanges'][0]
        self.assertFalse(e['turns'][0]['courtesy_only'])
        self.assertNotIn('courtesy_only_question_turn', e['flags'])

    def test_operator_interruption_is_not_silently_an_answer(self):
        bundle, catalog = self._replace_call('Fictitious call.\nQ&A\nQuestioner: What changed?\nOperator: Please hold.\nChief: Fictional demand rose.\n')
        e = bundle['qa_grounding']['exchanges'][0]
        self.assertIn('interrupted_response_boundary', e['flags'])
        row = {'exchange_id': e['exchange_id'], 'question_passage_ids': e['turns'][0]['passage_ids'],
               'answer_passage_ids': e['turns'][2]['passage_ids'], 'continuation_exchange_ids': [],
               'grounding_status': 'bound', 'grounding_notes': 'Fictitious claim.'}
        with self.assertRaisesRegex(ValueError, 'must remain unresolved'):
            grounding.validate_retrieval({'exchange_coverage': [row]}, bundle, catalog)
        row['grounding_status'] = 'unresolved'
        grounding.validate_retrieval({'exchange_coverage': [row]}, bundle, catalog)
        row['answer_passage_ids'] = e['turns'][1]['passage_ids']
        with self.assertRaisesRegex(ValueError, 'outside the indexed'):
            grounding.validate_retrieval({'exchange_coverage': [row]}, bundle, catalog)

    @staticmethod
    def _coverage(bundle):
        return {'exchange_coverage': [dict(exchange_id=e['exchange_id'],
                    question_passage_ids=[pid for t in e['turns'] if t['id'] in e['question_turn_ids'] for pid in t['passage_ids']],
                    answer_passage_ids=[pid for t in e['turns'] if t['id'] in e['answer_turn_ids'] for pid in t['passage_ids']],
                    continuation_exchange_ids=[], grounding_status='bound', grounding_notes='Fictitious membership only.')
                for e in bundle['qa_grounding']['exchanges']]}

    def test_substantive_unassigned_qa_blocks_even_with_complete_exchange_coverage(self):
        bundle, catalog = self._replace_call('Fictitious call.\nQ&A\nChief: Fictional margins fell.\nQuestioner: Why did demand rise?\nChief: Fictional demand rose.\n')
        out = self._coverage(bundle)
        grounding.validate_retrieval(out, bundle, catalog)
        unassigned = bundle['qa_grounding']['unassigned_qa_turns']
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]['mechanical_disposition'], 'unresolved')
        self.assertTrue(unassigned[0]['passage_offsets'])
        with self.assertRaisesRegex(ValueError, 'Substantive unassigned Q&A turns'):
            grounding.require_analysis_ready(out, bundle, catalog)
        # Omitting the coverage ledger entry cannot hide an unmapped source turn.
        broken = copy.deepcopy(bundle)
        broken['transcript_index']['coverage']['unassigned_qa_turn_ids'] = []
        with self.assertRaisesRegex(ValueError, 'differs from actual turn membership'):
            grounding.build(broken, catalog)

    def test_unassigned_exact_courtesy_and_moderator_routing_are_audited(self):
        bundle, catalog = self._replace_call('Fictitious call.\nQ&A\nChief: Hello.\nOperator: We now turn to questions.\nQuestioner: Why did demand rise?\nChief: Fictional demand rose.\n')
        rows = bundle['qa_grounding']['unassigned_qa_turns']
        self.assertEqual([r['mechanical_disposition'] for r in rows], ['courtesy_only', 'moderator_routing_only'])
        grounding.require_analysis_ready(self._coverage(bundle), bundle, catalog)
        self.assertEqual(set(bundle['qa_grounding']['unassigned_qa_turn_ids']), {r['id'] for r in rows})

    def test_unassigned_coverage_unknown_duplicate_or_mapped_ids_rejected(self):
        for declared in [['missing-turn'], [self.bundle['transcript_index']['turns'][-1]['id']],
                         ['missing-turn', 'missing-turn']]:
            bundle = copy.deepcopy(self.bundle)
            bundle['transcript_index']['coverage']['unassigned_qa_turn_ids'] = declared
            with self.subTest(declared=declared), self.assertRaisesRegex(ValueError, 'Q&A unassigned coverage'):
                grounding.build(bundle, self.catalog)

    def test_source_attribution_preflight_spends_no_model_calls(self):
        bundle=copy.deepcopy(self.bundle)
        bundle['qa_grounding']['version']=grounding.HEADER_VERSION
        bundle['qa_grounding']['exchanges'][0]['flags']=['unknown_speaker_role']
        bundle['qa_grounding']['exchanges'][0]['mechanical_disposition']=None
        with patch.object(pipe,'load',return_value=({'qa_grounding':grounding.HEADER_VERSION},bundle,self.catalog)), patch.object(pipe,'run_role',side_effect=AssertionError('must not launch')):
            with self.assertRaisesRegex(ValueError,'before any model call'):
                pipe.run(self.root/'preflight')

    def test_new_freeze_binds_sidecar_legacy_optout_leaves_plain_catalog(self):
        writing = self.root / 'writing.txt'; writing.write_text('Fictitious standard')
        root = self.root / 'grounded'
        protocol = pipe.freeze(self.casepath, root, writing)
        self.assertEqual(protocol['qa_grounding'], grounding.HEADER_VERSION)
        v1 = self.root/'explicit-v1'
        pipe.freeze(self.casepath, v1, writing, qa_grounding_version=grounding.VERSION)
        self.assertEqual(pipe.load(v1)[1]['qa_grounding']['version'], grounding.VERSION)
        _, bundle, catalog = pipe.load(root)
        self.assertIn('qa_grounding', bundle)
        self.assertNotIn('qa_grounding', catalog)
        self.assertIn('earnings_qa_grounding.py', [Path(c['path']).name for c in protocol['code']])
        for efficient in (False, True):
            text = pipe.prompt('retrieval', bundle, 'Fictitious standard', {'financial': pipe.bind_efficient_financial(self.financial, bundle) if efficient else self.financial}, [], catalog, efficient=efficient)
            self.assertIn('question_passage_ids', text)
            self.assertIn('SOURCE-BOUND Q&A MEMBERSHIP GATE', text)
        legacy = self.root / 'legacy'
        pipe.freeze(self.casepath, legacy, writing, qa_grounding=False)
        old, bundle, catalog = pipe.load(legacy)
        self.assertNotIn('qa_grounding', old)
        self.assertNotIn('qa_grounding', bundle)
        hashes = {Path(c['path']).name: c['sha256'] for c in old['code']}
        self.assertIn('earnings_qa_grounding.py', hashes)
        self.assertIn('earnings_budget.py', hashes)
        original_sha = base.sha
        def changed_helper(path):
            return '0' * 64 if Path(path).name == 'earnings_qa_grounding.py' else original_sha(path)
        with patch.object(base, 'sha', side_effect=changed_helper), self.assertRaisesRegex(ValueError, 'Frozen input/code changed'):
            pipe.load(legacy)
        out = copy.deepcopy(self.retrieval)
        for row in out['exchange_coverage']:
            for k in grounding.FIELDS: row.pop(k)
        pipe.validate('retrieval', out, bundle, catalog)

    def test_resealed_tampered_index_is_rejected_against_original_membership(self):
        writing = self.root / 'writing.txt'; writing.write_text('Fictitious standard')
        root = self.root / 'grounded'; pipe.freeze(self.casepath, root, writing)
        index = base.read(root / 'qa-grounding.json')
        index['exchanges'][0]['turns'][0]['role'] = 'management'
        (root / 'qa-grounding.json').write_text(__import__('json').dumps(index))
        protocol = base.read(root / 'protocol.json'); protocol['qa_grounding_sha256'] = base.sha(root / 'qa-grounding.json')
        (root / 'protocol.json').write_text(__import__('json').dumps(protocol))
        with self.assertRaisesRegex(ValueError, 'differs from original indexed sources'):
            pipe.load(root)


class GroundingRunTests(PipelineTests):
    def test_mismatched_exchange_membership_stops_analysis_and_replays_block(self):
        self.retrieval['exchange_coverage'][0]['answer_passage_ids'] = self.retrieval['exchange_coverage'][1]['answer_passage_ids']
        result = pipe.run(self.output)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(any(role in ('analysis', 'review') for role, _ in self.calls))
        self.assertEqual(pipe.verify(self.output), result)
