"""Lossless transport derivation, not semantic or source acceptance."""
import unittest
from research.earnings_prepared_retrieval import normalize
class PreparationTests(unittest.TestCase):
    def test_alias_conversion_retains_text_ids_other_fields_and_original(self):
        raw={'document_findings':[{'finding':'Fictional cash rose.','document_id':'D001'}],'quotes':[{'passage_id':'Pfake'}]}
        result=normalize(raw)
        self.assertEqual(result['document_findings'],[{'text':'Fictional cash rose.','citations':['D001']}])
        self.assertEqual(result['quotes'],raw['quotes']);self.assertIn('finding',raw['document_findings'][0])
        self.assertEqual(normalize(result),result)
    def test_mixed_unknown_or_missing_fields_cannot_be_silently_derived(self):
        for row in ({'finding':'Fictional','document_id':'D001','citations':['D002']},{'finding':'Fictional'}, {'text':'Fictional','source':'D001'}):
            with self.assertRaises(ValueError):normalize({'document_findings':[row]})
