"""Fictitious fixtures for coverage, Unicode provenance and output protection."""
import copy
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

import translation_artifact as artifact


class TranslationArtifactTests(unittest.TestCase):
    def setUp(self):
        self.text = '架空資料 😀\r\n売上高125億円。\r\n営業利益率12.4％。\r\n'
        self.sha = hashlib.sha256(self.text.encode('utf-8')).hexdigest()

    def translated(self, ranges=None):
        value = artifact.prepare(self.text, self.sha, 'ja', 'en', ranges=ranges)
        value['translator_version'] = 'fictitious-test-v1'
        for seg in value['segments']:
            seg['translated_text'] = 'Fictitious test rendering, not a reviewed translation.'
        return value

    def test_unicode_crlf_gzip_hash_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.txt.gz'
            path.write_bytes(gzip.compress(self.text.encode('utf-8')))
            self.assertEqual(artifact.source(path), (self.text, self.sha))
        value = self.translated()
        self.assertEqual(artifact.validate(value, self.text, self.sha)['coverage_percent'], 100)
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            artifact.validate(value, self.text, 'changed')

    def test_chunking_preserves_all_unicode_characters(self):
        value = artifact.prepare(self.text, self.sha, 'ja', 'en', max_chars=7)
        self.assertEqual(''.join(s['original_text'] for s in value['segments']), self.text)
        self.assertTrue(all(s['end'] - s['start'] <= 7 for s in value['segments']))

    def test_selected_coverage_and_workspace_mapping(self):
        value = self.translated([{'start': 9, 'end': 19}])
        receipt = artifact.validate(value, self.text, self.sha)
        self.assertEqual(receipt['translated_source_characters'], 10)
        self.assertEqual(receipt['scope'], 'selected')
        exported = artifact.export_workspace(value)
        self.assertEqual(exported['segments'][0]['english_text'], value['segments'][0]['translated_text'])
        self.assertEqual(exported['untranslated_ranges'], [{'start': 0, 'end': 9}, {'start': 19, 'end': len(self.text)}])
        value['target_language'] = 'fr'
        with self.assertRaisesRegex(ValueError, 'requires target language en'):
            artifact.export_workspace(value)

    def test_rejects_draft_and_changed_span(self):
        value = self.translated()
        value['segments'][0]['translated_text'] = ''
        with self.assertRaisesRegex(ValueError, 'draft is incomplete'):
            artifact.validate(value, self.text, self.sha)
        value = self.translated()
        value['segments'][0]['original_text'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'exact source span'):
            artifact.validate(value, self.text, self.sha)

    def test_rejects_coverage_gap_overlap_and_false_full_scope(self):
        original = self.translated([{'start': 9, 'end': 19}])
        for change in [8, 10]:
            value = copy.deepcopy(original)
            value['untranslated_ranges'][0]['end'] = change
            with self.assertRaisesRegex(ValueError, 'gap or overlap'):
                artifact.validate(value, self.text, self.sha)
        original['scope'] = 'full'
        with self.assertRaisesRegex(ValueError, 'Full scope contains untranslated'):
            artifact.validate(original, self.text, self.sha)

    def test_rejects_boolean_and_out_of_bounds_offsets(self):
        for ranges in [[{'start': False, 'end': 10}], [{'start': 0, 'end': 999}],
                       [{'start': 0, 'end': 10}, {'start': 9, 'end': 12}], []]:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                artifact.prepare(self.text, self.sha, 'ja', 'en', ranges=ranges)

    def test_output_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'output.json'
            artifact.write_new(path, {'kept': True})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                artifact.write_new(path, {'changed': True})
            self.assertEqual(path.read_bytes(), before)

    def test_artifact_hash_changes_after_translation_edit(self):
        value = self.translated()
        first = artifact.validate(value, self.text, self.sha)
        value['segments'][0]['translated_text'] += ' Corrected.'
        second = artifact.validate(value, self.text, self.sha)
        self.assertNotEqual(first['translation_sha256'], second['translation_sha256'])
        self.assertIn('separate semantic review', artifact.render(value, second))


if __name__ == '__main__':
    unittest.main()
