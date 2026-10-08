"""Synthetic provider failures; no live requests."""
import copy
import json
from pathlib import Path
import unittest
from research import earnings_provider_recovery as p, earnings_mixed_runner as r, earnings_role_import as imp
from tests.test_earnings_mixed_runner import RunnerTests

class FailureTests(unittest.TestCase):
    def setUp(self):
        self.f=RunnerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.complete();self.job=self.f.job;self.code=Path(r.__file__).parent.parent
        for name in ('stdout.txt','output.json','runtime-finish.json'):(self.job/name).unlink()
        self.f.entries[-1]['message'].update(content=[],stopReason='error',usage={k:0 for k in ('input','output','cacheRead','cacheWrite','totalTokens')},
            diagnostics=[{'type':'provider_stream_failure','error':{'code':'server_is_overloaded'}}])
        self.f.write_journal()
        self.write('execution.json',{'status':'returned','exit_code':1,'elapsed_seconds':1.25,
            'request_sha256':r.digest(self.f.request),'launch_sha256':r.sha(self.job/'launch.json')})
        self.write('runtime-failure.json',{'stage':'output_validation'})
    def write(self,name,value):(self.job/name).write_text(json.dumps(value))
    def test_confirmed_failure_preserves_receipt(self):
        out=p.inspect_failure(self.job,self.code)
        self.assertEqual(out['reason'],'server_is_overloaded');self.assertEqual(out['usage']['totalTokens'],0)
        ref={'job':str(self.job),'code':str(self.code),'files':imp.inventory(self.job),'code_files':{},'receipt':out}
        p.validate(ref)
        p.require_retry_prompt({'provider_retry':ref},'analysis-r0',self.f.prompt,'gpt-6.1-sol','medium')
        with self.assertRaisesRegex(ValueError,'preserve original'):p.require_retry_prompt({'provider_retry':ref},'analysis-r0','different','gpt-6.1-sol','medium')
        self.write('runtime-failure.json',{'stage':'other'})
        with self.assertRaisesRegex(ValueError,'attempt changed'):p.validate(ref)
    def test_rejects_success_partial_tokens_and_other_errors(self):
        original=copy.deepcopy(self.f.entries)
        for edit in ({'stopReason':'stop'},{'content':[{'type':'text','text':'partial'}]},
                     {'usage':{'input':1,'output':0,'cacheRead':0,'cacheWrite':0,'totalTokens':1}},
                     {'diagnostics':[{'type':'provider_stream_failure','error':{'code':'other'}}]}):
            self.f.entries=copy.deepcopy(original);self.f.entries[-1]['message'].update(edit);self.f.write_journal()
            with self.assertRaises(ValueError):p.inspect_failure(self.job,self.code)
    def test_timeout_unknown_exit_and_forged_identity_rejected(self):
        original=r.read(self.job/'execution.json')
        for edit in ({'status':'timeout'},{'exit_code':None},{'launch_sha256':'wrong'}):
            self.write('execution.json',{**original,**edit})
            with self.assertRaises(ValueError):p.inspect_failure(self.job,self.code)
        self.write('execution.json',original)
        start=r.read(self.job/'runtime-start.json');self.write('runtime-start.json',{**start,'session_id':'other'})
        with self.assertRaises(ValueError):p.inspect_failure(self.job,self.code)
    def test_completed_wrapper_rejected(self):
        self.write('output.json',{})
        with self.assertRaisesRegex(ValueError,'Completed'):p.inspect_failure(self.job,self.code)

if __name__=='__main__':unittest.main()

class InitializationTests(unittest.TestCase):
    def test_successor_preserves_settings_and_binds_inherited_failure(self):
        import tempfile
        from unittest.mock import patch
        from research import earnings_passage_pipeline as pipe
        with tempfile.TemporaryDirectory() as temp:
            seed=Path(temp)/'source';seed.mkdir();out=Path(temp)/'successor'
            old={'version':pipe.VERSION,'max_correction_rounds':2,'models':{'fake':'unchanged'},
                 'code':[{'path':r.__file__,'sha256':r.sha(r.__file__)}]}
            (seed/'protocol.json').write_text(json.dumps(old));(seed/'passages.json').write_text('{}')
            for name in ('financial-r0','retrieval-r0','analysis-r0'):
                job=seed/'jobs'/name;job.mkdir(parents=True);(job/'request.json').write_text('{}')
            with patch.object(imp,'reference',side_effect=lambda job,code:{'job':str(job)}), \
                 patch.object(imp,'authenticate',side_effect=lambda ref:{'session':{'id':ref['job']}}), \
                 patch.object(p,'inspect_failure',return_value={'session_id':'failed','attempt':1}), \
                 patch.object(pipe,'load') as load:
                recovery=p.initialize(seed,out,'Explicit authorized recovery')
                load.assert_called_once_with(out.resolve())
                actual=r.read(out/'protocol.json')
                self.assertEqual(actual['max_correction_rounds'],2);self.assertEqual(actual['models'],old['models'])
                self.assertEqual(set(recovery['imports']),{'financial-r0','retrieval-r0'})
                self.assertEqual(recovery['attempt'],2);self.assertEqual(r.read(seed/'protocol.json'),old)
                with self.assertRaises(ValueError):p.initialize(seed,out,'Authorized')
                (seed/'result.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'Terminal'):p.initialize(seed,Path(temp)/'other','Authorized')

class RecoveryRegistryTests(unittest.TestCase):
    def test_missing_or_replaced_import_rejected_before_launch(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            seed=Path(t);code=Path(r.__file__).parent.parent
            (seed/'protocol.json').write_text(json.dumps({'code':[{'path':r.__file__}]}))
            for name in ('financial-r0','retrieval-r0','analysis-r0'):
                d=seed/'jobs'/name;d.mkdir(parents=True);(d/'request.json').write_text('{}')
            refs={n:{'job':str(seed/'jobs'/n)} for n in ('financial-r0','retrieval-r0')}
            recovery={'seed':str(seed),'imports':refs,'provider_retry':{'job':str(seed/'jobs/analysis-r0'),'code':str(code)}}
            with patch.object(imp,'reference',side_effect=lambda job,code:{'job':str(job)}):
                imp.validate_recovery(recovery)
                broken=copy.deepcopy(recovery);broken['imports'].pop('financial-r0')
                with self.assertRaisesRegex(ValueError,'All completed'):imp.validate_recovery(broken)
                broken=copy.deepcopy(recovery);broken['imports']['financial-r0']={'job':'other'}
                with self.assertRaisesRegex(ValueError,'provenance'):imp.validate_recovery(broken)
                broken=copy.deepcopy(recovery);broken['provider_retry']['job']='other'
                with self.assertRaisesRegex(ValueError,'original first'):imp.validate_recovery(broken)
