"""Fictitious native runtime events only; no provider calls or issuer data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_native as native
from research import earnings_experiment as base
from test_earnings_experiment import make_case, review, write


def setup(root):
    case_path, case=make_case(root)
    prime=root/'prime'; write(prime/'case.json',case)
    codex=root/'fake-codex'; codex.write_text('Fictitious non-executable binary fixture')
    run=root/'native'
    with patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='codex fixture')):
        native.prepare(case_path,prime,run,codex)
    return run,case_path.resolve(),case


def stream(thread,text,usage=None):
    return [{'type':'thread.started','thread_id':thread}, {'type':'turn.started'},
            {'type':'item.completed','item':{'id':'item_1','type':'agent_message','text':text}},
            {'type':'turn.completed','usage':usage or {'input_tokens':100,'cached_input_tokens':20,'output_tokens':30}}]


def fake_process(argv,*,input,text,stdout,stderr,cwd,timeout):
    job=Path(cwd); role=job.name.rsplit('-r',1)[0]; revision=int(job.name.rsplit('-r',1)[1])
    if role=='reviewer': content=review(base.SUBSTANTIVE)
    elif role=='final_reviewer':
        content=review(base.EDITORIAL); content['report_sha256']=base.sha(job.parent/f'report-r{revision}.md')
    elif role=='editor': content={'report_markdown':'Fictitious sourced report. '*45}
    elif role=='extractor': content={'selected_fact_ids':['fictional-fact'],'financial_checks':[{'claim':'Synthetic check'}],'gaps':[]}
    else: content={'synthetic':'commentator'}
    value=json.dumps(content)
    (job/'final.txt').write_text(value+'\n')
    rollout(job,'fictional-'+job.name,input,value)
    stdout.write(''.join(json.dumps(e)+'\n' for e in stream('fictional-'+job.name,value)))
    return subprocess.CompletedProcess(argv,0)


def rollout(job,sid,prompt,final):
    events=[{'type':'session_meta','payload':{'id':sid,'cli_version':'fixture','model_provider':'openai'}},
            {'type':'turn_context','payload':{'model':native.MODEL,'effort':native.EFFORT,'sandbox_policy':{'type':'read-only'},'approval_policy':'never'}},
            {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':prompt}]}},
            {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':final}]}}]
    (job/'session.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.capture=patch.object(native,'capture_rollout')
        self.capture.start(); self.addCleanup(self.capture.stop)

    def test_prompt_command_and_complete_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            run,case_path,case=setup(Path(temp))
            with patch.object(native.subprocess,'run',side_effect=fake_process) as launch, patch.object(native,'validate_content'):
                native.execute(run)
                self.assertEqual(native.verify(run)['status'],'verified_local')
                self.assertEqual(launch.call_count,5)
                native.execute(run)
                self.assertEqual(launch.call_count,5)
            receipt=base.read(run/'accepted.json')
            self.assertEqual(receipt['runtime'],'native-codex')
            for role in receipt['roles']:
                job=run/receipt['roles'][role]
                deps=base.read(job/'dependencies.json')
                self.assertEqual((job/'prompt.txt').read_text(),base.role_prompt(role,case_path,case,deps,0))
                args=base.read(job/'request.json')['argv']
                self.assertIn('--ignore-user-config',args)
                self.assertIn('read-only',args)
                self.assertIn('model_reasoning_effort="max"',args)
                self.assertNotIn(str(Path(temp)/'prime'),(job/'prompt.txt').read_text())

    def test_mutated_runtime_and_provenance_rejected(self):
        mutations={
            'prompt':lambda j:(j/'prompt.txt').write_text('changed'),
            'events':lambda j:(j/'events.jsonl').write_text((j/'events.jsonl').read_text()+'{}\n'),
            'final':lambda j:(j/'final.txt').write_text('{}'),
            'stderr':lambda j:(j/'stderr.txt').write_text('changed'),
            'execution':lambda j:write(j/'execution.json',{**base.read(j/'execution.json'),'exit_code':1}),
            'request':lambda j:write(j/'request.json',{**base.read(j/'request.json'),'argv':[]}),
            'launch':lambda j:write(j/'launch.json',{'status':'launched'}),
            'session':lambda j:(j/'session.jsonl').write_text('{}\n'),
            'receipt':lambda j:write(j/'session-receipt.json',{}),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp:
                run,case_path,case=setup(Path(temp))
                with patch.object(native.subprocess,'run',side_effect=fake_process):
                    result=native.run_role(run,'extractor',0,case_path,case,{})
                mutate(result.parent)
                with self.assertRaises(ValueError):native.verify_job(result.parent,'extractor',case,{})

    def test_event_identity_usage_final_and_completion_required(self):
        for mutation in ('identity','usage','final','failed','duplicate','incomplete'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                job=Path(temp); value='{"fictional":true}'; events=stream('fictional-thread',value)
                if mutation=='identity': events[0]['thread_id']=''
                elif mutation=='usage': events[-1]['usage']['input_tokens']=-1
                elif mutation=='final': events[-2]['item']['text']='different'
                elif mutation=='failed': events.insert(2,{'type':'turn.failed'})
                elif mutation=='duplicate': events.insert(1,events[0])
                elif mutation=='incomplete':events.pop()
                (job/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
                (job/'final.txt').write_text(value)
                with self.assertRaises(ValueError):native.session_receipt(job)

    def test_failed_process_retained_and_duplicate_launch_blocked(self):
        for timed_out in (False,True):
            with self.subTest(timed_out=timed_out), tempfile.TemporaryDirectory() as temp:
                run,case_path,case=setup(Path(temp))
                effect=subprocess.TimeoutExpired('fictional',900) if timed_out else None
                with patch.object(native.subprocess,'run',side_effect=effect,return_value=subprocess.CompletedProcess([],7)):
                    with self.assertRaises(ValueError):native.run_role(run,'extractor',0,case_path,case,{})
                execution=base.read(run/'extractor-r0'/'execution.json')
                self.assertEqual(execution['status'],'launch_uncertain' if timed_out else 'returned')
                if not timed_out:self.assertEqual(execution['exit_code'],7)
                with patch.object(native.subprocess,'run') as launch:
                    with self.assertRaisesRegex(ValueError,'reconciled'):native.run_role(run,'extractor',0,case_path,case,{})
                    launch.assert_not_called()

    def test_frozen_code_binary_case_and_prime_binding(self):
        for kind in ('code','binary','case','prime','settings'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);run,case_path,case=setup(root)
                if kind=='code':
                    with patch.object(native,'code_hashes',return_value={}):
                        with self.assertRaisesRegex(ValueError,'code changed'):native.verify_config(run)
                    continue
                if kind=='binary':(root/'fake-codex').write_text('changed')
                elif kind=='case':case_path.write_text('{}')
                elif kind=='prime':(root/'prime'/'case.json').write_text('{}')
                else:write(run/'config.json',{**base.read(run/'config.json'),'reasoning_effort':'low'})
                with self.assertRaises(ValueError):native.verify_config(run)

    def test_shared_revision_budget_and_prior_review_only(self):
        with tempfile.TemporaryDirectory() as temp:
            run,case_path,case=setup(Path(temp)); calls=[]
            def role(run,role,revision,case_path,case,deps):
                calls.append((role,revision,deps))
                if role=='reviewer':content=review(base.SUBSTANTIVE,'revise' if revision==0 else 'pass','commentator')
                elif role=='final_reviewer':content=review(base.EDITORIAL,'revise','editor')
                elif role=='editor':content={'report_markdown':'Fictitious body. '*50}
                else:content={'synthetic':role}
                return write(run/f'{role}-r{revision}'/'output.json',{'content':content})
            with patch.object(native,'run_role',side_effect=role):native.execute(run)
            self.assertEqual(base.read(run/'blocked.json')['revisions'],2)
            self.assertFalse((run/'accepted.json').exists())
            for name,revision,deps in calls:
                if name in ('extractor','commentator'):
                    self.assertEqual(set(deps),{'prior_review'} if revision else set())
            self.assertNotIn(('extractor',1),[(r,v) for r,v,_ in calls])
            self.assertIn(('editor',2),[(r,v) for r,v,_ in calls])

    def test_observed_settings_and_original_prompt_are_attested(self):
        for field in ('model','effort','sandbox_policy','prompt','phase'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as temp:
                job=Path(temp); (job/'prompt.txt').write_text('Fictitious role prompt')
                rollout(job,'fictional-thread','Fictitious role prompt','{}')
                events=[json.loads(line) for line in (job/'session.jsonl').read_text().splitlines()]
                if field=='prompt':events[2]['payload']['content'][0]['text']='different'
                elif field=='phase':events[-1]['payload']['phase']='commentary'
                else:events[1]['payload'][field]={'type':'danger-full-access'} if field=='sandbox_policy' else 'different'
                (job/'session.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
                with self.assertRaises(ValueError):native.rollout_receipt(job,'fictional-thread','{}')

    def test_accepted_history_verifies_both_correction_rounds(self):
        with tempfile.TemporaryDirectory() as temp:
            run,_,_=setup(Path(temp)); original_review=review; counts={base.SUBSTANTIVE:0,base.EDITORIAL:0}
            def revision_review(criteria,*args):
                counts[criteria]+=1
                return original_review(criteria,'revise' if counts[criteria]==1 else 'pass',
                                       'commentator' if criteria==base.SUBSTANTIVE else 'editor')
            with patch.object(native.subprocess,'run',side_effect=fake_process), patch.object(native,'validate_content'), patch(__name__+'.review',side_effect=revision_review):
                native.execute(run)
                self.assertEqual(native.verify(run)['revisions'],2)
                self.assertEqual(len(list(run.glob('*/session-receipt.json'))),9)
                deps=base.read(run/'commentator-r1'/'dependencies.json')
                self.assertEqual(set(deps),{'prior_review'})
                (run/'reviewer-r0'/'stderr.txt').write_text('Historical receipt mutation')
                with self.assertRaisesRegex(ValueError,'capture changed'):native.verify(run)

    def test_prime_acceptance_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as temp:
            run,_,_=setup(Path(temp))
            with self.assertRaisesRegex(ValueError,'Unsupported acceptance'):
                native.verify_acceptance(run,{'version':base.VERSION,'runtime':'native-codex','status':'accepted_local'})


if __name__=='__main__':unittest.main()
