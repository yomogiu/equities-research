"""Adopt exact authenticated analysis after a deterministic source-label display hold.

No author output, source fact, correction allowance or provider session is altered.
Original complete context and receipts are replayed with the original frozen code.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path
from . import earnings_mixed_runner as b, earnings_file_context as c
from . import earnings_retrieval_reference_repair as ref
from . import earnings_compact_evidence as evidence, earnings_report_repair as repair
from . import earnings_financial_display as display, earnings_mechanical_preflight as mechanical

VERSION = 'authenticated-source-label-display-continuation-v1'
PROGRAM = r'''
import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
from research import earnings_file_context as context,earnings_financial_outline as outline
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis']
assert protocol.get('financial_mode')=='deterministic-original-facts-v1'
assert not any(protocol.get(k) for k in ('analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization','authorized_prior_tokens','retrieval_repair_rounds','analysis_repair_rounds'))
inherited=b.read(protocol['preparation_path'])
assert inherited['version']=='authenticated-exact-retrieval-identity-transport-v1'
assert protocol['inherited_tokens']==inherited['tokens'] and inherited['session_ids']==[inherited['session_id']]
assert protocol['max_correction_rounds']==2 and protocol['max_tokens']<=1200000
financial=outline.artifact(bundle['financial'],expanded=protocol.get('report_template')==p.template.VERSION)
p.pipe.validate('financial',financial,bundle,catalog)
p.pipe.validate('retrieval',inherited['content'],bundle,catalog)
case=b.read(protocol['case_path']);job=root/'jobs/analysis';q=b.read(job/'request.json');done=r.verify_job(job)
assert Path(q['context_index']).resolve()==root/'contexts/analysis/index.json'
deps={'financial':financial,'retrieval':inherited['content'],'qa_grounding':b.read(root/'qa-grounding.json'),'retrieval_transport_provenance':inherited['derivation']}
metadata={'role':'analysis','case':case['scope_notes'],'period':case.get('period'),'case_scope_notes':case.get('scope_notes',[])}
with tempfile.TemporaryDirectory(prefix='verified-analysis-context-') as temporary:
 expected=context.assemble(protocol['evidence_manifest'],catalog,Path(temporary)/'context',artifacts=deps,metadata=metadata)
 assert b.read(expected)==b.read(q['context_index'])
assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':'analysis','context_sha256':b.sha(q['context_index']),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
assert [q['model'],q['effort']]==protocol['models']['analysis']
assert q['max_tokens']==protocol['max_tokens']-protocol['inherited_tokens'] and q['max_tool_calls']==protocol['max_tool_calls_per_job']==48
assert (job/'prompt.md').read_text()==p.instruction('analysis',Path(q['context_index']),job,protocol)
p.coverage('analysis',Path(q['context_index']),job,done['content'],catalog,{})
p.pipe.validate('analysis',done['content'],bundle,catalog)
assert done['content'].get('report_template')==protocol.get('report_template')
try:p.mechanical.formatting(financial,bundle)
except ValueError as error:assert str(error)=='Bounded plain-text labels required'
else:raise AssertionError('Exact original financial-label display failure required')
sid=done['receipt']['session']['id'];used=done['receipt']['session']['usage']['totalTokens']
assert sid not in inherited['session_ids'] and type(used) is int and used>0
result={'content':done['content'],'tokens':protocol['inherited_tokens']+used,'analysis_tokens':used,'analysis_session_id':sid,'session_ids':inherited['session_ids']+[sid],
 'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens'],
 'models':protocol['models'],'report_template':protocol['report_template'],'writing_sha256':protocol['writing_sha256'],
 'retrieval_preparation_path':protocol['preparation_path'],'retrieval_preparation_sha256':protocol['preparation_sha256'],
 'financial':financial,'display_rows':p.mechanical.repair.row_catalog(financial,bundle),'evidence_manifest':protocol['evidence_manifest']}
assert result['tokens']<result['max_tokens']
print(json.dumps(result))
'''


def replay(previous):
    previous = Path(previous).resolve()
    code = ref.frozen(b.read(previous/'jobs/analysis/request.json')['code_root'])
    return json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', '-c', PROGRAM, str(code), str(previous)], text=True))


def verify_label_equivalence(before, after, observations):
    """All identities, facts, units, periods, values and qualifiers stay exact."""
    allowed = set()
    for observation in observations:
        if observation.get('method') != 'reviewed_html_table':
            continue
        label = observation['support']['source_label'];clean = display.strip_terminal_dot_leader(label)
        basis = observation['accounting_basis'];suffix = ' (' + basis + ')' if basis else ''
        if label != clean:allowed.add((label + suffix, clean + suffix))
    c.require(set(before) == set(after), 'Financial row identity or grouping changed')
    changes = []
    for key, old in before.items():
        expected = copy.deepcopy(old);new = after[key]
        if old['row']['metric'] != new['row']['metric']:
            pair = old['row']['metric'],new['row']['metric']
            c.require(pair in allowed, 'Display change is not exact original terminal dot layout')
            expected['row']['metric'] = pair[1]
            changes.append({'row_id':key,'before':pair[0],'after':pair[1],
                            'before_sha256':b.digest(old),'after_sha256':b.digest(new)})
        c.require(expected == new, 'Financial display changed substantive content')
    c.require(changes, 'At least one original layout-only display change required')
    return changes


def derive(previous):
    previous = Path(previous).resolve();actual = replay(previous)
    bundle = evidence.load_bundle(actual['evidence_manifest'])
    rows = repair.row_catalog(actual['financial'],bundle)
    changes = verify_label_equivalence(actual['display_rows'],rows,bundle['financial']['observations'])
    formatting = mechanical.formatting(actual['financial'],bundle)
    result = {k:v for k,v in actual.items() if k not in ('financial','display_rows','evidence_manifest')}
    result.update(version=VERSION,previous_root=str(previous),protocol_sha256=b.sha(previous/'protocol.json'),
                  output_sha256=b.sha(previous/'jobs/analysis/output.json'),spent_correction_rounds=0,
                  derivation={'method':'original-terminal-dot-layout-only','labels':changes,
                              'analysis_content_sha256':b.digest(actual['content']),
                              'formatting_sha256':b.digest(formatting),
                              'acceptance':'unreviewed unchanged analysis; fresh signals and full independent review required'})
    return result


def prepare(previous,case,output):
    c.require(not Path(output).exists(),'New immutable display continuation manifest required')
    result=derive(previous);c.require(result['case_sha256']==b.sha(case),'Original analysis case required')
    c.write(output,result);return result


def verify(path,case,catalog):
    result=b.read(path)
    c.require(isinstance(result,dict) and result.get('version')==VERSION,'Explicit display transport required')
    c.require(result==derive(result['previous_root']),'Original analysis/display derivation changed')
    c.require(result['case_sha256']==b.sha(case) and result['catalog_sha256']==b.digest(catalog),'Original analysis case/catalog required')
    return result
