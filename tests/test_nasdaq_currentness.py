"""Fictitious primary sources, strict negative checks and serialized replay."""
import copy,json,tempfile,unittest
from pathlib import Path
from research import transcript_nasdaq_transition as n,transcript_currentness as t,library,source_parse
from research.contracts import digest
from test_market_open_currentness import page,OPEN,URL

class NasdaqTests(unittest.TestCase):
 def info(self):
  return dict(version=n.AUTHORITY_VERSION,issuer_id='sec:0000000001',company_name='Fictional Technologies, Inc.',issuer_brand='Fictional',issuer_domain='fictional.com',ticker='FAKE',currency='USD',from_exchange='NYSE',to_exchange='NASDAQ',effective_date='2026-10-06',nyse_final_date='2026-10-05',source_url=URL,fetch_receipt_path='fetch.json')
 def pages(self):
  label='<div>Fictional Technologies, Inc. (FAKE)</div><div class="mt-px text-tiny text-faded">NYSE: FAKE · Real-Time Price · USD</div>'
  old=page().replace(b'<body>',b'<body>'+label.encode());new=page(OPEN,True).replace(b'<body>',b'<body>'+label.replace('>NYSE:', '>NASDAQ:').encode());return old,new
 def fixture(self,r,mutate=None):
  v=self.info();sec='0000000001 FORM 8-K Fictional Technologies, Inc. (Exact name of registrant as specified in its charter) approved the transfer of the listings of the Securities to The Nasdaq Stock Market LLC (“Nasdaq”). The Securities have been approved for listing on Nasdaq, where the Common Stock is expected to continue trading under the symbol “FAKE,” de-listed from the NYSE at the close of trading on October 5, 2026 and listed on Nasdaq effective at the opening of trading on October 6, 2026.'
  ex='On October 6, 2026, Fictional Technologies, Inc. (NYSE: FAKE) is expected to be listed and begin trading on the Nasdaq Global Select Market under the same ticker symbol FAKE. NYSE Ticker through October 5, 2026 Nasdaq Ticker as of October 6, 2026 <a href="https://ir.fictional.com/news/transfer">Issuer announcement</a>'
  rows=[]
  for kind,text,url in [('issuer',sec,'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/test.htm'),('exchange',ex,'https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-99'),('completion','Today, Fictional begins trading on Nasdaq.','https://www.fictional.com/blog/transfer')]:
   if mutate:text,url=mutate(kind,text,url)
   raw=('<html><body>'+text+'</body></html>').encode();(r/(kind+'.html')).write_bytes(raw);h=t.sha(raw);v[kind+'_raw_sha256']=h;rows.append(dict(url=url,final_url=url,raw_path=kind+'.html',raw_sha256=h,status=200,content_type='text/html',at='2026-10-19T14:05:00Z'))
  library.save(r/'fetch.json',rows);v['fetch_receipt_sha256']=t.sha((r/'fetch.json').read_bytes());return v
 def check(self,r,v,at='2026-10-19T14:00:00Z'):
  library.save(r/'authority.json',v);ref=dict(path='authority.json',sha256=t.sha((r/'authority.json').read_bytes()));return n.authority(r,ref,v['issuer_id'],URL,at)
 def test_primary_authority_and_negative_identity_route_timing(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();v=self.fixture(r);_,bound=self.check(r,v);self.assertEqual(len(bound),5)
   for key,value in [('issuer_id','sec:0000000002'),('company_name','Other Technologies, Inc.'),('ticker','OTHER'),('currency','CAD'),('to_exchange','TXSE'),('effective_date','2026-10-20'),('nyse_final_date','2026-10-06'),('issuer_domain','other.com'),('fetch_receipt_sha256','changed')]:
    with self.subTest(key=key),self.assertRaises(ValueError):self.check(r,{**v,key:value})
   with self.assertRaises(ValueError):self.check(r,v,'2026-10-05T14:00:00Z')
 def test_rehashed_bad_primary_content_and_domain_provenance_rejected(self):
  cases=[('issuer','FAKE,”','OTHER,”'),('issuer','0000000001','0000000002'),('issuer','October 6','October 7'),('exchange','same ticker symbol FAKE.','same ticker symbol OTHER.'),('exchange','ir.fictional.com','ir.other.com'),('completion','begins trading','expects to trade')]
  for kind,before,after in cases:
   with self.subTest(kind=kind,before=before),tempfile.TemporaryDirectory()as tmp:
    r=Path(tmp).resolve();v=self.fixture(r,lambda k,text,url:(text.replace(before,after)if k==kind else text,url))
    with self.assertRaises(ValueError):self.check(r,v)
  for kind in ['issuer','exchange','completion']:
   with self.subTest(host=kind),tempfile.TemporaryDirectory()as tmp:
    r=Path(tmp).resolve();v=self.fixture(r,lambda k,text,url:(text,url.replace('https://www.','https://untrusted.')if k==kind else url))
    with self.assertRaises(ValueError):self.check(r,v)
 def test_actual_fetch_certainty_and_raw_integrity_are_required(self):
  for key,value in [('status',403),('final_url','https://other.example/'),('content_type','application/json'),('at','2026-10-05T14:00:00Z')]:
   with self.subTest(key=key),tempfile.TemporaryDirectory()as tmp:
    r=Path(tmp).resolve();v=self.fixture(r);rows=library.read_json(r/'fetch.json');rows[2][key]=value;library.save(r/'fetch.json',rows);v['fetch_receipt_sha256']=t.sha((r/'fetch.json').read_bytes())
    with self.assertRaises(ValueError):self.check(r,v)
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();v=self.fixture(r);rows=library.read_json(r/'fetch.json');rows.append(rows[0]);library.save(r/'fetch.json',rows);v['fetch_receipt_sha256']=t.sha((r/'fetch.json').read_bytes())
   with self.assertRaises(ValueError):self.check(r,v)
   v=self.fixture(r);(r/'issuer.html').write_text('changed primary bytes')
   with self.assertRaises(ValueError):self.check(r,v)
 def test_only_unique_outside_call_header_and_strict_widget_changes(self):
  before,after=self.pages();v=self.info();result=n.compare(before,after,URL,v);self.assertEqual(result,json.loads(json.dumps(result)));self.assertEqual(len(result['signature']['block_sha256']),1)
  with self.assertRaises(ValueError):t.compare(before,after,URL,allow_market_open=True)
  for bad in [after+after,after.replace(b'USD',b'CAD'),after.replace(b'NASDAQ: FAKE',b'NASDAQ: OTHER'),after.replace(b'original source text',b'new claim'),after.replace(b'<title>Fictional',b'<title>Changed'),after.replace(b'9:50 AM EDT',b'19:50 AM EDT'),after.replace(b'/FAKE/100/',b'/FAKE/101/'),after.replace(b'quartrEventId:123',b'quartrEventId:124'),after.replace(b'Fictional Technologies',b'Other Technologies')]:
   with self.assertRaises(ValueError):n.compare(before,bad,URL,v)
 def test_full_create_save_replay_bindings_and_immutable_failed_receipt(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();v=self.fixture(r);self.check(r,v);auth=dict(path='authority.json',sha256=t.sha((r/'authority.json').read_bytes()));old,new=self.pages();text=source_parse.page(old,URL).text.encode()
   for name,raw in [('old.html',old),('old.txt',text),('sources/test/objects/new.html',new)]:
    p=r/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
   q=dict(document_id=digest([v['issuer_id'],t.sha(text)]),text_sha256=t.sha(text),period='FY2026-Q2',kind='transcript',completeness='full',source_accepted=True,source_spans=[dict(start=0,end=9,text=text.decode()[:9])]);qid=digest(q);library.save(r/f'library/qualifications/{qid}.json',q)
   checked='2026-10-19T14:00:00+00:00';library.save(r/'sources/test/http-cache.json',{URL:dict(sha256=t.sha(new),checked_at=checked,final_url=URL,content_type='text/html',body_path='objects/new.html')});doc=dict(source_url=URL,raw_path='old.html',raw_sha256=t.sha(old),text_path='old.txt',text_sha256=t.sha(text),qualification_id=qid);obs=dict(raw_path='sources/test/objects/new.html',observed_sha256=t.sha(new),checked_at=checked)
   with self.assertRaises(ValueError):t.create(r,dict(issuer_id=v['issuer_id'],period='FY2026-Q2'),doc,obs,'sources/test/http-cache.json',nasdaq_authority=auth,market_open=True)
   ref=t.create(r,dict(issuer_id=v['issuer_id'],period='FY2026-Q2'),doc,obs,'sources/test/http-cache.json',nasdaq_authority=auth);self.assertEqual(t.replay(r,ref)['version'],t.NASDAQ_VERSION);doc.update(scoped_currentness=ref,scoped_checked_at=checked,source_check_status=t.STATUS);self.assertTrue({'authority.json','fetch.json','issuer.html','exchange.html','completion.html'}<=set(t.bindings(r,doc)))
   original={'companies':[dict(issuer_id=v['issuer_id'],old_packet_id='old',new_packet_id='partial',documents=[dict(source_url=URL,status='changed_requires_review',scope_reason='Unrecognized quote widget',expected_sha256=t.sha(old),observed_sha256=t.sha(new),raw_path=obs['raw_path'],checked_at=checked),dict(source_url='other',status='already_fresh')])]};library.save(r/'failed.json',original)
   derived=copy.deepcopy(original);row=derived['companies'][0];row['new_packet_id']='qualified';row['documents'][0].update(status='scoped_transcript_currentness_verified',scoped_currentness=ref);row['documents'][0].pop('scope_reason');derived['derivation']=dict(version=n.VERSION,original_receipt='failed.json',original_receipt_sha256=t.sha((r/'failed.json').read_bytes()),scoped_currentness=ref,listing_authority=auth);self.assertEqual(len(n.verify_derivation(r,derived)),6)
   for key,value in [('issuer_id','other'),('old_packet_id','other')]:
    bad=copy.deepcopy(derived);bad['companies'][0][key]=value
    with self.assertRaises(ValueError):n.verify_derivation(r,bad)
   for key,value in [('expected_sha256','other'),('raw_path','other'),('checked_at','2026-10-19T15:00:00Z')]:
    bad=copy.deepcopy(derived);bad['companies'][0]['documents'][0][key]=value
    with self.assertRaises(ValueError):n.verify_derivation(r,bad)
   bad=copy.deepcopy(derived);bad['companies'][0]['documents'][1]['status']='waived'
   with self.assertRaises(ValueError):n.verify_derivation(r,bad)
   (r/'completion.html').write_text('changed')
   with self.assertRaises(ValueError):t.replay(r,ref)
