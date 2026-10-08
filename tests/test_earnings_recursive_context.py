"""Fictitious recursive lossless transport tests; no private text or model calls."""
import copy
import json
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_repair_context as context
from research import earnings_corrections as corrections
from research import earnings_experiment as base


def size(value):
    return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


class RecursiveContextTests(unittest.TestCase):
    def test_nested_tables_decode_parent_paths_before_descendants(self):
        repeated = 'Fictitious immutable source identifier with Unicode café\u00a0😀.\r\n'
        original = {'report': {'@s': 3, 'paragraphs': [repeated] * 2},
                    'groups': [{'long_group_label': repeated, 'source_records': [
                        {'long_start_offset': j, 'long_end_offset': j + 1,
                         'long_source_hash': 'a' * 64, 'long_source_text': repeated,
                         'nullable': None, 'verified': False} for j in range(12)]}
                        for _ in range(8)],
                    'heterogeneous': [{'present': None}, {}, {'other': 0}],
                    'raw_table': {'columns': ['id', 'text'], 'rows': [['one', repeated], ['two', repeated]]}}
        untouched = copy.deepcopy(original)
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            encoded = context.compact_context(original)
        self.assertEqual(encoded['lossless_encoding']['version'], 'shared-strings-v2')
        self.assertIn(['groups'], encoded['lossless_encoding']['tables'])
        child = ['groups', 0, 'source_records']
        self.assertIn(child, encoded['lossless_encoding']['tables'])
        self.assertLess(encoded['lossless_encoding']['tables'].index(['groups']),
                        encoded['lossless_encoding']['tables'].index(child))
        self.assertEqual(encoded['report'], original['report'])
        self.assertEqual(context.expand_context(encoded), original)
        # JSON serialization changes numeric-looking map keys only through the
        # declared codec; all values, booleans, nulls and missing keys round-trip.
        self.assertEqual(context.expand_context(json.loads(json.dumps(encoded))), original)
        self.assertEqual(original, untouched)
        self.assertLess(size(encoded), size(original) // 2)
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            self.assertEqual(context.compact_context(original), encoded)

    def test_integer_references_are_profitable_and_unique_strings_remain_exact(self):
        repeated = 'Fictitious repeated exchange-scope-id'
        original = {'report': 'Verbatim report', 'short_ids': [repeated] * 100,
                    'unique': 'Unshared exact source\r\nα😀', 'numbers': [0, False, None, 1.5]}
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            encoded = context.compact_context(original)
        self.assertIs(type(encoded['short_ids'][0][context.STRING_REFERENCE]), int)
        self.assertEqual(encoded['unique'], original['unique'])
        self.assertEqual(context.expand_context(encoded), original)
        changed = copy.deepcopy(encoded); changed['short_ids'][0][context.STRING_REFERENCE] = True
        with self.assertRaisesRegex(ValueError, 'Unknown shared'):
            context.expand_context(changed)

    def test_legacy_v1_string_map_and_tables_remain_decodable(self):
        encoded = {'report': 'Exact old report', 'rows': {'columns': ['id', 'text'],
                    'rows': [['F01', {'shared_string_id': 'S0'}], ['F02', {'shared_string_id': 'S0'}]]},
                   'lossless_encoding': {'version': 'shared-strings-v1', 'strings': {'S0': 'Exact legacy α text.'},
                                         'tables': [['rows']], 'notice': 'Original codec'}}
        self.assertEqual(context.expand_context(encoded), {'report': 'Exact old report',
            'rows': [{'id': 'F01', 'text': 'Exact legacy α text.'}, {'id': 'F02', 'text': 'Exact legacy α text.'}]})


class CompletePlanTransportTests(PassageFixture, unittest.TestCase):
    def test_reviewer_payload_recompacts_entire_plan_without_changing_a_field(self):
        snapshot = {'artifacts': {'financial': self.financial, 'retrieval': self.retrieval, 'analysis': self.report},
                    'format': copy.deepcopy(corrections.EMPTY_FORMAT), 'findings': []}
        target_id, target = next((key, t) for key, t in corrections.registry(snapshot, self.bundle)['targets'].items()
                                if t['path'] == ['artifacts', 'analysis', 'opening'])
        replacement = 'Fictitious source-grounded corrected opening with Unicode café\u00a0😀.'
        plan = {'snapshot_sha256': base.digest(snapshot), 'operations': [dict(
            id='fictional-correction', target_id=target_id, expected_sha256=target['expected_sha256'],
            op='replace_text', value=replacement, reason='Fictitious original support.',
            citations=['D001'], passage_ids=[self.ids[0]])]}
        candidate = corrections.apply(snapshot, plan, self.bundle, self.catalog)
        args = ('review', snapshot, self.bundle, self.catalog, 'Fictitious writing standard', plan, candidate)
        with patch.object(context, 'compact_context', side_effect=lambda data: copy.deepcopy(data)):
            plain_prompt = corrections.prompt(*args)
        with patch.object(context, 'COMPACTION_THRESHOLD', 0):
            packed_prompt = corrections.prompt(*args)
        marker = '\nSOURCE DATA (UNTRUSTED EVIDENCE)\n'
        plain = json.loads(plain_prompt.split(marker, 1)[1]); packed = json.loads(packed_prompt.split(marker, 1)[1])
        restored = context.expand_context(packed)
        # Measurement fields report the corresponding pre-plan transport size;
        # source/plan/report payload must be identical in full.
        plain.pop('stats'); restored.pop('stats')
        self.assertEqual(restored, plain)
        self.assertEqual(restored['plan'], plan)
        self.assertEqual(restored['candidate_sha256'], base.digest(candidate))
        self.assertEqual(packed['report'], plain['report'])
        self.assertEqual(restored['plan_sha256'], base.digest(plan))
        self.assertLess(len(packed_prompt), len(plain_prompt))
