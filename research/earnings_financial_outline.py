"""Mechanical starting rows from original consolidated observations; never acceptance."""
from datetime import date
from .financial_reviewed_proposals import usable

# Read-time aliases never rewrite frozen proposal records or their source basis.
IFRS_METRICS = {
 'ifrs-full:Revenue':'revenue',
 'ifrs-full:ProfitLossFromOperatingActivities':'operating_income',
 'ifrs-full:ProfitLossAttributableToOwnersOfParent':'net_income',
 'ifrs-full:DilutedEarningsLossPerShare':'diluted_eps',
 'ifrs-full:CashFlowsFromUsedInOperatingActivities':'operating_cash_flow',
 'ifrs-full:GrossProfit':'gross_profit',
 'ifrs-full:PurchaseOfPropertyPlantAndEquipment':'capital_expenditure',
 'ifrs-full:CashAndCashEquivalents':'cash_and_equivalents',
 'ifrs-full:Inventories':'inventory',
 'ifrs-full:Assets':'assets',
}

def build(data, *, expanded=False):
    contexts=data['contexts'];rows=[]
    metrics=('revenue','gross_profit','operating_income','net_income','diluted_eps','operating_cash_flow',
             'capital_expenditure','cash_and_equivalents','inventory','assets','liabilities','diluted_shares') if expanded else (
             'revenue','operating_income','net_income','diluted_eps','operating_cash_flow','cash_and_equivalents','assets')
    for metric in metrics:
        candidates=[]
        for o in data['observations']:
            ctx=contexts.get(o.get('context_id'),{})
            if (o.get('canonical_metric') or IFRS_METRICS.get(o.get('concept')))!=metric or o.get('nil') or not usable(o,data) or ctx.get('dimensions'):continue
            end=ctx.get('end_date') or ctx.get('instant');start=ctx.get('start_date')
            if not end:continue
            if metric in ('revenue','gross_profit','operating_income','net_income','diluted_eps','diluted_shares') and (not start or not 50<=(date.fromisoformat(end)-date.fromisoformat(start)).days<=110):continue
            candidates.append((o,ctx,end,start))
        if not candidates:continue
        current=max(x[2] for x in candidates);selected=[x for x in candidates if x[2]==current]
        first=min(selected,key=lambda x:((date.fromisoformat(x[2])-date.fromisoformat(x[3])).days if x[3] and (expanded or x[0]['concept'] in IFRS_METRICS) else 0,x[3] or '',x[0]['id']))
        comparable=[x for x in candidates if x[2]<current and x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and (x[3] is None)==(first[3] is None) and (x[3] is None or (x[3][5:],x[2][5:])==(first[3][5:],first[2][5:]))]
        facts=[first]
        if comparable:facts.append(max(comparable,key=lambda x:x[2]))
        if (expanded or first[0]['concept'] in IFRS_METRICS) and first[3] and 70<=(date.fromisoformat(first[2])-date.fromisoformat(first[3])).days+1<=105:
            previous=[x for x in candidates if x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and x[3] and 50<=(date.fromisoformat(x[2])-date.fromisoformat(x[3])).days<=110 and (date.fromisoformat(first[3])-date.fromisoformat(x[2])).days==1]
            if previous:
                q=max(previous,key=lambda x:x[2])
                if q not in facts:facts.append(q)
        if expanded and first[3] is None:
            previous=[x for x in candidates if x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and x[3] is None and 70<=(date.fromisoformat(current)-date.fromisoformat(x[2])).days<=105]
            if previous:
                q=max(previous,key=lambda x:x[2])
                if q not in facts:facts.append(q)
        rows.append({'label':metric.replace('_',' ').capitalize(),'fact_ids':[x[0]['id'] for x in facts],
                     'source_context':[{'id':x[0]['id'],'concept':x[0]['concept'],'start':x[3],'end_or_instant':x[2],'value':x[0]['value'],'scale':x[0].get('scale','0'),'unit_id':x[0]['unit_id']} for x in facts]})
    return {'status':'mechanical_unreviewed_outline','rows':rows,'must_verify_original_scopes':True,'gap_count':len(data.get('gaps',[])),
            'scope':'Consolidated original candidates only. Author must verify and may change selection; no acceptance or comparability conclusion is implied.'}


def artifact(data, *, expanded=False):
    """Compile a draft financial handoff; independent semantic review stays mandatory."""
    outline=build(data, expanded=expanded)
    if len(outline['rows'])<4:raise ValueError('Fewer than four supported consolidated rows; explicit financial profile required')
    return {'rows':[{'label':r['label'],'fact_ids':r['fact_ids']} for r in outline['rows']], 'context':[],
            'gaps':['Original extraction gap: '+str(g.get('reason') or g.get('kind') or g.get('status') or g) for g in data.get('gaps',[])[:8]]}
