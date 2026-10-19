"""Reuse independently reviewed HTML cells only when every source span is exact.

No profile/review is rewritten or re-signed. Current observations are derived from
original approved semantics and identical same-offset source bytes, with full
extracted text/fiscal/fact equivalence and both raw objects explicitly bound.
"""
from pathlib import Path
from urllib.parse import urlsplit
import copy,json
from . import financial_html_tables as adapter, financial_evidence as financial
from . import earnings_source_revalidation as equivalent,source_parse
VERSION='exact-reviewed-financial-spans-v1'

def extract(raw_bytes,source,profile_bytes,review_bytes,authorization):
 adapter.fields(authorization,('version','enabled','source','original_authorization','original_raw_path','source_url','profile_sha256','review_sha256'),'financial span currentness authorization')
 adapter.require(authorization['version']==VERSION and authorization['enabled'] is True and authorization['source']==source,'Exact current source authorization required')
 original=authorization['original_authorization'];old_source=original['source'];old=Path(authorization['original_raw_path']).read_bytes()
 adapter.require(all(source[k]==old_source[k] for k in ('document_id','text_sha256','issuer_id')),'Reviewed source identity/text changed')
 adapter.require(authorization['profile_sha256']==original['profile_sha256'] and authorization['review_sha256']==original['review_sha256'],'Original reviewed artifacts changed')
 accepted=adapter.extract(old,old_source,profile_bytes,review_bytes,original)
 adapter.require(financial.digest(raw_bytes)==source['raw_sha256'],'Current raw source changed')
 adapter.require(urlsplit(authorization['source_url']).hostname=='www.sec.gov','Reviewed span transition requires an explicit SEC source URL')
 adapter.require(equivalent.equivalent_html(old,raw_bytes,authorization['source_url'],old_source,source_parse.extract,financial),'Complete extracted text/fiscal/structured facts changed')
 def spans(v):
  if isinstance(v,dict):
   if set(v)=={'start','end','raw_span_sha256'}:yield v
   for x in v.values():yield from spans(x)
  elif isinstance(v,list):
   for x in v:yield from spans(x)
 original_html=old.decode('utf-8');current_html=raw_bytes.decode('utf-8');profile=json.loads(profile_bytes)
 for span in spans(profile['observations']):
  a,b=span['start'],span['end'];adapter.require(original_html[a:b]==current_html[a:b] and financial.digest(current_html[a:b].encode())==span['raw_span_sha256'],'Reviewed financial span moved or changed')
 observations=copy.deepcopy(accepted['observations'])
 for row in observations:
  row['source_raw_sha256']=source['raw_sha256'];row['observation_id']=financial.digest(financial.canonical({k:v for k,v in row.items() if k!='observation_id'}))
 artifact=financial.make_artifact(source,observations);artifact['html_table_review']=copy.deepcopy(authorization)
 return financial.seal(artifact,'artifact_sha256')
