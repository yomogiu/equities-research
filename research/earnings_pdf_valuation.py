"""Conservative annual diluted EPS from original audited USD PDF statements."""
from datetime import datetime
from decimal import Decimal
import re
from . import earnings_runtime_common as storage


def annual_eps(text,source,prices):
    quotes={(p['symbol'],p['currency']) for p in prices}
    if len(quotes)!=1 or not re.search(r'FORM\s+10-K\b',text[:15000],re.I):return []
    symbol,currency=next(iter(quotes))
    if currency!='USD':return []
    cover=text[:15000]
    if re.search(r'American\s+Depositar[yi]|\bADSs?\b|\bADRs?\b',cover,re.I):return []
    ticker_lines=list(re.finditer(r'(?m)^.*\b'+re.escape(symbol)+r'\b.*$',cover))
    if not ticker_lines:return []
    basis=re.search(r'U\.?S\.?\s*GAAP|(?:generally\s+accepted\s+accounting\s+principles|accounting\s+principles\s+generally\s+accepted)\s+in\s+(?:the\s+)?United\s+States',text,re.I)
    if not basis:return []
    pages=list(re.finditer(r'(?m)^\[Page \d+\]\n',text));result=[]
    for i,page in enumerate(pages):
        end=pages[i+1].start() if i+1<len(pages) else len(text);body=text[page.start():end]
        if not re.search(r'(?im)^[ \t]*Consolidated (?:Income Statements|Statements of (?:Income|Operations|Earnings))[ \t]*$',body):continue
        if not re.search(r'U\.?S\.?\s+dollars',body,re.I) or not re.search(r'except[^\n]{0,100}per[ -]share',body,re.I):continue
        header=re.search(r'(?:For\s+the\s+)?(?:Fiscal\s+)?Years?\s+Ended\s+([A-Za-z]+)\s+(\d{1,2})',body,re.I)
        if not header:continue
        years_line=re.search(r'(?m)^[ \t]*(20\d{2})(?:[ \t]+20\d{2}){1,3}[ \t]*$',body[header.end():header.end()+400])
        if not years_line:continue
        years=re.findall(r'20\d{2}',years_line[0])
        if years!=sorted(set(years),reverse=True):continue
        try:period_end=datetime.strptime(header[1]+' '+header[2]+', '+years[0],'%B %d, %Y').date().isoformat()
        except ValueError:continue
        headings=list(re.finditer(r'(?im)^[ \t]*(?:Earnings|Net income) per ([^\n:]{1,70})share[^\n]*$',body))
        for heading in headings:
            following=body[heading.end():]
            diluted=re.search(r'(?im)^[ \t]*(?:[—–-][ \t]*)?Diluted[ \t]+([^\n]+)',following)
            if not diluted or re.search(r'weighted\s+average',following[:diluted.start()],re.I):continue
            tokens=re.findall(r'\(?-?\d[\d,]*\.\d+\)?',diluted[1])
            if len(tokens)!=len(years):continue
            token=tokens[0];amount=Decimal(token.replace(',','').strip('()'))
            if token.startswith('('):amount=-abs(amount)
            share_basis=heading[1].strip();share_class=re.search(r'Class\s+([A-Z])\b',share_basis,re.I)
            def matches(line):
                if share_class:return bool(re.search(r'Class\s+'+share_class[1]+r'\b',line,re.I))
                return any(word in share_basis.casefold() and word in line.casefold() for word in ('common','ordinary'))
            bound=[line for line in ticker_lines if matches(line[0])]
            if len(bound)!=1:continue
            row={'kind':'annual_reported_pdf','symbol':symbol,'currency':'USD','value':str(amount),
                 'period_start':None,'period_end':period_end,'fiscal_year':int(years[0]),'basis':'GAAP',
                 'share_basis':share_basis,'security_binding':'exact-cover-ticker-and-share-class',
                 'source_id':'document-source-'+source['document_id'][:20],
                 'document_id':source['document_id'],'source_sha256':source['sha256'],
                 'start':page.start(),'end':end,'text':body,
                 'security_support':{'start':bound[0].start(),'end':bound[0].end(),'text':bound[0][0]},
                 'basis_support':{'start':basis.start(),'end':basis.end(),'text':basis[0]},
                 'notice':'Reported annual diluted EPS from an original audited USD statement. Fiscal end is explicit; start is not inferred. Review share class, accounting basis and original headings.'}
            row['id']='E-'+storage.digest(row)[:20];result.append(row)
    return result


def unique_pair(inventory):
    prices=inventory['prices']
    if len(prices)!=1 or Decimal(prices[0]['value'])<=0:return None
    price=prices[0]
    eligible=[e for e in inventory['annual_eps'] if (e.get('kind'),e.get('security_binding')) in {
              ('annual_reported_pdf','exact-cover-ticker-and-share-class'),('annual_reported_release','matched-release-listing-and-quote')}
              and e.get('basis')=='GAAP'
              and e['symbol']==price['symbol'] and e['currency']==price['currency']
              and e['period_end']<=price['date'] and Decimal(e['value'])>0]
    if not eligible:return None
    latest=max(e['period_end'] for e in eligible);eligible=[e for e in eligible if e['period_end']==latest]
    if len(eligible)!=1:return None
    return {'price_id':price['id'],'eps_id':eligible[0]['id'],'accounting_basis':'GAAP · reported annual diluted EPS'}


def complete(value,bundle):
    """Populate only an empty valuation slot from uniquely qualified inputs."""
    from copy import deepcopy
    from . import earnings_valuation_inventory as inventory
    support=value.get('analysis',{}).get('report_support',{}) if isinstance(value,dict) else {}
    valuation=support.get('valuation') if isinstance(support,dict) else None
    if not isinstance(valuation,dict) or set(valuation)!={'rows','gap','citations'} or valuation['rows']!=[]:return value,[]
    available=inventory.build(bundle);proposal=unique_pair(available)
    if not proposal:return value,[]
    bound=inventory.resolve(proposal,bundle,available)
    result=deepcopy(value)
    result['analysis']['report_support']['valuation']={'rows':[proposal],'gap':'',
        'citations':list(dict.fromkeys([bound['price']['source_id'],bound['eps']['source_id']]))}
    gaps=result.get('financial_selection',{}).get('gaps')
    if isinstance(gaps,list):
        for metric,key in (('price','price'),('annual_eps','eps')):
            matching=[g for g in gaps if g.get('metric')==metric]
            if not matching:
                matching=[{'metric':metric}];gaps.extend(matching)
            for gap in matching:
                gap.update(reason='Available as an original-source supplemental valuation observation; not a normalized core-table fact.',citations=[bound[key]['source_id']])
    return result,[{'path':'/analysis/report_support/valuation','rule':'unique-qualified-pdf-annual-inputs-v1',**proposal}]
