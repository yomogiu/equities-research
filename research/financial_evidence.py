"""Source-bound financial observations and a disposable, read-only SQLite query layer.

No company data belongs in this module. Numeric values are Decimal strings, never
binary floats. Parsing establishes provenance, not independent accounting review.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from html.parser import HTMLParser
from pathlib import Path

SCHEMA_VERSION = 1
METRICS = {
    'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax': 'revenue',
    'us-gaap:Revenues': 'revenue',
    'us-gaap:SalesRevenueNet': 'revenue',
    'us-gaap:GrossProfit': 'gross_profit',
    'us-gaap:OperatingIncomeLoss': 'operating_income',
    'us-gaap:NetIncomeLoss': 'net_income',
    'us-gaap:NetCashProvidedByUsedInOperatingActivities': 'operating_cash_flow',
    'us-gaap:PaymentsToAcquirePropertyPlantAndEquipment': 'capital_expenditure',
    'us-gaap:CashAndCashEquivalentsAtCarryingValue': 'cash_and_equivalents',
    'us-gaap:InventoryNet': 'inventory',
    'us-gaap:Assets': 'assets',
    'us-gaap:Liabilities': 'liabilities',
    'us-gaap:EarningsPerShareDiluted': 'diluted_eps',
    'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding': 'diluted_shares',
}
VOID = {'br', 'hr', 'img', 'meta', 'link', 'input', 'wbr', 'area', 'base', 'col', 'embed', 'param', 'source', 'track'}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def seal(value, field):
    result = dict(value)
    result.pop(field, None)
    result[field] = digest(canonical(result))
    return result


def _decimal(value):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError('A bounded decimal string is required')
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not parsed.is_finite() or abs(parsed.adjusted()) > 100:
        raise ValueError('Nonfinite or excessive numeric value')
    return parsed


class _Node:
    def __init__(self, tag, attrs, start=0, end=0):
        self.tag, self.attrs = tag, dict(attrs)
        self.start, self.end = start, end
        self.children = []
        self.parent = None

    def all(self, local):
        for child in self.children:
            if isinstance(child, _Node):
                if child.tag.split(':')[-1] == local:
                    yield child
                yield from child.all(local)

    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children
                       if not isinstance(c, _Node) or c.tag != 'ix:exclude')


class _Parser(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.root = _Node('root', [])
        self.stack = [self.root]
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', raw))
        self.raw = raw

    def absolute_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.absolute_offset()
        node = _Node(tag, attrs, start, start + len(self.get_starttag_text()))
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].end = self.raw.find('>', self.absolute_offset()) + 1
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _one_text(node, local):
    found = list(node.all(local))
    return found[0].text().strip() if len(found) == 1 else None


def _context(node):
    identifiers = list(node.all('identifier'))
    return {
        'id': node.attrs.get('id'),
        'entity': _one_text(node, 'identifier'),
        'entity_scheme': identifiers[0].attrs.get('scheme') if len(identifiers) == 1 else None,
        'start_date': _one_text(node, 'startdate'),
        'end_date': _one_text(node, 'enddate'),
        'instant': _one_text(node, 'instant'),
        'dimensions': sorted([
            {'dimension': n.attrs.get('dimension'), 'member': n.text().strip(), 'type': kind}
            for kind in ('explicitmember', 'typedmember') for n in node.all(kind)
        ], key=lambda d: canonical(d)),
    }


def _unit(node):
    divides = list(node.all('divide'))
    if divides:
        numerator = list(node.all('unitnumerator'))
        denominator = list(node.all('unitdenominator'))
        if len(numerator) != 1 or len(denominator) != 1:
            raise ValueError('Malformed divided unit')
        if not list(numerator[0].all('measure')) or not list(denominator[0].all('measure')):
            raise ValueError('Missing measure in divided unit')
        return {'id': node.attrs.get('id'),
                'numerator': sorted(n.text().strip() for n in numerator[0].all('measure')),
                'denominator': sorted(n.text().strip() for n in denominator[0].all('measure'))}
    return {'id': node.attrs.get('id'), 'numerator': sorted(n.text().strip() for n in node.all('measure')), 'denominator': []}


def _number(node):
    attrs = node.attrs
    if attrs.get('xsi:nil', '').lower() in ('true', '1'):
        return None
    if attrs.get('continuedat'):
        raise ValueError('Unsupported continued numeric fact')
    transform = attrs.get('format', '').split(':')[-1].lower()
    value = node.text().strip().replace('\u00a0', ' ')
    if transform in ('num-dot-decimal', 'numdotdecimal'):
        if not re.fullmatch(r'[+\-]?(?:\d{1,3}(?:[, ]\d{3})+|\d+)(?:\.\d+)?', value):
            raise ValueError('Invalid dot-decimal lexical value')
        value = value.replace(',', '').replace(' ', '')
    elif transform in ('num-comma-decimal', 'numcommadecimal'):
        if not re.fullmatch(r'[+\-]?(?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d+)?', value):
            raise ValueError('Invalid comma-decimal lexical value')
        value = value.replace('.', '').replace(' ', '').replace(',', '.')
    elif transform in ('zerodash', 'zero-dash'):
        if value not in ('-', '–', '—'):
            raise ValueError('Invalid zero-dash lexical value')
        value = '0'
    elif transform:
        raise ValueError('Unsupported numeric transformation: ' + transform)
    parsed = _decimal(value)
    scale = int(attrs.get('scale', '0'))
    if abs(scale) > 30:
        raise ValueError('Unsupported numeric scale')
    sign = attrs.get('sign', '')
    if sign not in ('', '-'):
        raise ValueError('Unsupported numeric sign')
    with localcontext() as arithmetic:
        arithmetic.prec = 256
        parsed = parsed.scaleb(scale) * (-1 if sign == '-' else 1)
    return str(_decimal(str(parsed)))


def _source(source):
    if not isinstance(source, dict) or not source.get('document_id'):
        raise ValueError('Source document_id required')
    for name in ('raw_sha256',):
        if not re.fullmatch('[0-9a-f]{64}', str(source.get(name, ''))):
            raise ValueError('Source raw_sha256 required')
    return dict(source)


def make_artifact(source, observations, gaps=None):
    return seal({'schema_version': SCHEMA_VERSION, 'source': _source(source),
                 'observations': observations, 'gaps': gaps or []}, 'artifact_sha256')


def extract_inline_xbrl_file(path, source):
    """Read and bind exact archived bytes before any parsing."""
    raw = Path(path).read_bytes()
    if digest(raw) != source.get('raw_sha256'):
        raise ValueError('Raw source hash mismatch')
    return extract_inline_xbrl(raw.decode('utf-8'), source)


def extract_inline_xbrl(raw_html: str, source: dict):
    """Parse numeric iXBRL without inferring quarter/year or silently coercing units.

    raw_sha256 binds the UTF-8 bytes of the exact supplied string. Decode source
    bytes deliberately before calling; never reserialize the HTML first.
    """
    source = _source(source)
    if digest(raw_html.encode('utf-8')) != source['raw_sha256']:
        raise ValueError('Raw source hash mismatch')
    parser = _Parser(raw_html)
    parser.feed(raw_html)
    parser.close()
    contexts, units, ambiguous, gaps = {}, {}, set(), []
    for kind, lookup, convert in [('context', contexts, _context), ('unit', units, _unit)]:
        for node in parser.root.all(kind):
            key = node.attrs.get('id')
            if not key or (kind, key) in ambiguous:
                continue
            if key in lookup:
                ambiguous.add((kind, key))
                del lookup[key]
                gaps.append({'reason': 'Duplicate ' + kind + ' ID', 'id': key})
                continue
            try:
                lookup[key] = convert(node)
            except ValueError as exc:
                gaps.append({'reason': str(exc), 'id': key})
    observations = []
    for node in parser.root.all('fraction'):
        if node.tag == 'ix:fraction':
            gaps.append({'reason': 'Unsupported inline fraction', 'start': node.start})
    for node in parser.root.all('nonfraction'):
        if node.tag != 'ix:nonfraction':
            continue
        attrs = node.attrs
        try:
            context = contexts.get(attrs.get('contextref'))
            unit = units.get(attrs.get('unitref'))
            if not context or not context['entity']:
                raise ValueError('Missing or ambiguous reporting context')
            instant, start, end = context['instant'], context['start_date'], context['end_date']
            if not ((instant and not start and not end) or (start and end and not instant)):
                raise ValueError('Missing or ambiguous reporting dates')
            for reporting_date in (instant, start, end):
                if reporting_date:
                    date.fromisoformat(reporting_date)
            if start and end and start > end:
                raise ValueError('Reporting duration ends before it starts')
            if source.get('entity_identifier') and context['entity'] != source['entity_identifier']:
                raise ValueError('Reporting entity does not match source manifest')
            if not unit or not unit['numerator']:
                raise ValueError('Missing or ambiguous unit')
            concept = attrs.get('name')
            if not concept:
                raise ValueError('Missing taxonomy concept')
            value = _number(node)
            record = {'concept': concept, 'canonical_metric': METRICS.get(concept),
                      'value': value, 'nil': value is None, 'context': context, 'unit': unit,
                      'decimals': attrs.get('decimals'), 'scale': attrs.get('scale', '0'),
                      'sign': attrs.get('sign', ''), 'format': attrs.get('format'),
                      'status': 'extracted', 'method': 'inline_xbrl',
                      'source_document_id': source['document_id'], 'source_raw_sha256': source['raw_sha256'],
                      'support': {'start': node.start, 'end': node.end, 'offset_unit': 'unicode_codepoint',
                                  'raw_span_sha256': digest(raw_html[node.start:node.end].encode()),
                                  'display_text': node.text().strip()}}
            ancestor = node.parent
            while ancestor is not None and ancestor.tag != 'tr':
                ancestor = ancestor.parent
            if ancestor is not None:
                row_text = ancestor.text().strip()
                record['support']['table_row'] = {
                    'start': ancestor.start, 'end': ancestor.end,
                    'text': row_text[:1200], 'truncated': len(row_text) > 1200,
                    'raw_span_sha256': digest(raw_html[ancestor.start:ancestor.end].encode())}
            record['observation_id'] = digest(canonical(record))
            observations.append(record)
        except (ValueError, InvalidOperation) as exc:
            gaps.append({'reason': str(exc), 'concept': attrs.get('name'), 'start': node.start})
    return make_artifact(source, observations, gaps)


def propose_fact(text, source, *, concept, value, context, unit, quote, start):
    """Construct a proposed fallback observation; exact support is not approval."""
    source = _source(source)
    if digest(text.encode()) != source.get('text_sha256'):
        raise ValueError('Text source hash mismatch')
    if not quote or not isinstance(start, int) or start < 0 or text[start:start + len(quote)] != quote:
        raise ValueError('Fallback requires exact source support')
    value = str(_decimal(value))
    record = {'concept': concept, 'canonical_metric': METRICS.get(concept), 'value': value,
              'nil': False, 'context': context, 'unit': unit, 'status': 'proposed',
              'method': 'manual_proposal', 'source_document_id': source['document_id'],
              'source_raw_sha256': source['raw_sha256'],
              'support': {'start': start, 'end': start + len(quote), 'quote': quote,
                          'text_sha256': source['text_sha256'], 'offset_unit': 'unicode_codepoint'}}
    record['observation_id'] = digest(canonical(record))
    return record


def validate_artifact(artifact, trusted_sources, *, html_table_inputs=None):
    """Require caller-owned source bindings, stable record hashes and finite values."""
    if artifact.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported financial artifact version')
    source = _source(artifact['source'])
    trusted = trusted_sources.get(source['document_id'])
    if not trusted or any(source.get(k) != trusted.get(k) for k in ('raw_sha256', 'text_sha256') if k in source or k in trusted):
        raise ValueError('Untrusted or stale source binding')
    if seal(artifact, 'artifact_sha256')['artifact_sha256'] != artifact.get('artifact_sha256'):
        raise ValueError('Financial artifact hash mismatch')
    if 'html_table_review' in artifact or any(o.get('method') == 'reviewed_html_table' for o in artifact['observations']):
        from . import financial_html_tables
        if (source.get('issuer_id') != trusted.get('issuer_id') or html_table_inputs is None
                or financial_html_tables.extract(*html_table_inputs) != artifact):
            raise ValueError('Reviewed HTML artifact differs from independently authorized source replay')
    seen = set()
    for observation in artifact['observations']:
        obs_id = observation.get('observation_id')
        if seal(observation, 'observation_id')['observation_id'] != obs_id or obs_id in seen:
            raise ValueError('Invalid or duplicated observation hash')
        seen.add(obs_id)
        if observation.get('source_document_id') != source['document_id'] or observation.get('source_raw_sha256') != source['raw_sha256']:
            raise ValueError('Observation source mismatch')
        if observation.get('status') not in ('extracted', 'proposed'):
            raise ValueError('Independent review cannot be self-certified')
        if observation['value'] is not None:
            if observation.get('nil'):
                raise ValueError('Nil fact cannot have a numeric value')
            _decimal(observation['value'])
        elif not observation.get('nil'):
            raise ValueError('Missing nil status')
        if not observation.get('concept') or not observation.get('context') or not observation.get('unit'):
            raise ValueError('Incomplete financial provenance')
        support = observation.get('support', {})
        if not isinstance(support.get('start'), int) or not isinstance(support.get('end'), int) or support['start'] < 0 or support['end'] <= support['start']:
            raise ValueError('Invalid evidence offsets')
        if observation.get('method') == 'manual_proposal':
            if observation['status'] != 'proposed' or not support.get('quote') or support.get('text_sha256') != source.get('text_sha256'):
                raise ValueError('Manual observations must retain proposed status and text evidence')
            if support['end'] - support['start'] != len(support['quote']):
                raise ValueError('Manual quote and offsets disagree')
        elif observation.get('method') in ('inline_xbrl', 'reviewed_html_table'):
            if observation['status'] != 'extracted' or not re.fullmatch('[0-9a-f]{64}', str(support.get('raw_span_sha256', ''))):
                raise ValueError('Invalid inline evidence')
        else:
            raise ValueError('Unsupported extraction method')
    return artifact


def rebuild_database(db_path, artifacts, trusted_sources):
    """Atomically replace a disposable database only after all inputs validate."""
    artifacts = list(artifacts)
    for artifact in artifacts:
        validate_artifact(artifact, trusted_sources)
    destination = Path(db_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + '.', suffix='.tmp', dir=destination.parent)
    os.close(fd)
    count = 0
    try:
        with sqlite3.connect(temporary) as connection:
            connection.execute('CREATE TABLE facts (observation_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, concept TEXT NOT NULL, metric TEXT, period_end TEXT, context_id TEXT, status TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, record_json TEXT NOT NULL)')
            connection.execute('CREATE INDEX facts_lookup ON facts(concept,period_end,context_id)')
            for artifact in artifacts:
                for record in artifact['observations']:
                    context = record['context']
                    connection.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?)', (
                        record['observation_id'], artifact['source']['document_id'], record['concept'], record.get('canonical_metric'),
                        context.get('end_date') or context.get('instant'), context.get('id'), record['status'],
                        artifact['artifact_sha256'], canonical(record).decode()))
                    count += 1
            connection.execute('CREATE TABLE metadata (manifest_json TEXT NOT NULL)')
            manifest = {'schema_version': SCHEMA_VERSION, 'artifacts': sorted(a['artifact_sha256'] for a in artifacts), 'trusted_sources': trusted_sources}
            connection.execute('INSERT INTO metadata VALUES(?)', (canonical(manifest).decode(),))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'observations': count, 'artifacts': len(artifacts), 'database': str(destination)}


def query_facts(db_path, *, concept=None, period_end=None, context_id=None, document_id=None, include_proposed=False, limit=100):
    """Bounded parameterized queries. Proposed fallback facts are excluded by default."""
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('Query limit must be between 1 and 1000')
    clauses, parameters = [], []
    for key, value in [('concept', concept), ('period_end', period_end), ('context_id', context_id), ('document_id', document_id)]:
        if value is not None:
            clauses.append(key + '=?')
            parameters.append(value)
    if not include_proposed:
        clauses.append("status='extracted'")
    sql = 'SELECT record_json, artifact_sha256 FROM facts' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY document_id,context_id,observation_id LIMIT ?'
    uri = Path(db_path).resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        return [{**json.loads(row[0]), 'artifact_sha256': row[1]} for row in connection.execute(sql, parameters + [limit])]
