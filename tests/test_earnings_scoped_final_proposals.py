"""Fictional exact authorized correction and terminal fresh-review regressions."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_scoped_final_proposals as scoped
from research import earnings_mixed_runner as b, earnings_file_pipeline as pipeline
from research import earnings_batch_review as batch, earnings_prepared_review as prepared
from research import earnings_qa_grounding as grounding, earnings_file_context as context
from test_earnings_passages import PassageFixture
import test_earnings_file_pipeline as fixtures


class ProposalTests(PassageFixture,unittest.TestCase):
    def proposal_fixture(self):
        state={'artifacts':{'financial':self.financial,'retrieval':self.retrieval,'analysis':self.report},
               'format':pipeline.mechanical.formatting(self.financial,self.bundle)}
        pack=fixtures.FilePipelineTests.pack(self,state);items=batch.units(state,pack)
        pid=self.ids[0];source=next(p for p in self.catalog['passages'] if p['passage_id']==pid)
        revised=copy.deepcopy(self.report);revised['findings'][0]['text']='Fictional source-backed corrected wording.';revised['findings'][0]['quotes']=[]
        original={'state':state,'signals':pack,'items':items,'review_output_sha256':'review-fake'}
        proposal={'version':'source-backed-final-correction-proposal-v1','provider_calls':0,'frozen_outputs_modified':False,
                  'review_output_sha256':'review-fake','batch_sha256':b.digest(items),'original_analysis_sha256':b.digest(self.report),
                  'proposed_analysis_sha256':b.digest(revised),'source_passages':{pid:copy.deepcopy(source)},'affected_units':['analysis:0'],'operations':[]}
        for field in ('text','quotes'):
            proposal['operations'].append({'unit_id':'analysis:0','unit_before_sha256':b.digest(items['analysis:0']['value']),
                'field':field,'before':copy.deepcopy(items['analysis:0']['value'][field]),'after':copy.deepcopy(revised['findings'][0][field]),
                'source_passage_ids':[pid],'reason':'Fictional reviewed source support.'})
        return original,proposal,revised

    def test_multiple_fields_use_original_unit_and_preserve_every_other_value(self):
        original,proposal,expected=self.proposal_fixture();before=copy.deepcopy(original)
        revised,pack,plan,pending=scoped.apply_proposal(original,proposal,self.catalog)
        self.assertEqual(revised['artifacts']['analysis'],expected);self.assertEqual(len(plan['changes']),1)
        self.assertEqual(revised['artifacts']['financial'],original['state']['artifacts']['financial'])
        self.assertEqual(revised['artifacts']['retrieval'],original['state']['artifacts']['retrieval'])
        self.assertEqual(revised['format'],original['state']['format']);self.assertEqual(original,before)
        self.assertIn('analysis:0',pending)

    def test_stale_added_duplicate_and_unsupported_operations_fail(self):
        for change in ('stale','duplicate','field','source','unit','digest','affected'):
            original,proposal,_=self.proposal_fixture()
            if change=='stale':proposal['operations'][0]['unit_before_sha256']='0'*64
            if change=='duplicate':proposal['operations'].append(copy.deepcopy(proposal['operations'][0]))
            if change=='field':proposal['operations'][0]['field']='heading'
            if change=='source':next(iter(proposal['source_passages'].values()))['text']='Fabricated source'
            if change=='unit':proposal['operations'][0]['unit_id']='financial'
            if change=='digest':proposal['proposed_analysis_sha256']='0'*64
            if change=='affected':proposal['affected_units'].append('analysis:1')
            with self.subTest(change=change),self.assertRaises(ValueError):scoped.apply_proposal(original,proposal,self.catalog)


class ApprovalTests(unittest.TestCase):
    def test_exact_parent_proposal_accounting_and_one_cycle_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();previous=root/'reporting/runs/fictional/pipeline';previous.mkdir(parents=True)
            b.save(previous/'protocol.json',{'fictional':'protocol'});b.save(previous.parent/'request.json',{'fictional':'request'})
            proposal=root/'proposal.json';b.save(proposal,{'fictional':'approved batch'})
            original={'tokens':50000,'max_tokens':200000,'models':pipeline.ORIGINAL_MODELS}
            approval={'version':'explicit-one-cycle-earnings-correction-v1','scope':'one_additional_correction_cycle','approved':True,
              'max_additional_correction_cycles':1,'approval':{'response':'Yes, approve this exact proposal.','question':'Approve one final cycle?'},
              'proposal_path':'proposal.json','proposal_sha256':b.sha(proposal),'source_run_id':'fictional',
              'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_request_sha256':b.digest(b.read(previous.parent/'request.json')),
              'report_max_tokens':200000,'inherited_report_tokens':50000,'remaining_tokens':150000,'models':copy.deepcopy(pipeline.ORIGINAL_MODELS),
              'source_preparation_tokens':100000,'original_total_max_tokens':300000}
            scoped.validate_approval(previous,proposal,approval,original)
            for key,value in [('max_additional_correction_cycles',2),('approved',False),('inherited_report_tokens',0),('remaining_tokens',200000),('report_max_tokens',250000),('source_run_id','another'),('proposal_sha256','0'*64),('proposal_path','../proposal.json')]:
                with self.subTest(key=key),self.assertRaises(ValueError):scoped.validate_approval(previous,proposal,{**approval,key:value},original)


class ScopedPipelineTests(PassageFixture,unittest.TestCase):
    def prepare(self):
        self.drain=fixtures.FilePipelineTests.drain.__get__(self);self.pack=fixtures.FilePipelineTests.pack.__get__(self)
        self.fake_run=fixtures.FilePipelineTests.fake_run.__get__(self)
        report=copy.deepcopy(self.report);report['report_template']=pipeline.template.VERSION
        for finding,section in zip(report['findings'],('demand','earnings','outlook','qa')):finding['section']=section
        old_state={'artifacts':{'financial':self.financial,'retrieval':self.retrieval,'analysis':report},'format':pipeline.mechanical.formatting(self.financial,self.bundle)}
        old_pack=self.pack(old_state);state=copy.deepcopy(old_state);state['artifacts']['analysis']['findings'][0]['text']='Fictional approved corrected report.'
        writing=self.root/'writing';writing.write_text('Fictional source-bound writing.')
        self.value={'version':scoped.VERSION,'state':state,'signals':old_pack,'tokens':50000,'max_tokens':200000,
          'session_ids':['old-retrieval','old-analysis','old-signal','old-review'],'models':copy.deepcopy(pipeline.ORIGINAL_MODELS),
          'writing_sha256':b.sha(writing),'report_template':pipeline.template.VERSION,'grounding':grounding.build(self.bundle,self.catalog,version=grounding.NAMED_GREETING_VERSION),
          'start_round':1,'spent_correction_rounds':1,'remaining_correction_rounds':0,'findings':{'analysis:0':'Fictional original source finding'},'derivation':{'fictional':'exact approved batch'}}
        self.path=self.root/'preparation';b.save(self.path,self.value);self.output=self.root/'continued'
        pipeline.initialize(self.casepath,self.output,writing,max_tokens=200000,review_preparation=self.path)

    def test_fresh_signals_then_full_review_count_all_prior_usage_and_exact_one_cycle(self):
        from research import earnings_file_runner as runner
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare()
            with patch.object(runner,'run_role',side_effect=self.fake_run) as launch:
                preview=pipeline.advance(self.output,False);launch.assert_not_called()
                self.assertEqual((preview['stage'],preview['tokens']),('signal_author',50000))
                first=pipeline.advance(self.output,True);self.assertEqual(launch.call_count,1)
                self.assertEqual((first['stage'],first['tokens']),('review-1',50040))
                result=pipeline.advance(self.output,True);self.assertEqual(launch.call_count,2)
                self.assertEqual(result['status'],'accepted');self.assertEqual(result['tokens'],50080);self.assertEqual(result['correction_rounds'],1)
                self.assertEqual(len(result['session_ids']),6)
                self.assertNotEqual(result['signals']['report_sha256'],self.value['signals']['report_sha256'])
                self.assertEqual({p.name for p in (self.output/'jobs').iterdir()},{'signal_author','review-1'})
                self.assertEqual(result['state'],self.value['state'])

    def test_failed_fresh_review_is_terminal_and_never_launches_another_correction(self):
        from research import earnings_file_runner as runner
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare();self.fail_reviews=1
            with patch.object(runner,'run_role',side_effect=self.fake_run) as launch:
                pipeline.advance(self.output,True);result=pipeline.advance(self.output,True)
                self.assertEqual(result['status'],'blocked');self.assertEqual(result['stage'],'review-1');self.assertEqual(result['correction_rounds'],1)
                for _ in range(2):self.assertEqual(pipeline.advance(self.output,True),result)
                self.assertEqual(launch.call_count,2)
                self.assertFalse((self.output/'jobs/correction-2').exists());self.assertFalse((self.output/'jobs/correction-1').exists())

    def test_reused_prior_session_cannot_be_counted_as_fresh_signals(self):
        from research import earnings_file_runner as runner
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare();self.value['session_ids'][2]='fictional-signal_author'
            self.path.unlink();b.save(self.path,self.value)
            protocol=self.output/'protocol.json';value=b.read(protocol);protocol.unlink()
            context.write(protocol,{**value,'review_preparation_sha256':b.sha(self.path)})
            with patch.object(runner,'run_role',side_effect=self.fake_run),self.assertRaisesRegex(ValueError,'Independent fresh role session'):
                pipeline.advance(self.output,True)
            self.assertFalse((self.output/'jobs/review-1').exists())

    def test_changed_grounding_or_template_rejected(self):
        with patch.object(prepared,'verify',side_effect=lambda *a:self.value):
            self.prepare();path=self.output/'protocol.json';value=b.read(path);path.unlink();context.write(path,{**value,'report_template':None})
            with self.assertRaisesRegex(ValueError,'Scoped final'):pipeline.load(self.output)


class FrozenReplayTests(PassageFixture,unittest.TestCase):
    def test_frozen_replay_authenticates_canonicalized_review_context_without_parent_writes(self):
        import json
        import subprocess
        import sys
        import test_earnings_analysis_display_transport as display_fixtures
        from research import earnings_prepared_retrieval as retrieval, earnings_prepared_analysis as analysis
        from research import earnings_financial_outline as outline, earnings_file_runner as runner
        self.drain=fixtures.FilePipelineTests.drain.__get__(self)
        def reversed_pack(state):
            result=fixtures.FilePipelineTests.pack(self,state);result['signals'].reverse();return result
        self.pack=reversed_pack;self.fail_reviews=1
        fake_run=fixtures.FilePipelineTests.fake_run.__get__(self)
        with patch.object(retrieval,'verify',side_effect=lambda *a:self.retrieval_value),patch.object(analysis,'verify',side_effect=lambda *a:self.analysis_value):
            display_fixtures.PipelineTests.setup_prepared(self)
            with patch.object(outline,'artifact',return_value=self.financial),patch.object(runner,'run_role',side_effect=fake_run):
                pipeline.advance(self.output,True);pending=pipeline.advance(self.output,True)
            self.assertEqual(pending['stage'],'correction-1')
        root=self.output.resolve();before={str(p.relative_to(root)):b.sha(p) for p in root.rglob('*') if p.is_file()}
        wrapper="""import sys,json
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
from research import earnings_prepared_retrieval as retrieval,earnings_prepared_analysis as analysis,earnings_financial_outline as outline,earnings_mixed_runner as b
with patch.object(retrieval,'verify',side_effect=lambda path,*args:b.read(path)),patch.object(analysis,'verify',side_effect=lambda path,*args:b.read(path)),patch.object(outline,'artifact',return_value=json.loads(sys.argv[3])):
 exec(sys.argv[4])
"""
        result=subprocess.run([sys.executable,'-I','-B','-c',wrapper,str(Path(pipeline.__file__).resolve().parents[1]),str(root),json.dumps(self.financial),scoped.PROGRAM],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['tokens'],24080);self.assertEqual(len(value['session_ids']),4)
        self.assertEqual(before,{str(p.relative_to(root)):b.sha(p) for p in root.rglob('*') if p.is_file()})
