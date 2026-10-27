"""Bounded fresh discovery and qualification for the finite report runner.

Profiles bind verified issuer identity and approved public discovery routes. The
current adapter supports calendar-year quarterly reports and attributable calls.
It never promotes an old packet or silently substitutes another fiscal period.
"""
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlsplit
from . import earnings_source_case as case
from . import financial_evidence as financial
from . import transcript_evidence as transcript
from . import earnings_financial_analysis_report as finance
from . import earnings_report_identity as identity
from . import earnings_events as events
from .fetch import Client, FetchError, PUBLIC_USER_AGENT
from .source_parse import extract, page

VERSION='fresh-quarter-sources-v1'


def require(value,message):
    if not value:raise ValueError(message)


def current_calls(body,url,as_of):
    event=events.select(body,url,as_of)
    return (event['year'],event['quarter']),event['url']


def filing_url(body,landing,kind='quarterly_report'):
    """Read the exact filing-ID object, never evaluate embedded JavaScript."""
    identifier=urlsplit(landing).path.strip('/').split('/')[-1]
    require(identifier.isdigit(),'Unrecognized provider filing identifier')
    require(kind in {'quarterly_report','annual_report','earnings_release'},'Unsupported attachment type')
    pattern=r'\{id:'+re.escape(identifier)+r',type:"'+re.escape(kind)+r'"[^{}]{0,1500}?fileUrl:"([^"\n]+)"'
    matches=set(re.findall(pattern,body.decode('utf-8')))
    require(len(matches)==1,'Exact financial-document download binding unavailable')
    return matches.pop().replace('\\u002F','/').replace('\\/','/')


def qualify_report(text,issuer,period,*,trading_update=False,provenance=None,verify=None,always_verify=False):
    recognized=None
    require(len(text)>(2500 if trading_update else 10000),'Financial document is incomplete or too short')
    checks=[r'income statement|statement of (?:profit|operations)',r'financial position|balance sheet',r'cash flow']
    if trading_update:
        require(re.search(r'\brevenue\b',text,re.I) and len(re.findall(r'\d[\d ,.]*\d',text))>=3,
                'Trading update lacks substantive reported financial evidence')
    else:require(all(re.search(p,text,re.I) for p in checks),'Financial statements missing from quarterly report')
    require(re.search(r'\[Page \d+\]',text),'PDF page extraction unavailable')
    if provenance is None:recognized=identity.recognize(text,issuer,period)
    else:
        from . import earnings_source_verification as verification
        recognized=verification.qualify(text,issuer,period,provenance,verify,always_verify=always_verify)
    return {'issuer_and_period':'explicit_document_evidence',**recognized,
            'completeness':'limited_trading_update' if trading_update else 'financial_statements_present',
            'language':'English financial headings verified','limitations':['Mechanical source qualification; report review independently checks interpretation and attribution.']}


def prepare(output,spec,*,client=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    profile=spec['fresh_sources'];as_of=date.fromisoformat(profile['as_of'])
    require(profile['version']==VERSION and profile['identity_verified'] is True,'Verified fresh-source profile required')
    require(profile['issuer_id']==spec['issuer_id'],'Fresh-source issuer mismatch')
    require(profile['fiscal_calendar']=='calendar_year','Explicit supported fiscal calendar required')
    require(isinstance(profile.get('transcript_skip_periods'),list),'Explicit transcript skip resolution required')
    require(profile['provider_index'].startswith('https://stockanalysis.com/') and profile['provider_index'].endswith('/transcripts/'),
            'Unsupported public transcript discovery route')
    collection=output/'collection';require(not collection.exists(),'Fresh collection must start with an empty directory')
    collection.mkdir()
    client=client or Client(collection,set(profile['allowed_hosts']),PUBLIC_USER_AGENT,max_requests=24,max_bytes=64*1024*1024)
    ledger=[];docs=[];artifacts=[];source_model_calls=0
    def fetch(url,kind):
        try:
            body,entry=client.get(url,0)
            ledger.append({'url':url,'kind':kind,'status':'retrieved',**entry})
            return body,entry
        except FetchError as exc:
            ledger.append({'url':url,'kind':kind,'status':'failed','reason':exc.code});raise
    def document(body,http,kind,url):
        text,_,status=extract(body,http['content_type'],url)
        require(status=='extracted','Source text extraction failed: '+status)
        did=financial.digest((spec['issuer_id']+'\n'+kind+'\n'+http['sha256']).encode())
        path=output/(did+'.txt');path.write_text(text)
        doc={'document_id':did,'kind':kind,'source_url':url,'final_url':http['final_url'],
            'raw_path':str(collection/http['body_path']),'raw_sha256':http['sha256'],
            'text_path':str(path),'text_sha256':case.sha(path),'retrieved_at':datetime.now(timezone.utc).isoformat()}
        docs.append(doc);return doc,text
    try:
        # Record the official archive attempt even if an attributable mirror is needed.
        official=None
        try:official=fetch(profile['official_index'],'official_discovery')[0]
        except FetchError:pass
        body,_=fetch(profile['provider_index'],'transcript_discovery')
        require(profile['issuer_name'].casefold() in page(body,profile['provider_index']).text.casefold(),
                'Discovery index issuer mismatch')
        event=events.select(body,profile['provider_index'],as_of)
        period=(event['year'],event['quarter']);call_url=event['url']
        require((as_of-date(period[0],period[1]*3,monthrange(period[0],period[1]*3)[1])).days<=150,
                'Latest discovered quarter is stale; refuse old-period substitution')
        period_id=event['period']
        require(not events.excluded(event,profile['transcript_skip_periods']),'User skipped transcript retrieval for this issuer and period')
        call_body,call_http=fetch(call_url,'transcript')
        call,call_text=document(call_body,call_http,'transcript',call_url)
        events.qualify_call(call_text,profile['issuer_name'],event)
        landing,attachment_kind=events.attachment(call_body,call_url,event)
        landing_body,_=fetch(landing,'report_landing')
        pdf_url=filing_url(landing_body,landing,attachment_kind)
        # Prefer official PDFs when the index exposes the same explicit quarter.
        report_body=report_http=report_url=None
        if official and attachment_kind=='quarterly_report':
            candidates={l['url'] for l in page(official,profile['official_index']).links
                if re.search(r'(?i)q'+str(period[1])+r'[-_ ]?'+str(period[0]),l['url']) and
                   re.search(r'(?i)report.*\.pdf',l['url'])}
            if len(candidates)==1:
                url=candidates.pop()
                try:report_body,report_http=fetch(url,'official_report');report_url=url
                except FetchError:pass
        if report_body is None:report_body,report_http=fetch(pdf_url,'issuer_report_mirror');report_url=pdf_url
        require(report_body.startswith(b'%PDF'),'Quarterly report must be original PDF bytes')
        source_kind='release' if attachment_kind=='earnings_release' else 'filing'
        report,report_text=document(report_body,report_http,source_kind,report_url)
        provenance={'verified_issuer_index':True,'matched_call':True,'exact_attachment':True,
                    'issuer_id':spec['issuer_id'],'provider_index':profile['provider_index'],'call_url':call_url,
                    'attachment_url':landing,'attachment_kind':attachment_kind,'report_url':report_url,
                    'report_raw_sha256':report['raw_sha256'],'report_text_sha256':report['text_sha256'],
                    'call_raw_sha256':call['raw_sha256'],'event':event}
        verifier=spec.get('_verify_source')
        def verify(payload):
            nonlocal source_model_calls
            require(source_model_calls==0,'Only one source-verification decision permitted')
            source_model_calls+=1
            originals={d[k+'_path']:d[k+'_sha256'] for d in docs for k in ('raw','text')}
            originals.update({str(collection/e['body_path']):e['sha256'] for e in ledger if e['status']=='retrieved'})
            return verifier({**payload,'_original_files':originals})
        qualification=qualify_report(report_text,profile['issuer_name'],period,trading_update=source_kind=='release',
                                     provenance=provenance,verify=verify if verifier else None,
                                     always_verify=profile.get('source_verification')=='always')
        binding={k:call[k] for k in ('document_id','text_sha256','raw_sha256')}
        binding.update(issuer_id=spec['issuer_id'],issuer_names=[profile['issuer_name']])
        index=transcript.index_publisher_transcript(call_text,binding,call_body)
        require(index['exchanges'] and len(index['turns'])>=4,'Complete indexed earnings Q&A unavailable')
        require(not index['coverage'].get('unassigned_qa_turn_ids'),'Unassigned Q&A turns prevent source qualification')
        gaps=['Annual background, consensus and current valuation inputs not collected by this bounded route.']
        if source_kind=='release':gaps.append('Trading-update release and call only; no full financial statements collected. Missing earnings, cash-flow and balance-sheet metrics must remain gaps. Never infer profitability from revenue or relabel guidance as realized cash flow.')
        else:gaps.append('Separate earnings release and presentation not collected by this bounded route.')
        qualification.update(version=VERSION,issuer_id=spec['issuer_id'],period=period_id,as_of=profile['as_of'],event=event,attachment_kind=attachment_kind,
            documents=docs,discovery_complete=False,transcript_exchanges=len(index['exchanges']),
            discovery_scope='Latest completed quarterly or semiannual reporting event in configured public issuer index. URL and index/call labels agree; attached document has explicit issuer and period evidence. Official-source failures are retained; no exhaustive web coverage claimed.',
            source_gaps=gaps)
        case.save(output/'qualification.json',qualification)
        case.save(output/'transcript-index.json',index)
        binding={k:report[k] for k in ('document_id','raw_sha256','text_sha256')}
        # Tagged metrics remain unavailable for PDF; the full positional inventory
        # supplies original reported rows. Never pretend inferred tags were filed.
        facts=financial.make_artifact(binding,[],[{'reason':'PDF contains no inline XBRL; use verbatim captured financial tables.'}])
        case.save(output/'financial.json',facts)
        sources=[]
        for doc in docs:
            for representation in ('raw','text'):
                row={'document_id':doc['document_id'],'kind':doc['kind'],'representation':representation,
                     'path':doc[representation+'_path'],'sha256':doc[representation+'_sha256'],'url':doc['source_url']}
                if doc['kind']!='transcript' and representation=='text':
                    row.update(derived_from_sha256=doc['raw_sha256'],extraction='pdftotext-layout-v1')
                sources.append(row)
        case.save(output/'retrieval.json',{'requests':client.requests,'cache_hits':client.cache_hits,
            'bytes_downloaded':client.bytes,'entries':ledger,'model_calls':source_model_calls})
        for name in ('qualification.json','financial.json','transcript-index.json','retrieval.json'):
            artifacts.append({'path':str(output/name),'sha256':case.sha(output/name)})
        bound={a['path'] for a in artifacts}|{s['path'] for s in sources}
        for entry in ledger:
            if entry['status']!='retrieved':continue
            raw_path=str(collection/entry['body_path'])
            if raw_path not in bound:
                artifacts.append({'path':raw_path,'sha256':entry['sha256']});bound.add(raw_path)
        writing=Path(spec['writing_standard']);artifacts.append({'path':str(writing),'sha256':case.sha(writing)})
        start=event['start'];end=event['end']
        value={'schema_version':1,'scope':'one_packet_experiment','authorization':spec['authorization'],
            'case_id':case.digest(qualification),'packet_id':case.digest(qualification),'issuer_id':spec['issuer_id'],'period':period_id,
            'sources':sources,'artifacts':artifacts,'financial_path':str(output/'financial.json'),
            'transcript_index_path':str(output/'transcript-index.json'),'transcript_path':call['text_path'],
            'writing_standard_path':str(writing),'financial_inventory_version':'packet-financial-inventory-v1',
            'financial_configuration':finance.configuration(start,end),
            'source_mode':'trading_update_release' if source_kind=='release' else 'financial_report',
            'qualification_path':str(output/'qualification.json'),
            'scope_notes':[
                'Freshly collected '+period_id+' '+event['kind']+'. Source qualification binds issuer, event label, document coverage, hashes and indexed call; it is not accounting or investment approval. H2 call labels do not establish standalone second-half accounting figures.',
                'Report document basis: '+qualification['report_period']['basis']+' ('+qualification['report_period']['start']+' to '+qualification['report_period']['end']+'). '+qualification['report_period']['interpretation'],
                'PDF financial tables are verbatim positional extraction, not normalized tagged facts. Prefer selected original rows, include their period/unit headers, and disclose unsupported normalized comparisons. Never infer issuer nondisclosure from a missing tag.',
                'Call and report may disagree; use the original financial report for reported accounting figures and explicitly flag material transcript conflicts.',
                'Public provider-hosted issuer report and attributable transcript may be used when official HTTP retrieval fails. No source search after authorship.',
                'Q&A roles and boundaries are provisional; review against the complete original call. Provider summary, market quote and navigation are not company evidence.',
                *qualification['source_gaps']]}
        case.validate_case(value);case.save(output/'case.json',value)
        return output/'case.json'
    finally:
        # Failure receipts survive before any author call; no source retry state.
        case.save(output/'retrieval.json',{'requests':client.requests,'cache_hits':client.cache_hits,
            'bytes_downloaded':client.bytes,'entries':ledger,'model_calls':source_model_calls})
