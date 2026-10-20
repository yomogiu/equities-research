"""Explicit fresh exact-content proof for a new bounded historical-work successor.

The old packet/case never changes. Ordinary packet validation remains strict;
this separately bound proof requires a fresh qualified successor and identical
source bytes, identities and qualification for every original document.
"""
from pathlib import Path
import re,hashlib
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import library
VERSION='exact-source-currentness-continuation-v1'
DOC_FIELDS=('document_id','catalog_document_id','source_url','raw_sha256','text_sha256','qualification_id','kind','period','completeness','publisher_type','language','english_coverage')

def packet_ids(old_id,new_id):
 c.require(all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in (old_id,new_id)),'Exact immutable packet IDs required')

def same_content(old,new,raw_equivalent=()):
 for key in ('issuer_id','period','identity_verified','translation_required','availability'):
  c.require(old[key]==new[key],'Source revalidation changed packet scope: '+key)
 def docs(packet):
  rows=[{k:('verified-equivalent-raw' if k=='raw_sha256' and d['document_id'] in raw_equivalent else d[k]) for k in DOC_FIELDS} for d in packet['documents']]
  c.require(len({r['document_id'] for r in rows})==len(rows),'Duplicate source document')
  return sorted(rows,key=lambda d:d['document_id'])
 c.require(docs(old)==docs(new),'Source content, raw bytes or qualification changed')

def equivalent_html(old,new,url,doc,extract,financial):
 a,af,ast=extract(old,'text/html',url);btext,bf,bst=extract(new,'text/html',url)
 if ast!='extracted' or bst!='extracted' or a!=btext or hashlib.sha256(btext.encode()).hexdigest()!=doc['text_sha256'] or af!=bf:return False
 facts=[]
 for body in (old,new):
  f=financial.extract_inline_xbrl(body.decode(),{'document_id':doc['document_id'],'raw_sha256':hashlib.sha256(body).hexdigest(),'text_sha256':doc['text_sha256']})
  facts.append({'observations':[{k:v for k,v in o.items() if k not in ('observation_id','source_raw_sha256','support')} for o in f['observations']],'gaps':[{k:v for k,v in g.items() if k!='start'} for g in f['gaps']]})
 return facts[0]==facts[1]

def historical_packet(root,packet,as_of):
 from . import freshness
 from datetime import datetime,timezone
 stamp=freshness.timestamp(as_of);c.require(stamp is not None,'Recorded timezone-aware launch required')
 moment=datetime.fromisoformat(stamp);c.require(moment<=datetime.now(timezone.utc),'Future role launch rejected')
 library.materialize(root,packet,historical_currentness=True)
 snapshot=b.read(root/f"library/snapshots/{packet['catalog_id']}.json")
 c.require(packet['identity_verified'] and not packet['translation_required'] and snapshot['issuers'].get(packet['issuer_id'],{}).get('monitoring_eligible') is True,'Historical qualified issuer required')
 c.require(freshness.assess_packet(packet,now=moment)['status']=='ready','Sources were not fresh at role launch')
 return packet

def checked(root,old_id,new_id,receipt_path,*,as_of=None):
 from .earnings_report_flow import validate_packet
 packet_ids(old_id,new_id)
 root=Path(root).resolve();old_path=library.resolve(root,'library/packets/'+old_id+'.json');new_path=library.resolve(root,'library/packets/'+new_id+'.json')
 old=b.read(old_path);new=b.read(new_path);c.require(old['packet_id']==old_id and new['packet_id']==new_id,'Packet identity changed')
 library.materialize(root,old,historical_currentness=True)
 current=validate_packet(root,new_id) if as_of is None else historical_packet(root,new,as_of)
 # Historical replay authenticates launch-time qualification; live gates remain fresh NOW.
 receipt=b.read(receipt_path)
 derivation=receipt.get('derivation',{})
 if derivation.get('version')=='authenticated-nasdaq-market-open-source-qualification-v1':
  from . import transcript_nasdaq_transition as nasdaq
  nasdaq.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('version')=='authenticated-kase-source-qualification-v1':
  from . import transcript_kase_transition as kase
  kase.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('version')=='authenticated-tsx-app-rating-legacy-source-v1':
  from . import transcript_tsx_legacy_transition as tsx_legacy
  tsx_legacy.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('version')=='authenticated-footer-app-rating-source-qualification-v1':
  from . import transcript_app_rating_transition as rating
  rating.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('version')=='authenticated-market-open-widget-source-qualification-v1':
  from . import transcript_market_widget_transition as widget
  widget.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('version')=='authenticated-listing-header-source-qualification-v1':
  from . import transcript_listing_transition as listing
  listing.verify_derivation(root,receipt,historical=as_of is not None)
 if derivation.get('legacy_equivalence'):
  from . import legacy_equivalent_source as legacy
  ref=derivation['legacy_equivalence'];proof_path=library.resolve(root,ref['path']);c.require(set(ref)=={'path','sha256'} and b.sha(proof_path)==ref['sha256'],'Legacy equivalence proof changed');proof=legacy.verify(root,proof_path)
  c.require(proof['packet_id']==old_id and proof['receipt_path']==derivation['original_receipt'] and b.sha(library.resolve(root,derivation['original_receipt']))==derivation['original_receipt_sha256'],'Original failed source receipt must remain bound')
 if as_of is not None:
  from . import freshness
  observed=freshness.timestamp(receipt.get('checked_at'));launch=freshness.timestamp(as_of)
  c.require(observed is not None and launch is not None and observed<=launch,'Source observation must precede recorded launch')
 rows=[r for r in receipt['companies'] if r['issuer_id']==old['issuer_id']]
 c.require(len(rows)==1 and rows[0]['old_packet_id']==old_id and rows[0]['new_packet_id']==new_id,'Fresh source observation must bind this exact old/new packet')
 c.require(len(rows[0]['documents'])==len(old['documents']) and all(d['status'] in ('raw_identical','already_fresh','scoped_transcript_currentness_verified','identical_extracted_text_fiscal_tags_and_structured_facts') for d in rows[0]['documents']),'Every original source must be revalidated without substantive change')
 c.require({d['source_url'] for d in rows[0]['documents']}=={d['source_url'] for d in old['documents']},'Observation source membership changed')
 from .source_parse import extract
 from . import financial_evidence as financial
 fresh={d['document_id']:d for d in current['documents']};observations={d['source_url']:d for d in rows[0]['documents']};equivalent=set()
 for doc in old['documents']:
  c.require(doc['document_id'] in fresh,'Original document disappeared');newdoc=fresh[doc['document_id']]
  if doc['raw_sha256']==newdoc['raw_sha256']:continue
  observation=observations[doc['source_url']]
  c.require(observation['status']=='identical_extracted_text_fiscal_tags_and_structured_facts' and observation['expected_sha256']==doc['raw_sha256'] and observation['observed_sha256']==newdoc['raw_sha256'],'Different raw source needs exact equivalence observation')
  oldbody=library.load_bytes(root,doc['raw_path'],doc['raw_sha256']);newbody=library.load_bytes(root,newdoc['raw_path'],newdoc['raw_sha256'])
  c.require(library.load_bytes(root,observation['raw_path'],observation['observed_sha256'])==newbody,'Fresh observed bytes differ from successor source')
  c.require(equivalent_html(oldbody,newbody,doc['source_url'],doc,extract,financial),'Extracted source, fiscal metadata or structured facts changed')
  equivalent.add(doc['document_id'])
 same_content(old,current,equivalent)
 return old,new

def prepare(root,old_id,new_id,receipt,output):
 root=Path(root).resolve();receipt=library.resolve(root,receipt);old,new=checked(root,old_id,new_id,receipt)
 record={'version':VERSION,'old_packet_id':old_id,'new_packet_id':new_id,'old_packet_sha256':b.sha(root/f'library/packets/{old_id}.json'),'new_packet_sha256':b.sha(root/f'library/packets/{new_id}.json'),'source_receipt':str(receipt.relative_to(root)),'source_receipt_sha256':b.sha(receipt)}
 c.require(not Path(output).exists(),'New immutable currentness proof required');c.write(output,record);return record

def verify(root,path,*,as_of=None):
 root=Path(root).resolve();v=b.read(path)
 if v.get('version')=='authenticated-two-link-source-currentness-v1':
  from . import earnings_source_chain
  return earnings_source_chain.verify(root,path,as_of=as_of)
 packet_ids(v['old_packet_id'],v['new_packet_id']);c.require(v['version']==VERSION,'Known exact-source currentness proof required');receipt=library.resolve(root,v['source_receipt'])
 c.require(v['old_packet_sha256']==b.sha(root/f"library/packets/{v['old_packet_id']}.json") and v['new_packet_sha256']==b.sha(root/f"library/packets/{v['new_packet_id']}.json") and v['source_receipt_sha256']==b.sha(receipt),'Currentness proof sources changed')
 old,_=checked(root,v['old_packet_id'],v['new_packet_id'],receipt,**({} if as_of is None else {'as_of':as_of}));return old

def input_bindings(root,path,*,as_of=None):
 root=Path(root).resolve();path=Path(path);path=library.resolve(root,str(path.relative_to(root)) if path.is_absolute() else str(path));v=b.read(path)
 if v.get('version')=='authenticated-two-link-source-currentness-v1':
  c.require(as_of is None,'Nested historical chains unsupported')
  from . import earnings_source_chain
  return earnings_source_chain.bindings(root,path)
 old=verify(root,path,as_of=as_of);new=b.read(root/f"library/packets/{v['new_packet_id']}.json")
 names={str(path.relative_to(root)),v['source_receipt']}
 for packet in (old,new):
  names.add('library/packets/'+packet['packet_id']+'.json');names.add('library/snapshots/'+packet['catalog_id']+'.json')
  for doc in packet['documents']:
   names.update((doc['raw_path'],doc['text_path'],'library/qualifications/'+doc['qualification_id']+'.json'))
 for row in b.read(root/v['source_receipt'])['companies']:
  if row['issuer_id']==old['issuer_id']:
   names.update(doc['raw_path'] for doc in row['documents'] if doc.get('raw_path'))
 receipt=b.read(root/v['source_receipt']);derivation=receipt.get('derivation',{})
 if derivation.get('version')=='authenticated-nasdaq-market-open-source-qualification-v1':
  from . import transcript_nasdaq_transition as nasdaq
  names.update(nasdaq.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('version')=='authenticated-kase-source-qualification-v1':
  from . import transcript_kase_transition as kase
  names.update(kase.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('version')=='authenticated-tsx-app-rating-legacy-source-v1':
  from . import transcript_tsx_legacy_transition as tsx_legacy
  names.update(tsx_legacy.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('version')=='authenticated-footer-app-rating-source-qualification-v1':
  from . import transcript_app_rating_transition as rating
  names.update(rating.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('version')=='authenticated-market-open-widget-source-qualification-v1':
  from . import transcript_market_widget_transition as widget
  names.update(widget.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('version')=='authenticated-listing-header-source-qualification-v1':
  from . import transcript_listing_transition as listing
  names.update(listing.verify_derivation(root,receipt,historical=as_of is not None))
 if derivation.get('legacy_equivalence'):
  from . import legacy_equivalent_source as legacy
  reference=derivation['legacy_equivalence'];proof_path=library.resolve(root,reference['path']);proof=legacy.verify(root,proof_path);names.update(proof['input_sha256']);names.update((reference['path'],derivation['manifest_path'],derivation['original_receipt']))
 result={name:b.sha(library.resolve(root,name)) for name in names}
 from .transcript_currentness import bindings
 for doc in new['documents']:result.update(bindings(root,doc,historical=as_of is not None))
 return result

def validate_request(root,request):
 root=Path(root).resolve()
 ref=request['spec']['source_currentness'];path=library.resolve(root,ref['path'])
 c.require(set(ref)=={'path','sha256'} and b.sha(path)==ref['sha256'] and request['input_sha256'].get(ref['path'])==ref['sha256'],'Explicit bound currentness proof required')
 old=verify(root,path)
 c.require(all(old[k]==request['spec'][k] for k in ('packet_id','issuer_id','period')),'Currentness proof belongs to another report')
 c.require(all(request['input_sha256'].get(name)==digest for name,digest in input_bindings(root,path).items()),'Every currentness source/proof must remain bound')
 return old
