from unittest import TestCase
from research import earnings_batch_review as b
from research import earnings_mixed_runner as r
class ResponseTests(TestCase):
 def test_bound_digest_does_not_mutate_original_or_decisions(self):
  original={'batch_sha256':'mistyped','decisions':[],'reopen':[]}
  derived=b.bind_review_response(original,{'batch_sha256':'bound'})
  self.assertEqual(original['batch_sha256'],'mistyped');self.assertEqual(derived,dict(original,batch_sha256='bound'))
 def test_pass_still_requires_source_evidence(self):
  items={'one':{'value':'fake','depends_on':[]}};review={'batch_sha256':r.digest(items),'decisions':[{'unit_id':'one','verdict':'pass','reason':'Checked exact source','passage_ids':[]}],'reopen':[]}
  with self.assertRaisesRegex(ValueError,'Exact original evidence'):b.adjudicate(items,{'one'},{},review,{'passages':[]},'receipt')
