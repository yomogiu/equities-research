import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from research import earnings_source_chain as h,earnings_source_revalidation as s
class SourceChain(unittest.TestCase):
 def test_adjacent_exact_proofs_and_tamper(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();a=r/'a.json';z=r/'z.json';receipt=r/'receipt.json';stamp='2026-10-01T00:00:00+00:00';receipt.write_text(json.dumps({'checked_at':stamp}));a.write_text(json.dumps({'version':s.VERSION,'old_packet_id':'a','new_packet_id':'b','source_receipt':'receipt.json'}));z.write_text(json.dumps({'version':s.VERSION,'old_packet_id':'b','new_packet_id':'c'}));out=r/'out.json'
   with patch.object(s,'verify',return_value={'issuer_id':'fake','period':'Q2'})as verify:
    h.prepare(r,a,z,out);h.verify(r,out);self.assertEqual(verify.call_args_list[0].kwargs,{'as_of':stamp});self.assertEqual(verify.call_args_list[1].kwargs,{'as_of':None})
    z.write_text(z.read_text()+' ')
    with self.assertRaises(ValueError):h.verify(r,out)
 def test_nonadjacent_rejects(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp);a=r/'a';z=r/'z';a.write_text(json.dumps({'version':s.VERSION,'new_packet_id':'x'}));z.write_text(json.dumps({'version':s.VERSION,'old_packet_id':'y'}))
   with self.assertRaises(ValueError):h.checked(r,a,z,'invalid')
