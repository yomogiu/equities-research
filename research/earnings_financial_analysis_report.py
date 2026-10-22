"""Table-first deterministic financial preview and opt-in report integration.

Consumes a frozen evidence manifest. Never launches a model, qualifies a new
observation, or treats a computed preview as an accepted research report.
"""
from datetime import date
from decimal import Decimal, localcontext
import json
from pathlib import Path
from . import earnings_financial_analysis as analysis
from . import earnings_financial_display as display
from . import earnings_markdown as markdown
from . import earnings_mixed_runner as base

HEADERS=['Metric','Unit / basis','Current','Prior quarter','Prior year','QoQ Δ / change','YoY Δ / change']
FAMILIES={'quarter':'Quarter','half':'Six-month duration','nine-month':'Nine-month duration',
          'annual':'Annual','instant':'Point-in-time balances','other':'Other reported duration'}
EARNINGS={'gross_profit','cost_of_revenue','operating_income','net_income','diluted_eps','diluted_shares',
          'gross_margin','operating_margin','net_margin','ebitda','ebitda_margin'}
CASH={'operating_cash_flow','capital_expenditure','cash_and_equivalents','inventory','assets','liabilities',
      'short_term_investments','current_debt','noncurrent_debt',*analysis.DERIVED.keys()}
EXPENSE_CONCEPTS={
    'us-gaap:CostOfRevenue','us-gaap:CostOfGoodsAndServicesSold','us-gaap:CostOfGoodsSold',
    'us-gaap:ResearchAndDevelopmentExpense','us-gaap:SellingGeneralAndAdministrativeExpense',
    'us-gaap:OperatingExpenses','us-gaap:InterestExpense','us-gaap:InterestExpenseNonOperating',
    'us-gaap:IncomeTaxExpenseBenefit','us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
    'us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
    'us-gaap:OtherNonoperatingIncomeExpense','us-gaap:IncomeLossFromContinuingOperations',
    'ifrs-full:CostOfSales','ifrs-full:ResearchAndDevelopmentExpense','ifrs-full:AdministrativeExpense',
    'ifrs-full:SellingExpense','ifrs-full:FinanceCosts','ifrs-full:IncomeTaxExpenseContinuingOperations',
    'ifrs-full:ProfitLossBeforeTax',
}
METRIC_LABELS={metric:metric.replace('_',' ').capitalize() for metric in analysis.CONCEPTS.values()}
METRIC_LABELS.update({metric:item[0] for metric,item in analysis.DERIVED.items()})
METRIC_LABELS.update(diluted_eps='Diluted EPS')


def metric_label(row):
    source=display.strip_terminal_dot_leader(row['label'])
    concept=row.get('concepts',[''])[0]
    friendly=METRIC_LABELS.get(row['metric_id'],display.humanize(concept))
    members={display.humanize(d.get('member') or d.get('value') or d.get('text') or '') for d in row.get('dimensions',[])}
    if source in members:return friendly
    if source in ('Total','TOTAL','Diluted','DILUTED'):return friendly+' · '+source
    if source in (concept,concept.partition(':')[2],display.humanize(concept)):return friendly
    # Qualified attribution and adjustment words are source meaning, not styling.
    return source


def basis_label(row):
    basis=str(row.get('basis') or 'basis not stated')
    if row.get('derived'):basis='Calculated · '+basis+' inputs'
    return basis+' (assumed)' if row.get('basis_origin')=='caller_declared' else basis


def configuration(start,end,capex_conventions=None,accounting_bases=None):
    begin,finish=date.fromisoformat(start),date.fromisoformat(end)
    if not 70<=(finish-begin).days+1<=105:raise ValueError('Explicit quarter start/end dates required')
    conventions={} if capex_conventions is None else capex_conventions
    if not isinstance(conventions,dict) or any(not isinstance(k,str) or not k or v not in ('signed_cash_flow','positive_payment') for k,v in conventions.items()):
        raise ValueError('Explicit per-fact capital-expenditure sign conventions required')
    bases={} if accounting_bases is None else accounting_bases
    if not isinstance(bases,dict) or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v.strip() for k,v in bases.items()):
        raise ValueError('Explicit per-fact source-reviewed accounting bases required')
    return {'version':analysis.VERSION,'current_period':['duration',start,end],'as_of':end,'capex_conventions':dict(conventions),'accounting_bases':dict(bases)}


def validate_configuration(value):
    if not isinstance(value,dict) or set(value)!={'version','current_period','as_of','capex_conventions','accounting_bases'}:
        raise ValueError('Exact deterministic financial analysis configuration required')
    period=value['current_period']
    if not isinstance(period,list) or len(period)!=3 or period[0]!='duration':
        raise ValueError('Explicit fiscal quarter dates required')
    if value!=configuration(period[1],period[2],value['capex_conventions'],value['accounting_bases']):raise ValueError('Financial analysis version or as-of anchor changed')
    return value


def compile(bundle,config):
    validate_configuration(config)
    return analysis.build(bundle,current_period=config['current_period'],as_of=config['as_of'],
                          capex_conventions=config['capex_conventions'],accounting_bases=config['accounting_bases'])


def verified(bundle):
    config=validate_configuration(bundle['financial_analysis_config'])
    value=bundle['financial_analysis']
    if value!=compile(bundle,config):raise ValueError('Computed financial analysis differs from source observations')
    return value


def handoff(value):
    """Small read-only table view; original observations already live in evidence."""
    tables=[]
    for table in value['tables']:
        rows=[]
        for row in table['rows']:
            cells={key:{k:v for k,v in item.items() if k in ('status','value','period','fact_ids','reason')}
                   for key,item in row['cells'].items()}
            rows.append({k:v for k,v in row.items() if k in ('metric_id','label','unit','basis','basis_origin','derived','dimensions','changes')}|{'cells':cells})
        tables.append({'period_family':table['period_family'],'rows':rows})
    return {'version':value['version'],'source_computation_sha256':base.digest(value),'as_of':value['as_of'],
            'current_period':value['current_period'],'tables':tables,'gaps':value.get('gaps',[]),'read_only':True}


def section(row):
    metric=row['metric_id']
    if metric=='revenue':return 'demand'
    if metric in EARNINGS or set(row.get('concepts',[]))&EXPENSE_CONCEPTS:return 'earnings'
    return 'cash' if metric in CASH else 'other'


def unit_display(unit):
    nums,dens=unit['numerator'],unit['denominator']
    if len(nums)==1 and nums[0].startswith('iso4217:'):
        currency=nums[0].partition(':')[2]
        if not dens:return currency+' millions',Decimal(1000000)
        if dens==['xbrli:shares']:return currency+'/share',Decimal(1)
    if nums==['xbrli:shares'] and not dens:return 'million shares',Decimal(1000000)
    if nums==['percent'] and not dens:return '%',Decimal(1)
    return ' × '.join(nums)+('/'+' × '.join(dens) if dens else ''),Decimal(1)


def number(value,divisor=Decimal(1),*,signed=False,places=None):
    amount=Decimal(value)
    if not amount.is_finite():raise ValueError('Finite computed financial value required')
    with localcontext() as ctx:
        ctx.prec=max(50,len(amount.as_tuple().digits)+abs(amount.adjusted())+12)
        scaled=amount/divisor
        if places is not None:
            rounded=scaled.quantize(Decimal(1).scaleb(-places))
            if rounded or not scaled:scaled=rounded
    text=display.format_number(scaled)
    return ('+' if signed and scaled>0 else '')+text


def calculation_text(value):
    """Keep the complete exact arithmetic trace in JSON and a readable formula."""
    if not value:return ''
    if isinstance(value,str):return value
    if isinstance(value,list):return ', '.join(calculation_text(v) for v in value)
    if not isinstance(value,dict):return str(value)
    if value.get('calculation'):return calculation_text(value['calculation'])
    operator=value.get('operator')
    if operator=='reported':return str(value['fact_id'])
    if operator:
        operands=value.get('operands',[])
        if isinstance(operands,dict):operands=list(operands.values())
        return str(operator)+'('+', '.join(calculation_text(v) for v in operands)+')'
    ids=value.get('fact_ids',[])
    if ids:return ', '.join(ids)
    return str(value.get('value',value.get('fact_id',value.get('id','source operand'))))


def value_cell(value,divisor,*,percentage=False):
    if value['status']!='available':
        return '—'
    return number(value['value'],divisor,places=2)+' '+markdown.refs(value.get('fact_ids',[]))


def change_cell(value,divisor,unit):
    citations=markdown.refs(value.get('fact_ids',[]))
    parts=[]
    if value.get('absolute') is not None:
        pp=value.get('kind')=='percentage_points'
        parts.append(number(value['absolute'],Decimal(1) if pp else divisor,signed=True,places=2)+(' pp' if pp else ''))
    if value.get('percent') is not None:
        parts.append(number(value['percent'],signed=True,places=2)+'%')
    elif value.get('kind')!='percentage_points':
        parts.append('N/M' if value['status']=='not_meaningful' else '—')
    elif value['status']!='available':parts.append('—')
    return ' / '.join(parts)+' '+citations


def sections(value):
    result={key:[] for key in ('demand','earnings','cash','outlook','qa','other')}
    for table in value['tables']:
        for target in ('demand','earnings','cash','other'):
            rows=[row for row in table['rows'] if section(row)==target and
                  (not row.get('derived') or any(cell['status']=='available' for cell in row['cells'].values()))]
            if not rows:continue
            lines=result[target]
            dates=[]
            for key,label in (('current','Current'),('prior_quarter','Prior quarter'),('prior_year','Prior year')):
                found=sorted({tuple(row['cells'][key]['period']) for row in rows if row['cells'][key].get('period')})
                if found:dates.append(label+': '+', '.join(display.period_label(p) for p in found))
            lines.extend(['### '+FAMILIES.get(table['period_family'],table['period_family']), '', ' · '.join(dates),'',
                          '| '+' | '.join(HEADERS)+' |','| '+' | '.join('---' for _ in HEADERS)+' |'])
            for row in rows:
                unit,divisor=unit_display(row['unit'])
                dimensions=display.dimensions_label(row.get('dimensions',[]))
                label=metric_label(row)+(' · '+dimensions if dimensions else '')
                values=[label,unit+' · '+basis_label(row),
                        *(value_cell(row['cells'][key],divisor,percentage=unit=='%') for key in ('current','prior_quarter','prior_year')),
                        *(change_cell(row['changes'][key],divisor,unit) for key in ('qoq','yoy'))]
                lines.append('| '+' | '.join(markdown.cell(v) for v in values)+' |')
            lines.extend(['','Δ / change: absolute change in the row’s unit / relative %. Margin changes use percentage points (pp). — unavailable; N/M nonpositive comparison base.',''])
            other=[]
            for row in rows:
                shown={tuple(c['period']) for c in row['cells'].values() if c.get('period') and c['status']=='available'}
                for observed in row.get('period_observations',[]):
                    if tuple(observed.get('period') or []) in shown:continue
                    other.append((row,observed))
            if other:
                lines.extend(['Other reported periods — these are not promoted to quarter or year comparators.','',
                    '| Metric | Unit / basis | Period | Value and source |','| --- | --- | --- | --- |'])
                for row,observed in other:
                    unit,divisor=unit_display(row['unit']);dimensions=display.dimensions_label(row.get('dimensions',[]))
                    label=metric_label(row)+(' · '+dimensions if dimensions else '')
                    values=[label,unit+' · '+basis_label(row),
                            display.period_label(observed['period']) if observed.get('period') else 'Unspecified',
                            value_cell(observed,divisor,percentage=unit=='%')]
                    lines.append('| '+' | '.join(markdown.cell(v) for v in values)+' |')
                lines.append('')
    return result


def notes(value):
    result=[];seen=set()
    for table in value['tables']:
        for row in table['rows']:
            label=metric_label(row)+' ('+FAMILIES.get(table['period_family'],table['period_family'])+')'
            source_labels=sorted({s for cell in row.get('period_observations',[]) for s in cell.get('source_labels',[])})
            if source_labels and source_labels!=[metric_label(row)]:
                text=label+' · source row labels: '+'; '.join(display.strip_terminal_dot_leader(s) for s in source_labels)
                if text not in seen:seen.add(text);result.append('- '+text)
            for slot,cell in row['cells'].items():
                calculation=cell.get('calculation')
                reason=cell.get('reason') if cell['status']!='available' else None
                formula=calculation_text(calculation) if calculation and calculation.get('operator')!='reported' else None
                if formula or reason:
                    text=label+' · '+slot.replace('_',' ')+': '+('derived as '+formula if formula else str(reason))
                    if text not in seen:seen.add(text);result.append('- '+text+' '+markdown.refs(cell.get('fact_ids',[])))
            for slot,change in row['changes'].items():
                if change.get('reason'):
                    text=label+' · '+slot.upper()+': '+str(change['reason'])
                    if text not in seen:seen.add(text);result.append('- '+text)
    for gap in value.get('gaps',[]):
        text=str(gap.get('reason',gap)) if isinstance(gap,dict) else str(gap)
        if text not in seen:
            seen.add(text);result.append('- '+text+' '+markdown.refs(gap.get('fact_ids',[]) if isinstance(gap,dict) else []))
    return result


def preview_markdown(value):
    from . import earnings_report_template as template
    rendered=sections(value)
    lines=['# Deterministic financial analysis','',
           'Quarter: '+display.period_label(value['current_period'])+'. As of: '+value['as_of']+'.','',
           'Source-derived calculations; no financial model prose or report acceptance is implied.','']
    for key in ('demand','earnings','cash'):
        lines.extend(['## '+template.SECTIONS[key],'',*rendered[key]])
        if not rendered[key]:lines.extend(['No supported metric observations for this section.',''])
    if rendered['other']:lines.extend(['## Other financial statement items','',*rendered['other']])
    lines.extend(['## Calculation and data notes','','Values are displayed to two decimal places. Exact values, source labels, observations, sign conventions and full calculation traces are retained in financial-analysis.json.','',*notes(value),''])
    lines.extend(['## Source references',''])
    import re
    identifiers=sorted(set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]', '\n'.join(lines))))
    lines.extend('[^'+identifier+']: Original evidence '+identifier for identifier in identifiers)
    return '\n'.join(lines).rstrip()+'\n'


def preview(manifest,output,*,quarter_start,quarter_end,config=None):
    from . import earnings_compact_evidence as evidence
    config=configuration(quarter_start,quarter_end) if config is None else validate_configuration(config)
    if config['current_period']!=['duration',quarter_start,quarter_end]:raise ValueError('CLI quarter differs from frozen analysis configuration')
    bundle=evidence.load_bundle(Path(manifest));value=compile(bundle,config)
    text=preview_markdown(value);page=markdown.render(text)
    root=Path(output);contents={'financial-analysis-config.json':json.dumps(config,ensure_ascii=False,sort_keys=True,indent=2)+'\n',
                                'financial-analysis.json':json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',
                                'financial-analysis.md':text,'financial-analysis.html':page}
    for name,content in contents.items():
        path=root/name
        if path.exists() and path.read_text()!=content:raise ValueError('Existing financial preview differs; choose a new output directory')
    root.mkdir(parents=True,exist_ok=True)
    for name,content in contents.items():(root/name).write_text(content)
    return {'version':analysis.VERSION,'output':str(root.resolve()),'model_calls':0,
            'files':{name:base.sha(root/name) for name in contents}}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--quarter-start',required=True)
    parser.add_argument('--quarter-end',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,help='Optional exact version, quarter, as-of, per-fact capex convention and accounting basis configuration JSON')
    args=parser.parse_args()
    print(json.dumps(preview(args.manifest,args.output,quarter_start=args.quarter_start,quarter_end=args.quarter_end,
                            config=base.read(args.config) if args.config else None),indent=2))

if __name__=='__main__':main()
