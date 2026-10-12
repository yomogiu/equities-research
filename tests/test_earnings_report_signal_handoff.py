import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_report_signal_handoff as h


class HandoffTests(unittest.TestCase):
    def test_mutated_full_candidate_html_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'candidate.html').write_text('exact rendered report')
            with patch.object(h.s,'_render_content',side_effect=lambda path,*a,**kw:path.write_text('exact rendered report')):
                h.check_render(root,{}, {},{}, {})
                (root/'candidate.html').write_text('mutated report')
                with self.assertRaisesRegex(ValueError,'Rendered full candidate changed'):h.check_render(root,{}, {},{}, {})

    def state(self):return {'artifacts':{'analysis':{'findings':[{'heading':'cash','text':'old'}]}},'format':{}}

    def test_exact_label_and_binding_repair(self):
        before=self.state();after=copy.deepcopy(before);after['artifacts']['analysis']['findings'][0]['text']='new'
        fid=next(iter(h.s.finding_catalog(before)))
        pack={'report_sha256':h.s.report_digest(before),'signals':[{'id':f'signal-{i}','finding_id':fid,'label':'unchanged'} for i in range(1,4)]+[
            {'id':'signal-4','finding_id':fid,'label':h.OLD_LABEL,'direction':'deteriorating','comparison':'increases $0.5 million','citations':['D187']}]}
        result,d=h.derive_pack(pack,before,after)
        self.assertEqual(result['signals'][3]['label'],h.NEW_LABEL)
        restored=copy.deepcopy(result);restored['report_sha256']=pack['report_sha256']
        for x in restored['signals']:x['finding_id']=fid
        restored['signals'][3]['label']=h.OLD_LABEL
        self.assertEqual(restored,pack)
        pack['signals'][3]['label']='other'
        with self.assertRaises(ValueError):h.derive_pack(pack,before,after)

    def test_forged_authority_cannot_pass_recomputed_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'protocol.json').write_text('p');pack=root/'pack';pack.write_text('s')
            value={'kind':h.VERSION,'enabled':True,'reason':'approved','source_protocol_sha256':h.m.base.sha(root/'protocol.json'),
                'source_signals_sha256':h.m.base.sha(pack),'max_tokens':200000,'max_review_attempts':1}
            h.authority(value,root,pack)
            for key,new in [('enabled',False),('max_tokens',200001),('max_review_attempts',2)]:
                forged={**value,key:new}
                with self.assertRaises(ValueError):h.authority(forged,root,pack)

    def review(self):
        return {'candidate_sha256':'c','plan_sha256':'p','verdict':'pass','report_criteria':{k:{'status':'pass','evidence':'specific'} for k in h.m.legacy.CRITERIA},
            'signal_review':{},'signal_label_resolution':{'id':h.FINDING,'status':'closed','reason':'corrected','citations':['D187'],'passage_ids':['P1']},'findings':[]}

    def test_pass_requires_closed_label_and_all_criteria(self):
        p={'candidate_sha256':'c','plan_sha256':'p'}
        with patch.object(h.s,'validate_review',return_value=True),patch.object(h.m.corrections,'claim'):
            self.assertTrue(h.validate_review(self.review(),p,{}, {},{},{}))
            value=self.review();value['signal_label_resolution']['status']='open'
            with self.assertRaises(ValueError):h.validate_review(value,p,{}, {},{}, {})
            value=self.review();value['report_criteria']['materiality']['status']='fail'
            with self.assertRaises(ValueError):h.validate_review(value,p,{}, {},{}, {})
            with patch.object(h.s,'validate_review',return_value=False):
                with self.assertRaises(ValueError):h.validate_review(self.review(),p,{}, {},{}, {})

    def test_duplicate_session_rejected_at_real_replay_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory)/'review';job.mkdir();text='full report';bindings={'candidate_sha256':'a'*64,'plan_sha256':'b'*64}
            expected={**bindings,'review_context_version':h.m.review_loop.VERSION,'evidence_expansion':0,
                'evidence_requests_sha256':h.m.base.digest([]),'extra_scope_ids_sha256':h.m.base.digest([]),'prior_review_output_sha256':None}
            (job/'prompt.txt').write_text(text)
            request={'bindings':expected,'model':h.MODEL[0],'effort':h.MODEL[1],'prompt_sha256':h.m.base.sha(job/'prompt.txt')}
            h.m.repair.write(job/'request.json',request)
            content={'candidate_sha256':'a'*64,'plan_sha256':'b'*64,'verdict':'pass'}
            h.m.repair.write(job/'output.json',{'request_sha256':h.m.base.digest(request),'content':content})
            result={'content':content,'receipt':{'session':{'id':'prior','usage':{'totalTokens':10}}}}
            with self.assertRaisesRegex(ValueError,'fresh review'):
                h.m.review_loop.replay(job,lambda extra:text,bindings,h.MODEL,{}, {},'a'*64,'b'*64,{'prior'},200000,350000,lambda _:result,max_expansions=0)

if __name__=='__main__':unittest.main()
