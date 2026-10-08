"""Opt-in extraction from independently reviewed, exact HTML cell profiles.

This adapter discovers no tables, infers no reporting metadata and launches no
models. The caller reserves the original source and distinct author/reviewer
identities. A profile selects exact cells and source evidence for its semantics;
code copies the source numbers. Profile approval is not report approval.
"""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
import re

from . import financial_evidence as financial
from .reviewed_transcript_index import _json

VERSION = 'reviewed-html-financial-v1'
METHOD = 'reviewed_html_table'
SOURCE_KEYS = ('document_id', 'raw_sha256', 'text_sha256', 'issuer_id')


def require(value, message):
    if not value:
        raise ValueError(message)


def fields(value, names, label):
    require(isinstance(value, dict) and set(value) == set(names), 'Exact ' + label + ' fields required')


def _span(raw, value):
    fields(value, ('start', 'end', 'raw_span_sha256'), 'source span')
    a, b = value['start'], value['end']
    require(type(a) is int and type(b) is int and 0 <= a < b <= len(raw), 'Invalid original source offsets')
    require(financial.digest(raw[a:b].encode()) == value['raw_span_sha256'], 'Original source span changed')
    return a, b


def _context(value, source):
    fields(value, ('entity', 'entity_scheme', 'start_date', 'end_date', 'instant', 'dimensions'), 'reporting context')
    require(value['entity'] == source['issuer_id'] and value['entity_scheme'] == 'qualified_packet_issuer_id',
            'Context must retain qualified source issuer identity')
    start, end, instant = value['start_date'], value['end_date'], value['instant']
    require((isinstance(instant, str) and start is None and end is None) or
            (instant is None and isinstance(start, str) and isinstance(end, str)), 'Exact instant or duration required')
    for text in (start, end, instant):
        if text is not None:
            require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', text) is not None, 'ISO reporting dates required')
            date.fromisoformat(text)
    require(not start or start <= end, 'Reversed financial duration')
    dims = value['dimensions']
    require(isinstance(dims, list) and len(dims) <= 20, 'Bounded source dimensions required')
    for dim in dims:
        fields(dim, ('dimension', 'member', 'type'), 'dimension')
        require(dim['type'] in ('explicitmember', 'typedmember') and
                all(isinstance(dim[k], str) and dim[k].strip() for k in ('dimension', 'member')), 'Invalid source dimension')
    require(len({d['dimension'] for d in dims}) == len(dims), 'Duplicate dimension axis')


def _unit(value):
    fields(value, ('numerator', 'denominator'), 'unit')
    for key in value:
        require(isinstance(value[key], list) and len(value[key]) <= 8 and
                all(isinstance(v, str) and re.fullmatch(r'[A-Za-z][\w.-]*:[A-Za-z][\w.-]*', v) for v in value[key]),
                'Exact source unit measures required')
    require(bool(value['numerator']), 'Unit numerator required')


def _number(text, scale):
    """Only explicit US-style numeric cells; ambiguous/dash/blank stay gaps."""
    require(type(scale) is int and -9 <= scale <= 12, 'Bounded reviewed decimal scale required')
    text = text.strip().replace('\u2212', '-')
    # Whitespace at cell boundaries is benign; whitespace inside digits is not.
    text = re.sub(r'^([$€£¥])\s*', '', text)
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1].strip()
    require(re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', text) is not None,
            'Ambiguous numeric cell; blanks, dashes, percentages and footnotes require a different explicit profile')
    require(not negative or not text.startswith('-'), 'Duplicate negative sign')
    value = financial._decimal(text.replace(',', ''))
    if negative:
        value = value.copy_negate()
    with localcontext() as ctx:
        ctx.prec = max(50, len(value.as_tuple().digits) + abs(scale) + 2)
        value *= Decimal(10) ** scale
    return str(financial._decimal(str(value)))


def extract(raw_bytes, source, profile_bytes, review_bytes, authorization):
    """Return source-bound observations; all arguments are caller-owned inputs."""
    require(isinstance(raw_bytes, bytes), 'Original UTF-8 bytes required')
    raw = raw_bytes.decode('utf-8')
    identity = {k: source.get(k) for k in SOURCE_KEYS}
    require(all(isinstance(v, str) and v for v in identity.values()), 'Complete financial source identity required')
    require(all(re.fullmatch('[0-9a-f]{64}', identity[k]) for k in ('raw_sha256', 'text_sha256')), 'Exact source hashes required')
    require(financial.digest(raw_bytes) == identity['raw_sha256'], 'Original source hash mismatch')
    fields(authorization, ('version', 'enabled', 'source', 'profile_sha256', 'review_sha256', 'author_id', 'reviewer_id'), 'adapter authorization')
    require(authorization['version'] == VERSION and authorization['enabled'] is True and authorization['source'] == identity,
            'Explicit original-source adapter authorization required')
    author, reviewer = authorization['author_id'], authorization['reviewer_id']
    require(all(isinstance(x, str) and x.strip() for x in (author, reviewer)) and author != reviewer,
            'Distinct authorized profile author and reviewer required')
    for key, value in (('profile_sha256', profile_bytes), ('review_sha256', review_bytes)):
        require(isinstance(value, bytes) and financial.digest(value) == authorization[key], 'Authorized adapter artifact changed')
    profile, review = _json(profile_bytes), _json(review_bytes)
    fields(profile, ('version', 'source', 'author_id', 'observations'), 'financial profile')
    fields(review, ('version', 'source', 'profile_sha256', 'author_id', 'reviewer_id', 'verdict', 'decisions'), 'profile review')
    require(profile['version'] == review['version'] == VERSION and profile['source'] == review['source'] == identity,
            'Profile/review source mismatch')
    require(profile['author_id'] == review['author_id'] == author and review['reviewer_id'] == reviewer and
            review['profile_sha256'] == authorization['profile_sha256'] and review['verdict'] == 'pass_profile_only',
            'Independent exact-profile approval required')
    rows, decisions = profile['observations'], review['decisions']
    require(isinstance(rows, list) and 1 <= len(rows) <= 5000 and isinstance(decisions, list), 'Bounded reviewed observations required')
    require(all(isinstance(r, dict) and isinstance(r.get('key'), str) and r['key'].strip() for r in rows), 'Observation keys required')
    keys = [r['key'] for r in rows]
    require(len(set(keys)) == len(keys), 'Duplicate profile key')
    for decision in decisions:
        fields(decision, ('key', 'verdict', 'observation_sha256'), 'observation decision')
    require(len(decisions) == len(rows) and {d['key'] for d in decisions} == set(keys), 'Every observation needs one independent decision')
    approved = {d['key']: d for d in decisions}
    parser = financial._Parser(raw)
    parser.feed(raw); parser.close()
    nodes = {(n.start, n.end): n for tag in ('table', 'tr', 'td', 'th') for n in parser.root.all(tag)}
    observations, selected, bases = [], set(), {}

    def element(span, tag):
        pos = _span(raw, span)
        require(pos in nodes and nodes[pos].tag in tag, 'Profile must select complete original HTML elements')
        return nodes[pos]

    for row in rows:
        fields(row, ('key', 'concept', 'context', 'unit', 'scale', 'accounting_basis', 'table', 'row',
                     'label', 'value_cells', 'evidence'), 'profile observation')
        decision = approved[row['key']]
        require(decision['verdict'] == 'pass' and decision['observation_sha256'] == financial.digest(financial.canonical(row)),
                'Unapproved observation semantics')
        require(isinstance(row['concept'], str) and re.fullmatch(r'[A-Za-z][\w.-]*:[A-Za-z][\w.-]*', row['concept']), 'Explicit reviewed concept required')
        require(isinstance(row['accounting_basis'], str) and 0 < len(row['accounting_basis']) <= 160, 'Explicit accounting basis required')
        _context(row['context'], source); _unit(row['unit'])
        metric = financial.canonical([row['concept'], row['context']['entity'], row['context']['entity_scheme'],
                                      sorted(row['context']['dimensions'], key=financial.canonical), row['unit']])
        require(metric not in bases or bases[metric] == row['accounting_basis'],
                'Different accounting bases require distinct source dimensions or concepts')
        bases[metric] = row['accounting_basis']
        table, tr, label = element(row['table'], {'table'}), element(row['row'], {'tr'}), element(row['label'], {'td', 'th'})
        require(tr.parent is not None and label.parent is tr, 'Label must belong to selected source row')
        ancestor = tr.parent
        while ancestor is not None and ancestor.tag != 'table':
            ancestor = ancestor.parent
        require(ancestor is table, 'Row must belong to selected source table')
        cells = row['value_cells']
        require(isinstance(cells, list) and 1 <= len(cells) <= 4, 'One bounded original numeric cell group required')
        values = [element(s, {'td', 'th'}) for s in cells]
        require(all(n.parent is tr and n is not label for n in values), 'Numeric cells must be distinct from label and in same row')
        positions = [(n.start, n.end) for n in values]
        require(positions == sorted(set(positions)) and not selected.intersection(positions), 'Duplicate or unordered original value cells')
        siblings = [n for n in tr.children if isinstance(n, financial._Node) and n.tag in ('td', 'th')]
        require(siblings[siblings.index(values[0]):siblings.index(values[-1])+1] == values, 'Numeric cell group must be contiguous')
        selected.update(positions)
        require(not any(list(n.all('table')) or list(n.all('sup')) for n in values), 'Nested tables and footnoted numeric cells require explicit review outside this adapter')
        # Concatenation handles parentheses/currency split by source layout cells;
        # a multi-value group must still parse as one unambiguous number.
        texts = [n.text().strip() for n in values]
        require(sum(bool(re.search(r'\d', t)) for t in texts) == 1, 'Exactly one numeric cell in group required')
        value = _number(''.join(texts), row['scale'])
        fields(row['evidence'], ('period', 'unit', 'entity', 'basis'), 'semantic evidence')
        for kind, spans in row['evidence'].items():
            require(isinstance(spans, list) and 1 <= len(spans) <= 8, 'Exact ' + kind + ' evidence required')
            for span in spans:
                _span(raw, span)
        label_text = label.text().strip()
        require(bool(label_text), 'Original row label required')
        support = {'start': values[0].start, 'end': values[-1].end, 'offset_unit': 'unicode_codepoint',
                   'raw_span_sha256': financial.digest(raw[values[0].start:values[-1].end].encode()),
                   'display_text': ''.join(texts), 'source_label': label_text, 'label': copy.deepcopy(row['label']),
                   'table_row': {'start': tr.start, 'end': tr.end, 'text': tr.text().strip(), 'truncated': False,
                                 'raw_span_sha256': financial.digest(raw[tr.start:tr.end].encode())},
                   'semantic_evidence': copy.deepcopy(row['evidence']), 'table': copy.deepcopy(row['table'])}
        record = {'concept': row['concept'], 'canonical_metric': financial.METRICS.get(row['concept']), 'value': value,
                  'nil': False, 'context': copy.deepcopy(row['context']), 'unit': copy.deepcopy(row['unit']),
                  'decimals': None, 'scale': str(row['scale']), 'sign': '', 'format': None,
                  'accounting_basis': row['accounting_basis'], 'status': 'extracted', 'method': METHOD,
                  'source_document_id': source['document_id'], 'source_raw_sha256': source['raw_sha256'],
                  'support': support, 'profile_key': row['key']}
        record['observation_id'] = financial.digest(financial.canonical(record))
        observations.append(record)
    artifact = financial.make_artifact(source, observations)
    artifact['html_table_review'] = copy.deepcopy(authorization)
    return financial.seal(artifact, 'artifact_sha256')


def case_inputs(case, raw_bytes, source):
    """Load only explicitly selected, hash-bound artifacts; no sidecar discovery."""
    selection = case.get('financial_adapter')
    require(source.get('issuer_id') == case.get('issuer_id') and bool(case.get('issuer_id')), 'Adapter issuer differs from frozen packet case')
    fields(selection, ('authorization_path', 'profile_path', 'review_path'), 'case adapter selection')
    bound = {str(Path(r['path']).resolve()): r['sha256'] for r in case['artifacts']}
    contents = {}
    for key, path in selection.items():
        resolved = str(Path(path).resolve())
        require(resolved in bound, 'Adapter input not frozen in case')
        contents[key] = Path(resolved).read_bytes()
        require(financial.digest(contents[key]) == bound[resolved], 'Frozen adapter input changed')
    return (raw_bytes, source, contents['profile_path'], contents['review_path'], _json(contents['authorization_path']))
