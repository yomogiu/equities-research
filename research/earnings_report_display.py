"""Compact layout in the model view; frozen originals and table cells stay exact."""
from copy import deepcopy
import hashlib,re

def compact(packet):
    result=deepcopy(packet)
    def table_view(value):
        if isinstance(value,str):return re.sub(r'[ \t]{2,}','\t',value)
        if isinstance(value,list):return [table_view(x) for x in value]
        if isinstance(value,dict):return {k:table_view(x) for k,x in value.items()}
        return value
    if 'financial_inventory' in result and 'original_tables' in result['financial_inventory']:
        result['financial_inventory']['original_tables']=table_view(result['financial_inventory']['original_tables'])
    for doc in result['documents']:
        original=doc['text'];end=doc['start']+len(original)
        if str(doc.get('omitted_prefix','')).startswith('Annual business/'):
            # Financial statements and controls remain. Directors, proxy and
            # exhibit appendices are outside this financial event-update view.
            suffix=re.search(r'(?im)^\s*Item\s+10[.\s]+Directors\b',original)
            if suffix:
                original=original[:suffix.start()];end=doc['start']+len(original)
                doc['omitted_suffix']='Annual directors, proxy and exhibit appendices omitted from model view. Full original and complete extracted table inventory remain frozen.'
        shown=re.sub(r'[ \t]{2,}','\t',original)
        if re.sub(r'[ \t]','',shown)!=re.sub(r'[ \t]','',original):raise ValueError('Display compaction changed source characters')
        doc['text']=shown
        doc['display_projection']={'rule':'horizontal-layout-v1','original_start':doc['start'],'original_end':end,
            'original_span_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'notice':'Repeated horizontal layout spaces are displayed as tabs in documents and table text; line breaks and non-layout characters are unchanged. Offsets refer to the frozen original, not this display. Original table IDs and positions are unchanged. Financial selection and rendering use the frozen original cells, units and dates.'}
    result['document_scopes']=[row for row in result['document_scopes']
        if row[2]>=result['documents'][row[1]]['start'] and row[3]<=result['documents'][row[1]]['display_projection']['original_end']]
    result['source_policy']+=' Model document views compact horizontal layout and omit annual directors/proxy/exhibit appendices after financial statements and controls. Complete original files and extracted table inventory remain unchanged; no metric or source absence is inferred from this view.'
    return result
