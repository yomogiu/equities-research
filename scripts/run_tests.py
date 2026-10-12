"""Run explicit offline suites; ordinary unittest discovery remains supported."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('active_pipeline', 'legacy_compatibility', 'other_workflows')


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


def manifest(root=ROOT):
    groups = json.loads((root/'tests/suites.json').read_text())
    if set(groups) != set(GROUPS):
        raise ValueError('Expected active, legacy and other-workflow suites')
    names = [name for group in groups.values() for name in group]
    available = {p.stem for p in (root/'tests').glob('test_*.py')}
    duplicate = sorted(name for name, count in Counter(names).items() if count != 1)
    if duplicate or set(names) != available:
        raise ValueError(f'Suite manifest mismatch: duplicates={duplicate}, '
                         f'unclassified={sorted(available-set(names))}, stale={sorted(set(names)-available)}')
    return groups


def load(groups, selected, root=ROOT):
    # Match unittest's canonical module names even when launched elsewhere.
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root/'tests'))
    loader = unittest.TestLoader()
    modules = sorted(name for group in selected for name in groups[group])
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in modules)
    if loader.errors:
        raise ValueError('\n'.join(loader.errors))
    ids = [test.id() for test in cases(suite)]
    repeated = sorted(name for name, count in Counter(ids).items() if count != 1)
    if repeated:
        raise ValueError('Duplicate test discovery: ' + ', '.join(repeated))
    return suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=('all', *GROUPS), nargs='?', default='active_pipeline')
    parser.add_argument('--list', action='store_true', help='Audit groups and counts without running tests')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    groups = manifest()
    selected = GROUPS if args.suite == 'all' else (args.suite,)
    suite = load(groups, selected)
    if args.list:
        counts = {group: load(groups, (group,)).countTestCases() for group in selected}
        print(json.dumps({'groups':counts, 'total':suite.countTestCases(), 'duplicate_test_ids':0}, sort_keys=True))
        return 0
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
