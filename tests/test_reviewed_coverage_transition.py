import copy
import unittest
from research import reviewed_coverage_transition as t
from research.contracts import digest
class TransitionTests(unittest.TestCase):
    def fixture(self):
        old={'source':{'document_id':'fictional','text_sha256':'a'*64},'parser_sha256':'b'*64,'boundary_review':'partially_reviewed','needs_review':True,'reviewed_sidecar':{'proposal_sha256':'c'*64},'turns':[{'id':'original-turn','start':0,'end':10,'speaker':'Operator','role':'operator','dialogue_function':'submitted_question'}],'exchanges':[{'id':'original-exchange','question_turn_ids':['original-turn']}],'coverage':{'assigned_characters':10},'issuer_affiliation':{'catalog_id':'d'*64}}
        new=copy.deepcopy(old);new['parser_sha256']='e'*64
        prior={'research/transcript_evidence.py':'b'*64,'research/reviewed_transcript_index.py':'f'*64};current={**prior,'research/transcript_evidence.py':'e'*64}
        return old,new,prior,current
    def test_exact_provenance_only_no_acceptance(self):
        a,b,p,c=self.fixture();original=copy.deepcopy((a,b));v=t.verify(a,b,digest(a),p,c);self.assertFalse(v['whole_report_accepted']);self.assertEqual((a,b),original)
    def test_every_other_field_remains_bound(self):
        for field,value in [('source',{'document_id':'other'}),('turns',[{'id':'guessed-turn'}]),('exchanges',[]),('coverage',{}),('reviewed_sidecar',{}),('issuer_affiliation',{'catalog_id':'new'}),('needs_review',False),('boundary_review','reviewed')]:
            a,b,p,c=self.fixture();b[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):t.verify(a,b,digest(a),p,c)
    def test_approval_and_actual_code_must_match(self):
        a,b,p,c=self.fixture()
        for h,prior,current in [('0'*64,p,c),(digest(a),{**p,'research/transcript_evidence.py':'0'*64},c),(digest(a),p,{**c,'research/transcript_evidence.py':'0'*64}),(digest(a),{},c)]:
            with self.assertRaises(ValueError):t.verify(a,b,h,prior,current)
