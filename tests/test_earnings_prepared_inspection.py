import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_inspection as p
class InspectionContinuationTests(unittest.TestCase):
 def test_spent_round_and_tokens_cannot_reset(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'protocol.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={'passages':[]};raw={'tokens':500000,'max_tokens':1200000,'start_round':2,'case_sha256':p.b.sha(case),'catalog_sha256':p.b.digest(catalog),'models':{'correction':['original','max']}};v={'version':p.VERSION,'previous_root':str(root),'protocol_sha256':p.b.sha(root/'protocol.json'),**raw};record=root/'record';record.write_text(json.dumps(v))
   with patch.object(p,'replay',return_value=raw):
    self.assertEqual(p.verify(record,case,catalog)['start_round'],2)
    for key,value in [('tokens',0),('start_round',1),('max_tokens',2400000),('models',{})]:
     record.write_text(json.dumps({**v,key:value}))
     with self.assertRaises(ValueError):p.verify(record,case,catalog)
