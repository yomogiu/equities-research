"""Fictitious KASE publisher fixtures only."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import transcript_currentness as t,transcript_kase_transition as d,library
URL='https://stockanalysis.com/quote/kase/FAKE/transcripts/123-q2-2026/'
OLD='10,000\n+100 (1.00%)\nAt close: Oct 2, 2026'
NEW='10,200\n+200 (2.00%)\nAt close: Oct 16, 2026'
def page(widget=OLD):
 return ('<html><head><title>Fictional Q2 2026</title></head><body><div class="mt-px text-tiny text-faded">Kazakhstan · Delayed Price · Currency is KZT</div><div class="mb-5 flex flex-row items-end">'+widget+'</div><a href="/filings/KASE:FAKE/900/">Slides</a><div class="border-t first:border-t-0"><div>Fictional Speaker</div><span class="transcript-sentence">Fictional complete discussion of Q2 performance and company guidance with original source text preserved.</span></div><script>quartrEventId:123,fiscalYear:2026,quarterLabel:"Q2 2026",detailSlug:"123-q2-2026",eventDate:"2026-08-01"</script></body></html>').encode()
class KaseTests(unittest.TestCase):
 def test_explicit_scope_and_roundtrip(self):
  with self.assertRaises(ValueError):t.compare(page(),page(NEW),URL)
  v=t.compare(page(),page(NEW),URL,allow_kase=True);self.assertEqual(v,json.loads(json.dumps(v)));self.assertEqual(len(v['signature']['block_sha256']),1)
  for url in [URL.replace('/kase/','/nyse/'),URL.replace('stockanalysis.com','other.example')]:
   with self.assertRaises(ValueError):t.compare(page(),page(NEW),url,allow_kase=True)
 def test_all_identity_evidence_and_strict_widget_bound(self):
  for a,b in [(b'KASE:FAKE',b'KASE:OTHER'),(b'/900/',b'/901/'),(b'Currency is KZT',b'Currency is USD'),(b'original source text',b'new source text'),(b'<title>Fictional',b'<title>Changed'),(b'2026-08-01',b'2026-08-02'),(b'quartrEventId:123',b'quartrEventId:124'),(b'At close: Oct 16, 2026',b'At close: Profit rose'),(b'+200 (2.00%)',b'new guidance')]:
   with self.subTest(a=a),self.assertRaises(ValueError):t.compare(page(),page(NEW).replace(a,b),URL,allow_kase=True)
 def test_create_replay_keeps_original_qualification_and_fetch_bound(self):
  from research import source_parse
  from research.contracts import digest
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();before=page();after=page(NEW);text=source_parse.page(before,URL).text.encode()
   for name,body in [('old.html',before),('old.txt',text),('sources/test/objects/new.html',after)]:
    f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(body)
   q={'document_id':digest(['fictional:1',t.sha(text)]),'text_sha256':t.sha(text),'period':'FY2026-Q2','kind':'transcript','completeness':'full','source_accepted':True,'source_spans':[{'start':0,'end':9,'text':text.decode()[:9]}]};qid=digest(q);library.save(root/'library/qualifications'/(qid+'.json'),q)
   cache={'sha256':t.sha(after),'checked_at':'2026-10-19T14:00:00+00:00','final_url':URL,'content_type':'text/html','body_path':'objects/new.html'};library.save(root/'sources/test/http-cache.json',{URL:cache});doc={'source_url':URL,'raw_path':'old.html','raw_sha256':t.sha(before),'text_path':'old.txt','text_sha256':t.sha(text),'qualification_id':qid};observed={'raw_path':'sources/test/objects/new.html','observed_sha256':t.sha(after),'checked_at':cache['checked_at']}
   ref=t.create(root,{'issuer_id':'fictional:1','period':'FY2026-Q2'},doc,observed,'sources/test/http-cache.json',kase=True);doc.update(scoped_currentness=ref,source_check_status=t.STATUS,scoped_checked_at=cache['checked_at']);self.assertEqual(t.replay(root,ref,doc)['version'],t.KASE_VERSION)
   library.save(root/'sources/later/http-cache.json',{URL:{'checked_at':'2026-10-19T15:00:00+00:00','sha256':'f'*64}})
   with self.assertRaises(ValueError):t.replay(root,ref,doc)
   t.replay(root,ref,doc,historical=True)
 def test_derived_receipt_changes_only_rejected_widget_and_packet(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();original={'companies':[{'issuer_id':'fictional:1','old_packet_id':'old','new_packet_id':'partial','documents':[{'source_url':URL,'status':'changed_requires_review','scope_reason':'Unsupported transcript publisher URL','expected_sha256':'oldraw','observed_sha256':'newraw','raw_path':'observed.bin','checked_at':'2026-10-19T14:00:00Z'}]}]};(root/'failed.json').write_text(json.dumps(original));ref={'path':'scoped.json','sha256':'bound'};proof={'version':t.KASE_VERSION,'issuer_id':'fictional:1','source_url':URL,'archived':{'raw_sha256':'oldraw'},'observed':{'raw_sha256':'newraw','raw_path':'observed.bin'},'checked_at':'2026-10-19T14:00:00+00:00'};receipt=copy.deepcopy(original);row=receipt['companies'][0];row['new_packet_id']='qualified';row['documents'][0].update(status='scoped_transcript_currentness_verified',scoped_currentness=ref);row['documents'][0].pop('scope_reason');receipt['derivation']={'version':d.VERSION,'original_receipt':'failed.json','original_receipt_sha256':t.sha((root/'failed.json').read_bytes()),'scoped_currentness':ref}
   with patch.object(t,'replay',return_value=proof):
    self.assertIn('failed.json',d.verify_derivation(root,receipt))
    for key,value in [('old_packet_id','different'),('issuer_id','different')]:
     bad=copy.deepcopy(receipt);bad['companies'][0][key]=value
     with self.assertRaises(ValueError):d.verify_derivation(root,bad)
