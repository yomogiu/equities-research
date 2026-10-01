"""Fictitious same-session resumes; no providers, credentials, or real source text."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_experiment as base
from research import earnings_native as native
from research import earnings_native_revision_recovery as revision
from research import earnings_native_timeout_recovery as recovery
from test_earnings_experiment import write
from test_earnings_native import stream,rollout
import test_earnings_native_revision_recovery as fixtures
from test_earnings_native_revision_recovery import runtime


def jsonl(path,events):path.write_text(''.join(json.dumps(e)+'\n' for e in events))


def usage(inputs,outputs):
    return {'input_tokens':inputs,'cached_input_tokens':inputs//2,'output_tokens':outputs,'total_tokens':inputs+outputs}


def tokens(value):return {'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':value}}}


def setup(root):
    run,path,case,valid,bad0,bad1=fixtures.RevisionRecoveryTests().failed_revision(root);revision.prepare(run)
    with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)):
        native.run_role(run,'reviewer',1,path,case,{'extractor':run/'extractor-r0'/'output.json','commentator':run/'commentator-r1'/'output.json'})
    sid='fictional-resumed-r2';job=run/'commentator-r2';deps={'prior_review':str(run/'reviewer-r1'/'output.json')}
    def fail(argv,*,input,text,stdout,stderr,cwd,timeout):
        # An incomplete original turn: native saves its true timeout branch.
        stdout.write(json.dumps({'type':'thread.started','thread_id':sid})+'\n'+json.dumps({'type':'turn.started'})+'\n')
        rollout(job,sid,input,'unused')
        ev=recovery.entries(job/'session.jsonl')[:-1];ev.append(tokens(usage(1000,100)))
        jsonl(job/'session.jsonl',ev)
        raise subprocess.TimeoutExpired(argv,timeout)
    with patch.object(native.subprocess,'run',side_effect=fail),patch.object(native.time,'monotonic',side_effect=[1,1+native.TIMEOUT+0.1]):
        with unittest.TestCase().assertRaisesRegex(ValueError,'uncertain'):
            native.run_role(run,'commentator',2,path,case,deps)
    rec=job/'recovery';rec.mkdir();(rec/'prompt.txt').write_text('Finish the original fictitious JSON in this same session.')
    argv=native.command(base.read(run/'config.json')['codex'],job)[:-1]
    argv[argv.index('-o')+1]=str(rec/'final.txt');argv+=['resume','--json','-o',str(rec/'final.txt'),sid,'-']
    req={'session_id':sid,'model':native.MODEL,'reasoning_effort':native.EFFORT,'argv':argv,'timeout_seconds':native.TIMEOUT,
         'prompt_sha256':base.sha(rec/'prompt.txt'),'original_request_sha256':base.sha(job/'request.json'),
         'original_session_sha256':base.sha(job/'session.jsonl'),
         'original_files':{n:base.sha(job/n) for n in recovery.ORIGINALS}}
    write(rec/'request.json',req);start=base.read(job/'launch.json')['started_at']+native.TIMEOUT+10
    write(rec/'launch.json',{'started_at':start,'request_sha256':base.digest(req),'argv_sha256':base.digest(argv)})
    write(rec/'inactive-before-resume.json',{'checked_at':start-1,'matching_original_role_pids':[],'session_id':sid})
    final=json.dumps(valid);(rec/'final.txt').write_text(final+'\n');(rec/'stderr.txt').write_text('')
    jsonl(rec/'events.jsonl',stream(sid,final,usage={'input_tokens':1500,'cached_input_tokens':750,'output_tokens':200}))
    before=recovery.entries(job/'session.jsonl');context=next(e for e in before if e['type']=='turn_context')
    after=before+[context,{'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':(rec/'prompt.txt').read_text()}]}},
                  tokens(usage(1500,200)),{'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':final}]}}]
    jsonl(rec/'session.jsonl',after)
    write(rec/'execution.json',{'status':'returned','exit_code':0,'elapsed_seconds':110,'completed_at':start+110,
                               'request_sha256':base.digest(req),'files':{n:base.sha(rec/n) for n in ('events.jsonl','stderr.txt','final.txt')}})
    write(rec/'cap-policy.json',{'effective_timeout_seconds':600,'original_requested_timeout_seconds':900,'reason':'Fictitious parity cap',
                                'recorded_at':start+1,'deadline':start+600,'request_sha256':base.digest(req)})
    write(rec/'cap-observation.json',{'checked_at':start+111,'effective_timeout_seconds':600,'execution_receipt_present':True,
                                     'terminated_exact_resume_pids':[],'cap_policy_sha256':base.sha(rec/'cap-policy.json')})
    return run,path,case,valid,bad0,bad1


class TimeoutRecoveryTests(unittest.TestCase):
    def setUp(self):
        # This historical recovery adapter binds a 900-second request and a
        # 600-second watchdog cap. Test that explicit legacy variant rather
        # than inheriting the new experiment's 1,800-second role timeout.
        timeout=patch.object(native,'TIMEOUT',900);timeout.start();self.addCleanup(timeout.stop)
        capture=patch.object(native,'capture_rollout');capture.start();self.addCleanup(capture.stop)

    def test_resume_acceptance_retains_failure_and_counts_cumulative_once(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,bad0,bad1=setup(Path(temp));job=run/recovery.JOB
            failure_hash=base.sha(job/'execution.json')
            with patch.object(native.subprocess,'run') as launch:recovery.prepare(run);launch.assert_not_called()
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)) as launch:
                recovery.execute(run);self.assertEqual(launch.call_count,3);self.assertEqual(recovery.verify(run)['revisions'],2)
            self.assertEqual(base.sha(job/'execution.json'),failure_hash)
            self.assertEqual(base.read(job/'execution.json')['status'],'launch_uncertain')
            receipt=base.read(job/'session-receipt.json')
            self.assertEqual(receipt['usage'],{'input_tokens':1500,'cached_input_tokens':750,'output_tokens':200});self.assertEqual(receipt['resume_increment']['input_tokens'],500)
            self.assertEqual(receipt['path'],'recovery/session.jsonl')
            accepted=base.read(run/'accepted.json');self.assertEqual(accepted['timeout_recovery_sha256'],base.sha(run/recovery.RECEIPT))
            self.assertIn('schema_recovery_sha256',accepted);self.assertIn('revision_schema_recovery_sha256',accepted)
            with self.assertRaisesRegex(ValueError,'not completed'):revision.verify(run)

    def test_original_prefix_identity_prompt_and_settings_cannot_change(self):
        for mutation in ('prefix','identity','continuation','model'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                run,*_=setup(Path(temp));job=run/recovery.JOB;rec=job/'recovery';events=recovery.entries(rec/'session.jsonl')
                if mutation=='prefix':events[0]['payload']['id']='different'
                elif mutation=='identity':events.append({'type':'session_meta','payload':{'id':'different','cli_version':'fixture','model_provider':'openai'}})
                elif mutation=='continuation':events[-3]['payload']['content'][0]['text']='different'
                else:events[-4]['payload']['model']='different'
                jsonl(rec/'session.jsonl',events)
                with self.assertRaises(ValueError):recovery.prepare(run)

    def test_invalid_final_exit_and_cap_are_rejected(self):
        for mutation in ('content','exit','cap','failed_original','duplicate_continuation'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                run,path,case,valid,bad0,bad1=setup(Path(temp));job=run/recovery.JOB;rec=job/'recovery'
                if mutation=='content':
                    invalid=json.dumps(bad1);(rec/'final.txt').write_text(invalid+'\n')
                    ev=recovery.entries(rec/'events.jsonl');ev[-2]['item']['text']=invalid;jsonl(rec/'events.jsonl',ev)
                    ev=recovery.entries(rec/'session.jsonl');ev[-1]['payload']['content'][0]['text']=invalid;jsonl(rec/'session.jsonl',ev)
                    ex=base.read(rec/'execution.json');ex['files']={n:base.sha(rec/n) for n in ('events.jsonl','stderr.txt','final.txt')};write(rec/'execution.json',ex)
                elif mutation=='exit':write(rec/'execution.json',{**base.read(rec/'execution.json'),'exit_code':1})
                elif mutation=='cap':write(rec/'cap-policy.json',{**base.read(rec/'cap-policy.json'),'effective_timeout_seconds':900})
                elif mutation=='failed_original':write(job/'execution.json',{**base.read(job/'execution.json'),'status':'returned','exit_code':0})
                else:
                    ev=recovery.entries(rec/'session.jsonl');ev.append(ev[-3]);jsonl(rec/'session.jsonl',ev)
                with self.assertRaises(ValueError):recovery.prepare(run)

    def test_immutable_receipts_and_no_resume_launch_api(self):
        with tempfile.TemporaryDirectory() as temp:
            run,*_=setup(Path(temp));recovery.prepare(run)
            with patch.object(native.subprocess,'run') as launch:
                recovery.prepare(run);recovery.policy(run);launch.assert_not_called()
            job=run/recovery.JOB;write(job/'session-receipt.json',{})
            with self.assertRaisesRegex(ValueError,'common session'):recovery.policy(run)


if __name__=='__main__':unittest.main()
