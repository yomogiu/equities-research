"""Synthetic quarantine and shared-budget recovery tests; no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from research import earnings_native as native
from research import earnings_native_recovery as recovery
from research import earnings_experiment as base
from test_earnings_experiment import make_case,write,review
from test_earnings_native import stream,rollout
from test_transcript_evidence import fixture,TEXT


def setup(root):
    case_path,case=make_case(root); case_path=case_path.resolve()
    index,findings=fixture(); Path(case['transcript_path']).write_text(TEXT)
    write(Path(case['transcript_index_path']),index)
    for item in case['sources']+case['artifacts']:item['sha256']=base.sha(item['path'])
    write(case_path,case); prime=root/'prime';write(prime/'case.json',case)
    codex=root/'fake-codex';codex.write_text('Fictitious binary')
    run=(root/'native').resolve()
    with patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='codex fixture')):
        native.prepare(case_path,prime,run,codex)
    valid={'findings':findings,'exchange_coverage':[{'exchange_id':e['id'],'disposition':'Fictitious coverage.'} for e in index['exchanges']]}
    invalid=deepcopy(valid); invalid['findings'][0]['exchange_ids']=[e['id'] for e in index['exchanges']]
    return run,case_path,case,valid,invalid


def runtime(valid,invalid,review_verdict='revise',corrected_invalid=False):
    def process(argv,*,input,text,stdout,stderr,cwd,timeout):
        job=Path(cwd); role,revision=job.name.rsplit('-r',1); revision=int(revision)
        if role=='commentator':content=invalid if revision==0 or corrected_invalid else valid
        elif role=='extractor':content={'selected_fact_ids':['fictional-fact'],'financial_checks':[{'claim':'Fictional context'}],'gaps':[]}
        elif role=='reviewer':content=review(base.SUBSTANTIVE,review_verdict if revision==0 else 'pass','commentator')
        elif role=='editor':content={'report_markdown':'Fictitious report. '*50}
        else:
            content=review(base.EDITORIAL);content['report_sha256']=base.sha(job.parent/f'report-r{revision}.md')
        body=json.dumps(content);(job/'final.txt').write_text(body+'\n')
        rollout(job,'synthetic-'+job.name,input,body)
        stdout.write(''.join(json.dumps(e)+'\n' for e in stream('synthetic-'+job.name,body)))
        return subprocess.CompletedProcess(argv,0)
    return process


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        capture=patch.object(native,'capture_rollout');capture.start();self.addCleanup(capture.stop)

    def failed_initial(self,run,case_path,case,valid,invalid):
        with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid)):
            with self.assertRaisesRegex(ValueError,recovery.ERROR):
                native.run_role(run,'commentator',0,case_path,case,{})
        self.assertFalse((run/'commentator-r0'/'output.json').exists())

    def test_quarantine_normal_review_correction_and_verified_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,invalid=setup(Path(temp)); self.failed_initial(run,path,case,valid,invalid)
            before=base.sha(run/'commentator-r0'/'final.txt')
            with patch.object(native.subprocess,'run') as launch:recovery.prepare(run);launch.assert_not_called()
            self.assertEqual(base.sha(run/'commentator-r0'/'final.txt'),before)
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid)) as launch:
                recovery.execute(run)
                self.assertEqual(launch.call_count,6)
                self.assertEqual(recovery.verify(run)['revisions'],1)
            acceptance=base.read(run/'accepted.json')
            self.assertEqual(acceptance['roles']['commentator'],'commentator-r1')
            self.assertEqual(acceptance['schema_recovery_sha256'],base.sha(run/recovery.RECEIPT))
            self.assertEqual(base.read(run/'commentator-r1'/'dependencies.json'),{'prior_review':str(run/'reviewer-r0'/'output.json')})
            with self.assertRaisesRegex(ValueError,recovery.ERROR):native.verify(run)

    def test_initial_reviewer_must_target_commentator_revision(self):
        for verdict in ('pass','blocked'):
            with self.subTest(verdict=verdict),tempfile.TemporaryDirectory() as temp:
                run,path,case,valid,invalid=setup(Path(temp));self.failed_initial(run,path,case,valid,invalid);recovery.prepare(run)
                with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid,verdict)):
                    with self.assertRaisesRegex(ValueError,'requires reviewer-r0 revise'):recovery.execute(run)
                self.assertTrue((run/'schema-recovery-blocked.json').exists())
                self.assertFalse((run/'editor-r0').exists());self.assertFalse((run/'accepted.json').exists())

    def test_corrected_draft_never_gets_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,invalid=setup(Path(temp));self.failed_initial(run,path,case,valid,invalid);recovery.prepare(run)
            with recovery.adapter(run):
                with self.assertRaisesRegex(ValueError,recovery.ERROR):native.validate_content('commentator',invalid,case,{})
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid,corrected_invalid=True)):
                with self.assertRaisesRegex(ValueError,recovery.ERROR):recovery.execute(run)
            self.assertFalse((run/'commentator-r1'/'output.json').exists());self.assertFalse((run/'accepted.json').exists())

    def test_scope_and_immutable_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,invalid=setup(Path(temp));self.failed_initial(run,path,case,valid,invalid)
            damaged=deepcopy(invalid);damaged['findings'][0]['quotes'][0]['text']='fabricated'
            with self.assertRaises(ValueError):recovery.diagnose(damaged,case)
            damaged=deepcopy(invalid);damaged['exchange_coverage']=[]
            with self.assertRaises(ValueError):recovery.diagnose(damaged,case)
            recovery.prepare(run)
            write(run/'commentator-r0'/'output.json',{'request_sha256':'changed','content':invalid})
            with self.assertRaisesRegex(ValueError,'differs'):recovery.policy(run)

    def test_existing_exact_wrapper_and_reviewer_are_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            run,path,case,valid,invalid=setup(Path(temp));self.failed_initial(run,path,case,valid,invalid)
            job=run/'commentator-r0';base.save(job/'output.json',{'request_sha256':base.digest(base.read(job/'request.json')),'content':invalid})
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid)):
                extractor=native.run_role(run,'extractor',0,path,case,{})
                native.run_role(run,'reviewer',0,path,case,{'extractor':extractor,'commentator':job/'output.json'})
            recovery.prepare(run)
            with patch.object(native.subprocess,'run',side_effect=runtime(valid,invalid)) as launch:
                recovery.execute(run);self.assertEqual(launch.call_count,4)
                recovery.verify(run)


if __name__=='__main__':unittest.main()
