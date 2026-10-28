"""Bind coverage to verbatim report spans; do not generate or change claims."""
import re
from copy import deepcopy
from .earnings_report_contract import COVERAGE

def synchronize(value):
    result=deepcopy(value);changes=[]
    analysis=result.get('analysis',{})
    coverage=analysis.get('report_support',{}).get('coverage',{})
    for key,(location,_) in COVERAGE.items():
        row=coverage.get(key,{})
        quote=row.get('report_excerpt','')
        actual=analysis.get('sections',{}).get(location,{}).get('text','')
        if not quote or quote in actual or row.get('status')=='not_material':continue
        # A model may omit sentences inserted between copied sentences. Every
        # requested sentence must occur verbatim, in order, in the same section.
        sentences=re.split(r'(?<=[.!?])\s+',quote.strip())
        cursor=0;start=None
        for sentence in sentences:
            position=actual.find(sentence,cursor)
            if position<0:break
            if start is None:start=position
            cursor=position+len(sentence)
        else:
            if start is not None:
                exact=actual[start:cursor]
                changes.append({'coverage':key,'before':quote,'after':exact,
                                'section':location,'start':start,'end':cursor})
                row['report_excerpt']=exact
    return result,changes
