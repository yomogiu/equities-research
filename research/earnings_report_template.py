"""Versioned, source-bound section layout. No model calls or new observations."""
from collections import OrderedDict
from datetime import date
from decimal import Decimal, localcontext

VERSION = 'source-led-six-sections-v1'
SECTIONS = OrderedDict([
    ('demand', 'Growth & Demand'),
    ('earnings', 'Earnings & Efficiency'),
    ('cash', 'Cash & Financial Capacity'),
    ('outlook', 'Outlook & Guidance'),
    ('qa', 'Questions That Matter — Earnings-Call Q&A'),
])

# Exact taxonomy identities, never keywords in an author's display label.
METRICS = {
    'RevenueFromContractWithCustomerExcludingAssessedTax': 'demand',
    'Revenues': 'demand', 'SalesRevenueNet': 'demand', 'Revenue': 'demand',
    'GrossProfit': 'earnings', 'OperatingIncomeLoss': 'earnings',
    'ProfitLossFromOperatingActivities': 'earnings', 'NetIncomeLoss': 'earnings',
    'ProfitLossAttributableToOwnersOfParent': 'earnings',
    'EarningsPerShareDiluted': 'earnings', 'DilutedEarningsLossPerShare': 'earnings',
}

INSTRUCTIONS = '''
## Source-led six-section report contract

Structure overrides older requests for next tests, valuation, an investment thesis
or word/finding quotas. Use supplied documents and call only; no broader market
research or new forecasts. Script renders Quarter in Focus; Growth & Demand;
Earnings & Efficiency; Cash & Financial Capacity; Outlook & Guidance;
Questions That Matter — Earnings-Call Q&A. Tables, units, comparisons, references
and colours are scripted. Do not author tables or repeat numbers without explanation.

Analysis: retain existing schema; add report_template: "source-led-six-sections-v1"
and section: demand|earnings|cash|outlook|qa to every finding. Opening supplies
Quarter in Focus. Return next_tests: []. No watchlist or portfolio conclusion.
Route each finding once; do not force commentary into unsupported sections.

Q&A remains substantive: select consequential actual questions and answers from
existing complete-call retrieval. Use Asked:, Management's answer:, Interpretation:
paragraphs where useful. Preserve speaker identity, qualifications, partial answers
and non-answers; cite original exchange/turn scopes. Explain supplied evidence
without a market thesis. Do not duplicate exchanges or impose an exchange quota.
If substantive Q&A is unavailable, state the gap rather than inventing exchanges.

Outlook covers company guidance. Optional valuation requires supplied, cited dated
price and forecast estimates, listing/currency/share-or-ADR basis and forecast
period. Otherwise omit it; do not request additional data to fill the template.

Review exact compiled candidate and existing Q&A coverage in the same fresh
session. Corrections retain template marker and section routing. Enabled signals
reuse existing findings within their sections; no separate Business signals section
or repeated summaries. Context-dependent movements remain neutral.
'''



def validate(analysis):
    marker = analysis.get('report_template')
    if marker is None:
        return
    if marker != VERSION:
        raise ValueError('Unknown report template')
    if analysis.get('next_tests') != []:
        raise ValueError('Six-section reports do not request next tests')
    if any(f.get('section') not in SECTIONS for f in analysis['findings']):
        raise ValueError('Every finding requires a supported report section')


def row_section(row):
    concept = row['concept']
    namespace, _, name = concept.partition(':')
    return METRICS.get(name, 'cash') if namespace in ('us-gaap', 'ifrs-full') else 'cash'


def comparisons(group, row):
    """Compare exact same-row contexts only; never blend YTD and quarters.

    Percentages use a positive denominator. Loss/zero comparisons are explicitly
    unavailable. Ratios need declared percentage semantics before computing pp.
    """
    result = {'QoQ': '—', 'YoY': '—'}
    periods = [p['key'] for p in group['periods']]
    if not periods or any(p[0] not in ('instant', 'duration') for p in periods):
        return result
    current = max(range(len(periods)), key=lambda i: periods[i][-1])
    p = periods[current]
    if p[0] == 'duration' and not 70 <= (date.fromisoformat(p[2]) - date.fromisoformat(p[1])).days + 1 <= 105:
        return result
    if group['unit'] == 'ratio':
        return result
    end = date.fromisoformat(p[-1])
    for i, prior in enumerate(periods):
        if i == current or prior[0] != p[0]:
            continue
        old_end = date.fromisoformat(prior[-1])
        if prior[0] == 'duration':
            days = (old_end - date.fromisoformat(prior[1])).days + 1
            if not 70 <= days <= 105:
                continue
            sequential = (date.fromisoformat(p[1]) - old_end).days == 1
            annual = (end.year == old_end.year + 1 and
                      (p[1][5:], p[2][5:]) == (prior[1][5:], prior[2][5:]))
        else:
            # Calendar/fiscal quarter-end dates are explicit; arbitrary 90-day
            # snapshots do not become quarterly comparisons.
            sequential = ((end.year * 12 + end.month) - (old_end.year * 12 + old_end.month) == 3
                          and (end.day == old_end.day or end.day >= 28 and old_end.day >= 28))
            annual = end.year == old_end.year + 1 and (end.month, end.day) == (old_end.month, old_end.day)
        kind = 'QoQ' if sequential else 'YoY' if annual else None
        if kind is None:
            continue
        value = Decimal(row['cells'][current]['original_value'])
        baseline = Decimal(row['cells'][i]['original_value'])
        ids = row['cells'][current]['fact_ids'] + row['cells'][i]['fact_ids']
        citation = ' '.join('[^' + fid + ']' for fid in dict.fromkeys(ids))
        if baseline <= 0:
            result[kind] = 'n/m ' + citation
        else:
            with localcontext() as ctx:
                ctx.prec = 50
                delta = (value - baseline) / baseline * 100
                rounded = delta.quantize(Decimal('0.1'))
            result[kind] = ('0.0%' if rounded == 0 else f'{rounded:+.1f}%') + ' ' + citation
    return result


def financial_sections(financial, bundle, formatting):
    from . import earnings_financial_display as display
    from . import earnings_mixed_runner as base
    from . import earnings_report_repair as repair
    from .earnings_markdown import cell, refs
    repair.validate_format(formatting, financial, bundle)
    if formatting.get('layout') or formatting.get('source_rows'):
        raise ValueError('Six-section tables require original rows without legacy folds or source-row overlays')
    compiled = display.build(financial, bundle)
    sections = {key: [] for key in SECTIONS}
    for group in compiled['groups']:
        key = 'table-' + base.digest([group['unit'], group['periods']])[:20]
        labels = formatting.get('tables', {}).get(key, {})
        periods = labels.get('period_labels', [p['label'] for p in group['periods']])
        unit = labels.get('unit_label', group['unit'])
        grouped = OrderedDict()
        for row in group['rows']:
            grouped.setdefault(row_section(row), []).append(row)
        for section, rows in grouped.items():
            lines = sections[section]
            lines.extend([unit + ' ' + refs(labels.get('citations', [])), '',
                          '| Metric | ' + ' | '.join(cell(p) for p in periods) + ' | QoQ | YoY |',
                          '| ' + ' | '.join('---' for _ in range(len(periods) + 3)) + ' |'])
            for row in rows:
                rid = 'row-' + base.digest([row['concept'], row['dimensions'], group['unit'], group['periods']])[:20]
                override = formatting['rows'].get(rid, {})
                label = override.get('label', row['metric'])
                dims = override.get('dimensions', row['dimensions'])
                label += (' · ' + dims if dims else '')
                label += ' ' + refs(override.get('citations', []))
                changes = comparisons(group, row)
                values = [c['value'] + ' ' + refs(c['fact_ids']) for c in row['cells']]
                lines.append('| ' + ' | '.join(cell(x) for x in [label, *values, changes['QoQ'], changes['YoY']]) + ' |')
            lines.extend(['', 'QoQ/YoY: calculated from the cited same-row observations; n/m means a nonpositive comparison base. — means no supported comparison.', ''])
    notes = compiled['basis_notes'] + compiled.get('source_context_notes', [])
    if formatting['basis']['text']:
        notes = [*notes, formatting['basis']]
    for note in notes:
        sections['cash'].extend([note['text'] + ' ' + refs(note['citations']), ''])
    return sections


def report(state, bundle, catalog, pack=None):
    from . import earnings_passages as passages, earnings_signals as signals
    from .earnings_markdown import refs
    analysis = state['artifacts']['analysis']
    validate(analysis)
    out = passages.hydrate('analysis', analysis, catalog)
    tables = financial_sections(state['artifacts']['financial'], bundle, state['format'])
    lines = ['# ' + out['title'], '', '## Quarter in Focus', '',
             out['opening'] + ' ' + refs(out['opening_citations']), '']
    by_finding = {}
    if pack is not None:
        signals.validate(pack, state, bundle, catalog)
        fc = signals.finding_catalog(state)
        for signal in pack['signals']:
            by_finding.setdefault(fc[signal['finding_id']]['index'], []).append(signal)
    for key, heading in SECTIONS.items():
        lines.extend(['## ' + heading, '', *tables[key]])
        findings = [(i, f) for i, f in enumerate(out['findings']) if f['section'] == key]
        for i, finding in findings:
            lines.extend(['### ' + finding['heading'], ''])
            for signal in by_finding.get(i, []):
                lines.extend([signals.DIRECTIONS[signal['direction']] + ' · ' + signals.BASES[signal['evidence_basis']] +
                              ' · ' + signal['period'] + ' ' + refs(signal['citations']), ''])
            lines.extend([finding['text'] + ' ' + refs(finding['citations']), ''])
            for quote in finding['quotes']:
                lines.extend(['\n'.join('> ' + line for line in quote['text'].splitlines()) + ' ' + refs([quote['scope_id']]), ''])
        if not findings and not tables[key]:
            lines.extend(['No additional source-backed commentary supplied for this section.' if key != 'qa' else
                          'No substantive Q&A selection supplied; call coverage remains a review requirement.', ''])
    lines.extend(['## Scope', '', out['scope'], '', '## Source references', ''])
    import re
    used = set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]', '\n'.join(lines)))
    lines.extend('[^' + identifier + ']: Original evidence ' + identifier for identifier in sorted(used))
    return '\n'.join(lines).rstrip() + '\n'
