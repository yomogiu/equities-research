"""Issuer-bound reporting events, including semiannual calls and trading updates."""
from calendar import monthrange
from datetime import date
import re
from .source_parse import page


def select(body,index_url,as_of):
    found={}
    for link in page(body,index_url).links:
        match=re.fullmatch(re.escape(index_url)+r'\d+-(q[1-4]|h[12])-(20\d{2})(-tu)?/',link['url'])
        if not match:continue  # AGM, media and post-call variants are not earnings events.
        label,year,suffix=match.groups();label=label.upper();year=int(year)
        title=re.fullmatch(r'Earnings Call:\s*(Q[1-4]|H[12])\s+(20\d{2})(?:\s+(?:TU|Trading Update))?',link['title'],re.I)
        if not title:continue  # Duplicate "Read transcript" links carry no period metadata.
        if (title[1].upper(),int(title[2]))!=(label,year):
            raise ValueError('Event index label conflicts with event URL period')
        quarter=int(label[1])*(2 if label.startswith('H') else 1)
        end=date(year,quarter*3,monthrange(year,quarter*3)[1])
        if end>as_of:continue
        start=date(year,((int(label[1])-1)*6+1) if label.startswith('H') else (quarter-1)*3+1,1)
        event={'url':link['url'],'label':label,'year':year,'quarter':quarter,
               'period':f'FY{year}-{label}','start':start.isoformat(),'end':end.isoformat(),
               'kind':'trading_update' if suffix else 'earnings_call','index_label':link['title']}
        found.setdefault((year,quarter),{})[link['url']]=event
    if not found:raise ValueError('No completed reporting event discovered from issuer transcript index')
    choices=found[max(found)]
    if len(choices)!=1:raise ValueError('Ambiguous latest earnings event')
    return next(iter(choices.values()))


def qualify_call(text,issuer,event):
    name=r'(?<!\w)'+r'\s+'.join(map(re.escape,issuer.split()))+r'(?!\w)'
    if not re.search(name,text[:1600],re.I):raise ValueError('Transcript issuer mismatch')
    headings=re.findall(r'(?m)^Earnings Call:\s*(Q[1-4]|H[12])\s+(20\d{2})(?:\s+(?:TU|Trading Update))?\s*$',text[:2500],re.I)
    if [(label.upper(),year) for label,year in headings]!=[(event['label'],str(event['year']))]:raise ValueError('Transcript heading differs from selected event')


def excluded(event,periods):
    # Preserve exclusions under either the native H label or equivalent quarter end.
    aliases={event['period'],f"FY{event['year']}-Q{event['quarter']}"}
    if event['quarter'] in (2,4):aliases.add(f"FY{event['year']}-H{event['quarter']//2}")
    return bool(aliases&set(periods))
