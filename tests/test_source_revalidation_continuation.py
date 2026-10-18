import copy,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_source_revalidation as p
class SourceIdentityTests(unittest.TestCase):
 def packet(self):
  return {'issuer_id':'fictional','period':'FY2026-Q2','identity_verified':True,'translation_required':[],'availability':{},'documents':[{k:'bound-'+k for k in p.DOC_FIELDS}]}
 def test_only_currentness_metadata_may_change(self):
  old=self.packet();new=copy.deepcopy(old);new['documents'][0]['checked_at']='fresh-observation';p.same_content(old,new)
  for key in p.DOC_FIELDS:
   bad=copy.deepcopy(new);bad['documents'][0][key]='changed'
   with self.assertRaises(ValueError,msg=key):p.same_content(old,bad)
  bad=copy.deepcopy(new);bad['documents'].append(copy.deepcopy(bad['documents'][0]))
  with self.assertRaises(ValueError):p.same_content(old,bad)
 def test_scope_or_issuer_change_is_rejected(self):
  for key in ('issuer_id','period','identity_verified','translation_required','availability'):
   bad=self.packet();bad[key]=None
   with self.assertRaises(ValueError,msg=key):p.same_content(self.packet(),bad)
 def test_verify_rechecks_live_currentness_and_rejects_changed_proof_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'library/packets').mkdir(parents=True)
   for n in ('a'*64,'b'*64):(r/f'library/packets/{n}.json').write_text('{}')
   (r/'receipt.json').write_text('{}');v={'version':p.VERSION,'old_packet_id':'a'*64,'new_packet_id':'b'*64,'old_packet_sha256':p.b.sha(r/('library/packets/'+'a'*64+'.json')),'new_packet_sha256':p.b.sha(r/('library/packets/'+'b'*64+'.json')),'source_receipt':'receipt.json','source_receipt_sha256':p.b.sha(r/'receipt.json')};proof=r/'proof';proof.write_text(json.dumps(v))
   with patch.object(p,'checked',return_value=({'packet_id':'old'},{})) as check:
    self.assertEqual(p.verify(r,proof)['packet_id'],'old');p.verify(r,proof);self.assertEqual(check.call_count,2)
    (r/'receipt.json').write_text('{"changed":true}')
    with self.assertRaises(ValueError):p.verify(r,proof)

 def test_checked_requires_live_freshness_even_for_identical_source_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'library/packets').mkdir(parents=True);old_id='a'*64;new_id='b'*64;old=self.packet();old['packet_id']=old_id;new=copy.deepcopy(old);new['packet_id']=new_id
   for ident,v in ((old_id,old),(new_id,new)):(r/f'library/packets/{ident}.json').write_text(json.dumps(v))
   receipt=r/'receipt';receipt.write_text(json.dumps({'companies':[{'issuer_id':'fictional','old_packet_id':old_id,'new_packet_id':new_id,'documents':[{'status':'raw_identical','source_url':old['documents'][0]['source_url']}]}]}))
   with patch.object(p.library,'materialize') as historical,patch('research.earnings_report_flow.validate_packet',return_value=new) as current:
    self.assertEqual(p.checked(r,old_id,new_id,receipt)[0]['packet_id'],old_id);self.assertTrue(historical.call_args.kwargs['historical_currentness']);current.assert_called_once_with(r.resolve(),new_id)
   with patch.object(p.library,'materialize'),patch('research.earnings_report_flow.validate_packet',side_effect=ValueError('Packet requires source freshness revalidation')):
    with self.assertRaisesRegex(ValueError,'freshness'):p.checked(r,old_id,new_id,receipt)
 def test_unbound_packet_paths_are_rejected(self):
  for ident in ('../outside','a'*63,'G'*64):
   with self.assertRaises(ValueError):p.packet_ids(ident,'b'*64)

 def test_html_equivalence_preserves_text_fiscal_tags_and_every_fact(self):
  import hashlib
  from types import SimpleNamespace
  doc={'document_id':'fictional','text_sha256':hashlib.sha256(b'Exact financial source').hexdigest()}
  extract=lambda body,mime,url:('Exact financial source',{'period':'2026-Q2'},'extracted')
  financial=SimpleNamespace(extract_inline_xbrl=lambda body,meta:{'observations':[{'value':'10','source_raw_sha256':meta['raw_sha256'],'support':body}],'gaps':[]})
  self.assertTrue(p.equivalent_html(b'<p a="1">10</p>',b'<p a="2">10</p>','https://example.test',doc,extract,financial))
  changed=SimpleNamespace(extract_inline_xbrl=lambda body,meta:{'observations':[{'value':'11' if 'changed' in body else '10'}],'gaps':[]})
  self.assertFalse(p.equivalent_html(b'10',b'changed','https://example.test',doc,extract,changed))
  self.assertFalse(p.equivalent_html(b'10',b'10','https://example.test',doc,lambda body,mime,url:('different text',{},'extracted'),financial))
 def test_request_must_bind_proof_and_every_source_without_changing_report_identity(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);proof=r/'proof.json';proof.write_text('{}');digest=p.b.sha(proof)
   old={'packet_id':'a'*64,'issuer_id':'fictional','period':'FY2026-Q2'};request={'spec':{**old,'source_currentness':{'path':'proof.json','sha256':digest}},'input_sha256':{'proof.json':digest,'fresh-source':'bound'}}
   with patch.object(p,'verify',return_value=old),patch.object(p,'input_bindings',return_value={'fresh-source':'bound'}):
    self.assertEqual(p.validate_request(r,request),old)
    bad=copy.deepcopy(request);bad['input_sha256'].pop('fresh-source')
    with self.assertRaises(ValueError):p.validate_request(r,bad)
    bad=copy.deepcopy(request);bad['spec']['issuer_id']='other'
    with self.assertRaises(ValueError):p.validate_request(r,bad)

 def test_input_bindings_normalizes_paths_and_rejects_escape(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d).resolve();(r/'library/packets').mkdir(parents=True);(r/'library/snapshots').mkdir()
   packet={'packet_id':'a'*64,'catalog_id':'snapshot','issuer_id':'fictional','documents':[]}
   for path,value in [('proof.json',{'new_packet_id':'a'*64,'source_receipt':'receipt.json'}),('receipt.json',{'companies':[]}),('library/packets/'+'a'*64+'.json',packet),('library/snapshots/snapshot.json',{})]:(r/path).write_text(json.dumps(value))
   with patch.object(p,'verify',return_value=packet):
    expected=p.input_bindings(r,'proof.json')
    self.assertEqual(p.input_bindings(r,Path('proof.json')),expected)
    self.assertEqual(p.input_bindings(r,r/'proof.json'),expected)
    with self.assertRaises(ValueError):p.input_bindings(r,r.parent/'outside')

 def test_historical_replay_uses_launch_freshness_but_live_gate_still_checks_now(self):
  packet=self.packet();packet.update(catalog_id='snapshot',freshness_policy={'event_max_age_hours':24,'annual_background_max_age_hours':720})
  packet['documents'][0].update(checked_at='2026-01-01T00:00:00+00:00',retrieved_at='2026-01-01T00:00:00+00:00')
  with patch.object(p.library,'materialize'),patch.object(p.b,'read',return_value={'issuers':{'fictional':{'monitoring_eligible':True}}}):
   self.assertEqual(p.historical_packet(Path('/tmp'),packet,'2026-01-01T01:00:00+00:00'),packet)
   for stamp in ('2026-01-03T00:00:00+00:00','2026-01-01T01:00:00','2999-01-01T00:00:00+00:00'):
    with self.assertRaises(ValueError):p.historical_packet(Path('/tmp'),packet,stamp)
