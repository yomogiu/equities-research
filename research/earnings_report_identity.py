"""Conservative document identity and calendar-period recognition from PDF text.

Evidence spans refer to the original extracted text. An incidental issuer mention
or comparative period in body prose is not a document identity or reporting title.
"""
import re
from calendar import monthrange
from .financial_evidence import digest


def span(text, start, end, rule):
    return {'start': start, 'end': end, 'text': text[start:end],
            'sha256': digest(text[start:end].encode()), 'rule': rule}


def front(text):
    pages=list(re.finditer(r'\[Page \d+\]',text))
    # Count extracted pages: an image-only cover may have no text/page marker.
    return text[:pages[3].start() if len(pages)>3 else len(text)]


def issuer_evidence(text, issuer):
    words=re.findall(r'\w+',issuer)
    if not words:raise ValueError('Explicit issuer name required')
    name=r'(?<!\w)'+r'[\W_]+'.join(map(re.escape,words))+r'(?!\w)'
    # Prefer affirmative legal identities anywhere in the accounting notes.
    legal=[r'This\s+press\s+release\s+is\s+an\s+official\s+information\s+document\s+of\s+(?:the\s+)?'+name+r'(?:\s+Group)?\s*\.',
           r"(?:the\s+)?(?:group[’']s\s+)?parent\s+company\s+is\s+"+name+r'(?:\s+(?:SA|S\.A\.|plc|Inc\.?|Ltd\.?))?\s*[.,]',
           r'(?:consolidated\s+financial\s+statements\s+of)\s+'+name+r'\s*[,\n]',
           name+r"(?:\s+Group)?[’']s\s+LEI\s+is\s+[A-Z0-9]{20}\b",
           name+r'\s+(?:(?:SA|S\.A\.|plc|Inc\.?|Ltd\.?)\s+)?is\s+(?:a\s+)?(?:company\s+)?(?:incorporated|domiciled|registered)\b']
    for pattern in legal:
        match=re.search(pattern,text,re.I)
        if match:return span(text,*match.span(),'explicit_legal_identity')
    # Short title/identity lines in the opening pages; not narrative mentions.
    title=r'(?:\s|[|,:()—–-]|\b(?:Q[1-4]|20\d{2}|first|second|third|fourth|quarter|quarterly|half|year|yearly|annual|interim|financial|report|results|group|SA|plc|Inc|Ltd|audited|unaudited)\b)*'
    lines=list(re.finditer(r'(?m)^.*$',front(text)))
    for i,line in enumerate(lines):
        for last in lines[i:i+3]:
            if last.end()-line.start()>400:break
            if re.fullmatch(title+name+title,text[line.start():last.end()],re.I):
                return span(text,line.start(),last.end(),'opening_identity_heading')
    raise ValueError('Report issuer lacks an explicit identity heading or legal statement')


def period_evidence(text, expected, issuer=''):
    """Read the first dated report heading, never choose a desired body comparison."""
    year,quarter=expected
    opening=front(text)
    # A heading may wrap across a few short lines. Preserve original offsets.
    lines=list(re.finditer(r'(?m)^.*$',opening));candidates=[]
    terms=r'(?:Q[1-4]|(?:first|second|third|fourth)[ -]quarter|(?:first[ -]half|half[ -]year(?:ly)?|H1)|(?:second[ -]half|H2)|(?:(?:first[ -])?nine[ -]months?|9M)|(?:full[ -]year|annual))'
    for i,line in enumerate(lines):
        if not line.group().strip() or len(line.group().strip())>160:continue
        end=line.end()
        for following in lines[i+1:i+5]:
            if following.group().strip() and len(following.group().strip())>160:break
            if following.end()-line.start()>300:break
            end=following.end()
        chunk=text[line.start():end]
        # Require a heading beginning (optional section number), avoiding body
        # prose such as "Compared with Q2 ..." and table comparative columns.
        prefix=r'(?:'+r'[\W_]+'.join(map(re.escape,re.findall(r'\w+',issuer)))+r'\s*[|,:—–-]?\s*)?' if issuer else ''
        lead=r'^\s*(?:\d+(?:\.\d+)*\s+)?'+prefix+r'(?:the\s+)?(?:20\d{2}\s+)?'
        for match in re.finditer(lead+r'(?P<label>'+terms+r')\b',chunk,re.I):
            tail=chunk[match.end():]
            # Date/year must belong to this short heading, with only heading
            # vocabulary between the label and year/date. No narrative bridging.
            heading_words=r'(?:\s|[-|,:()/]|financial|activity|interim|consolidated|condensed|report|results|statements|statement|at|as|of|for|the|period|ended|ending|to|june|september|december|march|\d{1,2})*?'
            after=re.match(heading_words+r'(?P<year>20\d{2})\b',tail,re.I)
            before=re.search(r'\b(20\d{2})\s*$',chunk[:match.start('label')])
            if not after and not before:continue
            found_year=int(after['year'] if after else before[1]);label=match['label'].lower()
            q=re.fullmatch(r'q([1-4])',label)
            ordinal=next((n for n,w in enumerate(('first','second','third','fourth'),1) if label.startswith(w) and 'quarter' in label),None)
            if q or ordinal:found_quarter=int(q[1]) if q else ordinal;basis='quarter'
            elif label.startswith(('nine','first nine','first-nine','9m')):found_quarter=3;basis='nine_months'
            elif label.startswith(('half','first','h1')):found_quarter=2;basis='half_year'
            elif label.startswith(('second','h2')):found_quarter=4;basis='second_half'
            else:found_quarter=4;basis='full_year'
            stop=line.start()+match.end()+(after.end() if after else 0)
            candidates.append((line.start(),found_year,found_quarter,basis,span(text,line.start(),stop,'dated_report_heading')))
    if not candidates:raise ValueError('Explicit dated reporting-period heading unavailable')
    _,found_year,found_quarter,basis,evidence=min(candidates,key=lambda item:item[0])
    if (found_year,found_quarter)!=(year,quarter):
        raise ValueError('Report heading period differs from discovered event; comparative periods cannot qualify it')
    start=f'{year}-{((quarter-1)*3+1 if basis=="quarter" else 7 if basis=="second_half" else 1):02d}-01'
    end=f'{year}-{quarter*3:02d}-{monthrange(year,quarter*3)[1]}'
    explicit=re.search(r'\b(?:at|ended|ending|to)\s+(\d{1,2})\s+(March|June|September|December)\s+(20\d{2})\b',evidence['text'],re.I)
    if explicit:
        month={'march':3,'june':6,'september':9,'december':12}[explicit[2].lower()]
        if f'{int(explicit[3])}-{month:02d}-{int(explicit[1]):02d}'!=end:
            raise ValueError('Report heading date conflicts with reporting-period label')
    return {'basis':basis,'start':start,'end':end,'event_period':f'FY{year}-Q{quarter}',
            'standalone_quarter':basis=='quarter','evidence':evidence,
            'interpretation':'Document reporting period only; each selected table retains its own units, duration and comparative headers. Cumulative flows must not be relabeled as standalone quarterly flows.'}


def recognize(text,issuer,period):
    return {'issuer_evidence':issuer_evidence(text,issuer),'report_period':period_evidence(text,period,issuer)}
