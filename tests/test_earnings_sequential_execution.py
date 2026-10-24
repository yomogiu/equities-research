"""Fictional isolated worker bootstrap and bounded failed-attempt reconciliation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_earnings_compact_evidence import fixture
from research import earnings_sequential_stages as stages
from research import earnings_sequential as controller
from research import earnings_file_context as context
from research import earnings_financial_analysis_report as finance
from research import earnings_mixed_runner as storage


class SequentialExecutionTests(unittest.TestCase):
    def test_exact_prompt_bootstraps_evidence_in_isolated_worker_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); case, _, _ = fixture(root)
            guide=root/'guide.md'; guide.write_text('Fictional concise writing.')
            jobroot=root/'job'
            controller.create(jobroot, {'case_path':str(case),'writing_standard':str(guide),
                'financial_analysis':finance.configuration('2040-01-01','2040-03-31')})
            controller.advance(jobroot, stages.handlers())
            job=controller.advance(jobroot, stages.handlers())
            self.assertEqual(job['stage'],'analysis')
            self.assertEqual(job['status'],'ready')
            self.assertIn('financial-analysis.json',job['artifacts'])
            index=stages._role_context(jobroot,job,'analysis')
            role=jobroot/'roles/analysis-r0'; role.mkdir(parents=True)
            context.write(role/'request.json',{'version':'file-prime-role-v1','job_path':str(role),'context_index':str(index)})
            prompt=stages._prompt('analysis',1)
            code=prompt.split('using the signed-in IPython tool:\n',1)[1].split('\nRepeat with',1)[0]
            result=subprocess.run([sys.executable,'-I','-c',code],cwd=role,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('original evidence',result.stdout)
            self.assertTrue((role/'retrieval.jsonl').exists())

    def test_retry_directories_use_attempt_ordinal_without_changing_revision(self):
        job={'revision_round':0,'attempts':[{'stage':'analysis','revision_round':0}]}
        self.assertEqual(stages._role_label(job,'analysis'),'analysis-r0')
        job['attempts'].append({'stage':'analysis','revision_round':0})
        self.assertEqual(stages._role_label(job,'analysis'),'analysis-r0-attempt2')
        self.assertEqual(stages._role_label(job,'review'),'review-r0')

    def failed_fixture(self, root):
        role=root/'roles/analysis-r0'; role.mkdir(parents=True)
        prompt='Fictional bound instruction'; (role/'prompt.md').write_text(prompt)
        request={'job_path':str(role),'bindings':{'workflow':stages.VERSION,'role':'sequential_analysis'},
                 'model':'fictional-model','provider':'openai-codex','effort':'medium','max_tokens':1000}
        launch={'id':'fictional-launch','request_sha256':storage.digest(request)}
        context.write(role/'request.json',request); context.write(role/'launch.json',launch)
        records={'execution.json':{'exit_code':1,'status':'execution_failed','request_sha256':storage.digest(request),'launch_sha256':storage.sha(role/'launch.json')},
                 'runtime-failure.json':{'stage':'local_guard','code':'role_budget'},
                 'budget-stop.json':{'stable_metered_prefix':True,'used_tokens':12,'completed_turns':1,'tool_calls':0,'job_cap':1000},
                 'runtime-start.json':{'session_id':'fictional-session','launch_id':launch['id'],'oauth':True,'provider':request['provider'],'model':request['model'],'effort':'medium'},'wire.json':[]}
        for name,value in records.items(): context.write(role/name,value)
        for name in ('delivery.jsonl','retrieval.jsonl'): (role/name).write_text('')
        usage={'input':8,'output':4,'cacheRead':0,'cacheWrite':0,'totalTokens':12}
        events=[{'type':'session','id':'fictional-session','cwd':str(role)},
                {'type':'message','message':{'role':'user','content':[{'type':'text','text':prompt}]}},
                {'type':'message','message':{'role':'assistant','model':request['model'],'provider':request['provider'],'api':'openai-codex-responses','usage':usage,'stopReason':'stop','content':[]}}]
        session=role/'sessions/fake.jsonl'; session.parent.mkdir();session.write_text('\n'.join(json.dumps(x) for x in events)+'\n')
        job={'revision_round':0,'attempts':[{'stage':'analysis','revision_round':0,'outcome':{'tokens':12,'execution_directory':str(role)}}]}
        return role,job

    def test_only_exact_stable_closed_prefix_is_certified_and_hashed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();role,job=self.failed_fixture(root)
            with patch.object(stages.runner,'verify_request'),patch.object(stages.runner,'verify_wire'),patch.object(stages.runner,'verify_delivery'):
                proof=stages.failed_execution(root,job)
                self.assertEqual(proof['execution_certainty'],'closed')
                self.assertEqual(proof['tokens'],12)
                self.assertEqual(len(proof['outputs']),11)
                self.assertTrue(all(storage.sha(root/name)==digest for name,digest in proof['outputs'].items()))
                value=stages.read(role/'budget-stop.json');value['used_tokens']=11
                (role/'budget-stop.json').write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError,'accounting differs'): stages.failed_execution(root,job)

    def test_unknown_timeout_failure_is_not_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();role,job=self.failed_fixture(root)
            value=stages.read(role/'execution.json');value['exit_code']=-15
            (role/'execution.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'not proven closed'): stages.failed_execution(root,job)

    def test_unstable_metering_is_not_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();role,job=self.failed_fixture(root)
            value=stages.read(role/'budget-stop.json');value['stable_metered_prefix']=False
            (role/'budget-stop.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'Unknown provider usage'): stages.failed_execution(root,job)


if __name__ == '__main__': unittest.main()
