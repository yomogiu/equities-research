import unittest
from research.earnings_financial_outline import build

class OutlineTests(unittest.TestCase):
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
