"""Fictitious mixed-unit presentation preserves source amounts and distinct periods."""
import copy
import hashlib
import unittest
from test_earnings_compact_layout import CompactLayoutTests
from research import earnings_report_repair as repair


class MixedUnitLayoutTests(CompactLayoutTests):
    def mixed(self):
        spec=copy.deepcopy(self.spec)
        spec['layout'].update(version='compact-financial-mixed-units-v2',fold=[],detail_rows=[],summaries=[])
        return spec

    def test_mixed_units_share_exact_period_header_and_keep_every_cell(self):
        spec=self.mixed(); before=copy.deepcopy((self.model,self.financial,spec))
        rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        text=repair.table(self.financial,self.bundle,spec)
        self.assertEqual(rendered.count('<table>'),1)
        self.assertEqual(rendered.count('<th>Unit</th>'),1)
        self.assertEqual(rendered.count('Jan 1, 2040'),1)
        self.assertIn('USD millions',rendered); self.assertIn('ratio',rendered)
        for fid,value in [('F001','12.34'),('F002','0.42'),('F003','4.56'),('F004','3.21')]:
            self.assertEqual(rendered.count('href="#e-'+fid+'"'),1)
            self.assertIn(value+' ['+fid+']',text)
        self.assertEqual(before,(self.model,self.financial,spec))

    def test_eps_keeps_unit_and_accounting_label_without_illegal_fold(self):
        self.groups[1]['unit']='USD / shares'
        self.groups[1]['rows'][0].update(metric='Diluted EPS (GAAP)',dimensions='')
        spec=self.mixed(); rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        self.assertEqual(rendered.count('<table>'),1)
        self.assertIn('Diluted EPS (GAAP)',rendered)
        self.assertIn('USD / shares',rendered)
        self.assertIn('0.42',rendered);self.assertNotIn('42%',rendered)

    def test_same_end_date_different_duration_is_not_merged(self):
        self.groups[0]['periods']=[{'key':['duration','2040-01-01','2040-06-30'],'label':'First half'}]
        self.groups[1]['periods']=[{'key':['duration','2040-04-01','2040-06-30'],'label':'Second quarter'}]
        rendered=repair.table(self.financial,self.bundle,self.mixed(),self.refs)
        self.assertEqual(rendered.count('<table>'),2)
        self.assertIn('First half',rendered);self.assertIn('Second quarter',rendered)

    def test_detail_routing_remains_separate_and_facts_appear_once(self):
        spec=self.mixed();spec['layout']['detail_rows']=[self.keys['Lease commitments']]
        rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        self.assertEqual(rendered.count('<table>'),2)
        self.assertEqual(rendered.count('href="#e-F003"'),1)
        self.assertIn('4.56',rendered.split('<details')[1])

    def test_visible_row_summary_keeps_context_in_new_version_only(self):
        spec=self.mixed();spec['layout']['summaries']=copy.deepcopy(self.spec['layout']['summaries'])
        rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        self.assertNotIn('<details',rendered)
        self.assertIn('Fictional leases total',rendered)
        spec['layout']['version']='compact-financial-v1'
        with self.assertRaises(ValueError):repair.table(self.financial,self.bundle,spec,self.refs)

    def test_equal_display_labels_do_not_merge_different_source_dates(self):
        self.groups[1]['periods']=[{'key':['instant','2041-01-01'],'label':'Jan 1, 2040'}]
        rendered=repair.table(self.financial,self.bundle,self.mixed(),self.refs)
        self.assertEqual(rendered.count('<table>'),2)

    def test_table_override_units_and_citations_remain_on_original_rows(self):
        spec=self.mixed(); tables=repair.table_catalog(self.financial,self.bundle)
        spec['tables']={key:{'unit_label':group['unit']+' <source>',
                            'period_labels':['Same reviewed date'],'citations':['D001']}
                        for key,group in tables.items()}
        rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        text=repair.table(self.financial,self.bundle,spec)
        self.assertEqual(rendered.count('<table>'),1)
        self.assertIn('USD millions &lt;source&gt;',rendered)
        self.assertIn('ratio &lt;source&gt;',rendered)
        self.assertIn('ratio <source> [D001]',text)
        self.assertEqual(rendered.count('Same reviewed date'),1)
        list(spec['tables'].values())[1]['period_labels']=['Different reviewed date']
        self.assertEqual(repair.table(self.financial,self.bundle,spec,self.refs).count('<table>'),2)

    def test_v1_fixture_is_byte_exact_against_frozen_renderer(self):
        rendered=repair.table(self.financial,self.bundle,self.spec,self.refs)
        self.assertEqual(hashlib.sha256(rendered.encode()).hexdigest(),
                         'b19d7015feaa50f969400420a605530d2c87ad93c6da6e9409c1bf499f160684')

    def test_old_version_keeps_original_unit_groups(self):
        spec=self.mixed();spec['layout']['version']='compact-financial-v1'
        rendered=repair.table(self.financial,self.bundle,spec,self.refs)
        self.assertEqual(rendered.count('<table>'),2)
        self.assertNotIn('<th>Unit</th>',rendered)

if __name__=='__main__':unittest.main()
