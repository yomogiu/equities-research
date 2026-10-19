"""Explicit NYSE-to-TXSE header qualification from two bound primary sources.

This never changes archived evidence or treats exchange metadata as a widget.
"""
import re
from datetime import date
from html import escape
from urllib.parse import urlsplit
from .contracts import require
from . import library,source_parse,transcript_evidence
from .freshness import timestamp

VERSION='stockanalysis-authenticated-listing-header-currentness-v7'
AUTHORITY_VERSION='authenticated-nyse-txse-primary-listing-v1'

def authority(root,reference,issuer_id,url,checked_at):
 from .transcript_currentness import sha
 path=library.resolve(root,reference['path']);require(sha(path.read_bytes())==reference['sha256'],'Listing authority changed')
 v=library.read_json(path)
 require(v['version']==AUTHORITY_VERSION and v['issuer_id']==issuer_id and v['source_url']==url,'Exact listing issuer and source required')
 require(re.fullmatch(r'sec:[0-9]{10}',issuer_id) and re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}',v['ticker']),'Exact SEC issuer and ticker required')
 require(url==f"https://stockanalysis.com/stocks/{v['ticker'].lower()}/transcripts/"+urlsplit(url).path.rsplit('/transcripts/',1)[-1] and url.endswith('/'),'Exact publisher ticker URL required')
 require(v['from_exchange']=='NYSE' and v['to_exchange']=='TXSE' and v['currency']=='USD','Supported exact listing route required')
 effective=date.fromisoformat(v['effective_date']);require(timestamp(checked_at) is not None and effective.isoformat()<=timestamp(checked_at)[:10],'Listing transition not yet effective')
 receipt=library.resolve(root,v['fetch_receipt_path']);require(sha(receipt.read_bytes())==v['fetch_receipt_sha256'],'Primary fetch receipt changed');records=library.read_json(receipt)
 names={reference['path']:reference['sha256'],v['fetch_receipt_path']:v['fetch_receipt_sha256']};texts={}
 for kind in ('issuer','exchange'):
  matches=[x for x in records if x.get('raw_sha256')==v[kind+'_raw_sha256']];require(len(matches)==1,'Unique actual primary fetch required');row=matches[0];parsed=urlsplit(row['url'])
  require(row['status']==200 and row['final_url']==row['url'] and 'html' in row['content_type'] and timestamp(row['at']) is not None,'Actual same-URL primary HTML observation required')
  if kind=='issuer':require(parsed.scheme=='https' and parsed.hostname=='www.sec.gov' and re.fullmatch(r'/Archives/edgar/data/'+str(int(issuer_id[4:]))+r'/[0-9]{18}/[^/]+\.htm',parsed.path),'Issuer primary filing CIK changed')
  else:require(parsed.scheme=='https' and parsed.hostname=='www.txse.com' and parsed.path.startswith('/press/'),'Destination exchange primary announcement required')
  raw=library.load_bytes(root,row['raw_path'],row['raw_sha256']);names[row['raw_path']]=row['raw_sha256'];texts[kind]=re.sub(r'\s+',' ',source_parse.page(raw,row['url']).text)
 name=v['company_name'];require(re.fullmatch(r"[A-Za-z0-9 &'.,()-]{3,100}",name),'Exact registrant name required')
 sec=texts['issuer'];exchange=texts['exchange'];long_date=effective.strftime('%B ')+str(effective.day)+effective.strftime(', %Y')
 require(issuer_id[4:] in sec and name.upper()+' (Exact name of Registrant' in sec and 'FORM 8-K' in sec,'Primary registrant identity changed')
 require('from listing on the New York Stock Exchange (“NYSE”), and the transfer of those listings to the Texas Stock Exchange (“TXSE”).' in sec and
         f'The ticker symbols for the Common Units (TXSE: {v["ticker"]})' in sec and 'will remain unchanged.' in sec and
         f'trading will begin on the TXSE at market open on {long_date}.' in sec,'Exact issuer listing-transfer statement required')
 require(long_date in exchange and name+f' (TXSE: {v["ticker"]})' in exchange and
         'held a market open bell ringing ceremony today celebrating the move' in exchange and 'primary listings to TXSE.' in exchange,'Completed destination exchange listing confirmation required')
 return v,names

def compare(before,after,url,v):
 from . import transcript_currentness as scope
 old=f'<div class="mt-px text-tiny text-faded">NYSE: {v["ticker"]} · Real-Time Price · USD</div>'
 new=old.replace('>NYSE:', '>TXSE:')
 for raw,header in ((before,old),(after,new)):
  html=raw.decode();require(html.count(header)==1,'Unique exact listing header required')
  blocks=transcript_evidence._TranscriptBlocks(html);blocks.feed(html);blocks.close()
  require(blocks.blocks and html.index(header)<html.index(blocks.blocks[0]),'Listing header must precede all original call blocks')
  require(escape(v['company_name']+f' ({v["ticker"]})') in html[:html.index(header)],'Publisher registrant/ticker label changed')
 # Only this exact header is rebound for comparison. Every speaker HTML block,
 # full call text, title, fiscal tag, fact and other non-widget byte-derived text
 # remains under the existing strict comparison.
 rebound=after.decode().replace(new,old).encode()
 result=scope.compare(before,rebound,url)
 result['listing_header_transition']={k:v[k] for k in ('issuer_id','company_name','ticker','currency','from_exchange','to_exchange','effective_date')}
 result['whole_page_bytes_equal']=before==after
 result['whole_page_text_equal']=source_parse.page(before,url).text==source_parse.page(after,url).text
 return result

def verify_derivation(root,receipt,*,historical=False):
 """Replay an additive source receipt without rewriting its failed ancestor."""
 import copy
 from . import transcript_currentness as scope
 d=receipt.get('derivation',{})
 require(d.get('version')=='authenticated-listing-header-source-qualification-v1','Known listing receipt derivation required')
 require(set(d)=={'version','original_receipt','original_receipt_sha256','listing_authority','scoped_currentness','scope'},'Exact listing derivation fields required')
 oldpath=library.resolve(root,d['original_receipt']);require(scope.sha(oldpath.read_bytes())==d['original_receipt_sha256'],'Original failed source receipt changed')
 original=library.read_json(oldpath);require('derivation' not in original and len(original['companies'])==len(receipt['companies'])==1,'Exact original single-issuer refresh required')
 proof=scope.replay(root,d['scoped_currentness'],historical=historical);require(proof['version']==scope.LISTING_VERSION and proof['listing_authority']==d['listing_authority'] and proof['issuer_id']==original['companies'][0]['issuer_id'],'Listing proof lineage mismatch')
 expected=copy.deepcopy(original);rows=[x for x in expected['companies'][0]['documents']if x['source_url']==proof['source_url']]
 require(len(rows)==1 and rows[0]['status']=='changed_requires_review' and rows[0]['observed_sha256']==proof['observed']['raw_sha256'] and timestamp(rows[0]['checked_at'])==proof['checked_at'],'Exact rejected listing fetch required')
 rows[0].update(status='scoped_transcript_currentness_verified',scoped_currentness=d['scoped_currentness']);rows[0].pop('scope_reason',None)
 expected['companies'][0]['new_packet_id']=receipt['companies'][0]['new_packet_id'];expected['derivation']=d
 require(expected==receipt,'Only qualified listing status and rebuilt packet may change')
 _,inputs=authority(root,d['listing_authority'],proof['issuer_id'],proof['source_url'],proof['checked_at']);inputs[d['original_receipt']]=d['original_receipt_sha256'];return inputs
