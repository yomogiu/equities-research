"""Exact-span transcript indexing and structural Q&A finding validation.

Offsets are Python Unicode character offsets into the unchanged source text, never
byte offsets. Heuristic parsing is intentionally provisional: it cannot certify
speaker identity, transcript completeness, answer quality, or investment relevance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from html.parser import HTMLParser
import re

VERSION = 'transcript-evidence-v1'
ROLES = {'analyst', 'management', 'operator', 'unknown'}
SECTION_KINDS = {'prepared_remarks', 'qa', 'other'}
ANSWER_CLASSES = {'direct', 'partial', 'redirected', 'explicitly_withheld',
                  'unresolved_after_followup', 'not_assessable'}
FINDING_FIELDS = ('technical_mechanism', 'financial_implication', 'counterevidence',
                  'uncertainty', 'next_test')


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _id(prefix, value):
    return prefix + '-' + _hash(json.dumps(value, sort_keys=True, ensure_ascii=False))[:24]


def _span(text, start, end):
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise ValueError('Offsets must be integer Unicode character positions')
    if not 0 <= start < end <= len(text):
        raise ValueError('Span outside source or empty')
    return {'start': start, 'end': end, 'text': text[start:end]}


def _nonoverlap(items, label):
    if any(a['end'] > b['start'] for a, b in zip(items, items[1:])):
        raise ValueError(f'Overlapping {label}')


def _detected_boundaries(text, source):
    # Only explicit whole-line headings; no claim that every publisher uses these.
    qa = list(re.finditer(r'(?im)^\s*(?:questions?\s*(?:and|&)\s*answers?|q\s*&\s*a)(?:\s+session)?\s*:?\s*$', text))
    sections = []
    if qa:
        start = qa[0].start()
        if start:
            sections.append({'start': 0, 'end': start, 'kind': 'prepared_remarks'})
        if start < len(text):
            sections.append({'start': start, 'end': len(text), 'kind': 'qa'})
    elif text:
        sections = [{'start': 0, 'end': len(text), 'kind': 'other'}]
    speakers = {'Operator': 'operator'}
    for speaker in source.get('speakers', []):
        if speaker.get('role') not in ROLES or not speaker.get('name'):
            raise ValueError('Invalid source speaker registry')
        speakers[speaker['name']] = speaker['role']
    markers = []
    for name, role in speakers.items():
        # Accept exact registered name on its own line or explicit colon prefix.
        pattern = r'(?m)^\s*' + re.escape(name) + r'(?:\s*:\s*|[ \t]*\r?$)'
        for match in re.finditer(pattern, text):
            markers.append((match.start(), name, role))
    markers.sort()
    if len({m[0] for m in markers}) != len(markers):
        raise ValueError('Ambiguous duplicate speaker markers')
    turns = []
    for i, (start, name, role) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        # A heading terminates the preceding turn; headings are not speaker text.
        section_ends = [s['end'] for s in sections if s['start'] <= start < s['end']]
        if section_ends:
            end = min(end, section_ends[0])
        turns.append({'start': start, 'end': end, 'speaker': name, 'role': role})
    return sections, turns, ['Automatic layout detection is provisional; review speaker and section boundaries.',
                             'Transcript completeness and issuer/period qualification are not assessed here.']


def index_transcript(text, source, reviewed_boundaries=None, *, provisional_boundaries=None):
    """Index unchanged text. Reviewed annotations are supplied, not self-certified.

    source: document_id, text_sha256; optional speakers [{name,role}].
    reviewed_boundaries: reviewed=True, sections [{start,end,kind}], turns
    [{start,end,speaker,role}]. Review provenance can be supplied as review_id.
    Returned source stores only identifiers/hashes (no duplicated source body).
    """
    if not isinstance(text, str) or not text:
        raise ValueError('Nonempty transcript text required')
    if not source.get('document_id') or source.get('text_sha256') != _hash(text):
        raise ValueError('Missing document identity or source hash mismatch')
    reviewed = reviewed_boundaries is not None
    if reviewed and provisional_boundaries is not None:
        raise ValueError('Choose reviewed or provisional boundaries, not both')
    if reviewed:
        if reviewed_boundaries.get('source_sha256', source['text_sha256']) != source['text_sha256']:
            raise ValueError('Reviewed boundaries belong to a different source')
        if reviewed_boundaries.get('reviewed') is not True:
            raise ValueError('Annotations must explicitly declare reviewed boundaries')
        sections = reviewed_boundaries.get('sections', [])
        turns = reviewed_boundaries.get('turns', [])
        uncertainty = ['Transcript completeness and issuer/period qualification are not assessed here.']
        if not sections or not turns:
            raise ValueError('Reviewed sections and turns required')
    elif provisional_boundaries is not None:
        if provisional_boundaries.get('source_sha256') != source['text_sha256']:
            raise ValueError('Provisional boundaries belong to a different source')
        sections, turns = provisional_boundaries['sections'], provisional_boundaries['turns']
        uncertainty = ['Publisher layout and speaker roles are provisional; independent review is required.',
                       'Transcript completeness and issuer/period qualification are not assessed here.']
    else:
        sections, turns, uncertainty = _detected_boundaries(text, source)
    source_key = {k: source[k] for k in ('document_id', 'text_sha256')}
    if source.get('source_path'):
        source_key['source_path'] = source['source_path']
    parser_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    base = [{k: source[k] for k in ('document_id', 'text_sha256')}, VERSION, parser_hash]
    indexed_sections = []
    for section in sorted(sections, key=lambda s: s['start']):
        if section.get('kind') not in SECTION_KINDS:
            raise ValueError('Unknown section kind')
        span = _span(text, section['start'], section['end'])
        indexed_sections.append({'start': span['start'], 'end': span['end'], 'kind': section['kind'],
                                 'id': _id('section', [base, span['start'], span['end'], section['kind']])})
    _nonoverlap(indexed_sections, 'sections')
    indexed_turns = []
    for turn in sorted(turns, key=lambda t: t['start']):
        if turn.get('role') not in ROLES or not isinstance(turn.get('speaker'), str) or not turn['speaker'].strip():
            raise ValueError('Invalid turn speaker/role')
        span = _span(text, turn['start'], turn['end'])
        owners = [s for s in indexed_sections if s['start'] <= span['start'] and span['end'] <= s['end']]
        section = owners[0] if len(owners) == 1 else None
        if not section:
            uncertainty.append(f"Turn at {span['start']} crosses or lacks a section boundary.")
        record = {'start': span['start'], 'end': span['end'], 'speaker': turn['speaker'], 'role': turn['role'],
                  'section_id': section['id'] if section else None,
                  'section_kind': section['kind'] if section else 'other'}
        record['id'] = _id('turn', [base, span['start'], span['end'], turn['speaker'], turn['role']])
        indexed_turns.append(record)
    _nonoverlap(indexed_turns, 'turns')
    exchanges = []
    current = None
    previous = None
    unassigned_qa = []
    for turn in indexed_turns:
        if turn['section_kind'] != 'qa':
            current = None
            previous = None
            continue
        role = turn['role']
        if role == 'analyst':
            # Consecutive analyst turns before an answer preserve multipart questions.
            if current and not current['answer_turn_ids'] and current['analyst'] == turn['speaker']:
                current['question_turn_ids'].append(turn['id'])
                current['turn_ids'].append(turn['id'])
            else:
                previous = current or previous
                current = {'analyst': turn['speaker'], 'question_turn_ids': [turn['id']],
                           'answer_turn_ids': [], 'operator_turn_ids': [], 'unknown_turn_ids': [],
                           'turn_ids': [turn['id']],
                           'followup_of': previous['id'] if previous and previous['analyst'] == turn['speaker'] else None}
                current['id'] = _id('exchange', [base, turn['id']])
                exchanges.append(current)
        elif current:
            current['turn_ids'].append(turn['id'])
            key = {'management': 'answer_turn_ids', 'operator': 'operator_turn_ids', 'unknown': 'unknown_turn_ids'}[role]
            current[key].append(turn['id'])
        else:
            unassigned_qa.append(turn['id'])
    for exchange in exchanges:
        exchange['status'] = 'response_identified' if exchange['answer_turn_ids'] else 'no_identified_answer'
        exchange['boundary_review'] = 'reviewed' if reviewed else 'provisional'
    if not exchanges:
        uncertainty.append('No Q&A exchanges identified; this does not establish absence of Q&A.')
    if any(t['role'] == 'unknown' for t in indexed_turns):
        uncertainty.append('Some speaker roles remain unknown.')
    covered = sum(t['end'] - t['start'] for t in indexed_turns)
    gaps, cursor = [], 0
    for turn in indexed_turns:
        if turn['start'] > cursor:
            gaps.append({'start': cursor, 'end': turn['start']})
        cursor = turn['end']
    if cursor < len(text):
        gaps.append({'start': cursor, 'end': len(text)})
    return {'schema_version': VERSION, 'source': source_key,
            'parser_sha256': parser_hash, 'offset_unit': 'unicode_character',
            'boundary_review': 'reviewed' if reviewed else 'provisional',
            'review_id': reviewed_boundaries.get('review_id') if reviewed else None,
            'needs_review': not reviewed or any(t['role'] == 'unknown' or t['section_id'] is None for t in indexed_turns),
            'sections': indexed_sections, 'turns': indexed_turns, 'exchanges': exchanges,
            'coverage': {'source_characters': len(text), 'assigned_characters': covered,
                         'unassigned_spans': gaps, 'unassigned_qa_turn_ids': unassigned_qa},
            'uncertainty': uncertainty}



class _TranscriptBlocks(HTMLParser):
    """Locate rendered timed transcript blocks; never execute embedded scripts."""
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw, self.blocks, self.depth, self.active = raw, [], 0, None
        self.unbound_sentences = 0
        self.lines = [0] + [m.end() for m in re.finditer('\n', raw)]

    def absolute_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if 'transcript-sentence' in dict(attrs).get('class', '').split() and self.active is None:
            self.unbound_sentences += 1
        if tag != 'div':
            return
        self.depth += 1
        classes = set(dict(attrs).get('class', '').split())
        if self.active is None and {'border-t', 'first:border-t-0'} <= classes:
            self.active = (self.depth, self.absolute_offset())

    def handle_endtag(self, tag):
        if tag != 'div':
            return
        if self.active and self.active[0] == self.depth:
            block = self.raw[self.active[1]:self.absolute_offset() + len('</div>')]
            if 'transcript-sentence' in block:
                self.blocks.append(block)
            self.active = None
        self.depth -= 1


class _TranscriptRole(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.active, self.parts = 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            self.depth += 1
            if 'italic' in dict(attrs).get('class', '').split():
                self.active = self.depth

    def handle_endtag(self, tag):
        if tag == 'div':
            if self.active == self.depth:
                self.active = None
            self.depth -= 1

    def handle_data(self, text):
        if self.active is not None:
            self.parts.append(text)


_LEGAL_SUFFIXES = {'inc', 'incorporated', 'corp', 'corporation', 'co', 'company',
                   'ltd', 'limited', 'plc', 'llc', 'lp', 'llp', 'ag', 'se', 'nv', 'sa'}


def _issuer_name_key(name):
    """Normalize typography and terminal legal forms, never invent brand aliases."""
    words = re.findall(r'[^\W_]+', name.casefold().replace('&', ' and '))
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return ''.join(words)


def _publisher_speaker_role(name, label, issuer_names):
    if name.casefold() == 'operator':
        return 'operator'
    # Explicit professional analyst labels, including senior/research variants.
    # A reference to analyst relations elsewhere in a title is not this role.
    title = label.split(',', 1)[0].strip()
    if re.search(r'\banalyst$', title, re.I):
        return 'analyst'
    names = {_issuer_name_key(n) for n in issuer_names if isinstance(n, str)} - {''}
    # A title alone cannot distinguish issuer management from an external firm's
    # CEO/chairperson. Require a matching company suffix in the rendered label.
    for comma in re.finditer(',', label):
        title, affiliation = label[:comma.start()], label[comma.end():]
        if _issuer_name_key(affiliation) in names and re.search(
                r'\b(?:CEO|CFO|COO|CTO|chief|president|chairman|chairwoman|chair|founder|investor relations|treasurer|controller)\b',
                title, re.I):
            return 'management'
    return 'unknown'


class _ParagraphBlocks(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw=raw;self.lines=[0]
        for match in re.finditer('\n',raw):self.lines.append(match.end())
        self.depth=0;self.container=None;self.heading=False;self.start=None;self.end=None
        self.paragraph=None;self.blocks=[];self.containers=0;self.headings=0
    def position(self):
        line,column=self.getpos();return self.lines[line-1]+column
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.depth+=1
            if attrs.get('id')=='article-body-transcript':
                self.containers+=1;self.container=self.depth
        if self.container is None:return
        if tag=='h2' and attrs.get('id')=='full-conference-call-transcript':
            self.headings+=1;self.heading=True
        if tag=='p' and self.start is not None and self.end is None:
            if self.paragraph is not None:raise ValueError('Nested transcript paragraphs')
            self.paragraph=self.position()
    def handle_endtag(self,tag):
        if tag=='h2' and self.heading:
            self.start=self.position()+len('</h2>');self.heading=False
        if tag=='p' and self.paragraph is not None:
            self.blocks.append(self.raw[self.paragraph:self.position()+len('</p>')]);self.paragraph=None
        if tag=='div':
            if self.container==self.depth:
                self.end=self.position();self.container=None
            self.depth-=1


def _paragraph_turns(text,raw):
    """Return exact source turns or None for an unrecognized layout.

    Speaker labels are structural evidence only. An unlabeled paragraph continues
    the immediately preceding speaker. Review must separately establish Q&A roles.
    """
    from .source_parse import page
    parser=_ParagraphBlocks(raw.decode('utf-8',errors='replace'));parser.feed(parser.raw)
    if not parser.containers:return None
    if parser.containers!=1 or parser.headings!=1 or parser.start is None or parser.end is None or parser.paragraph is not None:
        raise ValueError('Incomplete or ambiguous paragraph transcript container')
    if not parser.blocks:raise ValueError('Empty paragraph transcript')
    bodies=[page(block.encode(),'').text for block in parser.blocks]
    scoped=page(parser.raw[parser.start:parser.end].encode(),'').text
    if scoped!='\n'.join(bodies):raise ValueError('Unindexed content in paragraph transcript')
    cursor=text.find(scoped)
    if cursor<0 or text.find(scoped,cursor+1)>=0:raise ValueError('Paragraph transcript text not uniquely present')
    result=[]
    for block,body in zip(parser.blocks,bodies):
        if not body:raise ValueError('Empty paragraph inside transcript')
        match=re.match(r'<p(?:\s[^>]*)?>\s*<strong(?:\s[^>]*)?>(.*?)</strong>',block,re.S|re.I)
        if match:
            label=page(match.group(1).encode(),'').text
            if not re.fullmatch(r'[^:\n]{1,100}:',label):raise ValueError('Invalid paragraph speaker label')
            name=label[:-1].strip()
            if not name or not body.startswith(label):raise ValueError('Paragraph speaker differs from source')
            result.append({'start':cursor,'end':cursor+len(body),'speaker':name,
                           'role':'operator' if name.casefold()=='operator' else 'unknown'})
        elif result:
            result[-1]['end']=cursor+len(body)
        else:raise ValueError('Transcript begins without speaker label')
        cursor+=len(body)+1
    return result


def index_publisher_transcript(text, source, raw):
    """Index timed HTML call blocks against unchanged text and original offsets.

    The rendered speaker/role labels are evidence, not independent qualification.
    source.issuer_names must come from verified catalog identity or separately
    approved aliases; names discovered in this page are never affiliation proof.
    Unsupported layouts retain the conservative plain-text parser. Recognized
    layouts fail closed on a text mismatch rather than dropping unparsed speech.
    """
    from .source_parse import page
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != source.get('raw_sha256'):
        raise ValueError('Publisher HTML source hash mismatch')
    paragraphs = _paragraph_turns(text, raw)
    if paragraphs is not None:
        first, last = paragraphs[0]['start'], paragraphs[-1]['end']
        result = index_transcript(text, source, provisional_boundaries={
            'source_sha256': source['text_sha256'],
            'sections': [{'start': first, 'end': last, 'kind': 'prepared_remarks'}],
            'turns': paragraphs})
        result.update(layout='speaker-paragraphs-v1', raw_sha256=source['raw_sha256'],
                      issuer_affiliation={'issuer_id': source.get('issuer_id'),
                                          'catalog_id': source.get('catalog_id'),
                                          'names': source.get('issuer_names', [])},
                      call_span={'start': first, 'end': last},
                      excluded_spans=[{'start': a, 'end': b, 'reason': 'outside_rendered_call'}
                                      for a, b in ((0, first), (last, len(text))) if a < b])
        return result
    parser = _TranscriptBlocks(raw.decode('utf-8', errors='replace'))
    parser.feed(parser.raw)
    if parser.unbound_sentences:
        raise ValueError('Timed transcript sentences occur outside recognized speaker blocks')
    if not parser.blocks:
        return index_transcript(text, source)
    issuer_names = source.get('issuer_names', [])
    if not isinstance(issuer_names, list) or any(not isinstance(n, str) or not n.strip() for n in issuer_names):
        raise ValueError('Verified issuer names must be a list of nonempty strings')
    turns, cursor = [], 0
    for block in parser.blocks:
        body = page(block.encode('utf-8'), '').text
        lines = body.splitlines()
        if len(lines) < 2:
            raise ValueError('Incomplete publisher transcript block')
        start = text.find(body, cursor)
        if start < 0 or (turns and text[cursor:start].strip()):
            raise ValueError('Publisher transcript blocks do not exactly cover archived call text')
        name = lines[0].strip()
        metadata = _TranscriptRole()
        metadata.feed(block)
        label = ''.join(metadata.parts).strip()
        role = _publisher_speaker_role(name, label, issuer_names)
        cursor = start + len(body)
        turns.append({'start': start, 'end': cursor, 'speaker': name, 'role': role})
    first, last = turns[0]['start'], turns[-1]['end']
    qa = next((t['start'] for t in turns if t['role'] == 'analyst'), None)
    sections = []
    if qa is None:
        sections.append({'start': first, 'end': last, 'kind': 'prepared_remarks'})
    else:
        if qa > first:
            sections.append({'start': first, 'end': qa, 'kind': 'prepared_remarks'})
        sections.append({'start': qa, 'end': last, 'kind': 'qa'})
    result = index_transcript(text, source, provisional_boundaries={
        'source_sha256': source['text_sha256'], 'sections': sections, 'turns': turns})
    result['layout'] = 'timed-publisher-blocks-v1'
    result['raw_sha256'] = source['raw_sha256']
    result['issuer_affiliation'] = {'issuer_id': source.get('issuer_id'),
                                    'catalog_id': source.get('catalog_id'),
                                    'names': source.get('issuer_names', [])}
    result['call_span'] = {'start': first, 'end': last}
    result['excluded_spans'] = [{'start': a, 'end': b, 'reason': 'outside_rendered_call'}
                                for a, b in ((0, first), (last, len(text))) if a < b]
    return result


def validate_findings(findings, index, text, fact_ids=()):
    """Return structural validation receipt or raise ValueError.

    Does NOT judge semantic truth, completeness, quality or whether evidence supports
    an interpretation. Independent original-source review remains mandatory.
    """
    if index.get('source', {}).get('text_sha256') != _hash(text):
        raise ValueError('Source hash mismatch')
    if index.get('offset_unit') != 'unicode_character':
        raise ValueError('Unsupported offset unit')
    if not isinstance(findings, list) or not findings:
        raise ValueError('Nonempty findings list required')
    turns = {t['id']: t for t in index['turns']}
    exchanges = {e['id']: e for e in index['exchanges']}
    for turn in turns.values():
        _span(text, turn['start'], turn['end'])
    known_facts = set(fact_ids)
    seen = set()
    for finding in findings:
        fid = finding.get('id')
        if not isinstance(fid, str) or not fid.strip() or fid in seen:
            raise ValueError('Unique nonempty finding IDs required')
        seen.add(fid)
        if finding.get('answer_classification') not in ANSWER_CLASSES:
            raise ValueError('Unsupported answer classification')
        for key in ('question_assessed', 'answer_assessed', *FINDING_FIELDS):
            if not isinstance(finding.get(key), str) or not finding[key].strip():
                raise ValueError(f'Missing substantive field: {key}')
        exchange_ids = finding.get('exchange_ids')
        if not isinstance(exchange_ids, list) or not exchange_ids or any(e not in exchanges for e in exchange_ids):
            raise ValueError('Unknown or missing exchange IDs')
        references = finding.get('fact_ids')
        if not isinstance(references, list) or any(f not in known_facts for f in references):
            raise ValueError('Unknown or missing financial fact references')
        quotes = finding.get('quotes')
        if not isinstance(quotes, list) or not quotes:
            raise ValueError('Exact source quotes required')
        quoted_exchanges = set()
        for quote in quotes:
            if quote.get('document_id', index['source']['document_id']) != index['source']['document_id']:
                raise ValueError('Quote document identity mismatch')
            eid = quote.get('exchange_id')
            if eid not in exchange_ids:
                raise ValueError('Quote exchange not bound to finding')
            span = _span(text, quote['start'], quote['end'])
            if span['text'] != quote.get('text'):
                raise ValueError('Quote differs from original source')
            members = [turns[tid] for tid in exchanges[eid]['turn_ids'] if tid in turns]
            if not any(t['start'] <= span['start'] and span['end'] <= t['end'] for t in members):
                raise ValueError('Quote outside its exchange turns')
            quoted_exchanges.add(eid)
        if quoted_exchanges != set(exchange_ids):
            raise ValueError('Every referenced exchange needs exact source evidence')
    return {'status': 'structurally_valid', 'finding_count': len(findings),
            'source_sha256': _hash(text), 'semantic_review': 'required',
            'boundary_review': index.get('boundary_review', 'unknown')}
