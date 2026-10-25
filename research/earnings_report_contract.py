"""Shared report obligations and source-bound scalar arithmetic.

Semantic applicability and security/date interpretation remain independently reviewed.
This module checks coverage wiring, exact original quotations and arithmetic only.
"""
from datetime import date
from decimal import Decimal, localcontext
import re
from . import earnings_compact_evidence as evidence
from . import earnings_markdown_render as markdown

COVERAGE = {
    'comparison_basis': ('earnings', 'Identify material prior-period charges, gains, reclassifications and other distortions; quantify them when disclosed and explain how they affect the comparison.'),
    'liquidity_perimeter': ('cash', 'Distinguish consolidated cash from usable operating/parent cash, restricted or regulated balances, and undrawn credit. Give separate disclosed amounts and any subsidiary reporting-date lag.'),
    'funding_needs': ('cash', 'Compare funding resources with near-term maturities, investment and shareholder distributions. Quantify material embedded financing separately from the selected debt/lease perimeter; do not double count.'),
    'cash_flow_quality': ('cash', 'Explain material tax receipts/payments, working-capital or other temporary cash drivers. Compare the relevant operating cash flow with investment on the same segment, period and gross/net basis, quantifying disclosed scale.'),
    'guidance_basis': ('outlook', 'State the exact period, accounting basis, prior baseline, commitment strength and material financing progress behind the outlook. Separate guidance, aspiration and analyst inference.'),
}

def requirements():
    return {key:{'location':location,'requirement':text} for key,(location,text) in COVERAGE.items()}


def require(condition, message):
    if not condition: raise ValueError(message)


def normalized(text): return ' '.join(text.split())


def scalar(item, manifest):
    require(isinstance(item,dict) and set(item)=={'source_id','quote','token','security','currency','share_basis'}, 'Exact source-bound scalar fields required')
    require(all(isinstance(v,str) and v.strip() for v in item.values()), 'Nonempty scalar identity and original quotation required')
    require(len(item['quote'])<=6000, 'Bounded original scalar quotation required')
    scopes=evidence.source_slices(manifest,[item['source_id']])
    quote=normalized(item['quote'])
    require(any(quote in normalized(span['text']) for record in scopes for span in record['spans']), 'Scalar quotation does not match original source scope')
    token=item['token']
    require(re.fullmatch(r'(?:-?\d+(?:,\d{3})*(?:\.\d+)?|\(\d+(?:,\d{3})*(?:\.\d+)?\))',token) is not None, 'Exact decimal scalar token required')
    require(re.search(r'(?<![\w.,(+\-])'+re.escape(token)+r'(?!\w|[.,]\d|\))',quote) is not None, 'Scalar token is not a complete number in its original quotation')
    require(re.fullmatch('[A-Z]{3}',item['currency']) is not None,'Explicit ISO currency required')
    amount=Decimal(token.replace(',','').strip('()')) * (-1 if token.startswith('(') else 1)
    require(amount.is_finite(),'Finite scalar required')
    return amount


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
    computed=[];seen=set()
    for row in valuation['rows']:
        require(isinstance(row,dict) and set(row)=={'price','eps','price_date','period_kind','period_start','period_end','accounting_basis'}, 'Exact earnings multiple fields required')
        price=scalar(row['price'],manifest);eps=scalar(row['eps'],manifest)
        require(price>0,'Positive trading price required')
        for key in ('security','currency','share_basis'):
            require(row['price'][key]==row['eps'][key], 'Price and EPS '+key+' must match')
        quoted=date.fromisoformat(row['price_date']);start=date.fromisoformat(row['period_start']);end=date.fromisoformat(row['period_end'])
        require(row['period_kind'] in ('annual','ttm','forward_annual'), 'Annual EPS only; no quarterly annualization')
        require(350<=(end-start).days+1<=380,'Full annual earnings period required')
        require((end>quoted) == (row['period_kind']=='forward_annual'), 'Earnings period must match reported/forward classification')
        require(isinstance(row['accounting_basis'],str) and row['accounting_basis'].strip(),'Explicit earnings accounting basis required')
        identity=(row['price']['security'],row['period_kind'],str(start),str(end),row['accounting_basis'])
        require(identity not in seen,'Duplicate earnings multiple');seen.add(identity)
        with localcontext() as ctx:
            ctx.prec=40
            multiple=str((price/eps).quantize(Decimal('0.01'))) if eps>0 else None
        computed.append({**row,'price_value':str(price),'eps_value':str(eps),'multiple':multiple})
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
            values=[row['price']['security']+' / '+row['price']['share_basis'],row['price_date'],row['price']['currency']+' '+row['price_value'],row['eps_value']+' / '+row['accounting_basis'],row['period_kind']+' '+row['period_start']+' – '+row['period_end'],(row['multiple']+'×' if row['multiple'] is not None else 'N/M (nonpositive earnings)')+' '+refs]
            lines.append('| '+' | '.join(markdown.cell(v) for v in values)+' |')
        lines.append('')
    if support['valuation']['gap'].strip():lines += [support['valuation']['gap']+' '+markdown.refs(support['valuation']['citations']),'']
    return lines
