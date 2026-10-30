"""Fictional EPS qualification, rounding, period and routing regressions."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import hashlib
from research import earnings_eps_contract as eps,earnings_valuation_inventory as valuation
from research import earnings_runtime_common as storage

SOURCE={'document_id':'fictional','sha256':'a'*64}
HEADER='''[Page 1]
Fictional financial statements. The consolidated financial statements are prepared in accordance with IFRS.
(In Thousands of New Taiwan Dollars, Unless Stated Otherwise)
27. EARNINGS PER SHARE
                    For the Three Months Ended          For the Six Months Ended
                              June 30                            June 30
                         2040          2039                 2040          2039
Basic earnings per share   $ 2.01       $ 1.01                $ 4.01       $ 2.01
Diluted earnings per share $ 2.00       $ 1.00                $ 4.00       $ 2.00
'''
NOTE='''
Earnings used in the computation of
 basic and diluted earnings per share    $ 200       $ 100        $ 400       $ 200
The weighted average number of ordinary shares outstanding (in thousand shares) was as follows:
                    For the Three Months Ended          For the Six Months Ended
                              June 30                            June 30
                         2040          2039                 2040          2039
Weighted average number of ordinary
 shares used in the computation of
 diluted earnings per share                100         100          100         100
'''

class EPSContractTests(unittest.TestCase):
 def records(self,text=HEADER+NOTE):return eps.pdf_records(text,SOURCE,'fictional-issuer')
 def row(self,**changes):
  return {'id':'EPS-current','document_id':'fictional','issuer':'fictional','value':'2.00','currency':'USD','period_start':None,'period_end':'2040-06-30','months':3,'accounting_basis':'GAAP','share_class':'common','dilution':'diluted','status':'qualified','reconciliation':{'status':'unavailable'},**changes}
 def operand(self,row,role,value,rounding):return {**row,'role':role,'value':value,'rounding':rounding}
 def test_wrapped_pdf_headers_keep_quarter_half_basic_and_diluted_separate(self):
  rows=self.records();self.assertEqual(len(rows),8)
  diluted=[r for r in rows if r['dilution']=='diluted'];self.assertEqual([r['months'] for r in diluted],[3,3,6,6])
  self.assertEqual([r['value'] for r in diluted],['2.00','1.00','4.00','2.00'])
  self.assertTrue(all(r['currency']=='TWD' and r['status']=='qualified' and r['reconciliation']['status']=='pass' for r in diluted))
  for row in rows:
   v=row['support']['value'];self.assertEqual((HEADER+NOTE)[v['start']:v['end']],v['text']);self.assertEqual(v['sha256'],hashlib.sha256(v['text'].encode()).hexdigest())
 def test_reconciliation_rejects_unmatched_numerator_currency(self):
  rows=self.records((HEADER+NOTE).replace('In Thousands of New Taiwan Dollars, Unless Stated Otherwise','In Thousands of EUR, Unless Stated Otherwise').replace('27. EARNINGS PER SHARE','(In Thousands of New Taiwan Dollars)\n27. EARNINGS PER SHARE'))
  self.assertTrue(all(r['reconciliation']['status']=='unavailable' for r in rows if r['dilution']=='diluted'))
 def test_source_precision_not_fixed_percent_tolerance(self):
  row=self.row(value='1.23');n=self.operand(row,'eps_numerator','123400000','50000');s=self.operand(row,'weighted_average_diluted_shares','100000000','500')
  self.assertEqual(eps.reconcile(row,n,s)['status'],'pass')
  self.assertEqual(eps.reconcile({**row,'value':'1.22'},n,s)['status'],'conflict')
  self.assertEqual(eps.reconcile(row,None,s)['status'],'unavailable')
 def test_reconciliation_rejects_closing_shares_and_mismatched_basis(self):
  row=self.row();n=self.operand(row,'eps_numerator','200','0.5');s=self.operand(row,'weighted_average_diluted_shares','100','0.5')
  for key,value in [('currency','EUR'),('months',6),('accounting_basis','non-GAAP'),('share_class','preferred'),('issuer','other')]:
   self.assertEqual(eps.reconcile(row,n,{**s,key:value})['status'],'unavailable')
  with self.assertRaisesRegex(ValueError,'weighted-average'):eps.reconcile(row,n,{**s,'role':'closing_shares'})
  with self.assertRaisesRegex(ValueError,'explicitly diluted'):eps.reconcile({**row,'dilution':'basic'},n,s)
 def test_reported_eps_is_preserved_when_reconciliation_conflicts(self):
  rows=self.records((HEADER+NOTE).replace('share $ 2.00','share $ 2.05'))
  r=next(r for r in rows if r['dilution']=='diluted' and r['months']==3 and r['period_end']=='2040-06-30')
  self.assertEqual(r['value'],'2.05');self.assertEqual(r['status'],'conflict');self.assertEqual(r['reconciliation']['calculated'],'2')
  rendered='\n'.join(eps.render({'records':[r],'comparisons':[],'gap':None}))
  self.assertIn('2.05',rendered);self.assertIn('not replaced',rendered)
 def test_unknown_currency_basis_class_or_period_stays_local_gap(self):
  for text in [HEADER.replace('New Taiwan Dollars','Unknown Dollars'),HEADER.replace('in accordance with IFRS','under an unspecified framework'),HEADER+'\nClass A and Class B ordinary shares',HEADER.replace('2040          2039','2039          2040')]:
   rows=self.records(text)
   self.assertFalse(any(r['status']=='qualified' for r in rows))
 def test_adjusted_and_continuing_operations_rows_are_not_promoted_to_total_eps(self):
  for label in ['Adjusted diluted earnings per share','Diluted earnings per share from continuing operations']:
   rows=self.records(HEADER.replace('Diluted earnings per share',label))
   self.assertFalse(any(r['dilution']=='diluted' for r in rows))
 def test_like_for_like_comparisons_and_nonpositive_prior(self):
  row=self.row();prior=self.row(id='EPS-prior',period_end='2039-06-30',value='1.00')
  self.assertEqual(eps.comparison(row,prior,'yoy')['percent'],'100')
  self.assertEqual(eps.comparison(row,{**prior,'value':'-1.00'},'yoy')['status'],'not_meaningful')
  for changes in [{'months':6},{'currency':'EUR'},{'dilution':'basic'},{'document_id':'different-split-basis'},{'reconciliation':{'status':'conflict'}}]:
   self.assertEqual(eps.comparison(row,{**prior,**changes},'yoy')['status'],'unavailable')
  self.assertEqual(eps.comparison(self.row(months=6),self.row(period_end='2040-03-31',months=6),'qoq')['status'],'unavailable')
 def test_annual_valuation_never_accepts_basic_interim_or_continuing_only_eps(self):
  annual={'concept':'us-gaap:EarningsPerShareDiluted','period_start':'2040-01-01','period_end':'2040-12-31'}
  self.assertTrue(eps.annual_eligible(annual))
  for changed in [{**annual,'period_end':'2040-06-30'},{**annual,'concept':'us-gaap:EarningsPerShareBasic'},{**annual,'concept':'us-gaap:IncomeLossFromContinuingOperationsPerDilutedShare'}]:self.assertFalse(eps.annual_eligible(changed))
  self.assertFalse(eps.annual_eligible({'kind':'annual_guidance','basis':'GAAP','months':12,'dilution':'basic'}))
 def test_forward_eps_requires_explicit_dilution(self):
  text='Earnings Call: Q2 2040\nAugust 6, 2040\nFor the full year of 2040, we expect non-GAAP diluted earnings per share of $2.00 to $3.00.'
  quote={'document_id':'fictional','currency':'USD','symbol':'FAKE'}
  result=valuation.guidance_eps(text,SOURCE,[quote]);self.assertEqual(len(result),1);self.assertEqual(result[0]['months'],12)
  unspecified=valuation.guidance_eps(text.replace('diluted ',''),SOURCE,[quote]);self.assertEqual(unspecified[0]['dilution'],'unspecified');self.assertFalse(eps.annual_eligible(unspecified[0]))
 def test_eps_selection_cannot_relabel_basic_fact(self):
  row={**self.row(dilution='basic'),'fact_ids':['F1']};selection={'rows':[{'metric':'diluted_eps','fact_ids':['F1']}]}
  with self.assertRaisesRegex(ValueError,'qualified'):eps.validate_selection(selection,{'records':[row]})
 def test_conflicting_duplicate_source_is_not_hidden_by_a_matching_row(self):
  with TemporaryDirectory() as temporary:
   root=Path(temporary);raw=root/'source.pdf';raw.write_bytes(b'%PDF fictional');text=root/'source.txt';text.write_text(HEADER+NOTE+'\n'+HEADER.replace('share $ 2.00','share $ 2.05'))
   sources=[{**SOURCE,'kind':'filing','representation':rep,'path':str(p),'sha256':storage.sha(p)} for rep,p in [('raw',raw),('text',text)]]
   bundle={'manifest':{'sources':sources},'financial':{'observations':[]},'valuation_inventory':{'prices':[],'annual_eps':[]}}
   result=eps.build(bundle);current=[r for r in result['records'] if r['months']==3 and r['period_end']=='2040-06-30' and r['dilution']=='diluted']
   self.assertTrue(current);self.assertTrue(all(r['status']=='conflict' for r in current))
   self.assertFalse(any(c.get('current_id') in {r['id'] for r in current} for c in result['comparisons']))
   raw.write_bytes(b'%PDF changed')
   with self.assertRaisesRegex(ValueError,'source changed'):eps.build(bundle)

if __name__=='__main__':unittest.main()
