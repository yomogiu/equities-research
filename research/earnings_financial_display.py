"""Deterministic presentation of selected frozen observations; no new financial facts.

Author row labels are selection hints, never authority for unit scale or metric
identity. Values are converted with Decimal without rounding; every displayed
value keeps original fact IDs. Different metrics/dimensions/units stay separate.
"""
from collections import OrderedDict
from datetime import date
from decimal import Decimal, localcontext
import html
import json
import re

VERSION = 'financial-display-v1'
LABELS = {
 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax': 'Revenue',
 'us-gaap:Revenues': 'Revenue', 'us-gaap:GrossProfit': 'Gross profit',
 'us-gaap:OperatingIncomeLoss': 'Operating income (loss)',
 'us-gaap:NetIncomeLoss': 'Net income (loss)',
 'us-gaap:NetCashProvidedByUsedInOperatingActivities': 'Operating cash flow',
 'us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations': 'Operating cash flow · continuing operations',
 'us-gaap:PaymentsToAcquirePropertyPlantAndEquipment': 'Purchases of property, plant and equipment',
 'us-gaap:CashAndCashEquivalentsAtCarryingValue': 'Cash and cash equivalents',
 'us-gaap:ShortTermInvestments': 'Short-term investments',
 'us-gaap:AccountsReceivableNetCurrent': 'Accounts receivable, net',
 'us-gaap:InventoryNet': 'Inventory, net',
 'us-gaap:DebtCurrent': 'Current debt', 'us-gaap:LongTermDebtNoncurrent': 'Long-term debt',
 'us-gaap:DebtSecuritiesCurrent': 'Current debt securities',
 'us-gaap:GuaranteeObligationsMaximumExposure': 'Maximum guarantee exposure',
 'us-gaap:UnrecordedUnconditionalPurchaseObligationDueInRemainderOfFiscalYear': 'Unconditional purchase obligations · remainder of fiscal year',
 'us-gaap:UnrecordedUnconditionalPurchaseObligationBalanceOnFirstAnniversary': 'Unconditional purchase obligations · first anniversary',
 'us-gaap:UnrecordedUnconditionalPurchaseObligation': 'Unconditional purchase obligations · total',
 'us-gaap:OtherCommitmentsFutureMinimumPaymentsRemainderOfFiscalYear': 'Other commitments · remainder of fiscal year',
 'us-gaap:OtherCommitmentDueInNextTwelveMonths': 'Other commitments · next twelve months',
 'us-gaap:OtherCommitmentDueInSecondYear': 'Other commitments · second year',
 'us-gaap:OtherCommitment': 'Other commitments · total',
}


def humanize(value):
    value = str(value).split(':', 1)[-1]
    value = re.sub(r'(Axis|Member)$', '', value)
    value = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', value)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', value).replace('_', ' ')


def dimensions_label(dims):
    labels = []
    for d in dims:
        axis = d.get('dimension', '')
        value = d.get('member') or d.get('value') or d.get('text')
        if not isinstance(value, str):
            raise ValueError('Unsupported dimension display; explicit source-backed label required')
        member = humanize(value)
        if axis.endswith('StatementBusinessSegmentsAxis'):
            labels.append(member + ' segment')
        elif axis.endswith('ConsolidationItemsAxis') and value.endswith('OperatingSegmentsMember'):
            continue  # Business segment identity is retained above; allocation basis stays in evidence.
        else:
            labels.append(humanize(axis) + ': ' + member)
    return '; '.join(labels)


def format_number(value):
    text = format(value, ',f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def scaled_value(obs, unit):
    value = Decimal(obs['value'])
    if not value.is_finite():
        raise ValueError('Finite financial value required')
    nums, dens = unit['numerator'], unit['denominator']
    factor = Decimal(1)
    if len(nums) == 1 and nums[0].startswith('iso4217:') and not dens:
        factor = Decimal('1000000'); label = nums[0].split(':')[1] + ' millions'
    elif len(nums) == 1 and nums[0].startswith('iso4217:') and dens == ['xbrli:shares']:
        label = nums[0].split(':')[1] + '/share'
    elif nums == ['xbrli:shares'] and not dens:
        factor = Decimal('1000000'); label = 'million shares'
    elif nums == ['xbrli:pure'] and not dens:
        label = 'ratio'  # Never guess whether a pure ratio is a percentage.
    else:
        label = ' × '.join(humanize(x) for x in nums)
        if dens: label += '/' + ' × '.join(humanize(x) for x in dens)
    with localcontext() as ctx:
        ctx.prec = max(50, len(value.as_tuple().digits) + abs(value.adjusted()) + 12)
        display = value / factor
        if display * factor != value:
            raise ValueError('Inexact display scaling')
    return format_number(display), label, str(factor)


def period_key(context):
    if context.get('instant'):
        return ('instant', context['instant'])
    a, b = context.get('start_date'), context.get('end_date')
    if not a or not b or date.fromisoformat(b) < date.fromisoformat(a):
        raise ValueError('Complete valid financial period required')
    return ('duration', a, b)


def period_label(key):
    def short(x): return date.fromisoformat(x).strftime('%b %d, %Y').replace(' 0', ' ')
    return ('As filed: ' + short(key[1])) if key[0] == 'instant' else short(key[1]) + ' – ' + short(key[2])


def build(financial, bundle):
    facts = bundle['financial']; observations = {o['id']: o for o in facts['observations']}
    rows, seen, selected = OrderedDict(), set(), []
    for selection in financial['rows']:
        for fid in selection['fact_ids']:
            if fid in seen: continue
            seen.add(fid); selected.append(fid)
            obs = observations[fid]
            if obs['status'] != 'extracted' or obs['nil'] or obs['value'] is None:
                raise ValueError('Unqualified financial table observation')
            ctx, unit = facts['contexts'][obs['context_id']], facts['units'][obs['unit_id']]
            value, unit_label, divisor = scaled_value(obs, unit)
            dims = sorted(ctx['dimensions'], key=lambda d: json.dumps(d, sort_keys=True))
            period = period_key(ctx)
            # Entity, semantic identity, dimensions, currency and duration family all bind rows.
            duration_days = (date.fromisoformat(period[2])-date.fromisoformat(period[1])).days+1 if period[0]=='duration' else None
            family = ('quarter' if 70 <= duration_days <= 105 else 'half-year' if 150 <= duration_days <= 200 else str(duration_days)) if duration_days else 'instant'
            key = json.dumps([obs['concept'],ctx['entity'],ctx.get('entity_scheme'),dims,unit['numerator'],unit['denominator'],family],sort_keys=True)
            if key not in rows:
                label = LABELS.get(obs['concept'], humanize(obs['concept']))
                detail = dimensions_label(dims)
                rows[key] = {'metric':label, 'dimensions':detail, 'unit':unit_label, 'cells':OrderedDict(), 'concept':obs['concept']}
            row = rows[key]
            if period in row['cells']:
                cell = row['cells'][period]
                if Decimal(cell['original_value']) != Decimal(obs['value']):
                    raise ValueError('Conflicting values for the same metric, period and dimensions')
                cell['fact_ids'].append(fid)
            else:
                row['cells'][period] = {'value':value, 'original_value':obs['value'], 'divisor':divisor, 'fact_ids':[fid]}
    groups = OrderedDict()
    for row in rows.values():
        periods = tuple(sorted(row['cells'], key=lambda p:p[-1], reverse=True))
        key = (periods,row['unit'])
        if key not in groups:
            groups[key] = {'periods':[{'key':list(p),'label':period_label(p)} for p in periods], 'unit':row['unit'], 'rows':[]}
        groups[key]['rows'].append({k:v for k,v in row.items() if k!='cells'} | {'cells':[row['cells'][p] for p in periods]})
    return {'version':VERSION,'groups':list(groups.values()),'selected_fact_ids':selected,
            'period_basis':'Dates are filed observation contexts. Subsequent-event and payment-horizon qualifiers require source-backed notes; no fiscal-year mapping is inferred.'}


def text_table(financial, bundle):
    display = build(financial,bundle); lines=['Financial context']
    for group in display['groups']:
        lines += ['',group['unit'],'Metric | '+' | '.join(p['label'] for p in group['periods'])]
        for row in group['rows']:
            metric=row['metric']+(' · '+row['dimensions'] if row['dimensions'] else '')
            lines.append(metric+' | '+' | '.join(c['value']+' ['+', '.join(c['fact_ids'])+']' for c in row['cells']))
    return '\n'.join(lines)


def html_table(financial, bundle, refs):
    e=html.escape; parts=['<h2>Financial context</h2>']
    for group in build(financial,bundle)['groups']:
        parts.append('<table><caption>'+e(group['unit'])+'</caption><thead><tr><th>Metric</th>')
        parts.extend('<th>'+e(p['label'])+'</th>' for p in group['periods'])
        parts.append('</tr></thead><tbody>')
        for row in group['rows']:
            parts.append('<tr><th>'+e(row['metric'])+('<small>'+e(row['dimensions'])+'</small>' if row['dimensions'] else '')+'</th>')
            parts.extend('<td class="numeric">'+e(c['value'])+' '+refs(c['fact_ids'])+'</td>' for c in row['cells'])
            parts.append('</tr>')
        parts.append('</tbody></table>')
    return ''.join(parts)
