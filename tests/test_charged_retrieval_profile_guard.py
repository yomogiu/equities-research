import unittest,copy
from research import earnings_inherited_profile_guard as h
from research.earnings_file_pipeline import profile_models
class GuardTests(unittest.TestCase):
 def value(self):return dict(model_profile=None,preparation_version=h.CHARGED_RETRIEVAL_HANDLER,models=profile_models('original-file-review-routes-v1'),spent_correction_rounds=1,session_count=2)
 def test_exact_original_routes_and_usage_scope(self):self.assertTrue(h.matches_charged_retrieval(self.value(),'original-file-review-routes-v1'))
 def test_other_handlers_rounds_sessions_and_routes_rejected(self):
  for k,v in [('preparation_version',h.QUESTION_HANDLER),('spent_correction_rounds',0),('session_count',1),('models',{}),('model_profile','original-file-review-routes-v1')]:
   d=self.value();d[k]=v
   with self.assertRaises(ValueError):h.matches_charged_retrieval(d,'original-file-review-routes-v1')
