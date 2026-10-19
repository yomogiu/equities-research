"""Fictitious same-event publisher pages only; no private fixtures."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import transcript_currentness as t,transcript_market_widget_transition as d,library
URL='https://stockanalysis.com/stocks/fake/transcripts/123-q2-2026/'
BLOCK='<div class="border-t first:border-t-0"><div>Fictional Speaker</div><span class="transcript-sentence">Fictional complete discussion of Q2 performance and company guidance, with original source text preserved.</span></div>'
OPEN='232.72\n+0.58 (0.25%)\nOct 19, 2026, 9:50 AM EDT - Market open'
def page(widget='100 At close:',prepared=False):
 link='<li class="mb-0"><a href="/filings/FAKE/900/" class="pill"><span>Prepared remarks</span></a></li>' if prepared else ''
 other='<li class="mb-0"><a href="/filings/FAKE/100/" class="pill"><span>Quarterly report</span></a></li>'
 group='<ul aria-label="Downloads">'+link+other+'</ul>'
 event='quartrEventId:123,fiscalYear:2026,quarterLabel:"Q2 2026",files:['+('{id:900,label:"Prepared remarks"},'if prepared else '')+'{id:100,label:"Quarterly report"}]'
 return ('<html><head><title>Fictional Q2 2026</title></head><body><div class="mb-5 flex flex-row items-end">'+widget+'</div>'+group+BLOCK+group+'<script>'+event+'</script></body></html>').encode()
class MarketOpenTests(unittest.TestCase):
 def test_explicit_version_only_and_complete_original_blocks(self):
  with self.assertRaises(ValueError):t.compare(page(),page(OPEN,True),URL)
  v=t.compare(page(),page(OPEN,True),URL,allow_market_open=True);self.assertEqual(len(v['signature']['block_sha256']),1);self.assertEqual(v['archived']['downloads']['prepared'],[]);self.assertEqual(len(v['observed']['downloads']['prepared']),2)
 def test_numeric_time_status_and_extra_prose_are_strict(self):
  for text in [OPEN+'\nGuidance rose',OPEN.replace('9:50','19:50'),OPEN.replace('EDT','UTC'),OPEN.replace('Market open','Call underway'),OPEN.replace('232.72','NaN'),OPEN.replace('0.25%','growing%')]:
   with self.subTest(text=text),self.assertRaises(ValueError):t.compare(page(),page(text,True),URL,allow_market_open=True)
 def test_event_existing_destination_order_call_and_metadata_are_bound(self):
  for body in [page(OPEN,True).replace(b'/FAKE/100/',b'/FAKE/101/'),page(OPEN,True).replace(b'/FAKE/900/',b'/OTHER/900/'),page(OPEN,True).replace(b'quartrEventId:123',b'quartrEventId:124'),page(OPEN,True).replace(b'fiscalYear:2026',b'fiscalYear:2027'),page(OPEN,True).replace(b'original source text',b'changed source text'),page(OPEN,True).replace(b'<title>Fictional',b'<title>Changed'),page(OPEN,True).replace(b'{id:900,label:',b'{id:901,label:')]:
   with self.assertRaises(ValueError):t.compare(page(),body,URL,allow_market_open=True)
 def test_no_deletion_replacement_or_unbound_prepared_control(self):
  with self.assertRaises(ValueError):t.compare(page(prepared=True),page(OPEN),URL,allow_market_open=True)
  with self.assertRaises(ValueError):t.compare(page(prepared=True),page(OPEN,True).replace(b'/FAKE/900/',b'/FAKE/901/').replace(b'{id:900',b'{id:901'),URL,allow_market_open=True)
  with self.assertRaises(ValueError):t.compare(page(),page(OPEN,True).replace(b'aria-label="Downloads"',b'aria-label="Other"',1),URL,allow_market_open=True)
 def test_derived_receipt_changes_only_rejected_widget_and_packet(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();original={'companies':[{'issuer_id':'fictional:1','old_packet_id':'old','new_packet_id':'partial','documents':[{'source_url':URL,'status':'changed_requires_review','scope_reason':'Unrecognized quote widget','expected_sha256':'oldraw','observed_sha256':'newraw','raw_path':'observed.bin','checked_at':'2026-10-19T14:00:00Z'}]}]};(root/'failed.json').write_text(json.dumps(original));ref={'path':'scoped.json','sha256':'bound'};proof={'version':t.MARKET_OPEN_VERSION,'issuer_id':'fictional:1','source_url':URL,'archived':{'raw_sha256':'oldraw'},'observed':{'raw_sha256':'newraw','raw_path':'observed.bin'},'checked_at':'2026-10-19T14:00:00+00:00'};receipt=copy.deepcopy(original);row=receipt['companies'][0];row['new_packet_id']='qualified';row['documents'][0].update(status='scoped_transcript_currentness_verified',scoped_currentness=ref);row['documents'][0].pop('scope_reason');receipt['derivation']={'version':d.VERSION,'original_receipt':'failed.json','original_receipt_sha256':t.sha((root/'failed.json').read_bytes()),'scoped_currentness':ref}
   with patch.object(t,'replay',return_value=proof):
    self.assertIn('failed.json',d.verify_derivation(root,receipt))
    for key,value in [('old_packet_id','different'),('issuer_id','different')]:
     bad=copy.deepcopy(receipt);bad['companies'][0][key]=value
     with self.assertRaises(ValueError):d.verify_derivation(root,bad)
