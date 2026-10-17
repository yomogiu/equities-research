"""Fictitious once-only terminal provider failure; no credentials or model calls."""
import tempfile
import unittest
from pathlib import Path
from research import earnings_signal_overload_recovery as recovery,earnings_mixed_runner as r


class SignalOverloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.seed=self.root/'pipeline';self.job=self.seed/'batch-jobs/signal_author';self.job.mkdir(parents=True)
        r.save(self.seed/'protocol.json',{'signal_author_model':['gpt-6.1-sol','low']});r.save(self.root/'state.json',{'status':'execution_failed'})
        (self.job/'prompt.txt').write_text('Fictional source prompt')
        self.request={'version':'mixed-prime-role-v1','provider':'openai-codex','model':'gpt-6.1-sol','effort':'low','prompt_sha256':r.sha(self.job/'prompt.txt'),'bindings':{'role':'signal_author','protocol_sha256':r.sha(self.seed/'protocol.json')}}
        r.save(self.job/'request.json',self.request);r.save(self.job/'launch.json',{'id':'fake-launch','request_sha256':r.digest(self.request)})
        r.save(self.job/'execution.json',{'status':'returned','exit_code':1,'request_sha256':r.digest(self.request),'launch_sha256':r.sha(self.job/'launch.json')})
        r.save(self.job/'runtime-start.json',{'launch_id':'fake-launch','session_id':'fake-session','model':'gpt-6.1-sol','effort':'low','provider':'openai-codex','oauth':True})
        r.save(self.job/'runtime-failure.json',{'stage':'output_validation'});r.save(self.job/'wire.json',[{'model':'gpt-6.1-sol','effort':'low','tools':0}]);r.save(self.job/'token-estimate.json',{'prompt_sha256':self.request['prompt_sha256'],'estimated_input_tokens':6,'utf8_bytes':24})
        self.terminal={'role':'assistant','content':[],'stopReason':'error','errorMessage':recovery.ERROR,'model':'gpt-6.1-sol','provider':'openai-codex','usage':{k:0 for k in ('input','output','cacheRead','cacheWrite','totalTokens')},'diagnostics':[{'error':{'code':'server_is_overloaded'}}]}
        (self.job/'sessions').mkdir();self.journal=self.job/'sessions/fake.jsonl';self.write_journal()
    def write_journal(self):
        import json
        records=[{'type':'session','id':'fake-session','cwd':str(self.job)},{'type':'message','message':{'role':'user','content':'Fake'}},{'type':'message','message':self.terminal}]
        self.journal.write_text('\n'.join(json.dumps(v) for v in records)+'\n')
    def test_conclusive_failure_retains_reported_zero_and_conservative_uncertainty(self):
        value=recovery.inspect(self.seed);self.assertEqual(value['recorded_total_tokens'],0);self.assertTrue(value['usage_is_unknown']);self.assertEqual(value['failed_request_upper_bound_tokens'],272000)
    def test_partial_output_rejected(self):
        (self.job/'output.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'ambiguity'):recovery.inspect(self.seed)
    def test_nonterminal_or_nonempty_response_rejected(self):
        self.terminal['content']=[{'type':'text','text':'Partial answer'}];self.write_journal()
        with self.assertRaisesRegex(ValueError,'Unknown/nonterminal'):recovery.inspect(self.seed)
    def test_different_model_rejected(self):
        (self.job/'wire.json').write_text('[{"model":"fake-other","effort":"low","tools":0}]')
        with self.assertRaisesRegex(ValueError,'original provider'):recovery.inspect(self.seed)
    def test_repeated_retry_rejected(self):
        (self.seed/'protocol.json').write_text('{"signal_provider_recovery":{}}')
        with self.assertRaisesRegex(ValueError,'Repeated'):recovery.inspect(self.seed)
