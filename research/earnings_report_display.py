"""Compact layout in the model view; frozen originals and table cells stay exact."""
from copy import deepcopy
import hashlib,re
from bisect import bisect_right


def pdf_names(bundle):
    return {t['id']:'P'+str(i+1) for i,t in enumerate(bundle.get('packet_inventory',{}).get('tables',[]))
            if t.get('representation')=='pdf_layout_text'}


def annual_lines(text,tables):
    """Bound a large SEC annual model view without losing any captured table.

    Require substantive Item 7 -> Item 8 -> Item 9 spans, not TOC entries.
    Unrecognized layouts retain their complete text. Originals are never edited.
    """
    if len(text)<400_000 or not re.search(r'FORM\s+10-K\b',text[:15000],re.I):return None,[]
    pages=list(re.finditer(r'(?m)^\[Page \d+\]\n',text))
    if not pages:return None,[]
    headings=list(re.finditer(r'(?im)^[ \t]*Item[ \t]+(1A|1B|1C|2|7|8|9)[. \t]+',text))
    start=end=None
    for h in headings:
        if h[1]=='7' and re.search(r'Management',text[h.end():h.end()+250],re.I):
            eight=next((x for x in headings if x.start()>h.start() and x[1]=='8'),None)
            nine=next((x for x in headings if eight and x.start()>eight.start() and x[1]=='9'),None)
            if (eight and nine and eight.start()-h.start()>4000 and nine.start()-eight.start()>4000
                    and re.search(r'Financial\s+Statements',text[eight.end():eight.end()+250],re.I)):
                start,end=h.start(),nine.start();break
    if start is None:return None,[]
    final_page=max((p for p in pages if p.start()<=end),key=lambda p:p.start())
    if not text[final_page.end():end].strip():end=final_page.start()
    ranges=[(start,end)]
    # Every inventoried table and detached heading page remains visible, even
    # when it sits outside the usual financial sections.
    ranges.extend((t['start'],t['end']) for t in tables)
    ranges.extend((c['start'],c['end']) for t in tables for c in t.get('context',[]))
    keep=set(range(min(2,len(pages))))
    for i,p in enumerate(pages):
        stop=pages[i+1].start() if i+1<len(pages) else len(text)
        if any(a<stop and b>p.start() for a,b in ranges):keep.add(i)
    omitted=[{'start':p.start(),'end':pages[i+1].start() if i+1<len(pages) else len(text)}
             for i,p in enumerate(pages) if i not in keep]
    if sum(x['end']-x['start'] for x in omitted)<len(text)//10:return None,[]
    starts=[p.start() for p in pages];allowed=set();offset=0
    for i,line in enumerate(text.splitlines(keepends=True),1):
        if bisect_right(starts,offset)-1 in keep:allowed.add(i)
        offset+=len(line)
    return allowed,omitted


def compact(packet, bundle=None):
    result=deepcopy(packet)
    addressed={};row_labels={}
    if bundle:
        names=pdf_names(bundle)
        # PDF cell text already occurs in the complete original document. Index
        # every selectable row to a visible original line instead of printing
        # that entire table a second time. Raw cells and extraction stay frozen.
        for doc in result['documents']:
            if any(t.get('representation')=='pdf_layout_text' and t['source_id']==doc['source_id']
                   for t in bundle.get('packet_inventory',{}).get('tables',[])):
                addressed[doc['source_id']]=[doc['start'],*[doc['start']+m.end() for m in re.finditer('\n',doc['text'])]]
        raw_tables={t['id']:t for t in bundle.get('packet_inventory',{}).get('tables',[])}
        tables=result.get('financial_inventory',{}).get('original_tables',{})
        for table in tables.get('tables',[]):
            raw=raw_tables.get(table['id']);starts=addressed.get(table['source_id'])
            if not raw or not starts:continue
            cells={c['id']:c for c in raw['cells']}
            rows=[[row['id'],bisect_right(starts,min(cells[i]['start'] for i in row['cells']))] for row in raw['rows']]
            for rid,number in rows:
                row_labels.setdefault(table['source_id'],{}).setdefault(number,[]).append(names[table['id']]+'/'+rid)
            table['id']=names[table['id']]
            table['rows']=[];table['row_count']=len(rows);table['context']=[]
            table['row_format']='All table_id/row_id labels are printed beside the original document lines. Select those printed IDs directly; do not count rows or infer an ID from line numbers. Values, headers, units and detached heading context appear there once.'
            table['representation']='pdf_original_line_index'
    def table_view(value):
        if isinstance(value,str):return re.sub(r'[ \t]{2,}','\t',value)
        if isinstance(value,list):return [table_view(x) for x in value]
        if isinstance(value,dict):return {k:table_view(x) for k,x in value.items()}
        return value
    if 'financial_inventory' in result and 'original_tables' in result['financial_inventory']:
        result['financial_inventory']['original_tables']=table_view(result['financial_inventory']['original_tables'])
        original_tables=result['financial_inventory']['original_tables'];shared=original_tables.get('shared_text',[]);used=set()
        def refs(node):
            if isinstance(node,dict):
                if set(node)=={'text_ref'}:used.add(node['text_ref'])
                else:
                    for v in node.values():refs(v)
            elif isinstance(node,list):
                for v in node:refs(v)
        refs(original_tables.get('tables',[]));mapping={old:new for new,old in enumerate(sorted(used))}
        def remap(node):
            if isinstance(node,dict):
                if set(node)=={'text_ref'}:node['text_ref']=mapping[node['text_ref']]
                else:
                    for v in node.values():remap(v)
            elif isinstance(node,list):
                for v in node:remap(v)
        remap(original_tables.get('tables',[]))
        if 'shared_text' in original_tables:original_tables['shared_text']=[shared[i] for i in sorted(used)]
    for doc in result['documents']:
        original=doc['text'];end=doc['start']+len(original)
        shown=re.sub(r'[ \t]{2,}','\t',original)
        if re.sub(r'[ \t]','',shown)!=re.sub(r'[ \t]','',original):raise ValueError('Display compaction changed source characters')
        if doc.get('source_id') in addressed:
            raw_tables=[t for t in bundle['packet_inventory']['tables'] if t['source_id']==doc['source_id']]
            allowed,omitted=annual_lines(original,raw_tables) if doc['start']==0 else (None,[])
            labels=row_labels.get(doc['source_id'],{})
            shown='\n'.join(('['+', '.join(labels[i])+'] ' if i in labels else '')+line.strip(' \t') for i,line in enumerate(shown.split('\n'),1)
                            if line.strip(' \t') and (allowed is None or i in allowed))
            if omitted:
                shown='[Annual financial view: complete captured tables, financial statements, notes and MD&A. Other annual-report pages are omitted from this model view; the complete original remains frozen. This is not a full annual risk review.]\n'+shown
        doc['text']=shown
        doc['display_projection']={'rule':'horizontal-layout-v2','original_start':doc['start'],'original_end':end,
            'original_span_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'notice':'Horizontal layout spaces are compacted and blank layout lines omitted. Bracketed P-number/row_id labels are exact bound table-selection metadata, not source text. All non-layout source characters remain unless an explicit annual projection is recorded. Offsets refer to frozen originals. Financial selection and rendering use original cells, units and dates.'}
        if doc.get('source_id') in addressed and omitted:
            doc['display_projection'].update(rule='annual-financial-pages-v1',omitted_original_spans=omitted,
                notice='Complete original is frozen. The model view retains every captured table, complete Item 7 MD&A and Item 8 statements/notes. Other pages are omitted explicitly; this is not a full annual risk review. Offsets refer to the original; selection labels are metadata. No financial amount is changed.')
    result['document_scopes']=[row for row in result['document_scopes']
        if row[2]>=result['documents'][row[1]]['start'] and row[3]<=result['documents'][row[1]]['display_projection']['original_end']
        and not any(a['start']<row[3] and a['end']>row[2] for a in result['documents'][row[1]]['display_projection'].get('omitted_original_spans',[]))]
    result['source_policy']+=' Layout compaction and any explicit annual-page projection affect only the model view. Original files and extracted tables remain unchanged; no metric or source absence is inferred from display formatting.'
    return result
