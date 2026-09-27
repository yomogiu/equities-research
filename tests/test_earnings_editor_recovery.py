"""Fictitious editor retry fixtures; no model calls."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_experiment as base
from research import earnings_editor_recovery as recovery
from test_earnings_experiment import make_case,write

CONTENT={'report_markdown':'Fictitious report with source-bound claims. '*30}


def fixture(root):
    case_path,case=make_case(root);run=root/'run';job=run/'editor-r1';job.mkdir(parents=True)
    write(run/'case.json',case)
    deps={name:str(write(run/(name+'-fixture.json'),{'fictional':name})) for name in ('extractor','commentator','substantive_review','prior_review')}
    prompt=base.role_prompt('editor',case_path,case,deps,1);(job/'prompt.txt').write_text(prompt)
    request={'version':base.VERSION,'role':'editor','revision':1,'case_sha256':base.digest(case),
             'dependencies':{k:base.sha(v) for k,v in deps.items()},'prompt_sha256':base.sha(job/'prompt.txt')}
    write(job/'request.json',request);write(job/'dependencies.json',deps)
    write(job/'launch.json',{'status':'launched','request_sha256':base.digest(request)})
    write(job/'execution.json',{'status':'returned','exit_code':1,'session':None,'elapsed_seconds':657})
    (job/'stdout.txt').write_text('');(job/'stderr.txt').write_text('fetch failed\n')
    ev=[{'type':'session','id':'fictitious-editor'},{'type':'model_change','provider':'openai-codex','modelId':'fictitious-model'},
        {'type':'message','message':{'role':'user','content':prompt}},
        {'type':'message','message':{'role':'assistant','content':[],'stopReason':'error','errorMessage':'fetch failed'}}]
    session=job/'sessions'/'fixture.jsonl';session.parent.mkdir();session.write_text(''.join(json.dumps(e)+'\n' for e in ev))
    return run,job,case,deps


def simulate(command,**kwargs):
    job=Path(kwargs['cwd']);session=recovery.session_path(job)
    with session.open('a') as out:
        for m in ({'role':'user','content':kwargs['input']},{'role':'assistant','content':json.dumps(CONTENT),'stopReason':'stop'}):
            out.write(json.dumps({'type':'message','message':m})+'\n')
    kwargs['stdout'].write(json.dumps(CONTENT));kwargs['stdout'].flush()
    return subprocess.CompletedProcess(command,0)


class EditorRecoveryTests(unittest.TestCase):
    def test_exact_session_resume_preserves_failed_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,deps=fixture(Path(temp));failed=(job/'execution.json').read_bytes()
            with patch.object(recovery.subprocess,'run',side_effect=simulate):recovery.recover(run)
            self.assertEqual(recovery.verify_recovered_job(job,'editor',case,deps),'fictitious-editor')
            self.assertEqual(recovery.verify_recovered_job(job,'editor',case,{k:Path(v) for k,v in deps.items()}),'fictitious-editor')
            self.assertEqual((job/'execution.json').read_bytes(),failed)
            self.assertEqual((job/'stdout.txt').read_text(),'')
            self.assertTrue((run/'editor-recovery-policy.json').exists())
            with self.assertRaisesRegex(ValueError,'not completed'):base.verify_job(job,'editor',case,deps)
            with self.assertRaisesRegex(ValueError,'already launched'):recovery.recover(run)

    def test_provider_failure_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,deps=fixture(Path(temp));(job/'stderr.txt').write_text('different failure')
            with self.assertRaisesRegex(ValueError,'provider fetch failure'):recovery.prepare(run)

    def test_timeout_retains_uncertainty_no_second_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,deps=fixture(Path(temp))
            with patch.object(recovery.subprocess,'run',side_effect=subprocess.TimeoutExpired('fake',600)):
                with self.assertRaisesRegex(ValueError,'timed out'):recovery.recover(run)
            self.assertFalse((job/'output.json').exists())
            with self.assertRaisesRegex(ValueError,'already launched'):recovery.recover(run)

    def test_mutation_rejection(self):
        for change in ('dependency','deps_receipt','original_failure','stdout','output','session','continuation','policy'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                run,job,case,deps=fixture(Path(temp))
                with patch.object(recovery.subprocess,'run',side_effect=simulate):recovery.recover(run)
                if change=='dependency':write(Path(deps['extractor']),{'changed':True})
                elif change=='deps_receipt':write(job/'dependencies.json',{})
                elif change=='original_failure':write(job/'execution.json',{'status':'returned','exit_code':0})
                elif change=='stdout':(job/'recovery'/'stdout.txt').write_text('{}')
                elif change=='output':write(job/'output.json',{'request_sha256':'wrong','content':CONTENT})
                elif change=='session':p=recovery.session_path(job);p.write_text(p.read_text().replace('fictitious-editor','other-editor'))
                elif change=='continuation':(job/'recovery'/'continuation.txt').write_text('different task')
                elif change=='policy':p=base.read(run/'editor-recovery-policy.json');p['reconciliation_sha256']='changed';write(run/'editor-recovery-policy.json',p)
                with self.assertRaises(ValueError):recovery.verify_recovered_job(job,'editor',case,deps)

    def test_composed_adapter_retains_other_validators(self):
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,deps=fixture(Path(temp))
            with patch.object(recovery.subprocess,'run',side_effect=simulate):recovery.recover(run)
            with patch.object(recovery.reconciliation,'adapter',return_value=nullcontext()),patch.object(base,'verify_job',return_value='prior-validator') as prior:
                with recovery.adapter(run):
                    self.assertEqual(base.verify_job(job,'editor',case,deps),'fictitious-editor')
                    self.assertEqual(base.verify_job(run/'extractor-r0','extractor',case,{}),'prior-validator')
                prior.assert_called_once()


if __name__=='__main__':unittest.main()
