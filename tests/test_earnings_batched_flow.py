"""Synthetic production dispatch; model transport is mocked, no live calls."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_earnings_signals as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_batched_flow as flow
from research import earnings_batch_review as batch
from research import earnings_report_flow as dispatch

class FlowTests(PassageFixture,unittest.TestCase):
    state=fixtures.SignalTests.state
    pack=fixtures.SignalTests.pack

    def test_new_production_path_combines_review_and_replays_acceptance(self):
        self.exercise(False)

    def test_one_combined_correction_preserves_report_acceptance(self):
        self.exercise(True)

    def test_mechanical_policy_compiles_before_signal_author_and_retains_acceptance(self):
        self.exercise(True,mechanical=True)

    def exercise(self,correction,mechanical=False):
        root=self.root/'production';writing=self.root/'writing.txt';writing.write_text('Fictional writing')
        flow.pipe.freeze(self.casepath,root,writing,deterministic_corrections=True,batch_review=True,qa_grounding=False,mechanical_preflight=mechanical)
        outputs={'financial':self.financial,'retrieval':self.retrieval,'analysis':self.report,'signal_author':self.pack(self.state())}
        if mechanical:
            from research import earnings_mechanical_preflight as preflight
            state=self.state();state['format']=preflight.formatting(self.financial,self.bundle)
            outputs['signal_author']=self.pack(state)
        calls=[]
        def run(job,text,model,effort,bindings,timeout):
            job=Path(job);job.mkdir(parents=True);calls.append(str(job))
            if 'role' in bindings:out=outputs[bindings['role']]
            elif job.name.startswith('correction-'):
                prior=batch.replay(root/'batch-review');items=prior['items'];value=dict(items['signal-1']['value']);value['label']='Fictional corrected label'
                out={'before_sha256':batch.runner.digest(items),'changes':[{'unit_id':'signal-1','before_sha256':batch.runner.digest(items['signal-1']['value']),'value':value,'reason':'Fix fictional label'}]}
            else:
                data=json.loads(text.split('\nBATCH\n')[1])
                out={'batch_sha256':data['batch_sha256'],'decisions':[
                    {'unit_id':k,'verdict':'revise' if correction and data['round']==0 and k=='signal-1' else 'pass','reason':'Fictional original-source check','passage_ids':[] if mechanical and not (correction and data['round']==0 and k=='signal-1') else self.ids[:1]} for k in data['pending']],'reopen':[]}
            (job/'prompt.txt').write_text(text)
            batch.runner.save(job/'request.json',{'model':model,'effort':effort,'bindings':bindings})
            batch.runner.save(job/'output.json',out)
        def verify(job):
            return {'content':batch.runner.read(job/'output.json'),'receipt':{'session':{'id':str(job),'usage':{'totalTokens':17}}}}
        with patch.object(batch.runner,'run_role',side_effect=run),patch.object(batch.runner,'verify_job',side_effect=verify):
            for _ in range(12):
                before=len(calls);result=dispatch.advance(root)
                self.assertLessEqual(len(calls)-before,1)
                if result['status']=='accepted':break
            self.assertEqual(result['status'],'accepted')
            self.assertEqual(len(calls),7 if correction else 5)
            self.assertEqual(result['detail']['tokens'],119 if correction else 85)
            if correction:
                accepted=batch.replay(root/'batch-review')['accepted']
                self.assertEqual(accepted['analysis:0']['review_receipt_sha256'],batch.runner.sha(root/'batch-review/batches/0/review/output.json'))
            self.assertEqual(dispatch.advance(root,False)['report_sha256'],result['report_sha256'])
            self.assertEqual(len(calls),7 if correction else 5)
            self.assertFalse((root/'jobs/review-r0').exists())
            expected={'financial':('gpt-6-luna','max'),'retrieval':('gpt-6-luna','max'),
                      'analysis':('gpt-6-luna','max'),'signal_author':('gpt-6.1-sol','low')}
            for role,assignment in expected.items():
                request=batch.runner.read(root/'batch-jobs'/role/'request.json')
                self.assertEqual((request['model'],request['effort']),assignment)
            review=batch.runner.read(root/'batch-review/batches/0/review/request.json')
            self.assertEqual((review['model'],review['effort']),('gpt-6.1-sol','medium'))
            self.assertEqual(batch.runner.read(root/'protocol.json')['signal_author_model'],['gpt-6.1-sol','low'])
            if mechanical:
                self.assertEqual(batch.runner.read(root/'mechanical-preflight.json')['status'],'ready_for_independent_review')
                self.assertTrue(batch.runner.read(root/'batch-review/initial.json')['format']['value']['rows'])

    def test_legacy_protocol_does_not_route_to_batch_dispatcher(self):
        root=self.root/'legacy';writing=self.root/'writing.txt';writing.write_text('Fictional writing')
        flow.pipe.freeze(self.casepath,root,writing,deterministic_corrections=True,qa_grounding=False)
        with patch.object(flow,'advance') as advance:
            self.assertEqual(dispatch.advance(root,False)['status'],'pending');advance.assert_not_called()
