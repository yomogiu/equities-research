"""Compatibility preflight for archived multi-role report workflows only."""
import json
from pathlib import Path
from . import earnings_runtime_common as base
from . import earnings_compact_evidence as evidence
from .earnings_file_context import require


def validate_result(self, value):
    """Pre-submit feedback only; never an acceptance or coverage waiver.

    Uses the same immutable context, schemas and delivered-source checks as
    the host. Does not write an output, mutate the draft or launch a model.
    The current tool response cannot count as previously delivered evidence.
    """
    from . import earnings_file_pipeline as pipeline
    from . import earnings_passage_pipeline as pipe
    from . import earnings_signals as signals, earnings_batch_review as batch
    job=self.log.parent
    request=base.read(job/'request.json')
    require(request.get('version')=='file-prime-role-v1' and
            Path(request['context_index']).resolve()==self.root/'index.json',
            'Bound active role context required')
    role=request['bindings']['role']
    import copy
    value=copy.deepcopy(value)
    artifacts=base.read(self.root/'artifacts.json')
    self.verify()
    bundle=evidence.load_bundle(self.index['manifest'])
    try:
        if role=='correction' and base.read(self.root/'metadata.json').get('repair_version') in ('authenticated-combined-review-final-correction-v1','authenticated-six-role-review-final-v1'):
            from . import earnings_review_binding_final as binding
            binding.validate_proposal(self.root/'index.json',job,value,artifacts,self.catalog,bundle)
            return {'valid':True,'acceptance':False,'instruction':'Combined binding and authored correction passed original source/schema checks; NEW independent FULLreview2 required.'}
        if role=='analysis' and base.read(self.root/'metadata.json').get('repair_version')=='authenticated-missing-review-source-repair-v1':
            from . import earnings_review_binding_repair as binding
            binding.validate_proposal(self.root/'index.json',job,value,artifacts,self.catalog,bundle)
            return {'valid':True,'acceptance':False,'instruction':'Binding proposal passed full source and review checks; final correction and NEW independent review remain required.'}
        if role=='analysis' and base.read(self.root/'metadata.json').get('repair_version')=='authenticated-empty-signal-source-repair-v1':
            from . import earnings_signal_binding_repair as binding
            binding.validate_proposal(self.root/'index.json',job,value,artifacts,self.catalog,bundle)
            return {'valid':True,'acceptance':False,'instruction':'Binding proposal passed schema and delivered-source checks; independent full report review still required.'}
        # Report all mistyped exchange bindings together; never guess or rewrite IDs.
        exchange_ids=set(self.index['exchange_ids'])
        invalid=[]
        def check_ids(node):
            if isinstance(node,dict):
                for key,item in node.items():
                    if key=='exchange_id' and (not isinstance(item,str) or item not in exchange_ids):
                        invalid.append(item)
                    else:check_ids(item)
            elif isinstance(node,list):
                for item in node:check_ids(item)
        check_ids(value)
        if invalid:
            return {'valid':False,'acceptance':False,'error':'Unknown Q&A coverage entry exchange IDs',
                    'invalid_exchange_ids':invalid,'valid_exchange_ids':sorted(exchange_ids),
                    'instruction':'Copy exact IDs from the delivered call locators; do not infer bindings from similar spelling.'}
        if role in ('financial','retrieval','analysis'):
            if role=='analysis' and base.read(self.root/'metadata.json').get('repair_version')=='authenticated-analysis-address-repair-v1':
                from . import earnings_analysis_address_repair as addresses
                addresses.checked_candidate(json.loads(artifacts['unreviewed_prior_analysis_json']),value,bundle['transcript_index'])
            if role=='analysis' and base.read(self.root/'metadata.json').get('repair_version')=='authenticated-analysis-turn-address-repair-v1':
                from . import earnings_analysis_turn_address_repair as addresses
                addresses.checked_candidate(json.loads(artifacts['unreviewed_prior_analysis_json']),value,bundle['transcript_index'])
            pipe.validate(role,value,bundle,self.catalog)
            if role=='analysis':
                from . import earnings_report_template as template
                template.validate(value)
        elif role=='signal_author':
            signals.validate(value,artifacts['state'],bundle,self.catalog)
        elif role=='correction':
            if set(value)!={'blocked'}:
                plan,_=batch.resolve_correction_hashes(artifacts['units'],value,
                    bound_batch_sha256=base.read(self.root/'metadata.json')['before_sha256'])
                plan,_=batch.resolve_basis_citations(artifacts['units'],plan,bundle)
                units,_=batch.apply(artifacts['units'],plan,batch.EDITORIAL_VERSION)
                batch.validate(units,bundle,self.catalog)
        elif role=='retrieval_reference':
            from . import earnings_retrieval_reference_repair as reference
            if base.read(self.root/'metadata.json').get('repair_version')=='authenticated-single-retrieval-answer-quote-v1':
                from . import earnings_single_retrieval_answer_quote as linked
                linked.apply(artifacts['reference_candidate'],artifacts['reference_targets'],value,self.catalog,bundle['transcript_index'])
            elif base.read(self.root/'metadata.json').get('repair_version')=='authenticated-single-retrieval-question-addresses-v1':
                from .earnings_single_retrieval_questions import apply as apply_question
                apply_question(artifacts['reference_candidate'],artifacts['reference_targets'],value,self.catalog)
            elif base.read(self.root/'metadata.json').get('repair_version')=='authenticated-single-retrieval-quoted-addresses-v1':
                from .earnings_single_retrieval_addresses import apply_quoted
                apply_quoted(artifacts['reference_candidate'],artifacts['reference_targets'],value,self.catalog)
            else:reference.apply(artifacts['reference_candidate'],artifacts['reference_targets'],value,self.catalog)
            scope_ids=base.read(self.root/'metadata.json')['source_scope_ids']
            pipeline.coverage(role,self.root/'index.json',job,{'citations':scope_ids,'passage_ids':[x for r in value['repairs'] for x in r['after_ids']]},self.catalog,{})
        elif role=='review':
            payload=pipeline.review_payload(value,artifacts['units'],artifacts['state'],artifacts.get('report_questions'))
            batch.adjudicate(artifacts['units'],set(artifacts['units']),{},payload,
                             self.catalog,base.digest(value),batch.EDITORIAL_VERSION)
        else:
            raise ValueError('Unknown role')
        pipeline.coverage(role,self.root/'index.json',job,value,self.catalog,artifacts)
    except (ValueError,KeyError,TypeError) as error:
        return {'valid':False,'error':str(error),'acceptance':False,
                'instruction':'Repair the draft or inspect the missing original evidence; do not waive the check.'}
    return {'valid':True,'acceptance':False,
            'instruction':'Preflight only. Host validation and fresh independent review remain mandatory.'}

