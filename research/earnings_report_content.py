"""Shared report schemas, period resolution and rendering. No workflow state."""
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import re
from . import earnings_compact_evidence as evidence
from . import earnings_financial_analysis_report as finance
from . import earnings_runtime_common as storage
from . import earnings_markdown_render as markdown
from . import earnings_financial_selection as selection
from . import earnings_financial_context as financial_context
from . import earnings_valuation_inventory as valuation_inventory
from . import earnings_report_contract as report_contract
VERSION = 'single-author-report-v2'
SECTIONS = {'demand': 'Demand', 'earnings': 'Profits and margins',
            'cash': 'Cash and financial capacity', 'outlook': 'Outlook and earnings valuation'}

CRITERIA = ('source_accuracy', 'qa_fidelity', 'financial_context', 'reasoning',
            'counterevidence', 'coverage', 'materiality', 'concise_writing')

MODELS = {'analysis': ['gpt-6.1-sol', 'medium'], 'review': ['gpt-6.1-sol', 'medium'],
          'correction': ['gpt-6-luna', 'max']}

def require(condition, message):
    if not condition:
        raise ValueError(message)

_DATE_REGISTRIES = {
    'http://www.xbrl.org/inlineXBRL/transformation/2011-07-31',
    'http://www.xbrl.org/inlineXBRL/transformation/2015-02-26',
    'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12',
    'http://www.xbrl.org/inlineXBRL/transformation/2022-02-16',
}

_MONTH_NAMES = ('January February March April May June July August September October November December').split()

_MONTHS = {spelling.lower():number for number, name in enumerate(_MONTH_NAMES, 1)
           for spelling in (name, name[:3])}

_DATE_FORMATS = {
    'date-monthname-day-year-en':'mdy-name', 'datemonthdayyearen':'mdy-name',
    'date-day-monthname-year-en':'dmy-name', 'datedaymonthyearen':'dmy-name',
    'date-month-day-year':'mdy', 'datemonthdayyear':'mdy',
    'date-day-month-year':'dmy', 'datedaymonthyear':'dmy',
    'date-year-month-day':'ymd', 'dateyearmonthday':'ymd',
}

def _date_transform(text, declared_format, namespace):
    """Apply declared XBRL date ordering, never infer locale from date text.

    A strict supported subset of the registry is accepted. Unknown transforms,
    continued/excluded facts and more complex spellings require explicit source
    configuration. Registry 4: section 4.58 and the corresponding numeric/date
    functions define short years as 2000–2099 (not a sliding century window).
    https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2020-02-12/inlineXBRL-transformationRegistry-REC-2020-02-12.html
    """
    text = ' '.join(text.split())
    if not declared_format:
        require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text) is not None,
                'Non-ISO DocumentPeriodEndDate requires a declared supported XBRL date transform')
        return date.fromisoformat(text).isoformat()
    require(namespace in _DATE_REGISTRIES, 'Unknown DocumentPeriodEndDate transformation namespace')
    name = declared_format.split(':')[-1]
    order = _DATE_FORMATS.get(name)
    require(order is not None, 'Unsupported declared DocumentPeriodEndDate transform: '+name)
    # Deliberately bounded separators prevent silently accepting additional dates
    # or prose. Unicode whitespace (including NBSP) was normalized above.
    separator = r'[\s,./-]+'
    year = r'([0-9]{4}|[0-9]{1,2})'
    day = r'([0-9]{1,2})(?:st|nd|rd|th)?'
    if order.endswith('-name'):
        month = '('+'|'.join(sorted(_MONTHS, key=len, reverse=True))+r')\.?'
        pattern = month+separator+day+separator+year if order == 'mdy-name' else day+separator+month+separator+year
    else:
        number = r'([0-9]{1,2})'
        pattern = year+separator+number+separator+number if order == 'ymd' else number+separator+number+separator+year
    match = re.fullmatch(pattern, text, flags=re.I)
    require(match is not None, 'DocumentPeriodEndDate does not match its declared XBRL transform')
    first, second, third = match.groups()
    if order == 'mdy-name': month_number, day_number, year_text = _MONTHS[first.lower()], int(second), third
    elif order == 'dmy-name': month_number, day_number, year_text = _MONTHS[second.lower()], int(first), third
    elif order == 'mdy': month_number, day_number, year_text = int(first), int(second), third
    elif order == 'dmy': month_number, day_number, year_text = int(second), int(first), third
    else: month_number, day_number, year_text = int(second), int(third), first
    year_number = int(year_text) + (2000 if len(year_text) < 4 else 0)
    return date(year_number, month_number, day_number).isoformat()

class _PeriodEnd(HTMLParser):
    _VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(); self.values = []; self.depth = 0; self.parts = []
        self.namespaces = []; self.fact_format = None; self.fact_namespace = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        inherited = dict(self.namespaces[-1][1]) if self.namespaces else {}
        inherited.update({key[6:]:value for key, value in attrs.items() if key.startswith('xmlns:')})
        if tag not in self._VOID: self.namespaces.append((tag, inherited))
        if self.depth:
            require(tag != 'ix:exclude', 'Excluded DocumentPeriodEndDate text requires explicit configuration')
            if tag not in self._VOID: self.depth += 1
        elif attrs.get('name', '').lower() == 'dei:documentperiodenddate':
            require(tag.endswith(':nonnumeric'), 'DocumentPeriodEndDate must be an inline nonnumeric fact')
            require(not attrs.get('continuedat') and attrs.get('xsi:nil') not in ('true','1'),
                    'Continued or nil DocumentPeriodEndDate requires explicit configuration')
            self.depth = 1; self.parts = []
            self.fact_format = attrs.get('format')
            prefix = self.fact_format.split(':')[0] if self.fact_format and ':' in self.fact_format else ''
            self.fact_namespace = inherited.get(prefix)

    def handle_endtag(self, tag):
        if tag in self._VOID: return
        if self.depth:
            self.depth -= 1
            if not self.depth:
                self.values.append(_date_transform(''.join(self.parts), self.fact_format, self.fact_namespace))
        for position in range(len(self.namespaces)-1, -1, -1):
            if self.namespaces[position][0] == tag:
                del self.namespaces[position:]
                break

    def handle_data(self, data):
        if self.depth: self.parts.append(data)

def financial_configuration(bundle, explicit=None):
    """Resolve only an explicit configuration or an unambiguous filed quarter."""
    if explicit is not None:
        return finance.validate_configuration(explicit)
    source = bundle['financial']['source']
    raw = evidence._unique_source(bundle['manifest']['sources'], source['document_id'], source['raw_sha256'])
    require(storage.sha(raw['path']) == source['raw_sha256'], 'Original financial filing changed')
    parser = _PeriodEnd(); parser.feed(Path(raw['path']).read_text())
    ends = set(parser.values)
    require(len(ends) == 1, 'Explicit financial configuration required: no unique filed DocumentPeriodEndDate')
    end = ends.pop(); date.fromisoformat(end)
    candidates = set()
    for observation in bundle['financial']['observations']:
        if observation.get('status') != 'extracted' or observation.get('nil'):
            continue
        row = bundle['financial']['contexts'][observation['context_id']]
        start = row.get('start_date')
        if start and row.get('end_date') == end and not row.get('dimensions'):
            if 70 <= (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 <= 105:
                candidates.add(start)
    require(len(candidates) == 1, 'Explicit financial configuration required: ambiguous or absent consolidated fiscal quarter')
    return finance.configuration(candidates.pop(), end)

def _text(value, maximum=8000):
    require(isinstance(value, str) and value.strip() and len(value) <= maximum, 'Bounded nonempty text required')
    require('[^' not in value and not re.search(r'^\s*(?:\||#{1,6}\s|:::)', value, re.M), 'Narrative cannot inject tables, headings, references or renderer directives')
    return value

def _citations(value, known):
    require(isinstance(value, list) and value and len(value) == len(set(value)) and
            all(isinstance(x, str) and x in known for x in value), 'Known unique original-source citations required')

def cited(value):
    if isinstance(value, dict):
        result = set(value.get('citations', []))
        for key, child in value.items():
            if key != 'citations': result.update(cited(child))
        return result
    if isinstance(value, list):
        return set().union(*(cited(x) for x in value)) if value else set()
    return set()

def validate_analysis(value, known, exchange_ids):
    require(isinstance(value, dict) and set(value) in ({'title', 'opening', 'sections', 'qa', 'next_tests'}, {'title', 'opening', 'sections', 'qa', 'next_tests', 'report_support'}), 'Exact analysis fields required')
    _text(value['title'], 240)
    def paragraph(row, section=False):
        require(isinstance(row, dict) and (set(row) == {'text', 'citations'} or
                section and set(row) == {'heading', 'text', 'citations'}), 'Exact paragraph fields required')
        _text(row['text']); _citations(row['citations'], known)
        if 'heading' in row:
            _text(row['heading'], 180)
            require('\n' not in row['heading'], 'Section heading must be one line')
    paragraph(value['opening'])
    require(isinstance(value['sections'], dict) and set(value['sections']) == set(SECTIONS), 'All report sections required')
    for row in value['sections'].values(): paragraph(row, section=True)
    require(isinstance(value['qa'], list) and len(value['qa']) <= 8, 'At most eight material Q&A selections')
    require(value['qa'] or not exchange_ids, 'Select at least one material original Q&A exchange')
    selected = []
    for row in value['qa']:
        require(isinstance(row, dict) and set(row) == {'exchange_id', 'question', 'answer', 'assessment', 'citations'}, 'Exact Q&A fields required')
        require(row['exchange_id'] in exchange_ids, 'Q&A must bind an original exchange')
        for key in ('question', 'answer', 'assessment'): _text(row[key], 2500)
        _citations(row['citations'], known)
        require(row['exchange_id'] in row['citations'], 'Q&A must cite its original exchange')
        selected.append(row['exchange_id'])
    require(len(selected) == len(set(selected)), 'Duplicate Q&A selections')
    require(isinstance(value['next_tests'], list) and 1 <= len(value['next_tests']) <= 8, 'One to eight concrete next tests required')
    for row in value['next_tests']: paragraph(row)
    return value

def _reader_scope(scope):
    """Keep the cutoff and specific limitations, excluding preparer instructions."""
    require(isinstance(scope, list) and all(isinstance(note, str) for note in scope), 'Frozen scope notes must be plain text')
    internal = ('Historical event_update for the exact qualified packet',
                'Evidence is limited to the archived packet.',
                'Financial observations are deterministic extractions,',
                'Transcript speaker roles and Q&A boundaries are provisional.',
                'Historical earnings analysis from a fixed, qualified source snapshot;',
                'Call and report may disagree;', 'Public provider-hosted issuer report',
                'Q&A roles and boundaries are provisional;', 'Exact fiscal quarter boundaries',
                'Annual background, consensus and current valuation inputs')
    observations = [note for note in scope if note.startswith('Original source observation dates:')]
    dates = sorted(set(re.findall(r'\b\d{4}-\d{2}-\d{2}(?!\d)', ' '.join(observations))))
    result = []
    if dates:
        span = dates[0] if len(dates) == 1 else dates[0]+' to '+dates[-1]
        result.append('Sources observed '+span+'. This report covers the archived earnings materials; subsequent events are outside its scope.')
    for note in scope:
        if note.startswith('Freshly collected '):
            period=note.split()[2]
            result.append('Earnings update for '+period+'. Tables retain the dates and periods printed in the source materials.')
            continue
        if note.startswith('Report document basis:'):continue
        if note.startswith('PDF financial tables are verbatim'):
            result.append('Financial tables reproduce original reported rows where standardized comparisons are unavailable.')
            continue
        if note.startswith('Original-language financial report. Write English analysis;'):
            result.append('Analysis is in English; original financial table labels, units and reporting periods are retained.')
            continue
        if note.startswith('One qualified financial document and call collected;'):
            result.append('Sources comprise one financial report and the earnings call; separate releases and presentations were not collected.')
            continue
        if note.startswith(internal) or note in observations:
            continue
        cleaned = _text(' '.join(note.split()))
        if cleaned not in result: result.append(cleaned)
    return result or ['This report covers the archived earnings materials. A source observation cutoff was not recorded.']

def render_candidate(value, financial, manifest):
    tables = finance.sections(financial)
    if financial.get('reported_tables'):
        tables={key:[line for line in lines if not line.startswith('Normalized current-period comparisons unavailable:')]
                for key,lines in tables.items()}
    if financial.get('eps_validation') is not None:
        from . import earnings_eps_contract
        tables['earnings']=earnings_eps_contract.render(financial['eps_validation'])+tables.get('earnings',[])
    frozen = evidence.load_bundle(manifest)['manifest']
    scope = frozen.get('scope_notes', [])
    snapshot = _reader_scope(scope)
    def prose(row): return row['text'] + ' ' + markdown.refs(row['citations'])
    lines = ['# '+value['title'], '', prose(value['opening']), '',
             '## Source snapshot and scope', '', *snapshot, '']
    for name, title in SECTIONS.items():
        lines.extend(['## '+value['sections'][name].get('heading', title), '', *tables.get(name, []), prose(value['sections'][name]), ''])
    if 'report_support' in value:
        from . import earnings_report_contract
        lines.extend(earnings_report_contract.render(value['report_support'],value,manifest))
    if value['qa']:lines.extend(['## Earnings-call questions', ''])
    for row in value['qa']:
        lines.extend(['### '+row['question'], '', 'Management answer: '+row['answer'], '',
                      'Assessment: '+row['assessment']+' '+markdown.refs(row['citations']), ''])
    lines.extend(['## What to watch next', ''])
    lines.extend('- '+prose(row) for row in value['next_tests'])
    lines.extend(['', '## Source and calculation notes', '', *finance.notes(financial), '', '## Source references', ''])
    ids = sorted(set(re.findall(r'\[\^([A-Za-z0-9_-]+)\]', '\n'.join(lines))))
    records = {r['id']: r for r in evidence.source_slices(manifest, ids)}
    for identifier in ids:
        spans = records[identifier]['spans']
        origins = '; '.join(dict.fromkeys(str(s['document_id'])+' · characters '+str(s['start'])+'–'+str(s['end']) for s in spans))
        lines.append('[^'+identifier+']: '+origins)
    return '\n'.join(lines).rstrip()+'\n'

ANALYSIS_SCHEMA = ' including concise material Q&A analysis and concrete next tests, in a single object with exactly:\n{"title":"...","opening":{"text":"...","citations":["..."]},"sections":{"demand":{"heading":"concrete source-backed finding","text":"...","citations":["..."]},"earnings":{"heading":"concrete source-backed finding","text":"...","citations":["..."]},"cash":{"heading":"concrete source-backed finding","text":"...","citations":["..."]},"outlook":{"heading":"concrete source-backed finding","text":"...","citations":["..."]}},"qa":[{"exchange_id":"original exchange ID","question":"faithful question summary","answer":"faithful management answer summary","assessment":"what was answered, deferred or unsupported","citations":["same original exchange ID"]}],"next_tests":[{"text":"source-grounded test","citations":["..."]}]}\nEach section heading states a concrete source-backed finding; its paragraph citations support that heading. Every paragraph requires original citations. Select 1–8 material Q&A exchanges when exchanges exist; do not invent attribution. Use summaries rather than unverified direct quotations. Answer each expected question in the packet or explicitly state its missing source inputs. Distinguish QoQ/YoY, quarter/YTD, GAAP/adjusted, reported/derived and guidance/aspiration. Valuation is a dated matching annual/TTM/forward-annual earnings multiple only; disclose unavailable inputs. If prior review findings exist, address every one in the full replacement candidate, using the current deterministic table artifact. The controller may have rebuilt tables in response to a financial finding; treat the current tables as authoritative over older draft tables and do not reproduce stale gaps or values.\n'

def packet(bundle):
    inventory = selection.compact(bundle)
    if bundle.get('packet_inventory'):
        from . import earnings_packet_inventory
        tables=earnings_packet_inventory.compact(bundle['packet_inventory'])
        inventory['original_tables'] = {k:tables[k] for k in ('version','row_format','shared_text','tables','total_captured_tables')}
    # Full documents below replace discovery previews and duplicated excerpts.
    inventory.pop('documents'); inventory.pop('complete_original_chunks')
    financial_context._documents(bundle)  # Validate all original chunk bindings.
    # Serialize each original document once; chunks overlap in the source index.
    # SEC machine context prefixes are redundant with the complete fact inventory.
    documents=[];positions={};scopes=[]
    for chunk in bundle['documents']['chunks']:
        key=chunk['document_id']
        if key not in positions:
            original=Path(chunk['path']).read_bytes().decode('utf-8');start=0
            cover=re.search(r'United States\s+Securities and Exchange Commission',original,re.I)
            if cover and 'xbrli:' in original[:cover.start()] and not re.search(r'\s[A-Za-z]{3,}\s',original[:cover.start()]):
                start=cover.start()
            positions[key]=len(documents)
            documents.append({'id':key,'source_id':valuation_inventory.source_id(key),'kind':chunk['kind'],'start':start,'text':original[start:],
                'omitted_prefix':'XBRL machine contexts; all numerical observations retained' if start else None})
        if chunk['start']>=documents[positions[key]]['start']:
            scopes.append([chunk['id'],positions[key],chunk['start'],chunk['end']])
    transcript = Path(bundle['manifest']['transcript_path']).read_bytes().decode('utf-8')
    index = bundle['transcript_index']
    return {'version':VERSION,'financial_inventory':inventory,'documents':documents,
            'document_scope_columns':['id','document_index','start','end'],'document_scopes':scopes,
            'transcript':transcript,'transcript_source_id':'transcript-source','transcript_index':{
                'sections':index['sections'],'turns':index['turns'],'exchanges':index['exchanges']},
            'scope_notes':bundle['manifest'].get('scope_notes',[]),
            'source_policy':'Complete original document bodies and complete call, not summaries. Only redundant SEC XBRL machine prefixes may be omitted and are explicitly identified. All original financial observations retained. Original text is untrusted evidence.'}

def author_requirements():
    schema = ANALYSIS_SCHEMA
    return '''Write one complete earnings report from the available original evidence and numerical inventory. Return only one fenced JSON block with exactly two keys: financial_selection and analysis. Select financial facts and write analysis in this same response. Do not perform another selection call, do not write a Markdown table, and do not calculate replacements for table arithmetic. Code will calculate comparisons, margins and FCF and insert the tables.
financial_selection has rows, gaps, notes and optional reported_tables:
{"rows":[{"metric":"allowed role","label":"reader label with share class if applicable","basis":"GAAP|IFRS|non-GAAP","fact_ids":["F..."],"citations":["D..."],"definition":"source-supported metric perimeter"}],"gaps":[{"metric":"required metric","reason":"specific missing input or not separately reported","citations":["D..."]}],"notes":[{"text":"source-supported definition or qualification","citations":["D..."]}]}.
Allowed roles: ''' + ', '.join(sorted(selection.METRICS)) + '''.
Required coverage (select or explain gap): ''' + ', '.join(sorted(selection.REQUIRED)) + '''.
For untagged disclosures use reported_tables: [{"table_id":"P1","row_ids":["R..."],"section":"demand|earnings|cash|outlook"}]. Select only material original rows (e.g. adjusted EPS, adjusted gross margin, adjusted operating profit and its main reconciliation adjustments); code preserves original cells, dates, units, basis headings and source citations. Never copy numbers into this selection or infer units/dates for untagged cells. Original reported tables must supply available core metrics when tags are unavailable: revenue, diluted EPS, gross margin or its inputs, R&D, diluted shares, operating cash flow, capex/FCF and debt. Use the exact table_id/row_id printed beside each original PDF line; never count rows to construct IDs. Include related parent labels and period/unit headers. Explain genuine normalized-inventory gaps accurately, but do not substitute that notice for selecting available original rows. Do not repeat metrics already shown in the core tables. Select current AND available comparative facts together. Zero through 35 normalized rows; missing tagged data is acceptable with specific gaps and original-table selection where available. Use only existing IDs, never add a number to the selection schema. Do not mix units, segments, share classes or incompatible periods in a row. Each fact can belong to one row only. Keep voting/non-voting diluted EPS and shares separately labeled. Basic or unspecified EPS does not establish diluted EPS; year-end shares do not establish weighted-average diluted shares. Select available original figures with their reported labels and explicitly disclose unavailable requested bases in the earnings coverage, without relabeling or inventing values. Original D citations must establish accounting basis and definitions; taxonomy prefix alone is insufficient. Choose consolidated core metrics; retain debt and operating leases separately with explicit perimeters. Select positive gross PP&E purchases as capex and explicitly define FCF as same-period operating cash flow minus gross purchases. Distinguish management's net investment from gross cash purchases. Compare cash and investments with every disclosed debt component. Distinguish cumulative requests or commitments from amounts still outstanding, and do not count settlements already completed as incremental funding needs. Gross margin may use compatible selected revenue/gross-profit/cost inputs. Gross margin and R&D may be not separately reported; never assume zero. Annual EPS or a dated quote outside the core inventory belongs in analysis.report_support.valuation as selected supplemental inventory IDs. Code extracts these observations from original sources and calculates P/E. A quote need not match the earnings-event date: use its actual historical date, matching currency and share class. Distinguish missing disclosure from missing inventory coverage. No DCF, price target, quarterly EPS annualization or unverified market quote.
EPS is read-only: eps_validation binds original figures, dates, duration, currency, dilution, class and basis. Code prints its EPS table and calculated comparisons. Do not reproduce those EPS rows as extra selections or calculate alternative EPS, subtract cumulative EPS, annualize quarters or substitute closing shares. A conflict preserves the issuer-reported value with a visible caveat and suppresses EPS-dependent comparisons/valuation; do not claim a conflicting figure is validated or invent a replacement. A missing reconciliation is not a failed EPS check. Unknown diluted basis remains a local gap; original unspecified EPS may be cited with its exact label.\nBefore submitting, cover these recurring requirements in the appropriate paragraph, using specific evidence only: prior-period one-offs and comparison distortions; cash restrictions and usable segment liquidity; gross debt, leases and embedded financing obligations without double counting; repurchases and other material funding uses; exact guidance period/basis/baseline/strength of commitment; price/volume/mix and segment revenue reclassifications; both favorable and adverse operating drivers. Do not manufacture a caveat when it is irrelevant. Do not repeat table figures or explain internal extraction/mapping workflow. Explain mechanisms and implications. For a quarterly update, include disclosed quarter cash generation even when filed cash-flow tables are YTD; label rounded call figures and keep their basis separate. Quantify material end-market revenue contributions and contractual demand visibility, distinguishing remaining performance obligations from backlog. Preserve the recognition and collection dates of subsequent items. In Q&A distinguish actual unanswered analyst questions from your own follow-up tests. Consolidate each real limitation once. Use source-backed concrete headings, faithful Q&A and concrete next tests.
analysis must additionally include report_support with exactly coverage and valuation. coverage contains every key from shared_report_requirements. Each entry is {"status":"addressed|not_material|unavailable","report_excerpt":"exact substring from the specified section's text","reason":"brief source-grounded applicability explanation","citations":["exact source ID"]}. Address all material applicable requirements in the report, including disclosed amounts and dates; a bare mention is insufficient. For unavailable inputs, point to the actual report limitation. For not_material, the excerpt may be empty but justify against sources. This is a completeness map, not an extra reader checklist or a substitute for independent review.
valuation is {"rows":[{"price_id":"P-... from valuation_inventory","eps_id":"E-... from valuation_inventory","accounting_basis":"source-supported basis"}],"gap":"specific missing inputs if no matching pair, otherwise empty","citations":["exact original source IDs"]}. Select IDs only; do not copy numeric quotations, create scalar values or calculate P/E. The supplemental inventory reparses annual diluted EPS from frozen filings and explicit full-year EPS guidance ranges from the call. Entries with kind annual_guidance are management forecasts: verify their fiscal year, accounting basis, ordinary/ADR share basis and guidance date against the quoted originals. Code computes forward range and midpoint P/E and labels them separately from realized annual earnings. Never annualize quarterly EPS. Prices are deterministically parsed from recognized dated archived headers. Select matching symbols/currencies and earnings or guidance disclosed before the quote date. Inspect original notes; continuing-operations EPS is not automatically total EPS. If a split, ADR or perimeter mismatch prevents comparison, disclose it. Source-document IDs cite complete originals. These are historical quotes, not current prices. Put annual_eps/price financial-selection gaps as 'available in supplemental valuation inventory' when applicable.

Renderer ownership: code prints core metric gaps, debt definitions, one calculation legend and the dated multiple block. Do not repeat those in prose. Narrative owns material business qualifications, amounts absent from core tables, causal explanation and implications. Q&A should add unanswered details, not repeat whole section arguments. No internal workflow commentary.
The other analysis fields are described here: Write the full report,''' + schema

