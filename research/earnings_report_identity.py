"""Conservative document identity and calendar-period recognition from PDF text.

Evidence spans refer to the original extracted text. An incidental issuer mention
or comparative period in body prose is not a document identity or reporting title.
"""
import re
from calendar import monthrange
from .financial_evidence import digest


def issuer_pattern(issuer):
    """Match the distinctive name despite punctuation and terminal legal forms.

    Do not infer acronyms, discard distinctive words or match ticker fragments.
    A short name and a wholly different issuer must still fail.
    """
    words=re.findall(r'\w+',issuer.casefold())
    legal={'co','company','corp','corporation','inc','incorporated','ltd','limited','plc'}
    while words and words[-1] in legal:words.pop()
    if not words:raise ValueError('Distinctive issuer name required')
    return r'(?<!\w)'+r'[\W_]+'.join(map(re.escape,words))+r'(?!\w)'


def matches_issuer(text,issuer):
    return bool(re.search(issuer_pattern(issuer),text,re.I))


def span(text, start, end, rule):
    return {'start': start, 'end': end, 'text': text[start:end],
            'sha256': digest(text[start:end].encode()), 'rule': rule}


def front(text):
    pages=list(re.finditer(r'\[Page \d+\]',text))
    # Count extracted pages: an image-only cover may have no text/page marker.
    return text[:pages[3].start() if len(pages)>3 else len(text)]


# Legal forms qualify a bounded issuer name; they never substitute for its name.
LEGAL_FORM = r'(?:AB|ASA|AS|AG|SE|SA|S\.A\.|NV|N\.V\.|BV|B\.V\.|plc|Inc\.?|Ltd\.?|Limited|Corporation|Corp\.?)'
AUDIT_HEADING = r"(?:review report|independent (?:auditor[’']?s? report|review report|auditor[’']?s? review report)|report of (?:the )?independent auditors?)"
IDENTITY_HEADING = r'(?:'+AUDIT_HEADING+r'|corporate information|company information|registered office|contact information)'


def institutional_identity(text, name):
    """Find an issuer bound to an audit subject or labeled registration block.

    Context headings and line anchors distinguish these from mentions of an
    acquired business, competitor or quoted auditor. Offsets stay in original text.
    """
    entity=name+r'(?:[ \t]+Group)?(?:[ \t]+(?:'+LEGAL_FORM+r'))?(?:[ \t]*\(publ\.?\))?'
    def context(start, heading):
        prefix=text[max(0,start-700):start]
        matches=list(re.finditer(r'(?im)^[ \t]*'+heading+r'[ \t]*$',prefix))
        if not matches:return None
        match=matches[-1]
        between=prefix[match.end():]
        # Do not bridge another page or a long discussion into an identity.
        if '[Page ' in between or len(between)>500:return None
        return max(0,start-700)+match.start()
    subject=(r'(?im)^[ \t]*We have (?:audited|reviewed) (?:the )?'
             r'(?:(?:accompanying|condensed|consolidated|interim|annual|financial)\s+){0,5}'
             r'(?:financial statements|statements|report|financial information)\s+(?:of|for)\s+'
             +entity+r'(?=\s+(?:as (?:at|of|per)|at|for the|and (?:its|the))\b|[,.;])')
    for match in re.finditer(subject,text):
        start=context(match.start(),AUDIT_HEADING)
        if start is not None:return span(text,start,match.end(),'auditor_report_subject')
    registration=(r'(?im)^[ \t]*'+entity+r'[ \t]*,?[ \t]*(?:\n[ \t]*)?'
                  r'(?:org\.?[ \t]*(?:no\.?|number)|(?:company|corporate|business)'
                  r'[ \t]+(?:(?:registration|identity|identification)[ \t]+)?(?:no\.?|number)|'
                  r'registration[ \t]+(?:no\.?|number)|business[ \t]+ID)'
                  r'[ \t]*:?[ \t]*(?:\n[ \t]*)?'
                  r'(?=[A-Z0-9 -]{4,30}(?:$|\n))(?=[A-Z0-9 -]*\d)'
                  r'[A-Z0-9][A-Z0-9 -]{3,29}[ \t]*$')
    for match in re.finditer(registration,text):
        start=context(match.start(),IDENTITY_HEADING)
        if start is not None:return span(text,start,match.end(),'registered_issuer_block')
    return None


def issuer_evidence(text, issuer):
    words=re.findall(r'\w+',issuer)
    if not words:raise ValueError('Explicit issuer name required')
    name=r'(?<!\w)'+r'[\W_]+'.join(map(re.escape,words))+r'(?!\w)'
    headline=re.search(r'(?im)^\s*'+name+r'\s+(?:reports|announces|releases)\b[^\n]{0,220}',front(text))
    if headline:return span(text,*headline.span(),'issuer_results_headline')
    # Prefer affirmative legal identities anywhere in the accounting notes.
    legal=[r'This\s+press\s+release\s+is\s+an\s+official\s+information\s+document\s+of\s+(?:the\s+)?'+name+r'(?:\s+Group)?\s*\.',
           r"(?:the\s+)?(?:group[’']s\s+)?parent\s+company\s+is\s+"+name+r'(?:\s+(?:SA|S\.A\.|plc|Inc\.?|Ltd\.?))?\s*[.,]',
           r'(?:consolidated\s+financial\s+statements\s+of)\s+'+name+r'\s*[,\n]',
           name+r"(?:\s+Group)?[’']s\s+LEI\s+is\s+[A-Z0-9]{20}\b",
           name+r'\s+(?:(?:SA|S\.A\.|plc|Inc\.?|Ltd\.?)\s+)?is\s+(?:a\s+)?(?:company\s+)?(?:incorporated|domiciled|registered)\b']
    for pattern in legal:
        match=re.search(pattern,text,re.I)
        if match:return span(text,*match.span(),'explicit_legal_identity')
    # Running headers often combine the report title with a printed page counter.
    # Accept the whole bounded title line, never an arbitrary body-name match.
    entity=name+r'(?:[ \t]+Group)?(?:[ \t]+(?:'+LEGAL_FORM+r'))?(?:[ \t]*\(publ\.?\))?'
    report_title=r'(?:(?:interim|annual|quarterly|financial|half[ -]year|full[ -]year)[ \t]+)*(?:report|results)'
    counter=r'(?:[ \t]+(?:Page[ \t]+)?\d{1,3}[ \t]+(?:of|/)[ \t]+\d{1,3})?'
    heading=(r'(?im)^[ \t]*'+entity+r'[ \t|:—–-]+'+report_title+
             r'[ \t]+(?:Q[1-4][ \t]+20\d{2}|20\d{2}(?:[ \t]+Q[1-4])?)'+counter+r'[ \t]*$')
    match=re.search(heading,front(text))
    if match:return span(text,*match.span(),'issuer_report_running_heading')
    # A named issuer's statutory publication obligation is affirmative identity.
    obligation=(r'(?im)^[ \t]*(?:Note:[ \t]*)?'+entity+
                r'[ \t]+is[ \t]+(?:required|obliged)[ \t]+to[ \t]+(?:publish|make[ \t]+public)[ \t]+(?:the|this)[ \t]+information\b')
    disclosure=(r'(?im)^[ \t]*This[ \t]+(?:is[ \t]+information|information[ \t]+is[ \t]+information)[ \t]+that[ \t]+'+entity+
                r'[ \t]+is[ \t]+(?:required|obliged)[ \t]+to[ \t]+make[ \t]+public[ \t]+pursuant\b')
    match=re.search(obligation,text) or re.search(disclosure,text)
    if match:return span(text,*match.span(),'statutory_publishing_issuer')
    institutional=institutional_identity(text,name)
    if institutional:return institutional
    cover=re.search(r'(?im)^[ \t]*'+entity+r'\.?[ \t]*$',front(text))
    if cover:return span(text,*cover.span(),'opening_legal_name')
    # Short title/identity lines in the opening pages; not narrative mentions.
    title=r'(?:\s|[|,:()—–-]|\b(?:Q[1-4]|20\d{2}|first|second|third|fourth|quarter|quarterly|half|year|yearly|annual|interim|financial|report|results|group|SA|plc|Inc|Ltd|audited|unaudited)\b)*'
    lines=list(re.finditer(r'(?m)^.*$',front(text)))
    for i,line in enumerate(lines):
        for last in lines[i:i+3]:
            if last.end()-line.start()>400:break
            if re.fullmatch(title+name+title,text[line.start():last.end()],re.I):
                return span(text,line.start(),last.end(),'opening_identity_heading')
    raise ValueError('Report issuer lacks an explicit identity heading or legal statement')


def period_evidence(text, expected, issuer='', *, fiscal_calendar='calendar_year'):
    """Read the first dated report heading, never choose a desired body comparison."""
    year,quarter=expected
    opening=front(text)
    # A heading may wrap across a few short lines. Preserve original offsets.
    lines=list(re.finditer(r'(?m)^.*$',opening));candidates=[]
    terms=r'(?:Q[1-4]|(?:first|second|third|fourth)[ -]quarter|(?:first[ -]half|half[ -]year(?:ly)?|H1)|(?:second[ -]half|H2)|(?:(?:first[ -])?nine[ -]months?|9M)|(?:full[ -]year|annual))'
    if issuer:
        name=r'[\W_]+'.join(map(re.escape,re.findall(r'\w+',issuer)))
        headline=re.search(r'(?im)^\s*'+name+r'\s+(?:reports|announces|releases)\b[^\n]{0,220}',opening)
        if headline:
            label=re.search(r'\bQ([1-4])\s+(20\d{2})\b',headline[0],re.I)
            if label:candidates.append((headline.start(),int(label[2]),int(label[1]),'quarter',span(text,*headline.span(),'issuer_results_headline')))
    for i,line in enumerate(lines):
        if re.search(r'\b(?:expects?|expected|guidance|outlook)\b',line.group(),re.I):continue
        if len(re.findall(r'\b(?:Q[1-4]|H[12])\s+20\d{2}\b',line.group(),re.I))>1:continue
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
            heading_words=r'(?:fiscal|\s|[-|,:()/]|financial|activity|interim|consolidated|condensed|report|results|statements|statement|at|as|of|for|the|period|ended|ending|to|june|september|december|march|\d{1,2})*?'
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
    if fiscal_calendar=='document_defined':
        return {'basis':basis,'start':None,'end':document_end(text),
                'event_period':f'FY{year}-Q{quarter}','standalone_quarter':basis=='quarter','evidence':evidence,
                'interpretation':'Fiscal label matched to the event. Dates come from the original report; unestablished boundaries remain unknown. Each table retains its own dates, duration, units and comparisons.'}
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


def document_end(text):
    """An explicit opening reporting endpoint, never a calendar-quarter guess."""
    from .earnings_events import DATE, read_date
    opening=front(text)
    pattern=r'(?:for\s+the\s+)?(?:quarterly\s+period|(?:(?:first|second|third|fourth)\s+)?(?:fiscal\s+)?quarter(?:\s+(?:of\s+)?(?:fiscal\s+)?20\d{2})?|(?:three|six|nine|twelve)\s+months?|(?:fiscal\s+)?year)\s+ended\s+('+DATE+r')'
    match=re.search(pattern,opening,re.I)
    if not match:return None
    return read_date(match[1]).isoformat()
