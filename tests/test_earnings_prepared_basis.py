import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_basis as p
class BasisLineageTests(unittest.TestCase):
 def test_replay_preserves_usage_models_and_correction(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'protocol.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={'passages':[]}
   raw={'tokens':123,'models':{'review':['model','medium']},'max_tokens':1200000,'case_sha256':p.b.sha(case),'catalog_sha256':p.b.digest(catalog)}
   v={'version':p.VERSION,'previous_root':str(root),'protocol_sha256':p.b.sha(root/'protocol.json'),**raw,'prepared_correction':{'round':1},'address_derivation':['exact']};f=root/'record';f.write_text(json.dumps(v))
   with patch.object(p,'replay',return_value=raw),patch.object(p,'derive',return_value=({'round':1},['exact'])):
    self.assertEqual(p.verify(f,case,catalog)['tokens'],123)
    for key,value in [('tokens',0),('models',{}),('prepared_correction',{'round':0})]:
     bad={**v,key:value};f.write_text(json.dumps(bad))
     with self.assertRaises(ValueError):p.verify(f,case,catalog)
     f.write_text(json.dumps(v))
