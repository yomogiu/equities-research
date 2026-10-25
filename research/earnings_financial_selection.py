"""Compact model selection over immutable financial facts; arithmetic stays in code."""
from copy import deepcopy
from pathlib import Path
import json
import re

from . import earnings_runtime_common as storage
from . import earnings_financial_context as source_context
from . import earnings_compact_evidence as evidence
from . import earnings_financial_analysis as analysis

VERSION = 'financial-selection-v1'
METRICS = {'revenue','gross_profit','cost_of_revenue','operating_income','net_income','diluted_eps',
           'diluted_shares','research_and_development','operating_cash_flow','capital_expenditure',
           'cash_and_equivalents','current_debt','noncurrent_debt','total_debt','debt_component',
           'operating_leases','share_repurchases','available_cash','credit_capacity','interest_expense'}
REQUIRED = {'revenue','diluted_eps','diluted_shares','gross_margin','research_and_development',
            'operating_cash_flow','capital_expenditure','total_debt','annual_eps','price'}
MONETARY = METRICS-{'diluted_eps','diluted_shares'}


def require(condition, message):
    if not condition: raise ValueError(message)


def compact(bundle):
    """Every raw observation survives; repeated metadata is dictionary encoded."""
    facts=bundle['financial'];identities=source_context.source_identities(bundle)
    concepts=[];labels=[];dimensions=[];entities=[];contexts={};rows=[]
    def intern(items,value):
        if value not in items:items.append(value)
        return items.index(value)
    for key,c in facts['contexts'].items():
        period=['instant',c['instant']] if c.get('instant') else ['duration',c.get('start_date'),c.get('end_date')]
        contexts[key]=[intern(entities,[c.get('entity'),c.get('entity_scheme')]),period,intern(dimensions,c.get('dimensions',[]))]
    for o in facts['observations']:
        identity=identities.get(o['id'],{})
        rows.append([o['id'],intern(concepts,o['concept']),o.get('value'),o['context_id'],o.get('unit_id'),
                     intern(labels,[identity.get('label'),identity.get('basis'),identity.get('label_origin')]),
                     o.get('status'),bool(o.get('nil'))])
    docs,full=source_context._documents(bundle)
    inventory=[[d['id'],d['kind'],d['cues'],d['preview']] for d in docs]
    # Provide original basis and statement text first; other notes are retrieved
    # by ID. Previews are explicitly not evidence of inspection.
    selected=[]
    for cue in source_context.CUES:
        matches=[d['id'] for d in docs if cue in d['cues']]
        for identifier in matches[:2]:
            if identifier not in selected:selected.append(identifier)
    chunks=[{'id':i,'text':full[i]} for i in selected]
    # Losslessly coalesce equivalent context/unit definitions and duplicate facts.
    # All original IDs survive in each group's ids list; no value is averaged.
    shared_contexts=[];context_refs={}
    for key,c in contexts.items():context_refs[key]=intern(shared_contexts,c)
    shared_units=[];unit_refs={}
    for key,u in facts['units'].items():unit_refs[key]=intern(shared_units,{k:u[k] for k in ('numerator','denominator')})
    grouped={}
    for fid,concept,value,cid,uid,label,status,nil in rows:
        key=json.dumps([concept,value,context_refs[cid],unit_refs[uid],label,status,nil],separators=(',',':'))
        grouped.setdefault(key,[]).append(fid)
    compact_rows=[];exceptions={}
    for key,ids in grouped.items():
        concept,value,cid,uid,label,status,nil=json.loads(key)
        compact_rows.append([ids,concept,value,cid,uid,label])
        if status!='extracted' or nil or value is None:
            for fid in ids:exceptions[fid]={'status':status,'nil':nil}
    axes=[];members=[];dimension_rows=[]
    for dims in dimensions:
        dimension_rows.append([[intern(axes,d['dimension']),intern(members,{k:v for k,v in d.items() if k!='dimension'})] for d in dims])
    return {'version':VERSION,'fact_columns':['ids','concept_index','value','context_index','unit_index','label_index'],
            'facts':compact_rows,'concepts':concepts,'label_columns':['source_label','source_basis','origin'],'labels':labels,
            'context_columns':['entity_index','period','dimension_index'],'contexts':shared_contexts,'entities':entities,
            'dimension_columns':['axis_index','member_index'],'dimension_axes':axes,'dimension_members':members,
            'dimensions':dimension_rows,'units':shared_units,'exceptional_fact_status':exceptions,
            'default_fact_status':'extracted, non-nil','extraction_gaps':facts.get('gaps',[]),
            'document_columns':['id','kind','preview_not_evidence'],
            'documents':[[d['id'],d['kind'],d['preview'][:80]] for d in docs],
            'complete_original_chunks':chunks,'total_observations':len(rows),'omitted_observations':0,
            'grouping_rule':'Identical concept, value, period/entity/dimensions, unit, label and status share a row. Every original fact ID is retained.'}



def validate(value,bundle):
    require(isinstance(value,dict) and set(value) in ({'rows','gaps','notes'}, {'rows','gaps','notes','reported_tables'}),'Exact selection fields required')
    require(isinstance(value['rows'],list) and 0<=len(value['rows'])<=35,'Zero through 35 selected metric rows required')
    require(isinstance(value['gaps'],list) and isinstance(value['notes'],list),'Selection gaps and notes required')
    from . import earnings_packet_inventory as packet_inventory
    packet_inventory.validate_selection(value.get('reported_tables',[]),bundle)
    facts=bundle['financial'];byid={o['id']:o for o in facts['observations']};known=set(evidence._scopes(bundle))
    selected=set();covered=set()
    def text(v):require(isinstance(v,str) and bool(v.strip()) and 1<=len(v)<=2400 and not re.search(r'[\n\r|]|\[\^',v),'Bounded plain selection text required')
    def citations(v):require(isinstance(v,list) and v and len(set(v))==len(v) and set(v)<=known,'Known original evidence citations required')
    for row in value['rows']:
        require(isinstance(row,dict) and set(row)=={'metric','label','basis','fact_ids','citations','definition'},'Exact selected row fields required')
        require(row['metric'] in METRICS,'Unknown selected calculation role')
        for k in ('label','basis','definition'):text(row[k])
        require(row['basis'] in ('GAAP','IFRS','non-GAAP'),'Explicit bounded accounting classification required')
        citations(row['citations']);require(any(i.startswith(('D','document-source-')) for i in row['citations']),'Original statement/note support required for mapping and basis')
        ids=row['fact_ids'];require(isinstance(ids,list) and ids and len(ids)<=100 and len(set(ids))==len(ids) and set(ids)<=set(byid),'Known unique selected fact IDs required')
        require(not selected.intersection(ids),'A fact cannot be assigned to multiple metric rows');selected.update(ids);covered.add(row['metric'])
        signatures=set();period_values={}
        for fid in ids:
            o=byid[fid];require(o.get('status')=='extracted' and not o.get('nil') and o.get('value') is not None and o.get('method')=='inline_xbrl','Selected facts must be extracted original numeric observations')
            analysis._number(o['value']);c=facts['contexts'][o['context_id']];u=facts['units'][o['unit_id']]
            period=tuple(['instant',c['instant']] if c.get('instant') else ['duration',c['start_date'],c['end_date']])
            dims=c['dimensions']
            if dims and row['metric'] not in ('available_cash','credit_capacity','debt_component'):
                require(row['metric'] in ('diluted_eps','diluted_shares') and all(d['dimension']=='us-gaap:StatementClassOfStockAxis' for d in dims),
                        'Core consolidated metrics cannot silently use segment observations')
            signatures.add(storage.digest([c['entity'],c['entity_scheme'],dims,{k:u[k] for k in ('numerator','denominator')}]))
            if period in period_values:require(analysis._number(period_values[period])==analysis._number(o['value']),'Conflicting same-period facts cannot be silently selected together')
            period_values[period]=o['value']
            if row['metric']=='diluted_eps':require(len(u['numerator'])==1 and u['numerator'][0].startswith('iso4217:') and u['denominator']==['xbrli:shares'],'EPS requires currency/share units')
            elif row['metric']=='diluted_shares':require(u['numerator']==['xbrli:shares'] and not u['denominator'],'Share count requires shares')
            else:require(len(u['numerator'])==1 and u['numerator'][0].startswith('iso4217:') and not u['denominator'],'Monetary metric requires currency units')
            if row['metric'] in ('current_debt','noncurrent_debt','total_debt','debt_component','operating_leases','cash_and_equivalents','available_cash','credit_capacity'):require(period[0]=='instant','Balance requires filed instant')
            else:require(period[0]=='duration','Flow/EPS requires filed duration')
            if row['metric']=='capital_expenditure':require(analysis._number(o['value'])>=0,'Capex selection must use gross positive purchases; signed flows require explicit separate support')
        require(len(signatures)==1,'A row cannot mix entities, currencies, share classes or segments')
    gaps=set()
    for row in value['gaps']:
        require(set(row)=={'metric','reason','citations'} and row['metric'] in REQUIRED,'Known completeness gap required')
        require(row['metric'] not in gaps,'Duplicate completeness gap');gaps.add(row['metric']);text(row['reason']);citations(row['citations'])
    covered|={'gross_margin'} if {'gross_profit','revenue'}<=covered or {'cost_of_revenue','revenue'}<=covered else set()
    covered|={'total_debt'} if {'current_debt','noncurrent_debt'}<=covered else set()
    require(REQUIRED<=covered|gaps,'Every core metric and valuation input requires selection or a specific source-backed gap')
    require(not (covered&gaps),'Selected metrics cannot also be marked absent')
    for note in value['notes']:
        require(set(note)=={'text','citations'},'Exact financial definition note required');text(note['text']);citations(note['citations'])
    # Row definitions and notes are both validated, source-cited contract fields.
    # Do not require the author to duplicate a capex definition in a second field.
    conventions = [n['text'] for n in value['notes']] + [r['definition'] for r in value['rows']
        if r['metric'] in ('operating_cash_flow', 'capital_expenditure')]
    require(any(re.search(r'\b(?:free cash flow|fcf)\b',definition,re.I) and 'gross' in definition.lower() for definition in conventions)
            or not {'operating_cash_flow','capital_expenditure'}<=covered,'Explicit gross-capex FCF convention required')
    return value


def record(bundle,manifest,value):
    validate(value,bundle)
    return {'version':VERSION,'source_manifest_sha256':storage.sha(manifest),
            'financial_sha256':storage.digest(bundle['financial']),'selection':value}


def apply(bundle,value):
    """Attach a validated selection without mutating raw facts or contexts."""
    validate(value,bundle)
    from . import earnings_packet_inventory as packet_inventory
    result={**bundle,'financial_selection':deepcopy(value)}
    if value.get('reported_tables'):
        result['reported_tables']=packet_inventory.selected(value['reported_tables'],bundle)
    return result


def mapping(bundle):
    value=bundle.get('financial_selection')
    if value is None:return None
    validate(value,bundle)
    return {fid:{**row,'selection_group':number} for number,row in enumerate(value['rows']) for fid in row['fact_ids']}


def verify_record(bundle,manifest,value):
    require(value.get('version')==VERSION and value.get('source_manifest_sha256')==storage.sha(manifest)
            and value.get('financial_sha256')==storage.digest(bundle['financial']),'Frozen selection inputs changed')
    return apply(bundle,value['selection'])
