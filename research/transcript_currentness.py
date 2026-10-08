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
VERSION = 'stockanalysis-market-and-app-counter-currentness-v2'
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


def signature(raw, url, *, allow_app_counters=False):
    require(urlsplit(url).hostname == 'stockanalysis.com' and
            re.fullmatch(r'/stocks/[a-z0-9.-]+/transcripts/[a-z0-9-]+/', urlsplit(url).path),
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
    require(re.search(r'(?:Market closed|At close:|Pre-market:|After-hours:)', widget_text), 'Unrecognized quote widget')
    require('transcript-sentence' not in html[a:b], 'Widget overlaps call evidence')
    outside_html = html[:a] + '<div>QUOTE_WIDGET</div>' + html[b:]
    if allow_app_counters:
        outside_html = app_counters(outside_html)
    outside = source_parse.page(outside_html.encode(), url).text
    facts = financial_evidence.extract_inline_xbrl(html, {'document_id': 'scope', 'raw_sha256': sha(raw), 'text_sha256': sha(page.text.encode())})
    facts = {'observations': [{k:v for k,v in o.items() if k not in ('observation_id','source_raw_sha256','support')} for o in facts['observations']],
             'gaps': [{k:v for k,v in g.items() if k != 'start'} for g in facts['gaps']]}
    return {'title': page.title, 'fiscal': page.fiscal, 'outside_widget_sha256': sha(outside.encode()),
            'block_sha256': [sha(b.encode()) for b in blocks.blocks],
            'block_text_sha256': [sha(b.encode()) for b in bodies], 'facts': facts}, {
            'fulltext_sha256': sha(page.text.encode()), 'call_span': [spans[0][0],spans[-1][1]],
            'widget_html_span': [a,b], 'widget_sha256': sha(html[a:b].encode())}


def compare(before, after, url, *, allow_app_counters=True):
    old, old_spans = signature(before, url, allow_app_counters=allow_app_counters)
    new, new_spans = signature(after, url, allow_app_counters=allow_app_counters)
    require(old == new, 'Complete transcript, metadata or non-widget content changed')
    require(old['title'] and old['block_sha256'], 'Transcript metadata missing')
    return {'signature': old, 'archived': old_spans, 'observed': new_spans,
            'whole_page_bytes_equal': before == after,
            'whole_page_text_equal': old_spans['fulltext_sha256'] == new_spans['fulltext_sha256']}


def replay(root, reference, document=None, *, issuer_id=None):
    from . import library
    path = library.resolve(root, reference['path'])
    require(sha(path.read_bytes()) == reference['sha256'], 'Currentness receipt hash changed')
    value = library.read_json(path)
    require(value['version'] in (VERSION, LEGACY_VERSION), 'Unsupported currentness proof')
    old, new = value['archived'], value['observed']
    before = library.load_bytes(root, old['raw_path'], old['raw_sha256'])
    text = library.load_bytes(root, old['text_path'], old['text_sha256'])
    after = library.load_bytes(root, new['raw_path'], new['raw_sha256'])
    observed_text = library.load_bytes(root, new['text_path'], new['text_sha256'])
    require(source_parse.page(after,value['source_url']).text.encode() == observed_text, 'Observed extraction mismatch')
    require(source_parse.page(before,value['source_url']).text.encode() == text, 'Archived extraction mismatch')
    require(compare(before,after,value['source_url'], allow_app_counters=value['version'] == VERSION) == value['comparison'], 'Scoped comparison changed')
    cache = library.resolve(root,value['http_cache_path'])
    require(sha(cache.read_bytes()) == value['http_cache_sha256'], 'HTTP observation changed')
    observation = library.read_json(cache)[value['source_url']]
    require(observation['sha256'] == new['raw_sha256'] and timestamp(observation['checked_at']) == value['checked_at'], 'Fetch proof mismatch')
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


def create(root, packet, doc, observed, cache_path):
    from . import library
    before = library.load_bytes(root,doc['raw_path'],doc['raw_sha256'])
    after = library.load_bytes(root,observed['raw_path'],observed['observed_sha256'])
    observed_text = source_parse.page(after,doc['source_url']).text.encode()
    observed_text_path = str(library.resolve(root,observed['raw_path']).with_name(sha(observed_text)+'.txt').relative_to(root))
    destination = library.resolve(root,observed_text_path)
    if destination.exists(): require(destination.read_bytes() == observed_text, 'Conflicting immutable observed extraction')
    else: destination.write_bytes(observed_text)
    value = {'version': VERSION, 'issuer_id': packet['issuer_id'], 'period': packet['period'],
             'source_url': doc['source_url'], 'qualification_id': doc['qualification_id'],
             'archived': {k:doc[k] for k in ('raw_path','raw_sha256','text_path','text_sha256')},
             'observed': {'raw_path': observed['raw_path'], 'raw_sha256': observed['observed_sha256'],
                          'text_path': observed_text_path, 'text_sha256': sha(observed_text)},
             'checked_at': timestamp(observed['checked_at']), 'http_cache_path': cache_path,
             'http_cache_sha256': sha(library.resolve(root,cache_path).read_bytes()),
             'comparison': compare(before,after,doc['source_url'])}
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


def bindings(root, doc):
    """Immutable request dependencies for replay at every worker/import boundary."""
    from . import library
    ref = doc.get('scoped_currentness')
    if not ref: return {}
    value = replay(root,ref,doc)
    names = [ref['path'], value['observed']['raw_path'], value['observed']['text_path'], value['http_cache_path']]
    return {p:sha(library.resolve(root,p).read_bytes()) for p in names}


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
