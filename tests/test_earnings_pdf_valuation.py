"""Fictional original-statement, class and currency qualification regressions."""
import copy
import unittest
from unittest.mock import patch
from research import earnings_pdf_valuation as pdf


TEXT='''FORM 10-K
Class A ordinary shares       FAKE       Fictional Exchange
Accounting principles generally accepted in the United States.
[Page 1]
Consolidated Income Statements
(In thousands of U.S. dollars, except share and per share amounts)
For the Years Ended August 31, 2040, 2039 and 2038
                      2040       2039      2038
Revenue                100         90        80
Weighted average Class A ordinary shares:
Basic                  100         99        98
Diluted                110        109       108
Earnings per Class A ordinary share:
Basic                 1.10       1.00      0.90
Diluted               1.00       0.90      0.80
'''
SOURCE={'document_id':'fictional','sha256':'a'*64}
PRICES=[{'id':'P-fictional','symbol':'FAKE','currency':'USD','date':'2040-10-28',
         'value':'20.00','source_id':'transcript-source'}]


class PdfValuationTests(unittest.TestCase):
    def test_annual_eps_uses_original_diluted_earnings_not_share_counts(self):
        rows=pdf.annual_eps(TEXT,SOURCE,PRICES)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row['value'],'1.00');self.assertEqual(row['period_end'],'2040-08-31')
        self.assertIsNone(row['period_start']);self.assertEqual(row['share_basis'],'Class A ordinary')
        self.assertEqual(row['text'],TEXT[row['start']:row['end']])
        self.assertEqual(row['security_support']['text'],TEXT[row['security_support']['start']:row['security_support']['end']])
        self.assertEqual(pdf.unique_pair({'prices':PRICES,'annual_eps':rows})['eps_id'],row['id'])

    def test_quarter_currency_security_and_basis_ambiguities_cannot_qualify(self):
        for text in [TEXT.replace('Years Ended','Three Months Ended'),
                     TEXT.replace('U.S. dollars','Canadian dollars'),
                     TEXT.replace('ordinary shares       FAKE','ordinary shares       OTHER'),
                     TEXT.replace('Class A ordinary shares       FAKE','Class B ordinary shares       FAKE'),
                     TEXT.replace('Accounting principles generally accepted in the United States.','IFRS basis.'),
                     TEXT.replace('Consolidated Income Statements','Selected Quarterly Data'),
                     TEXT.replace('Class A ordinary shares','American Depositary Shares')]:
            self.assertEqual(pdf.annual_eps(text,SOURCE,PRICES),[])

    def test_multiple_candidates_negative_eps_and_future_period_are_not_automatic(self):
        rows=pdf.annual_eps(TEXT,SOURCE,PRICES)
        self.assertIsNone(pdf.unique_pair({'prices':PRICES,'annual_eps':rows+rows}))
        self.assertIsNone(pdf.unique_pair({'prices':PRICES,'annual_eps':[{**rows[0],'value':'-1.00'}]}))
        self.assertIsNone(pdf.unique_pair({'prices':PRICES,'annual_eps':[{**rows[0],'period_end':'2041-08-31'}]}))

    def test_completion_changes_only_valuation_and_obsolete_supplemental_gaps(self):
        rows=pdf.annual_eps(TEXT,SOURCE,PRICES);available={'prices':PRICES,'annual_eps':rows}
        value={'analysis':{'qa':[{'assessment':'Unchanged original Q&A.'}],
                 'report_support':{'valuation':{'rows':[],'gap':'Fictional indexing gap.','citations':['D1']}}},
               'financial_selection':{'gaps':[{'metric':'annual_eps','reason':'Fictional missing E ID.','citations':['D1']}]}}
        before=copy.deepcopy(value)
        with patch('research.earnings_valuation_inventory.build',return_value=available):
            completed,changes=pdf.complete(value,{})
        self.assertEqual(value,before);self.assertEqual(completed['analysis']['qa'],before['analysis']['qa'])
        self.assertEqual(completed['analysis']['report_support']['valuation']['gap'],'')
        self.assertEqual(len(completed['analysis']['report_support']['valuation']['rows']),1)
        self.assertTrue(changes)
        self.assertIn('Available',completed['financial_selection']['gaps'][0]['reason'])
        self.assertEqual({g['metric'] for g in completed['financial_selection']['gaps']},{'annual_eps','price'})


if __name__=='__main__':unittest.main()
