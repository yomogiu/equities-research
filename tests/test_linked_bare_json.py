import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_linked_bare_json as h,earnings_prepared_retrieval as p
class Bare(unittest.TestCase):
 def test_exact_bare_object(self):self.assertEqual(h.proposal('{"repairs": []}'),{'repairs':[]})
 def test_nonexact_responses_reject(self):
  for text in ['```json\n{"repairs":[]}\n```','prefix {"repairs":[]}','{"repairs":[]} suffix','[]','{"repairs":[],"repairs":[]}','{"repairs":[],"prose":"new"}']:
   with self.subTest(text=text),self.assertRaises((ValueError,json.JSONDecodeError)):h.proposal(text)
 def test_opt_in_only_dispatch(self):
  with tempfile.TemporaryDirectory()as tmp:
   file=Path(tmp)/'manifest';file.write_text(json.dumps({'version':h.VERSION}))
   with patch.object(h,'verify',return_value={'passed':True})as verify:
    self.assertEqual(p.verify(file,'case',{}),{'passed':True});verify.assert_called_once_with(file,'case',{})
 def test_preparation_preserves_charges_and_raw_hash(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');actual={'tokens':222222,'spent_correction_rounds':1,'session_ids':['old','fresh'],'raw_response_sha256':'unchanged','models':{'retrieval':['original','max']},'case_sha256':h.b.sha(case),'catalog_sha256':h.b.digest({})};v={'version':h.VERSION,'repair_root':str(root),'reservation_sha256':h.b.sha(root/'reservation.json'),**actual};file=root/'manifest'
   with patch.object(h,'completed',return_value=actual):
    file.write_text(json.dumps(v));self.assertEqual(h.verify(file,case,{})['tokens'],222222)
    for key,value in [('tokens',0),('raw_response_sha256','changed'),('spent_correction_rounds',0),('session_ids',['fresh'])]:
     file.write_text(json.dumps({**v,key:value}))
     with self.subTest(key=key),self.assertRaises(ValueError):h.verify(file,case,{})
