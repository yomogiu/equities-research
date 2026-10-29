"""Compact layout in the model view; frozen originals and table cells stay exact."""
from copy import deepcopy
import hashlib,re
from bisect import bisect_right

def compact(packet, bundle=None):
    result=deepcopy(packet)
    addressed={};row_labels={}
    if bundle:
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
            table['rows']=[[row['id'],bisect_right(starts,min(cells[i]['start'] for i in row['cells']))]
                           for row in raw['rows']]
            for rid,number in table['rows']:
                row_labels.setdefault(table['source_id'],{}).setdefault(number,[]).append(table['id']+'/'+rid)
            table['row_format']='[row_id, source_line_number]; the exact table_id/row_id is printed beside the original document line. Select those printed IDs directly; do not count rows or infer an ID from line numbers. Values, headers and units appear there once.'
            table['representation']='pdf_original_line_index'
    def table_view(value):
        if isinstance(value,str):return re.sub(r'[ \t]{2,}','\t',value)
        if isinstance(value,list):return [table_view(x) for x in value]
        if isinstance(value,dict):return {k:table_view(x) for k,x in value.items()}
        return value
    if 'financial_inventory' in result and 'original_tables' in result['financial_inventory']:
        result['financial_inventory']['original_tables']=table_view(result['financial_inventory']['original_tables'])
    for doc in result['documents']:
        original=doc['text'];end=doc['start']+len(original)
        shown=re.sub(r'[ \t]{2,}','\t',original)
        if re.sub(r'[ \t]','',shown)!=re.sub(r'[ \t]','',original):raise ValueError('Display compaction changed source characters')
        if doc.get('source_id') in addressed:
            labels=row_labels.get(doc['source_id'],{})
            shown='\n'.join('L'+str(i)+(' ['+', '.join(labels[i])+']' if i in labels else '')+': '+line.strip(' \t') for i,line in enumerate(shown.split('\n'),1)
                            if line.strip(' \t'))
        doc['text']=shown
        doc['display_projection']={'rule':'horizontal-layout-v2','original_start':doc['start'],'original_end':end,
            'original_span_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'notice':'Horizontal layout spaces are compacted; original PDF lines are visibly addressed as LN, with blank layout lines omitted. Bracketed table_id/row_id labels are selection metadata, not source text. All non-layout source characters remain. Offsets refer to frozen originals. Financial selection and rendering use original cells, units and dates.'}
    result['document_scopes']=[row for row in result['document_scopes']
        if row[2]>=result['documents'][row[1]]['start'] and row[3]<=result['documents'][row[1]]['display_projection']['original_end']]
    result['source_policy']+=' Model views compact layout only and retain all captured document content. Original files and extracted tables remain unchanged; no metric or source absence is inferred from display formatting.'
    return result
