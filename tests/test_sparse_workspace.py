"""Fictitious sparse Git archive: hydration never removes or expands the archive."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from research.sparse_workspace import hydrate_batch, pattern


class SparseTests(unittest.TestCase):
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
        for value in ['../secret', '/absolute', 'a\nb', '']:
            with self.assertRaises(ValueError):
                pattern(value)
