"""Replay scoped call currentness without claiming unchanged full-page bytes.

Only the recognized publisher's market widget may differ. Archived evidence,
qualifications and their original offsets stay authoritative.
"""
import copy
import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .contracts import digest, require
from .freshness import timestamp
from . import source_parse, transcript_evidence, financial_evidence

LEGACY_VERSION = 'stockanalysis-market-widget-currentness-v1'
APP_COUNTER_VERSION = 'stockanalysis-market-and-app-counter-currentness-v2'
COUNTRY_VERSION = 'stockanalysis-market-app-counter-and-country-navigation-currentness-v3'
MOBILE_VERSION = 'stockanalysis-market-app-counter-country-and-mobile-controls-currentness-v4'
PUBLISHER_LINK_VERSION = 'stockanalysis-exact-publisher-link-currentness-v5'
VERSION = 'stockanalysis-exact-tsx-publisher-currentness-v6'
LISTING_VERSION = 'stockanalysis-authenticated-listing-header-currentness-v7'
APP_RATING_VERSION = 'stockanalysis-explicit-footer-app-rating-currentness-v11'
MARKET_OPEN_VERSION = 'stockanalysis-exact-market-open-widget-currentness-v8'
KASE_VERSION = 'stockanalysis-exact-kase-publisher-currentness-v9'
NASDAQ_VERSION = 'stockanalysis-authenticated-nasdaq-market-open-currentness-v10'
STATUS = 'scoped_transcript_verified'


def sha(body):
    return hashlib.sha256(body).hexdigest()


class Widget(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw, self.depth, self.active, self.spans = raw, 0, None, []
        self.lines = [0] + [m.end() for m in re.finditer('\n', raw)]

    def absolute_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag != 'div': return
        self.depth += 1
        classes = set(dict(attrs).get('class', '').split())
        if {'mb-5', 'flex', 'flex-row', 'items-end'} <= classes:
            require(self.active is None, 'Nested quote widgets are ambiguous')
            self.active = (self.depth, self.absolute_offset())

    def handle_endtag(self, tag):
        if tag != 'div': return
        if self.active and self.active[0] == self.depth:
            self.spans.append((self.active[1], self.absolute_offset() + len('</div>')))
            self.active = None
        self.depth -= 1


def app_counters(html):
    """Mask only numeric download-review counts inside known footer app links."""
    footers = list(re.finditer(r'<footer\b[^>]*>.*?</footer>', html, re.S))
    if not footers:
        return html
    require(len(footers) == 1, 'Ambiguous publisher footer')
    footer = footers[0]
    require('transcript-sentence' not in footer.group(), 'Footer overlaps call evidence')
    links = (
        'https://apps.apple.com/us/app/stock-analysis-app/id6751272467',
        'https://play.google.com/store/apps/details?id=com.stockanalysis.app',
    )
    changes = []
    for url in links:
        matches = list(re.finditer(r'<a\b[^>]*href="' + re.escape(url) + r'"[^>]*>.*?</a>', footer.group(), re.S))
        require(len(matches) <= 2, 'Ambiguous app promotion')
        counted = 0
        for match in matches:
            counts = list(re.finditer(r'(<span class="text-gray-400">)([0-9]+(?:\.[0-9]+)?[KM]?)(</span>)', match.group()))
            if not counts and 'text-gray-400' not in match.group():
                continue
            counted += 1
            require(len(counts) == 1 and counted == 1, 'Unrecognized app counter')
            count = counts[0]
            start = footer.start() + match.start() + count.start(2)
            changes.append((start, start + len(count.group(2))))
    for start, end in reversed(sorted(changes)):
        html = html[:start] + 'APP_REVIEW_COUNT' + html[end:]
    return html



def app_ratings(html):
    """Explicit opt-in: numeric ratings in exact publisher app footer links only."""
    footers=list(re.finditer(r'<footer\b[^>]*>.*?</footer>',html,re.S))
    require(len(footers)==1,'Exactly one app footer required')
    footer=footers[0];require('transcript-sentence' not in footer.group(),'Footer overlaps evidence')
    changes=[]
    for url in ('https://apps.apple.com/us/app/stock-analysis-app/id6751272467','https://play.google.com/store/apps/details?id=com.stockanalysis.app'):
        links=list(re.finditer(r'<a\b[^>]*href="'+re.escape(url)+r'"[^>]*>.*?</a>',footer.group(),re.S))
        rated=0
        for link in links:
            ratings=list(re.finditer(r'(<span class="font-semibold text-(?:green|amber)-500">)([0-4]\.[0-9]|5\.0)(</span>)',link.group()))
            if not ratings:continue
            rated+=1;require(len(ratings)==1 and rated==1,'Ambiguous app rating')
            require(len(re.findall(r'<span class="text-gray-400">[0-9]+(?:\.[0-9]+)?[KM]?</span>',link.group()))==1,'Rating requires same app review count')
            match=ratings[0];start=footer.start()+link.start()+match.start(2);changes.append((start,start+len(match.group(2))))
        require(rated==1,'Exact rated publisher app link required')
    for start,end in reversed(sorted(changes)):html=html[:start]+'APP_RATING'+html[end:]
    return html


def country_navigation(html):
    """Ignore one exact publisher directory link inside its main Stocks menu.

    The complete call, metadata and every other navigation word remain compared.
    Old receipts never use this rule.
    """
    navs = list(re.finditer(r'<nav\b(?=[^>]*\baria-label="Main navigation")[^>]*>.*?</nav>', html, re.S))
    if not navs:
        return html
    require(len(navs) == 1, 'Ambiguous main navigation')
    nav = navs[0]
    require('transcript-sentence' not in nav.group(), 'Navigation overlaps call evidence')
    menus = list(re.finditer(r'<ul\b(?=[^>]*\bid="Stocks-menu")[^>]*>.*?</ul>', nav.group(), re.S))
    if not menus:
        return html
    require(len(menus) == 1, 'Ambiguous Stocks navigation menu')
    menu = menus[0]
    links = list(re.finditer(r'<li>\s*<a\b(?=[^>]*\bhref="/list/countries/")(?=[^>]*\btitle="By Country")[^>]*>By Country</a>\s*</li>', menu.group()))
    require(len(links) <= 1, 'Ambiguous country navigation link')
    if not links:
        return html
    link = links[0]
    start = nav.start() + menu.start() + link.start()
    end = nav.start() + menu.start() + link.end()
    return html[:start] + html[end:]



def mobile_controls(html):
    """Mask only the exact redundant mobile signup/login/help controls."""
    matches = []
    for match in re.finditer(r'<div\b(?=[^>]*class="[^"]*\bmt-auto\b)[^>]*class="([^"]*)"[^>]*>.*?</div>', html, re.S):
        classes = set(match.group(1).split())
        if {'mb-6', 'mt-auto', 'xxl:hidden', 'border-t', 'bg-default'} <= classes:
            matches.append(match)
    require(len(matches) <= 1, 'Ambiguous mobile controls')
    if not matches: return html
    match = matches[0]; block = match.group()
    require('transcript-sentence' not in block, 'Mobile controls overlap call evidence')
    links = re.findall(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.S)
    require([url for url, _ in links] == ['/pro/', '/login/', '/help/'], 'Unrecognized mobile control links')
    labels = [' '.join(source_parse.page(body.encode(), 'https://stockanalysis.com/').text.split()) for _, body in links]
    require(labels == ['Sign Up', 'Log In', 'Help'], 'Unrecognized mobile control labels')
    require(''.join(source_parse.page(block.encode(), 'https://stockanalysis.com/').text.split()) == 'SignUpLogInHelp', 'Unexpected mobile control content')
    return html[:match.start()] + html[match.end():]

def publisher_links(html, url):
    """Normalize exact non-call directory controls; keep filing destinations bound."""
    path = urlsplit(url).path
    parts = path.split('/')
    symbol = parts[3].lower() if path.startswith('/quote/tsx/') else parts[2]
    prefix = '/quote/tsx/'+parts[3] if path.startswith('/quote/tsx/') else '/stocks/'+symbol
    menus = list(re.finditer(r'<ul\b(?=[^>]*\bclass="navmenu")[^>]*>.*?</ul>', html, re.S))
    require(len(menus) <= 1, 'Ambiguous stock navigation')
    if menus:
        menu = menus[0]
        require('transcript-sentence' not in menu.group(), 'Navigation overlaps call')
        pattern = (r'<li><a href="' + re.escape(prefix) +
                   r'/forecast/" data-title="Forecast">Forecast(?:<!--.*?-->)*</a></li>')
        matches = list(re.finditer(pattern, menu.group(), re.S))
        require(len(matches) <= 1, 'Ambiguous Forecast control')
        if matches:
            m = matches[0]; start = menu.start() + m.start(); end = menu.start() + m.end()
            html = html[:start] + html[end:]
    filing_id = r'TSX:[A-Z0-9.-]+' if path.startswith('/quote/tsx/') else r'[A-Z0-9.-]+'
    expected_issuer = 'tsx:'+symbol if path.startswith('/quote/tsx/') else symbol
    pattern = r'<a\b[^>]*href="(/filings/'+filing_id+r'/[0-9]+/)"[^>]*><span>(Registration statement|Report|MD&amp;A)</span></a>'
    seen = {}
    def filing(match):
        href, label = match.groups()
        require(href.split('/')[2].lower() == expected_issuer, 'Other issuer filing control')
        count, previous = seen.get(href, (0, label))
        require(count < 2 and previous == label, 'Ambiguous filing controls')
        seen[href] = (count + 1, label)
        # Destination survives extraction/comparison, including duplicate order.
        return '<span>FILING_LINK:' + href + '</span>'
    # Never mask anchors inside the exact original speaker blocks.
    blocks = transcript_evidence._TranscriptBlocks(html); blocks.feed(html); blocks.close()
    require(not any(re.search(pattern, block) for block in blocks.blocks), 'Filing link overlaps call')
    return re.sub(pattern, filing, html)


def prepared_downloads(html, url):
    """Exact same-event added Prepared remarks controls, never call evidence."""
    require(urlsplit(url).path.startswith('/stocks/'),'Exact stock publisher download scope required')
    symbol=urlsplit(url).path.split('/')[2].upper()
    event=re.findall(r'quartrEventId:([0-9]+),fiscalYear:([0-9]{4}),quarterLabel:"(Q[1-4] [0-9]{4})"',html)
    require(len(event)==1 and event[0][2].endswith(event[0][1]) and urlsplit(url).path.split('/')[4].startswith(event[0][0]+'-'),'Exact publisher earnings event required')
    groups=list(re.finditer(r'<ul[^>]*aria-label="Downloads"[^>]*>.*?</ul>',html,re.S))
    require(len(groups)==2,'Two complete publisher download groups required')
    links=[];prepared=[];spans=[]
    for group in groups:
        require('transcript-sentence' not in group.group(),'Download group overlaps call')
        anchors=list(re.finditer(r'<a href="(/filings/([A-Z0-9.-]+)/([0-9]+)/)" class="[^"]+"><span>([^<>]+)</span></a>',group.group()))
        require(anchors and len(anchors)==len(re.findall(r'<a\b',group.group())),'Exact publisher filing controls required')
        rows=[];seen=0
        for anchor in anchors:
            href,issuer,identifier,label=anchor.groups();require(issuer==symbol,'Other issuer download control')
            if label=='Prepared remarks':
                seen+=1;require(seen==1 and anchors[0]==anchor,'Unique first prepared control required')
                literal='<li class="mb-0">'+anchor.group()+'</li>';relative=group.group().find(literal);require(relative>=0,'Exact prepared control structure required')
                spans.append((group.start()+relative,group.start()+relative+len(literal)));prepared.append(href)
                require(len(re.findall(r'\{id:'+identifier+r',label:"Prepared remarks"\}',html))==1,'Prepared control must bind one event file')
            else:rows.append([href,label])
        links.append(rows)
    require(links[0]==links[1] and (not prepared or len(prepared)==2 and prepared[0]==prepared[1]),'Repeated download identity/order differs')
    require(len(re.findall('label:"Prepared remarks"',html))==(1 if prepared else 0),'Unbound prepared event file')
    for a,b in reversed(spans):html=html[:a]+html[b:]
    return html,{'event':list(event[0]),'existing_downloads':links,'prepared':prepared}


def signature(raw, url, *, allow_app_counters=False, allow_country_navigation=False, allow_mobile_controls=False, allow_publisher_links=False, allow_tsx=False, allow_market_open=False, allow_kase=False, allow_app_ratings=False):
    require(urlsplit(url).hostname == 'stockanalysis.com' and
            (re.fullmatch(r'/stocks/[a-z0-9.-]+/transcripts/[a-z0-9-]+/', urlsplit(url).path) or
             allow_kase and re.fullmatch(r'/quote/kase/[A-Za-z0-9.-]+/transcripts/[a-z0-9-]+/', urlsplit(url).path) or
             allow_tsx and re.fullmatch(r'/quote/tsx/[A-Za-z0-9.-]+/transcripts/[a-z0-9-]+/', urlsplit(url).path)),
            'Unsupported transcript publisher URL')
    html = raw.decode('utf-8')
    page = source_parse.page(raw, url)
    blocks = transcript_evidence._TranscriptBlocks(html)
    blocks.feed(html); blocks.close()
    require(blocks.blocks and not blocks.unbound_sentences and blocks.active is None and blocks.depth == 0,
            'Missing, incomplete or unbound transcript blocks')
    bodies = [source_parse.page(b.encode(), url).text for b in blocks.blocks]
    require(all(len(b.splitlines()) >= 2 for b in bodies), 'Incomplete speaker block')
    cursor, spans = 0, []
    for body in bodies:
        start = page.text.find(body, cursor)
        require(start >= 0 and (not spans or not page.text[cursor:start].strip()), 'Incomplete call coverage')
        spans.append([start, start + len(body)]); cursor = start + len(body)
    widget = Widget(html); widget.feed(html); widget.close()
    require(len(widget.spans) == 1 and widget.active is None and widget.depth == 0, 'Ambiguous quote widget')
    a, b = widget.spans[0]
    widget_text = source_parse.page(html[a:b].encode(), url).text
    tsx_widget = (allow_tsx and urlsplit(url).path.startswith('/quote/tsx/') and
                  re.fullmatch(r'[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\n[+-][0-9]+(?:\.[0-9]+)? \([+-]?[0-9]+(?:\.[0-9]+)?%\)\n(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{1,2}, [0-9]{4}, [0-9]{1,2}:[0-9]{2} [AP]M (?:EST|EDT)', widget_text))
    market_open = allow_market_open and re.fullmatch(r'[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\n[+-][0-9]+(?:\.[0-9]+)? \([+-]?[0-9]+(?:\.[0-9]+)?%\)\n(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{1,2}, [0-9]{4}, (?:[1-9]|1[0-2]):[0-5][0-9] [AP]M (?:EST|EDT) - Market open', widget_text)
    if allow_kase:
        require(urlsplit(url).path.startswith('/quote/kase/'), 'Exact KASE URL required')
        require(re.fullmatch(r'[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\n[+-][0-9]+(?:\.[0-9]+)? \([+-]?[0-9]+(?:\.[0-9]+)?%\)\nAt close: (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{1,2}, [0-9]{4}', widget_text), 'Unrecognized KASE quote widget')
    require(re.search(r'(?:Market closed|At close:|Pre-market:|After-hours:)', widget_text) or tsx_widget or market_open, 'Unrecognized quote widget')
    require('transcript-sentence' not in html[a:b], 'Widget overlaps call evidence')
    outside_html = html[:a] + '<div>QUOTE_WIDGET</div>' + html[b:]
    if allow_app_ratings:outside_html=app_ratings(outside_html)
    if allow_app_counters:
        outside_html = app_counters(outside_html)
    if allow_country_navigation:
        outside_html = country_navigation(outside_html)
    if allow_mobile_controls:
        outside_html = mobile_controls(outside_html)
    if allow_publisher_links:
        outside_html = publisher_links(outside_html, url) if not allow_kase else outside_html
    downloads=None
    if allow_market_open:outside_html,downloads=prepared_downloads(outside_html,url)
    outside = source_parse.page(outside_html.encode(), url).text
    facts = financial_evidence.extract_inline_xbrl(html, {'document_id': 'scope', 'raw_sha256': sha(raw), 'text_sha256': sha(page.text.encode())})
    facts = {'observations': [{k:v for k,v in o.items() if k not in ('observation_id','source_raw_sha256','support')} for o in facts['observations']],
             'gaps': [{k:v for k,v in g.items() if k != 'start'} for g in facts['gaps']]}
    kase_identity = {}
    if allow_kase:
        symbol=urlsplit(url).path.split('/')[3].upper()
        filings=re.findall(r'href="(/filings/[^"]+)"', html)
        require(filings and all(re.fullmatch(r'/filings/KASE:'+re.escape(symbol)+r'/(?:[0-9]+/)?', x) for x in filings), 'Exact same KASE filing issuer required')
        event=re.findall(r'quartrEventId:([0-9]+),fiscalYear:([0-9]{4}),quarterLabel:"(Q[1-4] [0-9]{4})",detailSlug:"([^"]+)",eventDate:"([0-9-]+)"', html)
        require(len(event)==1 and event[0][3]==urlsplit(url).path.split('/')[5] and event[0][3].startswith(event[0][0]+'-') and event[0][2].endswith(event[0][1]), 'Exact KASE earnings event required')
        headers=re.findall(r'<div class="mt-px text-tiny text-faded">(.*?)</div>',html,re.S)
        require(len(headers)==1 and source_parse.page(headers[0].encode(),url).text=='Kazakhstan · Delayed Price · Currency is KZT', 'Exact KASE listing metadata required')
        kase_identity={'kase_identity': {'filing_destinations':filings, 'event':list(event[0]), 'listing':'Kazakhstan · Delayed Price · Currency is KZT'}}
    return {**kase_identity, 'title': page.title, 'fiscal': page.fiscal, 'outside_widget_sha256': sha(outside.encode()),
            'block_sha256': [sha(b.encode()) for b in blocks.blocks],
            'block_text_sha256': [sha(b.encode()) for b in bodies], 'facts': facts}, {
            'fulltext_sha256': sha(page.text.encode()), 'call_span': [spans[0][0],spans[-1][1]],
            'widget_html_span': [a,b], 'widget_sha256': sha(html[a:b].encode()), **({'downloads':downloads} if allow_market_open else {})}


def compare(before, after, url, *, allow_app_counters=True, allow_country_navigation=True, allow_mobile_controls=True, allow_publisher_links=True, allow_tsx=True, allow_market_open=False, allow_kase=False, allow_app_ratings=False):
    old, old_spans = signature(before, url, allow_app_counters=allow_app_counters, allow_country_navigation=allow_country_navigation, allow_mobile_controls=allow_mobile_controls, allow_publisher_links=allow_publisher_links, allow_tsx=allow_tsx, allow_market_open=allow_market_open, allow_kase=allow_kase, allow_app_ratings=allow_app_ratings)
    new, new_spans = signature(after, url, allow_app_counters=allow_app_counters, allow_country_navigation=allow_country_navigation, allow_mobile_controls=allow_mobile_controls, allow_publisher_links=allow_publisher_links, allow_tsx=allow_tsx, allow_market_open=allow_market_open, allow_kase=allow_kase, allow_app_ratings=allow_app_ratings)
    if allow_market_open:
        a,b=old_spans['downloads'],new_spans['downloads']
        require(a['event']==b['event'] and a['existing_downloads']==b['existing_downloads'] and (a['prepared']==b['prepared'] or not a['prepared'] and len(b['prepared'])==2),'Only same-event prepared control addition permitted')
    require(old == new, 'Complete transcript, metadata or non-widget content changed')
    require(old['title'] and old['block_sha256'], 'Transcript metadata missing')
    return {'signature': old, 'archived': old_spans, 'observed': new_spans,
            'whole_page_bytes_equal': before == after,
            'whole_page_text_equal': old_spans['fulltext_sha256'] == new_spans['fulltext_sha256']}


def replay(root, reference, document=None, *, issuer_id=None, historical=False):
    from . import library
    path = library.resolve(root, reference['path'])
    require(sha(path.read_bytes()) == reference['sha256'], 'Currentness receipt hash changed')
    value = library.read_json(path)
    require(value['version'] in (APP_RATING_VERSION, NASDAQ_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, LISTING_VERSION, VERSION, PUBLISHER_LINK_VERSION, MOBILE_VERSION, COUNTRY_VERSION, APP_COUNTER_VERSION, LEGACY_VERSION), 'Unsupported currentness proof')
    old, new = value['archived'], value['observed']
    before = library.load_bytes(root, old['raw_path'], old['raw_sha256'])
    text = library.load_bytes(root, old['text_path'], old['text_sha256'])
    after = library.load_bytes(root, new['raw_path'], new['raw_sha256'])
    observed_text = library.load_bytes(root, new['text_path'], new['text_sha256'])
    require(source_parse.page(after,value['source_url']).text.encode() == observed_text, 'Observed extraction mismatch')
    require(source_parse.page(before,value['source_url']).text.encode() == text, 'Archived extraction mismatch')
    if value['version'] in (LISTING_VERSION,NASDAQ_VERSION):
        if value['version']==NASDAQ_VERSION:
            from . import transcript_nasdaq_transition as listing
        else:
            from . import transcript_listing_transition as listing
        auth,_=listing.authority(root,value['listing_authority'],value['issuer_id'],value['source_url'],value['checked_at'])
        require(listing.compare(before,after,value['source_url'],auth)==value['comparison'],'Listing comparison changed')
    else:
        require(compare(before,after,value['source_url'], allow_app_counters=value['version'] in (APP_RATING_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, VERSION, PUBLISHER_LINK_VERSION, MOBILE_VERSION, COUNTRY_VERSION, APP_COUNTER_VERSION), allow_country_navigation=value['version'] in (APP_RATING_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, VERSION, PUBLISHER_LINK_VERSION, MOBILE_VERSION, COUNTRY_VERSION), allow_mobile_controls=value['version'] in (APP_RATING_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, VERSION, PUBLISHER_LINK_VERSION, MOBILE_VERSION), allow_publisher_links=value['version'] in (APP_RATING_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, VERSION, PUBLISHER_LINK_VERSION), allow_tsx=value['version'] in (APP_RATING_VERSION, KASE_VERSION, MARKET_OPEN_VERSION, VERSION), allow_market_open=value['version'] in (APP_RATING_VERSION,MARKET_OPEN_VERSION), allow_kase=value['version']==KASE_VERSION, allow_app_ratings=value['version']==APP_RATING_VERSION) == value['comparison'], 'Scoped comparison changed')
    cache = library.resolve(root,value['http_cache_path'])
    require(sha(cache.read_bytes()) == value['http_cache_sha256'], 'HTTP observation changed')
    observation = library.read_json(cache)[value['source_url']]
    require(observation['sha256'] == new['raw_sha256'] and timestamp(observation['checked_at']) == value['checked_at'], 'Fetch proof mismatch')
    # Historical adoption replays the immutable observation below, not present
    # currentness. Its successor must independently pass the ordinary replay.
    if not historical:
        latest = latest_observation(root,value['source_url'])
        require(latest is not None and latest[0] >= value['checked_at'] and latest[1] == new['raw_sha256'], 'Latest source observation conflicts with scoped proof')
    require(value['checked_at'] is not None and observation.get('final_url') == value['source_url'] and 'html' in observation.get('content_type',''), 'Actual same-URL HTML fetch required')
    require((cache.parent / observation['body_path']).resolve() == library.resolve(root,new['raw_path']).resolve(), 'Fetch body path mismatch')
    q = library.read_json(library.resolve(root, 'library/qualifications/'+value['qualification_id']+'.json'))
    require(digest(q) == value['qualification_id'] and q['document_id'] == digest([value['issuer_id'],old['text_sha256']]) and
            q['text_sha256'] == old['text_sha256'] and q['period'] == value['period'] and q['kind'] == 'transcript' and
            q['completeness'] == 'full' and q.get('source_accepted') is True, 'Qualified complete call required')
    for span in q['source_spans']:
        require(text.decode()[span['start']:span['end']] == span['text'], 'Qualification span mismatch')
    if issuer_id is not None: require(value['issuer_id'] == issuer_id, 'Scoped issuer changed')
    if document is not None:
        if 'qualification_id' in document: require(document['qualification_id'] == value['qualification_id'], 'Scoped qualification changed')
        if 'catalog_document_id' in document: require(document['catalog_document_id'] == q['document_id'], 'Scoped document changed')
        require(document['source_url'] == value['source_url'] and all(document[k] == old[k] for k in old), 'Scoped evidence binding changed')
        require(document.get('scoped_checked_at') == value['checked_at'] and document.get('source_check_status') == STATUS, 'Scoped timestamp mismatch')
        if 'period' in document: require(document['period'] == value['period'], 'Scoped period changed')
    return value


def create(root, packet, doc, observed, cache_path, *, listing_authority=None, market_open=False, kase=False, nasdaq_authority=None, app_rating=False):
    from . import library
    before = library.load_bytes(root,doc['raw_path'],doc['raw_sha256'])
    after = library.load_bytes(root,observed['raw_path'],observed['observed_sha256'])
    observed_text = source_parse.page(after,doc['source_url']).text.encode()
    observed_text_path = str(library.resolve(root,observed['raw_path']).with_name(sha(observed_text)+'.txt').relative_to(root))
    destination = library.resolve(root,observed_text_path)
    if destination.exists(): require(destination.read_bytes() == observed_text, 'Conflicting immutable observed extraction')
    else: destination.write_bytes(observed_text)
    require(nasdaq_authority is None or listing_authority is None and market_open is False and kase is False, 'Separate explicit combined Nasdaq qualification required')
    require(type(kase) is bool and (not kase or not market_open and listing_authority is None), 'Separate explicit KASE qualification required')
    require(type(market_open) is bool, 'Explicit widget qualification flag required')
    require(not market_open or listing_authority is None, 'Separate explicit market widget and listing transitions required')
    require(type(app_rating) is bool and (not app_rating or market_open and listing_authority is None and nasdaq_authority is None and not kase),'Separate explicit app rating qualification required')
    comparison=compare(before,after,doc['source_url'],allow_market_open=market_open, allow_kase=kase, allow_app_ratings=app_rating) if listing_authority is None and nasdaq_authority is None else None
    if listing_authority is not None:
        from . import transcript_listing_transition as listing
        auth,_=listing.authority(root,listing_authority,packet['issuer_id'],doc['source_url'],observed['checked_at'])
        comparison=listing.compare(before,after,doc['source_url'],auth)
    if nasdaq_authority is not None:
        from . import transcript_nasdaq_transition as listing
        auth,_=listing.authority(root,nasdaq_authority,packet['issuer_id'],doc['source_url'],observed['checked_at'])
        comparison=listing.compare(before,after,doc['source_url'],auth)
    value = {'version': APP_RATING_VERSION if app_rating else NASDAQ_VERSION if nasdaq_authority is not None else (KASE_VERSION if kase else MARKET_OPEN_VERSION if market_open else VERSION) if listing_authority is None else LISTING_VERSION, 'issuer_id': packet['issuer_id'], 'period': packet['period'],
             'source_url': doc['source_url'], 'qualification_id': doc['qualification_id'],
             'archived': {k:doc[k] for k in ('raw_path','raw_sha256','text_path','text_sha256')},
             'observed': {'raw_path': observed['raw_path'], 'raw_sha256': observed['observed_sha256'],
                          'text_path': observed_text_path, 'text_sha256': sha(observed_text)},
             'checked_at': timestamp(observed['checked_at']), 'http_cache_path': cache_path,
             'http_cache_sha256': sha(library.resolve(root,cache_path).read_bytes()),
             'comparison': comparison}
    if listing_authority is not None:value['listing_authority']=listing_authority
    if nasdaq_authority is not None:value['listing_authority']=nasdaq_authority
    name = 'reporting/source-currentness/'+digest(value)+'.json'
    library.save(library.resolve(root,name),value,immutable=True)
    reference = {'path':name,'sha256':sha(library.resolve(root,name).read_bytes())}
    replay(root,reference)
    return reference


def latest_observation(root, url):
    from . import library
    rows = []
    for path in [root/'collection/http-cache.json', *sorted((root/'sources').rglob('http-cache.json'))]:
        if path.is_file():
            value = library.read_json(path).get(url)
            if value and timestamp(value.get('checked_at')): rows.append((timestamp(value['checked_at']), value['sha256']))
    return max(rows) if rows else None


def apply(root, references):
    """New snapshot; preserve original evidence and qualification identities."""
    from . import library
    cat = copy.deepcopy(library.catalog(root))
    for reference in references:
        value = replay(root,reference); old = value['archived']; did = digest([value['issuer_id'],old['text_sha256']])
        matches = [d for d in cat['documents'][did]['sources'] if d['source_url'] == value['source_url'] and all(d[k] == old[k] for k in old)]
        require(len(matches) == 1, 'Archived catalog variant missing or ambiguous')
        require(latest_observation(root,value['source_url']) == (value['checked_at'],value['observed']['raw_sha256']), 'Later or conflicting source observation requires revalidation')
        variant = matches[0]
        variant.update(source_check_status=STATUS, scoped_checked_at=value['checked_at'], scoped_currentness=reference)
    cat.pop('catalog_id',None); cat['catalog_id'] = digest(cat)
    library.save(root/'library/snapshots'/ (cat['catalog_id']+'.json'),cat,immutable=True)
    library.save(root/'library/catalog.json',cat)
    return cat


def bindings(root, doc, *, historical=False):
    """Immutable request dependencies for replay at every worker/import boundary."""
    from . import library
    ref = doc.get('scoped_currentness')
    if not ref: return {}
    value = replay(root,ref,doc,historical=historical)
    names = [ref['path'], value['observed']['raw_path'], value['observed']['text_path'], value['http_cache_path']]
    result={p:sha(library.resolve(root,p).read_bytes()) for p in names}
    if value['version'] in (LISTING_VERSION,NASDAQ_VERSION):
        if value['version']==NASDAQ_VERSION:
            from . import transcript_nasdaq_transition as listing
        else:
            from . import transcript_listing_transition as listing
        _,inputs=listing.authority(root,value['listing_authority'],value['issuer_id'],value['source_url'],value['checked_at']);result.update(inputs)
    return result


def restore_available(root, issuer_ids):
    """Reapply exact still-current proofs after the collection catalog rebuild."""
    from . import library
    references = []
    for path in sorted((root/'reporting/source-currentness').glob('*.json')):
        value = library.read_json(path)
        if value.get('issuer_id') not in issuer_ids: continue
        # Older contradictory observations remain archived, never promoted.
        if latest_observation(root,value['source_url']) != (value['checked_at'],value['observed']['raw_sha256']): continue
        ref = {'path':str(path.relative_to(root)),'sha256':sha(path.read_bytes())}
        replay(root,ref)
        references.append(ref)
    if references: apply(root,references)
    return references


def rebuild_selected_packets(root, issuer_ids):
    from . import library
    from .freshness import assess_packet
    latest = library.read_json(root/'published/latest.json')
    cat = library.catalog(root)
    for iid in issuer_ids:
        row = latest['issuers'][iid]
        if not row.get('packet_id'): continue
        old = library.read_json(root/'library/packets'/(row['packet_id']+'.json'))
        require(old['issuer_id'] == iid and old['period'] == row['period'], 'Selected publication binding mismatch')
        packet = library.make_packet(root,iid,old['period'],[d['qualification_id'] for d in old['documents']],old['missing_reasons'])
        row.update(packet_id=packet['packet_id'],freshness=assess_packet(packet))
    latest['catalog_id'] = cat['catalog_id']
    library.save(root/'published/latest.json',latest)
    queue = library.read_json(root/'published/review-queue.json')
    for row in queue: row['catalog_id'] = cat['catalog_id']
    library.save(root/'published/review-queue.json',queue)
