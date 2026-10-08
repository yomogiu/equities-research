"""Explicitly authorized, deterministic remediation editions of stopped reports.

This is a new user-directed edition, never an ordinary correction continuation.
No author model runs here. An exact field plan is staged, then a fresh reviewer
accepts or rejects the complete report using source-bound focused evidence and the writing rubric.
"""
from __future__ import annotations
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

from research import earnings_experiment as base
from research import earnings_corrections as corrections
from research import earnings_report_repair as repair
from research import earnings_passage_pipeline as pipe
from research import earnings_mixed_pipeline as legacy
from research import earnings_compact_evidence as evidence
from research import earnings_passages as passages
from research import earnings_repair_context as context
from research import earnings_repair_review as review_loop
from research.earnings_mixed_runner import run_role, verify_job

VERSION = 'targeted-remediation-v3'
MODEL = ('gpt-6.1-sol', 'medium')
MAX_PROMPT_CHARS = 350000
STOPPED = {'blocked', 'budget_exhausted', 'invalid_patch', 'invalid_review', 'prompt_too_large', 'evidence_insufficient'}


def targets(snapshot, bundle):
    """Only existing commentary/citation fields and known display overrides."""
    result = {}
    def add(path, kind, value):
        result[tuple(path)] = {'kind': kind, 'value': value}
    def fields_at(prefix, value, names):
        for name in names:
            add(prefix + [name], 'citations' if name.endswith('citations') else 'text', value[name])
    art = snapshot['artifacts']
    for i, row in enumerate(art['financial']['context']):
        fields_at(['artifacts', 'financial', 'context', i], row, ('text', 'citations'))
    for i, text in enumerate(art['financial']['gaps']):
        add(['artifacts', 'financial', 'gaps', i], 'text', text)
    for i, row in enumerate(art['retrieval']['exchange_coverage']):
        fields_at(['artifacts', 'retrieval', 'exchange_coverage', i], row, ('question', 'answer', 'consequence'))
        for name in ('question_passage_ids','answer_passage_ids','continuation_exchange_ids'):
            if name in row: add(['artifacts','retrieval','exchange_coverage',i,name], 'source_links',row[name])
        if 'grounding_notes' in row: add(['artifacts','retrieval','exchange_coverage',i,'grounding_notes'],'text',row['grounding_notes'])
    for i, row in enumerate(art['retrieval']['document_findings']):
        fields_at(['artifacts', 'retrieval', 'document_findings', i], row, ('text', 'citations'))
    fields_at(['artifacts', 'analysis'], art['analysis'], ('title', 'opening', 'opening_citations', 'scope'))
    for i, row in enumerate(art['analysis']['findings']):
        fields_at(['artifacts', 'analysis', 'findings', i], row, ('heading', 'text', 'citations'))
        add(['artifacts','analysis','findings',i,'quotes'],'quote_subset',row['quotes'])
    for i, row in enumerate(art['analysis']['next_tests']):
        fields_at(['artifacts', 'analysis', 'next_tests', i], row, ('text', 'citations'))
    for key in repair.row_catalog(art['financial'], bundle):
        add(['format', 'rows', key], 'display_row', snapshot['format']['rows'].get(key))
    add(['format', 'basis'], 'display_basis', snapshot['format']['basis'])
    add(['format', 'layout'], 'layout', snapshot['format'].get('layout'))
    add(['format', 'tables'], 'display_tables', snapshot['format'].get('tables'))
    add(['format','source_rows'],'source_rows',snapshot['format'].get('source_rows'))
    return result


def apply(snapshot, plan, bundle, catalog):
    """Atomic compare-and-swap; source observations and list membership are inert."""
    if not isinstance(plan, dict) or set(plan) not in ({'snapshot_sha256', 'operations'}, {'snapshot_sha256', 'operations', 'claim_groups'}):
        raise ValueError('Unexpected remediation plan schema')
    if plan['snapshot_sha256'] != base.digest(snapshot):
        raise ValueError('Stale remediation snapshot')
    ops = plan['operations']
    if isinstance(ops, list) and ops and any('target_id' in op for op in ops if isinstance(op, dict)):
        if any(not isinstance(op, dict) or 'target_id' not in op or 'path' in op for op in ops):
            raise ValueError('Do not mix exact-target and legacy path plans')
        candidate = corrections.apply(snapshot, plan, bundle, catalog)
        if candidate['artifacts'] == snapshot['artifacts'] and candidate['format'] == snapshot['format']:
            raise ValueError('Unchanged remediation candidate')
        return candidate
    if not isinstance(ops, list) or not 1 <= len(ops) <= 24:
        raise ValueError('One to 24 explicit operations required')
    registry = targets(snapshot, bundle); out = copy.deepcopy(snapshot); used = set(); ids = set()
    for op in ops:
        corrections.fields(op, ('id', 'path', 'kind', 'before_sha256', 'after_sha256', 'value',
                               'reason', 'citations', 'passage_ids'), 'remediation operation')
        legacy.check_text(op['id'], 'operation ID')
        path = op['path']
        if not isinstance(path, list) or not path or any(type(p) not in (str, int) or (type(p) is int and p < 0) for p in path):
            raise ValueError('Typed exact field path required')
        key = tuple(path)
        if key not in registry or registry[key]['kind'] != op['kind']:
            raise ValueError('Field is outside remediation allowlist')
        if key in used or op['id'] in ids:
            raise ValueError('Duplicate/conflicting remediation operation')
        used.add(key); ids.add(op['id']); target = registry[key]; value = op['value']
        if op['before_sha256'] != base.digest(target['value']) or op['after_sha256'] != base.digest(value):
            raise ValueError('Field before/after hash mismatch')
        if value == target['value']:
            raise ValueError('No-op remediation operation')
        corrections.claim(op, bundle, catalog)
        if op['kind'] == 'text':
            legacy.check_text(value, 'remediation text')
            if len(value) > 4000: raise ValueError('Remediation text exceeds 4000 characters')
        elif op['kind'] == 'citations':
            legacy.check_ids(value, legacy.ids_for(bundle), 'replacement citations')
        elif op['kind'] == 'source_rows':
            repair.supplemental.build(value,bundle)
        elif op['kind'] == 'quote_subset':
            if not isinstance(value,list) or any(q not in target['value'] for q in value) or len(value)>len(target['value']):
                raise ValueError('Only an original quote subset is allowed')
        elif op['kind'] == 'source_links':
            allowed = ({x['exchange_id'] for x in bundle['qa_grounding']['exchanges']} if path[-1]=='continuation_exchange_ids' else {x['passage_id'] for x in catalog['passages']})
            legacy.check_ids(value,allowed,'reviewed source links',nonempty=False)
        elif op['kind'] == 'layout':
            repair.validate_layout(value, repair.row_catalog(out['artifacts']['financial'], bundle), legacy.ids_for(bundle))
        elif op['kind'] == 'display_tables':
            repair.validate_table_labels(value, out['artifacts']['financial'], bundle)
        else:
            names = ('label', 'dimensions', 'citations') if op['kind'] == 'display_row' else ('text', 'citations')
            corrections.fields(value, names, 'display metadata')
            for name, maximum in (('label', 160), ('dimensions', 200), ('text', 240)):
                if name in value and (not isinstance(value[name], str) or len(value[name]) > maximum):
                    raise ValueError('Invalid bounded display metadata')
            legacy.check_ids(value['citations'], legacy.ids_for(bundle), 'display citations')
        corrections.put(out, path, value)
    for role in ('financial', 'retrieval', 'analysis'):
        pipe.validate(role, out['artifacts'][role], bundle, catalog)
    repair.validate_format(out['format'], out['artifacts']['financial'], bundle)
    context.propagation_check(snapshot, out, plan, bundle)
    return out


EXPORT = '''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);p=json.loads((root/'protocol.json').read_text())
if p.get('prepared_recovery'):
 from research import earnings_passage_pipeline as c
 from research import earnings_report_repair as repair
 from research import earnings_experiment as base
 v=c.verify(root)
 if (v['status']!='blocked' or v['correction_rounds']!=2 or p['max_correction_rounds']!=2
     or p['prepared_recovery']['prior_rounds']!=2):
  raise ValueError('Prepared recovery must be stopped after its inherited two-round limit')
 artifacts=base.read(root/'artifacts.json'); review=base.read(root/'review.json')
 if set(artifacts)!={'financial','retrieval','analysis'} or not review or review['verdict']=='pass' or not review['findings']:
  raise ValueError('Completed analysis and unsuccessful independent review required')
 reviews=[j for j in v['jobs'] if j['role']=='review']
 if not reviews or reviews[-1]['round']!=2:
  raise ValueError('Final prepared candidate lacks a completed independent review')
 inputs=base.read(root/'inputs'/'review-r2.json')
 if inputs['dependencies']!=c.efficient_dependencies('review',artifacts):
  raise ValueError('Final independent review did not assess current candidate')
 snapshot={'artifacts':artifacts,'format':{'rows':{},'basis':{'text':'','citations':[]}},
           'findings':[{'id':repair.finding_id(f),'finding':f} for f in review['findings']]}
 print(json.dumps({'status':v['status'],'snapshot':snapshot,'source_protocol':p,
                  'prior_rounds':v['correction_rounds'],'prior_tokens':v['total_tokens']}))
 sys.exit(0)
elif p['version'].startswith('targeted-remediation-'):
 from research import earnings_remediation as c
 p,b,k,w=c.load(root);v=c._replay(root,p,b,k,w)
 rounds=p['history']['prior_rounds']+v['review_attempts']
 tokens=p['history']['prior_tokens']+v['tokens']
else:
 from research import earnings_corrections as c
 p,b,k,w=c.load(root);v=c.replay(root,p,b,k,w)
 rounds=p.get('prior_rounds',0)+v['round']
 tokens=p.get('inherited_tokens',0)+v['tokens']
print(json.dumps({'status':v['status'],'snapshot':v['state'],'source_protocol':p['source_protocol'],
 'prior_rounds':rounds,'prior_tokens':tokens}))
'''


def export_seed(seed):
    p = base.read(seed/'protocol.json')
    prepared = p.get('version') == pipe.EFFICIENT_VERSION and bool(p.get('prepared_recovery'))
    if not prepared and p.get('version') not in {'deterministic-corrections-v1', 'deterministic-corrections-v2', corrections.regression.VERSION, corrections.cited_passages.VERSION, corrections.financial_evidence.VERSION, 'targeted-remediation-v1', 'targeted-remediation-v2', VERSION}:
        raise ValueError('A stopped corrections or remediation seed is required')
    for item in p['code']:
        if base.sha(item['path']) != item['sha256']: raise ValueError('Seed verifier code changed')
    verifier_name = ('earnings_passage_pipeline.py' if prepared else
                     'earnings_remediation.py' if p['version'].startswith('targeted-remediation-') else 'earnings_corrections.py')
    code = Path(next(x['path'] for x in p['code'] if x['path'].endswith('/' + verifier_name))).parent.parent
    result = subprocess.run([sys.executable, '-c', EXPORT, str(seed)], cwd=code,
                            env={**os.environ, 'PYTHONPATH': str(code)}, check=True, capture_output=True, text=True)
    exported = json.loads(result.stdout)
    if exported['status'] not in STOPPED:
        raise ValueError('Seed must be conclusively stopped, not accepted or uncertain')
    return p, exported


def context_policy(value):
    policy = value.get('review_context_policy')
    if policy is None:
        return None
    from . import earnings_review_policy as rp
    expected = {'version': rp.VERSION, **rp.LIMITS}
    if (not isinstance(policy, dict) or set(policy) != set(expected) | {'authorization', 'token_authorization'}
            or any(policy.get(k) != v for k, v in expected.items())
            or any(not isinstance(policy.get(k), str) or not policy[k].strip()
                   for k in ('authorization', 'token_authorization'))
            or value.get('max_tokens') is not None):
        raise ValueError('Explicit complete-source context and uncapped-token authority required')
    return policy


def _authorization(value, seed, plan, output):
    names = ('kind', 'enabled', 'authorization_id', 'source_protocol_sha256',
             'first_plan_sha256', 'max_review_attempts', 'max_tokens', 'reason', 'output_path')
    if isinstance(value, dict) and 'budget_reference_jobs' in value:
        names += ('budget_reference_jobs',)
        refs = value['budget_reference_jobs']
        if (not isinstance(refs, list) or not 1 <= len(refs) <= 12 or
                any(not isinstance(x, str) or not Path(x).is_absolute() for x in refs) or len(set(refs)) != len(refs)):
            raise ValueError('Distinct absolute source review budget references required')
    if isinstance(value, dict) and 'review_context_policy' in value:
        names += ('review_context_policy',)
    corrections.fields(value, names, 'authorization')
    policy = context_policy(value)
    if value['kind'] != 'targeted_remediation' or value['enabled'] is not True:
        raise ValueError('Explicit targeted remediation authorization required')
    if value['source_protocol_sha256'] != base.sha(seed/'protocol.json') or value['first_plan_sha256'] != base.digest(plan):
        raise ValueError('Authorization binds a different seed or plan')
    if not isinstance(value['output_path'], str) or not Path(value['output_path']).is_absolute() or Path(value['output_path']).resolve() != output:
        raise ValueError('Authorization binds a different edition path')
    if type(value['max_review_attempts']) is not int or value['max_review_attempts'] not in (1, 2):
        raise ValueError('One or two explicitly authorized review attempts required')
    if policy is None and (type(value['max_tokens']) is not int or value['max_tokens'] <= 0):
        raise ValueError('Positive explicit remediation token budget required')
    for key in ('authorization_id', 'reason'): legacy.check_text(value[key], key)


def seed_bindings(seed, old):
    bindings = dict(old.get('source_bindings', {}))
    # Prepared editions inherit authenticated preparer jobs outside their own
    # directory. Preserve their bytes and exclude those sessions from new review.
    for name, digest in old.get('prepared_recovery', {}).get('bindings', {}).items():
        if name in bindings and bindings[name] != digest:
            raise ValueError('Conflicting inherited source binding')
        if base.sha(name) != digest:
            raise ValueError('Prepared ancestry source changed')
        bindings[name] = digest
    for p in seed.rglob('*'):
        if p.is_symlink(): raise ValueError('Seed symlinks are forbidden')
        if p.is_file() and not p.name.startswith('.'): bindings[str(p)] = base.sha(p)
    prior_sessions = []
    for name in bindings:
        if Path(name).name == 'execution.json':
            sid = base.read(name).get('session', {}).get('id')
            if sid: prior_sessions.append(sid)
    return bindings, sorted(set(prior_sessions))



def _source_bundle(source_protocol):
    """Replay original reviewed attribution before validating/reporting a derivative."""
    bundle = evidence.load_bundle(source_protocol['evidence_manifest'])
    catalog = passages.catalog(bundle['manifest'])
    corrections.qa_grounding.attach(None, source_protocol, bundle, catalog)
    if source_protocol.get('prepared_recovery'):
        from research import earnings_prepared_recovery
        bundle, _, _, _ = earnings_prepared_recovery.apply(source_protocol, bundle, catalog)
    return bundle, catalog


def initialize(seed, output, plan, authorization):
    seed = Path(seed).resolve(); root = Path(output).resolve()
    if root == seed or root.is_relative_to(seed) or root.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('New private sibling remediation directory required')
    _authorization(authorization, seed, plan, root)
    old, exported = export_seed(seed)
    snapshot = exported['snapshot']
    if set(snapshot['artifacts']) != {'financial', 'retrieval', 'analysis'} or not snapshot['findings']:
        raise ValueError('Complete stopped candidate and unresolved findings required')
    if root.exists() and any(root.iterdir()): raise ValueError('New remediation directory must be empty')
    bindings, prior_sessions = seed_bindings(seed, old)
    references = authorization.get('budget_reference_jobs')
    calibration = (corrections.budget.review_calibration(references, bindings, MODEL, verify_job)
                   if references else None)
    names = list(Path(__file__).parent.glob('earnings_*.py')) + [Path(__file__).with_name('earnings_mixed_prime.mjs')]
    protocol = {'version': VERSION, 'seed': str(seed), 'source_protocol': exported['source_protocol'],
                'source_bindings': bindings, 'source_code': old['code'] + old.get('source_code', []),
                'code': [{'path': str(p), 'sha256': base.sha(p)} for p in names],
                'authorization_sha256': base.digest(authorization), 'initial_sha256': base.digest(snapshot),
                'history': {k: exported[k] for k in ('status', 'prior_rounds', 'prior_tokens')},
                'excluded_session_ids': sorted(set(prior_sessions)), 'model': list(MODEL),
                'max_review_attempts': authorization['max_review_attempts'], 'max_tokens': authorization['max_tokens'], 'max_prompt_chars': MAX_PROMPT_CHARS}
    policy = context_policy(authorization)
    if policy is not None:
        protocol.update(review_context_policy=policy, max_prompt_chars=policy['prompt_characters'])
    if references:
        protocol.update(budget_reference_jobs=references, budget_calibration=calibration)
    # Validate the plan against original evidence before creating any edition.
    sp = protocol['source_protocol']; bundle, catalog = _source_bundle(sp)
    candidate = apply(snapshot, plan, bundle, catalog)
    root.mkdir(parents=True, exist_ok=True)
    repair.write(root/'authorization.json', authorization); repair.write(root/'initial.json', snapshot)
    repair.write(root/'protocol.json', protocol)
    _stage(root, 0, snapshot, plan, candidate, bundle, catalog)
    return {'status': 'pending', 'review_attempt': 0, 'historical_usage': protocol['history']}


def load(output):
    root = Path(output).resolve(); p = base.read(root/'protocol.json'); auth = base.read(root/'authorization.json')
    if p['version'] != VERSION or p['model'] != list(MODEL) or p['max_review_attempts'] not in (1, 2) or p['max_prompt_chars'] != (context_policy(auth) or {}).get('prompt_characters', MAX_PROMPT_CHARS):
        raise ValueError('Remediation policy changed')
    if base.digest(auth) != p['authorization_sha256'] or base.digest(base.read(root/'initial.json')) != p['initial_sha256']:
        raise ValueError('Remediation authorization or initial snapshot changed')
    _authorization(auth, Path(p['seed']), base.read(root/'attempts/0/plan.json'), root)
    if p.get('review_context_policy') != context_policy(auth):
        raise ValueError('Remediation review context authority changed')
    if p['max_tokens'] != auth['max_tokens'] or p['max_review_attempts'] != auth['max_review_attempts']:
        raise ValueError('Remediation budget changed')
    for c in p['code']:
        if base.sha(c['path']) != c['sha256'] or base.sha(Path(__file__).parent/Path(c['path']).name) != c['sha256']:
            raise ValueError('Remediation code changed')
    for c in p['source_code'] + p['source_protocol']['code']:
        if base.sha(c['path']) != c['sha256']: raise ValueError('Original verifier code changed')
    for name, h in p['source_bindings'].items():
        if base.sha(name) != h: raise ValueError('Original seed or source changed')
    references = auth.get('budget_reference_jobs')
    if references:
        expected = corrections.budget.review_calibration(references, p['source_bindings'], MODEL, verify_job)
        if p.get('budget_reference_jobs') != references or p.get('budget_calibration') != expected:
            raise ValueError('Authenticated review budget calibration changed')
    elif 'budget_reference_jobs' in p or 'budget_calibration' in p:
        raise ValueError('Unapproved review budget calibration')
    old, exported = export_seed(Path(p['seed']))
    expected_bindings, expected_sessions = seed_bindings(Path(p['seed']), old)
    if (p['source_bindings'] != expected_bindings or p['excluded_session_ids'] != expected_sessions
            or p['source_code'] != old['code'] + old.get('source_code', [])
            or p['source_protocol'] != exported['source_protocol']
            or p['history'] != {k: exported[k] for k in ('status', 'prior_rounds', 'prior_tokens')}
            or p['initial_sha256'] != base.digest(exported['snapshot'])):
        raise ValueError('Derived seed provenance differs from original authenticated replay')
    sp = p['source_protocol']
    for name, h in ((sp['case_path'], sp['case_sha256']), (sp['writing_standard'], sp['writing_sha256']),
                    (sp['evidence_manifest'], sp['evidence_sha256'])):
        if base.sha(name) != h: raise ValueError('Original evidence or writing changed')
    bundle, catalog = _source_bundle(sp)
    return p, bundle, catalog, Path(sp['writing_standard']).read_text()


def _stage(root, number, before, plan, candidate, bundle, catalog):
    folder = root/'attempts'/str(number)
    repair.write(folder/'before.json', before); repair.write(folder/'plan.json', plan)
    repair.write(folder/'candidate.json', candidate)
    legacy.immutable_text(folder/'candidate.html', corrections.rendered(candidate, bundle, catalog))


def prompt(before, plan, candidate, bundle, catalog, writing, extra_scope_ids=(), review_context_policy=None):
    return corrections.prompt('review', before, bundle, catalog, writing, plan, candidate,
                              extra_scope_ids=extra_scope_ids, financial_context_version=context.FINANCIAL_CONTEXT_VERSION,
                              review_context_policy=review_context_policy) + (
        '\nEXPLICIT USER-DIRECTED REMEDIATION EDITION\n'
        'This separately authorized edition preserves the exhausted historical run and accepted evidence. '
        'No author model will rewrite approved deterministic changes. Review the complete rendered report, '
        'all corrections and their repeated occurrences together. Upstream metadata edits require checking '
        'their downstream implications. Request original evidence only where the supplied context is insufficient. '
        'Formatting does not require re-extraction of unchanged observations. Mechanical checks alone never grant acceptance.')


def _replay(root, p, bundle, catalog, writing):
    state = base.read(root/'initial.json'); tokens = 0; seen_sessions = set(p['excluded_session_ids']); candidates = set()
    for number in range(p['max_review_attempts']):
        folder = root/'attempts'/str(number)
        if not (folder/'plan.json').exists():
            return {'status': 'awaiting_plan', 'state': state, 'tokens': tokens, 'review_attempts': number}
        plan = base.read(folder/'plan.json'); candidate = apply(state, plan, bundle, catalog)
        if base.read(folder/'before.json') != state or base.read(folder/'candidate.json') != candidate:
            raise ValueError('Staged remediation bytes changed')
        candidate_digest = base.digest({'artifacts': candidate['artifacts'], 'format': candidate['format']})
        if candidate_digest in candidates: raise ValueError('Unchanged candidate cannot be reviewed again')
        candidates.add(candidate_digest)
        if (folder/'candidate.html').read_text() != corrections.rendered(candidate, bundle, catalog):
            raise ValueError('Rendered remediation candidate changed')
        bindings = {'protocol_sha256': base.sha(root/'protocol.json'), 'authorization_sha256': p['authorization_sha256'],
                    'attempt': number, 'role': 'review', 'before_sha256': base.digest(state),
                    'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan)}
        reviewed = corrections.replay_review(p.get('review_context_policy'),
            folder/'review', lambda extra: prompt(state, plan, candidate, bundle, catalog, writing, extra, p.get('review_context_policy')),
            bindings, MODEL, bundle, catalog, base.digest(candidate), base.digest(plan),
            seen_sessions, corrections.budget.remaining(p['max_tokens'], tokens), p['max_prompt_chars'], verify_job,
            admission_fn=(lambda text, remaining: corrections.budget.calibrated_admission(
                text, remaining, p['budget_calibration'])) if p.get('budget_reference_jobs') else None)
        tokens += reviewed['tokens']
        if reviewed['status'] != 'completed' and not reviewed.get('requires_adjudication'):
            return {**reviewed, 'state': state, 'tokens': tokens, 'review_attempts': number}
        result, job = reviewed['result'], reviewed['job']
        after, status = corrections.adjudicate(state, candidate, plan, result['content'], bundle, catalog)
        if reviewed['status'] != 'completed':
            substantive = {'verdict': result['content']['verdict'], 'validation': 'valid', 'outcome': status,
                           'approve_patch': result['content']['approve_patch'], 'output_path': str(job/'output.json'),
                           'output_sha256': base.sha(job/'output.json'), 'candidate_sha256': base.digest(candidate),
                           'plan_sha256': base.digest(plan)}
            return {**reviewed, 'state': state, 'tokens': tokens, 'review_attempts': number + 1,
                    'substantive_review': substantive,
                    'budget_compliance': corrections.budget.compliance(tokens, p['max_tokens'])}
        state = after
        decision = {'before_sha256': plan['snapshot_sha256'], 'candidate_sha256': base.digest(candidate),
                    'plan_sha256': base.digest(plan), 'review_output_sha256': base.sha(job/'output.json'),
                    'patch_applied': result['content']['approve_patch'], 'status': status, 'after': state}
        repair.write(folder/'decision.json', decision)
        if status != 'revise' or number + 1 == p['max_review_attempts']:
            if (root/'attempts'/str(number+1)/'plan.json').exists(): raise ValueError('Plan after terminal review')
            return {'status': 'accepted' if status == 'accepted' else 'blocked', 'state': state,
                    'tokens': tokens, 'review_attempts': number + 1}
    raise ValueError('Invalid remediation attempt state')


def stage_plan(output, plan):
    root = Path(output).resolve()
    with (root/'.coordinator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        p, b, c, w = load(root); progress = _replay(root, p, b, c, w)
        if progress['status'] != 'awaiting_plan' or progress['review_attempts'] != 1:
            raise ValueError('A second plan requires an independently reviewed revise disposition')
        candidate = apply(progress['state'], plan, b, c)
        first = base.read(root/'attempts/0/candidate.json')
        if candidate['artifacts'] == first['artifacts'] and candidate['format'] == first['format']:
            raise ValueError('Unchanged candidate cannot be retried')
        _stage(root, 1, progress['state'], plan, candidate, b, c)
        return {'status': 'pending', 'review_attempt': 1}


def advance(output, execute=False):
    root = Path(output).resolve()
    with (root/'.coordinator.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {'status': 'running'}
        p, b, c, w = load(root); progress = _replay(root, p, b, c, w)
        if execute and progress['status'] == 'pending':
            run_role(progress['job'], progress['prompt'], *MODEL, progress['bindings'], timeout=1200)
            progress = _replay(root, p, b, c, w)
        summary = {k: v for k, v in progress.items() if k not in ('state', 'prompt', 'bindings', 'job', 'result')}
        if progress['status'] == 'accepted':
            repair.render(root/'report.html', {**progress['state'], 'status': 'accepted'}, b, c)
            repair.write(root/'result.json', {**summary, 'state': progress['state'],
                        'history': p['history'], 'authorization_sha256': p['authorization_sha256'],
                        'html_sha256': base.sha(root/'report.html')})
        elif (root/'result.json').exists():
            raise ValueError('Accepted result does not reproduce')
        return summary


def verify(output):
    return advance(output, execute=False)
