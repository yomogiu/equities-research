"""Annual EPS columns in original mixed quarter/year earnings-release PDFs."""
from datetime import datetime
from decimal import Decimal
import re
from . import earnings_runtime_common as storage


def extract(text,source,prices):
    quotes={(p['symbol'],p['currency']) for p in prices}
    if len(quotes)!=1:return []
    symbol,currency=next(iter(quotes));opening=text[:12000]
    security=re.search(r'\b(?:NYSE|NASDAQ)\s*:\s*'+re.escape(symbol)+r'\b',opening,re.I)
    if not security or currency!='USD':return []
    # Dollar signs alone are ambiguous across markets. This narrow release
    # route requires a matching US listing/quote, GAAP reconciliations and no
    # alternative dollar currency or depositary/share-class ambiguity. Retain
    # this contextual currency binding explicitly for independent review.
    if re.search(r'Canadian dollars|Australian dollars|Hong Kong dollars|NT\$|[€£¥]|\b(?:CAD|AUD|HKD|SGD|NZD|TWD|RMB|CNY|JPY|EUR|GBP|ADRs?|ADSs?)\b|depositary|Class\s+[AB]\b',text,re.I):return []
    if not re.search(r'\bGAAP\b',text) or re.search(r'\bIFRS\b|International Financial Reporting',text,re.I):return []
    pages=list(re.finditer(r'(?m)^\[Page \d+\]\n',text));result=[]
    for i,page in enumerate(pages):
        end=pages[i+1].start() if i+1<len(pages) else len(text);body=text[page.start():end]
        title=re.search(r'(?im)^\s*(?:CONDENSED\s+)?(?:CONSOLIDATED\s+)?STATEMENTS? OF (?:COMPREHENSIVE )?(?:INCOME|OPERATIONS|EARNINGS)\s*$',body)
        if not title:continue
        region=body[title.end():]
        headers=list(re.finditer(r'(?:(Three|Six|Nine|Twelve) Months?|Years?) Ended ([A-Za-z]+) (\d{1,2})',region,re.I))
        headers=[h for h in headers if h.start()<500]
        annual=[(n,h) for n,h in enumerate(headers) if h[1] is None]
        if len(annual)!=1:continue
        years_line=re.search(r'(?m)^[ \t]*(20\d{2})(?:[ \t]+20\d{2}){1,7}[ \t]*$',region[headers[-1].end():headers[-1].end()+300])
        if not years_line:continue
        years=re.findall(r'20\d{2}',years_line[0])
        if len(years)%len(headers):continue
        width=len(years)//len(headers)
        if width not in (2,3) or any(years[n:n+width]!=sorted(set(years[n:n+width]),reverse=True) for n in range(0,len(years),width)):continue
        index,heading=annual[0];column=index*width
        try:end_date=datetime.strptime(heading[2]+' '+heading[3]+', '+years[column],'%B %d, %Y').date().isoformat()
        except ValueError:continue
        row=re.search(r'(?im)^\s*Diluted (?:earnings|net income)(?: \(loss\))? per (?:common )?share\s+([^\n]+)',region)
        if not row or '$' not in row[1]:continue
        tokens=re.findall(r'\(?-?\d[\d,]*\.\d+\)?',row[1])
        if len(tokens)!=len(years):continue
        token=tokens[column];value=Decimal(token.replace(',','').strip('()'))
        if token.startswith('('):value=-abs(value)
        record={'kind':'annual_reported_release','symbol':symbol,'currency':currency,'value':str(value),
            'period_start':None,'period_end':end_date,'fiscal_year':int(years[column]),'basis':'GAAP',
            'share_basis':'reported diluted common share basis','security_binding':'matched-release-listing-and-quote',
            'currency_binding':'original dollar units, matched US listing and USD quote; independent review required',
            'source_id':'document-source-'+source['document_id'][:20],'document_id':source['document_id'],
            'source_sha256':source['sha256'],'start':page.start(),'end':end,'text':body,
            'security_support':{'start':security.start(),'end':security.end(),'text':security[0]},
            'notice':'Reported annual diluted EPS, not quarterly EPS or adjusted guidance. Annual column selected from original ordered duration/year headings. Currency and common-share basis require independent review.'}
        record['id']='E-'+storage.digest(record)[:20];result.append(record)
    return result
