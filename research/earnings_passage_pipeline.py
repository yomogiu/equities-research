"""Opt-in v3 of the mixed-model experiment: ID-only quotes and bounded slot repairs.

Retrieval uses GPT-6 Luna Max; other role settings are unchanged. Frozen v1 code and runs are unchanged.
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
from research import earnings_qa_grounding as grounding
from research.earnings_mixed_runner import run_role, verify_job

VERSION = 'luna6-sol-presentation-v4'
EFFICIENT_VERSION = 'luna6-sol-efficient-v5'
EFFICIENT_POLICY = {'version': 'role-evidence-reuse-v1', 'max_evidence_expansions': 1}
MODELS = legacy.MODELS
QUOTE_RULE = ('Quotations are selected ONLY as {"passage_id":"exact catalogue ID"}. '
              'Never return quotation text, offsets or scope IDs in a quote selection. '
              'Code copies the original text, source hash and Unicode offsets. '
              'Read surrounding passages and speakers; exact copying does not establish analytical relevance. '
              'Citation strings in JSON contain IDs only; the renderer adds brackets to displayed citations.')


def validate(role, out, bundle, catalog):
    hydrated = passages.hydrate(role, out, catalog)
    legacy.validate_output(role, hydrated, bundle)
    if role == 'retrieval':
        grounding.require_analysis_ready(out, bundle, catalog)
    return hydrated


def prompt(role, bundle, writing, deps, feedback, catalog, prior=None, issues=None, efficient=False, extra_scope_ids=()):
    if role in ('analysis', 'review') and 'retrieval' in deps:
        grounding.require_analysis_ready(deps['retrieval'], bundle, catalog)
    grounding_prompt = grounding.prompt_contract(role, bundle)
    if efficient and issues is None:
        from research import earnings_efficient_evidence as reuse
        return reuse.prompt(role, bundle, writing, deps, feedback, catalog, extra_scope_ids) + grounding_prompt
    if issues is not None:
        view = passages.repair_view(role, prior, issues, catalog)
        if view['unresolved_paths']:
            raise ValueError('Passage repair requires explicit source selection: ' + ', '.join(view['unresolved_paths']))
        if role == 'analysis':
            view['finding_context'] = {x['path']: {
                k: v for k, v in prior['findings'][int(x['path'].split('/')[2])].items() if k != 'quotes'
            } for x in issues}
        scopes = {p['scope_id'] for r in view['repairs'] for p in r['candidates_and_adjacent_context']}
        view['speaker_context'] = [t for t in bundle['transcript_index']['turns'] if t['id'] in scopes]
        return (legacy.COMMON + '\n\nPASSAGE SELECTION REPAIR\n' + QUOTE_RULE +
                '\nReplace each listed invalid selection exactly once. Return ONLY '
                '{"replacements":[{"path":"exact failing JSON path","passage_id":"supplied candidate ID"}]}. '
                'Choose only substantive, unused IDs in the window for that path. '
                'No other field can be edited. Preserve the intended evidence topic; do not repeat '
                'coverage analysis or report. If the window does not support the intended claim, '
                'return {"blocked":"Source selection needs broader review"}; do not guess.\n' + legacy.packed(view))
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
            'source_catalogue': passages.input_view(bundle['manifest'], catalog)}) + grounding_prompt
    text = legacy.prompt_for(role, bundle, writing, hydrated, feedback)
    if role == 'analysis':
        text = text.replace('"quotes":[{"scope_id":"EXACT SOURCE ID","text":"exact substring"}]',
                            '"quotes":[{"passage_id":"EXACT SELECTED PASSAGE ID"}]')
        text += '\n\nQUOTE SELECTION CONTRACT\n' + QUOTE_RULE + (
            ' Use passage IDs from the supplied retrieval quotes. Empty quotes arrays are allowed. '
            'Narrative paraphrases use ordinary citations and must not be presented as quotations.')
    if role == 'review':
        text += '\n\nRENDERING CONTRACT\nCode materializes selected quotations and inserts displayed citation brackets. '
        text += (' Complete one comprehensive audit before returning: reconcile every repeated claim across financial context, retrieval summaries and analysis; verify guidance ranges, conditions and accounting basis; inspect material coverage and concise writing. Return the complete actionable correction batch, with every affected occurrence and specific required edit. Separate factual defects from optional additions; do not withhold known findings for later rounds. ')
        text += 'Judge quote relevance and context against original sources; do not charge renderer-added brackets as an author-formatting defect.'
    return text + grounding_prompt


def bounded_patch(role, prior, patch, catalog):
    try:
        passages.resolve_selections(role, prior, catalog)
    except passages.SelectionError as exc:
        view = passages.repair_view(role, prior, exc.issues, catalog)
    else:
        raise ValueError('No invalid selections to repair')
    if view['unresolved_paths']:
        raise ValueError('No bounded repair window for invalid selection')
    if isinstance(patch, dict) and set(patch) == {'blocked'}:
        raise ValueError('Source selection needs broader review: ' + str(patch['blocked']))
    out = passages.apply_patch(role, prior, patch, catalog)
    allowed = {r['path']: {p['passage_id'] for p in r['candidates_and_adjacent_context']
                         if p['text'].strip() and p['passage_id'] not in r['already_selected_ids']}
               for r in view['repairs']}
    for edit in patch['replacements']:
        if not isinstance(edit['passage_id'], str) or edit['passage_id'] not in allowed[edit['path']]:
            raise ValueError('Replacement must be a supplied, substantive, unused candidate for its slot')
    return out


def repair_handoff(root, deps, prior, issues, review, catalog, refusals=None):
    """Explicit non-model queue; never turn an unresolved review into a pass."""
    if review and any(f['target'] == 'formatter' for f in review['findings']):
        return {'kind': 'formatter', 'findings': review['findings'],
                'review_digest': base.digest(review), 'artifact_digest': base.digest(deps),
                'protocol_sha256': base.sha(root / 'protocol.json'),
                'next_action': 'Repair code in a new version; rerender and independently review. Retain substantive findings.'}
    windows = {r: passages.repair_view(r, prior[r], v, catalog) for r, v in issues.items()}
    missing = {r: v for r, v in windows.items() if v['unresolved_paths']}
    if missing or refusals:
        return {'kind': 'source_selection', 'windows': missing, 'model_refusals': refusals or {},
                'prior_digest': base.digest(prior), 'artifact_digest': base.digest(deps),
                'protocol_sha256': base.sha(root / 'protocol.json'),
                'next_action': 'Select evidence from original source in a separately authorized repair; full catalogue is not resent automatically.'}
    return None


def freeze(case_path, output, writing_path, repair_loop=False, deterministic_corrections=False, signals=True, efficient=False, qa_grounding=True, qa_grounding_version=None):
    if repair_loop and deterministic_corrections:
        raise ValueError("Choose one correction strategy")
    root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=True)
    manifest = evidence.prepare(case_path, root / 'evidence')
    base.save(root / 'passages.json', passages.catalog(manifest))
    # Every new freeze binds imported helpers, including opt-out runs whose
    # validation still imports the grounding module. Legacy load is unchanged.
    names = tuple(sorted(p.name for p in Path(__file__).parent.glob('earnings_*')
                         if p.suffix in ('.py', '.mjs')))
    protocol = {'report_signals': bool(signals), 'version': EFFICIENT_VERSION if efficient else VERSION, 'repair_loop': bool(repair_loop), 'deterministic_corrections': bool(deterministic_corrections), 'case_path': str(Path(case_path).resolve()),
                'case_sha256': base.sha(case_path), 'evidence_manifest': str(root / 'evidence/manifest.json'),
                'evidence_sha256': base.sha(root / 'evidence/manifest.json'),
                'passages_sha256': base.sha(root / 'passages.json'),
                'writing_standard': str(Path(writing_path).resolve()), 'writing_sha256': base.sha(writing_path),
                'models': {k: list(v) for k, v in MODELS.items()}, 'max_correction_rounds': 2,
                'code': [{'path': str(Path(__file__).parent / n), 'sha256': base.sha(Path(__file__).parent / n)} for n in names]}
    if efficient:
        protocol['evidence_reuse'] = copy.deepcopy(EFFICIENT_POLICY)
    if qa_grounding:
        version = qa_grounding_version or grounding.HEADER_VERSION
        qa_index = grounding.build(evidence.load_bundle(manifest), base.read(root / 'passages.json'), version=version)
        base.save(root / 'qa-grounding.json', qa_index)
        protocol.update(qa_grounding=version, qa_grounding_path=str(root / 'qa-grounding.json'),
                        qa_grounding_sha256=base.sha(root / 'qa-grounding.json'))
    base.save(root / 'protocol.json', protocol)
    return protocol


def load(root):
    p = base.read(root / 'protocol.json')
    if p['version'] not in (VERSION, EFFICIENT_VERSION) or p['models'] != {k: list(v) for k, v in MODELS.items()} or p['max_correction_rounds'] != 2:
        raise ValueError('Protocol/settings differ')
    if (p['version'] == EFFICIENT_VERSION and p.get('evidence_reuse') != EFFICIENT_POLICY
            or p['version'] == VERSION and 'evidence_reuse' in p):
        raise ValueError('Evidence reuse policy differs')
    for path, digest in [(p['case_path'], p['case_sha256']), (p['evidence_manifest'], p['evidence_sha256']),
                         (p['writing_standard'], p['writing_sha256']), (root / 'passages.json', p['passages_sha256']),
                         *((c['path'], c['sha256']) for c in p['code'])]:
        if base.sha(path) != digest:
            raise ValueError('Frozen input/code changed: ' + str(path))
    if p.get('response_recovery'):
        recovery = p['response_recovery']
        if base.sha(Path(recovery['seed'])/'protocol.json') != recovery['protocol_sha256']:
            raise ValueError('Recovery source protocol changed')
        original = base.read(Path(recovery['seed'])/'protocol.json')
        compared = {k:v for k,v in p.items() if k not in ('code','response_recovery')}
        if original.get('qa_grounding_path'):
            compared['qa_grounding_path'] = original['qa_grounding_path']
        if compared != {k:v for k,v in original.items() if k != 'code'}:
            raise ValueError('Recovery must preserve original settings and evidence')
    bundle = evidence.load_bundle(p['evidence_manifest'])
    catalog = passages.catalog(p['evidence_manifest'])
    if catalog != base.read(root / 'passages.json'):
        raise ValueError('Passage catalogue differs from original evidence')
    grounding.attach(root, p, bundle, catalog)
    if p.get('prepared_recovery'):
        from .earnings_prepared_recovery import apply
        bundle, prepared, inherited, identities = apply(p, bundle, catalog)
        bundle['_prepared_recovery'] = {'artifacts':prepared,'tokens':inherited,'identities':identities}
    return p, bundle, catalog


def findings(role, exc):
    if isinstance(exc, passages.SelectionError):
        return [{'target': role, 'passage': x['path'], 'reason': x['reason'],
                 'required_change': x['required_change'], 'selection': x['selection']} for x in exc.issues]
    return [{'target': role, 'passage': 'Role schema/evidence validation', 'reason': str(exc),
             'required_change': 'Repair the stated schema or evidence defect and return full role JSON.'}]


class PendingJobs(Exception):
    """A finite coordinator turn used its new-job allowance."""


def measured_wall_seconds(jobs):
    receipts = list(execution_receipts(jobs))
    if any(r.get('usage_is_inherited') for r in receipts):
        return None  # Original process timing is unobserved for recovered responses.
    return (max(datetime.fromisoformat(r['finished_at']) for r in receipts) -
            min(datetime.fromisoformat(r['started_at']) for r in receipts)).total_seconds()


def efficient_exchange(root, role, number, inputs, bundle, catalog, writing, obtain):
    """Exactly replay a role and at most one source lookup; no budget reset."""
    from research import earnings_efficient_evidence as reuse
    input_path = root / 'inputs' / f'{role}-r{number}.json'
    extra, prior_hash, chain = (), None, []
    recovery = base.read(root/'protocol.json').get('response_recovery', {})
    extension = recovery.get('extra_evidence')
    if extension:
        from .earnings_role_import import authenticate
        ref = recovery.get('imports', {}).get(extension['job'])
        if (extension.get('max_additional_expansions') != 1 or ref is None
                or not extension['job'].startswith('retrieval-r') or not extension['job'].endswith('-evidence-1')
                or base.digest(authenticate(ref)['content']) != extension['request_sha256']):
            raise ValueError('Evidence recovery binding differs')
    permitted = bool(extension and extension['job'] == f'{role}-r{number}-evidence-1')
    for expansion in range(3 if permitted else 2):
        job = root / 'jobs' / (f'{role}-r{number}' + (f'-evidence-{expansion}' if expansion else ''))
        text = prompt(role, bundle, writing, inputs['dependencies'], inputs['feedback'], catalog,
                      inputs['prior'], inputs['issues'], efficient=True, extra_scope_ids=extra)
        bindings = {'protocol_sha256': base.sha(root / 'protocol.json'), 'role': role,
                    'round': number, 'inputs_sha256': base.sha(input_path),
                    'evidence_context_version': reuse.VERSION, 'evidence_expansion': expansion,
                    'extra_scope_ids_sha256': base.digest(list(extra)), 'prior_output_sha256': prior_hash}
        result = obtain(job, text, bindings)
        chain.append({'path': str(job), 'receipt': result['receipt']})
        requested = reuse.requested_scopes(result['content'], bundle, catalog, extra)
        if requested is None:
            return result['content'], chain, extra
        if inputs['issues'] is not None or (expansion and not (permitted and expansion == 1)):
            raise ValueError('Evidence expansion exhausted; no completed role output')
        # Financial expansion has stricter measured bounds; validate before any
        # second call. Other roles use the existing exact scope-response limits.
        if role == 'financial':
            from research import earnings_financial_context as financial
            financial.expand(bundle, list(requested))
        extra = tuple(sorted(set(extra) | set(requested)))
        prior_hash = base.sha(job / 'output.json')
    raise AssertionError('Unreachable evidence exchange')


def bind_efficient_financial(out, bundle, extra_scope_ids=()):
    from research import earnings_financial_context as financial
    if not isinstance(out, dict):
        raise ValueError('Financial role output must be an object')
    legacy.validate_output('financial', out, bundle)
    payload = financial.financial_role_payload(bundle)
    supplied = {row['id'] for row in payload['complete_context_chunks']} | set(extra_scope_ids)
    supplied.update(o['id'] for o in bundle['financial']['observations'])
    cited = {sid for row in out.get('context', []) for sid in row.get('citations', [])}
    if not cited <= supplied:
        raise ValueError('Financial context cites unavailable scopes without complete source expansion')
    return financial.bind(out, bundle)


def execution_receipts(jobs):
    return [entry['receipt'] for job in jobs for entry in job.get('evidence_jobs', [{'receipt': job['receipt']}])]


def measured_tokens(jobs):
    values = [r['session']['usage']['totalTokens'] for r in execution_receipts(jobs)]
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError('Every efficient role requires measured nonnegative token usage')
    return sum(values)


def efficient_dependencies(role, deps):
    names = () if role == 'financial' else ('financial',) if role == 'retrieval' else ('financial','retrieval') if role == 'analysis' else ('financial','retrieval','analysis')
    return {name: copy.deepcopy(deps[name]) for name in names}


def run(output, max_new_jobs=None):
    root = Path(output).resolve(); p, bundle, catalog = load(root)
    if (root / 'result.json').exists():
        return verify(root)
    if p.get('qa_grounding') == grounding.HEADER_VERSION:
        index = bundle['qa_grounding']
        blocked = [e['exchange_id'] for e in index['exchanges'] if e['flags'] and e['mechanical_disposition'] != 'courtesy_only']
        blocked += [t['id'] for t in index['unassigned_qa_turns'] if t['mechanical_disposition'] == 'unresolved']
        if blocked:
            raise ValueError('Source attribution preparation required before any model call: ' + ', '.join(blocked))
    writing = Path(p['writing_standard']).read_text()
    deps, prior, selection_issues, feedback, jobs, failures = {}, {}, {}, [], [], []
    prepared = bundle.get('_prepared_recovery')
    if prepared: deps = copy.deepcopy(prepared['artifacts'])
    need = {'analysis'} if prepared else {'financial', 'retrieval'}; review = None; handoff = None; refusals = {}
    new_jobs = 0

    def call(role, round_number, snapshot):
        nonlocal new_jobs
        repair = role in selection_issues
        inputs = {'dependencies': efficient_dependencies(role, snapshot) if p['version'] == EFFICIENT_VERSION else copy.deepcopy(snapshot),
                  'feedback': [f for f in feedback if f['target'] == role],
                  'prior': prior.get(role) if repair else None,
                  'issues': selection_issues.get(role)}
        job = root / 'jobs' / f'{role}-r{round_number}'
        if not (job / 'request.json').exists():
            if max_new_jobs is not None and new_jobs >= max_new_jobs:
                raise PendingJobs()
            new_jobs += 1
        job.mkdir(parents=True, exist_ok=True)
        input_path = root / 'inputs' / f'{role}-r{round_number}.json'
        base.save(input_path, inputs)
        if p['version'] == EFFICIENT_VERSION:
            # The ordinary base-job allowance above is charged once. Additional
            # evidence sessions are separately charged to the same finite turn.
            def obtain(path, text, bindings):
                nonlocal new_jobs
                if path != job and not (path / 'request.json').exists():
                    if max_new_jobs is not None and new_jobs >= max_new_jobs:
                        raise PendingJobs()
                    new_jobs += 1
                imported = p.get('response_recovery', {}).get('imports', {}).get(path.name)
                if imported is not None:
                    from .earnings_role_import import create
                    return create(path, text, *MODELS[role], bindings, 1200, imported)
                return run_role(path, text, *MODELS[role], bindings, timeout=1200)
            raw, chain, extra = efficient_exchange(root, role, round_number, inputs, bundle, catalog, writing, obtain)
            record = {'role': role, 'round': round_number, 'mode': 'selection_patch' if repair else 'full',
                      'path': str(job), 'receipt': chain[-1]['receipt'], 'evidence_jobs': chain,
                      'expanded_scope_ids': list(extra)}
            return raw, record, inputs
        text = prompt(role, bundle, writing, inputs['dependencies'], inputs['feedback'], catalog,
                      inputs['prior'], inputs['issues'])
        result = run_role(job, text, *MODELS[role], {'protocol_sha256': base.sha(root / 'protocol.json'),
                          'role': role, 'round': round_number, 'inputs_sha256': base.sha(input_path)}, timeout=1200)
        record = {'role': role, 'round': round_number, 'mode': 'selection_patch' if repair else 'full',
                  'path': str(job), 'receipt': result['receipt']}
        return result['content'], record, inputs

    def receive(role, result, errors):
        raw, record, inputs = result; jobs.append(record)
        if inputs['issues'] is not None and isinstance(raw, dict) and set(raw) == {'blocked'}:
            refusals[role] = raw['blocked']
        try:
            out = (bounded_patch(role, inputs['prior'], raw, catalog)
                   if inputs['issues'] is not None else raw)
            if role == 'financial' and p['version'] == EFFICIENT_VERSION:
                out = bind_efficient_financial(out, bundle, record['expanded_scope_ids'])
            if role == 'retrieval' and p.get('qa_grounding') == grounding.HEADER_VERSION:
                out, normalization = grounding.normalize_courtesy(out, bundle, catalog)
                record['courtesy_normalization'] = normalization
            if role == 'retrieval' and p.get('response_recovery'):
                from .earnings_role_import import complete_courtesy
                out, additions = complete_courtesy(out, bundle, catalog)
                record['deterministic_courtesy_additions'] = additions
            prior[role] = out
            selection_issues.pop(role, None)
            validate(role, out, bundle, catalog)
            if p['version'] == EFFICIENT_VERSION:
                from research import earnings_efficient_evidence as reuse
                reuse.validate_support(role, out, bundle, catalog, inputs['dependencies'], record['expanded_scope_ids'])
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

    for round_number in range(p.get("prepared_recovery", {}).get("prior_rounds", 0), 3):
        handoff = repair_handoff(root, deps, prior, selection_issues, review, catalog, refusals)
        if handoff:
            break
        errors = []
        snapshot = copy.deepcopy(deps)
        if max_new_jobs is not None or p['version'] == EFFICIENT_VERSION:
            preparers = need & {'financial', 'retrieval'}
            if p['version'] == EFFICIENT_VERSION and 'financial' in preparers:
                preparers.add('retrieval')
            for role in sorted(preparers):
                if errors and p['version'] == EFFICIENT_VERSION:
                    break
                receive(role, call(role, round_number, deps if p['version'] == EFFICIENT_VERSION else snapshot), errors)
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = {r: pool.submit(call, r, round_number, snapshot) for r in sorted(need & {'financial', 'retrieval'})}
                for role, future in pending.items():
                    receive(role, future.result(), errors)
        if not errors:
            receive('analysis', call('analysis', round_number, deps), errors)
        if not errors:
            review = receive('review', call('review', round_number, deps), errors)
            if review is not None:
                if p.get('repair_loop') or p.get('deterministic_corrections') or review['verdict'] in ('pass', 'blocked') or any(f['target'] == 'formatter' for f in review['findings']):
                    break
                errors = review['findings']
        failures.append({'round': round_number, 'findings': errors})
        feedback = errors
        need = {f['target'] for f in errors}
    handoff = repair_handoff(root, deps, prior, selection_issues, review, catalog, refusals)
    accepted = bool(review and review['verdict'] == 'pass' and not handoff)
    if handoff:
        base.save(root / 'repair-handoff.json', handoff)
    materialized = {r: passages.hydrate(r, v, catalog) for r, v in deps.items()}
    base.save(root / 'artifacts.json', deps)
    base.save(root / 'materialized-artifacts.json', materialized)
    base.save(root / 'review.json', review)
    result = {'version': p['version'], 'status': 'accepted' if accepted else 'blocked',
              'correction_rounds': max(j['round'] for j in jobs), 'jobs': jobs, 'failures': failures,
              'protocol_sha256': base.sha(root / 'protocol.json'),
              'artifact_digest': base.digest(deps), 'materialized_digest': base.digest(materialized),
              'review_sha256': base.sha(root / 'review.json'),
              'repair_handoff_sha256': base.sha(root / 'repair-handoff.json') if handoff else None,
              'wall_seconds': measured_wall_seconds(jobs)}
    if p['version'] == EFFICIENT_VERSION:
        result['total_tokens'] = measured_tokens(jobs) + bundle.get('_prepared_recovery', {}).get('tokens', 0)
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
    prepared = bundle.get('_prepared_recovery')
    if prepared:
        deps = copy.deepcopy(prepared['artifacts']); identities.update(prepared['identities'])
    review = None; review_deps = None; round_snapshots = {}; refusals = {}
    for job in result['jobs']:
        if review and any(f['target'] == 'formatter' for f in review['findings']):
            raise ValueError('Formatter failure must stop model correction loop')
        if refusals:
            raise ValueError('Source selection refusal must stop model correction loop')
        role, number = job['role'], job['round']
        key = (role, number)
        if key in keys or role not in MODELS or type(number) is not int or not p.get('prepared_recovery', {}).get('prior_rounds', 0) <= number <= 2 or (prepared and role in ('financial','retrieval')):
            raise ValueError('Duplicate/invalid job')
        keys.add(key)
        path = root / 'jobs' / f'{role}-r{number}'
        if Path(job['path']).resolve() != path:
            raise ValueError('Unexpected job path')
        input_path = root / 'inputs' / f'{role}-r{number}.json'
        inputs = base.read(input_path)
        round_snapshots.setdefault(number, copy.deepcopy(deps))
        expected_deps = (efficient_dependencies(role, deps) if p['version'] == EFFICIENT_VERSION else
                         round_snapshots[number] if role in ('financial', 'retrieval') else deps)
        if inputs['dependencies'] != expected_deps:
            raise ValueError('Dependency chain mismatch')
        if inputs['issues'] != expected_issues.get(role) or inputs['prior'] != (prior.get(role) if role in expected_issues else None):
            raise ValueError('Repair differs from actual failed selections')
        mode = 'selection_patch' if inputs['issues'] is not None else 'full'
        if job['mode'] != mode:
            raise ValueError('Job mode mismatch')
        if p['version'] == EFFICIENT_VERSION:
            def obtain(check_path, text, bindings):
                request = base.read(check_path / 'request.json'); item = verify_job(check_path)
                imported = p.get('response_recovery', {}).get('imports', {}).get(check_path.name)
                if imported is not None:
                    if base.read(check_path/'import.json')['source'] != imported:
                        raise ValueError('Recovery import changed')
                elif (check_path/'import.json').exists():
                    raise ValueError('Unreserved role import')
                if ((request['model'], request['effort']) != MODELS[role] or request['bindings'] != bindings
                        or (check_path / 'prompt.txt').read_text() != text):
                    raise ValueError('Efficient role differs from exact evidence request')
                sid = item['receipt']['session']['id']
                if sid in identities:
                    raise ValueError('Fresh independent sessions required')
                identities.add(sid)
                return item
            content, chain, extra = efficient_exchange(root, role, number, inputs, bundle, catalog, writing, obtain)
            if (job.get('evidence_jobs') != chain or job.get('expanded_scope_ids') != list(extra)
                    or job['receipt'] != chain[-1]['receipt']):
                raise ValueError('Evidence expansion receipt chain differs')
            value = {'content': content, 'receipt': chain[-1]['receipt']}
        else:
            request = base.read(path / 'request.json'); value = verify_job(path)
            if value['receipt'] != job['receipt'] or (request['model'], request['effort']) != MODELS[role]:
                raise ValueError('Receipt/model mismatch')
            sid = value['receipt']['session']['id']
            if sid in identities:
                raise ValueError('Fresh independent sessions required')
            identities.add(sid)
            if request['bindings'] != {'protocol_sha256': base.sha(root / 'protocol.json'), 'role': role,
                                       'round': number, 'inputs_sha256': base.sha(input_path)}:
                raise ValueError('Job input binding mismatch')
            text = prompt(role, bundle, writing, inputs['dependencies'], inputs['feedback'], catalog, inputs['prior'], inputs['issues'])
            if (path / 'prompt.txt').read_text() != text:
                raise ValueError('Prompt differs from original evidence and handoff')
        if mode == 'selection_patch' and isinstance(value['content'], dict) and set(value['content']) == {'blocked'}:
            refusals[role] = value['content']['blocked']
        try:
            out = bounded_patch(role, inputs['prior'], value['content'], catalog) if mode == 'selection_patch' else value['content']
            if role == 'financial' and p['version'] == EFFICIENT_VERSION:
                out = bind_efficient_financial(out, bundle, job['expanded_scope_ids'])
            if role == 'retrieval' and p.get('qa_grounding') == grounding.HEADER_VERSION:
                out, normalization = grounding.normalize_courtesy(out, bundle, catalog)
                if job.get('courtesy_normalization') != normalization:
                    raise ValueError('Courtesy derivation differs')
            if role == 'retrieval' and p.get('response_recovery'):
                from .earnings_role_import import complete_courtesy
                out, additions = complete_courtesy(out, bundle, catalog)
                if job.get('deterministic_courtesy_additions') != additions:
                    raise ValueError('Deterministic courtesy completion changed')
            prior[role] = out
            expected_issues.pop(role, None)
            validate(role, out, bundle, catalog)
            if p['version'] == EFFICIENT_VERSION:
                from research import earnings_efficient_evidence as reuse
                reuse.validate_support(role, out, bundle, catalog, inputs['dependencies'], job['expanded_scope_ids'])
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
    if not prepared and not {('financial', 0), ('retrieval', 0)} <= keys:
        raise ValueError('Initial preparers missing')
    if result['version'] != p['version'] or result['status'] not in ('accepted', 'blocked') or result['correction_rounds'] != max(n for _, n in keys):
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
    handoff = repair_handoff(root, deps, prior, expected_issues, review, catalog, refusals)
    path = root / 'repair-handoff.json'
    if handoff:
        if (result['status'] != 'blocked' or not path.exists() or base.read(path) != handoff or
                result.get('repair_handoff_sha256') != base.sha(path)):
            raise ValueError('Repair handoff differs from authenticated failures')
    elif path.exists() or result.get('repair_handoff_sha256'):
        raise ValueError('Unexpected repair handoff')
    if 'analysis' in deps:
        if (base.sha(root / 'report.txt') != result['report_sha256'] or base.sha(root / 'report.html') != result['html_sha256'] or
            (root / 'report.txt').read_bytes().decode('utf-8') != legacy.report_text(materialized['analysis'], materialized['financial'], bundle)):
            raise ValueError('Report differs from materialized sources')
    measured = measured_wall_seconds(result['jobs'])
    if result['wall_seconds'] != measured:
        raise ValueError('Timing differs from authenticated receipts')
    if p['version'] == EFFICIENT_VERSION and result.get('total_tokens') != measured_tokens(result['jobs']) + bundle.get('_prepared_recovery', {}).get('tokens', 0):
        raise ValueError('Efficient evidence-session usage differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze'); f.add_argument('case'); f.add_argument('output'); f.add_argument('writing'); f.add_argument('--repair-loop', action='store_true'); f.add_argument('--deterministic-corrections', action='store_true')
    f.add_argument('--signals', action=argparse.BooleanOptionalAction, default=True,
                   help='Add independently reviewed signals after acceptance (default: enabled; --no-signals opts out)')
    f.add_argument('--qa-grounding', action=argparse.BooleanOptionalAction, default=True,
                   help='Bind retrieval to indexed Q&A membership before analysis (new freezes only)')
    f.add_argument('--efficient', action='store_true', help='Opt into source-bound role evidence reuse; leaves v4 defaults unchanged')
    for name in ('run', 'verify'):
        sub.add_parser(name).add_argument('output')
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.case, args.output, args.writing, args.repair_loop, args.deterministic_corrections, args.signals, efficient=args.efficient, qa_grounding=args.qa_grounding); print('Frozen passage-selection protocol')
    else:
        result = (run if args.command == 'run' else verify)(args.output)
        summary = {k: result[k] for k in ('status', 'correction_rounds', 'wall_seconds')}
        if base.read(Path(args.output)/'protocol.json').get('deterministic_corrections') and result['status'] == 'blocked':
            from research import earnings_corrections as corrections
            root = Path(args.output).resolve()
            continuation = root.with_name(root.name + '-corrections')
            if not (continuation/'protocol.json').exists() and args.command == 'run':
                if set(base.read(root/'artifacts.json')) == {'financial', 'retrieval', 'analysis'} and base.read(root/'review.json'):
                    corrections.initialize(root, continuation)
                else:
                    summary['corrections_not_started'] = 'Complete preparation and substantive review required'
            if (continuation/'protocol.json').exists():
                if base.read(continuation/'protocol.json')['seed'] != str(root):
                    raise ValueError('Correction directory belongs to another seed')
                summary = (corrections.run if args.command == 'run' else corrections.verify)(continuation)
                summary['corrections_directory'] = str(continuation)
        if base.read(Path(args.output)/'protocol.json').get('repair_loop') and result['status'] == 'blocked':
            from research import earnings_report_repair as repair
            root = Path(args.output).resolve()
            continuation = root.with_name(root.name + '-repair')
            if not (continuation/'protocol.json').exists() and args.command == 'run':
                artifacts = base.read(root/'artifacts.json')
                review = base.read(root/'review.json')
                if set(artifacts) == {'financial', 'retrieval', 'analysis'} and review:
                    repair.initialize(root, continuation)
                else:
                    summary['repair_not_started'] = 'Source preparation must produce a complete candidate and substantive review first'
            if (continuation/'protocol.json').exists():
                if base.read(continuation/'protocol.json')['seed'] != str(root):
                    raise ValueError('Repair directory belongs to a different seed')
                summary = (repair.run if args.command == 'run' else repair.verify)(continuation)
                summary['repair_directory'] = str(continuation)
        if base.read(Path(args.output)/'protocol.json').get('report_signals') and summary['status'] == 'accepted':
            from research import earnings_signals as signals
            seed = Path(summary.get('corrections_directory', summary.get('repair_directory', args.output))).resolve()
            edition = seed.with_name(seed.name + '-signals')
            if not (edition/'protocol.json').exists() and args.command == 'run':
                signals.initialize(seed, edition)
            if (edition/'protocol.json').exists():
                if base.read(edition/'protocol.json')['seed'] != str(seed):
                    raise ValueError('Signal edition belongs to another report')
                summary['signals'] = (signals.run if args.command == 'run' else signals.verify)(edition)
                summary['signals_directory'] = str(edition)
            else:
                summary['signals'] = {'status': 'not_started'}
        print(legacy.packed(summary))


if __name__ == '__main__':
    main()
