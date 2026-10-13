"""Mechanical starting rows from original consolidated observations; never acceptance."""
from datetime import date

def build(data):
    contexts=data['contexts'];rows=[]
    for metric in ('revenue','operating_income','net_income','diluted_eps','operating_cash_flow','cash_and_equivalents','assets'):
        candidates=[]
        for o in data['observations']:
            ctx=contexts.get(o.get('context_id'),{})
            if o.get('canonical_metric')!=metric or o.get('nil') or o.get('status')!='extracted' or ctx.get('dimensions'):continue
            end=ctx.get('end_date') or ctx.get('instant');start=ctx.get('start_date')
            if not end:continue
            if metric in ('revenue','operating_income','net_income','diluted_eps') and (not start or not 50<=(date.fromisoformat(end)-date.fromisoformat(start)).days<=110):continue
            candidates.append((o,ctx,end,start))
        if not candidates:continue
        current=max(x[2] for x in candidates);selected=[x for x in candidates if x[2]==current]
        first=min(selected,key=lambda x:(x[3] or '',x[0]['id']))
        comparable=[x for x in candidates if x[2]<current and x[0]['concept']==first[0]['concept'] and (x[3] is None)==(first[3] is None) and (x[3] is None or (x[3][5:],x[2][5:])==(first[3][5:],first[2][5:]))]
        facts=[first]
        if comparable:facts.append(max(comparable,key=lambda x:x[2]))
        rows.append({'label':metric.replace('_',' ').capitalize(),'fact_ids':[x[0]['id'] for x in facts],
                     'source_context':[{'id':x[0]['id'],'concept':x[0]['concept'],'start':x[3],'end_or_instant':x[2],'value':x[0]['value'],'scale':x[0]['scale'],'unit_id':x[0]['unit_id']} for x in facts]})
    return {'status':'mechanical_unreviewed_outline','rows':rows,'must_verify_original_scopes':True,'gap_count':len(data.get('gaps',[])),
            'scope':'Consolidated original candidates only. Author must verify and may change selection; no acceptance or comparability conclusion is implied.'}


def artifact(data):
    """Compile a draft financial handoff; independent semantic review stays mandatory."""
    outline=build(data)
    if len(outline['rows'])<4:raise ValueError('Fewer than four supported consolidated rows; explicit financial profile required')
    return {'rows':[{'label':r['label'],'fact_ids':r['fact_ids']} for r in outline['rows']], 'context':[],
            'gaps':['Original extraction gap: '+str(g.get('reason') or g.get('kind') or g.get('status') or g) for g in data.get('gaps',[])[:8]]}
