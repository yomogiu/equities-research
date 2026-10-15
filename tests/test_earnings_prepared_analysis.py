import unittest,copy
from research.earnings_prepared_analysis import normalize
class AddressingTests(unittest.TestCase):
    def test_exact_address_mapping_keeps_all_prose_and_quote_selections(self):
        raw={'opening':'Fictional opening','opening_citations':['fake-call','D001'],'findings':[{'text':'Fictional claim','citations':['Pfake','fake-call','Pfake'],'quotes':[{'passage_id':'Pfake'}]}]}
        before=copy.deepcopy(raw);catalog={'passages':[{'passage_id':'Pfake','scope_id':'turn-fictional'}]}
        out=normalize(raw,catalog,'fake-call',['section-prepared','section-qa'])
        self.assertEqual(out['opening_citations'],['section-prepared','section-qa','D001'])
        self.assertEqual(out['findings'][0]['citations'],['turn-fictional','section-prepared','section-qa'])
        self.assertEqual(raw,before);self.assertEqual(out['findings'][0]['text'],raw['findings'][0]['text'])
        self.assertEqual(out['findings'][0]['quotes'],raw['findings'][0]['quotes'])
    def test_unknown_references_remain_for_validator_rejection(self):
        self.assertEqual(normalize({'citations':['unknown']},{'passages':[]},'fake-call',['section-qa'])['citations'],['unknown'])
        with self.assertRaises(ValueError):normalize({'citations':['fake-call']},{'passages':[]},'fake-call',[])
