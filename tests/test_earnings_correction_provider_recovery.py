"""Synthetic terminal provider failures and immutable successor accounting."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_correction_provider_recovery as c
from research import earnings_provider_recovery as p, earnings_mixed_runner as r
from tests.test_earnings_provider_recovery import FailureTests

class ServerFailureTests(unittest.TestCase):
    def setUp(self):
        self.fx=FailureTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.fx.f.entries[-1]['message']['diagnostics'][0]['error']['code']='server_error'
        self.fx.f.write_journal()
    def test_explicit_server_error_does_not_expand_default_overload_contract(self):
        with self.assertRaises(ValueError):p.inspect_failure(self.fx.job,self.fx.code)
        receipt=p.inspect_failure(self.fx.job,self.fx.code,error_code='server_error')
        self.assertEqual(receipt['reason'],'server_error')
        with self.assertRaises(ValueError):p.inspect_failure(self.fx.job,self.fx.code,error_code='any_error')
    def test_completed_partial_and_unknown_usage_cannot_resume(self):
        original=copy.deepcopy(self.fx.f.entries)
        for edit in ({'content':[{'type':'text','text':'partial result'}]}, {'stopReason':'stop'}, {'usage':{}}, {'usage':{'input':0,'output':1,'cacheRead':0,'cacheWrite':0,'totalTokens':1}}):
            self.fx.f.entries=copy.deepcopy(original);self.fx.f.entries[-1]['message'].update(edit);self.fx.f.write_journal()
            with self.assertRaises(ValueError):p.inspect_failure(self.fx.job,self.fx.code,error_code='server_error')

class EditionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.seed=Path(self.temp.name)/'seed';self.seed.mkdir()
        self.old={'version':'deterministic-corrections-v1','code':[],'source_code':[], 'source_protocol':{'original':'unchanged'},
                  'source_bindings':{},'prior_rounds':1,'max_rounds':1,'inherited_tokens':125,'max_tokens':600000,
                  'model':['gpt-6.1-sol','medium'],'initial_sha256':'fixed','imported_proposal':None,'new_experiment':False}
        r.save(self.seed/'protocol.json',self.old);r.save(self.seed/'initial.json',{'findings':['source-bound']})
        self.export={'initial':{'findings':['source-bound']},'prompt':'exact original\nsource prompt'}
        self.receipt={'session_id':'failed-session','usage':{'totalTokens':0},'reason':'server_error'}
        self.auth={'version':c.VERSION,'enabled':True,'source_protocol_sha256':r.sha(self.seed/'protocol.json'),
                   'token_policy':'uncapped','authorized_by':'synthetic explicit user instruction','reason':'Retain failed attempt; no reset.'}
        self.mock=patch.object(c,'original',return_value=(self.old,Path(self.temp.name),self.export,self.receipt));self.mock.start();self.addCleanup(self.mock.stop)
    def test_preserves_rounds_sources_and_usage_and_requires_new_directory(self):
        out=Path(self.temp.name)/'new';c.initialize(self.seed,out,self.auth);p0=r.read(out/'protocol.json')
        self.assertEqual((p0['prior_rounds'],p0['max_rounds'],p0['inherited_tokens']),(1,1,125))
        self.assertIsNone(p0['max_tokens']);self.assertEqual(p0['source_protocol'],self.old['source_protocol'])
        c.validate(p0,self.export['initial']);self.assertIn('not proof',p0['correction_provider_recovery']['usage_uncertainty'])
        with self.assertRaises(ValueError):c.initialize(self.seed,out,self.auth)
        self.assertEqual(r.read(self.seed/'protocol.json'),self.old)
    def test_mutated_accounting_and_failed_attempt_are_rejected(self):
        expected,_=c.expected(self.seed,self.auth,[])
        for key,value in [('prior_rounds',0),('max_rounds',2),('inherited_tokens',0),('source_protocol',{})]:
            mutated=copy.deepcopy(expected);mutated[key]=value
            with self.assertRaises(ValueError):c.validate(mutated,self.export['initial'])
        changed=copy.deepcopy(expected);changed['correction_provider_recovery']['failed_receipt']['session_id']='other'
        with self.assertRaises(ValueError):c.validate(changed,self.export['initial'])
    def test_missing_or_changed_authority_rejected(self):
        for changes in ({'enabled':False},{'source_protocol_sha256':'wrong'},{'authorized_by':''},{'token_policy':'reset'}):
            with self.assertRaises(ValueError):c.expected(self.seed,{**self.auth,**changes},[])
        preserved,_=c.expected(self.seed,{**self.auth,'token_policy':'preserve'},[])
        self.assertEqual(preserved['max_tokens'],600000)
    def test_exact_original_prompt_only_for_first_attempt(self):
        job=self.seed/'rounds/0/propose';job.mkdir(parents=True);(job/'prompt.txt').write_text(self.export['prompt'])
        p0,_=c.expected(self.seed,self.auth,[])
        self.assertEqual(c.proposer_prompt(p0,0),self.export['prompt']);self.assertIsNone(c.proposer_prompt(p0,1))
        self.assertIsNone(c.proposer_prompt({},0))

class OriginalReplayTests(unittest.TestCase):
    def test_legacy_original_subprocess_replays_exact_prompt_without_current_signature(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);code=root/'code';research=code/'research';research.mkdir(parents=True)
            (research/'__init__.py').write_text('')
            helper=research/'earnings_corrections.py'
            helper.write_text("import json\nclass base:\n @staticmethod\n def read(p): return json.loads(p.read_text())\ndef load(p): return base.read(p/'protocol.json'),None,None,None\ndef prompt(role,state,b,k,w): return 'original complete source prompt'\n")
            seed=root/'seed';job=seed/'rounds/0/propose';job.mkdir(parents=True)
            initial={'facts':'unchanged'};r.save(seed/'initial.json',initial)
            old={'version':'deterministic-corrections-v1','max_rounds':1,'prior_rounds':1,'inherited_tokens':20,
                 'model':['gpt-6.1-sol','medium'],'code':[{'path':str(helper),'sha256':r.sha(helper)}]}
            r.save(seed/'protocol.json',old);r.save(job/'request.json',{'model':'gpt-6.1-sol','effort':'medium','bindings':{'protocol_sha256':r.sha(seed/'protocol.json'),'snapshot_sha256':r.digest(initial),'round':0,'role':'propose'}})
            (job/'prompt.txt').write_text('original complete source prompt')
            with patch.object(p,'inspect_failure',return_value={'reason':'server_error'}) as inspect:
                _,_,exported,_=c.original(seed)
                self.assertEqual(exported['initial'],initial);inspect.assert_called_once_with(job.resolve(),code,error_code='server_error')
                request=r.read(job/'request.json');(job/'request.json').write_text(json.dumps({**request,'effort':'high'}))
                with self.assertRaisesRegex(ValueError,'model or effort'):c.original(seed)
                (job/'request.json').write_text(json.dumps(request))
                (job/'prompt.txt').write_text('changed prompt')
                with self.assertRaisesRegex(ValueError,'does not reproduce'):c.original(seed)
                (job/'prompt.txt').write_text('original complete source prompt');helper.write_text('# altered frozen verifier')
                with self.assertRaisesRegex(ValueError,'Original code changed'):c.original(seed)
