"""Fictitious closed envelope failure; never real source/session data."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_signal_binding_repair as h,earnings_file_runner as runner
class BareBinding(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name)/'binding-repair';self.job.mkdir();self.q={'bindings':{'repair_version':h.VERSION},'context_index':'fake','model':'fake-model','effort':'low'};self.receipt={'id':'fake-session','path':'fake-session.jsonl'}
  self.save('request.json',self.q);self.save('launch.json',{'id':'fake-launch','request_sha256':h.b.digest(self.q)});self.save('execution.json',{'status':'execution_failed','exit_code':0,'request_sha256':h.b.digest(self.q),'launch_sha256':h.b.sha(self.job/'launch.json'),'session':self.receipt});self.save('runtime-start.json',{'launch_id':'fake-launch','session_id':'fake-session','model':'fake-model','effort':'low','oauth':True});self.save('runtime-finish.json',{'session_id':'fake-session','model':'fake-model','effort':'low','oauth':True});self.save('wire.json',[]);self.save('response.md',{'bindings':[]});(self.job/'fake-session.jsonl').write_text('');(self.job/'retrieval.jsonl').write_text('')
 def save(self,name,obj):(self.job/name).write_text(json.dumps(obj))
 def invoke(self):
  with patch.object(runner,'verify_request') as req,patch.object(runner,'receipt',return_value=self.receipt),patch.object(runner,'verify_wire') as wire,patch.object(runner,'verify_delivery') as delivery,patch.object(h.c,'audit') as audit:
   out=h.bare_json_job(self.job);req.assert_called_once();wire.assert_called_once();delivery.assert_called_once();audit.assert_called_once();return out
 def test_recovers_without_mutating(self):
  before={p.name:p.read_bytes() for p in self.job.iterdir()};self.assertEqual(self.invoke()['content'],{'bindings':[]});self.assertEqual(before,{p.name:p.read_bytes() for p in self.job.iterdir()})
 def test_rejects_nonzero_process(self):
  d=h.b.read(self.job/'execution.json');d['exit_code']=1;self.save('execution.json',d)
  with self.assertRaises(ValueError):self.invoke()
 def test_rejects_unknown_runtime_failure(self):
  self.save('runtime-failure.json',{'code':'unknown'})
  with self.assertRaises(ValueError):self.invoke()
 def test_rejects_other_json_fields(self):
  self.save('response.md',{'report':'fake'})
  with self.assertRaises(ValueError):self.invoke()
 def test_rejects_changed_session(self):
  d=h.b.read(self.job/'execution.json');d['session']={'id':'other'};self.save('execution.json',d)
  with self.assertRaises(ValueError):self.invoke()
 def test_rejects_already_parsable_envelope(self):
  (self.job/'response.md').write_text('```json\n{"bindings":[]}\n```')
  with self.assertRaises(ValueError):self.invoke()

class BindingRoutes(unittest.TestCase):
 def test_exact_original_routes(self):
  from research import earnings_inherited_profile_guard as g,earnings_file_pipeline as p
  v={'model_profile':None,'preparation_version':g.SIGNAL_BINDING_HANDLER,'models':p.profile_models('original-file-review-routes-v1'),'spent_correction_rounds':1,'session_count':4}
  self.assertTrue(g.matches_signal_binding(v,'original-file-review-routes-v1'))
  for key,bad in [('model_profile','other'),('preparation_version','other'),('models',{}),('spent_correction_rounds',2),('session_count',3)]:
   with self.subTest(key=key),self.assertRaises(ValueError):g.matches_signal_binding({**v,key:bad},'original-file-review-routes-v1')
