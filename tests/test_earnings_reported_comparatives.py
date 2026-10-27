"""Fictional reported EPS prose: exact spans, date/unit anchors, no inferred EPS."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research import earnings_reported_comparatives as comparative

TEXT = ('Fictional Company Reports Results for the Second Quarter Ended June 30, 2040\n'
        'Net income for the second quarter was $120.0 million, or $2.00 per\n'
        'diluted share, compared to net income of $90.0 million, or $1.50 per diluted share, '
        'for the first quarter of 2040 and other reported information.\n')


class ReportedComparativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        def row(metric,unit,value):
            return {'metric_id':metric,'dimensions':[],'basis':'GAAP','entity':'FAKE','entity_scheme':'fictional',
                    'unit':unit,'cells':{'current':{'status':'available','value':value,'period':['duration','2040-04-01','2040-06-30'],'fact_ids':['F001']},
                                        'prior_quarter':{'status':'missing'}},'changes':{},'period_observations':[]}
        self.value={'current_period':['duration','2040-04-01','2040-06-30'],'tables':[{'period_family':'quarter','rows':[
            row('diluted_eps',{'numerator':['iso4217:USD'],'denominator':['xbrli:shares']},'2.00'),
            row('net_income',{'numerator':['iso4217:USD'],'denominator':[]},'120040000')]}]}

    def bundle(self,text=TEXT):
        p=self.root/'fictional-release.txt';p.write_text(text);digest=hashlib.sha256(text.encode()).hexdigest()
        source={'path':str(p),'sha256':digest,'document_id':'fake-release','representation':'text','kind':'release'}
        return {'manifest':{'sources':[source]},'documents':{'chunks':[{**source,'id':'D001','start':0,'end':len(text),'span_sha256':digest}]}}

    def test_reported_eps_is_source_bound_and_calculated_without_mutating_inputs(self):
        bundle=self.bundle();original=deepcopy(self.value)
        result=comparative.supplement(self.value,bundle);row=result['tables'][0]['rows'][0]
        prior=row['cells']['prior_quarter'];self.assertEqual(prior['value'],'1.50')
        self.assertEqual(prior['period'],['duration','2040-01-01','2040-03-31'])
        self.assertEqual(prior['fact_ids'],['D001'])
        self.assertEqual(row['changes']['qoq']['absolute'],'0.50')
        proof=prior['calculation'];snippet=TEXT[proof['start']:proof['end']]
        self.assertIn('$1.50',snippet)
        self.assertEqual(hashlib.sha256(snippet.encode()).hexdigest(),proof['span_sha256'])
        self.assertEqual(self.value,original)

    def test_mismatched_dates_values_adjusted_metrics_or_ambiguous_inputs_do_not_fill(self):
        variants=[TEXT.replace('$2.00','$2.01'),TEXT.replace('$120.0','$121.0'),
                  TEXT.replace('first quarter of 2040','first quarter of 2039'),
                  TEXT.replace('Net income','Adjusted net income'),
                  TEXT.replace('June 30','March 31'),TEXT.replace('first quarter','third quarter'),
                  TEXT+TEXT.replace('$1.50','$1.75')]
        for text in variants:
            with self.subTest(text=text):
                result=comparative.supplement(self.value,self.bundle(text))
                self.assertEqual(result,self.value)

    def test_unsupported_currency_fiscal_boundaries_and_existing_values_are_preserved(self):
        bundle=self.bundle()
        for alter in ('currency','period','prior'):
            value=deepcopy(self.value)
            if alter=='currency':value['tables'][0]['rows'][0]['unit']['numerator']=['iso4217:CAD']
            elif alter=='period':value['current_period']=['duration','2040-02-01','2040-04-30']
            else:value['tables'][0]['rows'][0]['cells']['prior_quarter']={'status':'available','value':'1.75'}
            self.assertEqual(comparative.supplement(value,bundle),value)

    def test_changed_source_or_scope_cannot_supply_a_comparative(self):
        bundle=self.bundle();Path(bundle['manifest']['sources'][0]['path']).write_text(TEXT+'tamper')
        with self.assertRaisesRegex(ValueError,'source changed'):comparative.supplement(self.value,bundle)
        bundle=self.bundle();bundle['documents']['chunks'][0]['span_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'scope changed'):comparative.supplement(self.value,bundle)


if __name__=='__main__':unittest.main()
