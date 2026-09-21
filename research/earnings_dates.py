"""Conservative issuer earnings-calendar parsing; no inferred dates or fiscal years.

The caller establishes issuer identity and source trust. ``issuer_published`` says
only that the source explicitly associates the date with an earnings event.
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .source_parse import page

EARNINGS = re.compile(
    r'earnings|financial\s+results|(?:quarterly|annual|interim|full.year|half.year)\s+results'
    r'|results\s+(?:announcement|release|presentation|conference|webcast|call)'
    r'|(?:決算|决算|業績|业绩|財務|财务|財報|财报).{0,12}(?:発表|发表|説明会|说明会|發布|发布|公佈|公布|公告|報告|报告)'
    r'|法說會|法说会|法人說明會|法人说明会', re.I)
UNRELATED = re.compile(r'investor\s+(?:conference|day)|dividend|ex.dividend|shareholder|股東大會|股东大会', re.I)
PERIOD_END = re.compile(r'(?:period|quarter|year|months?)\s+(?:ended|ending)|as\s+(?:of|at)|截至|截止|期末', re.I)
ANNOUNCE = re.compile(r'\b(?:will|to|scheduled\s+to|plans?\s+to|expects?\s+to)\s+(?:\w+\s+){0,3}(?:report|announce|release|publish|hold|host)\b', re.I)
DATE_TOKEN = re.compile(
    r'\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b'
    r'|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*20\d{2}\b'
    r'|\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+20\d{2}\b'
    r'|20\d{2}年\s*\d{1,2}月\s*\d{1,2}日', re.I)
CALENDAR = re.compile(r'financial\s+calendar|earnings\s+calendar|upcoming\s+events|events\s+(?:and|&)\s+presentations|IR\s+calendar|財務日曆|財務日历|財務行事曆|決算発表予定|IRカレンダー', re.I)
PUBLICATION = re.compile(r'\b(?:published|posted|updated|last updated|publication date)\b|發布日期|发布日期|掲載日|更新日', re.I)
EVENT_ACTION = re.compile(r'earnings\s+(?:call|release|webcast|announcement|presentation)|results\s+(?:announcement|release|presentation|conference|webcast|call)|決算発表|法說會|法说会|法人說明會|法人说明会', re.I)
TENTATIVE = re.compile(r'\btentative\b|\bestimated\b|\bexpected\b|\bprovisional\b|予定|預計|预计', re.I)


def _date(value):
    value = re.sub(r'(\d)(?:st|nd|rd|th)\b', r'\1', value, flags=re.I)
    value = re.sub(r'\bSept\.?\b', 'Sep', value, flags=re.I).replace('.', '')
    value = re.sub(r'\s+', ' ', value).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y', '%Y年%m月%d日'):
        try:
            return datetime.strptime(value.replace(' ', '') if '年' in value else value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _dates(text):
    return [(m.start(), m.end(), parsed) for m in DATE_TOKEN.finditer(text) if (parsed := _date(m.group()))]


def _period(text):
    # Explicit fiscal designators only, never derive a quarter from event date.
    match = re.search(r'\bFY\s*(20\d{2})\s*[- /]?\s*Q([1-4])\b', text, re.I)
    if match:
        return f'FY{match[1]}-Q{match[2]}'
    match = re.search(r'\bQ([1-4])\s+(?:FY|fiscal\s+(?:year\s+)?)(20\d{2})\b', text, re.I)
    if match:
        return f'FY{match[2]}-Q{match[1]}'
    return None


def _earnings(text):
    return bool(EARNINGS.search(text)) and not bool(UNRELATED.search(text))


def _event(title, start, url, method, evidence=None, **extra):
    evidence = evidence or title
    status = 'issuer_published_' + method
    if TENTATIVE.search(evidence):
        status = 'issuer_published_tentative'
    return {'title': title.strip()[:500], 'start': start, 'source_url': url,
            'date_status': status, 'fiscal_period': _period(title),
            'evidence_excerpt': evidence[:1600], **extra}


def _structured(p):
    found = []
    def visit(node):
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            types = node.get('@type', [])
            if isinstance(types, str):
                types = [types]
            title, start = node.get('name'), node.get('startDate')
            if ('Event' in types or 'BusinessEvent' in types) and isinstance(title, str) and _earnings(title) and isinstance(start, str):
                try:
                    # datetime.fromisoformat accepts compact dates; demand visible ISO.
                    if not re.match(r'^20\d{2}-\d{2}-\d{2}(?:T|$)', start):
                        raise ValueError('not ISO')
                    datetime.fromisoformat(start.replace('Z', '+00:00'))
                    if str(node.get('eventStatus', '')).endswith('EventCancelled'):
                        return
                    evidence = json.dumps({k: node[k] for k in ('name', 'startDate', 'eventStatus') if k in node}, ensure_ascii=False)
                    found.append(_event(title, start, p.base, 'structured_event', evidence))
                except ValueError:
                    pass
            for item in node.values():
                if isinstance(item, (dict, list)):
                    visit(item)
    for item in p.jsonld:
        visit(item)
    return found


def _ics(text, url):
    text = re.sub(r'\r?\n[ \t]', '', text)
    found = []
    for block in text.split('BEGIN:VEVENT')[1:]:
        fields = {}
        for line in block.split('END:VEVENT')[0].splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                fields[key.split(';')[0].upper()] = (key, value)
        title = fields.get('SUMMARY', ('', ''))[1].replace(r'\,', ',').replace(r'\n', ' ')
        if not _earnings(title) or fields.get('STATUS', ('', ''))[1].upper() == 'CANCELLED':
            continue
        key, value = fields.get('DTSTART', ('', ''))
        tz_match = re.search(r'TZID="?([^;"\r\n]+)', key, re.I)
        timezone = tz_match[1] if tz_match else None
        try:
            if len(value) == 8:
                start = datetime.strptime(value, '%Y%m%d').date().isoformat()
            else:
                parsed = datetime.strptime(value, '%Y%m%dT%H%M%SZ' if value.endswith('Z') else '%Y%m%dT%H%M%S')
                if timezone and not value.endswith('Z'):
                    try:
                        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
                    except ZoneInfoNotFoundError:
                        pass  # Retain original timezone label, never guess an offset.
                start = parsed.isoformat() + ('Z' if value.endswith('Z') else '')
        except ValueError:
            continue
        event = _event(title, start, url, 'ics', f'SUMMARY:{title}\n{key}:{value}', timezone_label=timezone)
        if fields.get('STATUS', ('', ''))[1].upper() == 'TENTATIVE':
            event['date_status'] = 'issuer_published_tentative'
        found.append(event)
    return found


def _prose(text, url):
    found = []
    # A date belongs only to the sentence that states the intended earnings action.
    for sentence in re.split(r'(?<=[!?。])\s*|(?<=\.)\s+(?=[A-Z])|[\r\n]+', text):
        sentence = sentence.strip()
        if len(sentence) > 1600 or not _earnings(sentence):
            continue
        actions = list(ANNOUNCE.finditer(sentence))
        if not actions:
            continue
        bound = []
        for begin, end, start in _dates(sentence):
            # Explicit preposition is mandatory; a dateline and 'quarter ended'
            # are not event dates. Optional weekday belongs to the date phrase.
            prefix = sentence[:begin]
            prep = re.search(r'\bon\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?$', prefix, re.I)
            if prep and any(a.start() < prep.start() and prep.start() - a.end() < 700 for a in actions):
                # 'results for the quarter ended on DATE' still describes a period.
                local = prefix[max(0, prep.start() - 50):prep.start()]
                if not re.search(r'\b(?:ended|ending|as of|as at)\s*$', local, re.I):
                    bound.append((start, begin, end))
        distinct = {x[0] for x in bound}
        for start, begin, end in bound:
            event = _event(sentence, start, url, 'announcement', sentence)
            if len(distinct) > 1:
                event['date_status'] = 'candidate_multiple_dates'
            found.append(event)
    return found


def parse_events(body, url, format='html'):
    """Extract explicit earnings dates with evidence and uncertainty retained.

    Accepts bytes or text. No relative dates, omitted years, publication dates,
    fiscal-period ends, or dates outside a bounded earnings-event block.
    """
    if isinstance(body, str):
        body = body.encode('utf-8')
    text = body.decode('utf-8', errors='replace')
    if format == 'ics' or 'BEGIN:VCALENDAR' in text[:1000]:
        events = _ics(text, url)
    else:
        p = page(body, url)
        events = _structured(p)
        calendar_page = format == 'dated_lines' or bool(CALENDAR.search(p.title + '\n' + p.text[:4000]))
        # HTML block boundaries can split an inline table: preserve row scope.
        for row in p.rows:
            label = ' '.join(row['cells'])
            if len(label) > 1600 or not _earnings(label) or PERIOD_END.search(label) or PUBLICATION.search(label):
                continue
            dates = _dates(label)
            if len({x[2] for x in dates}) == 1:
                event = _event(label, dates[0][2], url, 'table_date', label)
                if not calendar_page and not EVENT_ACTION.search(label):
                    event['date_status'] = 'candidate_unqualified_table_date'
                events.append(event)
        events.extend(_prose(p.text, url))
        if calendar_page:
            lines = p.text.splitlines()
            for index, line in enumerate(lines):
                if len(line) > 800 or PUBLICATION.search(line):
                    continue
                dates = _dates(line)
                if len(dates) == 1 and _earnings(line) and not PERIOD_END.search(line) and not ANNOUNCE.search(line):
                    events.append(_event(line, dates[0][2], url, 'calendar_block', line))
                # Only standalone dates may bind to the immediately adjacent title.
                if len(dates) != 1:
                    continue
                begin, end, start = dates[0]
                remainder = (line[:begin] + line[end:]).strip()
                if remainder and not re.fullmatch(r'[(),\s]*(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?|[月火水木金土日])[(),\s]*', remainder, re.I):
                    continue
                # Opposing adjacent titles cannot establish which card owns
                # the date after HTML flattening; retain candidates explicitly.
                neighbors = [title for title in lines[max(0, index - 1):index] + lines[index + 1:index + 2]
                             if len(title) <= 500 and _earnings(title) and not _dates(title)
                             and not PERIOD_END.search(title) and not ANNOUNCE.search(title)
                             and not PUBLICATION.search(title)]
                for title in neighbors:
                    event = _event(title, start, url, 'calendar_block', line + '\n' + title)
                    if len(set(neighbors)) > 1:
                        event['date_status'] = 'candidate_ambiguous_calendar_block'
                    events.append(event)
    # Retain distinct event types/titles even on the same day; collapse parser overlap.
    unique = {}
    for event in events:
        key = (event['start'], re.sub(r'\s+', ' ', event['title']).casefold())
        unique.setdefault(key, event)
    return list(unique.values())
