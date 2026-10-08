"""Render explicitly selected original observations, retaining XBRL nil semantics."""
import html
from . import earnings_financial_display as display


def build(selections, bundle):
    if not isinstance(selections, list) or len(selections) > 12:
        raise ValueError('Bounded supplemental source rows required')
    if not selections: return []
    facts = bundle['financial']; observations = {o['id']: o for o in facts['observations']}
    rows = []; seen = set()
    for selection in selections:
        if not isinstance(selection, dict) or set(selection) != {'label', 'fact_ids'}:
            raise ValueError('Supplemental row accepts label and original fact IDs only')
        label, ids = selection['label'], selection['fact_ids']
        if not isinstance(label, str) or not label.strip() or len(label) > 160:
            raise ValueError('Bounded supplemental label required')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 8:
            raise ValueError('Bounded original fact selection required')
        identity = None; periods = set()
        for fid in ids:
            if not isinstance(fid,str) or fid not in observations or fid in seen:
                raise ValueError('Unknown or duplicate supplemental fact')
            seen.add(fid); obs = observations[fid]
            if obs['status'] != 'extracted':
                raise ValueError('Unqualified supplemental fact')
            ctx = facts['contexts'][obs['context_id']]; unit = facts['units'][obs['unit_id']]
            current = (obs['concept'],ctx['entity'],ctx['dimensions'],unit)
            if identity is not None and current != identity:
                raise ValueError('Supplemental comparison changes metric, entity, dimensions or unit')
            identity = current; period = display.period_key(ctx)
            if period in periods: raise ValueError('Duplicate supplemental comparison period')
            periods.add(period)
            if obs.get('nil') is True:
                if obs['value'] is not None: raise ValueError('Nil observation has a numeric value')
                value = '— (reported nil)'
                _, unit_label, _ = display.scaled_value({**obs,'value':'0'},unit)
            else:
                if obs['value'] is None: raise ValueError('Missing value without source nil flag')
                value,unit_label,_ = display.scaled_value(obs,unit)
            rows.append({'label':label,'period':display.period_label(period),'value':value,
                         'unit':unit_label,'fact_id':fid,'dimensions':display.dimensions_label(ctx['dimensions'])})
    return rows


def render(selections,bundle,refs=None):
    rows=build(selections,bundle)
    if not rows:return ''
    if refs is None:
        return '\nSupplemental financial comparison\n'+'\n'.join(
            ' | '.join([r['label'],r['period'],r['value'],r['unit'],r['dimensions'],'['+r['fact_id']+']']) for r in rows)
    e=html.escape
    return '<table><caption>Supplemental financial comparison</caption><thead><tr><th>Measure</th><th>Period</th><th>Value</th><th>Unit</th><th>Source</th></tr></thead><tbody>'+''.join(
        '<tr><th>'+e(r['label'])+(' · '+e(r['dimensions']) if r['dimensions'] else '')+'</th><td>'+e(r['period'])+'</td><td>'+e(r['value'])+'</td><td>'+e(r['unit'])+'</td><td>'+refs([r['fact_id']])+'</td></tr>' for r in rows)+'</tbody></table>'
