"""Fictitious label repair, preserving accepted research and reviewed signals."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from test_earnings_signals import SignalTests
from research import earnings_signal_label_repair as m

class SignalLabelRepairTests(PassageFixture,unittest.TestCase):
    state=SignalTests.state
    pack=SignalTests.pack
    review=SignalTests.review
    def setUp(self):
        super().setUp();self.root=self.root.resolve();self.seed=self.root/'seed';self.seed.mkdir();self.out=self.root/'edition'
        state=self.state();pack=self.pack(state);review=self.review(pack);review['verdict']='blocked';review['decisions'][2]['approved']=False
        self.export={'state':state,'pack':pack,'review':review,'tokens':12345}
        writing=self.root/'writing.txt';writing.write_text('Fictional concise standard')
        self.old={'version':m.signals.VERSION,'code':[],'source_code':[],'source_bindings':{},'source_protocol':{'writing_standard':str(writing)},'max_prompt_chars':1500000,'excluded_session_ids':['original-author','original-reviewer']}
        m.runner.save(self.seed/'protocol.json',self.old)
        self.plan={'signals_sha256':m.runner.digest(pack),'changes':[{'signal_id':'signal-3','before':'Fictional result','after':'Fictional shipments await site readiness','reason':'Preserve shipment condition','citations':['D001'],'passage_ids':[self.ids[0]]}]}
        self.auth={'version':m.VERSION,'enabled':True,'seed_protocol_sha256':m.runner.sha(self.seed/'protocol.json'),'plan_sha256':m.runner.digest(self.plan),'output_path':str(self.out),'authorized_by':'Fictional user','reason':'Finish exact signal label repair'}
        original=patch.object(m,'original',return_value=(self.old,self.export));original.start();self.addCleanup(original.stop)
        bundle=patch.object(m.remediation,'_source_bundle',return_value=(self.bundle,self.catalog));bundle.start();self.addCleanup(bundle.stop)
    def init(self):return m.initialize(self.seed,self.out,self.plan,self.auth)
    def test_only_rejected_label_changes_and_every_other_byte_is_preserved(self):
        before=copy.deepcopy(self.export);candidate=m.apply(before['pack'],before['review'],self.plan)
        expected=copy.deepcopy(before['pack']);expected['signals'][2]['label']=self.plan['changes'][0]['after']
        self.assertEqual(candidate,expected);self.assertEqual(before,self.export)
        self.init();p,state,pack,*_=m.load(self.out)
        self.assertEqual(state,before['state']);self.assertEqual(pack,expected)
        self.assertEqual(p['historical_signal_tokens'],12345);self.assertEqual(p['max_review_attempts'],1)
    def test_approved_signal_other_fields_missing_evidence_and_stale_plan_rejected(self):
        mutations=[lambda p:p['changes'][0].update(signal_id='signal-1'),lambda p:p['changes'][0].update(summary='rewrite'),lambda p:p['changes'][0].update(before='stale'),lambda p:p['changes'][0].update(passage_ids=['invented']),lambda p:p['changes'].append(copy.deepcopy(p['changes'][0])),lambda p:p.update(signals_sha256='stale')]
        for mutate in mutations:
            p=copy.deepcopy(self.plan);mutate(p)
            with self.assertRaises(ValueError):m.apply(self.export['pack'],self.export['review'],p)
    def test_unknown_source_usage_is_not_silently_dropped(self):
        self.old['source_usage_uncertainty']={'total_tokens':None}
        with self.assertRaisesRegex(ValueError,'Unknown source usage'):self.init()
        self.assertFalse(self.out.exists())

    def test_second_successor_and_protocol_tampering_rejected(self):
        self.init();other=self.root/'other'
        with self.assertRaisesRegex(ValueError,'already reserved'):m.initialize(self.seed,other,self.plan,{**self.auth,'output_path':str(other)})
        p=m.runner.read(self.out/'protocol.json');p['max_review_attempts']=2;(self.out/'protocol.json').write_text(json.dumps(p))
        with self.assertRaises(ValueError):m.load(self.out)
    def complete(self,sid='new-review'):
        p,state,pack,b,k,w=m.load(self.out);job=self.out/'jobs/review';job.mkdir(parents=True)
        (job/'prompt.txt').write_text(m.signals.prompt('review',state,b,k,w,pack))
        binding={'protocol_sha256':m.runner.sha(self.out/'protocol.json'),'signals_sha256':m.runner.digest(pack),'report_sha256':m.signals.report_digest(state),'role':'signal_label_review','review_attempt':2}
        m.runner.save(job/'request.json',{'bindings':binding,'model':p['model'][0],'effort':p['model'][1]})
        result={'content':self.review(pack),'receipt':{'session':{'id':sid,'usage':{'totalTokens':789}}}};m.runner.save(job/'output.json',result);return result
    def test_fresh_review_checks_entire_pack_then_accepts_without_author_call(self):
        self.init();result=self.complete()
        with patch.object(m.runner,'verify_job',return_value=result),patch.object(m.runner,'run_role') as run:
            out=m.advance(self.out,True);self.assertEqual(out['status'],'accepted');self.assertEqual(out['total_signal_tokens'],13134);run.assert_not_called()
        self.assertTrue((self.out/'report.html').exists());self.assertFalse((self.out/'jobs/analysis').exists())
    def test_uncertain_call_and_original_reviewer_session_never_retry(self):
        self.init();job=self.out/'jobs/review';job.mkdir(parents=True);m.runner.save(job/'launch.json',{})
        with patch.object(m.runner,'run_role') as run:self.assertEqual(m.advance(self.out,True)['status'],'execution_uncertain');run.assert_not_called()
        (job/'launch.json').unlink();job.rmdir();result=self.complete('original-reviewer')
        with patch.object(m.runner,'verify_job',return_value=result):
            with self.assertRaisesRegex(ValueError,'Independent'):m.verify(self.out)
    def test_rejected_fresh_review_stops_without_report_or_additional_review(self):
        self.init();result=self.complete();result['content']['verdict']='blocked';result['content']['decisions'][2]['approved']=False
        with patch.object(m.runner,'verify_job',return_value=result),patch.object(m.runner,'run_role') as run:
            self.assertEqual(m.advance(self.out,True)['status'],'blocked');run.assert_not_called()
        self.assertFalse((self.out/'report.html').exists())

if __name__=='__main__':unittest.main()

class OriginalSignalReplayTests(unittest.TestCase):
    def test_original_verifier_and_accepted_report_replay_are_required(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=root/'signals';seed.mkdir();source=root/'report';source.mkdir();code=root/'code/research';code.mkdir(parents=True)
            (code/'__init__.py').write_text('')
            (code/'earnings_passage_pipeline.py').write_text('# fictional code identity')
            script="""import json
class base:
 @staticmethod
 def read(p):return json.loads(p.read_text())
def load(root):return base.read(root/'protocol.json'),{'artifacts':{},'format':{}},None,None,''
def verify(root):return {'status':base.read(root/'fixture.json')['status'],'tokens':7}
def verify_job(job):return {'content':{'verdict':'blocked'}}
EXPORT="import json;print(json.dumps({'state':{'artifacts':{},'format':{}}}))"
"""
            module=code/'earnings_signals.py';module.write_text(script)
            records=[{'path':str(p),'sha256':m.runner.sha(p)} for p in code.glob('earnings_*')]
            m.runner.save(seed/'protocol.json',{'version':m.signals.VERSION,'seed':str(source),'code':records,'source_code':[]})
            m.runner.save(source/'protocol.json',{'code':records});m.runner.save(seed/'fixture.json',{'status':'blocked'});m.runner.save(seed/'signals.json',{'signals':[]})
            _,export=m.original(seed);self.assertEqual(export['tokens'],7)
            (seed/'fixture.json').write_text(json.dumps({'status':'accepted'}))
            with self.assertRaises(Exception):m.original(seed)
            (seed/'fixture.json').write_text(json.dumps({'status':'blocked'}));module.write_text(script+'\n# changed')
            with self.assertRaisesRegex(ValueError,'verifier changed'):m.original(seed)
