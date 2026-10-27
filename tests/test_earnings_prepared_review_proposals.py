import copy,unittest
from research.earnings_prepared_review_proposals import derive_proposals,gaap_basis_sources

def fixture():
    items={'analysis:0':{'value':{'section':'qa','text':'Unchanged fictional prose','citations':['exchange-bb'],'quotes':[{'passage_id':'Pkeep'},{'passage_id':'Pdrop'}]},'depends_on':[]},'format':{'value':{'basis':{'text':'','citations':[]}},'depends_on':[]}}
    review={'reopen':[],'decisions':[{'unit_id':'analysis:0','verdict':'revise','review_kind':'mixed','reason':'Bind the answer to exchange-aa.','passage_ids':['Panswer'],'editorial_repairs':[{'field_path':['quotes'],'before':[{'passage_id':'Pkeep'},{'passage_id':'Pdrop'}],'after':[{'passage_id':'Pkeep'}],'reason':'Remove disconnected excerpt'}]}, {'unit_id':'format','verdict':'revise','review_kind':'editorial','reason':'Label basis','passage_ids':[],'editorial_repairs':[{'field_path':['basis','text'],'before':'','after':'Financial-table figures are GAAP.','reason':'Exact basis note'}]}]}
    return items,review,{'passages':[{'passage_id':'Panswer','scope_id':'turn-answer'}]},{'exchanges':[{'id':'exchange-aa','answer_turn_ids':['turn-answer']}]}
class ProposalTests(unittest.TestCase):
    def test_gaap_note_only_binds_unchanged_selected_native_extracted_facts(self):
        rows=[{'id':'F1','concept':'us-gaap:Revenues','status':'extracted'}]
        self.assertEqual(gaap_basis_sources('Financial-table figures are GAAP.',['F1'],rows),['F1'])
        for label,selected,obs in [('Adjusted figures are superior.',['F1'],rows),('Financial-table figures are GAAP.',[],rows),('Financial-table figures are GAAP.',['unknown'],rows),('Financial-table figures are GAAP.',['F1'],[{'id':'F1','concept':'issuer:Adjusted','status':'extracted'}])]:
            with self.assertRaises(ValueError):gaap_basis_sources(label,selected,obs)
    def test_exact_typed_edits_and_explicit_source_binding_preserve_all_prose(self):
        items,review,catalog,index=fixture();before=copy.deepcopy(items);out=derive_proposals(items,review,catalog,index)
        self.assertEqual(out['analysis:0']['value']['citations'],['exchange-bb','exchange-aa']);self.assertEqual(out['analysis:0']['value']['text'],before['analysis:0']['value']['text']);self.assertEqual(out['analysis:0']['value']['quotes'],[{'passage_id':'Pkeep'}]);self.assertEqual(items,before)
    def test_unproposed_prose_and_quote_addition_rejected(self):
        for change in ({'field_path':['text'],'before':'Unchanged fictional prose','after':'Invented prose','reason':'Rewrite'}, {'field_path':['quotes'],'before':[{'passage_id':'Pkeep'},{'passage_id':'Pdrop'}],'after':[{'passage_id':'Pnew'}],'reason':'Invented quote'}):
            items,review,catalog,index=fixture();review['decisions'][0]['editorial_repairs']=[change]
            with self.assertRaises(ValueError):derive_proposals(items,review,catalog,index)
    def test_missing_ambiguous_or_uninspected_target_rejected(self):
        for reason,ids in [('No explicit target.',['Panswer']),('Bind exchange-aa and exchange-cc.',['Panswer']),('Bind exchange-aa.',[]),('Bind exchange-cc.',['Panswer'])]:
            items,review,catalog,index=fixture();review['decisions'][0].update(reason=reason,passage_ids=ids)
            with self.assertRaises(ValueError):derive_proposals(items,review,catalog,index)
    def test_extra_or_partial_review_and_stale_edit_rejected(self):
        for mode in ['reopen','partial','stale']:
            items,review,catalog,index=fixture()
            if mode=='reopen':review['reopen']=[{'unit_id':'other'}]
            elif mode=='partial':review['decisions'].pop()
            else:review['decisions'][1]['editorial_repairs'][0]['before']='different'
            with self.assertRaises(ValueError):derive_proposals(items,review,catalog,index)
