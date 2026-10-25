"""Frozen annual EPS and dated quote observations; no model-supplied numbers.

Recognized formats only. Missing/ambiguous symbols, units or periods stay absent.
Semantic accounting basis and post-filing share changes still require review.
"""
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import re
from urllib.parse import urlsplit
from . import financial_evidence as financial
from . import earnings_runtime_common as storage

EPS_CONCEPTS={'us-gaap:EarningsPerShareDiluted','us-gaap:EarningsPerShareBasicAndDiluted',
              'us-gaap:IncomeLossFromContinuingOperationsPerDilutedShare','ifrs-full:DilutedEarningsLossPerShare'}
_CACHE={}


def source_id(document_id): return 'document-source-'+document_id[:20]


def _identity(context):
    return storage.digest({k:context[k] for k in ('entity','entity_scheme','dimensions')})


def build(bundle):
    if bundle.get('valuation_inventory') is not None:
        return deepcopy(bundle['valuation_inventory'])
    sources=bundle['manifest']['sources']
    inputs=[s for s in sources if (s['kind']=='filing' and s['representation']=='raw') or (s['kind']=='transcript' and s['representation']=='text')]
    # Recheck bytes even when the parsed result is cached in this process.
    for s in inputs:
        if storage.sha(s['path'])!=s['sha256']:raise ValueError('Valuation source changed')
    key=storage.digest(inputs)
    if key in _CACHE:return deepcopy(_CACHE[key])
    prices=[];earnings=[]
    for s in inputs:
        try:raw=Path(s['path']).read_bytes().decode('utf-8')
        except UnicodeDecodeError:continue
        if s['kind']=='transcript':
            url=urlsplit(s.get('url',''));ticker=re.fullmatch(r'/stocks/([^/]+)/transcripts/[^/]+/?',url.path)
            if url.hostname!='stockanalysis.com' or ticker is None:continue
            header=raw.split('Earnings Call:',1)[0]
            pattern=r'^([A-Z][A-Z ]*): ([A-Z0-9.\-]+) · Real-Time Price · ([A-Z]{3})\s*\n[^\n]*\n([0-9,]+\.[0-9]+)\s*\n[^\n]*\n(?:At close: )?([A-Z][a-z]{2} \d{1,2}, \d{4}),(?:[^\n]*Market closed|[^\n]*[AP]M [A-Z]{2,5})$'
            for match in re.finditer(pattern,header,re.M):
                exchange,symbol,currency,value,quoted=match.groups()
                if 'At close: ' not in match[0] and not match[0].endswith('Market closed'):continue
                if symbol.lower()!=ticker[1].lower():continue
                row={'symbol':symbol,'currency':currency,'value':str(financial._decimal(value.replace(',',''))),
                     'date':datetime.strptime(quoted,'%b %d, %Y').date().isoformat(),'source_id':'transcript-source',
                     'document_id':s['document_id'],'source_sha256':s['sha256'],'start':match.start(),'end':match.end(),'text':match[0]}
                row['id']='P-'+storage.digest(row)[:20];prices.append(row)
            continue
        extracted=financial.extract_inline_xbrl(raw,{'document_id':s['document_id'],'raw_sha256':s['sha256']})
        parser=financial._Parser(raw);parser.feed(raw);parser.close()
        nodes=list(parser.root.all('context'));contexts={}
        for node in nodes:
            try:contexts[node.attrs.get('id')]=financial._context(node)
            except ValueError:continue
        # Duplicate contexts cannot qualify a security binding.
        duplicate={k for k in contexts if sum(n.attrs.get('id')==k for n in nodes)>1}
        symbols={}
        for node in parser.root.all('nonnumeric'):
            cid=node.attrs.get('contextref');c=contexts.get(cid)
            if node.attrs.get('name')=='dei:TradingSymbol' and c and cid not in duplicate:
                symbol=node.text().strip()
                if re.fullmatch(r'[A-Z0-9.\-]+',symbol):symbols.setdefault(_identity(c),set()).add(symbol)
        grouped={}
        for obs in extracted['observations']:
            c=obs['context'];u=obs['unit'];symbol=symbols.get(_identity(c),set())
            if (obs['concept'] not in EPS_CONCEPTS or obs.get('nil') or obs.get('status')!='extracted' or
                    not c.get('start_date') or not c.get('end_date') or len(symbol)!=1 or
                    u['denominator']!=['xbrli:shares'] or len(u['numerator'])!=1 or not u['numerator'][0].startswith('iso4217:')):continue
            if not 350<=(date.fromisoformat(c['end_date'])-date.fromisoformat(c['start_date'])).days+1<=380:continue
            identity={k:c[k] for k in ('entity','entity_scheme','dimensions')}
            row={'symbol':next(iter(symbol)),'currency':u['numerator'][0].split(':')[1],'value':obs['value'],
                 'period_start':c['start_date'],'period_end':c['end_date'],'identity':identity,'concept':obs['concept'],
                 'document_id':s['document_id'],'source_sha256':s['sha256'],'source_id':source_id(s['document_id'])}
            k=storage.digest(row)
            if k not in grouped:grouped[k]={**row,'id':'E-'+k[:20],'observations':[]}
            grouped[k]['observations'].append({'id':obs['observation_id'],'support':obs['support']})
        earnings.extend(grouped.values())
    result={'prices':prices,'annual_eps':earnings,'scope':'Reparsed frozen filings and recognized dated source headers. Core financial facts are unchanged. Selection and interpretation remain independently reviewed.'}
    _CACHE[key]=result
    return deepcopy(result)


def resolve(row,bundle,inventory=None):
    """Bind IDs, or recover an old scalar proposal only from unique filed inputs."""
    inventory=inventory if inventory is not None else build(bundle)
    if set(row)=={'price_id','eps_id','accounting_basis'}:
        prices=[p for p in inventory['prices'] if p['id']==row['price_id']]
        eps=[e for e in inventory['annual_eps'] if e['id']==row['eps_id']]
    else:
        from . import earnings_compact_evidence as evidence
        expected={'price','eps','price_date','period_kind','period_start','period_end','accounting_basis'}
        if set(row)!=expected or row['period_kind']!='annual':raise ValueError('Exact inventory valuation selection required')
        scopes=evidence._scopes(bundle)
        source_ids=[scopes.get(row[k].get('source_id'),[]) for k in ('price','eps')]
        if any(len(s)!=1 for s in source_ids):raise ValueError('Unique original proposal source required')
        # Recover source selection, never trust the model-copied quotation or share basis.
        prices=[p for p in inventory['prices'] if p['document_id']==source_ids[0][0]['document_id'] and p['date']==row['price_date'] and financial._decimal(p['value'])==financial._decimal(row['price']['token']) and p['currency']==row['price']['currency'] and re.match(re.escape(p['symbol'])+r'(?:\s|$)',row['price']['security'])]
        eps=[e for e in inventory['annual_eps'] if e['document_id']==source_ids[1][0]['document_id'] and e['period_start']==row['period_start'] and e['period_end']==row['period_end'] and financial._decimal(e['value'])==financial._decimal(row['eps']['token']) and e['currency']==row['eps']['currency'] and re.match(re.escape(e['symbol'])+r'(?:\s|$)',row['eps']['security'])]
    if len(prices)!=1 or len(eps)!=1:raise ValueError('Valuation selection must bind unique deterministic price and annual EPS observations')
    price,eps=prices[0],eps[0]
    if price['symbol']!=eps['symbol'] or price['currency']!=eps['currency']:raise ValueError('Price and filed EPS security/currency differ')
    if eps['period_end']>price['date'] or financial._decimal(price['value'])<=0:raise ValueError('Positive dated price and previously reported annual earnings required')
    return {'price':price,'eps':eps,'accounting_basis':row['accounting_basis']}
