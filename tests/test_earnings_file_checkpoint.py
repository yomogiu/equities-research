"""Checkpoints preserve source progress without trusting old approvals or sessions."""
import copy
import json
import unittest
from pathlib import Path
from test_earnings_passages import PassageFixture
import test_earnings_file_pipeline as fixture
from research import earnings_file_context as c, earnings_file_checkpoint as cp, earnings_file_runner as r
from research import earnings_mixed_runner as base


def put(path,value):path.write_text(json.dumps(value)+'\n')

class CheckpointTests(PassageFixture,unittest.TestCase):
    fake_run=fixture.FilePipelineTests.fake_run
    pack=fixture.FilePipelineTests.pack
    drain=fixture.FilePipelineTests.drain
    assemble=fixture.FilePipelineTests.assemble

    def failed(self):
        index=self.assemble();job=(self.root/'jobs/financial').resolve()
        self.fake_run(job,'Fictional role','gpt-6.1-sol','low',{'role':'financial','candidate':'same'},index,max_tokens=200000,max_tool_calls=48)
        saved=self.stop_at_checkpoint(job,index)
        return job,index,saved

    def stop_at_checkpoint(self,job,index):
        ctx=c.Evidence(index,job/'retrieval.jsonl');saved=ctx.checkpoint({'fact_ids':['F002'],'partial':'unreviewed'},['Check comparable period'])
        path=job/'sessions/fake.jsonl';events=[json.loads(x) for x in path.read_text().splitlines()]
        last=events[-1]['message'];last.update(stopReason='error',errorMessage='checkpoint_yield',content=[],usage={k:0 for k in r.USAGE})
        path.write_text(''.join(json.dumps(x)+'\n' for x in events))
        wire=base.read(job/'wire.json');put(job/'wire.json',wire[:1])
        execution=base.read(job/'execution.json');execution.update(status='execution_failed',exit_code=1);put(job/'execution.json',execution)
        (job/'output.json').unlink();put(job/'runtime-failure.json',{'code':'checkpoint_yield'})
        return saved

    def test_fresh_sibling_restores_partial_data_and_counts_failed_usage(self):
        job,index,saved=self.failed();next_job,spent,resume=cp.select(job)
        self.assertEqual(spent,20);self.assertEqual(next_job.name,'financial--resume-1');self.assertEqual(resume['sha256'],saved['sha256'])
        next_job.mkdir();prompt='Resume identical role'
        q=r.request(next_job,prompt,'gpt-6.1-sol','low',{'role':'financial','candidate':'same'},index,200000-spent,48,1200,resume=resume)
        put(next_job/'request.json',q);put(next_job/'resume.json',resume);(next_job/'prompt.md').write_text(prompt)
        restored=c.Evidence(index,next_job/'retrieval.jsonl').restore()
        self.assertEqual(restored['draft'],{'fact_ids':['F002'],'partial':'unreviewed'})
        self.assertEqual(restored['pending'],['Check comparable period'])
        self.assertEqual(len(c.audit(index,job/'retrieval.jsonl')),restored['inspected_retrieval_events'])
        q['bindings']['candidate']='different';put(next_job/'request.json',q)
        with self.assertRaises(ValueError):cp.restore(next_job)

    def test_host_capture_saves_progress_without_model_checkpoint_and_preserves_draft(self):
        index=self.assemble();job=(self.root/'jobs/financial').resolve()
        self.fake_run(job,'Fictional role','gpt-6.1-sol','low',{'role':'financial'},index,max_tokens=200000,max_tool_calls=48)
        for path in (job/'checkpoints').glob('*.json'):path.unlink()
        captured=cp.capture(job);value=cp.validate(captured['checkpoint'])
        self.assertEqual(value['draft']['kind'],'source_progress_only')
        self.assertNotIn('approval',value['draft'])
        ctx=c.Evidence(index,job/'retrieval.jsonl');manual=ctx.checkpoint({'finding':'Fictional unreviewed draft'},['Check cash'])
        captured=cp.capture(job);self.assertEqual(captured['checkpoint'],manual['checkpoint'])
        self.assertEqual(cp.validate(captured['checkpoint'])['draft'],{'finding':'Fictional unreviewed draft'})

    def test_altered_checkpoint_or_read_log_cannot_resume(self):
        job,index,saved=self.failed();path=Path(saved['checkpoint']);v=base.read(path);v['retrieval_count']+=1;put(path,v)
        with self.assertRaises(ValueError):cp.select(job)

    def test_unknown_failure_and_unclosed_tool_result_are_not_retried(self):
        job,index,saved=self.failed();put(job/'runtime-failure.json',{'code':'network_error'})
        with self.assertRaises(ValueError):cp.select(job)
        put(job/'runtime-failure.json',{'code':'checkpoint_yield'})
        path=job/'sessions/fake.jsonl';events=[json.loads(x) for x in path.read_text().splitlines()]
        events=[e for e in events if e.get('message',{}).get('role')!='toolResult'];path.write_text(''.join(json.dumps(x)+'\n' for x in events))
        with self.assertRaises(ValueError):cp.select(job)

    def test_host_checkpoint_recovers_without_model_saved_draft(self):
        job,index,saved=self.failed();Path(saved['checkpoint']).unlink()
        selected,spent,resume=cp.select(job)
        self.assertNotEqual(selected,job);self.assertEqual(spent,20);self.assertIsNotNone(resume)
        self.assertEqual(cp.validate(resume['checkpoint'])['draft']['kind'],'source_progress_only')

    def test_missing_host_checkpoint_receipt_fails_closed(self):
        job,index,saved=self.failed()
        for path in (job/'checkpoints').glob('*.json'):path.unlink()
        with self.assertRaises((ValueError,FileNotFoundError)):cp.select(job)

    def test_oversized_read_gets_no_coverage_until_every_page_delivered(self):
        index=self.assemble();job=self.root/'spill';job.mkdir();ctx=c.Evidence(index,job/'retrieval.jsonl');ctx.scope('D001')
        (job/'tool-output').mkdir();identifier='b'*24;text='😀'*1000;path=job/'tool-output'/(identifier+'.txt');path.write_text(text)
        first={'id':identifier,'sha256':base.sha(path),'original_bytes':len(text.encode()),'unsupported':False,'complete':False,'retrieval_start':0,'retrieval_end':1,'limit':8192,'delivered_bytes':200}
        (job/'delivery.jsonl').write_text(json.dumps(first)+'\n')
        self.assertEqual(c.delivered_entries(job,c.audit(index,job/'retrieval.jsonl')),[])
        ctx.output(identifier,0,768)
        def add_delivery(name,start,end):
            p=job/'tool-output'/(name+'.txt');p.write_text('bounded page')
            record={**first,'id':name,'sha256':base.sha(p),'original_bytes':p.stat().st_size,'complete':True,'retrieval_start':start,'retrieval_end':end}
            with (job/'delivery.jsonl').open('a') as handle:handle.write(json.dumps(record)+'\n')
        add_delivery('c'*24,1,2)
        self.assertNotIn('D001',c.complete_ranges(c.delivered_entries(job,c.audit(index,job/'retrieval.jsonl')),'scope','id'))
        ctx.output(identifier,768,768);add_delivery('d'*24,2,3)
        entries=c.delivered_entries(job,c.audit(index,job/'retrieval.jsonl'))
        self.assertIn('D001',c.complete_ranges(entries,'scope','id'))
        with self.assertRaises(ValueError):ctx.output('../../escape')

    def test_pipeline_advances_fresh_resume_then_later_roles_without_relaunch(self):
        from unittest.mock import patch
        from research import earnings_file_pipeline as pipeline
        root=(self.root/'pipeline').resolve();writing=self.root/'writing.md';writing.write_text('Fictional source-grounded writing.')
        pipeline.initialize(self.casepath,root,writing,financial_mode='model-original-selector-v1')
        calls=[]
        def run(job,*args,**kwargs):
            calls.append(job.name);result=self.fake_run(job,*args,**kwargs)
            if job.name=='financial':
                self.stop_at_checkpoint(job,args[4]);raise RuntimeError('Known controlled stop')
            return result
        with patch.object(r,'run_role',side_effect=run):
            for _ in range(10):
                value=pipeline.advance(root,True)
                if value.get('status') in ('accepted','blocked','launch_uncertain','budget_exhausted'):break
            self.assertEqual(value['status'],'accepted',value)
            self.assertEqual(value['tokens'],220)
            self.assertEqual(calls,['financial','financial--resume-1','retrieval','analysis','signal_author','review-0'])
            self.assertEqual(pipeline.verify(root)['tokens'],220)
