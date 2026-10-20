"""Synthetic footer ratings; original comparator remains strict."""
import unittest
from test_transcript_currentness import html,URL
from research import transcript_currentness as t
class AppRatingTest(unittest.TestCase):
 def fixture(self):
  links=''.join('<a href="'+u+'"><span class="font-semibold text-green-500">4.9</span><span class="text-gray-400">7.0K</span></a>' for u in ('https://apps.apple.com/us/app/stock-analysis-app/id6751272467','https://play.google.com/store/apps/details?id=com.stockanalysis.app'))
  return html().replace(b'Fictional attribution',links.encode())
 def test_opt_in_only(self):
  a=self.fixture();b=a.replace(b'>4.9<',b'>4.8<');t.compare(a,b,URL,allow_app_ratings=True)
  with self.assertRaises(ValueError):t.compare(a,b,URL)
 def test_rejects_unrelated_mutations(self):
  a=self.fixture();b=a.replace(b'>4.9<',b'>4.8<')
  for bad in (b.replace(b'dialogue',b'new claim'),b.replace(b'Q2',b'Q3'),b.replace(b'>4.8<',b'>5.1<'),b.replace(b'id6751272467',b'id9999999999'),b.replace(b'>4.8<',b'>profit<'),b.replace(b'</a>',b'<span class="font-semibold text-green-500">4.7</span></a>'),b.replace(b'<footer>',b'<section>').replace(b'</footer>',b'</section>')):
   with self.subTest(bad=bad),self.assertRaises(ValueError):t.compare(a,bad,URL,allow_app_ratings=True)
 def test_create_replay_and_derived_receipt(self):
  import tempfile
  from pathlib import Path
  from research import source_parse,library,transcript_app_rating_transition as rating
  from research.contracts import digest
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp).resolve();a=self.fixture().replace(b'<body>',b'<body><script>quartrEventId:123,fiscalYear:2026,quarterLabel:"Q2 2026"</script>'+b'<ul aria-label="Downloads"><li><a href="/filings/FAKE/456/" class="pill"><span>Quarterly report</span></a></li></ul>'*2);b=a.replace(b'>4.9<',b'>4.8<');text=source_parse.page(a,URL).text.encode()
   for n,body in [('old.html',a),('old.txt',text),('sources/test/objects/new.html',b)]:
    p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
   q={'document_id':digest(['issuer:fake',t.sha(text)]),'text_sha256':t.sha(text),'period':'FY2026-Q2','kind':'transcript','completeness':'full','source_accepted':True,'source_spans':[{'start':0,'end':9,'text':text.decode()[:9]}]};qid=digest(q);library.save(r/'library/qualifications'/ (qid+'.json'),q)
   stamp='2026-10-05T12:00:00+00:00';library.save(r/'sources/test/http-cache.json',{URL:{'sha256':t.sha(b),'checked_at':stamp,'final_url':URL,'content_type':'text/html','body_path':'objects/new.html'}})
   doc={'source_url':URL,'raw_path':'old.html','raw_sha256':t.sha(a),'text_path':'old.txt','text_sha256':t.sha(text),'qualification_id':qid};obs={'source_url':URL,'raw_path':'sources/test/objects/new.html','expected_sha256':t.sha(a),'observed_sha256':t.sha(b),'checked_at':stamp,'status':'changed_requires_review','scope_reason':'Complete transcript, metadata or non-widget content changed'}
   ref=t.create(r,{'issuer_id':'issuer:fake','period':'FY2026-Q2'},doc,obs,'sources/test/http-cache.json',market_open=True,app_rating=True);self.assertEqual(t.replay(r,ref)['version'],t.APP_RATING_VERSION)
   import copy
   original={'companies':[{'issuer_id':'issuer:fake','new_packet_id':'old','documents':[obs]}]};library.save(r/'receipt.json',original);derived=copy.deepcopy(original);derived['companies'][0]['new_packet_id']='new';derived['companies'][0]['documents'][0].update(status='scoped_transcript_currentness_verified',scoped_currentness=ref);derived['companies'][0]['documents'][0].pop('scope_reason');derived['derivation']={'version':rating.VERSION,'original_receipt':'receipt.json','original_receipt_sha256':t.sha((r/'receipt.json').read_bytes()),'scoped_currentness':ref};rating.verify_derivation(r,derived)
   original['companies'][0]['documents'][0]['scope_reason']='Unrecognized quote widget';library.save(r/'receipt.json',original);derived['derivation']['original_receipt_sha256']=t.sha((r/'receipt.json').read_bytes());rating.verify_derivation(r,derived)
   original['companies'][0]['documents'][0]['scope_reason']='Unknown changed business claim';library.save(r/'receipt.json',original);derived['derivation']['original_receipt_sha256']=t.sha((r/'receipt.json').read_bytes())
   with self.assertRaises(ValueError):rating.verify_derivation(r,derived)
   original['companies'][0]['documents'][0]['scope_reason']='Unrecognized quote widget';library.save(r/'receipt.json',original);derived['derivation']['original_receipt_sha256']=t.sha((r/'receipt.json').read_bytes())
   derived['companies'][0]['documents'][0]['expected_sha256']='0'*64
   with self.assertRaises(ValueError):rating.verify_derivation(r,derived)
