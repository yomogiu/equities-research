"""Fictional native-source replay and narrow grounding derivations; no workers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_earnings_compact_evidence import fixture as case_fixture
from test_reviewed_transcript_index import fixture as sidecar_fixture, encoded, rebind, apply
from research import earnings_retrieval_identity_grounding as helper
from research import earnings_compact_evidence as evidence, earnings_passages as passages
from research import earnings_qa_grounding as qa, earnings_mixed_runner as b


class IdentityGroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self, function='live_analyst_transition', review_function='pass'):
        casepath, case, _ = case_fixture(self.root)
        values = sidecar_fixture(); text, raw, source, proposal, review, selection = values
        source['catalog_id'] = 'fictional-catalog'
        host = next(x for x in proposal['evidence'] if x['id'] == 'e1')
        proposal['dialogue_function_proposals'] = [{
            'source_speaker': 'Pat Host', 'start': host['start'], 'end': host['end'],
            'dialogue_function': function, 'evidence_id': 'e1'}]
        review['decisions'][0]['dialogue_function_decision'] = review_function
        selection['proposal_path'] = 'reviewed/proposal.json'; selection['review_path'] = 'reviewed/review.json'
        rebind(values)
        index = apply(values)
        rawpath = self.root/'reviewed-call.html'; rawpath.write_bytes(raw)
        textpath = self.root/'reviewed-call.txt'; textpath.write_bytes(text.encode())
        indexpath = self.root/'reviewed-index.json'; b.save(indexpath, index)
        selected = self.root/'reviewed/selection.json'; selected.parent.mkdir()
        pp = self.root/selection['proposal_path']; pp.write_bytes(encoded(proposal))
        rp = self.root/selection['review_path']; rp.write_bytes(encoded(review)); b.save(selected, selection)
        case['sources'] = [s for s in case['sources'] if s['kind'] != 'transcript'] + [
            {'document_id': source['document_id'], 'kind': 'transcript', 'representation': kind,
             'path': str(path), 'sha256': b.sha(path)} for kind, path in [('raw', rawpath), ('text', textpath)]]
        old_index = case['transcript_index_path']
        case['artifacts'] = [a for a in case['artifacts'] if a['path'] != old_index] + [
            {'path': str(path), 'sha256': b.sha(path)} for path in (indexpath, selected, pp, rp)]
        case.update(transcript_index_path=str(indexpath), transcript_path=str(textpath),
                    transcript_sidecar=index['reviewed_sidecar'], transcript_sidecar_selection_path=str(selected))
        casepath.write_text(json.dumps(case))
        previous = self.root/'pipeline'
        manifest = evidence.prepare(casepath, previous/'evidence')
        bundle = evidence.load_bundle(manifest); catalog = passages.catalog(manifest)
        grounding = qa.build(bundle, catalog, version=qa.NAMED_GREETING_VERSION)
        b.save(previous/'passages.json', catalog); b.save(previous/'qa-grounding.json', grounding)
        protocol = {'case_path': str(casepath), 'case_sha256': b.sha(casepath),
                    'evidence_manifest': str(previous/'evidence/manifest.json'), 'evidence_sha256': b.sha(previous/'evidence/manifest.json'),
                    'passages_sha256': b.sha(previous/'passages.json'), 'qa_grounding_sha256': b.sha(previous/'qa-grounding.json'),
                    'code': [{'path': module.__file__, 'sha256': b.sha(module.__file__)}
                             for module in (helper.reviewed, helper.transcript, qa)]}
        b.save(previous/'protocol.json', protocol)
        content = {'selected_document_ids': ['D001'], 'document_findings': [],
                   'quotes': [{'passage_id': p['passage_id']} for p in catalog['passages'][:4]], 'exchange_coverage': []}
        for group in grounding['exchanges']:
            content['exchange_coverage'].append({'exchange_id': group['exchange_id'], 'question': 'Fictional question',
                'answer': 'Fictional answer', 'consequence': 'Fictional consequence',
                'question_passage_ids': [pid for t in group['turns'] if t['id'] in group['question_turn_ids'] for pid in t['passage_ids']],
                'answer_passage_ids': [pid for t in group['turns'] if t['id'] in group['answer_turn_ids'] for pid in t['passage_ids']],
                'continuation_exchange_ids': [], 'grounding_status': 'bound', 'grounding_notes': 'Fictional exact source support.'})
        return previous, content, catalog

    def test_native_replay_preserves_sources_and_all_content(self):
        previous, content, catalog = self.fixture()
        original = copy.deepcopy(content)
        before = {str(p): b.sha(p) for p in self.root.rglob('*') if p.is_file()}
        result = helper.derive(previous, content, catalog)
        self.assertEqual(result['content'], original); self.assertEqual(content, original)
        self.assertEqual(result['derivation']['full_qa_validation'], 'passed')
        changed = result['derivation']['pre_question_dispositions']; self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]['dialogue_function'], 'live_analyst_transition')
        self.assertEqual(result['derivation']['pruned_links'], [])
        self.assertEqual(before, {str(p): b.sha(p) for p in self.root.rglob('*') if p.is_file()})
        original_qa = b.read(previous/'qa-grounding.json')
        self.assertEqual(original_qa['unassigned_qa_turns'][0]['mechanical_disposition'], 'unresolved')
        self.assertEqual(result['grounding']['unassigned_qa_turns'][0]['passage_ids'],
                         original_qa['unassigned_qa_turns'][0]['passage_ids'])

    def test_unreviewed_function_or_unresolved_business_turn_cannot_pass(self):
        previous, content, catalog = self.fixture(function='issuer_response_candidate')
        with self.assertRaisesRegex(ValueError, 'Substantive unassigned'):
            helper.derive(previous, content, catalog)

    def test_missing_explicit_dialogue_approval_fails_even_when_native_accepts(self):
        previous, content, catalog = self.fixture(review_function='not_proposed')
        with self.assertRaisesRegex(ValueError, 'Explicit reviewed dialogue'):
            helper.derive(previous, content, catalog)

    def test_forged_copied_index_cannot_replace_native_replay(self):
        previous, content, catalog = self.fixture()
        native = helper.reviewed.apply_reviewed_sidecar
        def different(*args, **kwargs):
            value = native(*args, **kwargs); value['uncertainty'].append('Fictional mismatch'); return value
        with patch.object(helper.reviewed, 'apply_reviewed_sidecar', side_effect=different):
            with self.assertRaisesRegex(ValueError, 'entire original index'):
                helper.derive(previous, content, catalog)

    def test_source_bytes_grounding_catalog_and_policy_changes_fail_closed(self):
        previous, content, catalog = self.fixture()
        modified = copy.deepcopy(catalog); modified['passages'][0]['text'] = 'Fictional changed passage'
        with self.assertRaisesRegex(ValueError, 'catalogue'):
            helper.derive(previous, content, modified)
        path = previous/'qa-grounding.json'; saved = path.read_bytes(); path.write_bytes(saved+b' ')
        with self.assertRaisesRegex(ValueError, 'grounding changed'):
            helper.derive(previous, content, catalog)
        path.write_bytes(saved)
        protocol = b.read(previous/'protocol.json'); protocol['code'][0]['sha256'] = '0'*64; (previous/'protocol.json').write_text(json.dumps(protocol))
        with self.assertRaisesRegex(ValueError, 'source policy'):
            helper.derive(previous, content, catalog)

    def test_frozen_artifact_references_cannot_escape_or_match_ambiguously(self):
        previous, _, _ = self.fixture(); case = b.read(b.read(previous/'protocol.json')['case_path'])
        with self.assertRaisesRegex(ValueError, 'Canonical'):
            helper.frozen_artifact(case, '../reviewed/proposal.json')
        case['artifacts'].append(copy.deepcopy(case['artifacts'][-1]))
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            helper.frozen_artifact(case, 'reviewed/review.json')


if __name__ == '__main__': unittest.main()
