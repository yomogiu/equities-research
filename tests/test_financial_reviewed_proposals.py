"""Fictitious reviewed fallback rows; authentication itself has runner tests."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from types import SimpleNamespace
from research import financial_reviewed_proposals as a, financial_evidence as f, earnings_mixed_runner as b

class ReviewedProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name)
        for name in ('request.json','output.json'):(self.job/name).write_text('{}')
        self.raw=b'%PDF fictitious fixture';self.text=b'Revenue 10'
        self.source={'document_id':'fictional','issuer_id':'sec:fictional','raw_sha256':f.digest(self.raw),'text_sha256':f.digest(self.text)}
        row=f.propose_fact(self.text.decode(),self.source,concept='us-gaap:Revenues',value='10',context={'id':'c','entity':'sec:fictional','entity_scheme':'SEC CIK','start_date':'2026-01-01','end_date':'2026-03-31','instant':None,'dimensions':[]},unit={'id':'u','numerator':['iso4217:USD'],'denominator':[]},quote=self.text.decode(),start=0)
        self.profile=f.make_artifact(self.source,[row]);self.auth={'version':a.VERSION,'enabled':True,'source':self.source,'profile_digest':b.digest(self.profile),'review_sha256':b.sha(self.job/'output.json'),'request_sha256':b.sha(self.job/'request.json'),'profile_author_id':'author','period':'FY2026-Q1'}
        self.verdict={'issuer_id':'sec:fictional','period':'FY2026-Q1','financial_mapping_verdict':'pass','financial_issues':[],'verdict':'revise'}
        self.entries=[{'method':'source_batch','name':'batch','start':0,'end':10,'total':10,'ids':['D001']}]
    def run_adapter(self):
        from research import earnings_file_runner as r,earnings_file_context as c
        reader=SimpleNamespace(artifacts={'financial_proposals':self.profile},records={'D001':{'spans':[{'document_id':'fictional'}]}})
        result={'content':self.verdict,'receipt':{'session':{'id':'reviewer'}}}
        with ExitStack() as stack:
            stack.enter_context(patch.object(r,'verify_job',return_value=result));stack.enter_context(patch.object(b,'read',return_value={'context_index':str(self.job/'index.json')}))
            stack.enter_context(patch.object(c,'Evidence',return_value=reader));stack.enter_context(patch.object(c,'audit',return_value=self.entries));stack.enter_context(patch.object(c,'delivered_entries',return_value=self.entries))
            return a.approve(self.profile,self.source,self.job,self.auth)
    def test_replay_preserves_proposals_and_other_review_findings(self):
        old=copy.deepcopy(self.profile);out=self.run_adapter();self.assertEqual(old,self.profile)
        self.assertEqual('proposed',self.profile['observations'][0]['status']);self.assertEqual('revise',self.verdict['verdict'])
        self.assertTrue(a.usable(self.profile['observations'][0],{'proposal_approval':out}))
        self.assertFalse(a.usable(self.profile['observations'][0],{}))
    def test_approved_proposal_outline_keeps_normalized_value_without_xbrl_scale(self):
        from research.earnings_financial_outline import build
        approval=self.run_adapter();original=self.profile['observations'][0]
        row={**original,'id':'F001','context_id':'c','unit_id':'u'}
        data={'observations':[row],'contexts':{'c':original['context']},'proposal_approval':approval}
        result=build(data);self.assertEqual('10',result['rows'][0]['source_context'][0]['value'])
        self.assertEqual('0',result['rows'][0]['source_context'][0]['scale'])
        self.assertNotIn('scale',original)
    def test_display_uses_existing_approval_and_rejects_unapproved_proposals(self):
        from research.earnings_financial_display import build
        original=self.profile['observations'][0]
        row={**original,'id':'F001','context_id':'c','unit_id':'u'}
        data={'observations':[row],'contexts':{'c':original['context']},'units':{'u':original['unit']},'proposal_approval':self.run_adapter()}
        selected={'rows':[{'label':'Revenue','fact_ids':['F001']}]}
        self.assertTrue(build(selected,{'financial':data}))
        del data['proposal_approval']
        with self.assertRaisesRegex(ValueError,'Unqualified'):build(selected,{'financial':data})
    def test_changed_original_bytes_rejected(self):
        self.auth['source']={**self.source,'raw_sha256':'0'*64}
        with self.assertRaisesRegex(ValueError,'authorization required'):self.run_adapter()
    def test_profile_value_cannot_be_changed_after_review(self):
        self.profile['observations'][0]['value']='99'
        with self.assertRaisesRegex(ValueError,'profile changed'):self.run_adapter()
    def test_financial_defects_cannot_be_waived(self):
        self.verdict['financial_issues']=[{'reason':'wrong period'}]
        with self.assertRaisesRegex(ValueError,'without unresolved'):self.run_adapter()
    def test_truncated_or_missing_delivery_rejected(self):
        self.entries[0]['end']=9
        with self.assertRaisesRegex(ValueError,'source delivery'):self.run_adapter()
    def test_author_cannot_review_own_profile(self):
        self.auth['profile_author_id']='reviewer'
        with self.assertRaisesRegex(ValueError,'Independent'):self.run_adapter()
    def test_review_output_cannot_be_replaced(self):
        (self.job/'output.json').write_text('{"forged":true}')
        with self.assertRaisesRegex(ValueError,'review changed'):self.run_adapter()
if __name__=='__main__':unittest.main()
