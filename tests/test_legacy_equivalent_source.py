import json,tempfile,unittest,copy
from pathlib import Path
from research import legacy_equivalent_source as s,library,source_parse
from research.contracts import digest
class LegacyTests(unittest.TestCase):
 def fixture(self,r):
  def save(p,v):library.save(r/p,v)
  old=b'<html><head><title>Fictional annual</title></head><body>Fictional annual financial statements for 2025. Original complete text.</body></html>';new=old.replace(b'<body>',b'<body class="updated">');text=source_parse.extract(old,'text/html','https://www.sec.gov/fake.htm')[0].encode();h=library.sha(text);iid='sec:0000000001';url='https://www.sec.gov/fake.htm';did=digest([iid,h]);doc={'document_id':did,'catalog_document_id':did,'kind':'annual_background','publisher_type':'regulator','period':'FY2025','completeness':'partial','source_url':url,'raw_path':'sources/old.bin','raw_sha256':library.sha(old),'text_path':'sources/text.txt','text_sha256':h};q={k:doc[k] for k in ('document_id','kind','publisher_type','period','completeness','text_sha256')};q['source_accepted']=True;doc['qualification_id']=digest(q);save('library/qualifications/'+digest(q)+'.json',q)
  row={'issuer_id':iid,'symbol':'FAKE','issuer':'Fictional issuer','url':url,'status':'extracted','qualification_status':'accepted_financial_material','raw_path':doc['raw_path'],'raw_sha256':doc['raw_sha256'],'text_path':doc['text_path'],'text_sha256':h,'report_date':'2025-12-31','form':'40-F'};legacy='reports/retrieval/fake/results.json';save(legacy,{'results':[{'documents':[row]}]});cat={'documents':{did:{'issuer_id':iid,'text_sha256':h,'collector_ids':[],'sources':[{'source_url':url,'raw_sha256':doc['raw_sha256'],'text_sha256':h,'provenance':legacy}]}}};cat['catalog_id']=digest(cat);save('library/snapshots/'+cat['catalog_id']+'.json',cat);packet={'catalog_id':cat['catalog_id'],'issuer_id':iid,'documents':[doc]};packet['packet_id']=digest(packet);save('library/packets/'+packet['packet_id']+'.json',packet)
  for p,b in [('sources/old.bin',old),('sources/new.bin',new),('sources/text.txt',text)]:
   (r/p).parent.mkdir(parents=True,exist_ok=True);(r/p).write_bytes(b)
  checked='2026-10-19T08:03:29+00:00';http={'sha256':library.sha(new),'checked_at':checked,'body_path':'new.bin','final_url':url,'content_type':'text/html'};save('sources/cache.json',{url:http});obs={'document_id':did,'source_url':url,'expected_sha256':doc['raw_sha256'],'observed_sha256':http['sha256'],'checked_at':checked,'raw_path':'sources/new.bin','status':'blocked','reason':'No collector manifest for equivalent version'};save('reporting/receipt.json',{'companies':[{'issuer_id':iid,'old_packet_id':packet['packet_id'],'documents':[obs]}]});save('collection/document-index.json',{});return packet['packet_id'],did,'reporting/receipt.json','sources/cache.json'
 def test_exact_legacy_import_retains_qualification_and_original_objects(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);args=self.fixture(r);old=(r/'sources/old.bin').read_bytes();proof=r/'reporting/proof.json';v=s.prepare(r,*args,proof);self.assertFalse(v['qualification_promoted']);self.assertEqual(v,s.verify(r,proof));result=s.apply(r,proof);m=library.read_json(r/result['manifest_path']);self.assertEqual(m['completeness'],'partial');self.assertEqual(m['kind'],'annual_background');self.assertEqual(m['report_date'],'2025-12-31');self.assertEqual(old,(r/'sources/old.bin').read_bytes());self.assertIn('equivalence_proof',m['metadata'])
 def test_wrong_source_http_qualification_and_duplicate_legacy_rejected(self):
  for change in ['source','http','qualification','duplicate','receipt']:
   with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
    r=Path(d);args=self.fixture(r)
    if change=='source':(r/'sources/new.bin').write_text('changed financial claim')
    if change=='http':v=library.read_json(r/'sources/cache.json');next(iter(v.values()))['final_url']='https://other.example/';library.save(r/'sources/cache.json',v)
    if change=='qualification':q=next((r/'library/qualifications').glob('*.json'));v=library.read_json(q);v['completeness']='full';library.save(q,v)
    if change=='duplicate':p=r/'reports/retrieval/fake/results.json';v=library.read_json(p);v['results'].append(copy.deepcopy(v['results'][0]));library.save(p,v)
    if change=='receipt':p=r/'reporting/receipt.json';v=library.read_json(p);v['companies'][0]['documents'][0]['reason']='different failure';library.save(p,v)
    with self.assertRaises(ValueError):s.derive(r,*args)
