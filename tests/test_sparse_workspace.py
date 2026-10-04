"""Fictitious sparse Git archive: hydration never removes or expands the archive."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from research.sparse_workspace import evidence_path, hydrate_batch, pattern


class SparseTests(unittest.TestCase):
    def archive(self, root, references=None):
        """All issuers and source bytes in this fixture are fictitious."""
        key = 'a' * 64
        references = references or {}
        files = {
            'config.json': {'earnings_pipeline': {'audit': 'reports/audit.json', 'languages': None}},
            'library/catalog.json': {'catalog_id': key, 'documents': references.get('catalog', {})},
            'published/latest.json': {'catalog_id': key},
            'library/snapshots/' + key + '.json': {},
            'reports/audit.json': {'results': references.get('audit', [])},
            'pipeline/source-coverage.json': {'companies': [
                {'issuer_id': 'issuer:a', 'collector_issuer_id': 'collector:a'}]},
            'collection/document-index.json': references.get('index', {}),
            **references.get('manifests', {})}
        self.git(root, 'init')
        for name, obj in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(obj))
        for name in ['sources/transcript-retrieval/fictitious/a.txt',
                     'sources/transcript-retrieval/fictitious/a.raw',
                     'sources/transcript-retrieval/fictitious/b.txt',
                     'collection/objects/normal.txt']:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fictitious source bytes')
        self.git(root, 'add', '.')
        self.git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-m', 'fictitious sparse archive')
        self.git(root, 'sparse-checkout', 'set', '--no-cone', '/*', '!/sources/',
                 '!/collection/objects/', '!/reports/', '!/library/snapshots/')

    def git(self, root, *args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                              text=True, check=True)

    def test_imported_manifest_paths_normalize_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = '../sources/transcript-retrieval/fictitious/'
            self.archive(root, {
                'index': {'a': {'issuer_id': 'collector:a', 'manifest_path': 'documents/a.json'},
                          'b': {'issuer_id': 'issuer:b', 'manifest_path': 'documents/b.json'},
                          'normal': {'issuer_id': 'issuer:a', 'manifest_path': 'documents/normal.json'}},
                'manifests': {
                    'collection/documents/a.json': {'raw_path': relative + 'a.raw', 'text_path': relative + 'a.txt'},
                    'collection/documents/b.json': {'raw_path': relative + 'b.txt', 'text_path': relative + 'b.txt'},
                    'collection/documents/normal.json': {'raw_path': 'objects/normal.txt', 'text_path': 'objects/normal.txt'}},
                'catalog': {'a': {'issuer_id': 'issuer:a', 'sources': [
                    {'raw_path': 'sources/transcript-retrieval/fictitious/a.raw',
                     'text_path': 'collection/' + relative + 'a.txt'}]}},
                'audit': [{'issuer_id': 'issuer:a', 'documents': [
                    {'raw_path': 'collection/' + relative + 'a.raw',
                     'text_path': 'sources/transcript-retrieval/fictitious/a.txt'}]}]})
            self.assertFalse((root / 'sources/transcript-retrieval/fictitious/a.txt').exists())
            self.assertEqual(hydrate_batch(root, {'issuer:a'}), 3)
            self.assertEqual(hydrate_batch(root, {'issuer:a'}), 3)
            for name in ['a.txt', 'a.raw']:
                self.assertEqual((root / 'sources/transcript-retrieval/fictitious' / name).read_text(),
                                 'fictitious source bytes')
            self.assertTrue((root / 'collection/objects/normal.txt').exists())
            self.assertFalse((root / 'sources/transcript-retrieval/fictitious/b.txt').exists())
            patterns = (root / '.git/info/sparse-checkout').read_text()
            self.assertNotIn('..', patterns)
            self.assertIn('/sources/transcript-retrieval/fictitious/a.txt', patterns)
            self.assertEqual(self.git(root, 'status', '--porcelain').stdout, '')

    def test_manifest_escape_rejected_before_evidence_hydration(self):
        for value in ['../../outside.txt', '/absolute.txt', 'C:/absolute.txt',
                      '../sources/a\n/sources/', '../sources/a\x00b', '', None,
                      '../sources/', '../sources/transcript-retrieval/fictitious/..',
                      '../sources/missing.txt']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.archive(root, {
                    'index': {'a': {'issuer_id': 'issuer:a', 'manifest_path': 'documents/a.json'}},
                    'manifests': {'collection/documents/a.json':
                                  {'raw_path': value, 'text_path': 'objects/normal.txt'}}})
                with self.assertRaises(ValueError):
                    hydrate_batch(root, {'issuer:a'})
                self.assertFalse((root / 'collection/objects/normal.txt').exists())
                self.assertFalse((root / 'sources/transcript-retrieval/fictitious/a.txt').exists())

    def test_evidence_path_contains_resolved_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'
            root.mkdir()
            self.assertEqual(evidence_path(root, '../sources/a.txt', 'collection'), 'sources/a.txt')
            self.assertEqual(evidence_path(root, 'collection/../sources/a.txt'), 'sources/a.txt')
            self.assertEqual(evidence_path(root, './sources/a.txt'), 'sources/a.txt')
            for value, base in [('../outside.txt', ''), ('../../outside.txt', 'collection'),
                                ('..', 'collection'), ('.', ''), ('/absolute.txt', 'collection'),
                                (str(root / 'inside.txt'), ''), ('C:\\outside.txt', 'collection'),
                                ('\\\\server\\share\\a', ''), ('C:relative.txt', ''),
                                (None, ''), (42, ''), ('', '')]:
                with self.subTest(value=value, base=base), self.assertRaises(ValueError):
                    evidence_path(root, value, base)
            for char in [chr(i) for i in range(32)] + ['\x7f', '\x85', '\x9f']:
                with self.subTest(control=ord(char)), self.assertRaises(ValueError):
                    evidence_path(root, 'sources/a' + char + 'b', 'collection')
            (root / 'outside-link').symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'escapes private storage'):
                evidence_path(root, '../outside-link/secret.txt', 'collection')

    def test_glob_metacharacters_stay_literal(self):
        self.assertEqual(pattern('sources/a*[1]?.txt'), '/sources/a\\*\\[1\\]\\?.txt')

    def test_sparse_symlink_rejected_before_hydration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root, {
                'index': {'a': {'issuer_id': 'issuer:a', 'manifest_path': 'documents/a.json'}},
                'manifests': {'collection/documents/a.json':
                              {'raw_path': '../sources/link', 'text_path': 'objects/normal.txt'}}})
            self.git(root, 'sparse-checkout', 'disable')
            (root / 'sources/link').symlink_to('/outside/secret.txt')
            self.git(root, 'add', 'sources/link')
            self.git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                     'commit', '-m', 'fictitious unsafe symlink')
            self.git(root, 'sparse-checkout', 'set', '--no-cone', '/*', '!/sources/',
                     '!/collection/objects/', '!/reports/', '!/library/snapshots/')
            self.assertFalse((root / 'sources/link').is_symlink())
            with self.assertRaisesRegex(ValueError, 'tracked regular file'):
                hydrate_batch(root, {'issuer:a'})
            self.assertFalse((root / 'sources/link').is_symlink())
            self.assertFalse((root / 'collection/objects/normal.txt').exists())

    def test_only_selected_evidence_and_required_metadata_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(['git', '-C', tmp, *args], capture_output=True, text=True, check=True)
            key = 'a' * 64
            files = {
                'config.json': {'earnings_pipeline': {'audit': 'reports/audit.json', 'languages': None}},
                'library/catalog.json': {'catalog_id': key, 'documents': {
                    'a': {'issuer_id': 'issuer:a', 'sources': [{'raw_path': 'collection/objects/a.bin', 'text_path': 'collection/objects/a.txt'}]},
                    'b': {'issuer_id': 'issuer:b', 'sources': [{'raw_path': 'collection/objects/b.bin', 'text_path': 'collection/objects/b.txt'}]}}},
                'published/latest.json': {'catalog_id': key},
                'library/snapshots/' + key + '.json': {},
                'reports/audit.json': {'results': []},
                'pipeline/source-coverage.json': {'companies': []}}
            git('init')
            for name, obj in files.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(obj))
            for name in ['a.bin', 'a.txt', 'b.bin', 'b.txt']:
                p = root / 'collection/objects' / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('fictitious bytes')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
            git('sparse-checkout', 'set', '--no-cone', '/*', '!/collection/objects/', '!/reports/', '!/library/snapshots/')
            self.assertEqual(hydrate_batch(root, {'issuer:a'}), 2)
            self.assertTrue((root / 'collection/objects/a.bin').exists())
            self.assertFalse((root / 'collection/objects/b.bin').exists())
            (root / 'collection/objects/new.bin').write_text('new fictitious source')
            git('add', '--sparse', '--', 'collection')
            self.assertEqual(git('diff', '--cached', '--name-status').stdout.strip(), 'A\tcollection/objects/new.bin')
            self.assertIn('fictitious bytes', git('show', 'HEAD:collection/objects/b.bin').stdout)

    def test_unsafe_paths_rejected(self):
        for value in ['../secret', 'collection/../sources/a.txt', '/absolute', 'a\nb',
                      'a\tb', 'a\x7fb', 'a\x85b', 'C:/absolute', 'C:relative', '.', '', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                pattern(value)
