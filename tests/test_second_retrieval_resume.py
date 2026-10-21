import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_second_retrieval_resume as h,earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence

class ResumeTests(unittest.TestCase):
 def run_case(self,change=None,coverage_error=False):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);code=root/'.report-workflow'/('a'*40);code.mkdir(parents=True);job=root/'job';job.mkdir();(job/'prompt.md').write_text('bound resume prompt');source=root/'source';source.mkdir();(source/'protocol.json').write_text(json.dumps({'evidence_manifest':'manifest'}));(source/'passages.json').write_text('{}')
   v={'job':'original','index':'same-index','bindings':{'role':'retrieval'},'max_tokens':800000,'models':{'retrieval':['original','max']},'prior':{'source_root':str(source),'tokens':400000,'session_ids':['original','first'],'max_tokens':1200000,'models':{'retrieval':['original','max']},'case_sha256':'case','catalog_sha256':'catalog','writing_sha256':'writing','report_template':'source-led-six-sections-v1'}}
   resume={'number':1};q={'code_root':str(code),'resume':resume,'bindings':v['bindings'],'context_index':'same-index','model':'original','effort':'max','max_tokens':700000,'max_tool_calls':48};value={'content':{'valid':'candidate'},'receipt':{'session':{'id':'resumed','usage':{'totalTokens':50000}}}}
   if change:change(q,value)
   read=h.b.read
   def load(path):return q if Path(path)==job/'request.json' else read(path)
   def git(args,**kwargs):return ('a'*40+'\n') if args[1:3]==['rev-parse','HEAD'] else ('' if args[1]=='status' else 'https://github.com/yomogiu/equities-research.git\n')
   with patch.object(h,'__file__',str(code/'research/module.py')),patch.object(h,'plan',return_value=(v,job,100000,resume)),patch.object(h.b,'read',side_effect=load),patch.object(h.subprocess,'check_output',side_effect=git),patch.object(h.checkpoint,'restore'),patch.object(runner,'verify_job',return_value=value),patch.object(h,'instruction',return_value='bound resume prompt'),patch.object(h,'failed_sessions',return_value=(['failed'],100000)),patch.object(evidence,'load_bundle',return_value={}),patch.object(pipeline,'coverage',side_effect=ValueError('missing source') if coverage_error else None),patch.object(pipeline.pipe,'validate'):
    return h.completed(root)
 def test_failed_usage_and_all_distinct_sessions_are_retained(self):
  v=self.run_case();self.assertEqual(v['tokens'],550000);self.assertEqual(v['session_ids'],['original','first','failed','resumed']);self.assertEqual(v['spent_correction_rounds'],2)
 def test_changed_route_context_allowance_and_reused_session_reject(self):
  changes=[lambda q,v:q.update(model='other'),lambda q,v:q.update(context_index='other'),lambda q,v:q.update(max_tokens=800000),lambda q,v:q.update(bindings={}),lambda q,v:v['receipt']['session'].update(id='failed')]
  for change in changes:
   with self.assertRaises(ValueError):self.run_case(change)
 def test_complete_source_inspection_still_required(self):
  with self.assertRaisesRegex(ValueError,'missing source'):self.run_case(coverage_error=True)
 def test_unknown_execution_and_missing_checkpoint_do_not_plan(self):
  v={'job':'original','max_tokens':500000}
  with patch.object(h.original,'verify_reservation',return_value=v),patch.object(h.checkpoint,'select',side_effect=ValueError('uncertain')):
   with self.assertRaisesRegex(ValueError,'uncertain'):h.plan('root')
  with patch.object(h.original,'verify_reservation',return_value=v),patch.object(h.checkpoint,'select',return_value=(Path('job'),1000,None)):
   with self.assertRaises(ValueError):h.plan('root')
