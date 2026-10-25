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
from . import earnings_markdown_render as markdown
from . import earnings_runtime_common as base

HEADERS=['Metric','Unit / basis','Current','Prior quarter','Prior year','QoQ Δ / change','YoY Δ / change']
FAMILIES={'quarter':'Quarter','half':'Six-month duration','nine-month':'Nine-month duration',
          'annual':'Annual','instant':'Point-in-time balances','other':'Other reported duration'}
EARNINGS={'gross_profit','cost_of_revenue','operating_income','net_income','diluted_eps','diluted_shares',
          'gross_margin','operating_margin','net_margin','ebitda','ebitda_margin'}
DEBT_COMPONENT_NAMES = {
    'current_debt_and_capital_leases':'Current portion of long-term debt and capital leases',
    'long_term_debt_and_capital_leases':'Long-term debt and capital leases (filed balance)',
    'short_term_borrowings':'Short-term borrowings',
}
CASH={*DEBT_COMPONENT_NAMES,'operating_cash_flow','capital_expenditure','cash_and_equivalents','inventory','assets','liabilities',
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
    if row['metric_id'] in DEBT_COMPONENT_NAMES: return DEBT_COMPONENT_NAMES[row['metric_id']]
    source=display.strip_terminal_dot_leader(row['label'])
    concept=row.get('concepts',[''])[0]
    friendly=METRIC_LABELS.get(row['metric_id'],display.humanize(concept))
    members={display.humanize(d.get('member') or d.get('value') or d.get('text') or '') for d in row.get('dimensions',[])}
    if source=='Diluted eps' and row['metric_id']=='diluted_eps':return 'Diluted EPS'
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
    value = analysis.build(bundle,current_period=config['current_period'],as_of=config['as_of'],
                          capex_conventions=config['capex_conventions'],accounting_bases=config['accounting_bases'])
    if bundle.get('financial_source_policy') == 'filed-statement-repair-v1':
        from . import earnings_reported_comparatives
        value = earnings_reported_comparatives.supplement(value, bundle)
    return value


def verified(bundle):
    config=validate_configuration(bundle['financial_analysis_config'])
    value=bundle['financial_analysis']
    if value!=compile(bundle,config):raise ValueError('Computed financial analysis differs from source observations')
    return value


def handoff(value):
    """Small read-only table view; original observations already live in evidence."""
    tables=[]
    selected=front_rows(value)
    chosen={id(row) for rows in selected.values() for _,row in rows}
    for table in value['tables']:
        rows=[]
        for row in table['rows']:
            if id(row) not in chosen:continue
            cells={key:{k:v for k,v in item.items() if k in ('status','value','period','fact_ids','reason')}
                   for key,item in row['cells'].items()}
            rows.append({k:v for k,v in row.items() if k in ('metric_id','label','entity','entity_scheme','unit','basis','basis_origin','derived','dimensions','changes')}|{'cells':cells})
        if rows:tables.append({'period_family':table['period_family'],'rows':rows})
    return {'version':value['version'],'source_computation_sha256':base.digest(value),'as_of':value['as_of'],
            'current_period':value['current_period'],'tables':tables,
            'gaps':[gap for key in FRONT_METRICS if (gap:=front_gaps(selected,key))],
            'inventory_scope':'Core consolidated selection; complete inventory and lineage are in financial-analysis.json.',
            'read_only':True}


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


# Display policy only: exact roles do not qualify observations or authorize new arithmetic.
FRONT_METRICS={
    'demand':('revenue',),
    'earnings':('diluted_eps','gross_margin','research_and_development','diluted_shares',
                'operating_income','operating_margin','net_income'),
    'cash':('free_cash_flow','operating_cash_flow','total_debt','current_debt','noncurrent_debt',
            'cash_and_equivalents', *DEBT_COMPONENT_NAMES),
}
DISPLAY_CONCEPTS={
    'us-gaap:ResearchAndDevelopmentExpense':'research_and_development',
    'ifrs-full:ResearchAndDevelopmentExpense':'research_and_development',
}
COMMENTARY_CONCEPTS={
    'us-gaap:InterestExpense','us-gaap:InterestExpenseNonOperating','ifrs-full:FinanceCosts',
    'us-gaap:OtherNonoperatingIncomeExpense','us-gaap:InvestmentIncomeInterest',
}
FRONT_HEADINGS={'demand':'Growth & Demand','earnings':'Profits & Margins','cash':'Cash & Financial Capacity'}
FRONT_NAMES={**METRIC_LABELS,'research_and_development':'Research and development',
             'total_debt':'Total debt','free_cash_flow':'Free cash flow'}


def front_role(row):
    return DISPLAY_CONCEPTS.get(row['metric_id'],row['metric_id'])


DISPLAY_SELECTION_VERSION='source-bound-financial-display-selection-v1'


def display_selection(value,fact_ids):
    if (not isinstance(fact_ids,(list,tuple)) or not fact_ids or
            any(not isinstance(fid,str) or not fid for fid in fact_ids) or len(set(fact_ids))!=len(fact_ids)):
        raise ValueError('Distinct explicit debt disclosure fact IDs required')
    selected={'version':DISPLAY_SELECTION_VERSION,'source_computation_sha256':base.digest(value),
              'debt_disclosure_fact_ids':list(fact_ids)}
    disclosure_rows(value,selected)
    return selected


def disclosure_rows(value,selection):
    if selection is None:return []
    if (not isinstance(selection,dict) or set(selection)!={'version','source_computation_sha256','debt_disclosure_fact_ids'}
            or selection['version']!=DISPLAY_SELECTION_VERSION or selection['source_computation_sha256']!=base.digest(value)):
        raise ValueError('Display selection differs from frozen financial computation')
    ids=selection['debt_disclosure_fact_ids']
    if not isinstance(ids,list) or not ids or any(not isinstance(fid,str) or not fid for fid in ids) or len(set(ids))!=len(ids):
        raise ValueError('Distinct explicit debt disclosure fact IDs required')
    result=[]
    for fid in ids:
        matches=[row for table in value['tables'] if table['period_family']=='instant' for row in table['rows']
                 if not row.get('dimensions') and not row.get('derived')
                 and row['cells']['current']['status']=='available'
                 and row['cells']['current'].get('period')==['instant',value['as_of']]
                 and fid in row['cells']['current'].get('fact_ids',[])]
        if len(matches)!=1:raise ValueError('Debt disclosure fact must identify one available current consolidated reported balance: '+fid)
        if not any(matches[0] is row for row in result):result.append(matches[0])
    return result


def front_identity(row):
    return base.digest([row.get('entity'),row.get('entity_scheme'),row.get('basis'),
                        row.get('basis_origin'),row.get('unit')])


def front_rows(value,selection=None):
    """Prefer durations only within the same entity, currency and accounting basis."""
    if value.get('financial_selection') is not None:
        result={key:[] for key in FRONT_METRICS}
        for table in value['tables']:
            for row in table['rows']:
                role=front_role(row)
                target = ('demand' if role=='revenue' else 'earnings' if role in EARNINGS or role=='research_and_development' else 'cash')
                if role=='interest_expense':continue
                if row['cells']['current']['status']!='available':continue
                if row.get('selected') or role in ('gross_margin','operating_margin','free_cash_flow','total_debt'):
                    result[target].append((table['period_family'],row))
        return result
    inventory=[(table['period_family'],row) for table in value['tables'] for row in table['rows']
               if not row.get('dimensions')]
    result={key:[] for key in FRONT_METRICS}
    for target,roles in FRONT_METRICS.items():
        if target == 'cash' and value.get('source_policy') in ('filed-statement-context-v1', 'filed-statement-repair-v1'):
            roles = ('free_cash_flow','operating_cash_flow','capital_expenditure',*roles[2:])
        for role in roles:
            candidates=[(family,row) for family,row in inventory if front_role(row)==role]
            families=('quarter',) if target!='cash' else (
                ('instant',) if role in ('total_debt','current_debt','noncurrent_debt','cash_and_equivalents', *DEBT_COMPONENT_NAMES)
                else ('quarter','nine-month','half','annual'))
            if role == 'capital_expenditure':
                flow_families = [family for family,row in result['cash'] if front_role(row) in ('free_cash_flow','operating_cash_flow')]
                if flow_families: families = tuple(dict.fromkeys(flow_families))
            identities=sorted({front_identity(row) for _,row in candidates})
            for identity in identities:
                for family in families:
                    chosen=[(f,row) for f,row in candidates if f==family and front_identity(row)==identity]
                    if any(row['cells']['current']['status']=='ambiguous' for _,row in chosen):break
                    available=[(f,row) for f,row in chosen if row['cells']['current']['status']=='available']
                    if available:
                        result[target].extend(available);break
    # Suppress only components covered by the same entity/unit/basis total.
    totals={front_identity(row) for _,row in result['cash'] if front_role(row)=='total_debt'}
    result['cash']=[(f,row) for f,row in result['cash'] if front_role(row) not in ('current_debt','noncurrent_debt')
                   or front_identity(row) not in totals]
    for row in disclosure_rows(value,selection):
        if not any(row is present for _,present in result['cash']):result['cash'].append(('instant',row))
    return result


def front_gaps(selected,target):
    present={front_role(row) for _,row in selected[target]}
    required={'demand':('revenue',),
              'earnings':('diluted_eps','gross_margin','research_and_development','diluted_shares'),
              'cash':('free_cash_flow','operating_cash_flow','total_debt')}[target]
    missing=[FRONT_NAMES[role] for role in required if role not in present]
    return ('Current consolidated metrics unavailable: '+', '.join(missing)+
            '.') if missing else ''


def earnings_commentary(value):
    sentences=[]
    for table in value['tables']:
        if table['period_family']!='quarter':continue
        for row in table['rows']:
            if row.get('dimensions') or not set(row.get('concepts',[]))&COMMENTARY_CONCEPTS:continue
            current=row['cells']['current'];prior=row['cells']['prior_year']
            if current['status']!='available':continue
            unit,divisor=unit_display(row['unit'])
            text=metric_label(row)+': '+value_cell(current,divisor)+' '+unit
            if prior['status']=='available':text+=' versus '+value_cell(prior,divisor)+' in the prior-year quarter'
            sentences.append(text+' ('+basis_label(row)+').')
    return sentences


def sections(value,selection=None):
    result={key:[] for key in ('demand','earnings','cash','outlook','qa','other')}
    selected=front_rows(value,selection)
    disclosure_ids={id(row) for row in disclosure_rows(value,selection)}
    entities={row.get('entity') for rows in selected.values() for _,row in rows}
    for target in ('demand','earnings','cash'):
        lines=result[target]
        for family in ('quarter','half','nine-month','annual','instant'):
            rows=[row for f,row in selected[target] if f==family]
            if not rows:continue
            dates=[]
            for key,label in (('current','Current'),('prior_quarter','Prior quarter'),('prior_year','Prior year')):
                found=sorted({tuple(row['cells'][key]['period']) for row in rows if row['cells'][key].get('period')})
                if found:dates.append(label+': '+', '.join(display.period_label(p) for p in found))
            family_name=({'half':'Six-month cash flow','nine-month':'Nine-month cash flow'}.get(family,FAMILIES[family]) if target=='cash' else FAMILIES[family])
            headers=HEADERS if family in ('quarter','instant') else [*HEADERS[:3],'Prior year',HEADERS[-1]]
            slots=('current','prior_quarter','prior_year') if family in ('quarter','instant') else ('current','prior_year')
            changes=('qoq','yoy') if family in ('quarter','instant') else ('yoy',)
            if family not in ('quarter','instant'):dates=[d for d in dates if not d.startswith('Prior quarter:')]
            if family=='instant':
                comparators=[(slot,change,title,delta) for slot,change,title,delta in
                    (('prior_quarter','qoq','Prior quarter',HEADERS[-2]),('prior_year','yoy','Prior year',HEADERS[-1]))
                    if any(row['cells'][slot]['status']=='available' for row in rows)]
                slots=('current',*(item[0] for item in comparators));changes=tuple(item[1] for item in comparators)
                headers=[*HEADERS[:3],*(item[2] for item in comparators),*(item[3] for item in comparators)]
                dates=[d for d in dates if d.startswith('Current:') or any(d.startswith(item[2]+':') for item in comparators)]
            lines.extend(['### '+family_name,'',' · '.join(dates),'',
                          '| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |'])
            for row in rows:
                unit,divisor=unit_display(row['unit']);label=metric_label(row)
                if row.get('derived') and front_role(row)=='free_cash_flow':label='Free cash flow'
                if id(row) in disclosure_ids:label+=' · selected disclosure'
                if len(entities)>1:label+=' · '+str(row.get('entity'))
                values=[label,unit+' · '+basis_label(row),
                        *(value_cell(row['cells'][key],divisor) for key in slots),
                        *(change_cell(row['changes'][key],divisor,unit) for key in changes)]
                lines.append('| '+' | '.join(markdown.cell(v) for v in values)+' |')
            lines.append('')
        conflicts=[]
        for table in value['tables']:
            if target!='cash' and table['period_family']!='quarter':continue
            for row in table['rows']:
                if (not row.get('dimensions') and front_role(row) in FRONT_METRICS[target]
                        and row['cells']['current']['status']=='ambiguous'):
                    conflicts.append(metric_label(row)+' ('+unit_display(row['unit'])[0]+' · '+basis_label(row)+')')
        if conflicts:lines.extend(['Conflicting current observations: '+'; '.join(dict.fromkeys(conflicts))+'. See supporting evidence.',''])
        gap=front_gaps(selected,target)
        if gap:lines.extend([gap,''])
        if target=='earnings' and earnings_commentary(value):
            lines.extend(['Quarter expense detail: '+' '.join(earnings_commentary(value)),''])
    from . import earnings_packet_inventory as packet_inventory
    for table in value.get('reported_tables',[]):
        renderer=packet_inventory.render_compact if value.get('reported_table_layout')==packet_inventory.LAYOUT else packet_inventory.render
        result[table['section']].extend(renderer(table))
    return result


def notes(value,selection=None):
    """Readable overview; complete source observations and traces stay in JSON."""
    selected=front_rows(value,selection)
    derived={front_role(row) for rows in selected.values() for _,row in rows if row.get('derived')}
    result=['- Δ / change: absolute change / relative %. Margin changes are percentage points (pp). — unavailable; N/M nonpositive earnings or comparison base.']
    if any(front_role(row) in DEBT_COMPONENT_NAMES for _, row in selected['cash']):
        result.append('- Debt and capital-lease components and short-term borrowings are shown as filed. No combined total is inferred because component overlap and scope have not been established.')
    if selection is not None:
        result.append('- Debt/lease disclosures are explicitly selected source balances. Selection does not classify them as pure debt or authorize a combined total.')
    if derived&{'gross_margin','operating_margin'}:
        result.append('- Calculated margins divide the corresponding profit by revenue. Margin changes are percentage-point differences.')
    if 'free_cash_flow' in derived:
        result.append('- Free cash flow equals operating cash flow less gross capital expenditure, using the same period.')
    if 'total_debt' in derived:
        result.append('- Calculated total debt adds compatible current and noncurrent debt observations; it does not estimate unreported obligations.')
        if value.get('source_policy') in ('filed-statement-context-v1', 'filed-statement-repair-v1'):
            result.append('- Debt is the balance-sheet carrying amount. Outstanding principal or management-reported gross debt may differ because of discounts, premiums, issuance costs or scope; those figures are not interchangeable.')
    if value.get('financial_selection') is not None:
        for row in value['financial_selection']['rows']:
            if row['metric'] in ('total_debt','debt_component','operating_leases'):
                result.append('- '+row['label']+': '+row['definition']+' '+markdown.refs(row['citations']))
    if any(row.get('basis_origin')=='caller_declared' for rows in selected.values() for _,row in rows):
        result.append('- A basis marked assumed is caller-declared where the source does not state it; it is not a company assertion.')
    return result


def multiples_references(value):
    references={}
    for slot in ('price','current_eps','forward_eps'):
        record=value.get('inputs',{}).get(slot)
        if not isinstance(record,dict) or not isinstance(record.get('id'),str):continue
        source=record.get('source') if isinstance(record.get('source'),dict) else {}
        identifier='PE-'+base.digest(record['id'])[:12]
        references[record['id']]=(identifier,'Supplied '+slot.replace('_',' ')+' input; '+
            str(source.get('document_id','source unspecified'))+'; '+str(source.get('url','URL unspecified'))+
            '; input date '+str(record.get('as_of','unspecified'))+'.')
    return references


def multiples_lines(value):
    references=multiples_references(value)
    security=value.get('security') if isinstance(value.get('security'),dict) else {}
    price_unit=str(security.get('currency') or 'currency unavailable')+' per '+str(security.get('earnings_unit') or 'security basis unavailable').replace('_',' ')
    result=['## Earnings multiples','',
            'Security: '+str(security.get('id') or 'unavailable')+' · '+price_unit+' · '+str(security.get('ordinary_shares_per_security') or 'unavailable')+' ordinary shares per security · split basis '+str(security.get('split_basis_id') or 'unavailable')+'.','',
            'Valuation date: '+value['as_of']+'. Supplied price and annual diluted EPS; source metadata is caller-provided, not independently verified.','',
            'Price and diluted EPS: '+price_unit+'.','',
            '| Metric | Price / diluted EPS | P/E | EPS period / basis |',
            '| --- | --- | --- | --- |']
    for row in value['rows']:
        multiple=number(row['value'],places=2)+'×' if row['status']=='available' else ('N/M' if row['status']=='not_meaningful' else '—')
        operands=row.get('operands') or {};period=row.get('earnings_period') if isinstance(row.get('earnings_period'),dict) else {}
        inputs=(number(operands['price'],places=2)+' / '+number(operands['annual_diluted_eps'],places=2)) if operands else '—'
        period_text=' – '.join(str(period.get(k,'unspecified')) for k in ('start','end'))
        period_text+=' · '+str(row.get('accounting_basis') or 'basis unavailable')
        if row.get('forecast_as_of'):period_text+=' · forecast dated '+str(row['forecast_as_of'])
        refs=markdown.refs([references[i][0] for i in row['input_ids'] if i in references])
        result.append('| '+' | '.join(markdown.cell(x) for x in [row['label']+' '+refs,inputs,multiple,period_text])+' |')
    result.append('')
    for row in value['rows']:
        if row.get('reason'):result.extend([row['label']+': '+row['reason']+'.',''])
    return result


def preview_markdown(value,earnings_multiples=None,selection=None):
    rendered=sections(value,selection)
    lines=['# Financial analysis','',
           'Quarter: '+display.period_label(value['current_period'])+'. As of: '+value['as_of']+'.','',
           'Core consolidated metrics. Cash-flow durations and balance-sheet dates are labeled separately.','']
    for key in ('demand','earnings','cash'):
        lines.extend(['## '+FRONT_HEADINGS[key],'',*rendered[key]])
    if earnings_multiples is not None:lines.extend(multiples_lines(earnings_multiples))
    else:lines.extend(['Earnings multiples unavailable: no dated price and matching annual/TTM or forward annual diluted EPS snapshot supplied.',''])
    lines.extend(['## Source and calculation notes','','Values are displayed to two decimal places; nonzero small values retain precision.','',*notes(value,selection),''])
    lines.extend(['## Source references',''])
    import re
    identifiers=sorted(set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]', '\n'.join(lines))))
    extra={identifier:description for identifier,description in multiples_references(earnings_multiples).values()} if earnings_multiples is not None else {}
    lines.extend('[^'+identifier+']: '+extra.get(identifier,'Original evidence '+identifier) for identifier in identifiers)
    return '\n'.join(lines).rstrip()+'\n'


def preview_html(text):
    page=markdown.render(text)
    # Fixed application markup only; all financial/source text was escaped by render.
    marker='<h2>Source and calculation notes</h2>'
    return page.replace(marker,'<details class="original-qa"><summary>Sources and calculation notes</summary>',1).replace('</main>','</details></main>',1)


def validate_multiple_issuer(value,multiples):
    security=multiples.get('security')
    issuer=security.get('issuer') if isinstance(security,dict) else None
    if (not isinstance(issuer,dict) or set(issuer)!={'entity','entity_scheme'} or
            any(not isinstance(issuer.get(k),str) or not issuer[k] for k in ('entity','entity_scheme'))):
        raise ValueError('Earnings snapshot requires explicit security.issuer entity and entity_scheme binding')
    entities={(row.get('entity'),row.get('entity_scheme')) for table in value['tables'] for row in table['rows']
              if not row.get('dimensions') and row['cells']['current']['status']=='available'}
    if entities!={(issuer['entity'],issuer['entity_scheme'])}:
        raise ValueError('Earnings snapshot issuer must match the sole current consolidated financial entity')


def preview(manifest,output,*,quarter_start,quarter_end,config=None,earnings_snapshot=None,valuation_as_of=None,debt_disclosure_facts=None):
    from . import earnings_compact_evidence as evidence
    config=configuration(quarter_start,quarter_end) if config is None else validate_configuration(config)
    if config['current_period']!=['duration',quarter_start,quarter_end]:raise ValueError('CLI quarter differs from frozen analysis configuration')
    if bool(earnings_snapshot)!=bool(valuation_as_of):raise ValueError('Earnings snapshot and explicit valuation date are required together')
    multiples=None
    if earnings_snapshot:
        from . import earnings_earnings_multiples
        multiples=earnings_earnings_multiples.load(earnings_snapshot,as_of=valuation_as_of)
    bundle=evidence.load_bundle(Path(manifest));value=compile(bundle,config)
    if multiples is not None:validate_multiple_issuer(value,multiples)
    selection=display_selection(value,debt_disclosure_facts) if debt_disclosure_facts is not None else None
    text=preview_markdown(value,multiples,selection);page=preview_html(text)
    root=Path(output);contents={'financial-analysis-config.json':json.dumps(config,ensure_ascii=False,sort_keys=True,indent=2)+'\n',
                                'financial-analysis.json':json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',
                                'financial-analysis.md':text,'financial-analysis.html':page}
    if selection is not None:contents['display-selection.json']=json.dumps(selection,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if multiples is not None:contents['earnings-multiples.json']=json.dumps(multiples,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
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
    parser.add_argument('--earnings-snapshot',type=Path,help='Optional dated price/EPS snapshot with exact security.issuer entity and entity_scheme matching this financial evidence')
    parser.add_argument('--valuation-as-of',help='Explicit quote date, required with --earnings-snapshot')
    parser.add_argument('--debt-disclosure-fact',action='append',help='Explicit qualified current consolidated debt/lease disclosure fact ID; repeat to show separate balances without summing')
    args=parser.parse_args()
    print(json.dumps(preview(args.manifest,args.output,quarter_start=args.quarter_start,quarter_end=args.quarter_end,
                            config=base.read(args.config) if args.config else None,earnings_snapshot=args.earnings_snapshot,
                            valuation_as_of=args.valuation_as_of,debt_disclosure_facts=args.debt_disclosure_fact),indent=2))

if __name__=='__main__':main()
