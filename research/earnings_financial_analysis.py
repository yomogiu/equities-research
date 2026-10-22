"""Deterministic tables over the complete qualified financial inventory.

This module interprets exact taxonomy identities, never source-label similarity.
Inputs are an already authenticated evidence bundle; labels/bases are re-bound to
its original source bytes. Dates and dimensions remain filed, not calendar guesses.
All arithmetic is Decimal; unavailable comparisons are data, never zeroes.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json

from . import earnings_financial_context as source_context
from . import earnings_financial_display as display
from . import earnings_period_comparisons as periods
from . import financial_evidence as evidence
from .financial_reviewed_proposals import usable

VERSION = 'deterministic-financial-analysis-v1'
# Only these exact concepts authorize a calculation role. A caller's
# canonical_metric and a model's prose cannot expand this whitelist.
CONCEPTS = dict(evidence.METRICS, **{
    'us-gaap:CostOfRevenue': 'cost_of_revenue',
    'us-gaap:CostOfGoodsAndServicesSold': 'cost_of_revenue',
    'ifrs-full:CostOfSales': 'cost_of_revenue',
    'us-gaap:ShortTermInvestments': 'short_term_investments',
    'us-gaap:DebtCurrent': 'current_debt',
    'us-gaap:LongTermDebtNoncurrent': 'noncurrent_debt',
    'ifrs-full:Revenue': 'revenue',
    'ifrs-full:GrossProfit': 'gross_profit',
    'ifrs-full:ProfitLossFromOperatingActivities': 'operating_income',
    'ifrs-full:ProfitLoss': 'net_income',
    'ifrs-full:CashFlowsFromUsedInOperatingActivities': 'operating_cash_flow',
    'ifrs-full:PurchaseOfPropertyPlantAndEquipment': 'capital_expenditure',
    'ifrs-full:CashAndCashEquivalents': 'cash_and_equivalents',
    'ifrs-full:DilutedEarningsLossPerShare': 'diluted_eps',
    'ifrs-full:WeightedAverageNumberOfDilutedSharesOutstanding': 'diluted_shares',
})
ADDITIVE = {'revenue', 'gross_profit', 'operating_income', 'net_income',
            'operating_cash_flow', 'capital_expenditure', 'cost_of_revenue'}
DERIVED = {
    'gross_profit': ('Calculated gross profit (revenue less cost of revenue)', 'subtract', 'revenue', 'cost_of_revenue'),
    'free_cash_flow': ('Free cash flow (operating cash flow less capital expenditure)', 'subtract', 'operating_cash_flow', 'capital_expenditure'),
    'gross_margin': ('Gross margin', 'ratio_percent', 'gross_profit', 'revenue'),
    'operating_margin': ('Operating margin', 'ratio_percent', 'operating_income', 'revenue'),
    'net_margin': ('Net margin', 'ratio_percent', 'net_income', 'revenue'),
    'operating_cash_flow_margin': ('Operating cash flow / revenue', 'ratio_percent', 'operating_cash_flow', 'revenue'),
    'free_cash_flow_margin': ('Free cash flow / revenue', 'ratio_percent', 'free_cash_flow', 'revenue'),
    'capex_intensity': ('Capital expenditure / revenue', 'ratio_percent', 'capital_expenditure', 'revenue'),
    'liquid_assets': ('Cash and equivalents plus short-term investments', 'add', 'cash_and_equivalents', 'short_term_investments'),
    'total_debt': ('Current plus noncurrent debt', 'add', 'current_debt', 'noncurrent_debt'),
    'net_debt': ('Total debt less cash and equivalents', 'subtract', 'total_debt', 'cash_and_equivalents'),
}
FAMILIES = ('quarter', 'half', 'nine-month', 'annual', 'instant', 'other')
PERCENT_UNIT = {'numerator': ['percent'], 'denominator': []}


def _key(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _number(value):
    # Source bounds are enforced on ingestion. A valid sum/ratio may have more
    # digits or a larger exponent than either source, so do not reapply source
    # lexical limits to code-owned calculation results.
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Bounded Decimal calculation string required')
    number = Decimal(value)
    if not number.is_finite(): raise ValueError('Finite Decimal required')
    return number


def _text(value):
    return format(value, 'f')


def _ids(cells):
    return sorted({fid for cell in cells for fid in cell.get('fact_ids', [])})


def _family(period):
    return periods.family(period) or 'other'


def _money(unit):
    return (len(unit['numerator']) == 1 and unit['numerator'][0].startswith('iso4217:')
            and len(unit['numerator'][0]) == 11 and not unit['denominator'])


def _gap(reason, fact_ids=(), **kwargs):
    return {'reason': reason, 'fact_ids': sorted(set(fact_ids)), **kwargs}


def _unavailable(reason, period=None, fact_ids=(), status='missing'):
    return {'status': status, 'value': None, 'period': list(period) if period else None,
            'fact_ids': sorted(set(fact_ids)), 'calculation': None, 'source_labels': [], 'reason': reason}


def _merge(cells, period):
    """Conflicts are never resolved by order, recency, or preferential source."""
    if not cells:
        return _unavailable('No comparable qualified observation', period)
    if any(c['status'] != 'available' for c in cells) or len({_number(c['value']) for c in cells}) != 1:
        return _unavailable('Conflicting or ambiguous observations', period, _ids(cells), 'ambiguous')
    result = deepcopy(cells[0])
    result['fact_ids'] = _ids(cells)
    result['source_labels'] = sorted({s for c in cells for s in c['source_labels']})
    if len(cells) > 1:
        result['calculation'] = {'operator': 'agreeing_observations', 'operands': deepcopy(cells)}
    return result


def _calculated(operator, left, right, period):
    operands = [left, right]
    if any(x['status'] != 'available' for x in operands):
        return _unavailable('Required operand unavailable or ambiguous', period, _ids(operands))
    a, b = _number(left['value']), _number(right['value'])
    if operator == 'ratio_percent' and b <= 0:
        return _unavailable('Ratio denominator must be positive', period, _ids(operands))
    # 512 exceeds the bounded input's maximum significant digits/exponent;
    # repeating ratios have a declared 50-digit precision and are never floats.
    with localcontext() as ctx:
        ctx.prec = 512 if operator != 'ratio_percent' else 50
        value = a - b if operator in ('subtract', 'ytd_difference') else a + b if operator == 'add' else a / b * 100
    return {'status': 'available', 'value': _text(value), 'period': list(period),
            'fact_ids': _ids(operands), 'source_labels': sorted({s for c in operands for s in c['source_labels']}),
            'calculation': {'operator': operator, 'operands': deepcopy(operands),
                            'precision': 50 if operator == 'ratio_percent' else 512}, 'reason': None}


def _quarter_before(current, prior):
    if current[0] == prior[0] == 'duration':
        return (_family(current) == _family(prior) == 'quarter'
                and date.fromisoformat(prior[2]) + timedelta(days=1) == date.fromisoformat(current[1]))
    if current[0] == prior[0] == 'instant':
        return 70 <= (date.fromisoformat(current[1]) - date.fromisoformat(prior[1])).days <= 105
    return False


def _year_ago(current, prior):
    # Fiscal year boundaries may straddle December/January in different civil
    # years after a 53-week year. Compare elapsed filed dates, not year digits.
    if current[0] != prior[0] or _family(current) == 'other' or _family(current) != _family(prior):
        return False
    offsets = [(date.fromisoformat(a)-date.fromisoformat(b)).days for a,b in zip(current[1:],prior[1:])]
    return all(357 <= days <= 374 for days in offsets) and max(offsets)-min(offsets) <= 8


def _change(current, prior, *, percent_unit=False, allowed=True, basis=None):
    ids = _ids([current, prior])
    result = {'status': 'unavailable', 'absolute': None, 'percent': None,
              'kind': 'percentage_points' if percent_unit else 'amount', 'fact_ids': ids,
              'reason': 'Comparable current and prior observations required'}
    if not allowed:
        return {**result, 'reason': 'QoQ is defined only for quarters and quarter-spaced instants'}
    if not basis:
        return {**result, 'reason': 'Accounting basis is not established by source'}
    if current['status'] != 'available' or prior['status'] != 'available':
        return result
    a, b = _number(current['value']), _number(prior['value'])
    with localcontext() as ctx:
        ctx.prec = 512
        result['absolute'] = _text(a-b)
        if percent_unit:
            return {**result, 'status': 'available', 'reason': None}
        if b <= 0:
            return {**result, 'status': 'not_meaningful', 'reason': 'Percentage change is not meaningful with a nonpositive prior value'}
        ctx.prec = 50
        result['percent'] = _text((a-b)/b*100)
    return {**result, 'status': 'available', 'reason': None}


def _dimensions(context):
    dims = context.get('dimensions')
    if not isinstance(dims, list) or any(not isinstance(d, dict) or not d.get('dimension') or
            not (d.get('member') or d.get('value') or d.get('text')) for d in dims):
        raise ValueError('Complete explicit dimensions required')
    return sorted(deepcopy(dims), key=_key)


def _inventory(bundle, capex_conventions, accounting_bases):
    facts = bundle['financial']
    observations = facts['observations']
    if len({o['id'] for o in observations}) != len(observations):
        raise ValueError('Duplicate observation ID')
    selected = [o for o in observations if usable(o, facts) and not o.get('nil') and o.get('value') is not None]
    identities = source_context.source_identities(bundle, [o['id'] for o in selected])
    groups, gaps = {}, deepcopy(facts.get('gaps', []))
    for obs in observations:
        if obs not in selected:
            gaps.append(_gap('Unqualified, nil, or missing observation', [obs['id']]))
            continue
        try:
            evidence._decimal(obs['value'])
            context = facts['contexts'][obs['context_id']]
            if not context.get('entity') or not context.get('entity_scheme'):
                raise ValueError('Complete entity identity required')
            if bool(context.get('instant')) == bool(context.get('start_date') or context.get('end_date')):
                raise ValueError('Ambiguous reporting period')
            period = display.period_key(context)
            # Instant strings also require full ISO validation.
            for boundary in period[1:]: date.fromisoformat(boundary)
            unit = {k: sorted(facts['units'][obs['unit_id']][k]) for k in ('numerator', 'denominator')}
            if not unit['numerator'] or any(not isinstance(x, str) or not x for x in unit['numerator']+unit['denominator']):
                raise ValueError('Complete units required')
            dims = _dimensions(context)
            identity = identities[obs['id']]
            label, basis = identity.get('label') or obs['concept'], identity.get('basis') or None
            override = accounting_bases.get(obs['id'])
            if override and basis and override != basis:
                raise ValueError('Configured accounting basis contradicts source basis')
            basis = basis or override
            # Undeclared basis remains undeclared, including inline GAAP tags.
            role = CONCEPTS.get(obs['concept'])
            convention = capex_conventions.get(obs['id'], 'positive_payment') if role == 'capital_expenditure' else None
            grouping_label = None if obs.get('method') == 'reviewed_html_table' and role else label
            row_label = display.LABELS.get(obs['concept'], role.replace('_', ' ').capitalize()) if grouping_label is None else label
            key = _key([obs['concept'], grouping_label, context['entity'], context['entity_scheme'], dims, unit, basis, convention])
            if key not in groups:
                groups[key] = {'metric_id': role or obs['concept'], 'label': row_label, 'concepts': [obs['concept']],
                    'entity': context['entity'], 'entity_scheme': context['entity_scheme'], 'dimensions': dims,
                    'basis': basis, 'unit': unit, 'derived': False, 'capex_convention': convention, 'basis_origin': 'source', '_periods': defaultdict(list)}
            if override and not identity.get('basis'):
                groups[key]['basis_origin'] = 'caller_declared'
                gaps.append(_gap('Calculation assumes caller-declared accounting basis; independent source review is not established by this configuration', [obs['id']], accounting_basis=override))
            groups[key]['_periods'][period].append({'status': 'available', 'value': _text(_number(obs['value'])),
                'period': list(period), 'fact_ids': [obs['id']], 'source_labels': [label], 'reason': None,
                'calculation': {'operator': 'reported', 'fact_id': obs['id'], 'concept': obs['concept'],
                                'context_id': obs['context_id'], 'unit_id': obs['unit_id'],
                                'basis_origin': 'caller_declared' if override and not identity.get('basis') else 'source',
                                'accounting_basis': basis}})
            if not basis:
                gaps.append(_gap('Source accounting basis unstated; arithmetic withheld', [obs['id']]))
            if not role:
                gaps.append(_gap('No exact calculation mapping; observation retained', [obs['id']]))
        except (KeyError, TypeError, ValueError) as exc:
            if 'Configured accounting basis contradicts' in str(exc): raise
            gaps.append(_gap(str(exc), [obs['id']]))
    for group in groups.values():
        group['_periods'] = {p: _merge(cells, p) for p, cells in group['_periods'].items()}
    return list(groups.values()), gaps


def _derive_quarters(groups, gaps):
    for row in groups:
        if row['metric_id'] not in ADDITIVE or not _money(row['unit']) or not row['basis']:
            continue
        original = list(row['_periods'].items())
        candidates = defaultdict(list)
        for longer, a in original:
            if longer[0] != 'duration' or _family(longer) not in ('half', 'nine-month', 'annual'):
                continue
            for shorter, b in original:
                if (shorter[0] != 'duration' or shorter[1] != longer[1] or shorter[2] >= longer[2]
                        or _family(shorter) not in ('quarter', 'half', 'nine-month')
                        or FAMILIES.index(_family(longer)) != FAMILIES.index(_family(shorter)) + 1):
                    continue
                quarter = ('duration', (date.fromisoformat(shorter[2])+timedelta(days=1)).isoformat(), longer[2])
                if _family(quarter) != 'quarter': continue
                derived = _calculated('ytd_difference', a, b, quarter)
                candidates[quarter].append(derived)
        for period, cells in candidates.items():
            if period in row['_periods']: cells.insert(0, row['_periods'][period])
            row['_periods'][period] = _merge(cells, period)
            if row['_periods'][period]['status'] != 'available':
                gaps.append(_gap('Reported and/or derived quarter conflict', _ids(cells), period=list(period)))


def _capex_operand(cell, convention):
    if cell['status'] != 'available': return cell
    value = _number(cell['value'])
    if convention == 'signed_cash_flow':
        if value > 0:
            return _unavailable('Signed cash-flow expenditure must be nonpositive; refunds require separate classification', cell['period'], cell['fact_ids'])
        return {**deepcopy(cell), 'value': _text(value.copy_negate()),
                'calculation': {'operator': 'signed_cash_flow_to_positive_payment',
                                'operands': [deepcopy(cell)], 'convention': convention}}
    if value < 0:
        return _unavailable('Capital expenditure sign contradicts positive-payment convention', cell['period'], cell['fact_ids'])
    return cell


def _derive_metrics(groups, gaps):
    # Every operand bucket keeps exact entity, dimensions, currency, and basis.
    buckets = defaultdict(list)
    for row in groups:
        if _money(row['unit']):
            buckets[_key([row[k] for k in ('entity', 'entity_scheme', 'dimensions', 'basis', 'unit')])].append(row)
    added = []
    for bucket in buckets.values():
        if not bucket[0]['basis']: continue
        by_role = defaultdict(list)
        for row in bucket:
            if row['metric_id'] not in {role for entry in DERIVED.values() for role in entry[2:]}: continue
            expected = 'duration' if row['metric_id'] in ADDITIVE else 'instant'
            valid = {p: c for p, c in row['_periods'].items() if p[0] == expected}
            if len(valid) != len(row['_periods']):
                gaps.append(_gap('Calculation role has incompatible period type', _ids(list(row['_periods'].values())), metric_id=row['metric_id']))
            if valid: by_role[row['metric_id']].append({**row, '_periods': valid})
        for metric, (label, op, left_role, right_role) in DERIVED.items():
            lefts, rights = by_role[left_role], by_role[right_role]
            # Explicit missing operand rows prevent false zero-based calculations.
            if not lefts and not rights: continue
            exemplar = bucket[0]
            row = {k: deepcopy(exemplar[k]) for k in ('entity', 'entity_scheme', 'dimensions', 'basis', 'unit')}
            row['basis_origin'] = 'caller_declared' if any(r.get('basis_origin') == 'caller_declared' for r in lefts+rights) else 'source'
            row.update(metric_id=metric, label=label, concepts=sorted({c for r in lefts+rights for c in r['concepts']}),
                       derived=True, _periods={})
            if op == 'ratio_percent': row['unit'] = deepcopy(PERCENT_UNIT)
            reported = list(by_role[metric]) if metric == 'gross_profit' else []
            row['concepts'] = sorted({c for r in lefts+rights+reported for c in r['concepts']})
            if any(r.get('basis_origin') == 'caller_declared' for r in reported):
                row['basis_origin'] = 'caller_declared'
            all_periods = {p for r in lefts+rights+reported for p in r['_periods']}
            for period in sorted(all_periods):
                operands = []
                for options in (lefts, rights):
                    matches = [r['_periods'][period] for r in options if period in r['_periods']]
                    # Aliases or differently qualified labels do not prove identical accounting scope,
                    # even when their values agree. Only duplicates within one exact row merge.
                    operand = matches[0] if len(matches) == 1 else _unavailable(
                        'Ambiguous calculation identity' if matches else 'Required compatible metric missing',
                        period, _ids(matches), 'ambiguous' if matches else 'missing')
                    selected_rows = [r for r in options if period in r['_periods']]
                    if len(selected_rows) == 1 and selected_rows[0]['metric_id'] == 'capital_expenditure':
                        operand = _capex_operand(operand, selected_rows[0]['capex_convention'])
                    if len(selected_rows) == 1 and selected_rows[0]['metric_id'] == 'cost_of_revenue' and operand['status'] == 'available' and _number(operand['value']) < 0:
                        operand = _unavailable('Cost sign contradicts positive-expense taxonomy', period, operand['fact_ids'])
                    operands.append(operand)
                row['_periods'][period] = _calculated(op, *operands, period)
                if reported:
                    actuals = [r['_periods'][period] for r in reported if period in r['_periods']]
                    if actuals:
                        actual = actuals[0] if len(actuals) == 1 else _unavailable('Ambiguous reported gross profit', period, _ids(actuals), 'ambiguous')
                        row['_periods'][period] = _merge([actual, row['_periods'][period]], period) if row['_periods'][period]['status'] == 'available' else deepcopy(actual)
                if row['_periods'][period]['status'] != 'available':
                    gaps.append(_gap('Derived metric unavailable: '+metric, _ids(operands), period=list(period),
                                     details=[x.get('reason') for x in operands if x.get('reason')]))
            added.append(row)
            if metric == 'gross_profit': by_role[metric] = [row]
            else: by_role[metric].append(row)
    return groups + added


def build(bundle, *, current_period=None, as_of=None, capex_conventions=None, accounting_bases=None):
    """Return full-inventory, source-bound tables at an explicit reporting end.

    current_period optionally supplies exact quarter boundaries. Otherwise a
    unique observed/derived quarter ending on as_of is required for quarter
    comparisons; no metric's older latest observation is promoted to current.
    No source files, bundles, or reports are written or mutated.
    """
    if current_period is not None:
        current_period = tuple(current_period)
        if len(current_period) != 3 or current_period[0] != 'duration' or _family(current_period) != 'quarter':
            raise ValueError('Explicit current_period must be a complete quarter')
        if as_of and as_of != current_period[2]: raise ValueError('Current quarter and as_of differ')
        as_of = current_period[2]
    if not isinstance(as_of, str): raise ValueError('Explicit as_of reporting date required')
    date.fromisoformat(as_of)
    capex_conventions = {} if capex_conventions is None else capex_conventions
    eligible = {o['id'] for o in bundle['financial']['observations'] if CONCEPTS.get(o['concept']) == 'capital_expenditure'}
    if (not isinstance(capex_conventions, dict) or not set(capex_conventions) <= eligible
            or any(v not in ('positive_payment', 'signed_cash_flow') for v in capex_conventions.values())):
        raise ValueError('Capex conventions require exact eligible fact IDs and known conventions')
    accounting_bases = {} if accounting_bases is None else accounting_bases
    all_ids = {o['id'] for o in bundle['financial']['observations']}
    if (not isinstance(accounting_bases, dict) or not set(accounting_bases) <= all_ids
            or any(not isinstance(v, str) or not v.strip() or len(v) > 160 or '\n' in v for v in accounting_bases.values())):
        raise ValueError('Accounting bases require exact fact IDs and bounded explicit basis strings')
    groups, gaps = _inventory(bundle, capex_conventions, accounting_bases)
    _derive_quarters(groups, gaps)
    quarter_candidates = {p for r in groups for p in r['_periods'] if p[-1] == as_of and _family(p) == 'quarter'}
    if current_period is None and len(quarter_candidates) == 1:
        current_period = next(iter(quarter_candidates))
    elif current_period is None and len(quarter_candidates) > 1:
        gaps.append(_gap('Ambiguous current quarter boundaries; supply explicit current_period'))
    groups = _derive_metrics(groups, gaps)
    tables = []
    for family in FAMILIES:
        rows = []
        for group in groups:
            available = {p: c for p, c in group['_periods'].items() if _family(p) == family}
            if not available: continue
            current_matches = [p for p in available if p[-1] == as_of and (family != 'quarter' or p == current_period)]
            current_key = current_matches[0] if len(current_matches) == 1 else None
            current = available[current_key] if current_key else _unavailable(
                'Ambiguous current reporting boundaries' if len(current_matches)>1 or family=='quarter' and len(quarter_candidates)>1 else 'Current period missing',
                fact_ids=_ids([available[p] for p in current_matches]), status='ambiguous' if len(current_matches)>1 else 'missing')
            cells = {'current': deepcopy(current)}
            for slot, matcher in [('prior_quarter', _quarter_before), ('prior_year', _year_ago)]:
                matches = [c for p, c in available.items() if current_key and matcher(current_key, p)]
                if slot == 'prior_quarter' and family not in ('quarter', 'instant'): matches = []
                if slot == 'prior_quarter' and family == 'instant':
                    anchor = (date.fromisoformat(current_period[1])-timedelta(days=1)).isoformat() if current_period else None
                    matches = [c for c in matches if c['period'][1] == anchor]
                cells[slot] = deepcopy(matches[0]) if len(matches)==1 else _unavailable(
                    'Multiple comparable periods' if matches else 'Comparable prior period missing',
                    fact_ids=_ids(matches), status='ambiguous' if matches else 'missing')
            row = {k: deepcopy(v) for k, v in group.items() if not k.startswith('_')}
            row['cells'] = cells
            row['changes'] = {name: _change(cells['current'], cells[slot], percent_unit=group['unit']==PERCENT_UNIT,
                allowed=name=='yoy' or family in ('quarter', 'instant'), basis=group['basis'])
                for name, slot in [('qoq', 'prior_quarter'), ('yoy', 'prior_year')]}
            row['period_observations'] = [deepcopy(c) for p, c in sorted(available.items())]
            rows.append(row)
        if rows: tables.append({'period_family': family, 'rows': sorted(rows, key=lambda r: _key([r['metric_id'],r['label'],r['entity'],r['dimensions'],r['basis'],r['unit']]))})
    return {'version': VERSION, 'as_of': as_of, 'current_period': list(current_period) if current_period else None,
            'capex_conventions': deepcopy(capex_conventions), 'accounting_bases': deepcopy(accounting_bases), 'tables': tables, 'observations': deepcopy(bundle['financial']['observations']),
            'contexts': deepcopy(bundle['financial']['contexts']), 'units': deepcopy(bundle['financial']['units']),
            'gaps': gaps, 'arithmetic': {'numeric_type': 'Decimal', 'ratio_precision': 50,
            'net_debt_definition': 'current debt + noncurrent debt - cash and cash equivalents',
            'quarter_derivation': 'Only whitelisted additive monetary flows: same-fiscal-start cumulative difference',
            'comparison_policy': 'Filed boundaries; quarter adjacency; bounded 52/53-week year-ago matching; no annualization'}}
