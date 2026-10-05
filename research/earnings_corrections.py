"""Source-bound, reviewer-approved deterministic report corrections.

Models propose and assess declarative patches. Python copies approved data, applies
exact prose replacements, and renders the reviewed result without a rewriting agent.
Numeric observations, selected quotations and original experiments are immutable.
"""
from __future__ import annotations
import argparse
import copy
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from research import earnings_experiment as base
from research import earnings_report_repair as repair
from research import earnings_passage_pipeline as pipe
from research import earnings_mixed_pipeline as legacy
from research import earnings_compact_evidence as evidence
from research import earnings_passages as passages
from research import earnings_repair_context as context
from research import earnings_repair_review as review_loop
from research.earnings_mixed_runner import run_role, verify_job

VERSION = 'deterministic-corrections-v1'
MODEL = ('gpt-6.1-sol', 'medium')
EMPTY_FORMAT = {'rows': {}, 'basis': {'text': '', 'citations': []}}


def fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(label + ': exact fields required: ' + ', '.join(names))


def registry(snapshot, bundle):
    """Opaque IDs identify allowlisted locations; the snapshot prevents index drift."""
    targets = {}
    def add(path, kind, value, citations=None):
        key = 'target-' + base.digest(path)[:20]
        targets[key] = {'path': path, 'kind': kind, 'value': value,
                        'expected_sha256': base.digest(value), 'citation_path': citations}
    a = snapshot['artifacts']['analysis']
    add(['artifacts', 'analysis', 'opening'], 'text', a['opening'], ['artifacts', 'analysis', 'opening_citations'])
    for i, item in enumerate(a['findings']):
        for field in ('heading', 'text'):
            add(['artifacts', 'analysis', 'findings', i, field], 'text', item[field], ['artifacts', 'analysis', 'findings', i, 'citations'])
        add(['artifacts', 'analysis', 'findings', i, 'quotes'], 'quotes', item['quotes'])
    for i, item in enumerate(a['next_tests']):
        add(['artifacts', 'analysis', 'next_tests', i, 'text'], 'text', item['text'], ['artifacts', 'analysis', 'next_tests', i, 'citations'])
    for key in repair.row_catalog(snapshot['artifacts']['financial'], bundle):
        add(['format', 'rows', key], 'row', snapshot['format']['rows'].get(key))
    add(['format', 'basis'], 'basis', snapshot['format']['basis'])
    add(['format', 'layout'], 'layout', snapshot['format'].get('layout'))
    # Interpretive metadata may be corrected without regenerating observations
    # or selected quotations. All repeated uses are inventoried for the batch.
    for i, item in enumerate(snapshot['artifacts']['financial']['context']):
        add(['artifacts','financial','context',i,'text'], 'text', item['text'], ['artifacts','financial','context',i,'citations'])
    for i, text in enumerate(snapshot['artifacts']['financial']['gaps']):
        add(['artifacts','financial','gaps',i], 'text', text)
    retrieval = snapshot['artifacts']['retrieval']
    for i, item in enumerate(retrieval['document_findings']):
        add(['artifacts','retrieval','document_findings',i,'text'], 'text', item['text'], ['artifacts','retrieval','document_findings',i,'citations'])
    for i, item in enumerate(retrieval['exchange_coverage']):
        for field in ('question','answer','consequence'):
            add(['artifacts','retrieval','exchange_coverage',i,field], 'text', item[field])
    sources = {}
    for i, note in enumerate(snapshot['artifacts']['financial']['context']):
        key = 'context-' + base.digest([i, note])[:20]
        sources[key] = {'value': note, 'sha256': base.digest(note),
                        'parent_sha256': base.digest(note), 'start': 0, 'end': len(note['text'])}
        # Sentence-sized exact spans let code copy one useful comparison without
        # appending an entire context sheet. Offsets are Python Unicode indices.
        cuts = [0] + [m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])', note['text'])] + [len(note['text'])]
        for start, end in zip(cuts, cuts[1:]):
            while end > start and note['text'][end-1].isspace(): end -= 1
            if start == 0 and end == len(note['text']): continue
            selected = {'text': note['text'][start:end], 'citations': note['citations']}
            sources[key + '-span-' + str(start)] = {
                'value': selected, 'sha256': base.digest(selected),
                'parent_sha256': base.digest(note), 'start': start, 'end': end}
    return {'targets': targets, 'context_sources': sources,
            'financial_rows': repair.row_catalog(snapshot['artifacts']['financial'], bundle)}


def get(value, path):
    for part in path: value = value[part]
    return value


def put(value, path, replacement):
    get(value, path[:-1])[path[-1]] = copy.deepcopy(replacement)


def claim(value, bundle, catalog):
    legacy.check_text(value['reason'], 'specific source-backed reason')
    legacy.check_ids(value['citations'], legacy.ids_for(bundle), 'evidence citations')
    legacy.check_ids(value['passage_ids'], {p['passage_id'] for p in catalog['passages']}, 'original passages')


def apply(snapshot, plan, bundle, catalog):
    """Pure atomic staging: a failed operation returns no partially changed state."""
    fields(plan, ('snapshot_sha256', 'operations', *(['claim_groups'] if 'claim_groups' in plan else [])), 'plan')
    if plan['snapshot_sha256'] != base.digest(snapshot): raise ValueError('Stale snapshot')
    if not isinstance(plan['operations'], list) or len(plan['operations']) > 24:
        raise ValueError('At most 24 operations per round')
    index = registry(snapshot, bundle); out = copy.deepcopy(snapshot); seen = set(); ids = set()
    common = {'id', 'target_id', 'expected_sha256', 'op', 'citations', 'passage_ids', 'reason'}
    for op in plan['operations']:
        if not isinstance(op, dict): raise ValueError('Operation must be an object')
        extra = {'source_id', 'source_sha256', 'old_text'} if op.get('op') == 'copy_context' else {'value'}
        if op.get('op') == 'replace_text' and 'old_text' in op:
            extra = {'value', 'old_text'}
        fields(op, common | extra, 'operation')
        legacy.check_text(op['id'], 'operation ID')
        if op['id'] in ids or op['target_id'] in seen: raise ValueError('Duplicate operation or conflicting target')
        ids.add(op['id']); seen.add(op['target_id'])
        if op['target_id'] not in index['targets']: raise ValueError('Target is outside correction allowlist')
        target = index['targets'][op['target_id']]
        if op['expected_sha256'] != target['expected_sha256']: raise ValueError('Stale target')
        claim(op, bundle, catalog)
        citations = op['citations']; kind = target['kind']; original = target['value']
        if op['op'] == 'copy_context' and kind in ('text', 'basis'):
            source = index['context_sources'].get(op['source_id'])
            if not source or source['sha256'] != op['source_sha256']: raise ValueError('Stale or unknown context source')
            old = op['old_text']; original_text = original['text'] if kind == 'basis' else original
            if not isinstance(old, str):
                raise ValueError('copy_context requires exact string old_text')
            if old == '':
                if original_text != '':
                    raise ValueError('copy_context empty old_text requires an exactly empty target')
                value = source['value']['text']
            else:
                start = original_text.find(old)
                if start < 0 or original_text.find(old, start + 1) >= 0:
                    raise ValueError('copy_context requires one exact existing text span')
                value = original_text[:start] + source['value']['text'] + original_text[start + len(old):]
            citations = list(dict.fromkeys(citations + source['value']['citations']))
            if kind == 'basis':
                if len(value) > 240: raise ValueError(f'display.text: limit 240 characters; received {len(value)}')
                value = {'text': value, 'citations': list(dict.fromkeys(original['citations'] + citations))}
            elif len(value) > 4000:
                raise ValueError('Context copy result exceeds 4000 characters')
        elif op['op'] == 'replace_text' and kind == 'text':
            value = op['value']
            if 'old_text' in op:
                old = op['old_text']
                if not isinstance(old, str) or not old or not isinstance(value, str):
                    raise ValueError('replace_text span requires nonempty old_text and string value')
                start = original.find(old)
                # Count overlapping matches too: 'aa' occurs twice in 'aaa'.
                if start < 0 or original.find(old, start + 1) >= 0:
                    raise ValueError('replace_text requires one exact existing text span')
                value = original[:start] + value + original[start + len(old):]
            legacy.check_text(value, 'replacement text')
            if len(value) > 4000: raise ValueError('Replacement result exceeds 4000 characters')
        elif op['op'] == 'set_display' and kind in ('row', 'basis'):
            value = op['value']
            fields(value, ('label', 'dimensions') if kind == 'row' else ('text',), 'display value')
            limits = {'label': 160, 'dimensions': 200, 'text': 240}
            for key, text in value.items():
                if not isinstance(text, str) or len(text) > limits[key]:
                    raise ValueError(f'display.{key}: limit {limits[key]} characters; received {len(text) if isinstance(text, str) else "non-text"}')
            value = {**value, 'citations': citations}
        elif op['op'] == 'set_layout' and kind == 'layout':
            value = op['value']
            repair.validate_format({**out['format'], 'layout': value}, out['artifacts']['financial'], bundle)
        elif op['op'] == 'retain_quotes' and kind == 'quotes':
            value = op['value']
            if not isinstance(value, list) or any(q not in original for q in value): raise ValueError('Quotes can only be retained or deleted')
            # Preserve original order and multiplicity; no replacement quote generation.
            remaining = iter(original)
            if any(not any(q == item for item in remaining) for q in value): raise ValueError('Quotes must remain an ordered subsequence')
        else:
            raise ValueError('Unsupported operation for target kind')
        if value == original: raise ValueError('No-op correction')
        put(out, target['path'], value)
        if target['citation_path']:
            before = get(out, target['citation_path'])
            put(out, target['citation_path'], list(dict.fromkeys(before + citations)))
    for role in ('financial', 'retrieval', 'analysis'):
        pipe.validate(role, out['artifacts'][role], bundle, catalog)
    repair.validate_format(out['format'], out['artifacts']['financial'], bundle)
    if out['artifacts']['financial']['rows'] != snapshot['artifacts']['financial']['rows']:
        raise ValueError('Verified observations changed')
    normalized = copy.deepcopy(plan)
    for op in normalized['operations']:
        op['path'] = index['targets'][op['target_id']]['path']
    context.propagation_check(snapshot, out, normalized)
    return out


def adjudicate(before, candidate, plan, review, bundle, catalog):
    fields(review, ('candidate_sha256', 'plan_sha256', 'approve_patch', 'verdict', 'criteria', 'operations', 'resolutions', 'findings'), 'review')
    if review['candidate_sha256'] != base.digest(candidate) or review['plan_sha256'] != base.digest(plan):
        raise ValueError('Reviewer assessed different candidate or plan')
    if type(review['approve_patch']) is not bool or review['verdict'] not in ('pass', 'revise', 'blocked'):
        raise ValueError('Explicit patch approval and report verdict required')
    if not isinstance(review['criteria'], dict) or set(review['criteria']) != set(legacy.CRITERIA):
        raise ValueError('Complete report rubric required')
    for item in review['criteria'].values():
        fields(item, ('status', 'evidence'), 'criterion')
        if item['status'] not in ('pass', 'fail', 'unavailable'): raise ValueError('Invalid criterion status')
        legacy.check_text(item['evidence'], 'rubric evidence')
    decisions = review['operations']
    if not isinstance(decisions, list) or len(decisions) != len(plan['operations']) or {d.get('id') for d in decisions} != {o['id'] for o in plan['operations']}:
        raise ValueError('Reviewer must assess each operation once')
    for d in decisions:
        fields(d, ('id', 'approve', 'reason', 'citations', 'passage_ids'), 'operation decision')
        if type(d['approve']) is not bool: raise ValueError('Explicit operation decision required')
        claim(d, bundle, catalog)
    if review['approve_patch'] and not all(d['approve'] for d in decisions): raise ValueError('Atomic patch has rejected operation')
    pending = before['findings']; resolutions = review['resolutions']
    if not isinstance(resolutions, list) or len(resolutions) != len(pending) or {r.get('id') for r in resolutions} != {f['id'] for f in pending}:
        raise ValueError('Reviewer must adjudicate every pending finding once')
    unresolved = []
    for r in resolutions:
        fields(r, ('id', 'status', 'reason', 'citations', 'passage_ids'), 'resolution')
        claim(r, bundle, catalog)
        if r['status'] not in ('closed', 'withdrawn', 'open'): raise ValueError('Unknown resolution')
        if r['status'] == 'closed' and not review['approve_patch']: raise ValueError('Rejected edits cannot close findings')
        if r['status'] == 'open': unresolved.append(next(f for f in pending if f['id'] == r['id']))
    if not isinstance(review['findings'], list): raise ValueError('Findings must be a list')
    for f in review['findings']:
        fields(f, ('reason', 'citations', 'passage_ids'), 'new finding'); claim(f, bundle, catalog)
        item = {'id': repair.finding_id(f), 'finding': f}
        if item['id'] not in {x['id'] for x in unresolved}: unresolved.append(item)
    accepted = review['verdict'] == 'pass'
    if accepted and (not review['approve_patch'] or unresolved or any(c['status'] != 'pass' for c in review['criteria'].values())):
        raise ValueError('Acceptance requires approved exact patch, resolved findings and passing rubric')
    out = copy.deepcopy(candidate if review['approve_patch'] else before)
    out['findings'] = unresolved
    return out, 'accepted' if accepted else review['verdict']


def rendered(snapshot, bundle, catalog):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'report.html'
        repair.render(path, {**snapshot, 'status': 'pending'}, bundle, catalog)
        return path.read_text()


# Execute only this fixed verifier program from a source's hash-bound code checkout.
EXPORT = '''
import json,sys
from pathlib import Path
from research import earnings_experiment as b
from research import earnings_report_repair as r
from research import earnings_passage_pipeline as p
root=Path(sys.argv[1]); protocol=b.read(root/'protocol.json'); imported=None; spent_tokens=0
if protocol.get('version') == 'deterministic-corrections-v1':
    from research import earnings_corrections as c
    cp,bundle,catalog,writing=c.load(root)
    progress=c.replay(root,cp,bundle,catalog,writing)
    snapshot=progress['state']; sp=cp['source_protocol']; used_rounds=progress['round']+(0 if cp.get('new_experiment') else cp.get('prior_rounds',0)); spent_tokens=progress['tokens']+cp.get('inherited_tokens',0)
    if len(sys.argv)>2 and sys.argv[2]=='reuse':
        if not ((progress['status'] in ('pending','budget_exhausted','prompt_too_large') and progress.get('role')=='review') or progress['status']=='invalid_patch'):
            raise ValueError('Only an authenticated unreviewed proposal may be reused')
        job=root/'rounds'/str(progress['round'])/'propose'
        imported={'job':str(job),'output_sha256':b.sha(job/'output.json')}
elif protocol.get('version') == r.VERSION:
    _,bundle,catalog,writing=r.load(root)
    state,usage,jobs=r.replay(root,bundle,catalog,writing)
    sp=b.read(Path(protocol['seed'])/'protocol.json')
    findings=[{'id':f['id'],'finding':f['finding']} for f in r.open_findings(state)]
    snapshot={'artifacts':state['artifacts'],'format':state['format'],'findings':findings}
    used_rounds=max(0,state['round']-1)
else:
    p.verify(root)
    sp=protocol; artifacts=b.read(root/'artifacts.json'); review=b.read(root/'review.json')
    snapshot={'artifacts':artifacts,'format':{'rows':{},'basis':{'text':'','citations':[]}},'findings':[{'id':r.finding_id(f),'finding':f} for f in review['findings']]}
    used_rounds=b.read(root/'result.json')['correction_rounds']
print(json.dumps({'snapshot':snapshot,'source_protocol':sp,'used_rounds':used_rounds,'imported_proposal':imported,'spent_tokens':spent_tokens}))
'''


def initialize(seed, output, max_rounds=2, max_tokens=600000, new_experiment=False, reuse_proposal=False):
    seed = Path(seed).resolve(); root = Path(output).resolve()
    if root == seed or root.is_relative_to(seed) or root.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Use a new private directory outside code and the seed')
    if type(max_rounds) is not int or not 1 <= max_rounds <= 2 or type(max_tokens) is not int or max_tokens <= 0:
        raise ValueError('One or two rounds and a positive token budget required')
    sp = base.read(seed/'protocol.json')
    for record in sp['code']:
        if base.sha(record['path']) != record['sha256']: raise ValueError('Frozen source code changed')
    code = Path(next(c['path'] for c in sp['code'] if c['path'].endswith('/earnings_passage_pipeline.py'))).parent.parent
    process = subprocess.run([sys.executable, '-c', EXPORT, str(seed), 'reuse' if reuse_proposal else 'fresh'], cwd=code, env={**os.environ, 'PYTHONPATH': str(code)}, check=True, capture_output=True, text=True)
    exported = json.loads(process.stdout); snapshot = exported['snapshot']; sp = exported['source_protocol']
    if reuse_proposal and not exported['imported_proposal']: raise ValueError('No reusable staged proposal')
    remaining = max_rounds if new_experiment else min(max_rounds, 2-exported['used_rounds'])
    if remaining <= 0: raise ValueError('Prior correction budget exhausted; a separately authorized experiment requires --new-experiment')
    if set(snapshot['artifacts']) != {'financial', 'retrieval', 'analysis'}: raise ValueError('Complete prepared report required')
    if not snapshot['findings']: raise ValueError('No unresolved review findings')
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()): raise ValueError('New correction directory must be empty')
    # Bind every input/receipt of this immutable seed, plus transitive original seed.
    dirs = [seed]
    if base.read(seed/'protocol.json').get('seed'): dirs.append(Path(base.read(seed/'protocol.json')['seed']))
    bound = {str(f): base.sha(f) for d in dirs for f in d.rglob('*') if f.is_file() and not f.name.startswith('.')}
    seed_protocol = base.read(seed/'protocol.json')
    bound.update(seed_protocol.get('source_bindings', {}))
    names = [f for f in Path(__file__).parent.glob('earnings_*.py')] + [Path(__file__).with_name('earnings_mixed_prime.mjs')]
    protocol = {'version': VERSION, 'seed': str(seed), 'source_bindings': bound, 'source_protocol': sp,
                'initial_sha256': base.digest(snapshot), 'code': [{'path': str(f), 'sha256': base.sha(f)} for f in names],
                'model': list(MODEL), 'max_rounds': remaining, 'max_tokens': max_tokens, 'max_prompt_chars': 1500000, 'imported_proposal': exported['imported_proposal'],
                'source_code': seed_protocol['code'] + seed_protocol.get('source_code', []),
                'new_experiment': bool(new_experiment), 'prior_rounds': exported['used_rounds'],
                'inherited_tokens': 0 if new_experiment else exported['spent_tokens']}
    repair.write(root/'protocol.json', protocol); repair.write(root/'initial.json', snapshot)
    load(root)
    return {'status': 'pending', 'max_rounds': remaining, 'findings': len(snapshot['findings'])}


def load(root):
    p = base.read(root/'protocol.json')
    if p['version'] != VERSION or p['model'] != list(MODEL): raise ValueError('Correction protocol changed')
    for c in p['code']:
        if base.sha(c['path']) != c['sha256'] or base.sha(Path(__file__).parent/Path(c['path']).name) != c['sha256']:
            raise ValueError('Correction code changed')
    for c in p.get('source_code', []) + p['source_protocol']['code']:
        if base.sha(c['path']) != c['sha256']: raise ValueError('Original verifier code changed')
    for path, digest in p['source_bindings'].items():
        if base.sha(path) != digest: raise ValueError('Original seed changed')
    if base.digest(base.read(root/'initial.json')) != p['initial_sha256']: raise ValueError('Initial snapshot changed')
    sp = p['source_protocol']
    for path, digest in [(sp['case_path'], sp['case_sha256']), (sp['writing_standard'], sp['writing_sha256']), (sp['evidence_manifest'], sp['evidence_sha256'])]:
        if base.sha(path) != digest: raise ValueError('Original source binding changed')
    bundle = evidence.load_bundle(sp['evidence_manifest']); catalog = passages.catalog(bundle['manifest'])
    if base.digest(catalog) != base.digest(base.read(Path(sp['evidence_manifest']).parent.parent/'passages.json')):
        raise ValueError('Original passages changed')
    return p, bundle, catalog, Path(sp['writing_standard']).read_text()


def prompt(role, snapshot, bundle, catalog, writing, plan=None, candidate=None, feedback=None, extra_scope_ids=()):
    common = legacy.COMMON + '\nWRITING STANDARD\n' + writing
    if role == 'propose':
        instruction = '''Propose a bounded correction plan. Patch only allowlisted metadata; never regenerate financial observations or retrieval selections. Prefer copy_context when an existing financial context note or sentence-sized context source supplies the correction: code copies its exact text and citations. For interpretive prose use an exact replace_text patch, preserving unaffected claims. Whole-artifact regeneration is forbidden. A proposal is not approval. Prior findings can be mistaken; inspect original evidence and leave disputed changes out for independent adjudication. Return only {"snapshot_sha256":"provided hash","operations":[OP,...],"claim_groups":[GROUP,...]}. At most 24 operations, one per target. Each OP has id (unique), target_id, expected_sha256, op, reason, citations (source IDs), passage_ids (original P IDs). copy_context targets text or basis and also has source_id, source_sha256 and old_text. A nonempty old_text must be one unique exact existing substring to replace. Empty old_text is allowed only to initialize an exactly empty target (or empty basis.text); code copies the hash-bound context source exactly, never inserts into nonempty text. The entire copied result must fit 4000 characters for text or 240 characters for basis. replace_text targets text only and has exactly one of two payloads: {value} replaces the entire hashed target, or {old_text,value} replaces one unique nonempty exact substring of that same target, preserving its prefix and suffix. With old_text, value may be empty to delete that span, but the resulting target must remain nonempty. The entire resulting target is limited to 4000 characters. The target hash is always checked; old_text is never ignored or treated as documentation. No other payload fields are allowed. set_display has value:{label,dimensions} for a row (max160/200 characters) or value:{text} for basis (max240 characters); code attaches citations. retain_quotes has value (ordered subset of original quote selections, possibly empty). No added quotes, source facts, executable text or status changes. Preserve concise useful commentary and documented non-answers; prune invented contrasts and redundant cautions. Empty operations allows a source-backed mistaken finding to be withdrawn by the reviewer.'''
        data = {'snapshot_sha256': base.digest(snapshot), 'pending_findings': snapshot['findings'],
                'registry': registry(snapshot, bundle), 'prepared_retrieval': snapshot['artifacts']['retrieval'],
                'previous_review': feedback}
        data['occurrence_inventory'] = context.occurrence_inventory(snapshot)
        instruction += (' Batch ALL pending corrections before returning. Correct repeated financial claims and qualifiers in every affected metadata/report field together. '
                        'Numerical observations and quote selections remain immutable. Include claim_groups for factual/qualifier changes: '
                        '{id,aliases:[case-insensitive exact phrases],required_paths:[changed field paths],unchanged:[{path,reason}]}. '
                        'Every matched existing occurrence must be patched or explicitly justified unchanged. Editorial-only changes need no claim group. '
                        'Use set_layout with an explicit supported format.layout object for presentation, retaining every numeric observation in visible or expandable detail. '
                        'A complete list of pending findings is provided; do not fix them one at a time.')
        # Only cited evidence is needed to author a bounded repair.
        ids = set(snapshot['artifacts']['retrieval']['selected_document_ids'])
        def collect(value):
            if isinstance(value, dict):
                ids.update(value.get('citations', []))
                for v in value.values(): collect(v)
            elif isinstance(value, list):
                for v in value: collect(v)
        collect(snapshot)
        slices = evidence.source_slices(bundle['manifest'], sorted(ids))
        relevant = repair.passages_for_sources(catalog, ids, slices)
        # Provenance stays in the immutable catalog. Repeating paths and hashes
        # for thousands of tiny spans costs far more than the source text itself.
        data['original_passages'] = {'columns': ['passage_id', 'scope_id', 'text'],
                                     'rows': [[p['passage_id'], p['scope_id'], p['text']] for p in relevant]}

    else:
        instruction = '''You are the independent final acceptance authority. Assess the EXACT staged report and each deterministic patch against original sources. Prior reviewer findings and proposed context notes are fallible claims. Verify periods, issuer, question/answer attribution, accounting basis, figures, citations, material coverage and concise writing. No hidden author reasoning is supplied. Code will apply approved operations unchanged; no author rewrites follow you. Distinguish patch approval from whole-report acceptance. Reject the whole atomic bundle if any operation is unsupported; it will not persist. Return only {candidate_sha256,plan_sha256,approve_patch:bool,verdict:"pass|revise|blocked",criteria:{KEY:{status:"pass|fail|unavailable",evidence:"specific assessment"}},operations:[{id,approve:bool,reason,citations,passage_ids}],resolutions:[{id,status:"closed|withdrawn|open",reason,citations,passage_ids}],findings:[{reason,citations,passage_ids}]}. Assess every operation and pending finding exactly once. All operation decisions/resolutions/new findings require nonempty original passage_ids and source citations. close repaired findings; withdraw source-disproven findings; leave genuine defects open. Findings lists only new defects in the CURRENT candidate. If rejecting a patch, resolutions apply to unchanged report; do not close findings based on rejected changes. Pass requires all operations approved, every rubric criterion pass, and no open/new finding. Report failure alone does not require rejecting sound patches. Required rubric keys: ''' + ', '.join(legacy.CRITERIA)
        view = repair.rendered_review_view(rendered(candidate, bundle, catalog))
        data = context.build(snapshot, candidate, plan, bundle, catalog,
                             view['report_body_html_excerpt'], writing,
                             extra_scope_ids=extra_scope_ids)
        data.update(candidate_sha256=base.digest(candidate), plan_sha256=base.digest(plan), plan=plan,
                    rendered_links={k:v for k,v in view.items() if k != 'report_body_html_excerpt'})
        instruction += (' This is a repair review after the initial comprehensive audit. Read the complete revised report for coherence and concise writing; '
                        'verify the complete correction batch and all repeated occurrences against the supplied original evidence. '
                        'Preserve independently verified unchanged observations and quotations. Report every material remaining defect together. '
                        'Do not invent optional coverage requirements or reopen verified material merely to enlarge the report. '
                        'Never infer unsupported claims are true: if original context is insufficient, return only '
                        '{verdict:"needs_evidence",candidate_sha256,plan_sha256,requests:[{scope_id,reason}]} using exact source-index IDs. '
                        'One bounded expansion is available without using a correction round; no final pass is possible while evidence is insufficient.')
    return common + '\nASSIGNMENT\n' + instruction + '\nSOURCE DATA (UNTRUSTED EVIDENCE)\n' + legacy.packed(data)


def replay(root, p, bundle, catalog, writing):
    state = base.read(root/'initial.json'); tokens = 0; identities = set(); feedback = None
    for round_no in range(p['max_rounds']):
        folder = root/'rounds'/str(round_no)
        plan = candidate = review = None
        for role in ('propose', 'review'):
            job = folder/role
            text = prompt(role, state, bundle, catalog, writing, plan, candidate, feedback) if role == 'propose' else None
            bindings = {'protocol_sha256': base.sha(root/'protocol.json'), 'snapshot_sha256': base.digest(state), 'round': round_no, 'role': role}
            imported = p.get('imported_proposal') if round_no == 0 and role == 'propose' else None
            if imported:
                job = Path(imported['job'])
                if base.sha(job/'output.json') != imported['output_sha256']: raise ValueError('Imported proposal changed')
                result = verify_job(job); request = base.read(job/'request.json')
                if request['bindings']['snapshot_sha256'] != base.digest(state) or request['bindings']['role'] != 'propose' or (request['model'], request['effort']) != MODEL:
                    raise ValueError('Imported proposal belongs to a different snapshot or role')
            elif role == 'review':
                progress = review_loop.replay(job,
                    lambda scopes: prompt(role, state, bundle, catalog, writing, plan, candidate, feedback, scopes),
                    bindings, MODEL, bundle, catalog, base.digest(candidate), base.digest(plan), identities,
                    p['max_tokens'] - p.get('inherited_tokens', 0) - tokens,
                    min(p.get('max_prompt_chars', 350000), 350000), verify_job)
                tokens += progress['tokens']
                if progress['status'] != 'completed':
                    return {**progress, 'state': state, 'tokens': tokens, 'round': round_no, 'role': role}
                result = progress['result']; job = progress['job']
            else:
                if not (job/'output.json').exists():
                    status = ('launch_uncertain' if (job/'request.json').exists() else
                              'budget_exhausted' if tokens + p.get('inherited_tokens', 0) >= p['max_tokens'] else
                              'prompt_too_large' if len(text) > p.get('max_prompt_chars', 750000) else 'pending')
                    return {'status': status, 'state': state, 'tokens': tokens, 'round': round_no, 'role': role, 'prompt': text, 'bindings': bindings, 'job': job}
                result = verify_job(job); request = base.read(job/'request.json')
                if request['bindings'] != bindings or (request['model'], request['effort']) != MODEL or (job/'prompt.txt').read_text() != text:
                    raise ValueError('Job differs from exact source-bound correction request')
            if role == 'propose':
                sid = result['receipt']['session']['id']
                if sid in identities: raise ValueError('Independent fresh sessions required')
                identities.add(sid)
                if not imported: tokens += result['receipt']['session']['usage']['totalTokens']
            if role == 'propose':
                plan = result['content']
                try: candidate = apply(state, plan, bundle, catalog)
                except (ValueError, KeyError, TypeError) as exc:
                    return {'status': 'invalid_patch', 'state': state, 'tokens': tokens, 'round': round_no, 'error': str(exc)}
                repair.write(folder/'plan.json', plan); repair.write(folder/'candidate.json', candidate)
                legacy.immutable_text(folder/'candidate.html', rendered(candidate, bundle, catalog))
            else:
                review = result['content']
                try: after, status = adjudicate(state, candidate, plan, review, bundle, catalog)
                except (ValueError, KeyError, TypeError) as exc:
                    return {'status': 'invalid_review', 'state': state, 'tokens': tokens, 'round': round_no, 'error': str(exc)}
                repair.write(folder/'decision.json', {'before_sha256': base.digest(state), 'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan), 'review_output_sha256': base.sha(job/'output.json'), 'review_job': str(job.relative_to(root)), 'patch_applied': review['approve_patch'], 'after': after})
                state = after; feedback = review
                if status in ('accepted', 'blocked'):
                    return {'status': status, 'state': state, 'tokens': tokens, 'round': round_no+1}
    return {'status': 'blocked', 'state': state, 'tokens': tokens, 'round': p['max_rounds'], 'error': 'Correction round limit reached'}


def verify(output):
    root = Path(output).resolve(); p, b, c, w = load(root); result = replay(root, p, b, c, w)
    summary = {k: v for k, v in result.items() if k not in ('state', 'prompt', 'bindings', 'job', 'result')}
    if result['status'] != 'pending' and result['status'] != 'launch_uncertain':
        repair.render(root/'report.html', {**result['state'], 'status': result['status']}, b, c)
        out = {**summary, 'state': result['state'], 'html_sha256': base.sha(root/'report.html'),
               'preserved': {r: base.digest(result['state']['artifacts'][r]) for r in ('financial', 'retrieval')}}
        repair.write(root/'result.json', out)
    return summary


def advance(output):
    root = Path(output).resolve()
    with (root/'.coordinator.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {'status': 'running'}
        p, b, c, w = load(root); next_job = replay(root, p, b, c, w)
        if next_job['status'] != 'pending': return verify(root)
        run_role(next_job['job'], next_job['prompt'], *MODEL, next_job['bindings'], timeout=1200)
        return verify(root)


def run(output):
    while True:
        result = advance(output)
        if result['status'] != 'pending': return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('seed'); init.add_argument('output')
    init.add_argument('--max-rounds', type=int, default=2); init.add_argument('--max-tokens', type=int, default=600000)
    init.add_argument('--new-experiment', action='store_true', help='Explicit separately authorized test; preserves exhausted prior run')
    init.add_argument('--reuse-proposal', action='store_true', help='Reuse a verified pending proposal from a prior correction experiment; no new author call')
    for name in ('advance', 'run', 'verify'): sub.add_parser(name).add_argument('output')
    args = parser.parse_args()
    result = initialize(args.seed, args.output, args.max_rounds, args.max_tokens, args.new_experiment, args.reuse_proposal) if args.command == 'init' else globals()[args.command](args.output)
    print(json.dumps(result))


if __name__ == '__main__': main()
