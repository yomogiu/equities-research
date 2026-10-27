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
from .fetch import Client, FetchError, PUBLIC_USER_AGENT
from .source_parse import extract, page

VERSION='fresh-quarter-sources-v1'


def require(value,message):
    if not value:raise ValueError(message)


def current_calls(body,url,as_of):
    """Only ordinary quarterly calls under the exact issuer index; no post calls."""
    found={}
    for link in page(body,url).links:
        match=re.fullmatch(re.escape(url)+r'\d+-q([1-4])-(20\d{2})/',link['url'])
        if not match:continue
        q,y=map(int,match.groups())
        if date(y,q*3,monthrange(y,q*3)[1])>as_of:continue
        found.setdefault((y,q),set()).add(link['url'])
    require(found,'No completed quarterly event discovered from issuer transcript index')
    key=max(found)
    require(len(found[key])==1,'Ambiguous latest ordinary earnings call')
    return key,next(iter(found[key]))


def filing_url(body,landing):
    """Read the exact filing-ID object, never evaluate embedded JavaScript."""
    identifier=urlsplit(landing).path.strip('/').split('/')[-1]
    require(identifier.isdigit(),'Unrecognized provider filing identifier')
    pattern=r'\{id:'+re.escape(identifier)+r',type:"quarterly_report"[^{}]{0,1500}?fileUrl:"([^"\n]+)"'
    matches=set(re.findall(pattern,body.decode('utf-8')))
    require(len(matches)==1,'Exact quarterly-report download binding unavailable')
    return matches.pop().replace('\\u002F','/').replace('\\/','/')


def qualify_report(text,issuer,period):
    recognized=identity.recognize(text,issuer,period)
    require(len(text)>10000,'Quarterly report is incomplete or too short')
    checks=[r'income statement|statement of (?:profit|operations)',r'financial position|balance sheet',r'cash flow']
    require(all(re.search(p,text,re.I) for p in checks),'Financial statements missing from quarterly report')
    require(re.search(r'\[Page \d+\]',text),'PDF page extraction unavailable')
    return {'issuer_and_period':'explicit_document_evidence',**recognized,'completeness':'financial_statements_present',
            'language':'English statement headings verified','limitations':['Mechanical source qualification; report review independently checks interpretation and attribution.']}


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
    ledger=[];docs=[];artifacts=[]
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
        period,call_url=current_calls(body,profile['provider_index'],as_of)
        require((as_of-date(period[0],period[1]*3,monthrange(period[0],period[1]*3)[1])).days<=150,
                'Latest discovered quarter is stale; refuse old-period substitution')
        period_id=f'FY{period[0]}-Q{period[1]}'
        require(period_id not in profile['transcript_skip_periods'],'User skipped transcript retrieval for this issuer and period')
        call_body,call_http=fetch(call_url,'transcript')
        call,call_text=document(call_body,call_http,'transcript',call_url)
        require(profile['issuer_name'].casefold() in call_text[:1600].casefold(),'Transcript issuer mismatch')
        require(f'Earnings Call: Q{period[1]} {period[0]}' in call_text[:2000],'Transcript period mismatch')
        # Only report links attached to the selected call are candidates.
        links={l['url'] for l in page(call_body,call_url).links if l['title'].strip().lower()=='quarterly report'}
        require(len(links)==1,'Selected call lacks a unique attached quarterly report')
        landing=links.pop();landing_body,_=fetch(landing,'report_landing')
        pdf_url=filing_url(landing_body,landing)
        # Prefer official PDFs when the index exposes the same explicit quarter.
        report_body=report_http=report_url=None
        if official:
            candidates={l['url'] for l in page(official,profile['official_index']).links
                if re.search(r'(?i)q'+str(period[1])+r'[-_ ]?'+str(period[0]),l['url']) and
                   re.search(r'(?i)report.*\.pdf',l['url'])}
            if len(candidates)==1:
                url=candidates.pop()
                try:report_body,report_http=fetch(url,'official_report');report_url=url
                except FetchError:pass
        if report_body is None:report_body,report_http=fetch(pdf_url,'issuer_report_mirror');report_url=pdf_url
        require(report_body.startswith(b'%PDF'),'Quarterly report must be original PDF bytes')
        report,report_text=document(report_body,report_http,'filing',report_url)
        qualification=qualify_report(report_text,profile['issuer_name'],period)
        binding={k:call[k] for k in ('document_id','text_sha256','raw_sha256')}
        binding.update(issuer_id=spec['issuer_id'],issuer_names=[profile['issuer_name']])
        index=transcript.index_publisher_transcript(call_text,binding,call_body)
        require(index['exchanges'] and len(index['turns'])>=4,'Complete indexed earnings Q&A unavailable')
        require(not index['coverage'].get('unassigned_qa_turn_ids'),'Unassigned Q&A turns prevent source qualification')
        qualification.update(version=VERSION,issuer_id=spec['issuer_id'],period=period_id,as_of=profile['as_of'],
            documents=docs,discovery_complete=False,transcript_exchanges=len(index['exchanges']),
            discovery_scope='Latest completed ordinary quarterly call in configured public issuer index, matched to explicit report identity and reporting-period evidence. Official-source failures are retained; no claim of exhaustive web coverage.',
            source_gaps=['Separate release, annual background, consensus and current valuation inputs not collected by this bounded route.'])
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
                if doc['kind']=='filing' and representation=='text':
                    row.update(derived_from_sha256=doc['raw_sha256'],extraction='pdftotext-layout-v1')
                sources.append(row)
        case.save(output/'retrieval.json',{'requests':client.requests,'cache_hits':client.cache_hits,
            'bytes_downloaded':client.bytes,'entries':ledger,'model_calls':0})
        for name in ('qualification.json','financial.json','transcript-index.json','retrieval.json'):
            artifacts.append({'path':str(output/name),'sha256':case.sha(output/name)})
        bound={a['path'] for a in artifacts}|{s['path'] for s in sources}
        for entry in ledger:
            if entry['status']!='retrieved':continue
            raw_path=str(collection/entry['body_path'])
            if raw_path not in bound:
                artifacts.append({'path':raw_path,'sha256':entry['sha256']});bound.add(raw_path)
        writing=Path(spec['writing_standard']);artifacts.append({'path':str(writing),'sha256':case.sha(writing)})
        year,q=period;start=date(year,(q-1)*3+1,1).isoformat();end=date(year,q*3,monthrange(year,q*3)[1]).isoformat()
        value={'schema_version':1,'scope':'one_packet_experiment','authorization':spec['authorization'],
            'case_id':case.digest(qualification),'packet_id':case.digest(qualification),'issuer_id':spec['issuer_id'],'period':period_id,
            'sources':sources,'artifacts':artifacts,'financial_path':str(output/'financial.json'),
            'transcript_index_path':str(output/'transcript-index.json'),'transcript_path':call['text_path'],
            'writing_standard_path':str(writing),'financial_inventory_version':'packet-financial-inventory-v1',
            'financial_configuration':finance.configuration(start,end),
            'scope_notes':[
                'Freshly collected '+period_id+' event_update. Source qualification binds issuer, explicit quarter, statement coverage, hashes and indexed call; it is not accounting or investment approval.',
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
            'bytes_downloaded':client.bytes,'entries':ledger,'model_calls':0})
