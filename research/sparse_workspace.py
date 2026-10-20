"""Hydrate exact, batch-scoped evidence from a private Git archive."""
from pathlib import PurePosixPath
import re
import subprocess

from .contracts import require
from .library import read_json


def pattern(value):
    require(isinstance(value, str) and value and not PurePosixPath(value).is_absolute()
            and '..' not in PurePosixPath(value).parts
            and not any(c in value for c in '\n\r\0'), 'Unsafe sparse evidence path')
    return '/' + ''.join('\\' + c if c in '\\*?[]' else c for c in value)


def include(root, paths):
    patterns = sorted({pattern(p) for p in paths})
    if patterns:
        subprocess.run(['git', 'sparse-checkout', 'add', '--stdin'], cwd=root,
                       input='\n'.join(patterns) + '\n', text=True, check=True,
                       stdout=subprocess.DEVNULL)


def hydrate_batch(root, issuer_ids):
    enabled = subprocess.run(['git', 'config', '--bool', 'core.sparseCheckout'],
                             cwd=root, capture_output=True, text=True, check=True)
    require(enabled.stdout.strip() == 'true', 'Batch hydration requires sparse checkout')
    cfg = read_json(root / 'config.json').get('earnings_pipeline', {})
    audit = cfg.get('audit', 'reports/retrieval/2026-09-20/universe/results.json')
    languages = cfg.get('languages', 'reports/retrieval/2026-09-20/universe/language-review.json')
    cat = read_json(root / 'library/catalog.json')
    baseline = read_json(root / 'published/latest.json')
    paths = {audit}
    if languages:
        paths.add(languages)
    for key in (cat['catalog_id'], baseline['catalog_id']):
        require(re.fullmatch(r'[a-f0-9]{64}', key) is not None, 'Invalid catalog snapshot ID')
        paths.add('library/snapshots/' + key + '.json')
    include(root, paths)
    evidence = set()
    def source(row, base=''):
        for key in ('raw_path', 'text_path'):
            evidence.add(base + row[key])
    for doc in cat['documents'].values():
        if doc['issuer_id'] in issuer_ids:
            for row in doc['sources']:
                source(row)
    for company in read_json(root / audit)['results']:
        if company['issuer_id'] in issuer_ids:
            for row in company['documents']:
                source(row)
    # Newly imported manifests may not yet be represented in the prior catalog.
    aliases = {row['collector_issuer_id'] for row in read_json(root / 'pipeline/source-coverage.json')['companies']
               if row['issuer_id'] in issuer_ids and row.get('collector_issuer_id')}
    index = root / 'collection/document-index.json'
    if index.exists():
        for row in read_json(index).values():
            if row['issuer_id'] in aliases or row['issuer_id'] in issuer_ids:
                manifest = row['manifest_path']
                pattern(manifest)
                source(read_json(root / 'collection' / manifest), 'collection/')
    include(root, evidence)
    return len(evidence)
