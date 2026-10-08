"""Deterministic, source-bound input for the opt-in financial preparer.

Every observation, context, unit, gap and document ID remains in the inventory.
Document text is a declared selection, never represented as the complete filing.
Exact F/D expansions are bounded by rejection, not by truncating evidence.
"""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from . import earnings_compact_evidence as evidence

VERSION = 'financial-context-v1'
DISPLAY_CONTRACT = 'source-bound-financial-v1'
MAX_EXPANSION_IDS = 12
MAX_EXPANSION_CHARACTERS = 60000
MAX_CONTEXT_CHUNKS = 12
PREVIEW_CHARACTERS = 160
CUES = {
    'basis': r'\b(?:non[- ]GAAP|GAAP|IFRS|unaudited|reconciliation)\b',
    'comparability': r'\b(?:restat\w*|reclassif\w*|comparabil\w*|discontinued|fiscal year|fiscal quarter)\b',
    'cash': r'\b(?:cash flows?|capital expenditures?|cash conversion|working capital)\b',
    'commitments': r'\b(?:commitments?|purchase obligations?|guarantees?|covenants?|maturities)\b',
    'subsequent_events': r'\b(?:subsequent events?|after (?:the )?(?:quarter|period)[- ]end)\b',
}


def _packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _explicit_basis(label):
    """Only a single basis explicitly named in the exact label is assigned."""
    bases = []
    for positive in ('GAAP', 'IFRS'):
        negative = r'\bnon[-\s\u2010-\u2015]*(?:U\.?S\.?\s+)?' + positive + r'\b'
        if re.search(negative, label, re.I): bases.append('non-' + positive)
        remainder = re.sub(negative, '', label, flags=re.I)
        if re.search(r'\b' + positive + r'\b', remainder, re.I): bases.append(positive)
    return bases[0] if len(bases) == 1 else None


def _span(text, start, end):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ValueError('Invalid financial source span')
    return text[start:end]


class _Row(HTMLParser):
    """Read complete leading label cells; numeric boundaries come from markup."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.cell = None
        self.depth = 0
        self.invalid = False
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.depth += 1
            if self.depth != 1:
                self.invalid = True
        if tag in ('td', 'th'):
            if self.cell is not None:
                self.invalid = True
            self.cell = {'text': [], 'number': False}
        if tag == 'ix:exclude':
            self.skip += 1
        if self.cell is not None and tag in ('ix:nonfraction', 'ix:fraction'):
            self.cell['number'] = True
        if self.cell is not None and tag == 'br':
            self.cell['text'].append(' ')

    def handle_endtag(self, tag):
        if tag == 'ix:exclude':
            self.skip = max(0, self.skip - 1)
        if tag in ('td', 'th'):
            if self.cell is None:
                self.invalid = True
            else:
                self.cells.append(self.cell)
                self.cell = None
        if tag == 'tr':
            self.depth -= 1

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell['text'].append(data)

    def label(self):
        if self.invalid or self.cell is not None or self.depth or not self.cells:
            return ''
        parts = []
        for cell in self.cells:
            if cell['number']:
                label = ' '.join(parts).strip()
                return label if label and re.search(r'[A-Za-z]', label) else ''
            text = ' '.join(''.join(cell['text']).split())
            # Currency/parenthesis spacer cells belong to numeric columns.
            if text and not re.fullmatch(r'[\s$€£¥()+−–—,.*-]*', text):
                # An untagged number before the first tagged cell is ambiguous;
                # never incorporate it into the metric name.
                if re.fullmatch(r'[\s$€£¥()+−–—,.\d%-]+', text):
                    return ''
                parts.append(text)
        return ''


class _NarrativeBlocks(HTMLParser):
    """Bind inline facts to complete nearest paragraph/division source spans."""
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw = raw; self.lines = [0] + [m.end() for m in re.finditer('\n', raw)]
        self.stack, self.facts = [], {}

    def absolute_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'div'):
            self.stack.append({'tag': tag, 'start': self.absolute_offset(), 'end': None, 'numbers': 0})
        if tag in ('ix:nonfraction', 'ix:fraction'):
            for block in self.stack: block['numbers'] += 1
            if self.stack: self.facts[self.absolute_offset()] = self.stack[-1]

    def handle_endtag(self, tag):
        if tag in ('p', 'div'):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]['tag'] == tag:
                    self.stack[i]['end'] = self.raw.find('>', self.absolute_offset()) + 1
                    del self.stack[i:]
                    break


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts = []

    def handle_data(self, data): self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == 'br': self.parts.append(' ')


def _narrative_identity(obs, raw, blocks):
    """Narrow grammar for a direct availability statement, not label invention.

    The target must be the final numeric fact in its complete block, and its
    immediately trailing words must explicitly name availability under a credit
    agreement/facility. Earlier facts (for example zero borrowings) are retained
    in the evidence block but cannot be mistaken for this availability amount. Other
    narrative measures require a separate reviewed source-label mapping.
    """
    if obs['concept'] != 'us-gaap:LineOfCreditFacilityRemainingBorrowingCapacity':
        return None
    support = obs['support']; block = blocks.facts.get(support['start'])
    if not block or block['end'] is None or block['end'] < support['end']:
        return None
    tail_raw = raw[support['end']:block['end']]
    if re.search(r'<ix:(?:nonfraction|fraction)\b', tail_raw, re.I):
        return None
    tail = _Plain(); tail.feed(tail_raw); tail.close()
    text = ' '.join(''.join(tail.parts).split())
    match = re.fullmatch(r'(?:thousand|million|billion)?\s*(available under (?:the |our )?(?:[A-Za-z]+ )*credit (?:agreement|facility))\.?', text, re.I)
    if not match:
        return None
    return {'label': match.group(1), 'basis': None, 'label_origin': 'exact_source_phrase',
            'source': {'document_id': obs['source_document_id'], 'sha256': obs['source_sha256'],
                       'start': block['start'], 'end': block['end'],
                       'span_sha256': _digest(raw[block['start']:block['end']]), 'offset_unit': 'unicode_character'},
            'reason': None}


def source_identities(bundle, fact_ids=None):
    """Re-derive exact labels from bound raw rows, never from model labels.

    Whitespace is normalized for display; all other label characters survive.
    Missing/ambiguous rows remain explicit and cannot pass strict preflight.
    """
    wanted = None if fact_ids is None else set(fact_ids)
    observations = bundle['financial']['observations']
    if wanted is not None and not wanted <= {o['id'] for o in observations}:
        raise ValueError('Unknown financial source ID')
    sources = {(s['path'], s['sha256'], s['document_id']) for s in bundle['manifest']['sources']}
    cache, rows, result, narrative_blocks = {}, {}, {}, {}
    for obs in observations:
        if wanted is not None and obs['id'] not in wanted:
            continue
        identity = {'label': None, 'basis': None, 'label_origin': 'unresolved',
                    'reason': 'No unambiguous complete inline-XBRL row label; expand this F ID before selecting an alternative.'}
        support = obs.get('support', {})
        row = support.get('table_row')
        if obs.get('method') in ('inline_xbrl', 'reviewed_html_table'):
            binding = (obs['source_path'], obs['source_sha256'], obs['source_document_id'])
            if binding not in sources:
                raise ValueError('Financial source is not bound to the frozen manifest')
            if binding not in cache:
                raw = Path(binding[0]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != binding[1]:
                    raise ValueError('Financial raw source changed')
                cache[binding] = raw.decode('utf-8')
            raw = cache[binding]
            snippet = _span(raw, support['start'], support['end'])
            if _digest(snippet) != support.get('raw_span_sha256'):
                raise ValueError('Financial observation span changed')
            if not row:
                if obs['concept'] == 'us-gaap:LineOfCreditFacilityRemainingBorrowingCapacity':
                    if binding not in narrative_blocks:
                        parser = _NarrativeBlocks(raw); parser.feed(raw); parser.close()
                        narrative_blocks[binding] = parser
                    identity = _narrative_identity(obs, raw, narrative_blocks[binding]) or identity
                result[obs['id']] = deepcopy(identity)
                continue
            if not row['start'] <= support['start'] < support['end'] <= row['end']:
                raise ValueError('Financial observation lies outside its source row')
            row_raw = _span(raw, row['start'], row['end'])
            if _digest(row_raw) != row.get('raw_span_sha256'):
                raise ValueError('Financial source row changed')
            if obs.get('method') == 'reviewed_html_table':
                from . import financial_evidence
                label_span = support['label']
                label_raw = _span(raw, label_span['start'], label_span['end'])
                if (not row['start'] <= label_span['start'] < label_span['end'] <= row['end']
                        or _digest(label_raw) != label_span['raw_span_sha256']):
                    raise ValueError('Reviewed financial source label changed')
                label_parser = financial_evidence._Parser(label_raw)
                label_parser.feed(label_raw); label_parser.close()
                label = label_parser.root.text().strip()
                if label != support['source_label']:
                    raise ValueError('Reviewed financial source label differs')
                result[obs['id']] = {'label': ' '.join(label.split()), 'basis': obs['accounting_basis'],
                    'label_origin': 'exact_source_cells', 'reason': None,
                    'source': {'document_id': binding[2], 'sha256': binding[1], 'start': row['start'],
                               'end': row['end'], 'span_sha256': _digest(row_raw), 'offset_unit': 'unicode_character'}}
                continue
            key = (*binding, row['start'], row['end'])
            if key not in rows:
                parser = _Row(); parser.feed(row_raw); parser.close()
                label = parser.label()
                if re.fullmatch(r'(?:total|subtotal|other|net|balance)\s*[:;]?', label, re.I):
                    label = ''  # A generic row needs table/header interpretation.
                basis = _explicit_basis(label)
                rows[key] = {'label': label or None, 'basis': basis,
                    'label_origin': 'exact_source_cells' if label else 'unresolved',
                    'source': {'document_id': binding[2], 'sha256': binding[1],
                               'start': row['start'], 'end': row['end'],
                               'span_sha256': _digest(row_raw), 'offset_unit': 'unicode_character'},
                    'reason': None if label else identity['reason']}
            identity = rows[key]
        result[obs['id']] = deepcopy(identity)
    return result


def _documents(bundle):
    chunks = bundle['documents']['chunks']
    sources = {(s['path'], s['sha256'], s['document_id']) for s in bundle['manifest']['sources']}
    cache, entries, full = {}, [], {}
    for chunk in chunks:
        binding = (chunk['path'], chunk['sha256'], chunk['document_id'])
        if binding not in sources:
            raise ValueError('Document is not bound to the frozen manifest')
        if binding not in cache:
            raw = Path(binding[0]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != binding[1]:
                raise ValueError('Financial context document changed')
            cache[binding] = raw.decode('utf-8')
        text = _span(cache[binding], chunk['start'], chunk['end'])
        if _digest(text) != chunk['span_sha256']:
            raise ValueError('Financial document chunk changed')
        # Inspect across chunk boundaries to preserve topic discovery there.
        window = cache[binding][max(0, chunk['start'] - 80):chunk['end'] + 80]
        cues = [name for name, pattern in CUES.items() if re.search(pattern, window, re.I)]
        preview = text[:PREVIEW_CHARACTERS]
        entries.append({**{k: chunk[k] for k in ('id', 'document_id', 'kind', 'sha256', 'start', 'end', 'span_sha256')},
                        'cues': cues, 'preview': preview,
                        'preview_end': chunk['start'] + len(preview),
                        'preview_truncated': len(preview) < len(text)})
        full[chunk['id']] = text
    return entries, full


def financial_role_payload(bundle):
    """Complete fact inventory + explicitly selected complete context chunks."""
    facts = bundle['financial']
    identities = source_identities(bundle)
    identity_keys, identity_rows, observations = {}, {}, []
    source_keys, sources, concept_keys, concepts = {}, {}, {}, {}
    def source_id(document_id, sha256):
        key = (document_id, sha256)
        if key not in source_keys:
            sid = 'S%03d' % (len(source_keys) + 1)
            source_keys[key] = sid
            sources[sid] = {'document_id': document_id, 'sha256': sha256}
        return source_keys[key]
    columns = ['id', 'concept_id', 'value', 'context_id', 'unit_id', 'status', 'nil', 'decimals', 'source_row_id']
    for obs in facts['observations']:
        identity = identities[obs['id']]
        key = _packed(identity)
        if key not in identity_keys:
            rid = 'R%04d' % (len(identity_keys) + 1)
            identity_keys[key] = rid
            src = identity.get('source')
            identity_rows[rid] = [identity['label'], identity['basis'], identity['label_origin'],
                source_id(src['document_id'], src['sha256']) if src else None,
                src['start'] if src else None, src['end'] if src else None]
        concept = (obs['concept'], obs.get('canonical_metric'))
        if concept not in concept_keys:
            cid = 'M%03d' % (len(concept_keys) + 1)
            concept_keys[concept] = cid
            concepts[cid] = {'concept': concept[0], 'canonical_metric': concept[1]}
        observations.append([obs['id'], concept_keys[concept]] + [obs.get(k) for k in columns[2:-1]] + [identity_keys[key]])
    # Contexts retain every original field; repeated entities/dimensions are
    # dictionaries, with explicit references rather than repeated long strings.
    contexts, dimension_keys, dimension_sets, entity_keys, entities = {}, {}, {}, {}, {}
    for cid, original in facts['contexts'].items():
        dimensions = _packed(original['dimensions'])
        if dimensions not in dimension_keys:
            did = 'DM%03d' % (len(dimension_keys) + 1)
            dimension_keys[dimensions] = did; dimension_sets[did] = deepcopy(original['dimensions'])
        entity = _packed([original['entity'], original.get('entity_scheme')])
        if entity not in entity_keys:
            eid = 'E%03d' % (len(entity_keys) + 1)
            entity_keys[entity] = eid; entities[eid] = {'entity': original['entity'], 'entity_scheme': original.get('entity_scheme')}
        contexts[cid] = {k: deepcopy(v) for k, v in original.items() if k not in ('dimensions', 'entity', 'entity_scheme')}
        contexts[cid].update(dimensions_id=dimension_keys[dimensions], entity_id=entity_keys[entity])
    documents, full = _documents(bundle)
    # Round-robin topics before filling remaining slots avoids cash/basis alone
    # crowding subsequent events and commitments out of the initial selection.
    selected = []
    buckets = [[d['id'] for d in documents if cue in d['cues']] for cue in CUES]
    for ordinal in range(max(map(len, buckets), default=0)):
        for bucket in buckets:
            if ordinal < len(bucket) and bucket[ordinal] not in selected and len(selected) < MAX_CONTEXT_CHUNKS:
                selected.append(bucket[ordinal])
    document_columns = ['id', 'source_id', 'kind', 'start', 'end', 'cues', 'preview', 'preview_end', 'preview_truncated']
    document_rows = [[d['id'], source_id(d['document_id'], d['sha256'])] + [d[k] for k in document_columns[2:]] for d in documents]
    return {'version': VERSION, 'sources': sources, 'financial_observations': {
        'columns': columns, 'rows': observations, 'concepts': concepts, 'contexts': contexts,
        'entities': entities, 'dimension_sets': dimension_sets,
        'units': deepcopy(facts['units']), 'gaps': deepcopy(facts.get('gaps', [])),
        'source_row_columns': ['label', 'basis', 'label_origin', 'source_id', 'start', 'end'],
        'source_rows': identity_rows, 'total_observations': len(observations), 'omitted_observation_ids': []},
        'document_inventory': {'columns': document_columns, 'rows': document_rows},
        'complete_context_chunks': [{'id': i, 'text': full[i]} for i in selected],
        'deferred_document_ids': [d['id'] for d in documents if d['id'] not in selected],
        'selection_rule': {'cue_patterns': CUES, 'max_complete_chunks': MAX_CONTEXT_CHUNKS,
                           'ordering': 'topic round-robin, frozen document order'},
        'expansion_contract': {'max_ids': MAX_EXPANSION_IDS, 'max_characters': MAX_EXPANSION_CHARACTERS,
            'allowed_ids': [o['id'] for o in facts['observations']] + [d['id'] for d in documents]},
        'notice': 'All observations are inventoried, including unmapped/proposed/nil facts. Dictionary references factor repeated concepts, entities, dimensions and sources; dates/values/qualifiers are unchanged. Source spans use Unicode character offsets. Parsing is not independent approval. Document previews and topic cues are discovery aids, not complete evidence. Only complete_context_chunks or explicit expansions may support document claims. Unresolved row labels cannot be rendered: request F/D IDs to inspect ambiguity and select unambiguous evidence. Never infer GAAP from taxonomy or preparer labels. An absent cue is not evidence of absence.'}


def expand(bundle, source_ids):
    """Resolve a bounded explicit source request without shortening any span."""
    allowed = {o['id'] for o in bundle['financial']['observations']} | {d['id'] for d in bundle['documents']['chunks']}
    if (not isinstance(source_ids, list) or not 1 <= len(source_ids) <= MAX_EXPANSION_IDS
            or any(not isinstance(i, str) for i in source_ids)
            or len(set(source_ids)) != len(source_ids) or not set(source_ids) <= allowed):
        raise ValueError('Expansion requires 1–12 distinct known financial/document IDs')
    result = evidence.source_slices(bundle['manifest'], source_ids)
    identities = source_identities(bundle, [i for i in source_ids if i.startswith('F')])
    for entry in result:
        identity = identities.get(entry['id'])
        if identity and identity['label_origin'] == 'exact_source_phrase':
            obs = next(o for o in bundle['financial']['observations'] if o['id'] == entry['id'])
            raw = Path(obs['source_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != obs['source_sha256']:
                raise ValueError('Financial raw source changed during expansion')
            src = identity['source']; text = _span(raw.decode('utf-8'), src['start'], src['end'])
            if _digest(text) != src['span_sha256']:
                raise ValueError('Financial label source changed during expansion')
            entry['label_source'] = {**src, 'text': text, 'label': identity['label']}
    if len(_packed(result)) > MAX_EXPANSION_CHARACTERS:
        raise ValueError('Financial expansion exceeds character budget; request fewer source IDs')
    return result


def bind(financial, bundle):
    """Attach only the code-owned opt-in contract and validate before review."""
    if '_display_contract' in financial and financial['_display_contract'] != DISPLAY_CONTRACT:
        raise ValueError('Unsupported financial display contract')
    result = deepcopy(financial)
    result['_display_contract'] = DISPLAY_CONTRACT
    preflight(result, bundle)
    return result


def preflight(financial, bundle):
    from . import earnings_financial_display as display
    if financial.get('_display_contract') != DISPLAY_CONTRACT:
        raise ValueError('Source-bound financial display contract required')
    # Rendering performs source-label, value, unit, period, dimension and
    # conflicting-comparison checks using the original frozen observations.
    return display.build(financial, bundle)
