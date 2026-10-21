"""Mechanical starting rows from original consolidated observations; never acceptance."""
from datetime import date
from .financial_reviewed_proposals import usable
from .earnings_period_comparisons import year_ago

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

# Selection preferences, not taxonomy aliases. These are literal reviewed source
# labels; the resulting rows retain those labels and never acquire GAAP metrics.
# The complete observation inventory remains available to authors and reviewers.
NATIVE_STARTING_LABELS = (
 'Revenue', 'Gross margin', 'Operating income', 'Net earnings',
 'Earnings per share – diluted',
 'Cash provided by (used in) operating activities',
 'Cash and cash equivalents', 'Total assets', 'Total liabilities',
 'Long-term debt', 'PP&E', 'Dividends',
)

# A separate literal label family; never merge alternatives into more than twelve
# starting rows or map upper-case native labels to taxonomy concepts.
UPPERCASE_NATIVE_STARTING_LABELS = (
 'REVENUE', 'Net fee revenue', 'Interest revenue', 'Retail revenue',
 'NET INCOME', 'Diluted (KZT)', 'Cash and cash equivalents',
 'TOTAL ASSETS', 'TOTAL LIABILITIES', 'TOTAL EQUITY',
 'Net cash inflow from operating activities',
 'Purchase of property, equipment and intangible assets',
)

def native_reviewed_rows(data, labels=NATIVE_STARTING_LABELS):
    """Bounded draft selection from literal independently reviewed table labels.

    No concept/name similarity or numeric inference is used. Ambiguous source
    identities, units or accounting bases fail closed for the affected label.
    """
    rows=[]
    for label in labels:
        candidates=[]
        for o in data['observations']:
            ctx=data['contexts'].get(o.get('context_id'),{})
            if (o.get('method')!='reviewed_html_table' or not usable(o,data)
                or o.get('nil') or ctx.get('dimensions')
                or o.get('support',{}).get('source_label')!=label):continue
            end=ctx.get('end_date') or ctx.get('instant');start=ctx.get('start_date')
            if not end or not o.get('accounting_basis'):continue
            candidates.append((o,ctx,end,start))
        identities={(x[0].get('concept'),x[0].get('unit_id'),
                     x[0].get('accounting_basis'),x[0].get('source_document_id'),
                     x[1].get('entity'),bool(x[3])) for x in candidates}
        if len(identities)!=1:continue
        current=max(x[2] for x in candidates)
        latest=[x for x in candidates if x[2]==current]
        first=min(latest,key=lambda x:((date.fromisoformat(x[2])-date.fromisoformat(x[3])).days if x[3] else 0,x[0]['id']))
        # Duplicate observations of the same period are not arbitrarily resolved.
        if sum(x[3]==first[3] for x in latest)!=1:continue
        facts=[first]
        a=['duration',first[3],first[2]] if first[3] else ['instant',first[2]]
        prior=[x for x in candidates if x[2]<current and year_ago(a,
            ['duration',x[3],x[2]] if x[3] else ['instant',x[2]])]
        if prior:
            end=max(x[2] for x in prior);matches=[x for x in prior if x[2]==end]
            if len(matches)==1:facts.append(matches[0])
        rows.append({'label':label,'fact_ids':[x[0]['id'] for x in facts]})
    return rows

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
        def annual_match(x):
            if expanded:
                a=['duration',first[3],first[2]] if first[3] else ['instant',first[2]]
                b=['duration',x[3],x[2]] if x[3] else ['instant',x[2]]
                return year_ago(a,b)
            return x[3] is None or (x[3][5:],x[2][5:])==(first[3][5:],first[2][5:])
        comparable=[x for x in candidates if x[2]<current and x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and (x[3] is None)==(first[3] is None) and annual_match(x)]
        facts=[first]
        if comparable:facts.append(max(comparable,key=lambda x:x[2]))
        if (expanded or first[0]['concept'] in IFRS_METRICS) and first[3] and 70<=(date.fromisoformat(first[2])-date.fromisoformat(first[3])).days+1<=105:
            previous=[x for x in candidates if x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and x[3] and 50<=(date.fromisoformat(x[2])-date.fromisoformat(x[3])).days<=110 and (date.fromisoformat(first[3])-date.fromisoformat(x[2])).days==1]
            if previous:
                q=max(previous,key=lambda x:x[2])
                if q not in facts:facts.append(q)
        if expanded and first[3] is None:
            previous=[x for x in candidates if x[0]['concept']==first[0]['concept'] and x[0]['unit_id']==first[0]['unit_id'] and x[1].get('entity')==first[1].get('entity') and x[3] is None and x[2]<current]
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
    if expanded and len(outline['rows'])<4:
        outline['rows']=native_reviewed_rows(data)
        if len(outline['rows'])<4:
            outline['rows']=native_reviewed_rows(data,UPPERCASE_NATIVE_STARTING_LABELS)
    if len(outline['rows'])<4:raise ValueError('Fewer than four supported consolidated rows; explicit financial profile required')
    return {'rows':[{'label':r['label'],'fact_ids':r['fact_ids']} for r in outline['rows']], 'context':[],
            'gaps':['Original extraction gap: '+str(g.get('reason') or g.get('kind') or g.get('status') or g) for g in data.get('gaps',[])[:8]]}
