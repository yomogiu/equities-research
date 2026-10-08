"""Prepared recovery must skip preparers and retain exhausted correction rounds."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_efficient_evidence import EfficientPipelineTests
from research import earnings_passage_pipeline as pipe

class PreparedFlowTests(unittest.TestCase):
 def setUp(self):
  self.fx=EfficientPipelineTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
 def loader(self,root):
  p,b,c=self.original_load(root);p['prepared_recovery']={'prior_rounds':2}
  b['_prepared_recovery']={'artifacts':{'financial':pipe.bind_efficient_financial(self.fx.financial,b),'retrieval':copy.deepcopy(self.fx.retrieval)},'tokens':700,'identities':{'inherited-financial','inherited-retrieval'}}
  return p,b,c
 def test_complete_run_and_verify_without_repeating_preparers(self):
  self.original_load=pipe.load
  with patch.object(pipe,'load',side_effect=self.loader):
   result=pipe.run(self.fx.output);self.assertEqual(result['status'],'accepted');pipe.verify(self.fx.output)
  self.assertEqual(self.fx.calls,[('analysis',2,0),('review',2,0)])
  self.assertEqual(result['correction_rounds'],2);self.assertEqual(result['total_tokens'],900)
 def test_failure_cannot_reset_rounds(self):
  self.original_load=pipe.load;self.fx.bad_analysis=True
  with patch.object(pipe,'load',side_effect=self.loader):result=pipe.run(self.fx.output)
  self.assertEqual(result['status'],'blocked');self.assertEqual(self.fx.calls,[('analysis',2,0)]);self.assertEqual(result['correction_rounds'],2)
