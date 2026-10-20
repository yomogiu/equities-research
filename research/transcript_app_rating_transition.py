"""Replay one exact rejected quote-widget observation; originals stay immutable."""
import copy
from . import library,transcript_currentness as scope
from .contracts import require
from .freshness import timestamp
VERSION='authenticated-footer-app-rating-source-qualification-v1'
def verify_derivation(root,receipt,*,historical=False):
 d=receipt.get('derivation',{});require(d.get('version')==VERSION and set(d)=={'version','original_receipt','original_receipt_sha256','scoped_currentness'},'Exact market-widget derivation required')
 path=library.resolve(root,d['original_receipt']);require(scope.sha(path.read_bytes())==d['original_receipt_sha256'],'Original rejected receipt changed');original=library.read_json(path);require('derivation' not in original and len(original['companies'])==len(receipt['companies'])==1,'Original single issuer receipt required')
 proof=scope.replay(root,d['scoped_currentness'],historical=historical);require(proof['version']==scope.APP_RATING_VERSION and proof['issuer_id']==original['companies'][0]['issuer_id'],'Exact explicit widget proof required')
 expected=copy.deepcopy(original);row=expected['companies'][0];rows=[x for x in row['documents']if x['source_url']==proof['source_url']];require(len(rows)==1,'Unique same-URL observation required');doc=rows[0]
 require(doc['status']=='changed_requires_review' and doc.get('scope_reason')=='Complete transcript, metadata or non-widget content changed' and doc['expected_sha256']==proof['archived']['raw_sha256'] and doc['observed_sha256']==proof['observed']['raw_sha256'] and doc['raw_path']==proof['observed']['raw_path'] and timestamp(doc['checked_at'])==proof['checked_at'],'Exact rejected widget fetch required')
 doc.update(status='scoped_transcript_currentness_verified',scoped_currentness=d['scoped_currentness']);doc.pop('scope_reason');row['new_packet_id']=receipt['companies'][0]['new_packet_id'];expected['derivation']=d;require(expected==receipt,'Only verified widget status and rebuilt packet may change');return {d['original_receipt']:d['original_receipt_sha256']}
