"""Synthetic completed-journal reconciliation; no model invocation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_experiment as base
from research import earnings_reconcile as rec
from test_earnings_recovery import fixture,CONTENT
from test_earnings_experiment import write


def completed(root):
    run,job,case=fixture(root)
    launch=base.read(job/'launch.json');launch['started_at']=1000;write(job/'launch.json',launch)
    session=next((job/'sessions').glob('*.jsonl'))
    ev=[json.loads(x) for x in session.read_text().splitlines()]
    ev[-1]['timestamp']='1970-01-01T00:28:20+00:00'
    ev[-1]['message']={'role':'assistant','stopReason':'stop','timestamp':1700000,
                       'provider':'openai-codex','model':'synthetic','content':json.dumps(CONTENT)}
    session.write_text(''.join(json.dumps(x)+'\n' for x in ev))
    listing=write(job/'runtime-list.json',{'sessions':[]})
    inactive=write(job/'runtime-inactive.json',{'command':['prime-agent','list','--json'],
                   'exit_code':0,'observed_at':2000,'stdout_sha256':base.sha(listing)})
    return run,job,case,inactive


class ReconciliationTests(unittest.TestCase):
    def test_reconcile_without_inventing_cli_success(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,inactive=completed(Path(temp))
            prior=(job/'execution.json').read_bytes()
            rec.reconcile(run,job.name,inactive)
            self.assertEqual((job/'execution.json').read_bytes(),prior)
            self.assertEqual((job/'stdout.txt').read_bytes(),b'')
            self.assertEqual(rec.verify_job(job,'extractor',case,{}),'fictitious-extractor')
            receipt=base.read(job/'reconciliation.json')
            self.assertEqual(receipt['status'],'journal_reconciled')
            self.assertIsNone(receipt['original_cli_exit_code'])
            self.assertEqual(receipt['new_model_calls'],0)
            with self.assertRaisesRegex(ValueError,'not completed'):base.verify_job(job,'extractor',case,{})
            with self.assertRaisesRegex(ValueError,'Existing reconciliation'):rec.reconcile(run,job.name,inactive)

    def test_late_final_event_is_explicit_and_response_start_is_not_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,inactive=completed(Path(temp))
            session=next((job/'sessions').glob('*.jsonl'))
            ev=[json.loads(x) for x in session.read_text().splitlines()]
            ev[-1]['timestamp']='1970-01-01T00:31:42+00:00'
            session.write_text(''.join(json.dumps(x)+'\n' for x in ev))
            rec.reconcile(run,job.name,inactive)
            evidence=base.read(job/'reconciliation.json')['evidence']
            self.assertEqual(evidence['completed_at'],1902)
            self.assertTrue(evidence['late_completion_after_timeout'])
            self.assertEqual(evidence['completion_delay_after_timeout_seconds'],2)
            self.assertEqual(evidence['completion_timestamp_source'],'outer_final_message_event')

    def test_invalid_completion_and_activity_rejected(self):
        for error in ('aborted','after_observation','extra_user','provider','active','early_observation','prompt','dependencies'):
            with self.subTest(error=error),tempfile.TemporaryDirectory() as temp:
                run,job,case,inactive=completed(Path(temp));session=next((job/'sessions').glob('*.jsonl'))
                ev=[json.loads(x) for x in session.read_text().splitlines()]
                if error=='aborted':ev[-1]['message']['stopReason']='aborted'
                elif error=='after_observation':ev[-1]['timestamp']='1970-01-01T00:35:00+00:00'
                elif error=='extra_user':ev.insert(-1,{'type':'message','message':{'role':'user','content':'extra task'}})
                elif error=='provider':ev[-1]['message']['provider']='other-provider'
                elif error=='active':
                    write(job/'runtime-list.json',{'sessions':[{'id':'active'}]})
                    d=base.read(inactive);d['stdout_sha256']=base.sha(job/'runtime-list.json');write(inactive,d)
                elif error=='early_observation':d=base.read(inactive);d['observed_at']=1800;write(inactive,d)
                elif error=='prompt':(job/'prompt.txt').write_text('changed')
                elif error=='dependencies':
                    d=base.read(job/'request.json');d['dependencies']={'prior_review':'fake'};write(job/'request.json',d)
                session.write_text(''.join(json.dumps(x)+'\n' for x in ev))
                with self.assertRaises(ValueError):rec.reconcile(run,job.name,inactive)
                self.assertFalse((job/'output.json').exists())

    def test_verified_record_mutations_rejected(self):
        for error in ('session','output','receipt','failed_execution','runtime_observation','exact_terminal'):
            with self.subTest(error=error),tempfile.TemporaryDirectory() as temp:
                run,job,case,inactive=completed(Path(temp));rec.reconcile(run,job.name,inactive)
                if error=='session':
                    p=next((job/'sessions').glob('*.jsonl'));p.write_text(p.read_text()+'\n')
                elif error=='output':d=base.read(job/'output.json');d['content']['gaps']=['invented'];write(job/'output.json',d)
                elif error=='receipt':d=base.read(job/'reconciliation.json');d['original_cli_exit_code']=0;write(job/'reconciliation.json',d)
                elif error=='failed_execution':write(job/'execution.json',{'status':'returned','exit_code':0})
                elif error=='runtime_observation':d=base.read(inactive);d['observed_at']=2001;write(inactive,d)
                elif error=='exact_terminal':(job/'journal-final.txt').write_text(json.dumps(CONTENT,indent=2))
                with self.assertRaises(ValueError):rec.verify_job(job,'extractor',case,{})

    def test_wrapper_preserves_other_validators(self):
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as temp:
            run,job,case,inactive=completed(Path(temp));rec.reconcile(run,job.name,inactive)
            with patch.object(rec.recovery,'adapter',return_value=nullcontext()),patch.object(base,'verify_job',return_value='base-check') as original:
                with rec.adapter(run):
                    self.assertEqual(base.verify_job(job,'extractor',case,{}),'fictitious-extractor')
                    self.assertEqual(base.verify_job(run/'reviewer-r0','reviewer',case,{}),'base-check')
                original.assert_called_once()


if __name__=='__main__':unittest.main()
