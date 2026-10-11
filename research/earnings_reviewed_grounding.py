"""Replay a narrow independent boundary review; preserve all original source turns."""
import copy
import hashlib
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_role_import as imp


def check(value,message):
    if not value:raise ValueError(message)


def apply(binding,bundle,original_retrieval):
    path=Path(binding['proposal']);check(r.sha(path)==binding['proposal_sha256'],'Boundary proposal changed')
    proposal=r.read(path);review=imp.authenticate(binding['review']);verdict=review['content']
    request=r.read(Path(binding['review']['job'])/'request.json')
    check(request['bindings']=={'proposal_sha256':r.sha(path),'scope':'source-attribution-only'},'Review is not bound to proposal')
    check(verdict.get('decision')=='accept' and all(verdict.get(k) is True for k in ('membership_accepted','coverage_status_change_accepted','closing_content_retained')),'Independent boundary acceptance required')
    source=proposal['source'];index=bundle['transcript_index'];text=Path(source['path']).read_text()
    check(r.sha(source['path'])==source['sha256']==index['source']['text_sha256'] and source['document_id']==index['source']['document_id'],'Reviewed source changed')
    derived=copy.deepcopy(bundle);idx=derived['transcript_index'];eid=proposal['exchange']['id'];exchanges=[e for e in idx['exchanges'] if e['id']==eid]
    check(len(exchanges)==1 and exchanges[0]==proposal['exchange'],'Original exchange changed')
    e=exchanges[0];turns={t['id']:t for t in idx['turns']};spans=proposal['turns']
    check(len(spans)==len(e['turn_ids']) and {t['id'] for t in spans}==set(e['turn_ids']),'Complete exchange evidence required')
    for t in spans:
        check(t['id'] in turns and all(t.get(k)==v for k,v in turns[t['id']].items()),'Reviewed turn changed')
        chunk=text[t['start']:t['end']]
        check(t['text']==chunk and hashlib.sha256(chunk.encode()).hexdigest()==t['span_sha256'],'Source span changed')
    m=proposal['proposed_membership'];check(set(m)=={'question_turn_ids','answer_turn_ids','non_question_turns'},'Unexpected membership fields')
    members=sum(m.values(),[]);check(len(members)==len(set(members)) and set(members)==set(e['turn_ids']),'All source turns must remain accounted for')
    check(m['question_turn_ids'] and m['answer_turn_ids'],'Question and answer required')
    e.update(question_turn_ids=m['question_turn_ids'],answer_turn_ids=m['answer_turn_ids'],reviewed_non_question_turn_ids=m['non_question_turns'],boundary_review='independently_reviewed_source_attribution')
    out=copy.deepcopy(original_retrieval);rows=[x for x in out['exchange_coverage'] if x['exchange_id']==eid]
    check(len(rows)==1 and rows[0]==proposal['coverage_row'],'Original coverage changed')
    change=proposal['proposed_coverage_change'];check(set(change)=={'grounding_status','grounding_notes'} and change['grounding_status']=='bound' and isinstance(change['grounding_notes'],str),'Only reviewed attribution status may change')
    rows[0].update(change)
    return derived,out,review
