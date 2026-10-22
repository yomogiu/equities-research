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
 def test_compact_values_comparators_pp_and_old_snapshot_are_visible(self):
  text=report.preview_markdown(self.value);page=markdown.render(text)
  self.assertIn('120 [^F001]',text);self.assertIn('100 [^F003]',text);self.assertIn('80 [^F005]',text)
  self.assertIn('+20 / +20%',text);self.assertIn('+5 pp',text)
  self.assertIn('Dec 31, 2025',text);self.assertIn('Other reported periods',text)
  self.assertIn('Capital Expenditures · Total',text);self.assertIn('-4 [^F010]',text)
  table_lines=[line for line in text.splitlines() if line.startswith('| ')]
  self.assertFalse(any('Filed observation' in x or 'Derived:' in x or 'comparator' in x for x in table_lines))
  self.assertIn('Calculated · GAAP (unaudited) inputs',text)
  self.assertNotIn('class="direction',page)
  self.assertIn('<table>',page)
 def test_income_expense_routing_and_neutral_unknown_concepts(self):
  rendered=report.sections(self.value)
  self.assertIn('Research and development','\n'.join(rendered['earnings']))
  self.assertNotIn('Research and development','\n'.join(rendered['cash']))
  self.assertIn('Capital Expenditures · Total','\n'.join(rendered['other']))
 def test_source_qualifiers_survive_while_generic_segment_labels_gain_metric(self):
  qualified={'metric_id':'net_income','concepts':['us-gaap:NetIncomeLoss'],
             'label':'Net income attributable to owners of parent','dimensions':[]}
  self.assertEqual(report.metric_label(qualified),qualified['label'])
  adjusted={**qualified,'metric_id':'fictional:AdjustedEBITDA','concepts':['fictional:AdjustedEBITDA'],
            'label':'Adjusted EBITDA excluding acquisition costs'}
  self.assertEqual(report.metric_label(adjusted),adjusted['label'])
  segment={**qualified,'metric_id':'capital_expenditure','label':'Space','concepts':['us-gaap:PaymentsToAcquirePropertyPlantAndEquipment'],
           'dimensions':[{'dimension':'us-gaap:StatementBusinessSegmentsAxis','member':'fictional:SpaceMember'}]}
  self.assertEqual(report.metric_label(segment),'Capital expenditure')
  rows=self.value['tables'][0]['rows'];rows[0].update(qualified);rows[1].update(adjusted)
  rendered=report.preview_markdown(self.value);page=markdown.render(rendered)
  self.assertIn(qualified['label'],rendered);self.assertIn(adjusted['label'],page)
 def test_unavailable_derived_rows_are_notes_without_losing_reported_metrics(self):
  value=copy.deepcopy(self.value);row=copy.deepcopy(value['tables'][0]['rows'][0]);row['label']='Missing derived metric';row['derived']=True
  row['metric_id']='free_cash_flow'
  for cell in row['cells'].values():cell.update(status='missing',value=None,reason='Missing compatible operand')
  value['tables'][0]['rows'].append(row)
  self.assertNotIn('Missing derived metric','\n'.join(report.sections(value)['cash']))
  self.assertIn('Missing compatible operand','\n'.join(report.notes(value)))
  row['derived']=False
  self.assertIn('Missing derived metric','\n'.join(report.sections(value)['cash']))
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
  original_rows=[r for table in self.value['tables'] for r in table['rows']]
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
  self.assertIn('<table>',(root/'financial-analysis.html').read_text())
  (root/'financial-analysis.md').write_text('retained existing output')
  with self.assertRaisesRegex(ValueError,'choose a new'):report.preview(self.root/'evidence/manifest.json',root,quarter_start='2026-07-01',quarter_end='2026-09-30')
  self.assertEqual((root/'financial-analysis.md').read_text(),'retained existing output')
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
