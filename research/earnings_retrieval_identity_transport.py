"""Replay one exact source-membership address derivation without a model call.

This does not accept a report or award another correction. All original bytes,
usage, model assignments and the independently reviewed source index are retained.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path
from . import earnings_mixed_runner as b, earnings_file_context as c
from . import earnings_retrieval_reference_repair as ref

VERSION = 'authenticated-exact-retrieval-identity-transport-v1'


def exact_identity(raw, catalog, index):
    """Replace one unknown exchange ID using unique exact Q/A scope membership."""
    rows = raw.get('exchange_coverage')
    exchanges = {e['id']: e for e in index['exchanges']}
    c.require(isinstance(rows, list) and len(rows) == len(exchanges), 'Complete exchange cardinality required')
    ids = [r['exchange_id'] for r in rows]
    c.require(len(set(ids)) == len(ids), 'Duplicate exchange addresses forbidden')
    unknown = [i for i, eid in enumerate(ids) if eid not in exchanges]
    missing = set(exchanges) - set(ids)
    c.require(len(unknown) == len(missing) == 1, 'Exactly one unknown and missing exchange required')
    pos = unknown[0]; row = rows[pos]
    passages = {p['passage_id']: p for p in catalog['passages']}
    scopes = {}
    for field in ('question_passage_ids', 'answer_passage_ids'):
        values = row[field]
        c.require(isinstance(values, list) and values and len(values) == len(set(values))
                  and all(v in passages for v in values), 'Exact nonempty original passage addresses required')
        scopes[field] = {passages[v]['scope_id'] for v in values}
    matches = [eid for eid, e in exchanges.items()
               if scopes['question_passage_ids'] <= set(e['question_turn_ids'])
               and scopes['answer_passage_ids'] <= set(e['answer_turn_ids'])]
    c.require(len(matches) == 1 and set(matches) == missing, 'Unique missing source membership required')
    # The erroneous address may not occur in prose, links or other fields.
    without = copy.deepcopy(raw); without['exchange_coverage'][pos]['exchange_id'] = ''
    c.require(ids[pos] not in json.dumps(without), 'Unknown exchange address also occurs outside typed identity')
    result = copy.deepcopy(raw); result['exchange_coverage'][pos]['exchange_id'] = matches[0]
    proof = {'path': f'/exchange_coverage/{pos}/exchange_id', 'before': ids[pos], 'after': matches[0],
             'question_passage_ids': list(row['question_passage_ids']),
             'answer_passage_ids': list(row['answer_passage_ids']),
             'question_scope_ids': sorted(scopes['question_passage_ids']),
             'answer_scope_ids': sorted(scopes['answer_passage_ids']),
             'method': 'unique-exact-original-question-and-answer-scope-membership'}
    return result, proof


PROGRAM = r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval']
assert not any(protocol.get(k) for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization','inherited_tokens','authorized_prior_tokens'))
job=root/'jobs/retrieval';q=b.read(job/'request.json');done=r.verify_job(job)
assert q['bindings']['role']=='retrieval' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert [q['model'],q['effort']]==protocol['models']['retrieval']
assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest']
assert protocol.get('financial_mode')=='deterministic-original-facts-v1'
from research import earnings_file_context as context,earnings_financial_outline as outline
import tempfile
case=b.read(protocol['case_path'])
deps={'financial':outline.artifact(bundle['financial'],expanded=protocol.get('report_template')==p.template.VERSION),'qa_grounding':b.read(root/'qa-grounding.json')}
metadata={'role':'retrieval','case':case['scope_notes'],'period':case.get('period'),'case_scope_notes':case.get('scope_notes',[])}
assert Path(q['context_index']).resolve()==root/'contexts/retrieval/index.json'
# Rebuild only ephemeral context copies. Never write to the original pipeline.
with tempfile.TemporaryDirectory(prefix='verified-identity-context-') as temporary:
 expected_index=context.assemble(protocol['evidence_manifest'],catalog,Path(temporary)/'context',artifacts=deps,metadata=metadata)
 assert b.read(expected_index)==b.read(q['context_index'])
assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':'retrieval','context_sha256':b.sha(q['context_index']),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
assert (job/'prompt.md').read_text()==p.instruction('retrieval',Path(q['context_index']),job,protocol)
assert protocol['max_correction_rounds']==2 and protocol['max_tokens']<=1200000
try:p.pipe.validate('retrieval',done['content'],bundle,catalog)
except ValueError as error:assert str(error)=='Every Q&A exchange needs exactly one coverage entry'
else:raise AssertionError('Exact original exchange cardinality failure required')
p.coverage('retrieval',Path(q['context_index']),job,done['content'],catalog,{})
candidate=json.load(sys.stdin)
if candidate is not None:
 p.pipe.validate('retrieval',candidate,bundle,catalog)
 p.coverage('retrieval',Path(q['context_index']),job,candidate,catalog,{})
print(json.dumps({'raw':done['content'],'catalog':catalog,'index':bundle['transcript_index'],
 'tokens':done['receipt']['session']['usage']['totalTokens'],'session_id':done['receipt']['session']['id'],
 'max_tokens':protocol['max_tokens'],'models':protocol['models'],'case_sha256':protocol['case_sha256'],
 'writing_sha256':protocol['writing_sha256'],'catalog_sha256':b.digest(catalog),
 'report_template':protocol.get('report_template'),'model_profile':protocol.get('model_profile')}))
'''


def replay(previous, candidate=None):
    previous = Path(previous).resolve()
    code = ref.frozen(b.read(previous/'jobs/retrieval/request.json')['code_root'])
    return json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', '-c', PROGRAM, str(code), str(previous)],
        input=json.dumps(candidate), text=True))


def derive(previous):
    previous = Path(previous).resolve(); original = replay(previous)
    content, identity = exact_identity(original['raw'], original['catalog'], original['index'])
    from . import earnings_retrieval_identity_grounding as grounding
    grounded = grounding.derive(previous, content, original['catalog'])
    content = grounded['content']
    checked = replay(previous, content)
    c.require(checked == original, 'Original changed during verification')
    c.require(type(original['tokens']) is int and 0 < original['tokens'] < original['max_tokens'], 'Charged original retrieval required')
    result = {k: original[k] for k in ('tokens', 'session_id', 'max_tokens', 'models', 'case_sha256',
                                      'writing_sha256', 'catalog_sha256', 'report_template', 'model_profile')}
    result.update(version=VERSION, previous_root=str(previous),
                  protocol_sha256=b.sha(previous/'protocol.json'),
                  output_sha256=b.sha(previous/'jobs/retrieval/output.json'),
                  session_ids=[original['session_id']], content=content, grounding=grounded['grounding'],
                  spent_correction_rounds=0,
                  derivation={'identity': identity, 'grounding': grounded['derivation'], 'original_content_sha256': b.digest(original['raw']),
                              'derived_content_sha256': b.digest(content),
                              'acceptance': 'unreviewed retrieval; independent full report review remains mandatory'})
    return result


def prepare(previous, case, output):
    c.require(not Path(output).exists(), 'New immutable transport manifest required')
    value = derive(previous)
    c.require(value['case_sha256'] == b.sha(case), 'Original case required')
    c.write(output, value)
    return value


def verify(path, case, catalog):
    value = b.read(path)
    c.require(isinstance(value, dict) and value.get('version') == VERSION, 'Explicit identity transport required')
    c.require(value == derive(value['previous_root']), 'Identity transport derivation changed')
    c.require(value['case_sha256'] == b.sha(case) and value['catalog_sha256'] == b.digest(catalog), 'Original case/catalog required')
    return value
