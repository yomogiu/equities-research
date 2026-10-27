import unittest
from research.earnings_financial_outline import build

class OutlineTests(unittest.TestCase):
    def test_shifted_year_ago_source_selected_without_currency_or_ytd_mix(self):
        data={'contexts':{},'observations':[],'gaps':[]}
        for fid,start,end,unit in [('Q','2026-04-27','2026-07-26','USD'),
                                   ('YEAR','2025-04-28','2025-07-27','USD'),
                                   ('YTD','2024-10-28','2025-07-27','USD'),
                                   ('OTHER','2025-04-28','2025-07-27','EUR')]:
            data['contexts'][fid]={'start_date':start,'end_date':end,'dimensions':[],'entity':'fictional'}
            data['observations'].append({'id':fid,'canonical_metric':'revenue',
                'concept':'us-gaap:Revenues','context_id':fid,
                'status':'extracted','nil':False,'value':'10','unit_id':unit})
        self.assertEqual(build(data,expanded=True)['rows'][0]['fact_ids'],['Q','YEAR'])

    def test_expanded_cash_flow_prefers_quarter_and_keeps_same_currency_comparisons(self):
        data={'contexts':{},'observations':[],'gaps':[]}
        for fid,start,end,unit in [('Q','2026-07-01','2026-09-30','USD'),
                                   ('YTD','2026-01-01','2026-09-30','USD'),
                                   ('PREV','2026-04-01','2026-06-30','USD'),
                                   ('YEAR','2025-07-01','2025-09-30','USD'),
                                   ('OTHER','2026-04-01','2026-06-30','EUR')]:
            data['contexts'][fid]={'start_date':start,'end_date':end,'dimensions':[],'entity':'fictional'}
            data['observations'].append({'id':fid,'canonical_metric':'operating_cash_flow',
                'concept':'us-gaap:NetCashProvidedByUsedInOperatingActivities','context_id':fid,
                'status':'extracted','nil':False,'value':'10','unit_id':unit})
        self.assertEqual(build(data,expanded=True)['rows'][0]['fact_ids'],['Q','YEAR','PREV'])

    def test_consolidated_comparable_candidates_do_not_mix_dimensions_or_ytd_income(self):
        data={'contexts':{'q':{'start_date':'2026-04-01','end_date':'2026-06-30','dimensions':[]},'prior':{'start_date':'2025-04-01','end_date':'2025-06-30','dimensions':[]},'ytd':{'start_date':'2026-01-01','end_date':'2026-06-30','dimensions':[]},'segment':{'start_date':'2026-04-01','end_date':'2026-06-30','dimensions':['segment']}},'observations':[],'gaps':[]}
        for fid,ctx in [('F1','q'),('F2','prior'),('F3','ytd'),('F4','segment')]:
            data['observations'].append({'id':fid,'canonical_metric':'revenue','concept':'us-gaap:Revenue','context_id':ctx,'status':'extracted','nil':False,'value':'10','scale':'6','unit_id':'USD'})
        value=build(data);self.assertEqual(value['rows'][0]['fact_ids'],['F1','F2']);self.assertEqual(value['status'],'mechanical_unreviewed_outline');self.assertTrue(value['must_verify_original_scopes'])

class NativeReviewedOutlineTests(unittest.TestCase):
    def fixture(self):
        from research.earnings_financial_outline import NATIVE_STARTING_LABELS
        data={'contexts':{},'observations':[],'gaps':[]}
        for i,label in enumerate(NATIVE_STARTING_LABELS):
            for suffix,start,end in [('Q','2026-04-01','2026-06-30'),('YEAR','2025-04-01','2025-06-30'),('YTD','2026-01-01','2026-06-30')]:
                fid=f'{i}-{suffix}';data['contexts'][fid]={'start_date':start,'end_date':end,'dimensions':[],'entity':'fictional'}
                data['observations'].append({'id':fid,'canonical_metric':None,'concept':f'native:Concept{i}',
                    'context_id':fid,'status':'extracted','method':'reviewed_html_table','nil':False,
                    'value':'10','unit_id':'USD','accounting_basis':'IFRS','source_document_id':'doc',
                    'support':{'source_label':label}})
        return data

    def test_bounded_literal_labels_periods_and_unchanged_inventory(self):
        import copy
        from research.earnings_financial_outline import artifact, NATIVE_STARTING_LABELS
        data=self.fixture();before=copy.deepcopy(data)
        rows=artifact(data,expanded=True)['rows']
        self.assertEqual(len(rows),12)
        self.assertEqual([r['label'] for r in rows],list(NATIVE_STARTING_LABELS))
        self.assertEqual(rows[0]['fact_ids'],['0-Q','0-YEAR'])
        self.assertEqual(data,before)
        with self.assertRaises(ValueError):artifact(data)

    def test_ambiguous_unit_basis_entity_and_duplicate_period_fail_closed(self):
        import copy
        from research.earnings_financial_outline import native_reviewed_rows
        for field,value in [('unit_id','EUR'),('accounting_basis','US-GAAP'),('concept','native:Other'),('source_document_id','other')]:
            data=self.fixture();extra=copy.deepcopy(data['observations'][0]);extra['id']='other';extra[field]=value
            data['observations'].append(extra)
            self.assertNotIn('Revenue',[r['label'] for r in native_reviewed_rows(data)])
        data=self.fixture();extra=copy.deepcopy(data['observations'][0]);extra['id']='duplicate';data['observations'].append(extra)
        self.assertNotIn('Revenue',[r['label'] for r in native_reviewed_rows(data)])

    def test_unreviewed_segment_and_similar_label_are_not_selected(self):
        from research.earnings_financial_outline import native_reviewed_rows
        for change in ('method','dimension','label'):
            data=self.fixture()
            for o in data['observations'][:3]:
                if change=='method':o['method']='automatic'
                if change=='dimension':data['contexts'][o['context_id']]['dimensions']=['segment']
                if change=='label':o['support']['source_label']='Revenue adjusted'
            self.assertNotIn('Revenue',[r['label'] for r in native_reviewed_rows(data)])

class UppercaseNativeOutlineTests(NativeReviewedOutlineTests):
    def fixture(self):
        from research.earnings_financial_outline import NATIVE_STARTING_LABELS, UPPERCASE_NATIVE_STARTING_LABELS
        data=super().fixture()
        mapping=dict(zip(NATIVE_STARTING_LABELS,UPPERCASE_NATIVE_STARTING_LABELS))
        for o in data['observations']:o['support']['source_label']=mapping[o['support']['source_label']]
        return data

    def test_bounded_literal_labels_periods_and_unchanged_inventory(self):
        import copy
        from research.earnings_financial_outline import artifact,UPPERCASE_NATIVE_STARTING_LABELS
        data=self.fixture();before=copy.deepcopy(data);rows=artifact(data,expanded=True)['rows']
        self.assertEqual([r['label'] for r in rows],list(UPPERCASE_NATIVE_STARTING_LABELS));self.assertEqual(rows[0]['fact_ids'],['0-Q','0-YEAR']);self.assertEqual(data,before)
        with self.assertRaises(ValueError):artifact(data)

    def test_ambiguous_unit_basis_entity_and_duplicate_period_fail_closed(self):
        import copy
        from research.earnings_financial_outline import native_reviewed_rows,UPPERCASE_NATIVE_STARTING_LABELS
        for field,value in [('unit_id','EUR'),('accounting_basis','US-GAAP'),('concept','native:Other'),('source_document_id','other')]:
            data=self.fixture();extra=copy.deepcopy(data['observations'][0]);extra['id']='other';extra[field]=value;data['observations'].append(extra)
            self.assertNotIn('REVENUE',[r['label'] for r in native_reviewed_rows(data,UPPERCASE_NATIVE_STARTING_LABELS)])
        data=self.fixture();extra=copy.deepcopy(data['observations'][0]);extra['id']='duplicate';data['observations'].append(extra)
        self.assertNotIn('REVENUE',[r['label'] for r in native_reviewed_rows(data,UPPERCASE_NATIVE_STARTING_LABELS)])

    def test_unreviewed_segment_and_similar_label_are_not_selected(self):
        from research.earnings_financial_outline import native_reviewed_rows,UPPERCASE_NATIVE_STARTING_LABELS
        for change in ('method','dimension','label'):
            data=self.fixture()
            for o in data['observations'][:3]:
                if change=='method':o['method']='automatic'
                if change=='dimension':data['contexts'][o['context_id']]['dimensions']=['segment']
                if change=='label':o['support']['source_label']='REVENUE adjusted'
            self.assertNotIn('REVENUE',[r['label'] for r in native_reviewed_rows(data,UPPERCASE_NATIVE_STARTING_LABELS)])

    def test_label_families_are_never_concatenated(self):
        from research.earnings_financial_outline import artifact,NATIVE_STARTING_LABELS
        data=NativeReviewedOutlineTests().fixture();other=self.fixture()
        for o in other['observations']:o['id']='ALT-'+o['id']
        data['observations']+=other['observations'];rows=artifact(data,expanded=True)['rows']
        self.assertLessEqual(len(rows),12)
        # Shared Cash label has duplicate period evidence and is rejected.
        self.assertEqual(rows[0]['label'],NATIVE_STARTING_LABELS[0])
