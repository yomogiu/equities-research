"""Issuer-bound reporting events, including semiannual calls and trading updates."""
from calendar import monthrange
from datetime import date
import re
from .source_parse import page, Page


MONTHS = {name.lower(): i for i, name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'), 1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})
DATE = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+20\d{2}'


def read_date(text):
    match=re.fullmatch(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(20\d{2})',text.strip())
    if not match:raise ValueError('Explicit publication date required')
    return date(int(match[3]),MONTHS[match[1].lower()],int(match[2]))


class EventIndex(Page):
    def handle_endtag(self,tag):
        anchor=tag=='a' and self.anchor is not None
        super().handle_endtag(tag)
        if anchor:self.links[-1]['following']=len(self.text_parts)


def select(body,index_url,as_of,*,fiscal_calendar='calendar_year'):
    parsed=EventIndex(index_url);parsed.feed(body.decode('utf-8',errors='replace'))
    found={}
    for link in parsed.links:
        if not link['url'].startswith(index_url):continue
        slug=link['url'][len(index_url):].strip('/')
        if not slug or '/' in slug:continue
        # Investor calls and arbitrary descriptive suffixes are eligible. Separate
        # media events and prerecorded interviews cannot replace the full call.
        if re.search(r'(?:^|-)(?:media|post-call|pre-recorded|prerecorded|agm)(?:-|$)',slug,re.I):continue
        title=re.fullmatch(r'(?:Earnings|Results|Investor) Call:\s*(Q[1-4]|H[12])\s+(20\d{2})(?:\s+.*)?',link['title'],re.I)
        if not title:continue
        label,year=title[1].upper(),int(title[2])
        url_period=re.search(r'(?:^|-)(q[1-4]|h[12])-(20\d{2})(?:-|$)',slug,re.I)
        if url_period and (url_period[1].upper(),int(url_period[2]))!=(label,year):
            raise ValueError('Event index label conflicts with event URL period')
        following=''.join(parsed.text_parts[link['following']:])[:160].strip()
        published=re.match(DATE,following,re.I)
        published=read_date(published[0]) if published else None
        quarter=int(label[1])*(2 if label.startswith('H') else 1)
        end=date(year,quarter*3,monthrange(year,quarter*3)[1])
        if published:
            if published>as_of:continue
        elif fiscal_calendar=='calendar_year':
            if end>as_of:continue
        else:raise ValueError('Fiscal event requires a published call date')
        start=date(year,((int(label[1])-1)*6+1) if label.startswith('H') else (quarter-1)*3+1,1)
        event={'url':link['url'],'label':label,'year':year,'quarter':quarter,
               'period':f'FY{year}-{label}','start':start.isoformat() if fiscal_calendar=='calendar_year' else None,
               'end':end.isoformat() if fiscal_calendar=='calendar_year' else None,
               'published_on':published.isoformat() if published else None,'fiscal_calendar':fiscal_calendar,
               'kind':'trading_update' if re.search(r'(?:-tu|-trading-update)$',slug,re.I) else 'earnings_call','index_label':link['title']}
        found.setdefault((year,quarter),{})[link['url']]=event
    if not found:raise ValueError('No completed reporting event discovered from issuer transcript index')
    choices=found[max(found)]
    if len(choices)!=1:raise ValueError('Ambiguous latest earnings event')
    return next(iter(choices.values()))


def qualify_call(text,issuer,event):
    from .earnings_report_identity import matches_issuer
    if not matches_issuer(text[:1600],issuer):raise ValueError('Transcript issuer mismatch')
    headings=re.findall(r'(?m)^(?:Earnings|Results|Investor) Call:\s*(Q[1-4]|H[12])\s+(20\d{2})(?:\s+(?:TU|Trading Update))?\s*$',text[:2500],re.I)
    if [(label.upper(),year) for label,year in headings]!=[(event['label'],str(event['year']))]:raise ValueError('Transcript heading differs from selected event')


def excluded(event,periods):
    # Preserve exclusions under either the native H label or equivalent quarter end.
    aliases={event['period'],f"FY{event['year']}-Q{event['quarter']}"}
    if event['quarter'] in (2,4):aliases.add(f"FY{event['year']}-H{event['quarter']//2}")
    return bool(aliases&set(periods))
