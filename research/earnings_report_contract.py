"""Shared report obligations and source-bound scalar arithmetic.

Semantic applicability and security/date interpretation remain independently reviewed.
This module checks coverage wiring, original extracted observations and arithmetic only.
"""
from decimal import Decimal, localcontext
from . import earnings_compact_evidence as evidence
from . import earnings_markdown_render as markdown

COVERAGE = {
    'comparison_basis': ('earnings', 'Identify material prior-period charges, gains, reclassifications and other distortions; quantify them when disclosed and explain how they affect the comparison. Include disclosed segment profit or adjusted EBITDA and margin changes when central to the operating thesis; label segment and non-GAAP basis. Distinguish source-reported changes from differences of rounded totals.'),
    'liquidity_perimeter': ('cash', 'Distinguish consolidated cash from usable operating/parent cash, restricted or regulated balances, and undrawn credit. Give separate disclosed amounts and any subsidiary reporting-date lag.'),
    'funding_needs': ('cash', 'Compare funding resources with near-term maturities, investment and shareholder distributions. Quantify material embedded financing separately from the selected debt/lease perimeter; do not double count. Reconcile updates across filings and the call using the latest supplied cutoff for each measure. Keep share counts, cash costs and remaining authorizations attached to their own dates; never combine later counts with earlier costs.'),
    'cash_flow_quality': ('cash', 'Explain material tax receipts/payments, working-capital or other temporary cash drivers. Compare the relevant operating cash flow with investment on the same segment, period and gross/net basis, quantifying disclosed scale.'),
    'guidance_basis': ('outlook', 'State the exact period, accounting basis, prior baseline, commitment strength and material financing progress behind the outlook. Separate guidance, aspiration and analyst inference.'),
}

def requirements():
    return {key:{'location':location,'requirement':text} for key,(location,text) in COVERAGE.items()}


def require(condition, message):
    if not condition: raise ValueError(message)


def validate(support, analysis, manifest):
    require(isinstance(support,dict) and set(support)=={'coverage','valuation'}, 'Exact report support fields required')
    require(isinstance(support['coverage'],dict) and set(support['coverage'])==set(COVERAGE), 'Every shared coverage obligation required')
    known=set(evidence._scopes(evidence.load_bundle(manifest)))
    for key,(location,_) in COVERAGE.items():
        row=support['coverage'][key]
        require(isinstance(row,dict) and set(row)=={'status','report_excerpt','reason','citations'}, 'Exact coverage fields required')
        require(row['status'] in ('addressed','not_material','unavailable'), 'Explicit coverage disposition required')
        require(isinstance(row['reason'],str) and row['reason'].strip(), 'Source-grounded coverage reason required')
        require(isinstance(row['citations'],list) and row['citations'] and set(row['citations'])<=known, 'Original coverage citations required')
        require(isinstance(row['report_excerpt'],str), 'Coverage excerpt must be text')
        if row['status']!='not_material':
            require(row['report_excerpt'].strip() and row['report_excerpt'] in analysis['sections'][location]['text'], 'Coverage must point to actual report text in '+location)
    valuation=support['valuation']
    require(isinstance(valuation,dict) and set(valuation)=={'rows','gap','citations'}, 'Exact valuation fields required')
    require(isinstance(valuation['rows'],list) and len(valuation['rows'])<=4, 'At most four matching-security multiples')
    require(isinstance(valuation['gap'],str), 'Valuation gap must be text')
    require(isinstance(valuation['citations'],list) and valuation['citations'] and set(valuation['citations'])<=known, 'Original valuation citations required')
    require(valuation['rows'] or valuation['gap'].strip(), 'Explain unavailable valuation inputs')
    if not valuation['rows']:return []
    from . import earnings_valuation_inventory as inventory
    bundle=evidence.load_bundle(manifest);available=inventory.build(bundle)
    computed=[];seen=set()
    for proposal in valuation['rows']:
        row=inventory.resolve(proposal,bundle,available);price=row['price'];eps=row['eps']
        require(isinstance(row['accounting_basis'],str) and row['accounting_basis'].strip(),'Explicit earnings accounting basis required')
        identity=(price['id'],eps['id']);require(identity not in seen,'Duplicate earnings multiple');seen.add(identity)
        with localcontext() as ctx:
            ctx.prec=40
            multiple=str((Decimal(price['value'])/Decimal(eps['value'])).quantize(Decimal('0.01'))) if Decimal(eps['value'])>0 else None
        values={}
        if eps.get('kind')=='annual_guidance':
            with localcontext() as ctx:
                ctx.prec=40
                values={'range_low':str((Decimal(price['value'])/Decimal(eps['high'])).quantize(Decimal('0.01'))),
                        'range_high':str((Decimal(price['value'])/Decimal(eps['low'])).quantize(Decimal('0.01')))}
        computed.append({**row,'multiple':multiple,**values})
    return computed


def render(support,analysis,manifest):
    computed=validate(support,analysis,manifest)
    lines=['### Dated earnings multiples','']
    if computed:
        lines+=['Historical source quotes below retain their actual dates; they are not current market prices.','',
                '| Security / share basis | Quote date | Price | Annual diluted EPS / basis | Earnings period | P/E |',
                '| --- | --- | --- | --- | --- | --- |']
        for row in computed:
            refs=markdown.refs([row['price']['source_id'],row['eps']['source_id']])
            forward=row['eps'].get('kind')=='annual_guidance'
            period=('FY'+str(row['eps']['fiscal_year'])+' management guidance, issued '+row['eps']['guidance_date']) if forward else 'annual '+row['eps']['period_start']+' – '+row['eps']['period_end']
            eps_value=(row['eps']['low']+'–'+row['eps']['high']) if forward else row['eps']['value']
            multiple=(row['range_low']+'–'+row['range_high']+'× forward; '+row['multiple']+'× midpoint') if forward else (row['multiple']+'×' if row['multiple'] is not None else 'N/M (nonpositive earnings)')
            values=[row['price']['symbol']+' / source share basis',row['price']['date'],row['price']['currency']+' '+row['price']['value'],eps_value+' / '+row['accounting_basis'],period,multiple+' '+refs]
            lines.append('| '+' | '.join(markdown.cell(v) for v in values)+' |')
        lines.append('')
    if not computed and support['valuation']['gap'].strip():lines += [support['valuation']['gap']+' '+markdown.refs(support['valuation']['citations']),'']
    return lines
