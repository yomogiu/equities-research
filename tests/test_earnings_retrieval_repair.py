import unittest
from research.earnings_retrieval_repair import budget
class RetrievalRepairBudgetTests(unittest.TestCase):
 def test_original_usage_is_subtracted(self):
  self.assertEqual(budget({'tokens':250000,'max_tokens':1200000}),950000)
 def test_reset_unbounded_and_exhausted_rejected(self):
  for value in ({'tokens':0,'max_tokens':1200000},{'tokens':1200000,'max_tokens':1200000},{'tokens':1,'max_tokens':2400000}):
   with self.assertRaises(ValueError):budget(value)

class RetrievalCompletionTests(unittest.TestCase):
 def test_preparation_cannot_reset_charged_round_or_tokens(self):
  import tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  from research import earnings_retrieval_repair as p
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={'passages':[]};actual={'tokens':500000,'spent_correction_rounds':1,'case_sha256':p.b.sha(case),'catalog_sha256':p.b.digest(catalog)};v={'version':p.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':p.b.sha(root/'reservation.json'),**actual};record=root/'record';record.write_text(json.dumps(v))
   with patch.object(p,'completed',return_value=actual):
    self.assertEqual(p.verify(record,case,catalog)['tokens'],500000)
    for key,value in [('tokens',0),('spent_correction_rounds',0)]:
     record.write_text(json.dumps({**v,key:value}))
     with self.assertRaises(ValueError):p.verify(record,case,catalog)
