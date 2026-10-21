import unittest,copy,json
import tempfile
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_analysis as prepared
from research.earnings_prepared_analysis import normalize,remove_single_duplicate,resolve_quoted_exchange
class AddressingTests(unittest.TestCase):
    def test_exchange_address_comes_only_from_unique_original_quoted_answer(self):
        raw={'findings':[{'section':'qa','text':'Fictional question and answer','citations':['exchange-unrelated-missing-id'],'quotes':[{'passage_id':'Pexact'}]}]}
        catalog={'passages':[{'passage_id':'Pexact','scope_id':'turn-answer'}]}
        index={'exchanges':[{'id':'exchange-original','answer_turn_ids':['turn-answer']}]}
        before=copy.deepcopy(raw);expected=copy.deepcopy(raw);expected['findings'][0]['citations']=['exchange-original']
        self.assertEqual(resolve_quoted_exchange(raw,catalog,index),expected);self.assertEqual(raw,before)

    def test_exchange_address_rejects_ambiguous_or_nonanswer_provenance(self):
        raw={'findings':[{'section':'qa','citations':['exchange-missing'],'quotes':[{'passage_id':'Pexact'}]}]}
        catalog={'passages':[{'passage_id':'Pexact','scope_id':'turn-answer'}]}
        for exchanges in ([],[{'id':'exchange-one','answer_turn_ids':['other-turn']}],
                          [{'id':'exchange-one','answer_turn_ids':['turn-answer']},{'id':'exchange-two','answer_turn_ids':['turn-answer']}]):
            with self.assertRaises(ValueError):resolve_quoted_exchange(raw,catalog,{'exchanges':exchanges})
        for changes in ({'section':'outlook'},{'quotes':[]},{'quotes':[{'passage_id':'unknown'}]},
                        {'citations':['exchange-missing','D001']}):
            bad=copy.deepcopy(raw);bad['findings'][0].update(changes)
            with self.assertRaises(ValueError):resolve_quoted_exchange(bad,catalog,{'exchanges':[{'id':'exchange-one','answer_turn_ids':['turn-answer']}]})

    def test_single_cross_finding_duplicate_keeps_prose_and_all_distinct_selections(self):
        raw={'opening':'Fictional opening','findings':[{'text':'First','citations':['turn-a'],'quotes':[{'passage_id':'Pfirst'}]},
            {'text':'Second','citations':['turn-b'],'quotes':[{'passage_id':'Psecond'},{'passage_id':'Pfirst'}]}]}
        before=copy.deepcopy(raw);expected=copy.deepcopy(raw);expected['findings'][1]['quotes'].pop()
        self.assertEqual(remove_single_duplicate(raw),expected);self.assertEqual(raw,before)

    def test_duplicate_derivation_refuses_broader_or_unknown_repairs(self):
        for selections in ([{'passage_id':'Pone'}],[{'passage_id':'Pone'}]*3,
                           [{'passage_id':'Pone'},{'passage_id':'Pone','text':'invented'}]):
            with self.assertRaises(ValueError):remove_single_duplicate({'findings':[{'quotes':selections}]})

    def test_duplicate_manifest_cannot_reset_usage_or_original_models(self):
        from research import earnings_mixed_runner as base
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'jobs/analysis').mkdir(parents=True)
            case=root/'case.json';case.write_text('{}');(root/'protocol.json').write_text('{}')
            (root/'jobs/analysis/output.json').write_text('{}')
            replay={'content':{'findings':[]},'tokens':123456,'max_tokens':1200000,
                    'session_ids':['first','second'],'case_sha256':base.sha(case),
                    'catalog_sha256':base.digest({'passages':[]}),
                    'models':{'analysis':['original-model','original-effort']},'spent_correction_rounds':0}
            path=root/'preparation.json'
            with patch.object(prepared,'replay',return_value=replay):
                record=prepared.prepare(root,case,path,duplicate_quotes=True)
                self.assertEqual(prepared.verify(path,case,{'passages':[]})['tokens'],123456)
                for key,bad in [('tokens',0),('models',{'analysis':['replacement','low']}),('spent_correction_rounds',2)]:
                    changed=copy.deepcopy(record);changed[key]=bad;path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError,'lineage changed'):prepared.verify(path,case,{'passages':[]})

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
