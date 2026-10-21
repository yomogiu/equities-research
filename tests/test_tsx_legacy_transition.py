import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_legacy_equivalent_source as legacy_tests
import test_transcript_app_rating as rating_tests
from test_transcript_currentness import html
from research import transcript_currentness as t,transcript_tsx_legacy_transition as combined,legacy_equivalent_source as legacy,library,source_parse
from research.contracts import digest
class TsxLegacy(unittest.TestCase):
 def test_tsx_rating_roundtrip_explicit_only(self):
  url='https://stockanalysis.com/quote/tsx/FAKE/transcripts/123-q2-2026/'
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();a=rating_tests.AppRatingTest().fixture();b=a.replace(b'>4.9<',b'>4.8<');text=source_parse.page(a,url).text.encode()
   for n,body in [('old.html',a),('old.txt',text),('sources/test/objects/new.html',b)]:
    p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
   q={'document_id':digest(['issuer:fake',t.sha(text)]),'text_sha256':t.sha(text),'period':'FY2026-Q2','kind':'transcript','completeness':'full','source_accepted':True,'source_spans':[{'start':0,'end':9,'text':text.decode()[:9]}]};qid=digest(q);library.save(r/'library/qualifications'/(qid+'.json'),q);stamp='2026-10-20T12:00:00+00:00';library.save(r/'sources/test/http-cache.json',{url:{'sha256':t.sha(b),'checked_at':stamp,'final_url':url,'content_type':'text/html','body_path':'objects/new.html'}});doc={'source_url':url,'raw_path':'old.html','raw_sha256':t.sha(a),'text_path':'old.txt','text_sha256':t.sha(text),'qualification_id':qid};obs={'raw_path':'sources/test/objects/new.html','observed_sha256':t.sha(b),'checked_at':stamp};packet={'issuer_id':'issuer:fake','period':'FY2026-Q2'}
   ref=t.create(r,packet,doc,obs,'sources/test/http-cache.json',tsx_app_rating=True);self.assertEqual(t.replay(r,ref)['version'],t.TSX_APP_RATING_VERSION)
   forged=library.read_json(r/ref['path']);forged['source_url']='https://stockanalysis.com/stocks/fake/transcripts/123-q2-2026/';library.save(r/'forged.json',forged)
   with self.assertRaisesRegex(ValueError,'Exact TSX app-rating URL required'):t.replay(r,{'path':'forged.json','sha256':t.sha((r/'forged.json').read_bytes())})
   with self.assertRaises(ValueError):t.compare(a,b,url)
   with self.assertRaises(ValueError):t.create(r,packet,{**doc,'source_url':'https://stockanalysis.com/stocks/fake/transcripts/123-q2-2026/'},obs,'sources/test/http-cache.json',tsx_app_rating=True)
 def test_combined_original_receipt_and_legacy_manifest(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();args=legacy_tests.LegacyTests().fixture(r);proof=r/'annual-proof.json';receipt=library.read_json(r/args[2]);row=receipt['companies'][0];url='https://stockanalysis.com/quote/tsx/FAKE/transcripts/123-q2-2026/';obs={'document_id':'transcript','checked_at':'2026-10-20T12:00:00+00:00','source_url':url,'expected_sha256':'a'*64,'observed_sha256':'b'*64,'raw_path':'new-transcript.bin','status':'changed_requires_review','scope_reason':'Unsupported transcript publisher URL'};row['documents'].append(obs);library.save(r/args[2],receipt)
   # Bind the annual derivation to the complete immutable receipt before testing.
   legacy.prepare(r,*args,proof);applied=legacy.apply(r,proof)
   scope={'checked_at':'2026-10-20T12:00:00+00:00','version':t.TSX_APP_RATING_VERSION,'issuer_id':row['issuer_id'],'source_url':url,'archived':{'raw_sha256':'a'*64},'observed':{'raw_sha256':'b'*64,'raw_path':'new-transcript.bin'}};ref={'path':'scope.json','sha256':'c'*64};derived=copy.deepcopy(receipt);rr=derived['companies'][0];rr['new_packet_id']='new';rr['documents'][0].update(status='identical_extracted_text_fiscal_tags_and_structured_facts',manifest_path=applied['manifest_path']);rr['documents'][0].pop('reason');rr['documents'][1].update(status='scoped_transcript_currentness_verified',scoped_currentness=ref);rr['documents'][1].pop('scope_reason');derived['derivation']={'version':combined.VERSION,'original_receipt':args[2],'original_receipt_sha256':t.sha((r/args[2]).read_bytes()),'scoped_currentness':ref,'legacy_equivalence':{'path':'annual-proof.json','sha256':t.sha(proof.read_bytes())},'manifest_path':applied['manifest_path'],'manifest_sha256':t.sha((r/applied['manifest_path']).read_bytes())}
   with patch.object(t,'replay',return_value=scope):
    combined.verify_derivation(r,derived)
    bad=copy.deepcopy(derived);bad['companies'][0]['documents'][0]['expected_sha256']='0'*64
    with self.assertRaises(ValueError):combined.verify_derivation(r,bad)
    bad=copy.deepcopy(derived);bad['companies'][0]['documents'][1]['raw_path']='other.bin'
    with self.assertRaises(ValueError):combined.verify_derivation(r,bad)
