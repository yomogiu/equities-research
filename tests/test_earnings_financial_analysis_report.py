"""Fictional financial-only previews, immutable opt-in and compact metric tables."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_earnings_financial_analysis as facts
from test_earnings_passages import PassageFixture
from research import earnings_financial_analysis_report as report
from research import earnings_file_pipeline as pipeline,earnings_markdown as markdown
from research import earnings_report_template as template,earnings_mixed_runner as base


class FinancialTableTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.config=report.configuration('2026-07-01','2026-09-30')
  rows=[]
  for period,revenue,operating in ((facts.Q3,120000000,24000000),(facts.Q2,100000000,15000000),(facts.PY3,80000000,8000000)):
   rows.extend([facts.spec('revenue',revenue,period),facts.spec('operating_income',operating,period)])
  rows.extend([facts.spec('cash_and_equivalents',50000000,('instant','2026-09-30')),
               facts.spec('cash_and_equivalents',30000000,('instant','2025-12-31')),
               facts.spec('us-gaap:ResearchAndDevelopmentExpense',7000000,label='Research and development'),
               facts.spec('fictional:CapitalExpenditures',-4000000,label='Total')])
  self.bundle=facts.fixture(self.root,rows);self.value=report.compile(self.bundle,self.config)
 def test_compact_core_values_keep_comparisons_and_supporting_inventory(self):
  text=report.preview_markdown(self.value);page=markdown.render(text)
  self.assertIn('120 [^F001]',text);self.assertIn('100 [^F003]',text);self.assertIn('80 [^F005]',text)
  self.assertIn('+20 / +20%',text);self.assertIn('+5 pp',text)
  self.assertNotIn('Dec 31, 2025',text);self.assertNotIn('Other reported periods',text)
  self.assertNotIn('Capital Expenditures · Total',text)
  self.assertIn('2025-12-31',json.dumps(self.value));self.assertIn('-4000000',json.dumps(self.value))
  self.assertEqual(page.count('<table>'),3)
  self.assertLessEqual(sum(line.startswith('| ') for line in text.splitlines()),12)
  collapsed=report.preview_html(text)
  self.assertIn('<summary>Sources and calculation notes</summary>',collapsed)
  self.assertNotIn('subtract(',text);self.assertNotIn('Other financial statement items',text)
  table_lines=[line for line in text.splitlines() if line.startswith('| ')]
  self.assertFalse(any('Filed observation' in x or 'Derived:' in x or 'comparator' in x for x in table_lines))
  self.assertIn('Calculated · GAAP (unaudited) inputs',text)
  self.assertNotIn('class="direction',page)
  self.assertIn('<table>',page)
 def test_income_expense_routing_and_neutral_unknown_concepts(self):
  rendered=report.sections(self.value)
  self.assertIn('Research and development','\n'.join(rendered['earnings']))
  self.assertNotIn('Research and development','\n'.join(rendered['cash']))
  self.assertEqual(rendered['other'],[])
  self.assertIn('fictional:CapitalExpenditures',json.dumps(self.value))
 def test_source_qualifiers_survive_while_generic_segment_labels_gain_metric(self):
  qualified={'metric_id':'net_income','concepts':['us-gaap:NetIncomeLoss'],
             'label':'Net income attributable to owners of parent','dimensions':[]}
  self.assertEqual(report.metric_label(qualified),qualified['label'])
  self.assertEqual(report.metric_label({**qualified,'metric_id':'diluted_eps','label':'Diluted eps'}),'Diluted EPS')
  adjusted={**qualified,'metric_id':'fictional:AdjustedEBITDA','concepts':['fictional:AdjustedEBITDA'],
            'label':'Adjusted EBITDA excluding acquisition costs'}
  self.assertEqual(report.metric_label(adjusted),adjusted['label'])
  segment={**qualified,'metric_id':'capital_expenditure','label':'Space','concepts':['us-gaap:PaymentsToAcquirePropertyPlantAndEquipment'],
           'dimensions':[{'dimension':'us-gaap:StatementBusinessSegmentsAxis','member':'fictional:SpaceMember'}]}
  self.assertEqual(report.metric_label(segment),'Capital expenditure')
  value=report.compile(facts.fixture(self.root,[facts.spec('net_income',3000000,label=qualified['label'])]),self.config)
  facts.one(value,'net_income')['label']=qualified['label']
  rendered=report.preview_markdown(value);page=markdown.render(rendered)
  self.assertIn(qualified['label'],rendered);self.assertIn(qualified['label'],page)
 def test_unavailable_derived_rows_are_notes_without_losing_reported_metrics(self):
  value=copy.deepcopy(self.value);row=copy.deepcopy(value['tables'][0]['rows'][0]);row['label']='Missing derived metric';row['derived']=True
  row['metric_id']='free_cash_flow'
  for cell in row['cells'].values():cell.update(status='missing',value=None,reason='Missing compatible operand')
  value['tables'][0]['rows'].append(row)
  self.assertNotIn('Missing derived metric','\n'.join(report.sections(value)['cash']))
  self.assertIn('Free cash flow','\n'.join(report.sections(value)['cash']))
  self.assertIn('Missing compatible operand',json.dumps(value))
  row['derived']=False
  self.assertNotIn('Missing derived metric','\n'.join(report.sections(value)['cash']))
 def test_core_selection_prefers_quarter_and_labels_ytd_cash_separately(self):
  specs=[facts.spec('revenue',120000000),facts.spec('revenue',330000000,facts.YTD),
         facts.spec('net_income',7000000),facts.spec('net_income',21000000,facts.YTD),
         facts.spec('operating_cash_flow',30000000,facts.YTD),facts.spec('capital_expenditure',10000000,facts.YTD),
         facts.spec('cash_and_equivalents',50000000,('instant','2026-09-30')),
         facts.spec('revenue',40000000,dimensions=[{'dimension':'fictional:SegmentAxis','member':'fictional:NorthMember'}]),
         facts.spec('us-gaap:InterestExpense',6000000,label='Interest expense including finance leases'),
         facts.spec('us-gaap:OtherNonoperatingIncomeExpense',-2000000,label='Other expense, net'),
         facts.spec('us-gaap:InvestmentIncomeInterest',3000000,label='Interest income')]
  value=report.compile(facts.fixture(self.root,specs),self.config);text=report.preview_markdown(value)
  self.assertEqual(text.count('| Revenue |'),1);self.assertNotIn('330 [^',text)
  self.assertNotIn('North',text);self.assertIn('NorthMember',json.dumps(value))
  self.assertIn('### Nine-month cash flow',text);self.assertIn('Jan 1, 2026',text)
  self.assertIn('| Free cash flow |',text);self.assertIn('20 [^',text)
  self.assertIn('Quarter expense detail: Interest expense including finance leases: 6 [^',text)
  self.assertIn('Other expense, net: -2 [^',text);self.assertIn('Interest income: 3 [^',text)
  self.assertNotIn('| Interest expense',text)
  cash='\n'.join(report.sections(value)['cash']);ytd=cash.split('### Point-in-time')[0]
  self.assertNotIn('Prior quarter',ytd);self.assertNotIn('QoQ',ytd)
  self.assertEqual(report.preview_html(text).count('<table>'),4)
 def test_distinct_bases_and_currency_are_not_silently_selected(self):
  specs=[facts.spec('revenue',100000000),facts.spec('revenue',110000000,basis='Adjusted'),
         facts.spec('revenue',70000000,unit={'numerator':['iso4217:EUR'],'denominator':[]})]
  text=report.preview_markdown(report.compile(facts.fixture(self.root,specs),self.config))
  self.assertEqual(text.count('| Revenue |'),3)
  self.assertIn('USD millions · Adjusted',text);self.assertIn('EUR millions · GAAP',text)
 def test_conflicting_current_metric_has_gap_not_zero_or_historical_fallback(self):
  specs=[facts.spec('revenue',100000000),facts.spec('revenue',110000000),facts.spec('revenue',50000000,facts.PY3)]
  value=report.compile(facts.fixture(self.root,specs),self.config);text=report.preview_markdown(value)
  self.assertIn('Current consolidated metrics unavailable: Revenue.',text)
  self.assertNotIn('| Revenue |',text);self.assertNotIn('50 [^',text)
  self.assertIn('Conflicting',json.dumps(value))
 def test_period_preference_and_debt_suppression_are_per_entity_unit_basis(self):
  eur={'numerator':['iso4217:EUR'],'denominator':[]};instant=('instant','2026-09-30')
  specs=[facts.spec('operating_cash_flow',30000000),facts.spec('capital_expenditure',10000000),
         facts.spec('operating_cash_flow',40000000,facts.YTD,unit=eur,entity='SECOND'),
         facts.spec('capital_expenditure',10000000,facts.YTD,unit=eur,entity='SECOND'),
         facts.spec('current_debt',10000000,instant),facts.spec('noncurrent_debt',30000000,instant),
         facts.spec('current_debt',20000000,instant,unit=eur,entity='SECOND')]
  value=report.compile(facts.fixture(self.root,specs),self.config)
  chosen=report.front_rows(value)['cash']
  self.assertEqual({(f,r['entity']) for f,r in chosen if r['metric_id']=='free_cash_flow'},
                   {('quarter','FICTIONAL'),('nine-month','SECOND')})
  self.assertEqual([r['entity'] for _,r in chosen if r['metric_id']=='current_debt'],['SECOND'])
  text=report.preview_markdown(value)
  self.assertIn('SECOND',text);self.assertIn('EUR millions',text)
  self.assertEqual({r['entity'] for t in report.handoff(value)['tables'] for r in t['rows']},{'FICTIONAL','SECOND'})
  self.assertTrue(all(r['entity_scheme']=='test:entity' for t in report.handoff(value)['tables'] for r in t['rows']))
 def test_explicit_debt_disclosures_preserve_source_labels_without_arithmetic_alias(self):
  instant=('instant','2026-09-30')
  specs=[facts.spec('fictional:DebtAndLeasesCurrent',11000000,instant,label='Current debt and finance lease obligations'),
         facts.spec('fictional:DebtAndLeasesNoncurrent',25000000,instant,label='Noncurrent debt and finance lease obligations')]
  value=report.compile(facts.fixture(self.root,specs),self.config);original=copy.deepcopy(value)
  selection=report.display_selection(value,['F001','F002'])
  text=report.preview_markdown(value,selection=selection)
  self.assertIn('Current debt and finance lease obligations · selected disclosure',text)
  self.assertIn('Noncurrent debt and finance lease obligations · selected disclosure',text)
  self.assertIn('11 [^F001]',text);self.assertIn('25 [^F002]',text)
  self.assertNotIn('36 [^',text);self.assertIn('Debt total unavailable',text)
  self.assertIn('| Metric | Unit / basis | Current |',text)
  self.assertNotIn('QoQ Δ / change',text)
  with patch('research.earnings_visual_signals.badges',side_effect=AssertionError('No heuristic badge on computed balances')):
   page=report.preview_html(text)
  self.assertNotIn('class="direction',page)
  self.assertEqual(value,original);self.assertEqual(selection['source_computation_sha256'],base.digest(value))
  output=self.root/'selected-preview'
  with patch('research.earnings_compact_evidence.load_bundle',return_value=facts.fixture(self.root,specs)):
   receipt=report.preview(self.root/'manifest.json',output,quarter_start='2026-07-01',quarter_end='2026-09-30',debt_disclosure_facts=['F001','F002'])
  self.assertIn('display-selection.json',receipt['files'])
  self.assertEqual(base.read(output/'display-selection.json'),selection)
  self.assertIn('Earnings multiples unavailable:',(output/'financial-analysis.md').read_text())
  selection['source_computation_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'differs from frozen'):report.preview_markdown(value,selection=selection)
 def test_debt_disclosure_selection_refuses_unknown_duration_segment_missing_or_conflict(self):
  instant=('instant','2026-09-30')
  specs=[facts.spec('fictional:Obligation',10),facts.spec('fictional:Obligation',10,instant,
          dimensions=[{'dimension':'fictional:SegmentAxis','member':'fictional:EastMember'}]),
         facts.spec('fictional:MissingBalance',10,('instant','2025-12-31')),
         facts.spec('fictional:Conflict',10,instant),facts.spec('fictional:Conflict',20,instant)]
  value=report.compile(facts.fixture(self.root,specs),self.config)
  for ids in (['F001'],['F002'],['F003'],['F004'],['unknown'],['F001','F001']):
   with self.subTest(ids=ids),self.assertRaises(ValueError):report.display_selection(value,ids)
 def test_caller_basis_assumption_and_negative_nonzero_amount_are_retained(self):
  self.assertEqual(report.basis_label({'basis':'GAAP','basis_origin':'caller_declared','derived':True}),
                   'Calculated · GAAP inputs (assumed)')
  self.assertEqual(report.number('-120',report.Decimal(1000000),places=2),'-0.00012')
 def test_computed_values_ignore_model_row_and_format_overrides(self):
  bundle={**self.bundle,'financial_analysis':self.value,'financial_analysis_config':self.config}
  actual=template.financial_sections({'rows':[]},bundle,{'rows':{'fake':{'label':'Model invented margin'}}})
  self.assertIn('120 [^F001]','\n'.join(actual['demand']))
  self.assertNotIn('Model invented','\n'.join(sum(actual.values(),[])))
  mutated=copy.deepcopy(bundle);mutated['financial_analysis']['tables'][0]['rows'][0]['cells']['current']['value']='999999999'
  with self.assertRaisesRegex(ValueError,'differs from source'):template.financial_sections({},mutated,{})
 def test_handoff_is_read_only_and_does_not_repeat_original_inventory(self):
  handoff=report.handoff(self.value)
  self.assertTrue(handoff['read_only']);self.assertEqual(handoff['source_computation_sha256'],base.digest(self.value))
  self.assertNotIn('observations',handoff);self.assertNotIn('contexts',handoff)
  self.assertNotIn('fictional:CapitalExpenditures',json.dumps(handoff))
  chosen={id(r) for rows in report.front_rows(self.value).values() for _,r in rows}
  original_rows=[r for table in self.value['tables'] for r in table['rows'] if id(r) in chosen]
  copied_rows=[r for table in handoff['tables'] for r in table['rows']]
  self.assertEqual([(r['derived'],r['basis_origin']) for r in copied_rows],[(r['derived'],r['basis_origin']) for r in original_rows])
 def test_config_requires_exact_dates_version_and_bound_assumptions(self):
  self.assertEqual(report.validate_configuration(self.config),self.config)
  for key,value in (('version','unknown'),('as_of','2026-10-01'),('capex_conventions',{'F1':'guess'}),('accounting_bases',{'F1':''})):
   with self.subTest(key=key),self.assertRaises(ValueError):report.validate_configuration({**self.config,key:value})
  with self.assertRaises(ValueError):report.configuration('2026-01-01','2026-09-30')


class FinancialOptInTests(PassageFixture,unittest.TestCase):
 def test_standalone_preview_uses_only_frozen_manifest_and_preserves_outputs(self):
  root=self.root/'preview'
  with patch.object(pipeline,'_job',side_effect=AssertionError('No model role allowed')):
   receipt=report.preview(self.root/'evidence/manifest.json',root,quarter_start='2026-07-01',quarter_end='2026-09-30')
  self.assertEqual(receipt['model_calls'],0)
  self.assertEqual(set(receipt['files']),{'financial-analysis-config.json','financial-analysis.json','financial-analysis.md','financial-analysis.html'})
  self.assertIn('Current consolidated metrics unavailable',(root/'financial-analysis.html').read_text())
  self.assertNotIn('<table>',(root/'financial-analysis.html').read_text())
  (root/'financial-analysis.md').write_text('retained existing output')
  with self.assertRaisesRegex(ValueError,'choose a new'):report.preview(self.root/'evidence/manifest.json',root,quarter_start='2026-07-01',quarter_end='2026-09-30')
  self.assertEqual((root/'financial-analysis.md').read_text(),'retained existing output')
 def test_optional_dated_earnings_snapshot_is_separate_and_never_inferred(self):
  import test_earnings_earnings_multiples as multiple_fixtures
  snapshot=self.root/'supplied.json';inputs=multiple_fixtures.fixture()
  inputs['security']['issuer']={'entity':'FICTIONAL','entity_scheme':'test:entity'}
  snapshot.write_text(json.dumps(inputs))
  output=self.root/'with-multiples'
  current_bundle=facts.fixture(self.root,[facts.spec('revenue',100000000)])
  with patch('research.earnings_compact_evidence.load_bundle',return_value=current_bundle):
   receipt=report.preview(self.root/'evidence/manifest.json',output,quarter_start='2026-07-01',quarter_end='2026-09-30',
                          earnings_snapshot=snapshot,valuation_as_of='2026-10-20')
  text=(output/'financial-analysis.md').read_text();result=base.read(output/'earnings-multiples.json')
  self.assertIn('20×',text);self.assertIn('15×',text);self.assertIn('forecast dated 2026-10-19',text)
  self.assertIn('not independently verified',text);self.assertIn('https://example.invalid/',text)
  self.assertIn('FICTIONAL.ordinary',text);self.assertIn('1 ordinary shares per security',text)
  self.assertIn('fictional-split-basis-2026',text)
  self.assertEqual(result['snapshot_binding']['sha256'],base.sha(snapshot))
  self.assertEqual(len(receipt['files']),5)
  for kwargs in ({'earnings_snapshot':snapshot},{'valuation_as_of':'2026-10-20'}):
   with self.subTest(kwargs=kwargs),self.assertRaisesRegex(ValueError,'required together'):
    report.preview(self.root/'evidence/manifest.json',self.root/'bad',quarter_start='2026-07-01',quarter_end='2026-09-30',**kwargs)
  self.assertFalse((self.root/'bad').exists())
 def test_optional_multiples_must_match_the_financial_issuer_explicitly(self):
  import test_earnings_earnings_multiples as multiple_fixtures
  from research import earnings_earnings_multiples as multiples
  value=report.compile(facts.fixture(self.root,[facts.spec('revenue',100000000)]),report.configuration('2026-07-01','2026-09-30'))
  snapshot=multiple_fixtures.fixture()
  with self.assertRaisesRegex(ValueError,'explicit security.issuer'):report.validate_multiple_issuer(value,multiples.build(snapshot,as_of='2026-10-20'))
  for entity,scheme in [('OTHER','test:entity'),('FICTIONAL','different:scheme')]:
   snapshot['security']['issuer']={'entity':entity,'entity_scheme':scheme}
   with self.assertRaisesRegex(ValueError,'must match'):report.validate_multiple_issuer(value,multiples.build(snapshot,as_of='2026-10-20'))
  snapshot['security']['issuer']={'entity':'FICTIONAL','entity_scheme':'test:entity'}
  report.validate_multiple_issuer(value,multiples.build(snapshot,as_of='2026-10-20'))
 def test_invalid_optional_snapshot_records_render_explicit_gaps_without_crashing(self):
  import test_earnings_earnings_multiples as multiple_fixtures
  from research import earnings_earnings_multiples as multiples
  snapshot=multiple_fixtures.fixture();snapshot['current_eps']['period']='invalid'
  snapshot['forward_eps']['forecast_as_of']=20261020
  value=multiples.build(snapshot,as_of='2026-10-20')
  rendered='\n'.join(report.multiples_lines(value))
  self.assertIn('Explicit complete EPS period required',rendered)
  self.assertIn('Explicit ISO calendar date required',rendered)
  self.assertIn('USD per ordinary share',rendered)
 def test_protocol_absent_by_default_and_opt_in_recomputes_exact_source_artifact(self):
  writing=self.root/'writing.md';writing.write_text('Fictional writing guide')
  old=pipeline.initialize(self.casepath,self.root/'legacy',writing)
  self.assertNotIn('financial_analysis',old);self.assertFalse((self.root/'legacy/financial-analysis.json').exists())
  config=report.configuration('2026-07-01','2026-09-30');root=self.root/'opt-in'
  protocol=pipeline.initialize(self.casepath,root,writing,financial_analysis=config)
  self.assertEqual(protocol['financial_analysis'],config)
  frozen,bundle,_=pipeline.load(root)
  self.assertEqual(bundle['financial_analysis'],report.compile(bundle,config))
  self.assertEqual(protocol['financial_analysis_sha256'],base.sha(root/'financial-analysis.json'))
  body=base.read(root/'financial-analysis.json');body['as_of']='2025-09-30';(root/'financial-analysis.json').write_text(json.dumps(body))
  with self.assertRaisesRegex(ValueError,'computed financial analysis changed'):pipeline.load(root)
  protocol['financial_analysis_sha256']=base.sha(root/'financial-analysis.json');(root/'protocol.json').write_text(json.dumps(protocol))
  with self.assertRaisesRegex(ValueError,'differs from source'):pipeline.load(root)
 def test_cannot_retrofit_legacy_preparations_or_model_selected_mode(self):
  writing=self.root/'writing.md';writing.write_text('Fictional writing guide');config=report.configuration('2026-07-01','2026-09-30')
  for kwargs in ({'preparation':self.root/'unused.json'},{'financial_mode':'model-original-selector-v1'},{'report_template':None}):
   with self.subTest(kwargs=kwargs),self.assertRaisesRegex(ValueError,'new deterministic'):pipeline.initialize(self.casepath,self.root/'reject',writing,financial_analysis=config,**kwargs)
  self.assertFalse((self.root/'reject').exists())
 def test_legacy_prompt_unchanged_and_opt_in_tables_are_primary(self):
  self.assertEqual(template.instructions(),template.INSTRUCTIONS)
  instructions=template.instructions(financial_analysis=True)
  self.assertIn('financial analysis tables are primary',instructions)
  self.assertIn('No financial model prose is required',instructions)
  self.assertNotIn('Tables\nsupport the prose',instructions)
 def test_cli_produces_financial_only_preview_with_explicit_dates(self):
  out=self.root/'cli-preview'
  command=[sys.executable,'-m','research.earnings_financial_analysis_report','--manifest',str(self.root/'evidence/manifest.json'),
           '--quarter-start','2026-07-01','--quarter-end','2026-09-30','--output',str(out)]
  receipt=json.loads(subprocess.check_output(command,text=True))
  self.assertEqual(receipt['model_calls'],0);self.assertTrue((out/'financial-analysis.html').is_file())

if __name__=='__main__':unittest.main()
