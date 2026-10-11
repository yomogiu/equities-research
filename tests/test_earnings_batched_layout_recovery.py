"""Fictional lossless presentation recovery; no model calls."""
import copy,unittest
from research import earnings_batched_layout_recovery as recovery
from research import earnings_report_repair as repair

class LayoutRecoveryTests(unittest.TestCase):
    def plan(self):
        return {'before_sha256':'fake','changes':[{'unit_id':'format','before_sha256':'fake','value':{'basis':{'text':'Fictional basis','citations':['F1']},'rows':{},'layout':{'summaries':[{'text':'Fictional comparison','row_ids':['row-fake'],'citations':['F1']}]}}} ]}
    def test_exact_summary_and_all_other_fields_preserved(self):
        original=self.plan();snapshot=copy.deepcopy(original);derived=recovery.derive(original)
        self.assertEqual(original,snapshot)
        layout=derived['changes'][0]['value']['layout']
        for key,value in recovery.DEFAULTS.items():self.assertEqual(layout.pop(key),value)
        self.assertEqual(derived,original)
    def test_complete_or_unknown_layouts_not_reinterpreted(self):
        for key,value in [('version','unknown'),('fold',[]),('executable','anything')]:
            plan=self.plan();plan['changes'][0]['value']['layout'][key]=value
            with self.assertRaises(ValueError):recovery.derive(plan)
    def test_missing_empty_and_duplicate_format_refused(self):
        for plan in [{'changes':[]},{'changes':self.plan()['changes']*2}]:
            with self.assertRaises(ValueError):recovery.derive(plan)
        plan=self.plan();plan['changes'][0]['value']['layout']['summaries']=[]
        with self.assertRaises(ValueError):recovery.derive(plan)
    def test_normal_validator_still_rejects_missing_evidence_rows(self):
        layout=recovery.derive(self.plan())['changes'][0]['value']['layout']
        with self.assertRaises(ValueError):repair.validate_layout(layout,{}, {'F1'})
    def test_prompt_supplies_complete_schema(self):
        from unittest.mock import patch
        with patch.object(recovery.flow,'proposal_prompt',return_value='Fictional prompt'):
            text=recovery.proposal_prompt({}, {}, {}, '',{})
        self.assertIn('exactly version',text);self.assertIn('Do not emit a partial layout',text)

    def test_summary_on_visible_row_passes_without_moving_or_folding_it(self):
        layout=recovery.derive(self.plan())['changes'][0]['value']['layout']
        repair.validate_layout(layout,{'row-fake':{}},{'F1'})
        self.assertEqual(layout['detail_rows'],[]);self.assertEqual(layout['fold'],[])
        self.assertEqual(layout['basis_position'],'before_tables')
