"""Fictitious source-bound scalars: matching identity, original tokens and arithmetic."""
import copy,unittest
from unittest.mock import patch
from research import earnings_report_contract as contract

class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.quote='FAKE voting ordinary shares USD. Closing price on January 2, 2041: 48.00. Annual diluted EPS for January 1 to December 31, 2040: 2.00.'
        scalar={'source_id':'D001','quote':self.quote,'token':'48.00','security':'FAKE voting','currency':'USD','share_basis':'ordinary share, unsplit'}
        self.row={'price':scalar,'eps':{**scalar,'token':'2.00'},'price_date':'2041-01-02','period_kind':'annual','period_start':'2040-01-01','period_end':'2040-12-31','accounting_basis':'GAAP'}
        self.analysis={'sections':{section:{'text':'Disclosed fictional constraint.'} for section,_ in contract.COVERAGE.values()}}
        self.support={'coverage':{key:{'status':'addressed','report_excerpt':'Disclosed fictional constraint.','reason':'Fictional original disclosure.','citations':['D001']} for key in contract.COVERAGE},'valuation':{'rows':[self.row],'gap':'Forward annual EPS unavailable.','citations':['D001']}}
        for name,value in [('source_slices',[{'spans':[{'text':self.quote}]}]),('load_bundle',{}),('_scopes',{'D001':{}})]:
            p=patch.object(contract.evidence,name,return_value=value);p.start();self.addCleanup(p.stop)
    def test_actual_historical_quote_date_need_not_equal_earnings_date(self):
        self.assertEqual(contract.validate(self.support,self.analysis,'fake')[0]['multiple'],'24.00')
        text='\n'.join(contract.render(self.support,self.analysis,'fake'))
        self.assertIn('2041-01-02',text);self.assertIn('24.00×',text)
    def test_fabricated_quote_or_partial_number_rejected(self):
        for changes in ({'quote':'fabricated 48.00'},{'token':'8.00'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):contract.scalar({**self.row['price'],**changes},'fake')
    def test_incompatible_share_class_currency_or_basis_rejected(self):
        for key in ('security','currency','share_basis'):
            with self.subTest(key=key):
                s=copy.deepcopy(self.support);s['valuation']['rows'][0]['eps'][key]='CAD' if key=='currency' else 'other'
                with self.assertRaisesRegex(ValueError,'must match'):contract.validate(s,self.analysis,'fake')
    def test_quarterly_annualization_and_future_reported_eps_rejected(self):
        for changes in ({'period_start':'2040-10-01'},{'price_date':'2040-06-01'},{'period_kind':'quarter'}):
            with self.subTest(changes=changes):
                s=copy.deepcopy(self.support);s['valuation']['rows'][0].update(changes)
                with self.assertRaises(ValueError):contract.validate(s,self.analysis,'fake')
    def test_nonpositive_eps_is_not_meaningful(self):
        self.quote=self.quote.replace('2.00','0.00');self.row['eps'].update(quote=self.quote,token='0.00');self.row['price']['quote']=self.quote
        with patch.object(contract.evidence,'source_slices',return_value=[{'spans':[{'text':self.quote}]}]):
            self.assertIsNone(contract.validate(self.support,self.analysis,'fake')[0]['multiple'])
    def test_omitted_obligation_rejected(self):
        del self.support['coverage']['funding_needs']
        with self.assertRaisesRegex(ValueError,'Every shared coverage'):contract.validate(self.support,self.analysis,'fake')
