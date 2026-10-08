"""Opt-in role evidence reuse: exact source blocks, navigation and bounded lookup."""
from __future__ import annotations
import copy
from research import earnings_experiment as base
from research import earnings_compact_evidence as evidence
from research import earnings_mixed_pipeline as legacy
from research import earnings_passages as passages
from research import earnings_repair_context as context
from research import earnings_financial_display as display

VERSION = 'role-evidence-reuse-v1'
MAX_EXPANSIONS = 1
EXPANSION_RULE = '''If needed original evidence is missing, return ONLY
{"needs_evidence":[{"scope_id":"exact source ID","reason":"specific missing context"}]}.
One source-ID expansion is available per role/round, without increasing the
existing two-correction-round budget. Ask for every needed scope together. An
evidence request is never an artifact, approval or verdict. Never invent missing
evidence. If expansion is insufficient, identify the unresolved source gap.'''


def preflight(role, deps, bundle, catalog):
    required = ('financial','retrieval','analysis') if role == 'review' else ('financial','retrieval') if role == 'analysis' else ('financial',) if role == 'retrieval' else ()
    for name in required:
        legacy.validate_output(name, passages.hydrate(name,deps[name],catalog),bundle)
    if 'financial' in required:
        from research import earnings_financial_context as financial
        financial.preflight(deps['financial'],bundle)
    if 'format' in deps:
        from research import earnings_report_repair as repair
        repair.validate_format(deps['format'],deps['financial'],bundle)


def requested_scopes(content,bundle,catalog,supplied=()):
    if not isinstance(content,dict) or 'needs_evidence' not in content: return None
    if set(content) != {'needs_evidence'}: raise ValueError('Evidence request cannot include artifact or verdict')
    result=context.evidence_response(bundle,catalog,content['needs_evidence'],supplied)
    if not result['scope_ids']: raise ValueError('Evidence request has no new original scopes')
    return tuple(result['scope_ids'])


def validate_support(role,out,bundle,catalog,deps,extra_scope_ids=()):
    """A preview/ID catalogue cannot become evidence without original context."""
    if role not in ('retrieval','analysis'):return
    view=build(role,bundle,catalog,deps,extra_scope_ids)
    supplied=set(view['coverage']['supplied_original_scope_ids'])
    supplied.update(x['id'] for group in ('turns','sections','exchanges') for x in bundle['transcript_index'][group])
    if role=='analysis':supplied.update(row[0] for row in view['financial_observations']['rows'])
    cited,quoted=context._references(out)
    if role=='retrieval':cited.update(out['selected_document_ids'])
    if role=='analysis' and not quoted<={q['passage_id'] for q in deps['retrieval']['quotes']}:
        raise ValueError('Analysis quotation must reuse a validated retrieval selection')
    by_id={p['passage_id']:p for p in catalog['passages']}
    cited.update(by_id[pid]['scope_id'] for pid in quoted)
    if not cited<=supplied:
        raise ValueError('Role claims rely on deferred source previews; request complete original scopes: '+', '.join(sorted(cited-supplied)))


def _full_call(bundle):
    v=evidence.transcript_view(bundle['manifest']); index=v['index']
    limits=index.get('call_span',{'start':0,'end':len(v['text'])});a,b=limits['start'],limits['end']
    if not 0<=a<b<=len(v['text']):raise ValueError('Invalid complete call bounds')
    text=v['text'][a:b]
    span={'path':bundle['manifest']['transcript_path'],'sha256':bundle['manifest']['transcript_sha256'],
          'document_id':index['source']['document_id'],'start':a,'end':b,'text':text,
          'offset_unit':'unicode_character','span_sha256':evidence._sha_text(text)}
    return {'id':'__complete_call_context__','spans':[span]}


def columnar(records):
    """Lossless groups retain missing-versus-null fields without repeated keys."""
    groups={}
    for record in records:
        columns=tuple(sorted(record))
        groups.setdefault(columns,[]).append([record[k] for k in columns])
    return [{'columns':list(k),'rows':v} for k,v in groups.items()]


def financial_inventory(bundle, selected=None):
    from research import earnings_financial_context as financial
    payload=financial.financial_role_payload(bundle)
    value=payload['financial_observations']
    if selected is not None:
        rows=[dict(zip(value['columns'],row)) for row in value['rows'] if row[0] in selected]
        value['rows']=[[r[k] for k in value['columns']] for r in rows]
        for field,ref in [('concepts','concept_id'),('contexts','context_id'),('units','unit_id'),('source_rows','source_row_id')]:
            wanted={r[ref] for r in rows};value[field]={k:v for k,v in value[field].items() if k in wanted}
        for field,ref in [('entities','entity_id'),('dimension_sets','dimensions_id')]:
            wanted={r[ref] for r in value['contexts'].values()};value[field]={k:v for k,v in value[field].items() if k in wanted}
        value['omitted_observation_ids']=[o['id'] for o in bundle['financial']['observations'] if o['id'] not in selected]
    return {'source_registry':payload['sources'],**value}


def build(role,bundle,catalog,deps,extra_scope_ids=()):
    if role=='financial':
        from research import earnings_financial_context as financial
        data=financial.financial_role_payload(bundle)
        if extra_scope_ids:data={**data,'requested_original_evidence':financial.expand(bundle,list(extra_scope_ids))}
        return data
    if role not in ('retrieval','analysis','review'):raise ValueError('Unknown efficient role')
    preflight(role,deps,bundle,catalog)
    scopes,pids,parents=context._index(bundle,catalog)
    cited,quoted=context._references(deps)
    if not cited<=set(scopes) or not quoted<=set(pids):raise ValueError('Unknown dependency evidence')
    selected=set(extra_scope_ids)
    if not selected<=set(scopes):raise ValueError('Unknown expanded source')
    selected.update(cited);selected.update(pids[p]['scope_id'] for p in quoted)
    prep=None
    if role=='review':selected.update(x['id'] for x in bundle['documents']['chunks'])
    elif role=='retrieval':
        from research import earnings_financial_context as financial
        prep=financial.financial_role_payload(bundle)
        selected.update(row['id'] for row in prep['complete_context_chunks'])
        selected.update(row['id'] for row in bundle['documents']['chunks'] if row['kind']=='release')
    else:selected.update(deps['retrieval']['selected_document_ids'])
    selected.update(x['id'] for x in bundle['transcript_index']['turns'])
    for sid in list(selected):selected.update(parents.get(sid,()))
    facts={o['id'] for o in bundle['financial']['observations']}
    # Structured facts contain complete original contexts/units. Raw markup is
    # available on explicit F-ID expansion; never repeat it for every mention.
    material=(selected-facts)|(set(extra_scope_ids)&facts)
    entries=context._materialize(scopes,material)+[_full_call(bundle)]
    refs,blocks=context._compact_spans(entries)
    quote_rows=[p for p in catalog['passages'] if p['scope_id'] in material and (role=='retrieval' or p['passage_id'] in quoted)]
    quote_refs=context._compact_passages(quote_rows,blocks)
    # Scope references already bind source blocks and original hashes. Avoid
    # repeating that provenance for every sentence in the quote catalogue.
    quote_groups={}
    for row in quote_refs:
        quote_groups.setdefault(row['scope_id'],[]).append([row['passage_id'],row['start'],row['end']])
    case=base.read(bundle['manifest']['case_path'])
    navigation=context._navigation_index(scopes)
    # D boundaries are not repeated elsewhere. Transcript scopes already have
    # full section/turn/exchange indices; F IDs have exact structured metadata.
    navigation['rows']=[row for row in navigation['rows'] if row[0].startswith('D') or row[0] in extra_scope_ids]
    navigation['other_scopes']='Transcript scopes are indexed below; financial F IDs are in financial_observations. Every original ID can be expanded.'
    source_index={(row[0],row[1]):i for i,row in enumerate(navigation['sources'])}
    compact_blocks={'columns':['source_index','start','end','text'],
                    'rows':[[source_index[(b['document_id'],b['sha256'])],b['start'],b['end'],b['text']] for b in blocks]}
    transcript=copy.deepcopy(bundle['transcript_index'])
    for key in ('sections','turns','exchanges'):transcript[key]=columnar(transcript[key])
    data={'version':VERSION,'case_id':case['case_id'],'scope_notes':case['scope_notes'],
          'source_blocks':compact_blocks,
          'passages':{'columns':['passage_id','start','end'],'groups':[{'scope_id':k,'rows':v} for k,v in quote_groups.items()]},
          'complete_source_navigation':navigation,'transcript_index':transcript,
          'coverage':{'complete_call':True,'complete_nontranscript_text':role=='review',
                      'supplied_original_scope_ids':sorted(material),
                      'excluded_representations':bundle['documents'].get('excluded_representations',[]),
                      'notice':'Blocks retain exact original text once. Original Unicode offsets reconstruct each scope and quote. All IDs remain requestable; omission of raw markup is not absence of evidence.'}}
    if role=='retrieval':
        data.update(financial_context=copy.deepcopy(deps['financial']),document_navigation=prep['document_inventory'],
                    navigation_sources=prep['sources'],
                    deferred_document_ids=[d['id'] for d in bundle['documents']['chunks'] if d['id'] not in material])
    if role!='retrieval':
        data.update(financial_context=copy.deepcopy(deps['financial']),retrieval_batch=copy.deepcopy(deps['retrieval']),
                    financial_table=display.build(deps['financial'],bundle))
        data['financial_observations']=financial_inventory(bundle,None if role=='review' else selected & facts)
    if role=='review':data.update(candidate_analysis=copy.deepcopy(deps['analysis']),candidate_format=copy.deepcopy(deps.get('format')))
    return data


def prompt(role,bundle,writing,deps,feedback,catalog,extra_scope_ids=()):
    preflight(role,deps,bundle,catalog)
    hydrated={r:passages.hydrate(r,v,catalog) for r,v in deps.items() if r!='format'}
    original=legacy.prompt_for(role,bundle,writing,hydrated,feedback)
    head=original.split('\n\nFROZEN EVIDENCE / ARTIFACTS\n',1)[0]
    head=head.replace('No tools are available; all evidence needed for your assigned task is supplied below.',
                      'No tools are available; exact source-ID expansion is available below.')
    head=head.replace('"quotes":[{"scope_id":"EXACT TURN/EXCHANGE OR D ID","text":"Exact distinctive short source substring"}]','"quotes":[{"passage_id":"EXACT CATALOGUE ID"}]')
    head=head.replace('"quotes":[{"scope_id":"EXACT SOURCE ID","text":"exact substring"}]','"quotes":[{"passage_id":"EXACT SELECTED PASSAGE ID"}]')
    head=head.replace('Do not include start offsets unless needed for repeated text.','Select quotation IDs only; code copies source bytes.')
    if role=='retrieval':
        head=head.replace('Read the complete transcript and all nontranscript documents.',
                          'Read the complete transcript and supplied original document contexts. Inspect the complete document navigation and request deferred original chunks when needed; previews are discovery aids, never claim evidence.')
    head=head.replace('Aim for 650–900 total report words including deterministic financial table and quotes.',
                      'Use a short substantive opening, compact financial table and 4–6 consequential findings. Prefer 550–750 total words when the evidence permits; preserve all material evidence.')
    head=head.replace('Synthesize 4–7 distinct consequential findings;','Synthesize 4–6 distinct consequential findings;')
    instructions=('Quoted passages use IDs only. Original source blocks and financial IDs, not preparer claims, establish support. '
                  'Read full speaker turns and surrounding context. Source-ID navigation is complete; omission never proves absence. ')
    if role=='review':instructions+=('The full structured candidate plus deterministic table is the exact report. Audit every field, repeated claim, quote, guidance condition, attribution and material omission in one comprehensive pass. Complete original narrative sources are supplied independently of preparer selections. Do not demand longer prose merely for completeness. ')
    if role=='financial':instructions+=('The compact source inventory explicitly distinguishes complete materialized chunks from previews and deferred IDs. Read original context for material qualifications; request missing complete source spans before asserting completeness. Do not output display/layout objects; code binds deterministic source labels after validation. ')
    return head+'\n\nEVIDENCE PROTOCOL\n'+instructions+EXPANSION_RULE+'\n\nFROZEN EVIDENCE / ARTIFACTS\n'+legacy.packed(build(role,bundle,catalog,deps,extra_scope_ids))


def benchmark_inputs(bundle,catalog,writing,deps):
    from research import earnings_passage_pipeline as pipe
    from research import earnings_financial_context as financial
    result={}
    for role in ('financial','retrieval','analysis','review'):
        selected={} if role in ('financial','retrieval') else {k:deps[k] for k in ('financial','retrieval')} if role=='analysis' else deps
        old=pipe.prompt(role,bundle,writing,selected,[],catalog)
        try:
            efficient=copy.deepcopy(selected)
            if role=='retrieval':efficient={'financial':copy.deepcopy(deps['financial'])}
            if 'financial' in efficient:efficient['financial']=financial.bind(efficient['financial'],bundle)
            new=prompt(role,bundle,writing,efficient,[],catalog)
            result[role]={'original_characters':len(old),'efficient_characters':len(new),'reduction_fraction':1-len(new)/len(old)}
        except (ValueError,KeyError,TypeError) as exc:
            result[role]={'original_characters':len(old),'efficient_characters':None,'reduction_fraction':None,
                          'preflight_status':'blocked','preflight_error':str(exc)}
    return result
