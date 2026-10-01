"""Opt-in v2 of the mixed-model experiment: ID-only quotes and bounded slot repairs.

Uses the original role/model settings. Frozen v1 code and runs are unchanged.
Research artifacts must remain private. No production/schedule changes.
"""
from __future__ import annotations
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from research import earnings_experiment as base
from research import earnings_compact_evidence as evidence
from research import earnings_mixed_pipeline as legacy
from research import earnings_passages as passages
from research.earnings_mixed_runner import run_role, verify_job

VERSION = 'luna-sol-passages-v2'
MODELS = legacy.MODELS
QUOTE_RULE = ('Quotations are selected ONLY as {"passage_id":"exact catalogue ID"}. '
              'Never return quotation text, offsets or scope IDs in a quote selection. '
              'Code copies the original text, source hash and Unicode offsets. '
              'Read surrounding passages and speakers; exact copying does not establish analytical relevance. '
              'Citation strings in JSON contain IDs only; the renderer adds brackets to displayed citations.')


def validate(role, out, bundle, catalog):
    hydrated = passages.hydrate(role, out, catalog)
    legacy.validate_output(role, hydrated, bundle)
    return hydrated


def prompt(role, bundle, writing, deps, feedback, catalog, prior=None, issues=None):
    if issues is not None:
        return (legacy.COMMON + '\n\nPASSAGE SELECTION REPAIR\n' + QUOTE_RULE +
                '\nReplace each listed invalid selection exactly once. Return ONLY '
                '{"replacements":[{"path":"exact failing JSON path","passage_id":"exact catalogue ID"}]}. '
                'No other field can be edited. Preserve the intended evidence topic using the current selections '
                'and surrounding source context. Do not repeat the coverage analysis or report.\n' +
                legacy.packed({'issues': issues, 'current_selections': passages.quote_slots(role, prior),
                               'original_selection_context': prior,
                               'source_catalogue': passages.input_view(bundle['manifest'], catalog)}))
    hydrated = {r: passages.hydrate(r, v, catalog) for r, v in deps.items()}
    if role == 'retrieval':
        # Keep the original evidence assignment but replace its quote schema and text supply.
        old = legacy.prompt_for(role, bundle, writing, deps, feedback)
        head = old.split('\n\nFROZEN EVIDENCE / ARTIFACTS\n', 1)[0]
        head = head.replace('"quotes":[{"scope_id":"EXACT TURN/EXCHANGE OR D ID","text":"Exact distinctive short source substring"}]',
                            '"quotes":[{"passage_id":"EXACT CATALOGUE ID"}]')
        head = head.replace('Do not include start offsets unless needed for repeated text.', QUOTE_RULE)
        case = base.read(bundle['manifest']['case_path'])
        return head + '\n\nFROZEN EVIDENCE / ARTIFACTS\n' + legacy.packed({
            'case_id': case['case_id'], 'scope_notes': case['scope_notes'],
            'source_catalogue': passages.input_view(bundle['manifest'], catalog)})
    text = legacy.prompt_for(role, bundle, writing, hydrated, feedback)
    if role == 'analysis':
        text = text.replace('"quotes":[{"scope_id":"EXACT SOURCE ID","text":"exact substring"}]',
                            '"quotes":[{"passage_id":"EXACT SELECTED PASSAGE ID"}]')
        text += '\n\nQUOTE SELECTION CONTRACT\n' + QUOTE_RULE + (
            ' Use passage IDs from the supplied retrieval quotes. Empty quotes arrays are allowed. '
            'Narrative paraphrases use ordinary citations and must not be presented as quotations.')
    if role == 'review':
        text += '\n\nRENDERING CONTRACT\nCode materializes selected quotations and inserts displayed citation brackets. '
        text += 'Judge quote relevance and context against original sources; do not charge renderer-added brackets as an author-formatting defect.'
    return text


def freeze(case_path, output, writing_path):
    root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=True)
    manifest = evidence.prepare(case_path, root / 'evidence')
    base.save(root / 'passages.json', passages.catalog(manifest))
    names = ('earnings_passage_pipeline.py', 'earnings_passages.py', 'earnings_mixed_pipeline.py',
             'earnings_compact_evidence.py', 'earnings_experiment.py', 'earnings_mixed_runner.py',
             'earnings_mixed_prime.mjs')
    protocol = {'version': VERSION, 'case_path': str(Path(case_path).resolve()),
                'case_sha256': base.sha(case_path), 'evidence_manifest': str(root / 'evidence/manifest.json'),
                'evidence_sha256': base.sha(root / 'evidence/manifest.json'),
                'passages_sha256': base.sha(root / 'passages.json'),
                'writing_standard': str(Path(writing_path).resolve()), 'writing_sha256': base.sha(writing_path),
                'models': {k: list(v) for k, v in MODELS.items()}, 'max_correction_rounds': 2,
                'code': [{'path': str(Path(__file__).parent / n), 'sha256': base.sha(Path(__file__).parent / n)} for n in names]}
    base.save(root / 'protocol.json', protocol)
    return protocol


def load(root):
    p = base.read(root / 'protocol.json')
    if p['version'] != VERSION or p['models'] != {k: list(v) for k, v in MODELS.items()} or p['max_correction_rounds'] != 2:
        raise ValueError('Protocol/settings differ')
    for path, digest in [(p['case_path'], p['case_sha256']), (p['evidence_manifest'], p['evidence_sha256']),
                         (p['writing_standard'], p['writing_sha256']), (root / 'passages.json', p['passages_sha256']),
                         *((c['path'], c['sha256']) for c in p['code'])]:
        if base.sha(path) != digest:
            raise ValueError('Frozen input/code changed: ' + str(path))
    bundle = evidence.load_bundle(p['evidence_manifest'])
    catalog = passages.catalog(p['evidence_manifest'])
    if catalog != base.read(root / 'passages.json'):
        raise ValueError('Passage catalogue differs from original evidence')
    return p, bundle, catalog


def findings(role, exc):
    if isinstance(exc, passages.SelectionError):
        return [{'target': role, 'passage': x['path'], 'reason': x['reason'],
                 'required_change': x['required_change'], 'selection': x['selection']} for x in exc.issues]
    return [{'target': role, 'passage': 'Role schema/evidence validation', 'reason': str(exc),
             'required_change': 'Repair the stated schema or evidence defect and return full role JSON.'}]


def run(output):
    root = Path(output).resolve(); p, bundle, catalog = load(root)
    if (root / 'result.json').exists():
        return verify(root)
    writing = Path(p['writing_standard']).read_text()
    deps, prior, selection_issues, feedback, jobs, failures = {}, {}, {}, [], [], []
    need = {'financial', 'retrieval'}; review = None

    def call(role, round_number, snapshot):
        repair = role in selection_issues
        inputs = {'dependencies': copy.deepcopy(snapshot),
                  'feedback': [f for f in feedback if f['target'] == role],
                  'prior': prior.get(role) if repair else None,
                  'issues': selection_issues.get(role)}
        job = root / 'jobs' / f'{role}-r{round_number}'
        job.mkdir(parents=True, exist_ok=True)
        base.save(job / 'inputs.json', inputs)
        text = prompt(role, bundle, writing, inputs['dependencies'], inputs['feedback'], catalog,
                      inputs['prior'], inputs['issues'])
        result = run_role(job, text, *MODELS[role], {'protocol_sha256': base.sha(root / 'protocol.json'),
                          'role': role, 'round': round_number, 'inputs_sha256': base.sha(job / 'inputs.json')}, timeout=1200)
        record = {'role': role, 'round': round_number, 'mode': 'selection_patch' if repair else 'full',
                  'path': str(job), 'receipt': result['receipt']}
        return result['content'], record, inputs

    def receive(role, result, errors):
        raw, record, inputs = result; jobs.append(record)
        try:
            out = (passages.apply_patch(role, inputs['prior'], raw, catalog)
                   if inputs['issues'] is not None else raw)
            prior[role] = out
            selection_issues.pop(role, None)
            validate(role, out, bundle, catalog)
            selection_issues.pop(role, None)
            if role == 'review':
                return out
            deps[role] = out
        except (ValueError, KeyError, TypeError) as exc:
            errors.extend(findings(role, exc))
            if isinstance(exc, passages.SelectionError):
                selection_issues[role] = exc.issues
            # A malformed patch still gets a bounded patch retry on the same failed slots.
            elif inputs['issues'] is None:
                selection_issues.pop(role, None)
        return None

    for round_number in range(3):
        errors = []
        snapshot = copy.deepcopy(deps)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = {r: pool.submit(call, r, round_number, snapshot) for r in sorted(need & {'financial', 'retrieval'})}
            for role, future in pending.items():
                receive(role, future.result(), errors)
        if not errors:
            receive('analysis', call('analysis', round_number, deps), errors)
        if not errors:
            review = receive('review', call('review', round_number, deps), errors)
            if review is not None:
                if review['verdict'] in ('pass', 'blocked'):
                    break
                errors = review['findings']
        failures.append({'round': round_number, 'findings': errors})
        feedback = errors
        need = {f['target'] for f in errors}
    accepted = bool(review and review['verdict'] == 'pass')
    materialized = {r: passages.hydrate(r, v, catalog) for r, v in deps.items()}
    base.save(root / 'artifacts.json', deps)
    base.save(root / 'materialized-artifacts.json', materialized)
    base.save(root / 'review.json', review)
    result = {'version': VERSION, 'status': 'accepted' if accepted else 'blocked',
              'correction_rounds': round_number, 'jobs': jobs, 'failures': failures,
              'protocol_sha256': base.sha(root / 'protocol.json'),
              'artifact_digest': base.digest(deps), 'materialized_digest': base.digest(materialized),
              'review_sha256': base.sha(root / 'review.json'),
              'wall_seconds': (max(datetime.fromisoformat(j['receipt']['finished_at']) for j in jobs) -
                               min(datetime.fromisoformat(j['receipt']['started_at']) for j in jobs)).total_seconds()}
    if 'analysis' in materialized:
        legacy.immutable_text(root / 'report.txt', legacy.report_text(materialized['analysis'], materialized['financial'], bundle))
        legacy.render(root, materialized['analysis'], materialized['financial'], bundle,
                      'Independent substantive and writing review passed' if accepted else 'DRAFT — unresolved findings')
        result.update(report_sha256=base.sha(root / 'report.txt'), html_sha256=base.sha(root / 'report.html'))
    base.save(root / 'result.json', result)
    return verify(root)


def verify(output):
    """Replay authenticated full/patch outputs; independently recopy every source quote."""
    root = Path(output).resolve(); p, bundle, catalog = load(root)
    result = base.read(root / 'result.json'); writing = Path(p['writing_standard']).read_text()
    deps, prior, expected_issues, identities, keys = {}, {}, {}, set(), set()
    review = None; review_deps = None; round_snapshots = {}
    for job in result['jobs']:
        role, number = job['role'], job['round']
        key = (role, number)
        if key in keys or role not in MODELS or type(number) is not int or not 0 <= number <= 2:
            raise ValueError('Duplicate/invalid job')
        keys.add(key)
        path = root / 'jobs' / f'{role}-r{number}'
        if Path(job['path']).resolve() != path:
            raise ValueError('Unexpected job path')
        inputs = base.read(path / 'inputs.json'); request = base.read(path / 'request.json'); value = verify_job(path)
        if value['receipt'] != job['receipt'] or (request['model'], request['effort']) != MODELS[role]:
            raise ValueError('Receipt/model mismatch')
        sid = value['receipt']['session']['id']
        if sid in identities:
            raise ValueError('Fresh independent sessions required')
        identities.add(sid)
        if request['bindings'] != {'protocol_sha256': base.sha(root / 'protocol.json'), 'role': role,
                                   'round': number, 'inputs_sha256': base.sha(path / 'inputs.json')}:
            raise ValueError('Job input binding mismatch')
        round_snapshots.setdefault(number, copy.deepcopy(deps))
        expected_deps = round_snapshots[number] if role in ('financial', 'retrieval') else deps
        if inputs['dependencies'] != expected_deps:
            raise ValueError('Dependency chain mismatch')
        if inputs['issues'] != expected_issues.get(role) or inputs['prior'] != (prior.get(role) if role in expected_issues else None):
            raise ValueError('Repair differs from actual failed selections')
        mode = 'selection_patch' if inputs['issues'] is not None else 'full'
        if job['mode'] != mode:
            raise ValueError('Job mode mismatch')
        text = prompt(role, bundle, writing, inputs['dependencies'], inputs['feedback'], catalog, inputs['prior'], inputs['issues'])
        if (path / 'prompt.txt').read_text() != text:
            raise ValueError('Prompt differs from original evidence and handoff')
        try:
            out = passages.apply_patch(role, inputs['prior'], value['content'], catalog) if mode == 'selection_patch' else value['content']
            prior[role] = out
            expected_issues.pop(role, None)
            validate(role, out, bundle, catalog)
            expected_issues.pop(role, None)
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, passages.SelectionError):
                expected_issues[role] = exc.issues
            elif mode == 'full':
                expected_issues.pop(role, None)
            continue
        if role == 'review':
            review, review_deps = out, copy.deepcopy(deps)
        else:
            deps[role] = out
    if not {('financial', 0), ('retrieval', 0)} <= keys:
        raise ValueError('Initial preparers missing')
    if result['version'] != VERSION or result['status'] not in ('accepted', 'blocked') or result['correction_rounds'] != max(n for _, n in keys):
        raise ValueError('Invalid result status or correction count')
    materialized = {r: passages.hydrate(r, v, catalog) for r, v in deps.items()}
    if (result['protocol_sha256'] != base.sha(root / 'protocol.json') or deps != base.read(root / 'artifacts.json') or
        result['artifact_digest'] != base.digest(deps) or materialized != base.read(root / 'materialized-artifacts.json') or
        result['materialized_digest'] != base.digest(materialized)):
        raise ValueError('Derived artifacts differ from authenticated selections or original sources')
    if base.read(root / 'review.json') != review or result['review_sha256'] != base.sha(root / 'review.json'):
        raise ValueError('Review differs')
    if result['status'] == 'accepted' and (not review or review['verdict'] != 'pass' or review_deps != deps or expected_issues):
        raise ValueError('Acceptance lacks passing review of exact final artifacts')
    if 'analysis' in deps:
        if (base.sha(root / 'report.txt') != result['report_sha256'] or base.sha(root / 'report.html') != result['html_sha256'] or
            (root / 'report.txt').read_text() != legacy.report_text(materialized['analysis'], materialized['financial'], bundle)):
            raise ValueError('Report differs from materialized sources')
    measured = (max(datetime.fromisoformat(j['receipt']['finished_at']) for j in result['jobs']) -
                min(datetime.fromisoformat(j['receipt']['started_at']) for j in result['jobs'])).total_seconds()
    if result['wall_seconds'] != measured:
        raise ValueError('Timing differs from authenticated receipts')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze'); f.add_argument('case'); f.add_argument('output'); f.add_argument('writing')
    for name in ('run', 'verify'):
        sub.add_parser(name).add_argument('output')
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.case, args.output, args.writing); print('Frozen passage-selection protocol')
    else:
        result = (run if args.command == 'run' else verify)(args.output)
        print(legacy.packed({k: result[k] for k in ('status', 'correction_rounds', 'wall_seconds')}))


if __name__ == '__main__':
    main()
