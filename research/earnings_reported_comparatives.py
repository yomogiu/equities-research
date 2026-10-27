"""Narrow original-release comparative extraction; no models or inferred EPS.

Only a calendar-quarter net-income sentence anchored to the filed current EPS
and rounded current income qualifies. Other prose formats remain unsupported.
Original facts stay immutable; the added cell cites its original D scope and
carries exact character offsets/hashes for independent inspection.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from pathlib import Path
import re

from . import earnings_financial_analysis as analysis

ORDINALS = ('first', 'second', 'third', 'fourth')
NUMBER = r'\d+(?:\.\d+)?'
PATTERN = re.compile(
    r'^Net\s+income\s+for\s+the\s+(?P<quarter>first|second|third|fourth)\s+quarter'
    r'(?:\s+of\s+(?P<year>\d{4}))?\s+was\s+\$(?P<income>'+NUMBER+r')\s+million,\s+or\s+'
    r'\$(?P<eps>'+NUMBER+r')\s+per\s+diluted\s+share,\s+compared\s+to\s+net\s+income\s+of\s+'
    r'\$(?P<prior_income>'+NUMBER+r')\s+million,\s+or\s+\$(?P<prior_eps>'+NUMBER+r')\s+per\s+'
    r'diluted\s+share,\s+for\s+the\s+(?P<prior_quarter>first|second|third|fourth)\s+quarter\s+of\s+(?P<prior_year>\d{4})\b',
    re.I | re.M)


def supplement(value, bundle):
    period = value.get('current_period')
    if not period: return value
    start, end = (date.fromisoformat(x) for x in period[1:])
    if start.day != 1 or start.month not in (1, 4, 7, 10): return value
    next_month = start.month + 3
    following = date(start.year + int(next_month > 12), (next_month-1) % 12+1, 1)
    if end != following-timedelta(days=1): return value
    prior_end = start-timedelta(days=1)
    prior_start = date(prior_end.year, ((prior_end.month-1)//3)*3+1, 1)
    eps_rows = [r for t in value['tables'] if t['period_family']=='quarter' for r in t['rows']
                if r['metric_id']=='diluted_eps' and not r['dimensions'] and r['basis']=='GAAP'
                and r['unit']=={'numerator':['iso4217:USD'],'denominator':['xbrli:shares']}
                and r['cells']['current']['status']=='available']
    if len(eps_rows) != 1: return value
    eps = eps_rows[0]
    incomes = [r for t in value['tables'] if t['period_family']=='quarter' for r in t['rows']
               if r['metric_id']=='net_income' and not r['dimensions'] and r['basis']==eps['basis']
               and r['entity']==eps['entity'] and r['entity_scheme']==eps['entity_scheme']
               and r['unit']=={'numerator':['iso4217:USD'],'denominator':[]}
               and r['cells']['current']['status']=='available']
    if len(incomes) != 1: return value
    matches = []; cache = {}
    for chunk in bundle.get('documents', {}).get('chunks', []):
        if chunk['kind'] != 'release': continue
        binding = (chunk['path'],chunk['sha256'],chunk['document_id'])
        if not any((s['path'],s['sha256'],s['document_id'])==binding and s.get('representation')=='text'
                   for s in bundle['manifest']['sources']): raise ValueError('Comparative source is not frozen')
        if binding not in cache:
            raw = Path(chunk['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=chunk['sha256']: raise ValueError('Comparative original source changed')
            cache[binding] = raw.decode('utf-8')
        text = cache[binding]; excerpt = text[chunk['start']:chunk['end']]
        if hashlib.sha256(excerpt.encode()).hexdigest()!=chunk['span_sha256']:
            raise ValueError('Comparative original scope changed')
        # Explicit release quarter/date anchor; do not infer a noncalendar fiscal year.
        anchor = (ORDINALS[(start.month-1)//3]+r'\s+quarter\s+ended\s+'
                  +end.strftime('%B')+r'\s+'+str(end.day)+r',\s+'+str(end.year))
        if not re.search(anchor,text[:2500],re.I): continue
        for match in PATTERN.finditer(excerpt):
            m=match.groupdict()
            if (m['quarter'].lower()!=ORDINALS[(start.month-1)//3]
                or m['year'] is not None and int(m['year'])!=end.year
                or m['prior_quarter'].lower()!=ORDINALS[(prior_end.month-1)//3]
                or int(m['prior_year'])!=prior_end.year): continue
            if Decimal(m['eps']) != Decimal(eps['cells']['current']['value']): continue
            reported_income=Decimal(m['income'])
            rounded=(Decimal(incomes[0]['cells']['current']['value'])/Decimal(1000000)).quantize(
                Decimal(1).scaleb(reported_income.as_tuple().exponent),rounding=ROUND_HALF_UP)
            if rounded!=reported_income: continue
            begin=chunk['start']+match.start(); finish=chunk['start']+match.end()
            matches.append({'status':'available','value':str(Decimal(m['prior_eps'])),
                'period':['duration',prior_start.isoformat(),prior_end.isoformat()], 'fact_ids':[chunk['id']],
                'source_labels':['Reported diluted EPS'], 'reason':None,
                'calculation':{'operator':'reported_comparative', 'rule':'release_calendar_quarter_eps_v1',
                    'document_id':chunk['document_id'],'sha256':chunk['sha256'],
                    'start':begin,'end':finish,'span_sha256':hashlib.sha256(text[begin:finish].encode()).hexdigest(),
                    'offset_unit':'unicode_character','accounting_basis':'GAAP',
                    'current_eps_anchor':eps['cells']['current']['fact_ids'],
                    'current_income_anchor':incomes[0]['cells']['current']['fact_ids']}})
    if not matches or len({m['value'] for m in matches})!=1: return value
    prior=eps['cells']['prior_quarter']
    if prior['status']!='missing': return value  # Never replace available/conflicting filed evidence.
    result=deepcopy(value)
    for table in result['tables']:
        for row in table['rows']:
            if table['period_family']=='quarter' and row==eps:
                cell=matches[0]
                cell['fact_ids']=sorted({i for m in matches for i in m['fact_ids']})
                cell['calculation']['additional_support']=[m['calculation'] for m in matches[1:]]
                row['cells']['prior_quarter']=cell
                row['period_observations'].append(deepcopy(cell))
                row['changes']['qoq']=analysis._change(row['cells']['current'],cell,basis=row['basis'])
    return result
