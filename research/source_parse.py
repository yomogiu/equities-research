"""Conservative source parsing: candidates retain uncertainty, never invented dates."""
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urldefrag

BLOCKS = {'p', 'div', 'section', 'article', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'br'}
EARNINGS = re.compile(r'earnings|financial results|quarter(?:ly| fiscal)|\b[1-4]q\b|\bq[1-4]\b', re.I)


class Page(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.text_parts, self.links, self.jsonld, self.rows = [], [], [], []
        self.skip = 0
        self.anchor = None
        self.ld = None
        self.row = self.cell = None
        self.title = ''
        self.in_title = False
        self.fiscal = {}
        self.focus = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'ix:hidden'):
            self.skip += 1
            if tag == 'script' and attrs.get('type') == 'application/ld+json':
                self.ld = []
            return
        if self.skip:
            return
        if tag == 'title':
            self.in_title = True
        if tag in BLOCKS:
            self.text_parts.append('\n')
        if tag in ('td', 'th'):
            self.text_parts.append('\t')
            self.cell = []
        if tag == 'tr':
            self.row = {'cells': [], 'links': []}
        if tag == 'a' and attrs.get('href'):
            self.anchor = {'url': urldefrag(urljoin(self.base, attrs['href']))[0], 'parts': []}
        if tag in ('ix:nonnumeric', 'ix:nonfraction') and attrs.get('name', '').startswith('dei:'):
            self.focus = attrs['name'].split(':')[-1]

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'ix:hidden'):
            if tag == 'script' and self.ld is not None:
                try:
                    self.jsonld.append(json.loads(''.join(self.ld)))
                except (ValueError, TypeError):
                    pass
                self.ld = None
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == 'title':
            self.in_title = False
        if tag == 'a' and self.anchor:
            link = {'url': self.anchor['url'], 'title': ''.join(self.anchor['parts']).strip()}
            self.links.append(link)
            if self.row is not None:
                self.row['links'].append(link)
            self.anchor = None
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row['cells'].append(''.join(self.cell).strip())
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag in BLOCKS:
            self.text_parts.append('\n')
        if tag in ('ix:nonnumeric', 'ix:nonfraction'):
            self.focus = None

    def handle_data(self, text):
        if self.skip:
            if self.ld is not None:
                self.ld.append(text)
            return
        if self.in_title:
            self.title += text
        else:
            self.text_parts.append(text)
        if self.anchor:
            self.anchor['parts'].append(text)
        if self.cell is not None:
            self.cell.append(text)
        if self.focus:
            self.fiscal[self.focus] = self.fiscal.get(self.focus, '') + text.strip()

    @property
    def text(self):
        return '\n'.join(re.sub(r' +', ' ', line).strip()
                         for line in ''.join(self.text_parts).splitlines() if line.strip())


def page(body, url):
    p = Page(url)
    p.feed(body.decode('utf-8', errors='replace'))
    return p


def extract(body, content_type, url):
    if body.startswith(b'%PDF') or 'application/pdf' in content_type:
        executable = shutil.which('pdftotext')
        if not executable:
            return '', {}, 'pdf_extractor_unavailable'
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'source.pdf', Path(tmp) / 'text.txt'
            source.write_bytes(body)
            try:
                subprocess.run([executable, '-layout', str(source), str(target)],
                               check=True, timeout=45, capture_output=True)
            except (subprocess.SubprocessError, OSError):
                return '', {}, 'pdf_extraction_failed'
            pages = target.read_text(errors='replace').split('\f')
            text = '\n\n'.join(f'[Page {i}]\n{s.strip()}' for i, s in enumerate(pages, 1) if s.strip())
            return text, {}, 'extracted' if text else 'ocr_required'
    if 'html' in content_type or b'<html' in body[:2000].lower() or b'<HTML' in body[:2000]:
        p = page(body, url)
        return p.text, p.fiscal, 'extracted'
    if 'text/plain' in content_type:
        return body.decode('utf-8', errors='replace'), {}, 'extracted'
    return '', {}, 'unsupported_document_type'


def kind_for(title, url):
    s = title + ' ' + url
    if title.strip().lower() in ('events & presentations', 'events and presentations', 'presentations'):
        return 'earnings_page'
    if re.search(r'to (?:report|announce|host)|will (?:report|announce|host)|announces? date', title, re.I):
        return 'earnings_page'
    if re.search(r'transcript|prepared.remark', s, re.I):
        return 'transcript'
    if re.search(r'presentation|slide.deck|earnings.slides', s, re.I):
        return 'presentation'
    if re.search(r'10-q', s, re.I):
        return 'periodic_filing'
    if re.search(r'annual.report|10-k|20-f|40-f', s, re.I):
        return 'annual_background'
    if re.search(r'press.release|earnings.release|reports.*(?:quarter|results)|financial.results', s, re.I):
        return 'release'
    if EARNINGS.search(s):
        return 'earnings_page'
    return None


def transcript_checks(text):
    qa = bool(re.search(r'question.and.answer|questions.and.answers|\bQ&A\b', text, re.I))
    speakers = len(set(re.findall(r'^([A-Z][A-Z .\'-]{3,60}):', text, re.M)))
    return {'characters': len(text), 'qa_detected': qa, 'speaker_labels': speakers,
            'substantial_call_text': len(text) >= 5000 and qa and speakers >= 2}


def structured_events(p):
    found = []
    def visit(x):
        if isinstance(x, list):
            for value in x:
                visit(value)
        elif isinstance(x, dict):
            types = x.get('@type', [])
            if isinstance(types, str):
                types = [types]
            if 'Event' in types and EARNINGS.search(x.get('name', '')):
                date = x.get('startDate')
                if isinstance(date, str):
                    try:
                        datetime.fromisoformat(date.replace('Z', '+00:00'))
                        found.append({'title': x['name'], 'start': date, 'source_url': p.base,
                                      'date_status': 'issuer_published', 'fiscal_period': None})
                    except ValueError:
                        pass
            for value in x.values():
                if isinstance(value, (dict, list)):
                    visit(value)
    for item in p.jsonld:
        visit(item)
    return found


def feed_links(body, base):
    # Do not process XML entity declarations from remote sources.
    if b'<!ENTITY' in body or b'<!DOCTYPE' in body:
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    found = []
    for item in root.iter():
        if item.tag.split('}')[-1] not in ('item', 'entry'):
            continue
        title, link, published = '', '', None
        for child in item:
            tag = child.tag.split('}')[-1]
            if tag == 'title':
                title = ''.join(child.itertext())
            elif tag == 'link':
                link = child.get('href') or (child.text or '')
            elif tag in ('pubDate', 'published', 'updated'):
                published = child.text
        if link and EARNINGS.search(title):
            found.append({'title': title, 'url': urljoin(base, link), 'published_label': published})
    return found


def calendar_events(body, url, format='html'):
    """Extract explicit dates only. No event date inferred from publication dates."""
    if format == 'ics':
        text = re.sub(r'\r?\n[ \t]', '', body.decode('utf-8', errors='replace'))
        events = []
        for block in text.split('BEGIN:VEVENT')[1:]:
            fields = {}
            for line in block.split('END:VEVENT')[0].splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    fields[key.split(';')[0]] = (key, value)
            title = fields.get('SUMMARY', ('', ''))[1]
            key, start = fields.get('DTSTART', ('', ''))
            if not EARNINGS.search(title):
                continue
            pattern = '%Y%m%d' if len(start) == 8 else '%Y%m%dT%H%M%SZ' if start.endswith('Z') else '%Y%m%dT%H%M%S'
            try:
                parsed = datetime.strptime(start, pattern)
            except ValueError:
                continue
            events.append({'title': title, 'start': parsed.date().isoformat() if len(start) == 8 else parsed.isoformat() + ('Z' if start.endswith('Z') else ''),
                           'source_url': url, 'timezone_label': key.split('TZID=')[-1] if 'TZID=' in key else None,
                           'date_status': 'issuer_published', 'fiscal_period': None})
        return events
    p = page(body, url)
    events = structured_events(p)
    if format == 'dated_lines':
        # Opt-in adapter for issuer calendars with a standalone date followed by title.
        lines = p.text.splitlines()
        for first, title in zip(lines, lines[1:]):
            match = re.fullmatch(r'([A-Z][a-z]+ \d{1,2}, 20\d{2})(?: \([A-Za-z]+\))?', first)
            if match and EARNINGS.search(title):
                try:
                    start = datetime.strptime(match[1], '%B %d, %Y').date().isoformat()
                except ValueError:
                    continue
                events.append({'title': title, 'start': start, 'source_url': url,
                               'date_status': 'issuer_published_date_block', 'fiscal_period': None,
                               'timezone_label': None})
    # Restrict unstructured dates to a single table row with an earnings label.
    for row in p.rows:
        label = ' '.join(row['cells'])
        if not EARNINGS.search(label):
            continue
        candidates = re.findall(r'\b(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|[A-Z][a-z]+ \d{1,2},? 20\d{2})\b', label)
        dates = set()
        for candidate in candidates:
            for pattern in ('%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y'):
                try:
                    dates.add(datetime.strptime(candidate, pattern).date().isoformat())
                    break
                except ValueError:
                    continue
        if len(dates) == 1:
            events.append({'title': label, 'start': dates.pop(), 'source_url': url,
                           'date_status': 'issuer_published_table_date', 'fiscal_period': None,
                           'timezone_label': None})
    return events
