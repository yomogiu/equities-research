import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from research import earnings_pending_final as h,earnings_mixed_runner as b
class PendingFinal(unittest.TestCase):
 def test_retains_round_sessions_and_finding_bytes(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp).resolve();(r/'protocol.json').write_text('{}');(r/'passages.json').write_text('{}');case=r/'case.json';case.write_text('{}');out=r/'prep.json';v={'case_sha256':b.sha(case),'catalog_sha256':b.digest({}),'tokens':999,'session_ids':['a','b','c','d','e'],'start_round':2,'spent_correction_rounds':1,'findings':{'analysis:0':{'reason':'Unchanged original finding'}}}
   with patch.object(h,'replay',return_value=v):
    a=h.prepare(r,case,out);self.assertEqual(h.verify(out,case,{}),a)
    for key,value in [('tokens',0),('spent_correction_rounds',0),('session_ids',['a']),('findings',{})]:
     bad={**a,key:value};out.write_text(json.dumps(bad))
     with self.assertRaises(ValueError):h.verify(out,case,{})
