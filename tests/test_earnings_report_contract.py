"""Fictitious inventory-backed report coverage and earnings multiples."""
import copy,unittest
from unittest.mock import patch
from research import earnings_report_contract as contract,earnings_valuation_inventory as inventory

class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.price={'id':'P-fake','symbol':'FAKE','currency':'USD','value':'48.00','date':'2041-01-02','source_id':'D001'}
        self.eps={'concept':'us-gaap:EarningsPerShareDiluted','id':'E-fake','symbol':'FAKE','currency':'USD','value':'2.00','period_start':'2040-01-01','period_end':'2040-12-31','source_id':'D001'}
        self.analysis={'sections':{section:{'text':'Disclosed fictional constraint.'} for section,_ in contract.COVERAGE.values()}}
        self.support={'coverage':{key:{'status':'addressed','report_excerpt':'Disclosed fictional constraint.','reason':'Fictional disclosure.','citations':['D001']} for key in contract.COVERAGE},'valuation':{'rows':[{'price_id':'P-fake','eps_id':'E-fake','accounting_basis':'GAAP'}],'gap':'','citations':['D001']}}
        for name,value in [('load_bundle',{}),('_scopes',{'D001':{}})]:
            p=patch.object(contract.evidence,name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch.object(inventory,'build',return_value={'prices':[self.price],'annual_eps':[self.eps]});p.start();self.addCleanup(p.stop)
    def test_historical_quote_date_and_decimal_arithmetic(self):
        self.assertEqual(contract.validate(self.support,self.analysis,'fake')[0]['multiple'],'24.00')
        text='\n'.join(contract.render(self.support,self.analysis,'fake'))
        self.assertIn('2041-01-02',text);self.assertIn('24.00×',text)
    def test_unknown_id_rejected(self):
        self.support['valuation']['rows'][0]['eps_id']='E-invented'
        with self.assertRaisesRegex(ValueError,'unique deterministic'):contract.validate(self.support,self.analysis,'fake')
    def test_incompatible_security_and_currency_rejected(self):
        for key in ('symbol','currency'):
            with self.subTest(key=key),patch.dict(self.eps,{key:'OTHER'}):
                with self.assertRaisesRegex(ValueError,'differ'):contract.validate(self.support,self.analysis,'fake')
    def test_future_reported_eps_rejected(self):
        self.eps['period_end']='2041-12-31'
        with self.assertRaises(ValueError):contract.validate(self.support,self.analysis,'fake')
    def test_nonpositive_eps_is_not_meaningful(self):
        self.eps['value']='-2.00'
        self.assertIsNone(contract.validate(self.support,self.analysis,'fake')[0]['multiple'])
    def test_omitted_obligation_rejected(self):
        del self.support['coverage']['funding_needs']
        with self.assertRaisesRegex(ValueError,'Every shared coverage'):contract.validate(self.support,self.analysis,'fake')
