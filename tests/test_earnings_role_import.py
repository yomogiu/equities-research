"""Synthetic complete journals; recovery must never call a provider or forge exit status."""
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.test_earnings_mixed_runner import RunnerTests
from research import earnings_role_import as imp, earnings_mixed_runner as r

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.fixture=RunnerTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.complete();self.job=self.fixture.job;self.code=Path(r.__file__).parent.parent
    def missing_wrapper(self):
        (self.job/'execution.json').unlink();(self.job/'output.json').unlink()
    def test_completed_response_without_wrapper_is_imported_without_model_or_exit_claim(self):
        self.missing_wrapper();ref=imp.reference(self.job,self.code);dest=self.job.with_name('import')
        with patch.object(r,'run_role',side_effect=AssertionError('No provider call')):
            v=imp.create(dest,self.fixture.prompt,'gpt-6.1-sol','medium',{'new':'binding'},900,ref)
            self.assertEqual(r.verify_job(dest),v)
        self.assertEqual(v['receipt']['status'],'imported_completed_response')
        self.assertIsNone(v['receipt']['exit_code']);self.assertEqual(v['receipt']['new_model_calls'],0)
        self.assertEqual(v['receipt']['session']['usage']['totalTokens'],110)
        self.assertFalse((self.job/'execution.json').exists())
    def test_existing_complete_receipt_is_replayed(self):
        ref=imp.reference(self.job,self.code)
        self.assertEqual(imp.authenticate(ref)['original_elapsed_seconds'],1.5)
    def test_changed_prompt_or_model_cannot_import(self):
        ref=imp.reference(self.job,self.code)
        for prompt,model,effort in [('Changed','gpt-6.1-sol','medium'),(self.fixture.prompt,'gpt-6-luna','max')]:
            with self.assertRaises(ValueError):imp.create(self.job.with_name('new'),prompt,model,effort,{},900,ref)
    def test_missing_or_failed_runtime_or_incomplete_session_rejected(self):
        self.missing_wrapper();(self.job/'runtime-failure.json').write_text('{"stage":"output_validation"}')
        with self.assertRaises(ValueError):imp.reference(self.job,self.code)
        (self.job/'runtime-failure.json').unlink()
        self.fixture.entries[-1]['message']['stopReason']='error';self.fixture.write_journal()
        with self.assertRaises(ValueError):imp.reference(self.job,self.code)
    def test_source_and_import_tampering_rejected(self):
        ref=imp.reference(self.job,self.code);dest=self.job.with_name('import')
        imp.create(dest,self.fixture.prompt,'gpt-6.1-sol','medium',{},900,ref)
        (self.job/'stdout.txt').write_text('{"changed":true}')
        with self.assertRaises(ValueError):r.verify_job(dest)
    def test_import_execution_cannot_claim_observed_exit(self):
        ref=imp.reference(self.job,self.code);dest=self.job.with_name('import')
        imp.create(dest,self.fixture.prompt,'gpt-6.1-sol','medium',{},900,ref)
        v=r.read(dest/'execution.json');v['exit_code']=0;(dest/'execution.json').write_text(__import__('json').dumps(v))
        with self.assertRaises(ValueError):r.verify_job(dest)

class CourtesyTests(unittest.TestCase):
    def fixture(self):
        bundle={'transcript_index':{'turns':[{'id':'q','speaker':'A','role':'analyst'},{'id':'a','speaker':'B','role':'management'}],
                'exchanges':[{'id':'e','question_turn_ids':['q'],'answer_turn_ids':['a'],'unknown_turn_ids':[]}]}}
        rows=[]
        for tid,parts in [('q',['A\n','Analyst, Fake\n','Thank you.']),('a',['B\n','President and CEO, Fake\n','Thank you.'])]:
            for i,text in enumerate(parts):rows.append({'scope_id':tid,'text':text,'start':i*20,'passage_id':tid+str(i)})
        return bundle,{'passages':rows}
    def test_only_missing_courtesy_is_added_and_original_is_unchanged(self):
        b,c=self.fixture();original={'exchange_coverage':[],'quotes':[{'passage_id':'existing'}]}
        out,added=imp.complete_courtesy(original,b,c)
        self.assertEqual(len(added),1);self.assertEqual(original['exchange_coverage'],[])
        self.assertEqual(out['quotes'],original['quotes']);self.assertEqual(added[0]['question_passage_ids'],['q2'])
        self.assertEqual(imp.complete_courtesy(out,b,c)[1],[])
    def test_real_question_or_unknown_role_remains_unfilled(self):
        b,c=self.fixture();c['passages'][2]['text']='Thank you. What is revenue?'
        self.assertEqual(imp.complete_courtesy({'exchange_coverage':[]},b,c)[1],[])
        b,c=self.fixture();b['transcript_index']['turns'][0]['role']='unknown'
        self.assertEqual(imp.complete_courtesy({'exchange_coverage':[]},b,c)[1],[])
