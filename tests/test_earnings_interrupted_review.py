"""Fictional interruption recovery, no credentials or model calls."""
import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from test_earnings_passages import PassageFixture
import test_earnings_remediation as remediation_tests
import test_earnings_corrections as correction_tests
from research import earnings_interrupted_review as m
from research import earnings_mixed_runner as r, earnings_signals as signals

class InterruptedReviewTests(PassageFixture, unittest.TestCase):
    state=correction_tests.CorrectionTests.state
    op=correction_tests.CorrectionTests.op
    plan=correction_tests.CorrectionTests.plan
    review=remediation_tests.RemediationTests.review

    def setUp(self):
        super().setUp();self.root=self.root.resolve();self.seed=self.root/'seed';self.seed.mkdir();self.out=self.root/'successor'
        self.old={'code':[],'source_code':[],'source_bindings':{},'source_protocol':{},'model':list(m.corrections.MODEL),
                  'prior_rounds':1,'max_rounds':1,'inherited_tokens':50,'max_tokens':None}
        r.save(self.seed/'protocol.json',self.old);job=self.seed/'rounds/0/review';job.mkdir(parents=True);r.save(job/'request.json',{'fictional':True})
        before=self.state();plan=self.plan(before);candidate=m.corrections.apply(before,plan,self.bundle,self.catalog)
        self.export={'before':before,'plan':plan,'candidate':candidate,'prompt':'exact fictional unchanged review prompt','known_tokens':125}
        (job/'prompt.txt').write_text(self.export['prompt'])
        self.auth={'version':m.VERSION,'enabled':True,'seed_protocol_sha256':r.sha(self.seed/'protocol.json'),
                   'output_path':str(self.out),'authorized_by':'Explicit fictional user','reason':'Resume stopped review only',
                   'unknown_usage_authorization':'Prior unknown usage remains unknown; authorize one distinct review.'}
        self.pause=self.root/'pause.json';self.inventory=self.root/'inventory.json';r.save(self.pause,{});r.save(self.inventory,{})
        self.proof={'pause_record':str(self.pause),'pause_sha256':r.sha(self.pause),'partial_inventory':str(self.inventory),'partial_inventory_sha256':r.sha(self.inventory)}
        original=patch.object(m,'original',return_value=(self.old,self.export,'interrupted-session'));original.start();self.addCleanup(original.stop)
        bundle=patch.object(m.remediation,'_source_bundle',return_value=(self.bundle,self.catalog));bundle.start();self.addCleanup(bundle.stop)

    def edition(self):
        m.initialize(self.seed,self.out,self.auth,self.proof);return self.out

    def complete(self,sid='fresh-review',verdict='pass'):
        p,e,_,_=m.load(self.out);job=self.out/'review';job.mkdir();(job/'prompt.txt').write_text(e['prompt'])
        bindings={'protocol_sha256':r.sha(self.out/'protocol.json'),'role':'interrupted_report_review','review_attempt':2,
                  'candidate_sha256':p['candidate_sha256'],'plan_sha256':p['plan_sha256'],'interrupted_session_id':'interrupted-session'}
        r.save(job/'request.json',{'bindings':bindings,'model':p['model'][0],'effort':p['model'][1]})
        content=self.review(e['before'],e['plan'],e['candidate'],verdict=verdict)
        result={'content':content,'receipt':{'session':{'id':sid,'usage':{'totalTokens':91}}}};r.save(job/'output.json',result);return result

    def test_one_exact_review_preserves_unknown_usage_and_no_round_reset(self):
        self.edition();p,e,_,_=m.load(self.out)
        self.assertEqual((p['correction_round'],p['remaining_correction_rounds'],p['review_attempt']),(2,0,2))
        self.assertIsNone(p['total_tokens']);self.assertIsNone(p['unknown_prior_usage']['total_tokens'])
        self.assertEqual(p['known_correction_tokens'],175)
        with patch.object(m.runner,'run_role') as run:self.assertEqual(m.verify(self.out)['status'],'pending');run.assert_not_called()
        result=self.complete()
        with patch.object(m.runner,'verify_job',return_value=result),patch.object(m.runner,'run_role') as run:
            v=m.advance(self.out,True);self.assertEqual(v['status'],'accepted');self.assertEqual(v,m.verify(self.out));run.assert_not_called()
        self.assertEqual(v['measured_new_tokens'],91);self.assertIsNone(v['total_tokens']);self.assertTrue((self.out/'report.html').exists())
        self.assertEqual((self.seed/'rounds/0/review/prompt.txt').read_text(),e['prompt'])

    def test_second_successor_and_modified_accounting_rejected(self):
        self.edition();other=self.root/'fork'
        with self.assertRaisesRegex(ValueError,'already reserved'):m.initialize(self.seed,other,{**self.auth,'output_path':str(other)},self.proof)
        original=r.read(self.out/'protocol.json')
        for key,value in [('review_attempt',1),('remaining_correction_rounds',1),('max_tokens',600000),('unknown_prior_usage',{}),('known_prior_tokens',999)]:
            bad={**original,key:value};(self.out/'protocol.json').write_text(json.dumps(bad))
            with self.assertRaises(ValueError):m.load(self.out)
        (self.out/'protocol.json').write_text(json.dumps(original))
        (self.out/'prompt.txt').write_text('different prompt')
        with self.assertRaisesRegex(ValueError,'prompt changed'):m.load(self.out)

    def test_uncertain_successor_never_retries_or_reuses_original_session(self):
        self.edition();job=self.out/'review';job.mkdir();r.save(job/'launch.json',{})
        with patch.object(m.runner,'run_role') as run:
            self.assertEqual(m.advance(self.out,True)['status'],'execution_uncertain');run.assert_not_called()
        (job/'launch.json').unlink();job.rmdir();result=self.complete(sid='interrupted-session')
        with patch.object(m.runner,'verify_job',return_value=result):
            with self.assertRaisesRegex(ValueError,'Distinct'):m.verify(self.out)

    def test_revise_cannot_create_another_correction_round(self):
        self.edition();result=self.complete(verdict='revise')
        with patch.object(m.runner,'verify_job',return_value=result):self.assertEqual(m.verify(self.out)['status'],'blocked')
        self.assertFalse((self.out/'result.json').exists())

    def test_blocked_or_needs_evidence_never_accepts_or_launches_again(self):
        self.edition();result=self.complete(verdict='blocked')
        with patch.object(m.runner,'verify_job',return_value=result),patch.object(m.runner,'run_role') as run:
            self.assertEqual(m.advance(self.out,True)['status'],'blocked');run.assert_not_called()
            result['content']={'verdict':'needs_evidence'}
            self.assertEqual(m.advance(self.out,True)['status'],'blocked');run.assert_not_called()
        self.assertFalse((self.out/'result.json').exists())
        self.assertFalse((self.out/'report.html').exists())

    def test_concurrent_claim_reservations_have_only_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2);original_save=m.runner.save;claim=m.claim_path(self.seed)
        def save(path,value):
            if Path(path)==claim:barrier.wait(timeout=5)
            return original_save(path,value)
        outputs=[self.out,self.root/'other-output']
        def initialize(out):
            try:m.initialize(self.seed,out,{**self.auth,'output_path':str(out)},self.proof);return 'reserved'
            except FileExistsError:return 'lost'
        with patch.object(m.runner,'save',side_effect=save),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(initialize,outputs))
        self.assertEqual(sorted(results),['lost','reserved'])
        self.assertEqual(sum(p.exists() for p in outputs),1)
        self.assertTrue(Path(r.read(claim)['output']).exists())

    def test_live_original_helper_is_rejected(self):
        job=Path('/fictional/review')
        with patch.object(subprocess,'check_output',return_value='42 node /f/earnings_mixed_prime.mjs /sdk /fictional/review\n'):
            with self.assertRaisesRegex(ValueError,'still running'):m.no_live_process(job)

    def test_signal_export_keeps_unknown_usage_and_session_exclusion(self):
        import contextlib,io,sys
        self.edition();result=self.complete()
        r.save(self.out/'review/execution.json',result['receipt'])
        with patch.object(m.runner,'verify_job',return_value=result):
            self.assertEqual(m.verify(self.out)['status'],'accepted')
            with patch.object(sys,'argv',['export',str(self.out)]),contextlib.redirect_stdout(io.StringIO()) as capture:
                exec(signals.EXPORT,{})
        exported=json.loads(capture.getvalue())
        self.assertEqual(exported['source_usage_uncertainty']['status'],'unknown_interrupted_request')
        self.assertIsNone(exported['source_usage_uncertainty']['total_tokens'])
        self.assertEqual(set(exported['excluded_session_ids']),{'interrupted-session','fresh-review'})
        self.assertEqual(exported['state']['artifacts'],self.export['candidate']['artifacts'])

class OriginalProofTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.seed=self.root/'seed';self.job=self.seed/'rounds/0/review';self.job.mkdir(parents=True)
        author=self.seed/'rounds/0/propose';author.mkdir();r.save(author/'request.json',{})
        self.code=self.root/'code/research';self.code.mkdir(parents=True);(self.code/'__init__.py').write_text('')
        (self.code/'earnings_corrections.py').write_text("import json\nclass base:\n @staticmethod\n def read(p):return json.loads(p.read_text())\ndef load(root):return base.read(root/'protocol.json'),None,None,None\ndef replay(root,p,b,k,w):return base.read(root/'fictional-replay.json')\n")
        (self.code/'earnings_mixed_runner.py').write_text('# fictional runner')
        (self.code/'earnings_mixed_prime.mjs').write_text('// fictional helper')
        self.old={'version':'deterministic-corrections-v1','max_tokens':None,'prior_rounds':1,'max_rounds':1,'model':list(m.corrections.MODEL),
                  'source_code':[],'code':[{'path':str(p),'sha256':r.sha(p)} for p in self.code.glob('earnings_*')]}
        r.save(self.seed/'protocol.json',self.old);r.save(self.seed/'rounds/0/plan.json',{'exact':'plan'});r.save(self.seed/'rounds/0/candidate.json',{'exact':'candidate'})
        text='Original fictional exact prompt';(self.job/'prompt.txt').write_text(text)
        self.request={'job_path':str(self.job),'model':m.corrections.MODEL[0],'effort':m.corrections.MODEL[1],
                      'provider':r.PROVIDER,'bindings':{'candidate_sha256':r.digest({'exact':'candidate'})},
                      'prompt_sha256':r.sha(self.job/'prompt.txt'),'runner_sha256':r.sha(self.code/'earnings_mixed_runner.py'),
                      'helper_sha256':r.sha(self.code/'earnings_mixed_prime.mjs')}
        r.save(self.job/'request.json',self.request);r.save(self.job/'launch.json',{'id':'launch','request_sha256':r.digest(self.request)})
        r.save(self.job/'runtime-start.json',{'launch_id':'launch','session_id':'old-session','model':self.request['model'],
               'effort':self.request['effort'],'provider':r.PROVIDER,'oauth':True})
        r.save(self.seed/'fictional-replay.json',{'status':'launch_uncertain','role':'review','round':0,'state':{'exact':'before'},
               'prompt':text,'bindings':self.request['bindings'],'tokens':125})
        pause=self.root/'pause.json';inventory=self.root/'inventory.json'
        r.save(pause,{'paused':True,'processes':{'terminated_pids':[999999]},'interrupted_jobs':['seed/rounds/0/review']})
        r.save(inventory,{'job':str(self.job),'files':m.imports.inventory(self.job)})
        self.proof={'job':str(self.job),'request_sha256':r.sha(self.job/'request.json'),'launch_sha256':r.sha(self.job/'launch.json'),
                    'session_id':'old-session','candidate_sha256':r.digest({'exact':'candidate'}),'prompt_sha256':r.sha(self.job/'prompt.txt'),
                    'pause_record':str(pause),'pause_sha256':r.sha(pause),'partial_inventory':str(inventory),
                    'partial_inventory_sha256':r.sha(inventory),'model_pid':999999,'observed_stopped_at':'fictional-time','attested_by':'fictional host supervisor'}
        stop=patch.object(m,'no_live_process');stop.start();self.addCleanup(stop.stop)

    def test_original_frozen_replay_and_exact_stop_proof(self):
        old,e,sid=m.original(self.seed,self.proof);self.assertEqual(sid,'old-session');self.assertEqual(e['known_tokens'],125)
        self.assertEqual(e['candidate'],{'exact':'candidate'})
        for key,value in [('session_id','other'),('model_pid',17),('candidate_sha256','wrong'),('attested_by','')]:
            with self.assertRaises(ValueError):m.original(self.seed,{**self.proof,key:value})
        (self.job/'prompt.txt').write_text('changed')
        with self.assertRaises(ValueError):m.original(self.seed,self.proof)

    def test_existing_output_journal_and_finite_budget_require_reconciliation(self):
        for name in ('stdout.txt','execution.json','runtime-finish.json','output.json'):
            p=self.job/name;p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Completed or failed'):m.original(self.seed,self.proof)
            p.unlink()
        journal=self.job/'sessions/any.jsonl';journal.parent.mkdir();journal.write_text('{}\n')
        with self.assertRaisesRegex(ValueError,'journal'):m.original(self.seed,self.proof)
        journal.unlink();(self.seed/'protocol.json').write_text(json.dumps({**self.old,'max_tokens':600000}))
        with self.assertRaisesRegex(ValueError,'finite cap'):m.original(self.seed,self.proof)

    def test_nonreview_and_partial_inventory_tampering_rejected(self):
        replay=self.seed/'fictional-replay.json';v=r.read(replay);v['role']='propose';replay.write_text(json.dumps(v))
        with self.assertRaises(subprocess.CalledProcessError):m.original(self.seed,self.proof)
        v['role']='review';replay.write_text(json.dumps(v));(self.job/'unexpected.txt').write_text('partial update')
        with self.assertRaisesRegex(ValueError,'Interrupted bytes'):m.original(self.seed,self.proof)
