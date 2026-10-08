"""Original verifier execution uses fictional code and receipts only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_corrections as c

class OriginalProposalVerifierTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.code=self.root/'original';research=self.code/'research';research.mkdir(parents=True)
  (research/'__init__.py').write_text('')
  self.runner=research/'earnings_mixed_runner.py';self.helper=research/'earnings_mixed_prime.mjs'
  self.runner.write_text("import json\ndef verify_job(job):\n value=json.loads((job/'output.json').read_text())\n if value.get('receipt')!='fictional-original':raise ValueError('Original authentication rejected')\n return {'authenticated_by':'frozen-original','content':value['content']}\n")
  self.helper.write_text('// fictional original helper\n');self.job=self.root/'saved-job';self.job.mkdir()
  self.output={'receipt':'fictional-original','content':{'operations':[]}}
  (self.job/'output.json').write_text(json.dumps(self.output))
  (self.job/'request.json').write_text(json.dumps({'runner_sha256':c.base.sha(self.runner),'helper_sha256':c.base.sha(self.helper)}))
  self.imported={'job':str(self.job),'output_sha256':c.base.sha(self.job/'output.json')}
  self.records=[{'path':str(p),'sha256':c.base.sha(p)} for p in [self.runner,self.helper]]
 def test_missing_original_records_rejected_without_fallback(self):
  with patch.object(c,'verify_job',side_effect=AssertionError('No current fallback')):
   with self.assertRaisesRegex(ValueError,'Bound original'):c.verify_saved_proposal(self.imported,[])
 def test_executes_original_runner_not_current(self):
  with patch.object(c,'verify_job',side_effect=AssertionError('Current runner must not execute')):
   result=c.verify_saved_proposal(self.imported,self.records)
  self.assertEqual(result,{'authenticated_by':'frozen-original','content':{'operations':[]}})
 def test_changed_original_helper_rejected_before_execution(self):
  self.helper.write_text('// mutated helper')
  with patch.object(c.subprocess,'run') as run:
   with self.assertRaisesRegex(ValueError,'verifier changed'):c.verify_saved_proposal(self.imported,self.records)
   run.assert_not_called()
 def test_nonmatching_runner_hash_has_no_current_fallback(self):
  request=json.loads((self.job/'request.json').read_text());request['runner_sha256']='0'*64;(self.job/'request.json').write_text(json.dumps(request))
  with patch.object(c,'verify_job',side_effect=AssertionError('No current fallback')):
   with self.assertRaisesRegex(ValueError,'No bound original'):c.verify_saved_proposal(self.imported,self.records)
 def test_missing_helper_binding_has_no_fallback(self):
  with patch.object(c,'verify_job',side_effect=AssertionError('No current fallback')):
   with self.assertRaisesRegex(ValueError,'No bound original'):c.verify_saved_proposal(self.imported,self.records[:1])
 def test_changed_output_rejected_before_execution(self):
  (self.job/'output.json').write_text('{}')
  with patch.object(c.subprocess,'run') as run:
   with self.assertRaisesRegex(ValueError,'proposal changed'):c.verify_saved_proposal(self.imported,self.records)
   run.assert_not_called()
 def test_original_authentication_failure_propagates(self):
  (self.job/'output.json').write_text(json.dumps({'receipt':'invalid'}));self.imported['output_sha256']=c.base.sha(self.job/'output.json')
  with patch.object(c,'verify_job',side_effect=AssertionError('No current fallback')):
   with self.assertRaises(c.subprocess.CalledProcessError):c.verify_saved_proposal(self.imported,self.records)

if __name__=='__main__':unittest.main()
