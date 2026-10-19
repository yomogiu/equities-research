"""Fictitious issuers and documents only."""
import copy,json,tempfile,unittest
from pathlib import Path
from research import transcript_listing_transition as listing,transcript_currentness as scope
from test_transcript_currentness import html,URL

class ListingTests(unittest.TestCase):
 def info(self):return {'issuer_id':'sec:0000000001','company_name':'Fictional LP','ticker':'FAKE','currency':'USD','from_exchange':'NYSE','to_exchange':'TXSE','effective_date':'2026-10-05'}
 def pages(self):
  label='<div>Fictional LP (FAKE)</div><div class="mt-px text-tiny text-faded">NYSE: FAKE · Real-Time Price · USD</div>'
  old=html().replace(b'<h1>',label.encode()+b'<h1>');return old,old.replace(b'>NYSE: FAKE',b'>TXSE: FAKE')
 def test_explicit_header_only_and_legacy_stays_strict(self):
  old,new=self.pages();before=bytes(old);v=listing.compare(old,new,URL,self.info());self.assertEqual(old,before);self.assertEqual(len(v['signature']['block_sha256']),1)
  with self.assertRaises(ValueError):scope.compare(old,new,URL)
  for bad in [new.replace(b'USD',b'CAD'),new.replace(b'TXSE: FAKE',b'TXSE: OTHER'),new.replace(b'dialogue',b'new claim'),new.replace(b'Q2',b'Q3'),new.replace(b'Fictional Speaker',b'Other Speaker'),new+new,new.replace(b'Fictional LP',b'Other LP')]:
   with self.subTest(bad=bad),self.assertRaises(ValueError):listing.compare(old,bad,URL,self.info())
 def fixture(self,r):
  v=self.info();v.update(version=listing.AUTHORITY_VERSION,source_url=URL,fetch_receipt_path='fetch.json')
  sec=('0000000001 FORM 8-K FICTIONAL LP (Exact name of Registrant as specified in its charter) from listing on the New York Stock Exchange (“NYSE”), and the transfer of those listings to the Texas Stock Exchange (“TXSE”). The ticker symbols for the Common Units (TXSE: FAKE) will remain unchanged. trading will begin on the TXSE at market open on October 5, 2026.')
  exchange='October 5, 2026 Fictional LP (TXSE: FAKE) held a market open bell ringing ceremony today celebrating the move of primary listings to TXSE.'
  records=[]
  for kind,text,url in [('issuer',sec,'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/test.htm'),('exchange',exchange,'https://www.txse.com/press/fictional')]:
   raw=('<html><body>'+text+'</body></html>').encode();p=r/(kind+'.html');p.write_bytes(raw);h=scope.sha(raw);v[kind+'_raw_sha256']=h;records.append({'url':url,'final_url':url,'raw_path':p.name,'raw_sha256':h,'status':200,'content_type':'text/html','at':'2026-10-19T11:00:00Z'})
  (r/'fetch.json').write_text(json.dumps(records));v['fetch_receipt_sha256']=scope.sha((r/'fetch.json').read_bytes());return v
 def test_primary_identity_receipts_timing_and_all_inputs_bound(self):
  with tempfile.TemporaryDirectory()as d:
   r=Path(d).resolve();v=self.fixture(r)
   def check(value,issuer='sec:0000000001',url=URL,at='2026-10-19T10:00:00Z'):
    p=r/'authority.json';p.write_text(json.dumps(value));return listing.authority(r,{'path':p.name,'sha256':scope.sha(p.read_bytes())},issuer,url,at)
   _,inputs=check(v);self.assertEqual(set(inputs),{'authority.json','fetch.json','issuer.html','exchange.html'})
   for key,bad in [('issuer_id','sec:0000000002'),('ticker','OTHER'),('currency','CAD'),('to_exchange','OTHER'),('effective_date','2026-10-20'),('company_name','Other LP'),('fetch_receipt_sha256','wrong')]:
    with self.subTest(key=key),self.assertRaises(ValueError):check({**v,key:bad})
   with self.assertRaises(ValueError):check(v,at='2026-10-04T10:00:00Z')
   (r/'issuer.html').write_text('changed raw')
   with self.assertRaises(ValueError):check(v)
 def test_new_receipt_replays_and_binds_all_primary_sources(self):
  from research import library,source_parse
  from research.contracts import digest
  with tempfile.TemporaryDirectory()as d:
   r=Path(d).resolve();v=self.fixture(r);library.save(r/'authority.json',v);auth={'path':'authority.json','sha256':scope.sha((r/'authority.json').read_bytes())};old,new=self.pages();text=source_parse.page(old,URL).text.encode()
   for name,body in [('old.html',old),('old.txt',text),('sources/test/objects/new.html',new)]:
    p=r/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
   q={'document_id':digest([v['issuer_id'],scope.sha(text)]),'text_sha256':scope.sha(text),'period':'FY2026-Q2','kind':'transcript','completeness':'full','source_accepted':True,'source_spans':[{'start':0,'end':9,'text':text.decode()[:9]}]};qid=digest(q);library.save(r/f'library/qualifications/{qid}.json',q)
   checked='2026-10-19T10:00:00+00:00';library.save(r/'sources/test/http-cache.json',{URL:{'sha256':scope.sha(new),'checked_at':checked,'final_url':URL,'content_type':'text/html','body_path':'objects/new.html'}})
   doc={'source_url':URL,'raw_path':'old.html','raw_sha256':scope.sha(old),'text_path':'old.txt','text_sha256':scope.sha(text),'qualification_id':qid};obs={'raw_path':'sources/test/objects/new.html','observed_sha256':scope.sha(new),'checked_at':checked}
   ref=scope.create(r,{'issuer_id':v['issuer_id'],'period':'FY2026-Q2'},doc,obs,'sources/test/http-cache.json',listing_authority=auth);actual=scope.replay(r,ref);self.assertEqual(actual['version'],scope.LISTING_VERSION)
   doc.update(scoped_currentness=ref,scoped_checked_at=checked,source_check_status=scope.STATUS);bindings=scope.bindings(r,doc);self.assertTrue({'authority.json','fetch.json','issuer.html','exchange.html'}<=set(bindings))
   (r/'exchange.html').write_text('different primary body')
   with self.assertRaises(ValueError):scope.replay(r,ref)
