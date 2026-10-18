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

class InspectionFailureScopeTests(unittest.TestCase):
 def test_source_coverage_is_exactly_scoped(self):
  for message in ('Complete candidate Markdown must be inspected','Required original evidence was not completely inspected: D001, F002, Pabc'):
   self.assertTrue(p.inspection_failure(message))
  for message in ('fetch failed','Invalid/duplicate/unknown signal passages','Required original evidence was not completely inspected: ','Required original evidence was not completely inspected: not an ID','Complete candidate Markdown was inspected'):
   self.assertFalse(p.inspection_failure(message))
