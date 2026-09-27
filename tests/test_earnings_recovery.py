"""Fictitious recovery fixtures; never execute a model."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_experiment as base
from research import earnings_recovery as recovery
from test_earnings_experiment import make_case, write


def fixture(root):
    case_path, case = make_case(root)
    run = root/'run'; job=run/'extractor-r0'; job.mkdir(parents=True)
    write(run/'case.json',case)
    prompt=base.role_prompt('extractor',case_path,case,{},0)
    (job/'prompt.txt').write_text(prompt)
    request={'version':base.VERSION,'role':'extractor','revision':0,'case_sha256':base.digest(case),
             'dependencies':{},'prompt_sha256':base.sha(job/'prompt.txt')}
    write(job/'request.json',request);write(job/'dependencies.json',{})
    write(job/'launch.json',{'status':'launched','request_sha256':base.digest(request)})
    write(job/'execution.json',{'status':'launch_uncertain','elapsed_seconds':900})
    (job/'stdout.txt').write_text('');(job/'stderr.txt').write_text('')
    events=[{'type':'session','id':'fictitious-extractor'},
            {'type':'model_change','provider':'openai-codex','modelId':'fictitious-model'},
            {'type':'message','message':{'role':'user','content':prompt}},
            {'type':'message','message':{'role':'assistant','stopReason':'aborted','content':''}}]
    session=job/'sessions'/'fake.jsonl';session.parent.mkdir()
    session.write_text(''.join(json.dumps(e)+'\n' for e in events))
    return run,job,case


CONTENT={'selected_fact_ids':['fictional-fact'],'financial_checks':[{'claim':'fictitious context check'}],'gaps':[]}

def simulate_success(command,**kwargs):
    job=Path(kwargs['cwd']);session=recovery.session_path(job)
    with session.open('a') as out:
        for m in ({'role':'user','content':kwargs['input']},
                  {'role':'assistant','stopReason':'stop','content':json.dumps(CONTENT)}):
            out.write(json.dumps({'type':'message','message':m})+'\n')
    kwargs['stdout'].write(json.dumps(CONTENT));kwargs['stdout'].flush()
    return subprocess.CompletedProcess(command,0)


class RecoveryTests(unittest.TestCase):
    def test_success_preserves_failure_and_base_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case=fixture(Path(temp));before=(job/'execution.json').read_bytes()
            with patch.object(recovery.subprocess,'run',side_effect=simulate_success) as process:
                recovery.recover(run)
            self.assertIn('--resume',process.call_args.args[0])
            self.assertEqual((job/'execution.json').read_bytes(),before)
            self.assertEqual((job/'stdout.txt').read_bytes(),b'')
            self.assertEqual(recovery.verify_recovered_job(job,'extractor',case,{}),'fictitious-extractor')
            with self.assertRaisesRegex(ValueError,'not completed'): base.verify_job(job,'extractor',case,{})
            with recovery.adapter(run): self.assertEqual(base.verify_job(job,'extractor',case,{}),'fictitious-extractor')
            with self.assertRaisesRegex(ValueError,'not completed'): base.verify_job(job,'extractor',case,{})
            with self.assertRaisesRegex(ValueError,'already launched'): recovery.recover(run)

    def test_timeout_retained_without_second_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case=fixture(Path(temp))
            with patch.object(recovery.subprocess,'run',side_effect=subprocess.TimeoutExpired('fake',600)):
                with self.assertRaisesRegex(ValueError,'timed out'):recovery.recover(run)
            self.assertEqual(base.read(job/'recovery'/'execution.json')['status'],'launch_uncertain')
            self.assertFalse((job/'output.json').exists())
            with self.assertRaisesRegex(ValueError,'already launched'):recovery.recover(run)

    def test_mutations_fail_closed(self):
        for change in ('failed_receipt','original_prefix','continuation','stdout','output','session_id','extra_user','provider','case','policy_code'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                run,job,case=fixture(Path(temp))
                with patch.object(recovery.subprocess,'run',side_effect=simulate_success):recovery.recover(run)
                session=recovery.session_path(job)
                if change=='failed_receipt':write(job/'execution.json',{'status':'returned','exit_code':0})
                elif change=='original_prefix':session.write_text(session.read_text().replace('fictitious-model','changed-model'))
                elif change=='continuation':(job/'recovery'/'continuation.txt').write_text('Other request')
                elif change=='stdout':(job/'recovery'/'stdout.txt').write_text('{}')
                elif change=='output':write(job/'output.json',{'request_sha256':'wrong','content':CONTENT})
                elif change=='session_id':session.write_text(session.read_text().replace('fictitious-extractor','other-session'))
                elif change=='extra_user':
                    with session.open('a') as out:out.write(json.dumps({'type':'message','message':{'role':'user','content':'extra'}})+'\n')
                elif change=='provider':
                    with session.open('a') as out:out.write(json.dumps({'type':'model_change','provider':'other-provider','modelId':'bad'})+'\n')
                elif change=='case':case['authorization']='changed';write(run/'case.json',case)
                elif change=='policy_code':p=base.read(run/'recovery-policy.json');p['adapter_sha256']='wrong';write(run/'recovery-policy.json',p)
                with self.assertRaises(ValueError):recovery.verify_recovered_job(job,'extractor',case,{})

    def test_scope_and_original_completed_session_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case=fixture(Path(temp))
            session=recovery.session_path(job);session.write_text(session.read_text().replace('aborted','stop'))
            with self.assertRaisesRegex(ValueError,'observed abort'):recovery.prepare(run)

    def test_no_resume_after_session_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case=fixture(Path(temp));recovery.prepare(run)
            session=recovery.session_path(job);session.write_text(session.read_text()+'\n')
            with patch.object(recovery.subprocess,'run') as process:
                with self.assertRaisesRegex(ValueError,'changed before resume'):recovery.recover(run)
            process.assert_not_called()

    def test_adapter_preserves_other_role_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case=fixture(Path(temp));recovery.prepare(run)
            with patch.object(base,'verify_job',return_value='other-real-validator') as original:
                with recovery.adapter(run):
                    self.assertEqual(base.verify_job(run/'reviewer-r0','reviewer',case,{}),'other-real-validator')
                original.assert_called_once()


if __name__=='__main__':unittest.main()
