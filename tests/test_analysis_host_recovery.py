import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_analysis_host_recovery as h
class HostRecoveryTests(unittest.TestCase):
 def fixture(self,root):
  job=root/'job';job.mkdir();code=root/'code/research';code.mkdir(parents=True);prime=code/'earnings_file_prime.mjs';prime.write_text("stage = 'auth_storage';auth.drainErrors();stage = 'registry';")
  q={'code_root':str(code.parent),'helper_sha256':h.b.sha(prime)};h.c.write(job/'request.json',q);h.c.write(job/'launch.json',{'id':'fixed'});h.c.write(job/'execution.json',{'status':'execution_failed','exit_code':1,'request_sha256':h.b.digest(q),'launch_sha256':h.b.sha(job/'launch.json')});h.c.write(job/'runtime-failure.json',{'stage':'auth_storage'});h.c.write(job/'wire.json',[]);(job/'retrieval.jsonl').touch();return job
 def test_exact_premodel_stop_and_all_failed_bytes_bound(self):
  with tempfile.TemporaryDirectory() as d:
   j=self.fixture(Path(d));v=h.stopped(j);self.assertIn('request.json',v);self.assertIn('runtime-failure.json',v);self.assertEqual(len(v),6)
 def test_runtime_session_transport_and_evidence_fail_closed(self):
  for name in ['sessions','runtime-start.json','runtime-finish.json','output.json','response.md','delivery.jsonl','transport-lifecycle.jsonl']:
   with tempfile.TemporaryDirectory() as d:
    j=self.fixture(Path(d));(j/name).touch()
    with self.assertRaises(ValueError):h.stopped(j)
  with tempfile.TemporaryDirectory() as d:
   j=self.fixture(Path(d));(j/'retrieval.jsonl').write_text('evidence')
   with self.assertRaises(ValueError):h.stopped(j)
 def test_uncertain_or_changed_stage_request_helper_refused(self):
  for name,value in [('wire.json',[{'phase':'started'}]),('runtime-failure.json',{'stage':'model_request'}),('execution.json',{'status':'execution_failed','exit_code':1,'request_sha256':'changed','launch_sha256':'changed'})]:
   with tempfile.TemporaryDirectory() as d:
    j=self.fixture(Path(d));(j/name).write_text(json.dumps(value))
    with self.assertRaises(ValueError):h.stopped(j)
 def test_fixed_child_preserves_original_budget_models_bindings(self):
  from research import earnings_analysis_address_repair as a
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);j=self.fixture(root);(root/'jobs').mkdir();j.rename(root/'jobs/address-repair');h.c.write(root/'reservation.json',{});prior=root/'prior';prior.mkdir();h.c.write(prior/'protocol.json',{})
   v={'previous_root':str(prior),'index':'original-index','bindings':{'original':'bound'},'models':{'analysis':['original','max']},'max_tokens':846709}
   with patch.object(a,'prompt',return_value='exact assignment'):
    m=h.expected(root,v)
   self.assertEqual(m['job'],str(root/'jobs/auth-recovery-1'));self.assertEqual(m['max_tokens'],846709);self.assertEqual(m['models'],v['models']);self.assertEqual(m['bindings']['original'],'bound');self.assertEqual(m['max_tool_calls'],48)
 def test_manifest_cannot_change_models_limits_prompt_or_failed_hashes(self):
  from research import earnings_analysis_address_repair as a
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);code=root/'.report-workflow'/('a'*40);base={'version':h.VERSION,'models':{'analysis':['original','max']},'max_tokens':846709,'max_tool_calls':48,'prompt':'exact','failed_artifacts':{'request.json':'original'},'job':str(root/'jobs/auth-recovery-1')};v={'previous_root':str(root/'prior'),'source_currentness':{}}
   for field,value in [('models',{}),('max_tokens',1200000),('max_tool_calls',99),('prompt','changed'),('failed_artifacts',{}),('job',str(root/'jobs/another'))]:
    (root/'host-recovery.json').write_text(json.dumps({**base,'code_root':str(code),field:value}))
    with patch.object(a,'verify_reservation',return_value=v),patch.object(a,'currentness'),patch.object(h,'expected',return_value=base):
     with self.assertRaises(ValueError):h.verify(root)

from test_analysis_address_repair import AnalysisRepairPipelineTests
class HostPipelineTests(AnalysisRepairPipelineTests):
 def test_three_sessions_one_spent_round_and_original_budget_survive_pipeline(self):
  from research import earnings_analysis_address_repair as a
  with patch.object(a,'PREPARATION_VERSION',h.PREPARATION_VERSION):
   super().test_three_sessions_one_spent_round_and_original_budget_survive_pipeline()
