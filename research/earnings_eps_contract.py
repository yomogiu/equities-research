"""Source-bound EPS records, compatible comparisons and optional reconciliation.

No inferred EPS, quarter subtraction, annualization or model-provided numbers.
Original reported figures remain authoritative; absent inputs are local gaps.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
import re
import hashlib
from . import earnings_runtime_common as storage

VERSION='source-bound-eps-v1'
DILUTED={'us-gaap:EarningsPerShareDiluted','us-gaap:EarningsPerShareBasicAndDiluted',
         'ifrs-full:DilutedEarningsLossPerShare'}
BASIC={'us-gaap:EarningsPerShareBasic','ifrs-full:BasicEarningsLossPerShare'}
AMOUNT=re.compile(r'(?<![A-Za-z0-9])\(?-?\d[\d,]*\.\d+\)?(?![A-Za-z0-9])')
DURATION=re.compile(r'(?:(Three|Six|Nine|Twelve)\s+Months?|Years?)\s+Ended\b',re.I)
MONTHS={'three':3,'six':6,'nine':9,'twelve':12}
NAMES={name.lower():i for i,name in enumerate('January February March April May June July August September October November December'.split(),1)}


def decimal(value):
    n=Decimal(value)
    if not n.is_finite():raise ValueError('Finite EPS input required')
    return n


def half_rounding(value):
    return Decimal(1).scaleb(decimal(value).as_tuple().exponent)/2


def reconcile(eps,numerator,shares):
    """Inputs explicitly identify the EPS numerator and diluted weighted shares.

    Values are scaled absolute amounts; rounding is absolute uncertainty supplied
    from original precision, not a guessed percent tolerance. No generic profit
    or closing-share substitution is allowed by the input contract.
    """
    if eps.get('dilution')!='diluted':raise ValueError('Diluted EPS reconciliation requires an explicitly diluted EPS record')
    if not numerator or not shares:return {'status':'unavailable','reason':'Explicit matching EPS numerator and weighted-average diluted shares not supplied'}
    if numerator.get('role')!='eps_numerator' or shares.get('role')!='weighted_average_diluted_shares':
        raise ValueError('EPS-specific numerator and weighted-average diluted shares required')
    keys=('issuer','currency','period_start','period_end','months','accounting_basis','share_class')
    if any(any(v.get(k)!=eps.get(k) for k in keys) for v in (numerator,shares)):
        return {'status':'unavailable','reason':'Reconciliation inputs differ in issuer, period, currency, basis or share class'}
    n,s=decimal(numerator['value']),decimal(shares['value'])
    nr,sr=decimal(numerator['rounding']),decimal(shares['rounding'])
    if nr<0 or sr<0 or s-sr<=0:return {'status':'conflict','reason':'Invalid numerator precision or nonpositive diluted-share interval'}
    with localcontext() as ctx:
        ctx.prec=60
        values=[a/b for a in (n-nr,n+nr) for b in (s-sr,s+sr)]
        lo,hi=min(values),max(values);e=decimal(eps['value']);er=half_rounding(eps['value'])
        return {'status':'pass' if lo<=e+er and hi>=e-er else 'conflict',
                'calculated':str(n/s),'interval':[str(lo),str(hi)],
                'reason':'Reported precision intervals overlap' if lo<=e+er and hi>=e-er else 'Reported EPS is outside the disclosed numerator/share rounding interval'}


def _span(text,start,end):
    return {'start':start,'end':end,'sha256':hashlib.sha256(text[start:end].encode()).hexdigest(),'text':text[start:end]}


def _headers(text,position):
    """Bind a row only to its nearest complete original duration/year group."""
    prefix=text[max(0,position-6500):position];offset=max(0,position-6500)
    groups=list(DURATION.finditer(prefix))
    if not groups:return None
    # Keep just the final adjacent duration headings, never a previous table.
    last=groups[-1];group=[last]
    for h in reversed(groups[:-1]):
        if group[0].start()-h.end()>180:break
        group.insert(0,h)
    tail=prefix[last.end():]
    years=re.search(r'(?m)^[ \t]*(20\d{2})(?:[ \t]+20\d{2}){1,7}[ \t]*$',tail[:500])
    if not years:return None
    tokens=re.findall(r'20\d{2}',years[0])
    if len(tokens)%len(group):return None
    width=len(tokens)//len(group)
    if width not in (2,3):return None
    dates=list(re.finditer(r'\b('+'|'.join(NAMES)+r')\s+(\d{1,2})\b',prefix[group[0].start():last.end()+years.start()],re.I))
    if len(dates)!=len(group):return None
    periods=[]
    for i,h in enumerate(group):
        yy=tokens[i*width:(i+1)*width]
        if yy!=sorted(set(yy),reverse=True):return None
        month=NAMES.get(dates[i][1].lower())
        if not month:return None
        for year in yy:
            try:end=date(int(year),month,int(dates[i][2])).isoformat()
            except ValueError:return None
            periods.append({'months':MONTHS[h[1].lower()] if h[1] else 12,'period_start':None,'period_end':end})
    return periods,_span(text,offset+group[0].start(),offset+last.end()+years.end())


def _currency(text):
    matches=[]
    for pattern,currency in [(r'New Taiwan Dollars?|NT\$', 'TWD'),(r'U\.?S\.? dollars?|United States dollars|\bUSD\b','USD'),
                             (r'\bEUR\b|\beuros?\b','EUR'),(r'\bGBP\b|pounds sterling','GBP')]:
        match=re.search(pattern,text,re.I)
        if match:matches.append((currency,match))
    return matches[0] if len(matches)==1 else (None,None)


def _pdf_reconciliation(text,position,row,column,width):
    """Recognize an explicit EPS note; generic net income is never substituted."""
    headings=list(re.finditer(r'(?im)^\s*(?:\d+\.\s*)?EARNINGS PER SHARE[^\n]*$',text[:position]))
    if not headings:return row['reconciliation']
    start=headings[-1].start();body=text[start:start+6500]
    next_note=re.search(r'(?m)^\s*\d+\.\s+[A-Z][A-Z ]{3,}',body[len(headings[-1][0]):])
    if next_note:body=body[:len(headings[-1][0])+next_note.start()]
    units=list(re.finditer(r'(?im)^\s*\(In (Thousands?|Millions?) of [^\n]*Unless Stated Otherwise\)',text[:start]))
    if not units:return row['reconciliation']
    declared_currency,_=_currency(units[-1][0])
    if declared_currency!=row['currency']:return {'status':'unavailable','reason':'EPS numerator currency is not explicitly matched'}
    money_scale=Decimal(1000 if units[-1][1].lower().startswith('thousand') else 1000000)
    lines=list(re.finditer(r'[^\n]+',body));found={}
    for i,line in enumerate(lines):
        tokens=list(re.finditer(r'(?<![A-Za-z0-9])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![A-Za-z0-9])',line[0]))
        if len(tokens)!=width:continue
        prefix=' '.join(' '.join(x[0].split()) for x in lines[max(0,i-3):i])+ ' '+line[0][:tokens[0].start()]
        prefix=' '.join(prefix.split()).lower().rstrip(' $')
        role=('eps_numerator' if re.search(r'earnings used in the computation of basic and diluted earnings per share$',prefix) else
              'weighted_average_diluted_shares' if re.search(r'weighted average number of ordinary shares used in the computation of diluted earnings per share$',prefix) else None)
        if not role:continue
        period_headers=_headers(text,start+line.start())
        if not period_headers or len(period_headers[0])!=width or period_headers[0][column]!= {k:row[k] for k in ('months','period_start','period_end')}:continue
        scale=money_scale
        if role=='weighted_average_diluted_shares':
            share_units=list(re.finditer(r'\(in (thousand|million) shares\)',body[:line.start()],re.I))
            if not share_units:continue
            scale=Decimal(1000 if share_units[-1][1].lower()=='thousand' else 1000000)
        token=tokens[column][0];value=decimal(token.replace(',','').strip('()'))
        if token.startswith('('):value=-abs(value)
        operand={k:row[k] for k in ('issuer','currency','period_start','period_end','months','accounting_basis','share_class')}
        operand.update(role=role,value=str(value*scale),rounding=str(half_rounding(str(value))*scale),
                       support=_span(text,start+line.start(),start+line.end()),scale=str(scale),
                       unit_support=_span(text,units[-1].start(),units[-1].end()) if role=='eps_numerator' else _span(text,start+share_units[-1].start(),start+share_units[-1].end()))
        if role in found:return {'status':'unavailable','reason':'Ambiguous EPS reconciliation operands'}
        found[role]=operand
    result=reconcile(row,found.get('eps_numerator'),found.get('weighted_average_diluted_shares'))
    if found:result['operands']=found
    return result


def pdf_records(text,source,issuer,qualified_annual=()):
    """Primary EPS rows/notes with exact ordered duration/year headings only."""
    result=[]
    presentation=list(re.finditer(r'(?im)^\s*\(In [^\n]*(?:Dollars|USD|EUR|euros|pounds)[^\n]*\)\s*$',text))
    anchor=next((e for e in qualified_annual if e.get('document_id')==source['document_id'] and e.get('currency')),None)
    declaration=re.search(r'consolidated financial statements.{0,100}?(?:have been |are )?prepared in accordance with.{0,350}?(?:IFRS|IAS\s*34)',text,re.I|re.S)
    us=re.search(r'consolidated financial statements.{0,100}?prepared.{0,100}?(?:in accordance|in conformity).{0,200}?(?:U\.?S\.? GAAP|generally accepted accounting principles in the United States)',text,re.I|re.S)
    basis='IFRS' if declaration and not us else 'GAAP' if us and not declaration else anchor.get('basis') if anchor and not declaration and not us else None
    multiple_classes=bool(re.search(r'\bClass\s+[A-Z]\b|\bADSs?\b|\bADRs?\b|depositary',text,re.I))
    lines=list(re.finditer(r'[^\n]+',text))
    for i,line in enumerate(lines):
        before=text[max(0,line.start()-400):line.start()]
        label=line[0].split('$')[0]
        mode=re.match(r'^\s*(Basic|Diluted)\s+(?:(?:earnings|net income)(?: \(loss\))? per (?:common )?share(?:\([^)]*\))?\s*)?',line[0],re.I)
        if not mode:continue
        suffix=line[0][mode.end():]
        values=list(AMOUNT.finditer(suffix))
        if not values or not (re.search(r'earnings per share',label,re.I) or re.search(r'earnings per share[^\n]*\n\s*$',before,re.I) or
                                re.search(r'earnings per share[^\n]*\n\s*Basic[^\n]*\n\s*$',before,re.I)):continue
        # Weighted-average share rows and adjusted rows are never EPS values.
        if re.search(r'weighted|average|adjusted|continuing|discontinued',label,re.I):continue
        header=_headers(text,line.start())
        if not header or len(values)!=len(header[0]):continue
        periods,heading=header;dilution=mode[1].lower()
        local=[h for h in presentation if h.start()<line.start()]
        currency,currency_match=_currency(local[-1][0]) if local else (None,None)
        currency_offset=local[-1].start() if local else 0
        if not currency and anchor:currency=anchor['currency']
        for col,(token,period) in enumerate(zip(values,periods)):
            raw=token[0];n=decimal(raw.replace(',','').strip('()'))
            if raw.startswith('('):n=-abs(n)
            row={'issuer':issuer,'currency':currency,**period,'value':str(n),'dilution':dilution,
                 'accounting_basis':basis,'share_class':None if multiple_classes else 'single reported common/ordinary class',
                 'source_id':'document-source-'+source['document_id'][:20],'document_id':source['document_id'],
                 'source_sha256':source['sha256'],'origin':'reported_pdf','column':col+1,
                 'support':{'row':_span(text,line.start(),line.end()),'heading':heading,
                            'value':_span(text,line.start()+mode.end()+token.start(),line.start()+mode.end()+token.end())},
                 'reconciliation':{'status':'unavailable','reason':'No explicit matching EPS reconciliation bound'},'fact_ids':[]}
            if declaration or us:
                proof=declaration or us;row['support']['accounting_basis']=_span(text,proof.start(),proof.end())
            elif anchor:row['support']['accounting_basis']=anchor.get('basis_support',anchor.get('notice'))
            if currency_match:row['support']['currency']=_span(text,currency_offset+currency_match.start(),currency_offset+currency_match.end())
            elif anchor:row['support']['currency_binding']=anchor.get('currency_binding',anchor.get('security_binding'))
            row['status']='qualified' if currency and basis and row['share_class'] else 'ambiguous'
            if dilution=='diluted':row['reconciliation']=_pdf_reconciliation(text,line.start(),row,col,len(values))
            if row['reconciliation']['status']=='conflict':row['status']='conflict'
            row['id']='EPS-'+storage.digest(row)[:20];result.append(row)
    return result


def _same(a,b):
    return all(a.get(k)==b.get(k) for k in ('issuer','document_id','currency','accounting_basis','share_class','dilution','months'))


def comparison(current,prior,kind):
    if not _same(current,prior) or any(r['status']!='qualified' or r.get('reconciliation',{}).get('status')=='conflict' for r in (current,prior)):
        return {'status':'unavailable','reason':'Compatible qualified EPS records required'}
    a,b=date.fromisoformat(current['period_end']),date.fromisoformat(prior['period_end'])
    match=(357<=(a-b).days<=374 and a.month==b.month) if kind=='yoy' else (current['months']==3 and 70<=(a-b).days<=105)
    if not match:return {'status':'unavailable','reason':'Matching reported duration and comparison endpoints required'}
    with localcontext() as ctx:
        ctx.prec=60;x,y=decimal(current['value']),decimal(prior['value'])
        return {'status':'available' if y>0 else 'not_meaningful','absolute':str(x-y),
                'percent':str((x-y)/y*100) if y>0 else None,'current_id':current['id'],'prior_id':prior['id']}


def build(bundle):
    """Recompute from immutable source bytes; do not trust model/cache metadata."""
    from . import earnings_valuation_inventory as valuation
    from . import earnings_financial_context as context
    from .financial_reviewed_proposals import usable
    from . import earnings_financial_statement_context as statements
    bundle=statements.qualify(bundle)
    sources=bundle['manifest']['sources'];facts=bundle['financial'];records=[]
    case_path=bundle['manifest'].get('case_path');case=storage.read(case_path) if case_path else {}
    issuer=case.get('issuer_id')
    for source in sources:
        if source.get('kind') not in ('transcript','source_gap') and storage.sha(source['path'])!=source['sha256']:
            raise ValueError('EPS source changed')
    annual=valuation.build(bundle)['annual_eps']
    pdf_ids={s['document_id'] for s in sources if s['representation']=='raw' and Path(s['path']).read_bytes().startswith(b'%PDF')}
    for source in sources:
        if source['representation']!='text' or source['document_id'] not in pdf_ids:continue
        if storage.sha(source['path'])!=source['sha256']:raise ValueError('EPS source changed')
        records.extend(pdf_records(Path(source['path']).read_bytes().decode('utf-8'),source,issuer or source['document_id'],annual))
    selected=[o for o in facts['observations'] if o['concept'] in DILUTED|BASIC and usable(o,facts) and not o.get('nil')]
    identities=context.source_identities(bundle,[o['id'] for o in selected]) if selected else {}
    for o in selected:
        c=facts['contexts'][o['context_id']];u=facts['units'][o['unit_id']];identity=identities[o['id']]
        if not c.get('start_date') or not c.get('end_date') or u['denominator']!=['xbrli:shares'] or len(u['numerator'])!=1 or not u['numerator'][0].startswith('iso4217:'):continue
        from .earnings_period_comparisons import family
        duration=family(['duration',c['start_date'],c['end_date']]);months={'quarter':3,'half':6,'nine-month':9,'annual':12}.get(duration)
        row={'issuer':c['entity'],'currency':u['numerator'][0].split(':')[1],'months':months,'period_start':c['start_date'],'period_end':c['end_date'],
             'value':o['value'],'dilution':'diluted' if o['concept'] in DILUTED else 'basic','accounting_basis':identity.get('basis'),
             'share_class':storage.digest(c.get('dimensions',[])),'source_id':'document-source-'+o['source_document_id'][:20],
             'document_id':o['source_document_id'],'origin':'reported_fact','fact_ids':[o['id']],
             'support':{'fact_id':o['id'],'original_support':o['support']},'reconciliation':{'status':'unavailable','reason':'EPS-specific numerator not established'}}
        row['status']='qualified' if months and row['accounting_basis'] else 'ambiguous'
        row['id']='EPS-'+storage.digest(row)[:20];records.append(row)
    groups=defaultdict(list)
    for row in records:groups[storage.digest({k:row.get(k) for k in ('issuer','currency','period_end','period_start','months','dilution','accounting_basis','share_class')})].append(row)
    records=[]
    for rows in groups.values():
        conflicting=len({decimal(r['value']) for r in rows})>1 or any(r['reconciliation']['status']=='conflict' for r in rows)
        best=next((r for r in rows if r['reconciliation']['status']=='conflict'),next((r for r in rows if r['reconciliation']['status']=='pass'),rows[0]))
        if conflicting:
            for row in rows:row.update(status='conflict',reason='Conflicting EPS values or numerator/share reconciliation for the same period and basis')
        if len({decimal(r['value']) for r in rows})==1:
            best['additional_support']=[r['support'] for r in rows if r is not best]
            best['fact_ids']=sorted({fid for r in rows for fid in r['fact_ids']})
            records.append(best)
        else:records.extend(rows)
    for row in records:row['id']='EPS-'+storage.digest({k:v for k,v in row.items() if k!='id'})[:20]
    comparisons=[]
    for current in records:
        for kind in ('qoq','yoy'):
            eligible=[p for p in records if p['id']!=current['id'] and comparison(current,p,kind)['status']!='unavailable']
            values={p['value'] for p in eligible}
            if len(values)==1:comparisons.append({'kind':kind,**comparison(current,eligible[0],kind)})
    return {'version':VERSION,'records':records,'comparisons':comparisons,'read_only':True,
            'gap':None if any(r['status']=='qualified' and r['dilution']=='diluted' for r in records) else 'Diluted EPS could not be established on a matching currency, period and share basis. Original reported figures retain their own labels.',
            'policy':'Reported EPS only. No annualization or subtraction of cumulative EPS. Numerator reconciliation is optional; a conflict suppresses dependent calculations. Missing EPS does not fail a report.'}


def annual_eligible(eps):
    if eps.get('kind')=='annual_guidance':return eps.get('dilution')=='diluted' and eps.get('months')==12 and eps.get('basis') in ('GAAP','non-GAAP','IFRS') and eps.get('security_binding')=='matched-call-symbol-unambiguous-class'
    if eps.get('kind') in ('annual_reported_pdf','annual_reported_release'):return eps.get('basis') in ('GAAP','IFRS') and bool(eps.get('share_basis'))
    if eps.get('concept') not in DILUTED or not eps.get('period_start') or not eps.get('period_end'):return False
    return 350<=(date.fromisoformat(eps['period_end'])-date.fromisoformat(eps['period_start'])).days+1<=380


def _annual_problem(eps,registry):
    if not annual_eligible(eps):return 'Explicit annual diluted earnings required'
    if eps.get('kind')=='annual_guidance':return None
    matching=[r for r in registry['records'] if r['document_id']==eps['document_id'] and r['period_end']==eps['period_end'] and r['months']==12 and r['dilution']=='diluted']
    if any(r['status']=='conflict' for r in matching):return 'Conflicting annual EPS reconciliation'
    if matching and not any(r['status']=='qualified' and decimal(r['value'])==decimal(eps['value']) for r in matching):return 'Annual EPS period, value or basis not qualified'
    if eps.get('concept') and not matching:return 'Annual tagged EPS is not qualified in the EPS register'
    return None


def valuation_view(bundle,registry):
    """Only eligible annual inputs reach new authors; all gaps stay inspectable."""
    from . import earnings_valuation_inventory
    value=earnings_valuation_inventory.build(bundle)
    qualified=[];gaps=[]
    for eps in value['annual_eps']:
        reason=_annual_problem(eps,registry)
        if reason:gaps.append({'eps_id':eps['id'],'reason':reason})
        else:qualified.append(eps)
    return {**value,'annual_eps':qualified,'eps_qualification_gaps':gaps}


def validate_annual(eps,bundle):
    if not annual_eligible(eps):raise ValueError('Annual diluted EPS qualification required; basic, interim and continuing-only EPS cannot supply this multiple')
    if eps.get('kind')=='annual_guidance' or not bundle.get('packet_inventory'):return
    reason=_annual_problem(eps,build(bundle))
    if reason:raise ValueError(reason)


def validate_selection(value,registry):
    known={f:r for r in registry['records'] for f in r['fact_ids']}
    for row in value['rows']:
        if row['metric']!='diluted_eps':continue
        for fid in row['fact_ids']:
            r=known.get(fid)
            if not r or r['dilution']!='diluted' or r['status']!='qualified' or r['reconciliation']['status']=='conflict':
                raise ValueError('Diluted EPS selection requires a qualified source-bound EPS record: '+fid)


def render(registry):
    from .earnings_markdown_render import cell,refs
    rows=[];seen=set()
    for row in registry['records']:
        if row['dilution']!='diluted':continue
        key=tuple(row.get(k) for k in ('issuer','currency','period_end','months','accounting_basis','share_class','value','status'))
        if key in seen:continue
        seen.add(key);rows.append(row)
    if not rows:return ['### Diluted EPS','',registry['gap'] or 'Qualified diluted EPS unavailable.','']
    lines=['### Reported diluted EPS','', '| Period | Currency / basis | Reported EPS | QoQ change | YoY change | Validation |','| --- | --- | --- | --- | --- | --- |']
    for row in sorted(rows,key=lambda r:(r['months'],r['period_end']),reverse=True):
        def change(kind):
            changes=[c for c in registry['comparisons'] if c['kind']==kind and c.get('current_id')==row['id']]
            item=changes[0] if changes else {};percent=item.get('percent')
            return format(decimal(percent).quantize(Decimal('0.01')),'f')+'%' if percent is not None else 'N/M' if item.get('status')=='not_meaningful' else '—'
        status=('Unresolved discrepancy' if row['status']=='conflict' else 'Currency, basis or share class unresolved' if row['status']!='qualified' else
                'Matches disclosed earnings and diluted shares' if row['reconciliation']['status']=='pass' else 'Reported; matching reconciliation inputs unavailable')
        values=[str(row['months'])+' months ended '+row['period_end'],str(row['currency'] or 'currency unavailable')+' / '+str(row['accounting_basis'] or 'basis unavailable'),row['value']+' '+refs([row['source_id']]),change('qoq'),change('yoy'),status]
        lines.append('| '+' | '.join(cell(v) for v in values)+' |')
    for row in rows:
        if row['status']=='conflict':
            rec=row['reconciliation'];detail=(' Disclosed EPS numerator / diluted shares = '+format(decimal(rec['calculated']).quantize(Decimal('0.000001')),'f')+'.') if rec.get('calculated') else ''
            lines+=['',str(row['months'])+' months ended '+row['period_end']+': reported EPS '+row['value']+' has an unresolved validation conflict.'+detail+' Dependent growth rates and earnings multiples are unavailable; the reported figure is not replaced. '+refs([row['source_id']]) ]
    return lines+['','Reported EPS is retained as filed. Missing reconciliation inputs do not imply an incorrect reported figure.','']
