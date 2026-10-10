"""Recovery admission uses fictional files only; no model or remote calls."""
import json,tempfile,unittest
from pathlib import Path
from research import earnings_review_recovery as m
class RecoveryTests(unittest.TestCase):
 def test_unproven_failure_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);seed=root/'seed';job=root/'new';failed=seed/'jobs/review';failed.mkdir(parents=True);job.mkdir()
   for path,value in [(seed/'protocol.json',{'version':'signal-label-repair-v1'}),(root/'manifest.json',{'version':'wrong'}),(job/'request.json',{})]:path.write_text(json.dumps(value))
   with self.assertRaisesRegex(ValueError,'authority'):m.export(seed,job,root/'manifest.json')
 def test_proven_failure_contract_is_exact(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);seed=root/'seed';job=root/'new';failed=seed/'jobs/review';failed.mkdir(parents=True);job.mkdir()
   q={'bindings':{},'model':'fictional','effort':'medium','timeout_seconds':1}
   files={seed/'protocol.json':{'version':'signal-label-repair-v1'},job/'request.json':q,failed/'request.json':q,root/'manifest.json':{'version':'proven-pre-model-host-access-retry-v1','companies':{}}}
   for p,v in files.items():p.write_text(json.dumps(v))
   with self.assertRaisesRegex(ValueError,'reserve'):m.export(seed,job,root/'manifest.json')

from unittest.mock import patch
from test_earnings_passages import PassageFixture
import test_earnings_signals as fixtures
class EditionTests(PassageFixture,unittest.TestCase):
 state=fixtures.SignalTests.state
 pack=fixtures.SignalTests.pack
 review=fixtures.SignalTests.review
 def test_recovered_acceptance_renders_without_model_and_tamper_is_rejected(self):
  seed=self.root/'seed';job=self.root/'job';seed.mkdir();job.mkdir();manifest=self.root/'manifest.json'
  for p,v in [(seed/'protocol.json',{'code':[]}),(job/'output.json',{}),(manifest,{})]:p.write_text(json.dumps(v))
  state=self.state();pack=self.pack(state)
  value={'state':state,'signals':pack,'source_protocol':{},'kind':'signals','report_seed':str(seed),'excluded_session_ids':['fresh'],'source_usage_uncertainty':None,'tokens':19,'history':{}}
  with patch.object(m,'export',return_value=value),patch.object(m.rem,'_source_bundle',return_value=(self.bundle,self.catalog)),patch.object(m.r,'verify_job',return_value={'content':self.review(pack)}),patch.object(m.r,'run_role') as call:
   root=self.root/'edition';v=m.initialize(seed,job,manifest,root)
   self.assertEqual(v['status'],'accepted');self.assertTrue((root/'report.html').exists());call.assert_not_called()
   self.assertEqual(m.verify(root)['html_sha256'],v['html_sha256'])
   (root/'state.json').write_text('{}')
   with self.assertRaises(ValueError):m.verify(root)
