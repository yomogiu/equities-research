"""Explicit primary-source NYSE/Nasdaq header plus strict market-open proof.

No exchange metadata is generally masked, and older proof versions are untouched.
"""
import copy,re
from datetime import date
from html import escape
from urllib.parse import urlsplit
from . import library,source_parse,transcript_evidence
from .contracts import require
from .freshness import timestamp
VERSION='authenticated-nasdaq-market-open-source-qualification-v1'
PROOF_VERSION='stockanalysis-authenticated-nasdaq-market-open-currentness-v10'
AUTHORITY_VERSION='authenticated-nyse-nasdaq-primary-listing-v1'

def authority(root,reference,issuer_id,url,checked_at):
 from .transcript_currentness import sha
 path=library.resolve(root,reference['path']);require(sha(path.read_bytes())==reference['sha256'],'Listing authority changed');v=library.read_json(path)
 require(v['version']==AUTHORITY_VERSION and v['issuer_id']==issuer_id and v['source_url']==url,'Exact primary issuer and URL required')
 require(re.fullmatch(r'sec:[0-9]{10}',issuer_id) and re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}',v['ticker']),'Exact SEC issuer/ticker required')
 require(re.fullmatch(r'https://stockanalysis\.com/stocks/'+v['ticker'].lower()+r'/transcripts/[0-9]+-q[1-4]-[0-9]{4}/',url),'Exact publisher issuer/event URL required')
 require((v['from_exchange'],v['to_exchange'],v['currency'])==('NYSE','NASDAQ','USD'),'Explicit NYSE/Nasdaq USD route required')
 effective=date.fromisoformat(v['effective_date']);previous=date.fromisoformat(v['nyse_final_date']);require(previous<effective and timestamp(checked_at) is not None and effective.isoformat()<=timestamp(checked_at)[:10],'Effective listing timing required')
 name=v['company_name'];brand=v['issuer_brand'];require(re.fullmatch(r"[A-Za-z0-9 &'.,()-]{3,100}",name) and re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{1,30}',brand) and name.startswith(brand+' '),'Exact registrant and issuer brand required')
 receipt=library.resolve(root,v['fetch_receipt_path']);require(sha(receipt.read_bytes())==v['fetch_receipt_sha256'],'Actual primary fetch receipt changed');records=library.read_json(receipt)
 inputs={reference['path']:reference['sha256'],v['fetch_receipt_path']:v['fetch_receipt_sha256']};texts={};raws={};urls={}
 for kind in ('issuer','exchange','completion'):
  rows=[x for x in records if x.get('raw_sha256')==v[kind+'_raw_sha256']];require(len(rows)==1,'Unique primary observation required');row=rows[0];u=urlsplit(row['url']);urls[kind]=u
  require(row['status']==200 and row['final_url']==row['url'] and 'html' in row['content_type'] and timestamp(row['at']) is not None and timestamp(row['at'])[:10]>=effective.isoformat(),'Actual effective same-URL HTTP200 HTML observation required')
  require(u.scheme=='https' and not u.fragment and not u.username and not u.password,'Exact primary HTTPS URL required')
  if kind=='issuer':require(u.hostname=='www.sec.gov' and re.fullmatch(r'/Archives/edgar/data/'+str(int(issuer_id[4:]))+r'/[0-9]{18}/[^/]+\.htm',u.path) and not u.query,'Primary CIK filing required')
  elif kind=='exchange':require(u.hostname=='www.nasdaqtrader.com' and u.path=='/TraderNews.aspx' and re.fullmatch(r'id=DTN[0-9]{4}-[0-9]+',u.query),'Official operational destination-exchange notice required')
  else:require(u.hostname=='www.'+v['issuer_domain'] and u.path.startswith('/blog/') and not u.query,'Exact issuer completion blog required')
  raw=library.load_bytes(root,row['raw_path'],row['raw_sha256']);inputs[row['raw_path']]=row['raw_sha256'];raws[kind]=raw.decode();texts[kind]=re.sub(r'\s+',' ',source_parse.page(raw,row['url']).text)
 require(re.fullmatch(r'[a-z][a-z0-9-]+\.com',v['issuer_domain']) and v['issuer_domain']==brand.lower()+'.com','Bound issuer domain required')
 # The independently hosted operational notice must itself link the issuer IR
 # domain. A supplied blog hostname alone is never domain-ownership evidence.
 require(re.search(r'href=[\"\']https://ir\.'+re.escape(v['issuer_domain'])+r'/news/[^\"\']+[\"\']',raws['exchange']) is not None,'Exchange-to-issuer domain provenance required')
 long=lambda d:d.strftime('%B ')+str(d.day)+d.strftime(', %Y')
 sec=texts['issuer'];exchange=texts['exchange'];completion=texts['completion']
 require(issuer_id[4:] in sec and 'FORM 8-K' in sec and name+' (Exact name of registrant as specified in its charter)' in sec,'Exact primary registrant required')
 require('approved the transfer of the listings of the Securities to The Nasdaq Stock Market LLC (“Nasdaq”).' in sec and 'The Securities have been approved for listing on Nasdaq, where the Common Stock is expected to continue trading under the symbol “'+v['ticker']+',”' in sec and 'de-listed from the NYSE at the close of trading on '+long(previous) in sec and 'listed on Nasdaq effective at the opening of trading on '+long(effective) in sec,'Explicit issuer route, unchanged ticker and timing required')
 require('On '+long(effective)+', '+name+' (NYSE: '+v['ticker']+') is expected to be listed and begin trading on the Nasdaq Global Select Market under the same ticker symbol '+v['ticker']+'.' in exchange and 'NYSE Ticker through '+long(previous) in exchange and 'Nasdaq Ticker as of '+long(effective) in exchange,'Exact operational listing/ticker/effective-date confirmation required')
 require('Today, '+brand+' begins trading on Nasdaq.' in completion,'Observed issuer completion statement required')
 # The blog has no independently established publication date. Only its HTTP
 # observation and completion statement are used; dates come from SEC/notice.
 return v,inputs

def compare(before,after,url,v):
 from . import transcript_currentness as scope
 old=f'<div class="mt-px text-tiny text-faded">NYSE: {v["ticker"]} · Real-Time Price · USD</div>';new=old.replace('>NYSE:', '>NASDAQ:')
 for raw,header in ((before,old),(after,new)):
  body=raw.decode();require(body.count(header)==1,'Unique exact listing header required');blocks=transcript_evidence._TranscriptBlocks(body);blocks.feed(body);blocks.close()
  require(blocks.blocks and body.index(header)<body.index(blocks.blocks[0]),'Header must precede all call blocks');require(escape(v['company_name']+f' ({v["ticker"]})') in body[:body.index(header)],'Exact publisher issuer/ticker label required')
 result=scope.compare(before,after.decode().replace(new,old).encode(),url,allow_market_open=True)
 result['listing_header_transition']={k:v[k] for k in ('issuer_id','company_name','ticker','currency','from_exchange','to_exchange','effective_date')};result['whole_page_bytes_equal']=before==after;result['whole_page_text_equal']=source_parse.page(before,url).text==source_parse.page(after,url).text
 return result

def verify_derivation(root,receipt,*,historical=False):
 from . import transcript_currentness as scope
 d=receipt.get('derivation',{});require(d.get('version')==VERSION and set(d)=={'version','original_receipt','original_receipt_sha256','scoped_currentness','listing_authority'},'Exact combined listing/widget derivation required')
 path=library.resolve(root,d['original_receipt']);require(scope.sha(path.read_bytes())==d['original_receipt_sha256'],'Original failed receipt changed');original=library.read_json(path);require('derivation' not in original and len(original['companies'])==len(receipt['companies'])==1,'Original single issuer receipt required')
 proof=scope.replay(root,d['scoped_currentness'],historical=historical);require(proof['version']==PROOF_VERSION and proof['listing_authority']==d['listing_authority'] and proof['issuer_id']==original['companies'][0]['issuer_id'],'Exact combined proof lineage required')
 expected=copy.deepcopy(original);row=expected['companies'][0];docs=[x for x in row['documents'] if x['source_url']==proof['source_url']];require(len(docs)==1,'Unique original URL required');doc=docs[0]
 require(doc['status']=='changed_requires_review' and doc.get('scope_reason')=='Unrecognized quote widget' and doc['expected_sha256']==proof['archived']['raw_sha256'] and doc['observed_sha256']==proof['observed']['raw_sha256'] and doc['raw_path']==proof['observed']['raw_path'] and timestamp(doc['checked_at'])==proof['checked_at'],'Exact rejected original fetch required')
 doc.update(status='scoped_transcript_currentness_verified',scoped_currentness=d['scoped_currentness']);doc.pop('scope_reason');row['new_packet_id']=receipt['companies'][0]['new_packet_id'];expected['derivation']=d;require(expected==receipt,'Only qualified combined status and rebuilt packet may change')
 _,inputs=authority(root,d['listing_authority'],proof['issuer_id'],proof['source_url'],proof['checked_at']);inputs[d['original_receipt']]=d['original_receipt_sha256'];return inputs
