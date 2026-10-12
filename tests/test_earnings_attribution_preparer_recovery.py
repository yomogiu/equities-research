"""Fictitious immutable attribution acceptance and authentication regressions."""
import copy
from unittest.mock import patch
from test_earnings_attribution_overlay import OverlayTests
from research import earnings_attribution_preparer_recovery as recovery, earnings_mixed_runner as r


class PreparedAttributionTests(OverlayTests):
    def setUp(self):
        super().setUp()
        proposal=r.read(self.proposal);proposal['source']=self.value['source'];self.proposal.write_text(__import__('json').dumps(proposal));self.value['proposal']['sha256']=r.sha(self.proposal)
        self.run_overlay()
        self.bundle['manifest']={'transcript_path':str(self.source),'transcript_sha256':r.sha(self.source)}
        self.original=self.root/'retrieval.json';r.save(self.original,{'content':{'quotes':[]}})
        self.catalog_path=self.root/'catalog.json';r.save(self.catalog_path,self.catalog)
        self.bundle['transcript_index'].setdefault('coverage',{})['unassigned_qa_turn_ids']=[]
        self.candidate=self.root/'candidate.json';self.job=self.root/'job';self.job.mkdir()
        r.save(self.candidate,{'source':self.value['source'],'proposal':str(self.proposal),'overlay_review':str(self.review),'input_sha256':{str(self.proposal):r.sha(self.proposal),str(self.review):r.sha(self.review),str(self.source):r.sha(self.source)},'unassigned_turns':[],'original_retrieval_path':str(self.original),'catalog_path':str(self.catalog_path)})
        self.binding={'candidate_path':str(self.candidate),'candidate_sha256':r.sha(self.candidate),'review':{'job':str(self.job)}}
        r.save(self.job/'request.json',{'bindings':{'candidate_sha256':r.sha(self.candidate),'scope':recovery.VERSION},'model':'gpt-6.1-sol','effort':'medium'})
        (self.job/'prompt.txt').write_text(recovery.review_prompt(self.candidate))
        self.verdict={'decision':'accept','candidate_sha256':r.sha(self.candidate),**{k:True for k in ('full_source_reviewed','all_turns_accounted','submitted_questions_preserved','coverage_supported','original_financial_and_quotes_unchanged')}}
        self.response={'session':{'id':'fresh-review'},'content':self.verdict}
    def adjudicate(self):
        with patch.object(recovery.imp,'authenticate',return_value=self.response):
            return recovery.adjudicate(self.binding,self.bundle,self.catalog,{'financial-session','retrieval-session'})
    def test_authenticated_review_preserves_original_source(self):
        old=copy.deepcopy(self.bundle);derived,candidate,review=self.adjudicate()
        self.assertEqual(self.bundle,old);self.assertEqual(derived['transcript_index']['source'],old['transcript_index']['source'])
    def test_reused_preparer_session_rejected(self):
        self.response['session']['id']='financial-session'
        with self.assertRaisesRegex(ValueError,'reused a preparer'):self.adjudicate()
    def test_no_inferred_acceptance_from_partial_review(self):
        self.verdict['full_source_reviewed']=False
        with self.assertRaisesRegex(ValueError,'Complete source'):self.adjudicate()
    def test_changed_frozen_candidate_rejected(self):
        self.candidate.write_text('{}')
        with self.assertRaisesRegex(ValueError,'candidate changed'):self.adjudicate()
    def test_span_tampering_rejected(self):
        turn={'id':'fake-turn','start':0,'end':3};span={'turn_id':'fake-turn','start':0,'end':3,'text':'bad','span_sha256':'invented'}
        with self.assertRaisesRegex(ValueError,'span text changed'):recovery.span_check(turn,span,'abc')

    def test_changed_complete_review_prompt_rejected(self):
        (self.job/'prompt.txt').write_text('Partial source review')
        with self.assertRaisesRegex(ValueError,'source review prompt changed'):self.adjudicate()

class BatchedInheritedAttributionBoundaryTests(__import__('unittest').TestCase):
    def test_authenticated_candidate_reaches_independent_review_boundary_without_duplicate_normalization(self):
        import tempfile
        from pathlib import Path
        from research import earnings_batched_flow as flow, earnings_qa_grounding as qa
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);writing=root/'writing.txt';writing.write_text('Fictitious writing standard')
            protocol={'batch_review':'batched-report-review-v1','writing_standard':str(writing),'attribution_preparer_recovery':{'fake':True},'evidence_manifest':'fake','qa_grounding':qa.HEADER_VERSION}
            (root/'protocol.json').write_text(__import__('json').dumps(protocol))
            inherited={role:{'content':{},'receipt':{'session':{'id':role,'usage':{'totalTokens':1}}}} for role in ('financial','retrieval')}
            review={'session':{'id':'source-review','usage':{'totalTokens':1}}}
            def role_job(root,role,*args):
                return {'content':{},'receipt':{'session':{'id':role,'usage':{'totalTokens':1}}}}
            with patch.object(flow.pipe,'load',return_value=(protocol,{},{})), patch.object(flow.pipe.evidence,'load_bundle',return_value={}), patch.object(recovery,'apply',return_value=({},inherited,review)), patch.object(flow.pipe,'prompt',return_value='fictitious'), patch.object(flow.pipe,'validate'), patch.object(flow.signals,'prompt',return_value='fictitious'), patch.object(flow.signals,'validate'), patch.object(flow,'job',side_effect=role_job) as jobs, patch.object(flow.pipe.grounding,'normalize_courtesy',side_effect=AssertionError('Duplicate normalizer must not run')):
                result=flow._advance(root,False)
            self.assertEqual(result,{'status':'pending','stage':'batch_initialization'})
            self.assertEqual([call.args[1] for call in jobs.call_args_list],['analysis','signal_author'])

class MissingEmptyQuoteDerivationTests(__import__('unittest').TestCase):
    def test_only_one_absent_empty_list_changes(self):
        original={'findings':[{'text':'Fake first','citations':['D001'],'quotes':[{'passage_id':'fake'}]},{'text':'Fake second','citations':['D002']}]}
        derived,receipt=recovery.empty_quotes(original)
        self.assertNotIn('quotes',original['findings'][1]);self.assertEqual(derived['findings'][0],original['findings'][0]);self.assertEqual(derived['findings'][1],{**original['findings'][1],'quotes':[]});self.assertEqual(receipt['path'],'/findings/1/quotes')
    def test_no_missing_or_multiple_missing_lists_rejected(self):
        for findings in ([{'quotes':[]}],[{},{}]):
            with self.assertRaisesRegex(ValueError,'Exactly one'):recovery.empty_quotes({'findings':findings})
    def test_other_invalid_or_substantive_list_cannot_be_changed(self):
        for quotes in ('fake',list(range(5))):
            with self.assertRaisesRegex(ValueError,'Other invalid'):recovery.empty_quotes({'findings':[{'quotes':quotes},{}]})
