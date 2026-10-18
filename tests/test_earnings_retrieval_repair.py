import unittest
from research.earnings_retrieval_repair import budget
class RetrievalRepairBudgetTests(unittest.TestCase):
 def test_original_usage_is_subtracted(self):
  self.assertEqual(budget({'tokens':250000,'max_tokens':1200000}),950000)
 def test_reset_unbounded_and_exhausted_rejected(self):
  for value in ({'tokens':0,'max_tokens':1200000},{'tokens':1200000,'max_tokens':1200000},{'tokens':1,'max_tokens':2400000}):
   with self.assertRaises(ValueError):budget(value)
