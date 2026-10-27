"""Explicit offline answer-list and linked quotation address contract.

No mapping is selected by eligibility. Only fresh original source adjudication
may bind the same invalid address in these two positions to one answer paragraph.
No launcher, preparation or coordinator activation is supplied by this module.
"""
import copy,json,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_retrieval_reference_repair as ref,earnings_retrieval_repair as original
VERSION='authenticated-answer-list-linked-quote-proposal-v1'

def targets(raw,catalog,index):
 candidate,found,preserved=ref.candidate_and_targets(raw,raw,catalog,index)
 c.require(candidate==raw and not preserved and len(found)==1 and found[0]['field']=='answer_passage_ids','One exact answer-list target required')
 t=found[0];known={p['passage_id']for p in catalog['passages']};bad=[x for x in t['before_ids']if x not in known]
 c.require(len(bad)==1 and len(t['before_ids'])==len(set(t['before_ids']))and 2<=len(t['before_ids'])<=32 and 1<=len(t['allowed_passage_ids'])<=32,'One unknown address with retained valid answer support required')
 quotes=raw.get('quotes');c.require(isinstance(quotes,list),'Original quotation ledger required');unknown=[(i,q)for i,q in enumerate(quotes)if not isinstance(q,dict)or q.get('passage_id')not in known]
 c.require(len(unknown)==1 and unknown[0][1]=={'passage_id':bad[0]},'Exactly one bare quotation linked to same unknown answer address required')
 return [{**t,'quote_index':unknown[0][0],'unknown_id':bad[0]}]

def apply(raw,catalog,index,proposal):
 selected=targets(raw,catalog,index);t=selected[0];out=ref.apply(raw,selected,proposal,catalog);after=next(x for x in out['exchange_coverage']if x['exchange_id']==t['exchange_id'])['answer_passage_ids'];pos=t['before_ids'].index(t['unknown_id'])
 c.require(len(after)==len(t['before_ids']) and after[:pos]==t['before_ids'][:pos]and after[pos+1:]==t['before_ids'][pos+1:],'Replace only invalid position with exactly one source-adjudicated paragraph')
 out['quotes'][t['quote_index']]['passage_id']=after[pos];return out

PROGRAM=r'''
import copy,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);t=json.loads(sys.argv[3])[0];protocol,bundle,catalog=p.load(root);job=root/'jobs/retrieval';q=b.read(job/'request.json');v=r.verify_job(job);raw=v['content']
assert sorted(x.name for x in(root/'jobs').iterdir())==['retrieval'] and protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2 and protocol.get('report_template')=='source-led-six-sections-v1'
assert not any(protocol.get(k)for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert [q['model'],q['effort']]==protocol['models']['retrieval'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')and(job/'prompt.md').read_text()==p.instruction('retrieval',Path(q['context_index']),job,protocol)
e=next(x for x in bundle['transcript_index']['exchanges']if x['id']==t['exchange_id']);assert t['allowed_passage_ids']==[x['passage_id']for x in catalog['passages']if x['scope_id']in e['answer_turn_ids']]
try:p.verify(root)
except ValueError as err:assert str(err)=='Required original evidence was not completely inspected: '+t['unknown_id']
else:raise AssertionError('Exact original unknown address failure required')
# Retain every original row and valid reference. Only the two invalid typed
# positions are omitted from this outside-defect inspection diagnostic.
inspected=copy.deepcopy(raw);row=next(x for x in inspected['exchange_coverage']if x['exchange_id']==t['exchange_id']);row['answer_passage_ids']=[x for x in row['answer_passage_ids']if x!=t['unknown_id']];inspected['quotes'].pop(t['quote_index']);p.coverage('retrieval',Path(q['context_index']),job,inspected,catalog,{})
# Structural checking only, never an address mapping/repair or accepted output.
# The disposable diagnostic copy is not returned as a repaired candidate.
diagnostic=copy.deepcopy(raw);row=next(x for x in diagnostic['exchange_coverage']if x['exchange_id']==t['exchange_id']);row['answer_passage_ids']=[x for x in row['answer_passage_ids']if x!=t['unknown_id']];diagnostic['quotes'].pop(t['quote_index']);p.pipe.validate('retrieval',diagnostic,bundle,catalog)
print(json.dumps({'checked':True}))
'''

def authenticate(previous):
 from . import earnings_compact_evidence as evidence
 previous=Path(previous).resolve();prior=original.original(previous);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);selected=targets(prior['raw'],catalog,bundle['transcript_index']);code=ref.frozen(b.read(previous/'jobs/retrieval/request.json')['code_root']);subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(previous),json.dumps(selected)],text=True)
 return prior,copy.deepcopy(prior['raw']),selected

def reservation_path(previous,output):
 # Same canonical slot and cross-version/legacy usage guard as question repair.
 from . import earnings_single_retrieval_questions as question
 return question.reservation_path(previous,output)
