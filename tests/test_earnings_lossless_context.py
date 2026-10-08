"""Fictitious lossless review transport; no model calls or private source text."""
import copy
import json
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_repair_context as context
from research import earnings_experiment as base


def size(value):
    return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


class LosslessContextTests(PassageFixture, unittest.TestCase):
    def state(self):
        return {'artifacts': {'financial': self.financial, 'retrieval': self.retrieval,
                              'analysis': self.report},
                'format': {'rows': {}, 'basis': {'text': '', 'citations': []}}, 'findings': []}

    def test_large_repeated_metadata_round_trips_unicode_nulls_and_report_verbatim(self):
        text = 'Fictional α\u00a0café 😀 source line.\r\n' * 60
        report = '<main>Complete fictional report — all paragraphs retained.</main>'
        original = {'report': report, 'source_blocks': [
            {'block_id': 'fake-' + str(i), 'text': text, 'path': '/fictional/' + 'x' * 180,
             'sha256': 'f' * 64, 'start': 0, 'end': len(text), 'offset_unit': 'unicode_character'}
            for i in range(170)],
            'field_changes': [{'id': str(i), 'before': text, 'after': text, 'reason': 'Fictional exact retention'}
                              for i in range(20)],
            'occurrence_inventory': [{'text': text, 'nullable': None, 'flag': False, 'number': i}
                                     for i in range(20)],
            'misc': [None, False, True, 0, 1.5, [], {}, '']}
        before = copy.deepcopy(original)
        self.assertGreater(size(original), context.MAX_CONTEXT_CHARACTERS)
        packed = context.compact_context(original)
        self.assertLess(context._bounded(packed), context.MAX_CONTEXT_CHARACTERS)
        self.assertEqual(packed['report'], report)
        self.assertEqual(context.expand_context(packed), original)
        self.assertEqual(original, before)
        self.assertEqual(packed, context.compact_context(original))
        self.assertIn(['field_changes'], packed['lossless_encoding']['tables'])
        self.assertIn('Resolve references before interpreting source text', packed['lossless_encoding']['notice'])

    def test_actual_builder_transport_retains_every_scope_passage_mapping_and_hash(self):
        before = self.state(); after = copy.deepcopy(before)
        after['artifacts']['analysis']['opening'] = 'Fictional corrected interpretation.'
        plan = {'operations': [{'id': 'fictional-edit', 'path': ['artifacts', 'analysis', 'opening'],
                               'reason': 'Fictional correction', 'citations': ['D001'],
                               'passage_ids': [self.ids[0]]}]}
        args = (before, after, plan, self.bundle, self.catalog,
                '<main>Full fictional report with no omitted paragraph.</main>', 'Fictional writing standard')
        with patch.object(context, 'compact_context', side_effect=lambda value: value):
            plain = context.build(*args)
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            packed = context.build(*args)
        restored = context.expand_context(packed)
        self.assertEqual(packed['report'], plain['report'])
        self.assertFalse(packed['stats']['truncated'])
        plain.pop('stats'); restored.pop('stats')
        self.assertEqual(restored, plain)
        self.assertEqual(restored['candidate_sha256'], base.digest(after))
        blocks = {b['block_id']: b for b in restored['source_blocks']}
        for row in restored['passages']['rows']:
            passage = dict(zip(restored['passages']['columns'], row))
            block = blocks[passage['block_id']]
            text = block['text'][passage['start'] - block['start']:passage['end'] - block['start']]
            self.assertEqual(context.evidence._sha_text(text), passage['span_sha256'])
            self.assertEqual(text, next(p['text'] for p in self.catalog['passages']
                                        if p['passage_id'] == passage['passage_id']))

    def test_heterogeneous_records_keep_missing_distinct_from_null(self):
        original = {'report': 'Complete report',
                    'field_changes': [{'id': 'one', 'text': 'Repeated fictional text ' * 100},
                                      {'id': 'two', 'text': 'Repeated fictional text ' * 100, 'optional': None}]}
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            packed = context.compact_context(original)
        self.assertNotIn(['field_changes'], packed['lossless_encoding']['tables'])
        self.assertEqual(context.expand_context(packed), original)

    def test_original_context_limit_still_rejects_noncompressible_report(self):
        original = {'report': 'F' * (context.MAX_CONTEXT_CHARACTERS + 1), 'metadata': []}
        packed = context.compact_context(original)
        self.assertEqual(packed, original)
        with self.assertRaisesRegex(context.ContextTooLarge, 'exceeds 330000'):
            context._bounded(packed)

    def test_small_context_shape_and_existing_passage_table_are_unchanged(self):
        original = {'report': 'Fictional report', 'passages': {'columns': ['id'], 'rows': [['P-fake']]}}
        self.assertEqual(context.compact_context(original), original)
        self.assertEqual(context.expand_context(original), original)

    def test_unknown_reference_or_reserved_source_shape_fails_closed(self):
        original = {'report': 'Complete report', 'repeated': ['Fictional repeated source ' * 200] * 4}
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            packed = context.compact_context(original)
            with self.assertRaisesRegex(ValueError, 'Reserved'):
                context.compact_context({'report': 'Complete report', 'injected': {context.STRING_REFERENCE: 'S0'}})
        changed = copy.deepcopy(packed)
        changed['repeated'][0][context.STRING_REFERENCE] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'Unknown shared'):
            context.expand_context(changed)


if __name__ == '__main__':
    unittest.main()
