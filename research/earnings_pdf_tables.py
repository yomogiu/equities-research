"""Verbatim positional PDF table inventory; no inferred financial facts or units."""
import re
from . import earnings_runtime_common as storage
from . import financial_evidence as financial

NUMBER = re.compile(r'[($+\-−]?(?:\d[\d ,.]*\d|\d)(?:[%)]|\.\d+)?|[—–-]')


def _data_line(body):
    pieces=re.findall(r'\S(?:\S| (?=\S))*',body)
    numbers=[p for p in pieces if NUMBER.fullmatch(p)]
    return (len(numbers)>=2 and any(re.search('[A-Za-z\u3400-\u9fff]',p) for p in pieces)
            and not all(re.fullmatch(r'20\d{2}',p) for p in numbers))


def tables(text, source):
    """Capture page rows with original offsets and stable horizontal columns.

    Poppler layout text is a bound derivative of the PDF. Sparse rows keep their
    columns. Headers and all page text remain available; no semantic mapping or
    period/unit/scale inference takes place here.
    """
    result=[]
    pages=list(re.finditer(r'(?m)^\[Page \d+\]\n',text))
    for ordinal,marker in enumerate(pages,1):
        end=pages[ordinal].start() if ordinal<len(pages) else len(text)
        lines=[];numeric=[]
        for line in re.finditer(r'[^\n]+',text[marker.end():end]):
            base=marker.end()+line.start();body=line.group()
            pieces=[m for m in re.finditer(r'\S(?:\S| (?=\S))*',body)]
            values=[p for p in pieces if NUMBER.fullmatch(p.group())]
            if len(values)>=2 and any(re.search('[A-Za-z\u3400-\u9fff]',p.group()) for p in pieces):
                numeric.extend(p.end() for p in values)
            lines.append((base,body,pieces))
        if len(numeric)<6:continue
        clusters=[]
        for position in sorted(numeric):
            if clusters and position-clusters[-1][-1]<=4:clusters[-1].append(position)
            else:clusters.append([position])
        anchors=[sorted(c)[len(c)//2] for c in clusters if len(c)>=2]
        if len(anchors)<2:continue
        rows=[];cells=[];source_lines=[]
        for base,body,pieces in lines:
            if not pieces:continue
            ids=[];used=set()
            for p in pieces:
                # Labels remain in column zero; note columns remain distinct.
                col=0 if p.end()<anchors[0]-4 else 1+min(range(len(anchors)),key=lambda i:abs(anchors[i]-p.end()))
                if col in used:
                    # Ambiguous layout is preserved as a single exact line,
                    # never silently merged into an incorrect numeric column.
                    ids=[];cells=cells[:-len(used)] if used else cells
                    pieces=[];break
                used.add(col);identifier='C'+str(len(cells)+1)
                start=base+p.start();stop=base+p.end()
                cells.append({'id':identifier,'row':len(rows),'column':col,'rowspan':1,'colspan':1,
                    'text':p.group(),'start':start,'end':stop,'raw_span_sha256':financial.digest(text[start:stop].encode()),
                    'tagged':False,'nested_table':False,'layout':'pdf_positional'})
                ids.append(identifier)
            if not ids:
                start=base;stop=base+len(body);identifier='C'+str(len(cells)+1)
                cells.append({'id':identifier,'row':len(rows),'column':0,'rowspan':1,'colspan':len(anchors)+1,
                    'text':body.strip(),'start':start,'end':stop,'raw_span_sha256':financial.digest(text[start:stop].encode()),
                    'tagged':False,'nested_table':False,'layout':'pdf_unresolved_line'})
                ids=[identifier]
            rows.append({'id':'R'+str(len(rows)+1),'cells':ids})
            source_lines.append({'row_id':rows[-1]['id'],'text':body,'start':base,'end':base+len(body)})
        preceding=[]
        if ordinal>1:
            previous=pages[ordinal-2]
            previous_text=text[previous.end():marker.start()]
            # A PDF sometimes places the statement title/units on an otherwise
            # empty page immediately before its numbers. Preserve that heading
            # as quoted context, never infer a currency or scale from it.
            heading=re.search(r'statements?|balance sheets?|cash flows?|\(?in (?:thousands?|millions?|billions?)|單位|单位|資產負債表|资产负债表|現金流量表|现金流量表',previous_text,re.I)
            if len(previous_text)<3500 and heading and not any(_data_line(line) for line in previous_text.splitlines()):
                preceding=[{'text':previous_text.strip(),'start':previous.end(),'end':marker.start(),
                            'raw_span_sha256':financial.digest(previous_text.encode())}]
        result.append({'id':'T-'+storage.digest([source['document_id'],source['sha256'],marker.start()])[:20],
            'document_id':source['document_id'],'source_sha256':source['sha256'],
            'source_id':'document-source-'+source['document_id'][:20],'start':marker.start(),'end':end,
            'raw_span_sha256':financial.digest(text[marker.start():end].encode()),'rows':rows,'cells':cells,'ordinal':ordinal,
            'source_lines':source_lines,
            'context':[*preceding,{'text':marker.group().strip(),
                        'start':marker.start(),'end':marker.end(),'raw_span_sha256':financial.digest(marker.group().encode())}],
            'representation':'pdf_layout_text','limitation':'Positional extraction; wrapped or ambiguous rows retained verbatim. Verify against complete original page.'})
    return result


def render(table):
    """Display selected source rows in their captured columns, with all headers.

    This intentionally avoids the HTML compactor's numeric normalization and
    colspan expansion. Full-width unresolved lines remain single verbatim text.
    """
    from . import earnings_markdown_render as markdown
    cells={c['id']:c for c in table['cells']};chosen=set(table['selected_row_ids'])
    last=max((i for i,row in enumerate(table['rows']) if row['id'] in chosen),default=-1)
    original_lines={s['row_id']:s['text'] for s in table.get('source_lines',[])}
    width=max(c['column']+c['colspan'] for c in cells.values());rows=[];kept=[]
    for position,row in enumerate(table['rows']):
        # Parent labels and period/unit headers precede their selected values.
        # Do not append unrelated footnotes, dangling labels or page footers.
        if position>last:break
        values=[cells[i] for i in row['cells']]
        numeric=sum(bool(NUMBER.fullmatch(c['text'])) for c in values)
        label=next((c['text'] for c in values if re.search('[A-Za-z\u3400-\u9fff]',c['text'])),'')
        header=bool(re.search(r'^\W*(?:amounts?|note|currency|units?|USD|EUR|NOK|GBP|SEK|CHF)\b',label,re.I)
                    or '單位' in label
                    or re.match(r'^\s*\(?in\s+(?:[€£$]|USD|EUR|NOK|GBP|SEK|CHF|thousands?|millions?|billions?|percent)',label,re.I))
        numeric_cells=[c['text'] for c in values if NUMBER.fullmatch(c['text'])]
        header=header or bool(numeric_cells and all(re.fullmatch(r'20\d{2}',s) for s in numeric_cells)) or bool(re.search(r'民國|民国|年度|months? ended|quarter ended|year ended',label,re.I))
        data=not header and ((numeric>=2 and any(re.search('[A-Za-z\u3400-\u9fff]',c['text']) for c in values))
                              or _data_line(original_lines.get(row['id'],'')))
        if data and row['id'] not in chosen:continue
        kept.append(row['id'])
        line=['']*width
        for c in values:line[c['column']]=c['text']
        rows.append(line)
    if table.get('source_lines'):
        # Positional heuristics are useful for discovery, but must not move
        # numeric cells under guessed columns in the published report.
        lines=[*[c['text'] for c in table['context']],*[s['text'] for s in table['source_lines'] if s['row_id'] in kept]]
        block='\n'.join(lines)
        fence='`'*max(3,max((len(s) for s in re.findall(r'`+',block)),default=0)+1)
        return ['### Reported financial detail','',
                'Original PDF layout; selected rows retain their printed alignment, units and period headings.',
                '',markdown.refs([table['source_id']]),'',fence+'text',*lines,fence,'']
    columns=[i for i in range(width) if any(r[i] for r in rows)]
    lines=['### Reported financial detail','',*[c['text'] for c in table['context']],
           'Verbatim PDF rows; original units and period headers retained.','',markdown.refs([table['source_id']]),'',
           '| '+' | '.join('Source label' if i==0 else 'Source column '+str(i) for i in columns)+' |',
           '| '+' | '.join('---' for i in columns)+' |']
    return lines+['| '+' | '.join(markdown.cell(row[i]) for i in columns)+' |' for row in rows]+['']
