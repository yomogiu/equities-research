"""Packet-wide, source-bound extraction before authorship.

Tagged observations are normalized by the XBRL parser. Ordinary table cells stay
verbatim with their row/column spans: no guessed dates, scales, units or GAAP basis.
The author selects rows, never supplies replacement financial values.
"""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import re
from . import financial_evidence as financial
from . import earnings_runtime_common as storage

VERSION = 'packet-financial-inventory-v1'


def _ancestor(node, tag):
    node = node.parent
    while node is not None:
        if node.tag == tag: return node
        node = node.parent


def _text(node):
    return re.sub(r'[\s\u200b\ufeff]+', ' ', node.text()).strip()


def tables(raw, source):
    parser = financial._Parser(raw); parser.feed(raw); parser.close()
    result = []
    blocks=sorted([n for tag in ('p','h1','h2','h3','h4') for n in parser.root.all(tag)
                   if _ancestor(n,'table') is None and n.end>n.start and _text(n)],key=lambda n:n.end)
    for ordinal, table in enumerate(parser.root.all('table'), 1):
        rows = []; occupied = {}; cells = []
        for row_number, row in enumerate(n for n in table.all('tr') if _ancestor(n, 'table') is table):
            column = 0; ids = []
            for node in row.children:
                if not isinstance(node, financial._Node) or node.tag not in ('td', 'th'): continue
                while (row_number, column) in occupied: column += 1
                # Malformed/excessive layouts remain recorded, not expanded into huge grids.
                try:
                    rowspan = int(node.attrs.get('rowspan', '1')); colspan = int(node.attrs.get('colspan', '1'))
                except ValueError: rowspan = colspan = 0
                if not 1 <= rowspan <= 100 or not 1 <= colspan <= 100:
                    rowspan = colspan = 1; layout = 'ambiguous_span'
                else: layout = 'explicit'
                identifier = 'C'+str(len(cells)+1)
                nested = bool(list(node.all('table')))
                cell = {'id':identifier, 'row':row_number, 'column':column,
                        'rowspan':rowspan, 'colspan':colspan, 'text':_text(node),
                        'start':node.start, 'end':node.end,
                        'raw_span_sha256':financial.digest(raw[node.start:node.end].encode()),
                        'tagged':bool(list(node.all('nonfraction'))), 'nested_table':nested,
                        'layout':layout}
                cells.append(cell); ids.append(identifier)
                for r in range(row_number, row_number+rowspan):
                    for c in range(column, column+colspan): occupied[r,c] = identifier
                column += colspan
            rows.append({'id':'R'+str(row_number+1),'cells':ids})
        context=[{'text':_text(n),'start':n.start,'end':n.end,
                  'raw_span_sha256':financial.digest(raw[n.start:n.end].encode())}
                 for n in [b for b in blocks if b.end<=table.start][-3:]]
        result.append({'context':context,'id':'T-'+storage.digest([source['document_id'], source['sha256'], table.start])[:20],
            'document_id':source['document_id'], 'source_sha256':source['sha256'],
            'source_id':'document-source-'+source['document_id'][:20],
            'start':table.start,'end':table.end,'raw_span_sha256':financial.digest(raw[table.start:table.end].encode()),
            'rows':rows,'cells':cells,'ordinal':ordinal})
    return result


def build(sources):
    """Read every bound raw document once; inventory failures explicitly."""
    artifacts = []; extracted_tables = []; coverage = []
    seen = set()
    for source in sources:
        if source['representation'] != 'raw' or source['kind'] == 'transcript': continue
        key = source['document_id'], source['sha256']
        if key in seen: continue
        seen.add(key)
        data = Path(source['path']).read_bytes()
        if financial.digest(data) != source['sha256']: raise ValueError('Packet inventory source changed')
        row = {'document_id':source['document_id'],'kind':source['kind'],'sha256':source['sha256'],
               'tagged_observations':0,'tables':0,'status':'extracted','limitations':[]}
        try: raw = data.decode('utf-8')
        except UnicodeDecodeError:
            row.update(status='unsupported_format', limitations=['Binary/PDF source requires a qualified table representation; not issuer nondisclosure.'])
            coverage.append(row); continue
        binding = {'document_id':source['document_id'],'raw_sha256':source['sha256']}
        artifact = financial.extract_inline_xbrl(raw, binding)
        captured = tables(raw, source)
        artifacts.append(artifact); extracted_tables.extend(captured)
        row.update(tagged_observations=len(artifact['observations']),tables=len(captured))
        row['limitations'] = artifact['gaps']
        if not artifact['observations'] and not captured:
            row.update(status='unstructured_text',limitations=['No tagged observations or HTML tables. Original text remains available; this does not establish nondisclosure.'])
        coverage.append(row)
    raw_ids = {r['document_id'] for r in coverage}
    for s in sources:
        if s['representation']=='text' and s['kind']!='transcript' and s['document_id'] not in raw_ids:
            coverage.append({'document_id':s['document_id'],'kind':s['kind'],'sha256':s['sha256'],
                'status':'raw_source_missing','tagged_observations':0,'tables':0,
                'limitations':['Only text available; original table structure unavailable.']})
    kinds = {s['kind'] for s in sources}
    return {'version':VERSION,'artifacts':artifacts,'tables':extracted_tables,'coverage':coverage,
            'source_set':{k:('present' if k in kinds else 'not_in_qualified_packet') for k in ('filing','release','transcript')},
            'periods':[list(p) for p in sorted({tuple([o['context']['instant']]) if o['context'].get('instant') else (o['context']['start_date'],o['context']['end_date']) for a in artifacts for o in a['observations']})],
            'policy':'Every archived raw financial document is inventoried before authorship. Untagged cells retain original text, headers and spans; semantic normalization is not inferred. Missing source coverage is not issuer nondisclosure. No downstream retrieval.'}


def compact(inventory):
    """Lossless table grid, with empty cells and repeated strings dictionary encoded."""
    result = []
    for table in inventory['tables']:
        # Prose/layout tables remain in complete original documents. All tables
        # with an untagged numeric cell get an explicit grid as well.
        numeric = lambda c: bool(re.fullmatch(r'[($€£+\-−]?\s*[\d,.]+\s*[%)]?', c['text']))
        if not any(numeric(c) and not c['tagged'] and not c['nested_table'] for c in table['cells']): continue
        byid={c['id']:c for c in table['cells']}; rows=[]
        for row in table['rows']:
            values=[]
            for identifier in row['cells']:
                c=byid[identifier]
                if not c['text'].strip(' \u200b\ufeff'): continue
                item=[c['column'],c['text']]
                if c['colspan']!=1 or c['rowspan']!=1:item.extend([c['colspan'],c['rowspan']])
                if c['nested_table'] or c['layout']!='explicit':item.append('layout_only')
                values.append(item)
            if values:rows.append([row['id'],values])
        result.append({'id':table['id'],'source_id':table['source_id'],
            'context':[c['text'] for c in table.get('context',[])],'rows':rows})
    strings=Counter(text for t in result for text in [*t['context'],*[c[1] for r in t['rows'] for c in r[1]]])
    shared=sorted(text for text,count in strings.items() if count>1 and len(text)>16)
    references={text:i for i,text in enumerate(shared)}
    def reference(text):return {'text_ref':references[text]} if text in references else text
    for t in result:
        t['context']=[reference(text) for text in t['context']]
        for row in t['rows']:
            for cell in row[1]:cell[1]=reference(cell[1])
    return {'version':VERSION,'shared_text':shared,'row_format':'[row_id, cells]; cell=[column,text,optional colspan,rowspan]; empty cells implicit. Text may be {text_ref:index} into shared_text.', 'tables':result,'coverage':inventory['coverage'],'source_set':inventory['source_set'],'periods':inventory['periods'],
            'policy':inventory['policy'],'total_captured_tables':len(inventory['tables'])}


def validate_selection(rows, bundle):
    if not isinstance(rows,list) or len(rows)>12: raise ValueError('At most twelve original table selections required')
    byid = {t['id']:t for t in bundle.get('packet_inventory',{}).get('tables',[])}
    seen = set()
    for pick in rows:
        if not isinstance(pick,dict) or set(pick)!={'table_id','row_ids','section'}: raise ValueError('Select original table/row IDs and section only; no replacement values')
        if pick['section'] not in ('demand','earnings','cash','outlook') or pick['table_id'] not in byid: raise ValueError('Known original table and report section required')
        if pick['table_id'] in seen: raise ValueError('Duplicate original table selection')
        seen.add(pick['table_id']); table=byid[pick['table_id']]
        ids=pick['row_ids']; known={r['id']:r for r in table['rows']}
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or not set(ids)<=set(known):raise ValueError('Known unique original table rows required')
        cells={c['id']:c for c in table['cells']}
        for rid in ids:
            if any(cells[c]['nested_table'] or cells[c]['layout']!='explicit' for c in known[rid]['cells']):
                raise ValueError('Ambiguous or nested layout cannot become a report table')
    return rows


def selected(rows,bundle):
    validate_selection(rows,bundle)
    byid={t['id']:t for t in bundle.get('packet_inventory',{}).get('tables',[])}
    return [{**deepcopy(byid[p['table_id']]),'selected_row_ids':p['row_ids'],'section':p['section']} for p in rows]


def render(table):
    """Keep original labels, date/unit/basis headers and intervening subheadings.

    Cells retain their column positions. No calculated comparison is invented for
    an unnormalized table; filed comparisons appear exactly as reported.
    """
    from . import earnings_markdown_render as markdown
    cells={c['id']:c for c in table['cells']}; chosen=set(table['selected_row_ids']); kept=[]
    def data_row(row):
        content=[cells[i]['text'] for i in row['cells'] if cells[i]['text']]
        return len(content)>1 and bool(re.search('[A-Za-z]',content[0])) and any(re.fullmatch(r'[($€£+\-−]?\s*[\d,.]+\s*[%)]?',c) for c in content[1:])
    # All non-data rows retain title, basis, column dates, units and footnotes.
    for row in table['rows']:
        if row['id'] in chosen or not data_row(row):kept.append(row)
    grid={}; width=0
    for row in table['rows']:
        for identifier in row['cells']:
            c=cells[identifier];width=max(width,c['column']+c['colspan'])
            for r in range(c['row'],c['row']+c['rowspan']):
                for col in range(c['column'],c['column']+c['colspan']):grid[r,col]=c['text']
    matrix=[]
    for row in kept:
        index=int(row['id'][1:])-1
        values=[grid.get((index,c),'') for c in range(width)]
        if any(values):matrix.append(values)
    columns=[c for c in range(width) if any(r[c] for r in matrix)]
    # Drop only columns identical across every retained row (colspan copies).
    columns=[c for i,c in enumerate(columns) if not i or any(r[c]!=r[columns[i-1]] for r in matrix)]
    if not columns:return []
    lines=['### Reported financial detail', '', *[markdown.cell(c['text']) for c in table.get('context',[])], '', markdown.refs([table['source_id']]), '',
           '| '+' | '.join('Original label / value' if i==0 else 'Reported column '+str(i) for i in range(len(columns)))+' |',
           '| '+' | '.join('---' for _ in columns)+' |']
    lines.extend('| '+' | '.join(markdown.cell(r[c]) for c in columns)+' |' for r in matrix)
    return lines+['']


LAYOUT = 'original-table-columns-v2'


def render_compact(table):
    """Project selected numeric columns, folding source headers and number affixes.

    This is layout only: no semantic period/unit classification or arithmetic.
    The original row grid, exact cell text and hashes remain in the artifact.
    """
    from . import earnings_markdown_render as markdown
    cells={c['id']:c for c in table['cells']}; chosen=set(table['selected_row_ids'])
    rows=[row for row in table['rows'] if row['id'] in chosen]
    numeric=lambda text:bool(re.fullmatch(r'[($€£+\-−]?\s*[\d,.]+\s*[%)]?',text))
    def data(row):
        populated=[cells[i] for i in row['cells'] if cells[i]['text']]
        return len(populated)>1 and bool(re.search('[A-Za-z]',populated[0]['text'])) and any(numeric(c['text']) for c in populated[1:])
    first_data=next((int(row['id'][1:])-1 for row in table['rows'] if data(row)),len(table['rows']))
    columns=sorted({cells[i]['column'] for row in rows for i in row['cells']
                    if cells[i]['column']>0 and numeric(cells[i]['text'])})
    if not columns:return render(table)
    headers={col:[] for col in columns}
    for c in table['cells']:
        if c['row']>=first_data or not c['text'] or c['text'] in ('$', '%', '(', ')'):continue
        for col in columns:
            if c['column']<=col<c['column']+c['colspan'] and c['text'] not in headers[col]:headers[col].append(c['text'])
    common=[s for s in headers[columns[0]] if all(s in headers[col] for col in columns)] if len(columns)>1 else []
    column_labels=[' / '.join(s for s in headers[col] if s not in common) for col in columns]
    if any(not label for label in column_labels):
        # One shared date header can itself be the column name.
        column_labels=[' / '.join(headers[col]) or 'Reported value' for col in columns]
        common=[]
    contexts=[c['text'] for c in table.get('context',[]) if c['text'] and not re.fullmatch(r'\d+',c['text'])]
    # The nearest preceding title and its trailing unit declaration apply to
    # this table; earlier paragraphs/page furniture do not become report prose.
    title_index=next((i for i in reversed(range(len(contexts))) if not contexts[i].startswith('(')),None)
    if title_index is not None:contexts=contexts[title_index:]
    title=contexts[0] if contexts and not contexts[0].startswith('(') else 'Reported financial detail'
    context=contexts[1:] if contexts and title==contexts[0] else contexts
    lines=['### '+markdown.cell(title),'',*dict.fromkeys([*context,*common]),'',markdown.refs([table['source_id']]),'',
           '| '+' | '.join(markdown.cell(s) for s in ['Metric',*column_labels])+' |',
           '| '+' | '.join('---' for _ in range(len(columns)+1))+' |']
    for row in rows:
        actual=sorted([cells[i] for i in row['cells'] if cells[i]['text']],key=lambda c:c['column'])
        label=' '.join(c['text'] for c in actual if c['column']<columns[0] and c['text'] not in ('$','€','£','('))
        values=[]
        for col in columns:
            matches=[(i,c) for i,c in enumerate(actual) if c['column']==col and numeric(c['text'])]
            if not matches:values.append('');continue
            i,c=matches[0];value=c['text']
            left=i-1
            while left>=0 and actual[left]['text'] in ('$', '€', '£', '(', '-', '−', '+'):
                value=actual[left]['text']+value;left-=1
            right=i+1
            while right<len(actual) and actual[right]['text'] in ('%',')','^','†','*'):
                value+=actual[right]['text'];right+=1
            values.append(value)
        lines.append('| '+' | '.join(markdown.cell(s) for s in [label,*values])+' |')
    return lines+['']


def render_comparison(tables):
    """Combine compatible source-reported GAAP/non-GAAP rows; no recalculation."""
    from . import earnings_markdown_render as markdown
    combined=[];fallback=[];sources=[]
    def split(line):return [s.strip() for s in re.split(r'(?<!\\)\|',line)[1:-1]]
    for table in tables:
        lines=render_compact(table);grid=[split(s) for s in lines if s.startswith('|')]
        if len(grid)<3:fallback.extend(lines);continue
        heads=grid[0];normalized=[re.sub(r'\W','',s.casefold()) for s in heads]
        if normalized.count('gaap')!=1 or normalized.count('nongaap')!=1:
            fallback.extend(lines);continue
        gaap,adjusted=normalized.index('gaap'),normalized.index('nongaap')
        title=lines[0][4:] if lines[0].startswith('### ') else 'Reported metric'
        period=re.search(r'\(([^)]*\b\d{4}\b[^)]*)\)',title)
        period=period[1] if period else next((s for s in lines if re.search(r'\b(?:ended|ending|as of)\b',s,re.I)),title)
        units=next((c['text'] for c in reversed(table.get('context',[])) if c['text'].startswith('(')),'Source-reported units')
        clean=lambda s:re.sub(r'[\^†*]+$','',s)
        for row in grid[2:]:
            if len(row)!=len(heads):raise ValueError('Source table column count changed')
            label=row[0]
            if label.casefold() in ('basic','diluted','total'):
                label=re.sub(r'\s*\([^)]*\b\d{4}\b[^)]*\)','',title)+' · '+label
            values=[clean(row[gaap]),clean(row[adjusted])]
            scale='%' if all(v.endswith('%') for v in values if v) else units
            adjustments=[]
            for i,heading in enumerate(heads[1:],1):
                if i not in (gaap,adjusted) and row[i]:
                    name=re.sub(r'^Non-GAAP Adjustments\s*/\s*','',heading,flags=re.I)
                    adjustments.append(name+': '+clean(row[i]))
            combined.append([label,markdown.cell(period),markdown.cell(scale),*values,'; '.join(adjustments)])
        sources.append(table['source_id'])
    if not combined:return fallback
    # Keep each metric's reported periods together without deriving a date order.
    labels=list(dict.fromkeys(row[0] for row in combined))
    combined.sort(key=lambda row:labels.index(row[0]))
    lines=['### Reported GAAP and non-GAAP comparison','',markdown.refs(list(dict.fromkeys(sources))),'',
           '| Metric | Reported period | Unit / scale | GAAP | Non-GAAP | Reconciliation adjustments |',
           '| --- | --- | --- | --- | --- | --- |']
    lines.extend('| '+' | '.join(row)+' |' for row in combined)
    return lines+['',*fallback]


COMPACT_LAYOUT = LAYOUT
LAYOUT = 'original-table-comparison-v3'
