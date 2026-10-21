import copy,unittest
from research import earnings_inherited_profile_guard as g,earnings_file_pipeline as p
class GuardTests(unittest.TestCase):
 def test_exact_inherited_original_routes_only(self):
  v={'model_profile':None,'models':p.profile_models('original-file-review-routes-v1'),'preparation_version':g.HANDLER};self.assertTrue(g.matches(v,'original-file-review-routes-v1'))
  for field,value in [('model_profile','another'),('models',{}),('preparation_version','unreviewed')]:
   bad=copy.deepcopy(v);bad[field]=value
   with self.assertRaises(ValueError):g.matches(bad,'original-file-review-routes-v1')
  bad=copy.deepcopy(v);bad['models']['analysis']=['gpt-6.1-sol','medium']
  with self.assertRaises(ValueError):g.matches(bad,'original-file-review-routes-v1')
  with self.assertRaises(ValueError):g.matches(v,'another')
