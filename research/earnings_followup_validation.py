"""Source-preserving validation for explicitly approved follow-up context links.

The frozen schema demands a quote for every referenced indexed exchange. A single
question interrupted by a correction can span a parent and follow-up exchange,
with its exact answer quotes in the child. This adapter permits the unquoted
parent as context only when a private, independently inspected policy binds the
source, full reviewed index and exact direct adjacent same-questioner pair.

No output or prompt is rewritten. The original validator checks a temporary copy
with those context-only references removed; all quote, identity, span, field and
fact checks remain. Full findings still go to independent substantive review.
This is structural compatibility, not approval of the finding's interpretation.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from . import transcript_evidence as transcript

VERSION = 'earnings-followup-context-validation-v1'
ERROR = 'Every referenced exchange needs exact source evidence'
_ORIGINAL = transcript.validate_findings


def index_digest(index):
    return hashlib.sha256(json.dumps(index,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _questioner(exchange):
    # Legacy indexes name this field analyst. New indexes keep occupation separate.
    value = exchange.get('questioner', exchange.get('analyst'))
    if 'questioner' in exchange and 'analyst' in exchange and exchange['questioner'] != exchange['analyst']:
        raise ValueError('Conflicting questioner identities')
    return value if isinstance(value, str) and value.strip() else None


def _policy(index, text, source_sha256, index_sha256, allowed_links):
    if (hashlib.sha256(text.encode()).hexdigest()!=source_sha256
            or index.get('source',{}).get('text_sha256')!=source_sha256):
        raise ValueError('Follow-up policy source hash mismatch')
    if index_digest(index)!=index_sha256:
        raise ValueError('Follow-up policy index hash mismatch')
    if index.get('boundary_review')!='reviewed' or index.get('needs_review'):
        raise ValueError('Follow-up context policy requires a reviewed index')
    if not isinstance(allowed_links,list) or not allowed_links:
        raise ValueError('Explicit independently inspected context links required')
    exchanges=index['exchanges'];by_id={e['id']:e for e in exchanges};positions={e['id']:i for i,e in enumerate(exchanges)}
    if len(by_id)!=len(exchanges):raise ValueError('Unique indexed exchanges required')
    permitted=set()
    for link in allowed_links:
        if not isinstance(link,dict) or set(link)!={'parent_exchange_id','child_exchange_id'}:
            raise ValueError('Exact parent/child context policy fields required')
        parent_id,child_id=link['parent_exchange_id'],link['child_exchange_id']
        if parent_id not in by_id or child_id not in by_id:
            raise ValueError('Context policy references unknown exchange')
        parent,child=by_id[parent_id],by_id[child_id]
        if (child.get('followup_of')!=parent_id or positions[child_id]!=positions[parent_id]+1
                or not _questioner(parent) or _questioner(parent)!=_questioner(child)
                or parent.get('boundary_review')!='reviewed' or child.get('boundary_review')!='reviewed'):
            raise ValueError('Context policy requires direct adjacent same-questioner reviewed follow-up')
        if (parent_id,child_id) in permitted:raise ValueError('Duplicate context policy link')
        permitted.add((parent_id,child_id))
    return permitted


def inspect_context_links(findings,index,text,fact_ids=(),*,source_sha256,index_sha256,allowed_links):
    """Validate unchanged findings and describe any approved context-only links.

    index_sha256 is index_digest(index), not the JSON file byte hash. An adapter
    receipt should retain both, together with raw output/session hashes. Success
    always requires independent semantic review of the full original finding.
    """
    permitted=_policy(index,text,source_sha256,index_sha256,allowed_links)
    try:
        receipt=_ORIGINAL(findings,index,text,fact_ids)
    except ValueError as error:
        if str(error)!=ERROR:raise
    else:
        return {**receipt,'context_links':[],'validation_adapter':VERSION}
    projected=deepcopy(findings);links=[]
    for original,finding in zip(findings,projected):
        referenced=set(original['exchange_ids']);quoted={q.get('exchange_id') for q in original.get('quotes',[])}
        for parent in sorted(referenced-quoted):
            children=sorted(child for p,child in permitted if p==parent and child in referenced and child in quoted)
            if len(children)!=1:
                raise ValueError('Unquoted exchange lacks one approved directly quoted follow-up')
            links.append({'finding_id':original['id'],'parent_exchange_id':parent,'child_exchange_id':children[0],
                          'disposition':'unquoted_parent_context_retained_in_original_finding'})
        finding['exchange_ids']=[eid for eid in original['exchange_ids'] if eid in quoted]
    # Do not traverse ancestry: every removed parent must have an actually quoted
    # immediate child. A chain of unquoted intermediate exchanges cannot qualify.
    receipt=_ORIGINAL(projected,index,text,fact_ids)
    if not links:raise ValueError('No contextual link explains the structural failure')
    return {**receipt,'context_links':links,'validation_adapter':VERSION,
            'original_findings_unchanged':findings!=projected,
            'semantic_review':'required_on_full_original_findings'}


@contextmanager
def adapter(*,source_sha256,index_sha256,allowed_links):
    """Temporarily apply one frozen policy to both runtimes' shared validator.

    Call once around the bounded executor/verification operation. Do not nest
    adapters or combine unreviewed recovery exceptions. The caller persists and
    authenticates its private policy and records the technical intervention.
    """
    if transcript.validate_findings is not _ORIGINAL:
        raise ValueError('Another transcript validation adapter is already active')
    policy=deepcopy({'source_sha256':source_sha256,'index_sha256':index_sha256,'allowed_links':allowed_links})
    def validate(findings,index,text,fact_ids=()):
        return inspect_context_links(findings,index,text,fact_ids,**policy)
    transcript.validate_findings=validate
    try:yield
    finally:transcript.validate_findings=_ORIGINAL
