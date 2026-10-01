"""Synthetic quotation integrity and bounded-repair tests. No model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_earnings_compact_evidence import fixture, refreeze, write
from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base
from research import earnings_passages as passages
from research import earnings_passage_pipeline as pipe


class PassageFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.casepath, self.case, self.text = fixture(self.root)
        self.case['case_id'] = 'FICTIONAL-CASE'
        # Same visually rendered value with NBSP, CRLF, Unicode and repeated text.
        path = self.root / 'note.txt'
        path.write_bytes('Fictitious $9.5\u00a0billion.\r\n'.encode())
        self.case['sources'].append({'document_id': 'fictional-note', 'kind': 'release', 'representation': 'text', 'path': str(path), 'sha256': base.sha(path)})
        write(self.casepath, self.case)
        self.manifest = evidence.prepare(self.casepath, self.root / 'evidence')
        self.bundle = evidence.load_bundle(self.manifest)
        self.catalog = passages.catalog(self.manifest)
        self.ids = [p['passage_id'] for p in self.catalog['passages'] if p['text'].strip()][:4]
        self.retrieval = {'selected_document_ids': ['D001'], 'exchange_coverage': [
            {'exchange_id': e['id'], 'question': 'Fictional question', 'answer': 'Fictional answer',
             'consequence': 'Fictional implication'} for e in self.bundle['transcript_index']['exchanges']],
            'document_findings': [], 'quotes': [{'passage_id': i} for i in self.ids]}
        self.financial = {'rows': [{'label': 'Fictional revenue', 'fact_ids': ['F002']} for _ in range(4)], 'context': [], 'gaps': []}
        self.report = {'title': 'Fictional report', 'opening': 'Fictional evidence', 'opening_citations': ['D001'],
                       'findings': [{'heading': 'Fictional heading', 'text': 'Fictional finding', 'citations': ['D001'],
                                     'quotes': [{'passage_id': self.ids[0]}] if i == 0 else []} for i in range(4)],
                       'next_tests': [], 'scope': 'Fictional scope'}


class PassageTests(PassageFixture, unittest.TestCase):
    def test_all_source_characters_reconstruct_with_no_cross_speaker_spans(self):
        view = passages.input_view(self.manifest, self.catalog)
        docrows = [p for p in self.catalog['passages'] if p['document_id'] == 'fictional-filing']
        self.assertEqual(''.join(p['text'] for p in docrows), (self.root / 'filing.txt').read_bytes().decode())
        callrows = [p for p in self.catalog['passages'] if p['document_id'] == 'fictional-call']
        restored = sorted(callrows + view['unassigned_transcript_spans'], key=lambda p: p['start'])
        self.assertEqual(''.join(p['text'] for p in restored), self.text)
        turns = {t['id']: t for t in view['transcript_index']['turns']}
        for p in callrows:
            t = turns[p['scope_id']]
            self.assertTrue(t['start'] <= p['start'] < p['end'] <= t['end'])
        self.assertEqual(self.catalog, passages.catalog(self.manifest))

    def test_nbsp_and_duplicate_passages_copy_exactly_with_distinct_offsets(self):
        rows = self.catalog['passages']
        repeated = [p for p in rows if p['scope_id'] == 'D001' and p['text'].strip() == 'Repeated phrase.']
        self.assertEqual(len(repeated), 2)
        self.assertNotEqual(repeated[0]['passage_id'], repeated[1]['passage_id'])
        self.assertNotEqual(repeated[0]['start'], repeated[1]['start'])
        nbsp = next(p for p in rows if '$9.5\u00a0billion' in p['text'])
        out = copy.deepcopy(self.retrieval)
        out['quotes'] = [{'passage_id': p['passage_id']} for p in [*repeated, nbsp, rows[0]]]
        resolved = passages.hydrate('retrieval', out, self.catalog)
        for q in resolved['quotes']:
            evidence.validate_quote(self.manifest, q)
            self.assertEqual(Path(q['path']).read_bytes().decode()[q['start']:q['end']], q['text'])
        self.assertIn('\u00a0', resolved['quotes'][2]['text'])
        self.assertNotIn('text', out['quotes'][0])

    def test_aggregate_errors_paths_and_patch_preserves_other_content(self):
        out = copy.deepcopy(self.retrieval)
        out['quotes'][1] = {'passage_id': 'bad'}
        out['quotes'][3] = {'scope_id': 'D001', 'text': 'Invented quote'}
        with self.assertRaises(passages.SelectionError) as raised:
            passages.resolve_selections('retrieval', out, self.catalog)
        self.assertEqual([x['path'] for x in raised.exception.issues], ['/quotes/1', '/quotes/3'])
        fixed = passages.apply_patch('retrieval', out, {'replacements': [
            {'path': '/quotes/1', 'passage_id': self.ids[1]}, {'path': '/quotes/3', 'passage_id': self.ids[3]}]}, self.catalog)
        self.assertEqual(fixed, self.retrieval)
        self.assertEqual(out['quotes'][1]['passage_id'], 'bad')
        pipe.validate('retrieval', fixed, self.bundle, self.catalog)

    def test_repair_cannot_change_valid_selection_or_other_fields(self):
        out = copy.deepcopy(self.retrieval); out['quotes'][1] = {'passage_id': 'bad'}
        for edits in [[], [{'path': '/quotes/0', 'passage_id': self.ids[0]}],
                      [{'path': '/selected_document_ids/0', 'passage_id': self.ids[0]}],
                      [{'path': '/quotes/1', 'passage_id': self.ids[1]}] * 2]:
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                passages.apply_patch('retrieval', out, {'replacements': edits}, self.catalog)
        with self.assertRaises(ValueError):
            passages.apply_patch('retrieval', out, {'replacements': [], 'document_findings': []}, self.catalog)

    def test_duplicate_wrong_id_type_and_model_text_are_rejected(self):
        for selection in [{'passage_id': self.ids[0]}, {'passage_id': []},
                          {'passage_id': self.ids[1], 'text': 'tampered'}, {'passage_id': 'other-case-id'}]:
            out = copy.deepcopy(self.retrieval); out['quotes'][1] = selection
            with self.subTest(selection=selection), self.assertRaises(passages.SelectionError):
                pipe.validate('retrieval', out, self.bundle, self.catalog)

    def test_prompt_requests_id_only_and_preserves_full_context(self):
        text = pipe.prompt('retrieval', self.bundle, 'Fictional standard', {}, [], self.catalog)
        self.assertIn('"quotes":[{"passage_id":', text)
        self.assertNotIn('Exact distinctive short source substring', text)
        self.assertIn('unassigned_transcript_spans', text)
        deps = {'financial': self.financial, 'retrieval': self.retrieval}
        text = pipe.prompt('analysis', self.bundle, 'Fictional standard', deps, [], self.catalog)
        self.assertIn('"quotes":[{"passage_id":', text)
        self.assertNotIn('"text":"exact substring"', text)
        self.assertIn('span_sha256', text)

    def test_source_tampering_rejected(self):
        (self.root / 'filing.txt').write_text('Changed evidence')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            passages.catalog(self.manifest)


class PipelineTests(PassageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.writing = self.root / 'writing.txt'; self.writing.write_text('Fictional concise standard')
        self.output = self.root / 'run'; pipe.freeze(self.casepath, self.output, self.writing)
        self.jobs = {}; self.calls = []; self.bad_patch = False; self.bad_review = False
        for name, side in [('run_role', self.call), ('verify_job', lambda p: self.jobs[str(p)])]:
            mock = patch.object(pipe, name, side_effect=side); mock.start(); self.addCleanup(mock.stop)

    def call(self, path, prompt, model, effort, bindings, timeout):
        self.calls.append((bindings['role'], bindings['round']))
        role, number = bindings['role'], bindings['round']
        if role == 'financial':
            out = self.financial
        elif role == 'retrieval':
            if number == 0:
                out = copy.deepcopy(self.retrieval); out['quotes'][1] = {'passage_id': 'bad-id'}
            else:
                out = {'replacements': [{'path': '/quotes/1', 'passage_id': 'still-bad' if self.bad_patch else self.ids[1]}]}
        elif role == 'analysis':
            out = self.report
        else:
            out = {'verdict': 'blocked' if self.bad_review else 'pass', 'criteria': {
                c: {'status': 'pass', 'evidence': 'Fictional source check'} for c in pipe.legacy.CRITERIA}, 'findings': []}
        base.save(path / 'request.json', {'bindings': bindings, 'model': model, 'effort': effort})
        (path / 'prompt.txt').write_text(prompt)
        receipt = {'started_at': '2040-01-01T00:00:00+00:00', 'finished_at': '2040-01-01T00:00:01+00:00',
                   'session': {'id': path.name}}
        result = {'content': copy.deepcopy(out), 'receipt': receipt}
        self.jobs[str(path)] = result
        return result

    def test_full_flow_selective_patch_persistence_and_resume(self):
        result = pipe.run(self.output)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(self.calls.count(('financial', 0)), 1)
        self.assertNotIn(('financial', 1), self.calls)
        self.assertEqual([j['mode'] for j in result['jobs']], ['full', 'full', 'selection_patch', 'full', 'full'])
        raw = base.read(self.output / 'artifacts.json')
        material = base.read(self.output / 'materialized-artifacts.json')
        self.assertEqual(raw['retrieval'], self.retrieval)
        q = material['analysis']['findings'][0]['quotes'][0]
        self.assertEqual(q['text'], Path(q['path']).read_bytes().decode()[q['start']:q['end']])
        n = len(self.calls); pipe.run(self.output); self.assertEqual(n, len(self.calls))
        self.assertIn(q['text'], (self.output / 'report.txt').read_text())

    def test_two_failed_patch_rounds_stop_before_analysis(self):
        self.bad_patch = True
        result = pipe.run(self.output)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['correction_rounds'], 2)
        self.assertFalse(any(role in ('analysis', 'review') for role, _ in self.calls))
        self.assertEqual(len(result['jobs']), 4)

    def test_fresh_reviewer_can_block_exact_quotes(self):
        self.bad_review = True
        self.assertEqual(pipe.run(self.output)['status'], 'blocked')
        self.assertIn('DRAFT', (self.output / 'report.html').read_text())

    def test_changed_materialized_quote_is_rejected_even_with_resealed_digest(self):
        result = pipe.run(self.output)
        material = base.read(self.output / 'materialized-artifacts.json')
        material['retrieval']['quotes'][0]['text'] = 'Tampered'
        (self.output / 'materialized-artifacts.json').write_text(json.dumps(material))
        result['materialized_digest'] = base.digest(material)
        (self.output / 'result.json').write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'Derived artifacts differ'):
            pipe.verify(self.output)

    def test_changed_catalogue_even_resealed_is_rejected(self):
        cat = base.read(self.output / 'passages.json'); cat['passages'][0]['start'] += 1
        (self.output / 'passages.json').write_text(json.dumps(cat))
        protocol = base.read(self.output / 'protocol.json'); protocol['passages_sha256'] = base.sha(self.output / 'passages.json')
        (self.output / 'protocol.json').write_text(json.dumps(protocol))
        with self.assertRaisesRegex(ValueError, 'catalogue differs'):
            pipe.load(self.output)


if __name__ == '__main__':
    unittest.main()
