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
