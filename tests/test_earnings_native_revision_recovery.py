"""Fictitious revision-one quarantine tests; no model or provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_experiment as base
from research import earnings_native as native
from research import earnings_native_recovery as initial
from research import earnings_native_revision_recovery as recovery
from test_earnings_experiment import make_case,write,review
from test_earnings_native import stream,rollout
from test_transcript_evidence import fixture,TEXT


def setup(root):
    path,case=make_case(root);path=path.resolve();index,findings=fixture()
    # Synthetic fourth exchange reuses a known source span solely for binding tests.
    extra=deepcopy(index['exchanges'][-1]);extra['id']='fictional-fourth-exchange';index['exchanges'].append(extra)
    Path(case['transcript_path']).write_text(TEXT);write(Path(case['transcript_index_path']),index)
    for item in case['sources']+case['artifacts']:item['sha256']=base.sha(item['path'])
    write(path,case);prime=root/'prime';write(prime/'case.json',case);codex=root/'fake-codex';codex.write_text('Fictitious binary')
    run=(root/'native').resolve()
    with patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='codex fixture')):native.prepare(path,prime,run,codex)
    findings=[deepcopy(findings[0]) for _ in range(3)]
    for number,finding in enumerate(findings):finding['id']='fictional-finding-'+str(number+1)
    third=findings[2];third['exchange_ids']=[e['id'] for e in index['exchanges']];third['quotes']=[]
    turns={t['id']:t for t in index['turns']}
    for exchange in index['exchanges']:
        turn=turns[exchange['turn_ids'][0]];start,end=turn['start'],turn['end']
        third['quotes'].append({'exchange_id':exchange['id'],'start':start,'end':end,'text':TEXT[start:end]})
    valid={'findings':findings,'exchange_coverage':[{'exchange_id':e['id'],'disposition':'Fictitious coverage'} for e in index['exchanges']]}
    bad0=deepcopy(valid);bad0['findings'][0]['exchange_ids']=[e['id'] for e in index['exchanges'][:3]]
    bad1=deepcopy(valid);bad1['findings'][2]['quotes'].pop()
    return run,path,case,valid,bad0,bad1


def runtime(valid,bad0,bad1,review1='revise',bad2=False,final_verdict='pass',review1target='commentator'):
    def process(argv,*,input,text,stdout,stderr,cwd,timeout):
        job=Path(cwd);role,revision=job.name.rsplit('-r',1);revision=int(revision)
        if role=='commentator':content=bad0 if revision==0 else bad1 if revision==1 or bad2 else valid
        elif role=='extractor':content={'selected_fact_ids':['fictional-fact'],'financial_checks':[{'claim':'Fictional source context'}],'gaps':[]}
        elif role=='reviewer':content=review(base.SUBSTANTIVE,'revise' if revision==0 else review1 if revision==1 else 'pass',review1target if revision==1 else 'commentator')
        elif role=='editor':content={'report_markdown':'Fictitious report. '*50}
        else:
            content=review(base.EDITORIAL,final_verdict,'editor');content['report_sha256']=base.sha(job.parent/f'report-r{revision}.md')
        body=json.dumps(content);(job/'final.txt').write_text(body+'\n');rollout(job,'fictional-'+job.name,input,body)
        stdout.write(''.join(json.dumps(e)+'\n' for e in stream('fictional-'+job.name,body)))
        return subprocess.CompletedProcess(argv,0)
    return process


def envelope(run,bad1,case):
    job=run/'commentator-r1';scope=recovery.diagnose(bad1,case)
    write(job/'output.json',{'request_sha256':base.digest(base.read(job/'request.json')),'content':bad1,
          'validation':{'status':'failed','error':recovery.ERROR,'missing_quote_bindings':scope['missing_quote_bindings'],
                        'required_change':'Bind the listed exchange to an exact source quote or narrow the supported references.'}})


class RevisionRecoveryTests(unittest.TestCase):
    def setUp(self):
        capture=patch.object(native,'capture_rollout');capture.start();self.addCleanup(capture.stop)

    def failed_revision(self,root):
        run,path,case,valid,bad0,bad1=setup(root)
        with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)):
            with self.assertRaisesRegex(ValueError,initial.ERROR):native.execute(run)
            initial.prepare(run)
            with self.assertRaisesRegex(ValueError,initial.ERROR):initial.execute(run)
        self.assertFalse((run/'commentator-r1'/'output.json').exists())
        envelope(run,bad1,case)
        return run,path,case,valid,bad0,bad1

    def test_exact_history_corrected_r2_and_budget_two(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,bad0,bad1=self.failed_revision(Path(temp))
            original=base.sha(run/'commentator-r1'/'final.txt')
            with patch.object(native.subprocess,'run') as launch:recovery.prepare(run);launch.assert_not_called()
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)) as launch:
                recovery.execute(run);self.assertEqual(launch.call_count,5)
                self.assertEqual(recovery.verify(run)['revisions'],2)
            acceptance=base.read(run/'accepted.json')
            self.assertEqual(acceptance['roles']['commentator'],'commentator-r2')
            self.assertEqual(acceptance['schema_recovery_sha256'],base.sha(run/initial.RECEIPT))
            self.assertEqual(acceptance['revision_schema_recovery_sha256'],base.sha(run/recovery.RECEIPT))
            self.assertEqual(base.sha(run/'commentator-r1'/'final.txt'),original)
            self.assertFalse(list(run.glob('*-r3')))
            with self.assertRaisesRegex(ValueError,initial.ERROR):initial.verify(run)

    def test_pass_or_wrong_target_revision_review_blocks(self):
        for verdict,target in (('pass','commentator'),('blocked','commentator'),('revise','extractor')):
            with self.subTest(verdict=verdict,target=target),tempfile.TemporaryDirectory() as temp:
                run,path,case,valid,bad0,bad1=self.failed_revision(Path(temp));recovery.prepare(run)
                with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1,review1=verdict,review1target=target)):
                    with self.assertRaisesRegex(ValueError,'requires reviewer-r1 revise'):recovery.execute(run)
                self.assertTrue((run/'revision-schema-recovery-blocked.json').exists())
                self.assertFalse((run/'commentator-r2').exists());self.assertFalse((run/'accepted.json').exists())

    def test_invalid_r2_is_rejected_and_no_third_round(self):
        for bad2 in (True,False):
            with self.subTest(bad2=bad2),tempfile.TemporaryDirectory() as temp:
                run,path,case,valid,bad0,bad1=self.failed_revision(Path(temp));recovery.prepare(run)
                with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1,bad2=bad2,final_verdict='revise')):
                    if bad2:
                        with self.assertRaisesRegex(ValueError,initial.ERROR):recovery.execute(run)
                    else:
                        recovery.execute(run);self.assertEqual(base.read(run/'blocked.json')['revisions'],2)
                self.assertFalse((run/'accepted.json').exists());self.assertFalse(list(run.glob('*-r3')))

    def test_initial_receipt_and_exact_metadata_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,bad0,bad1=self.failed_revision(Path(temp));recovery.prepare(run)
            with recovery.adapter(run):
                with self.assertRaisesRegex(ValueError,initial.ERROR):native.validate_content('commentator',bad1,case,recovery.dependencies(run))
            job=run/'commentator-r1';output=base.read(job/'output.json');output['validation']['required_change']='Changed instruction'
            write(job/'output.json',output)
            with self.assertRaisesRegex(ValueError,'Frozen revision'):recovery.policy(run)
            (run/initial.RECEIPT).unlink()
            with self.assertRaises(FileNotFoundError):recovery.policy(run)

    def test_original_reviewer1_is_reused_and_scope_is_narrow(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,bad0,bad1=self.failed_revision(Path(temp))
            damaged=deepcopy(bad1);damaged['exchange_coverage']=[]
            with self.assertRaises(ValueError):recovery.diagnose(damaged,case)
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)):
                native.run_role(run,'reviewer',1,path,case,{'extractor':run/'extractor-r0'/'output.json','commentator':run/'commentator-r1'/'output.json'})
            recovery.prepare(run)
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,bad0,bad1)) as launch:
                recovery.execute(run);self.assertEqual(launch.call_count,4);recovery.verify(run)


if __name__=='__main__':unittest.main()
