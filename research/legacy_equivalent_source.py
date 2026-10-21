"""Import an equivalent SEC annual HTML version from authenticated legacy evidence.

The new collector artifact explicitly records its derived origin. Original audit,
qualification, packet, HTTP receipt and source objects remain immutable. No fiscal
classification or evidence address is inferred from a filename or filing date.
"""
from pathlib import Path
import os,copy
from urllib.parse import urlsplit
from . import library,source_parse,financial_evidence
from .contracts import digest,require
from .freshness import timestamp
from . import earnings_source_revalidation as equivalent
VERSION='authenticated-legacy-annual-equivalence-v1'

def select_legacy(audit,doc,issuer):
 matches=[]
 def visit(v):
  if isinstance(v,dict):
   if v.get('issuer_id')==issuer and v.get('url')==doc['source_url'] and all(v.get(k)==doc[k] for k in ('raw_sha256','text_sha256')):matches.append(v)
   for value in v.values():visit(value)
  elif isinstance(v,list):
   for value in v:visit(value)
 visit(audit)
 require(len(matches)==1,'Exactly one original legacy source record required');row=matches[0]
 require(row.get('status')=='extracted' and row.get('qualification_status')=='accepted_financial_material','Accepted original legacy financial source required')
 return row

def derive(root,packet_id,document_id,receipt_path,cache_path):
 root=Path(root).resolve();packet_path='library/packets/'+packet_id+'.json';packet=library.read_json(library.resolve(root,packet_path));require(packet['packet_id']==packet_id,'Original packet identity changed')
 docs=[d for d in packet['documents'] if d['catalog_document_id']==document_id];require(len(docs)==1,'Exact original document required');doc=docs[0]
 require(doc['kind']=='annual_background' and doc['publisher_type']=='regulator' and urlsplit(doc['source_url']).hostname=='www.sec.gov','Only qualified SEC annual background supported')
 catalog_path='library/snapshots/'+packet['catalog_id']+'.json';catalog=library.read_json(library.resolve(root,catalog_path));require(digest({k:v for k,v in catalog.items() if k!='catalog_id'})==packet['catalog_id'],'Original catalog identity changed')
 catalog_doc=catalog['documents'][doc['catalog_document_id']];require(catalog_doc['issuer_id']==packet['issuer_id'] and catalog_doc['text_sha256']==doc['text_sha256'],'Original catalog source ownership changed')
 variants=[s for s in catalog_doc['sources'] if s['source_url']==doc['source_url'] and s['raw_sha256']==doc['raw_sha256'] and s['text_sha256']==doc['text_sha256']];require(len(variants)==1,'Unique original catalog variant required');legacy_path=variants[0]['provenance'];require(legacy_path.startswith('reports/retrieval/') and not catalog_doc['collector_ids'],'Uncollected authenticated legacy source required')
 row=select_legacy(library.read_json(library.resolve(root,legacy_path)),doc,packet['issuer_id'])
 qpath='library/qualifications/'+doc['qualification_id']+'.json';q=library.read_json(library.resolve(root,qpath));require(digest(q)==doc['qualification_id'] and q['document_id']==doc['catalog_document_id']==digest([packet['issuer_id'],doc['text_sha256']]) and all(q[k]==doc[k] for k in ('kind','period','completeness','publisher_type','text_sha256')) and q.get('source_accepted') is True,'Original annual qualification changed')
 receipt=library.read_json(library.resolve(root,receipt_path));companies=[x for x in receipt['companies'] if x['issuer_id']==packet['issuer_id'] and x['old_packet_id']==packet_id];require(len(companies)==1,'Exact original refresh receipt required');observations=[d for d in companies[0]['documents'] if d['document_id']==document_id and d['source_url']==doc['source_url'] and d['expected_sha256']==doc['raw_sha256']];require(len(observations)==1,'Unique exact original observation required');observed=observations[0]
 require(observed.get('status')=='blocked' and observed.get('reason')=='No collector manifest for equivalent version','Only exact missing legacy collector failure supported')
 cache=library.read_json(library.resolve(root,cache_path));http=cache[doc['source_url']];require(http['sha256']==observed['observed_sha256'] and timestamp(http['checked_at'])==timestamp(observed['checked_at']) and http['final_url']==doc['source_url'] and 'html' in http['content_type'],'Actual same-URL HTML fetch required')
 cache_file=library.resolve(root,cache_path);body=(cache_file.parent/http['body_path']).resolve();require(body==library.resolve(root,observed['raw_path']) and body.is_relative_to(root),'Observed body path changed')
 old=library.load_bytes(root,doc['raw_path'],doc['raw_sha256']);new=library.load_bytes(root,observed['raw_path'],observed['observed_sha256']);text=library.load_bytes(root,doc['text_path'],doc['text_sha256']);require(library.load_bytes(root,row['raw_path'],row['raw_sha256'])==old and library.load_bytes(root,row['text_path'],row['text_sha256'])==text,'Legacy source objects differ')
 require(equivalent.equivalent_html(old,new,doc['source_url'],doc,source_parse.extract,financial_evidence),'Complete extracted text/fiscal metadata/structured facts must match')
 extracted,fiscal,status=source_parse.extract(new,'text/html',doc['source_url']);require(status=='extracted' and extracted.encode()==text,'Exact original extracted text required')
 inputs={p:library.sha(library.resolve(root,p).read_bytes()) for p in {packet_path,catalog_path,qpath,legacy_path,receipt_path,cache_path,doc['raw_path'],doc['text_path'],row['raw_path'],row['text_path'],observed['raw_path']}}
 collector_id=digest([VERSION,doc['catalog_document_id'],doc['source_url'],digest(row)])
 manifest={'document_id':collector_id,'issuer_id':packet['issuer_id'],'symbol':row['symbol'],'issuer':row['issuer'],'source_url':doc['source_url'],'final_url':http['final_url'],'publisher_type':q['publisher_type'],'kind':q['kind'],'title':row.get('form') or q['kind'],'retrieved_at':timestamp(http['checked_at']),'raw_path':os.path.relpath(body,root/'collection'),'raw_sha256':http['sha256'],'text_path':os.path.relpath(library.resolve(root,doc['text_path']),root/'collection'),'text_sha256':doc['text_sha256'],'parse_status':'extracted','characters':len(extracted),'fiscal_tags':fiscal,'completeness':q['completeness'],'metadata':{'legacy_source_provenance':legacy_path,'legacy_source_record_sha256':digest(row),'source_qualification_id':doc['qualification_id'],'derived_equivalence_version':VERSION}}
 for k in ('form','filing_date','report_date'): 
  if k in row:manifest[k]=row[k]
 return {'version':VERSION,'packet_id':packet_id,'document_id':document_id,'receipt_path':receipt_path,'cache_path':cache_path,'input_sha256':inputs,'manifest':manifest,'original_source_record_sha256':digest(row),'qualification_promoted':False}

def prepare(root,packet_id,document_id,receipt_path,cache_path,output):
 value=derive(root,packet_id,document_id,receipt_path,cache_path);library.save(Path(output),value,immutable=True);return value

def verify(root,path):
 value=library.read_json(path);require(value==derive(root,value['packet_id'],value['document_id'],value['receipt_path'],value['cache_path']),'Legacy equivalent derivation changed');return value

def apply(root,path):
 root=Path(root).resolve();v=verify(root,path);m=copy.deepcopy(v['manifest']);m['metadata']['equivalence_proof']=str(Path(path).resolve().relative_to(root));m['metadata']['equivalence_proof_sha256']=library.sha(Path(path).read_bytes())
 relative='documents/'+m['issuer_id'].replace(':','-')+'/'+m['document_id']+'-'+m['raw_sha256']+'.json';library.save(root/'collection'/relative,m,immutable=True)
 index_path=root/'collection/document-index.json';index=library.read_json(index_path);brief={k:m[k] for k in ('document_id','issuer_id','symbol','kind','title','source_url','raw_sha256','text_path','retrieved_at')};brief['manifest_path']=relative
 require(m['document_id'] not in index or index[m['document_id']]==brief,'Conflicting derived collector identity');index[m['document_id']]=brief;library.save(index_path,index);return {'manifest_path':'collection/'+relative,'document_id':m['document_id'],'proof_path':str(Path(path).resolve().relative_to(root))}
