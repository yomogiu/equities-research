"""Official report-only collection with explicit absent transcript, never a fake call."""
from datetime import date, datetime, timezone
from pathlib import Path
import re
from . import earnings_source_case as case, financial_evidence as financial
from . import earnings_financial_analysis_report as finance
from .fetch import Client, PUBLIC_USER_AGENT
from .source_parse import extract,page

GAP='No transcript was collected or verified. No management call, analyst questions, answers or call-derived guidance are available. This report is based on the original financial report only.'

def require(value,message):
    if not value:raise ValueError(message)

def candidates(body,url,as_of):
    """Read disclosed labels; never construct a guessed report URL."""
    result=[]
    for link in page(body,url).links:
        label=link.get('title','');target=link.get('url','')
        match=re.search(r'(20\d{2})\s*年?\s*第?\s*([1-4])\s*季',label)
        if not match:
            match=re.search(r'(20\d{2})\s*[- ]?\s*Q([1-4])',label,re.I)
        if not match or not re.search(r'合併財務|consolidated|financial report',label,re.I):continue
        year,quarter=map(int,match.groups())
        from calendar import monthrange
        end=date(year,quarter*3,monthrange(year,quarter*3)[1])
        if end<=as_of:result.append({'year':year,'quarter':quarter,'end':end.isoformat(),'url':target,'label':label})
    require(result,'No dated consolidated report links found on official archive')
    latest=max((x['year'],x['quarter']) for x in result)
    selected=[x for x in result if (x['year'],x['quarter'])==latest]
    require(len({x['url'] for x in selected})==1,'Ambiguous latest official report')
    require((as_of-date.fromisoformat(selected[0]['end'])).days<=150,'Latest official report is stale')
    return selected[0]

def qualify(text,profile,event):
    opening=text[:6000]
    names=[profile['issuer_name'],*profile.get('issuer_aliases',[])]
    quote=next((n for n in names if n in opening),None)
    require(quote,'Official report issuer identity missing from opening pages')
    require(len(text)>10000 and re.search(r'\[Page \d+\]',text),'Complete extracted report required')
    english=all(re.search(x,text,re.I) for x in [r'balance sheet|financial position',r'income|profit|operations',r'cash flows?'])
    chinese=all(x in text for x in ['資產負債表','綜合損益表','現金流量表'])
    require(english or chinese,'Financial statements absent from report')
    year,quarter=event['year'],event['quarter']
    # Republic of China dates on Taiwan statements are explicit calendar years,
    # not fiscal-year labels. Both digit-by-digit and Arabic forms are accepted.
    digits='零一二三四五六七八九'
    roc=''.join(digits[int(x)] for x in str(year-1911))
    labels=[str(year),str(year-1911),roc]
    ordinal=['','一','二','三','四'][quarter]
    title=re.search(r'(?:民國\s*)?(?:'+ '|'.join(labels)+r')\s*年[^\n]{0,45}(?:第'+ordinal+r'季|第'+str(quarter)+r'季|Q'+str(quarter)+r')',opening,re.I)
    require(title,'Original report heading does not confirm discovered year and quarter')
    return {'issuer_quote':quote,'period_quote':title.group(),'language':'Chinese' if chinese else 'English',
            'basis':'quarter_and_cumulative','end':event['end']}

def prepare(output,spec,*,client=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    profile=spec['fresh_sources'];as_of=date.fromisoformat(profile['as_of'])
    require(profile['identity_verified'] is True and profile['issuer_id']==spec['issuer_id'],'Verified report-only issuer required')
    require(profile.get('source_ownership_review') and profile.get('source_mode')=='report_only','Explicit report-only profile required')
    collection=output/'collection';require(not collection.exists(),'Fresh collection directory required');collection.mkdir()
    client=client or Client(collection,set(profile['allowed_hosts']),PUBLIC_USER_AGENT,max_requests=8,max_bytes=64*1024*1024)
    ledger=[]
    def fetch(url,kind):
        b,e=client.get(url,0);ledger.append({'url':url,'kind':kind,'status':'retrieved',**e});return b,e
    try:
        body,_=fetch(profile['official_index'],'official_discovery')
        event=candidates(body,profile['official_index'],as_of)
        raw,http=fetch(event['url'],'official_report')
        require(raw.startswith(b'%PDF'),'Original financial PDF required')
        text,_,status=extract(raw,http['content_type'],event['url'])
        require(status=='extracted','Original PDF extraction failed')
        q=qualify(text,profile,event)
        did=financial.digest((spec['issuer_id']+'\n'+http['sha256']).encode())
        text_path=output/(did+'.txt');text_path.write_text(text)
        raw_path=collection/http['body_path'];period=f"FY{event['year']}-Q{event['quarter']}"
        gap_path=output/'transcript-unavailable.txt';gap_path.write_text('')
        gap_id=case.digest({'issuer':spec['issuer_id'],'period':period,'status':'transcript_unavailable'})
        index={'source':{'document_id':gap_id,'text_sha256':case.sha(gap_path)},'offset_unit':'unicode_character',
               'sections':[],'turns':[],'exchanges':[],'coverage':{'status':'unavailable','reason':GAP}}
        case.save(output/'transcript-index.json',index)
        facts=financial.make_artifact({'document_id':did,'raw_sha256':http['sha256'],'text_sha256':case.sha(text_path)},[],[{'reason':'PDF has no normalized tagged facts. Original tables retained.'}])
        case.save(output/'financial.json',facts)
        sources=[{'document_id':did,'kind':'filing','representation':'raw','path':str(raw_path),'sha256':http['sha256'],'url':event['url']},
                 {'document_id':did,'kind':'filing','representation':'text','path':str(text_path),'sha256':case.sha(text_path),'url':event['url'],
                  'derived_from_sha256':http['sha256'],'extraction':'pdftotext-layout-v1'},
                 {'document_id':gap_id,'kind':'source_gap','representation':'text','path':str(gap_path),'sha256':case.sha(gap_path),'url':None}]
        qualification={'source_mode':'report_only','issuer_id':spec['issuer_id'],'period':period,'event':event,
                       'report':q,'documents':[{'document_id':did,'raw_sha256':http['sha256']}],
                       'completeness':'financial_statements_present','source_gaps':[GAP],
                       'checked_at':datetime.now(timezone.utc).isoformat()}
        case.save(output/'qualification.json',qualification)
        case.save(output/'retrieval.json',{'entries':ledger,'requests':client.requests,'bytes_downloaded':client.bytes})
        artifacts=[{'path':str(output/n),'sha256':case.sha(output/n)} for n in ['financial.json','transcript-index.json','qualification.json','retrieval.json']]
        artifacts.append({'path':str(spec['writing_standard']),'sha256':case.sha(spec['writing_standard'])})
        for entry in ledger:
            p=collection/entry['body_path']
            if str(p)!=str(raw_path):artifacts.append({'path':str(p),'sha256':case.sha(p)})
        value={'schema_version':1,'scope':'one_packet_experiment','authorization':spec['authorization'],
               'case_id':case.digest(qualification),'packet_id':case.digest(qualification),'issuer_id':spec['issuer_id'],'period':period,
               'sources':sources,'artifacts':artifacts,'financial_path':str(output/'financial.json'),
               'transcript_index_path':str(output/'transcript-index.json'),'transcript_path':str(gap_path),
               'writing_standard_path':str(spec['writing_standard']),'financial_inventory_version':'packet-financial-inventory-v1',
               'financial_configuration':finance.unresolved_configuration(event['end']),
               'source_mode':'report_only','qualification_path':str(output/'qualification.json'),
               'scope_notes':[GAP,'Original-language financial report. Write English analysis; preserve the original financial table cells, units and periods. Independent reviewer checks translations against originals. Quarter and YTD are distinct. Missing normalized facts do not imply issuer nondisclosure.']}
        case.validate_case(value);case.save(output/'case.json',value);return output/'case.json'
    finally:
        if not (output/'retrieval.json').exists():case.save(output/'retrieval.json',{'entries':ledger,'requests':client.requests,'bytes_downloaded':client.bytes})
