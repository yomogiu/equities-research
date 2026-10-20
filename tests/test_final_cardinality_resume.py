import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_final_cardinality_resume as h,earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence

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

class CanonicalResumeTests(unittest.TestCase):
 def fixture(self,private):
  private=private.resolve()
  run='b'*24;source=private/'reporting/runs'/run/'pipeline';request=source/'jobs/retrieval/request.json';request.parent.mkdir(parents=True);request.write_text(json.dumps({'code_root':str(private/'.report-workflow'/('a'*40))}))
  first=private/'reporting/repairs/retrieval-addresses'/run;root=private/'reporting/repairs/retrieval-final'/run;first.mkdir(parents=True);root.mkdir(parents=True)
  (first/'reservation.json').write_text(json.dumps({'previous_root':str(source)}));v={'previous_repair':str(first),'prior':{'source_root':str(source),'tokens':350000,'max_tokens':1200000,'spent_correction_rounds':1},'spent_correction_rounds':2};(root/'reservation.json').write_text(json.dumps(v));job=root/'jobs/retrieval-repair-2--resume-1';return run,source,first,root,v,job
 def test_exact_existing_slots_reuse_without_creation_or_usage_reset(self):
  with tempfile.TemporaryDirectory() as d:
   run,source,first,root,v,job=self.fixture(Path(d));before={p:p.read_bytes() for p in [first/'reservation.json',root/'reservation.json']}
   with patch.object(h,'plan',return_value=(v,job,150000,{'number':1})):
    proof=h.canonical_plan(root)[4];self.assertEqual(proof['canonical_tokens'],500000);self.assertEqual(proof['remaining_original_allowance'],700000);self.assertFalse(job.exists());self.assertFalse(proof['new_reservation'])
   self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))
 def test_unknown_normalized_legacy_slot_and_duplicate_sibling_reject(self):
  with tempfile.TemporaryDirectory() as d:
   run,source,first,root,v,job=self.fixture(Path(d));legacy=root.parent.parent/'alternate/reservation.json';legacy.parent.mkdir();legacy.write_text(json.dumps({'nested':[str(source.parent/'unused/../pipeline')]}))
   with patch.object(h,'plan',return_value=(v,job,150000,{'number':1})):
    with self.assertRaisesRegex(ValueError,'Alternate/legacy'):h.canonical_plan(root)
    legacy.unlink();job.mkdir(parents=True)
    with self.assertRaisesRegex(ValueError,'duplicate launch'):h.canonical_plan(root)
 def test_changed_canonical_slot_and_accounting_reject(self):
  with tempfile.TemporaryDirectory() as d:
   run,source,first,root,v,job=self.fixture(Path(d))
   with patch.object(h,'plan',return_value=(v,job,900000,{'number':1})):
    with self.assertRaisesRegex(ValueError,'original cap'):h.canonical_plan(root)
   v['previous_repair']=str(first.parent/'other')
   with patch.object(h,'plan',return_value=(v,job,100000,{'number':1})):
    with self.assertRaisesRegex(ValueError,'canonical first'):h.canonical_plan(root)
