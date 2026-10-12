import copy
import unittest
from research.earnings_batched_grounding_recovery import derive_question_ids

class QuestionIDTransportTests(unittest.TestCase):
    def fixture(self):
        prior={'exchange_coverage':[{'exchange_id':'exchange-fake','question_passage_ids':['P123456789ab'], 'answer_passage_ids':['P999999999999']}], 'quotes':[{'passage_id':'P999999999999'}]}
        catalog={'passages':[{'passage_id':'P123456789abc','scope_id':'turn-question','text':'Full fictional question'}, {'passage_id':'P999999999999','scope_id':'turn-answer','text':'Full fictional answer'}]}
        grounding={'exchanges':[{'exchange_id':'exchange-fake','question_turn_ids':['turn-question'],'turns':[{'id':'turn-question','courtesy_only':False,'passage_ids':['P123456789abc']}]}]}
        return prior,catalog,grounding,{'files':{'output.json':'original-bytes'}}

    def test_exact_scoped_derivation_preserves_original_and_other_fields(self):
        p,c,g,r=self.fixture();original=copy.deepcopy(p)
        out,audit=derive_question_ids(p,c,g,r)
        self.assertEqual(p,original)
        self.assertEqual(out['exchange_coverage'][0]['question_passage_ids'],['P123456789abc'])
        self.assertEqual(out['quotes'],p['quotes'])
        self.assertEqual(out['exchange_coverage'][0]['answer_passage_ids'],p['exchange_coverage'][0]['answer_passage_ids'])
        self.assertEqual(audit['original_output_sha256'],'original-bytes')
        self.assertTrue(audit['independent_review_required'])

    def test_global_collision_rejected_even_outside_question(self):
        p,c,g,r=self.fixture();c['passages'].append({'passage_id':'P123456789abd','scope_id':'other','text':'Other'})
        with self.assertRaisesRegex(ValueError,'globally unique'):derive_question_ids(p,c,g,r)

    def test_wrong_scope_empty_text_and_courtesy_rejected(self):
        for kind in ('scope','empty','courtesy'):
            p,c,g,r=self.fixture()
            if kind=='scope':c['passages'][0]['scope_id']='answer'
            if kind=='empty':c['passages'][0]['text']=' '
            if kind=='courtesy':g['exchanges'][0]['turns'][0]['courtesy_only']=True
            with self.assertRaisesRegex(ValueError,'question scope'):derive_question_ids(p,c,g,r)

    def test_no_general_prefix_alias_duplicate_or_noop(self):
        for pid in ('P123456789a','P123456789abcd','P123456789abc'):
            p,c,g,r=self.fixture();p['exchange_coverage'][0]['question_passage_ids']=[pid]
            with self.assertRaises(ValueError):derive_question_ids(p,c,g,r)
        p,c,g,r=self.fixture();p['exchange_coverage'][0]['question_passage_ids'].append('P123456789abc')
        with self.assertRaisesRegex(ValueError,'duplicate'):derive_question_ids(p,c,g,r)
