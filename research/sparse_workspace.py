"""Hydrate exact, batch-scoped evidence from a private Git archive."""
from pathlib import PurePosixPath, PureWindowsPath
import re
import subprocess

from .contracts import require
from .library import read_json, resolve


def relative_path(value):
    require(isinstance(value, str) and value and not PurePosixPath(value).is_absolute()
            and not PureWindowsPath(value).drive
            and re.search(r'[\x00-\x1f\x7f-\x9f]', value) is None,
            'Unsafe sparse evidence path')
    return value


def evidence_path(root, value, base=''):
    """Resolve importer-relative evidence, then enforce the private-root boundary."""
    relative_path(value)  # Validate before joining: an absolute value must not be hidden.
    path = resolve(root, str(PurePosixPath(base) / value))
    return path.relative_to(root).as_posix()


def pattern(value):
    relative_path(value)
    require('..' not in PurePosixPath(value).parts and PurePosixPath(value).parts,
            'Unsafe sparse evidence path')
    return '/' + ''.join('\\' + c if c in '\\*?[]' else c for c in value)


def include(root, paths):
    paths = set(paths)
    patterns = sorted({pattern(p) for p in paths})
    if patterns:
        # A normalized directory would expand the batch to every descendant.
        # Consult the index, since sparse evidence need not exist on disk yet.
        tracked = subprocess.run(['git', '--literal-pathspecs', 'ls-files', '--stage', '-z',
                                  '--', *sorted(paths)], cwd=root, capture_output=True,
                                 text=True, check=True)
        files = set()
        for entry in tracked.stdout.split('\0'):
            if entry:
                metadata, name = entry.split('\t', 1)
                mode, _, stage = metadata.split()
                require(mode in {'100644', '100755'} and stage == '0',
                        'Sparse evidence must be a tracked regular file')
                files.add(name)
        require(files == paths, 'Sparse evidence must name exact tracked files')
        subprocess.run(['git', 'sparse-checkout', 'add', '--stdin'], cwd=root,
                       input='\n'.join(patterns) + '\n', text=True, check=True,
                       stdout=subprocess.DEVNULL)


def hydrate_batch(root, issuer_ids):
    root = root.resolve()
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
            evidence.add(evidence_path(root, row[key], base))
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
                source(read_json(resolve(root, 'collection/' + manifest)), 'collection')
    include(root, evidence)
    return len(evidence)
