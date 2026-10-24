"""Entirely fictional exact-source financial arithmetic and refusal fixtures."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from research import earnings_financial_analysis as analysis

Q3 = ('duration', '2026-07-01', '2026-09-30')
Q2 = ('duration', '2026-04-01', '2026-06-30')
PY3 = ('duration', '2025-07-01', '2025-09-30')
H1 = ('duration', '2026-01-01', '2026-06-30')
YTD = ('duration', '2026-01-01', '2026-09-30')
CONCEPT = {v:k for k,v in analysis.CONCEPTS.items() if k.startswith('us-gaap:')}
CONCEPT['revenue'] = 'us-gaap:Revenues'


def spec(metric, value, period=Q3, **kw):
    return {'concept': CONCEPT.get(metric, metric), 'value': str(value), 'period': period, **kw}


def fixture(root, specs):
    """Bound numeric and label spans mimic qualified reviewed table output."""
    raw = ''; observations = []; contexts = {}; units = {}
    path = root / 'fictional-source.html'
    for i, row in enumerate(specs):
        fid = 'F%03d' % (i+1)
        label = row.get('label', row['concept'].split(':')[-1])
        snippet = '<tr><td>'+label+'</td><td>'+row['value']+'</td></tr>'
        start = len(raw); raw += snippet
        ls = start+len('<tr><td>'); le = ls+len(label)
        ns = le+len('</td><td>'); ne = ns+len(row['value'])
        cid, uid = 'C'+fid, 'U'+fid
        period = row['period']
        contexts[cid] = {'id': cid, 'entity': row.get('entity','FICTIONAL'), 'entity_scheme': 'test:entity',
                         'dimensions': row.get('dimensions', []), 'instant': period[1] if period[0]=='instant' else None,
                         'start_date': period[1] if period[0]=='duration' else None,
                         'end_date': period[2] if period[0]=='duration' else None}
        units[uid] = {'id': uid, **row.get('unit', {'numerator':['iso4217:USD'],'denominator':[]})}
        sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
        observations.append({'id':fid,'observation_id':'obs'+fid,'concept':row['concept'], 'value': row['value'],
            'context_id':cid,'unit_id':uid,'nil':row.get('nil',False),'status':row.get('status','extracted'),
            'method':'reviewed_html_table','accounting_basis':row.get('basis','GAAP (unaudited)'),
            'source_path':str(path),'source_document_id':'fictional-financials',
            'support':{'start':ns,'end':ne,'raw_span_sha256':sha(row['value']),
                       'source_label':label,'label':{'start':ls,'end':le,'raw_span_sha256':sha(label)},
                       'table_row':{'start':start,'end':len(raw),'raw_span_sha256':sha(snippet)}}})
    path.write_text(raw)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    for obs in observations: obs['source_sha256'] = digest
    return {'manifest':{'sources':[{'path':str(path),'sha256':digest,'document_id':'fictional-financials'}]},
            'financial':{'observations':observations,'contexts':contexts,'units':units,'gaps':[]}}


def rows(result, metric, family='quarter'):
    return [r for t in result['tables'] if t['period_family']==family for r in t['rows'] if r['metric_id']==metric]


def one(result, metric, family='quarter'):
    found = rows(result,metric,family)
    assert len(found)==1, (metric,len(found))
    return found[0]


class FinancialAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def build(self, specs, **kwargs):
        return analysis.build(fixture(self.root,specs),current_period=Q3,**kwargs)

    def test_full_inventory_tables_growth_margins_and_lineage(self):
        specs=[]
        for p, rev, cost, op, net, ocf, capex in [(Q3,120,72,24,18,36,12),(Q2,100,65,15,10,20,8),(PY3,80,56,8,4,12,4)]:
            specs += [spec(k,v,p) for k,v in [('revenue',rev),('cost_of_revenue',cost),('operating_income',op),('net_income',net),('operating_cash_flow',ocf),('capital_expenditure',capex)]]
        bundle=fixture(self.root,specs); original=copy.deepcopy(bundle)
        result=analysis.build(bundle,current_period=Q3)
        self.assertEqual(result['observations'],original['financial']['observations'])
        self.assertEqual(bundle,original)
        rev=one(result,'revenue'); self.assertEqual(rev['changes']['qoq']['percent'],'20.0')
        self.assertEqual(rev['changes']['yoy']['percent'],'50.0')
        self.assertEqual(one(result,'gross_profit')['cells']['current']['value'],'48')
        self.assertEqual(one(result,'gross_margin')['cells']['current']['value'],'40.0')
        self.assertEqual(one(result,'operating_margin')['changes']['qoq']['absolute'],'5.00')
        self.assertEqual(one(result,'operating_margin')['changes']['qoq']['kind'],'percentage_points')
        self.assertIsNone(one(result,'operating_margin')['changes']['qoq']['percent'])
        fcf=one(result,'free_cash_flow')['cells']['current']
        self.assertEqual(fcf['value'],'24'); self.assertEqual(fcf['fact_ids'],['F005','F006'])
        self.assertEqual(fcf['calculation']['operator'],'subtract')
        self.assertEqual(one(result,'free_cash_flow_margin')['cells']['current']['fact_ids'],['F001','F005','F006'])

    def test_ytd_derivation_is_separate_and_never_eps_or_weighted_shares(self):
        data=[spec('revenue',300,YTD),spec('revenue',180,H1),spec('diluted_eps',3,YTD),spec('diluted_eps',1.8,H1),
              spec('diluted_shares',100,YTD),spec('diluted_shares',95,H1)]
        result=self.build(data)
        q=one(result,'revenue')['cells']['current']
        self.assertEqual(q['value'],'120'); self.assertEqual(q['calculation']['operator'],'ytd_difference')
        self.assertEqual(q['fact_ids'],['F001','F002'])
        self.assertEqual(one(result,'revenue','nine-month')['cells']['current']['value'],'300')
        self.assertEqual(one(result,'revenue','nine-month')['changes']['qoq']['status'],'unavailable')
        self.assertFalse(rows(result,'diluted_eps')); self.assertFalse(rows(result,'diluted_shares'))

    def test_direct_derived_disagreement_is_ambiguous_no_preference(self):
        result=self.build([spec('revenue',300,YTD),spec('revenue',180,H1),spec('revenue',119)])
        self.assertEqual(one(result,'revenue')['cells']['current']['status'],'ambiguous')
        self.assertTrue(any('conflict' in g['reason'].lower() for g in result['gaps']))

    def test_duplicate_agreement_preserves_all_ids_conflicts_suppress(self):
        result=self.build([spec('revenue',120),spec('revenue',120),spec('revenue',100,Q2)])
        self.assertEqual(one(result,'revenue')['cells']['current']['fact_ids'],['F001','F002'])
        result=self.build([spec('revenue',120),spec('revenue',121),spec('revenue',100,Q2)])
        self.assertEqual(one(result,'revenue')['cells']['current']['status'],'ambiguous')
        self.assertIsNone(one(result,'revenue')['changes']['qoq']['percent'])

    def test_no_cross_currency_basis_entity_or_dimension_ratio(self):
        variants=[{'unit':{'numerator':['iso4217:EUR'],'denominator':[]}}, {'basis':'Adjusted'},
                  {'entity':'DIFFERENT'}, {'dimensions':[{'dimension':'SegmentAxis','member':'WidgetMember'}]}]
        for variant in variants:
            with self.subTest(variant=variant):
                result=self.build([spec('revenue',100),spec('operating_income',20,**variant)])
                self.assertTrue(all(r['cells']['current']['value'] is None for r in rows(result,'operating_margin')))
                self.assertEqual(len(result['observations']),2)

    def test_aliases_never_arbitrarily_selected_but_reviewed_same_concept_labels_match(self):
        result=self.build([spec('revenue',100),spec('us-gaap:SalesRevenueNet',100),spec('operating_income',20)])
        self.assertIsNone(one(result,'operating_margin')['cells']['current']['value'])
        result=self.build([spec('revenue',100,label='Total revenue'),spec('revenue',100,label='Product revenue'),spec('operating_income',20)])
        self.assertEqual(one(result,'operating_margin')['cells']['current']['value'],'20.0')
        self.assertEqual(one(result,'revenue')['cells']['current']['source_labels'],['Product revenue','Total revenue'])

    def test_missing_basis_unknown_concept_and_unqualified_stay_explicit(self):
        result=self.build([spec('revenue',100,basis=''),spec('revenue',80,Q2,basis=''),spec('fictional:AdjustedProfit',40),spec('net_income',10,status='proposed')])
        self.assertEqual(one(result,'revenue')['changes']['qoq']['status'],'unavailable')
        self.assertEqual(one(result,'fictional:AdjustedProfit')['cells']['current']['value'],'40')
        self.assertEqual(len(result['observations']),4)
        self.assertTrue(any('Unqualified' in g['reason'] for g in result['gaps']))
        self.assertTrue(any('No exact' in g['reason'] for g in result['gaps']))

    def test_nonpositive_prior_growth_and_ratio_denominator(self):
        result=self.build([spec('net_income',5),spec('net_income',-5,Q2),spec('revenue',0)])
        delta=one(result,'net_income')['changes']['qoq']
        self.assertEqual(delta['absolute'],'10'); self.assertEqual(delta['status'],'not_meaningful')
        self.assertIsNone(delta['percent']); self.assertIsNone(one(result,'net_margin')['cells']['current']['value'])

    def test_signed_cash_flow_requires_explicit_frozen_convention(self):
        specs=[spec('operating_cash_flow',100),spec('capital_expenditure',-30)]
        self.assertIsNone(one(self.build(specs),'free_cash_flow')['cells']['current']['value'])
        result=self.build(specs,capex_conventions={'F002':'signed_cash_flow'})
        cell=one(result,'free_cash_flow')['cells']['current']
        self.assertEqual(cell['value'],'70')
        self.assertEqual(cell['calculation']['operands'][1]['calculation']['operands'][0]['value'],'-30')
        self.assertEqual(one(result,'capital_expenditure')['cells']['current']['value'],'-30')
        self.assertIsNone(one(self.build([spec('operating_cash_flow',100),spec('capital_expenditure',30)],capex_conventions={'F002':'signed_cash_flow'}),'free_cash_flow')['cells']['current']['value'])
        for cfg in [{'unknown':'signed_cash_flow'},{'F001':'signed_cash_flow'},{'F002':'absolute'}]:
            with self.assertRaises(ValueError): self.build(specs,capex_conventions=cfg)

    def test_52_53_week_years_and_true_quarter_adjacency(self):
        q=('duration','2026-07-05','2026-10-03'); prior=('duration','2025-07-06','2025-10-04')
        prev=('duration','2026-04-05','2026-07-04')
        result=analysis.build(fixture(self.root,[spec('revenue',120,q),spec('revenue',100,prior),spec('revenue',110,prev)]),current_period=q)
        self.assertEqual(one(result,'revenue')['changes']['yoy']['status'],'available')
        self.assertEqual(one(result,'revenue')['changes']['qoq']['status'],'available')
        result=self.build([spec('revenue',120),spec('revenue',100,('duration','2026-03-31','2026-06-29'))])
        self.assertEqual(one(result,'revenue')['cells']['prior_quarter']['status'],'missing')

    def test_instant_quarter_spacing_and_liquidity_no_missing_zero(self):
        specs=[]
        for p in [('instant','2026-09-30'),('instant','2026-06-30'),('instant','2025-09-30')]:
            specs += [spec(k,v,p) for k,v in [('cash_and_equivalents',20),('short_term_investments',10),('current_debt',5),('noncurrent_debt',35)]]
        result=self.build(specs)
        self.assertEqual(one(result,'liquid_assets','instant')['cells']['current']['value'],'30')
        self.assertEqual(one(result,'total_debt','instant')['cells']['current']['value'],'40')
        self.assertEqual(one(result,'net_debt','instant')['cells']['current']['value'],'20')
        self.assertEqual(one(result,'cash_and_equivalents','instant')['changes']['qoq']['status'],'available')
        result=self.build([spec('cash_and_equivalents',20,('instant','2026-09-30')),spec('cash_and_equivalents',10,('instant','2026-07-15'))])
        self.assertEqual(one(result,'cash_and_equivalents','instant')['cells']['prior_quarter']['status'],'missing')
        self.assertIsNone(one(result,'liquid_assets','instant')['cells']['current']['value'])

    def test_explicit_anchor_never_uses_stale_latest_as_current(self):
        result=self.build([spec('revenue',100,Q2)])
        self.assertEqual(one(result,'revenue')['cells']['current']['status'],'missing')
        self.assertEqual(one(result,'revenue')['period_observations'][0]['value'],'100')
        with self.assertRaises(ValueError): analysis.build(fixture(self.root,[spec('revenue',1)]))
        with self.assertRaises(ValueError): self.build([spec('revenue',1)],as_of='2026-12-31')

    def test_reported_gross_profit_conflict_blocks_calculated_margin(self):
        result=self.build([spec('revenue',100),spec('cost_of_revenue',60),spec('gross_profit',39)])
        self.assertIsNone(one(result,'gross_margin')['cells']['current']['value'])
        self.assertTrue(any(r['cells']['current']['status']=='ambiguous' for r in rows(result,'gross_profit')))

    def test_decimal_arithmetic_is_exact_and_source_tamper_fails(self):
        value='1'+'0'*90+'.12345678901234567890'
        result=self.build([spec('operating_cash_flow',value),spec('capital_expenditure','0.00000000000000000001')])
        self.assertEqual(one(result,'free_cash_flow')['cells']['current']['value'],'1'+'0'*90+'.12345678901234567889')
        bundle=fixture(self.root,[spec('revenue',100)])
        (self.root/'fictional-source.html').write_text('changed')
        with self.assertRaisesRegex(ValueError,'source changed'): analysis.build(bundle,current_period=Q3)

    def test_independently_reviewed_labels_can_differ_across_periods(self):
        result=self.build([spec('revenue',120,label='Revenue .........'),spec('revenue',100,Q2,label='Total')])
        self.assertEqual(one(result,'revenue')['changes']['qoq']['percent'],'20.0')
        self.assertEqual(one(result,'revenue')['cells']['prior_quarter']['source_labels'],['Total'])

    def test_explicit_basis_configuration_fills_only_unstated_basis(self):
        specs=[spec('revenue',100,basis=''),spec('revenue',80,Q2,basis='')]
        result=self.build(specs,accounting_bases={'F001':'Reviewed statutory basis','F002':'Reviewed statutory basis'})
        self.assertEqual(one(result,'revenue')['changes']['qoq']['percent'],'25.00')
        self.assertEqual(one(result,'revenue')['cells']['current']['calculation']['basis_origin'],'caller_declared')
        self.assertEqual(result['observations'][0]['accounting_basis'],'')
        for cfg in [{'unknown':'GAAP'},{'F001':''},{'F001':3}]:
            with self.assertRaises(ValueError): self.build(specs,accounting_bases=cfg)
        with self.assertRaisesRegex(ValueError,'contradicts'):
            self.build([spec('revenue',100)],accounting_bases={'F001':'Non-GAAP'})

    def test_negative_cost_is_not_silently_added_to_revenue(self):
        result=self.build([spec('revenue',100),spec('cost_of_revenue',-60)])
        self.assertIsNone(one(result,'gross_profit')['cells']['current']['value'])

    def test_calculated_values_can_exceed_source_lexical_bounds_without_float(self):
        result=self.build([spec('revenue','1e-100'),spec('operating_income','1e100')])
        self.assertEqual(one(result,'operating_margin')['cells']['current']['value'],'1'+'0'*202)

    def test_duration_and_instant_roles_do_not_cross_into_calculations(self):
        result=self.build([spec('revenue',100,('instant','2026-09-30')),spec('operating_income',20,('instant','2026-09-30')),
                           spec('cash_and_equivalents',10),spec('short_term_investments',5)])
        self.assertFalse(rows(result,'operating_margin','instant'))
        self.assertFalse(rows(result,'liquid_assets'))
        self.assertTrue(any('incompatible period' in g['reason'] for g in result['gaps']))

    def test_reported_gross_profit_basis_assumption_survives_fallback(self):
        result=self.build([spec('revenue',100),spec('gross_profit',40,basis='')],
                          accounting_bases={'F002':'GAAP (unaudited)'})
        margin=one(result,'gross_margin')
        self.assertEqual(margin['cells']['current']['value'],'40.0')
        self.assertEqual(margin['basis_origin'],'caller_declared')
        self.assertIn(CONCEPT['gross_profit'],margin['concepts'])

    def test_fiscal_year_comparison_crossing_december_january_civil_boundary(self):
        current=('duration','2026-01-04','2026-04-04')
        prior=('duration','2024-12-29','2025-03-29')
        result=analysis.build(fixture(self.root,[spec('revenue',120,current),spec('revenue',100,prior)]),current_period=current)
        self.assertEqual(one(result,'revenue')['changes']['yoy']['percent'],'20.0')
        outside=('duration','2024-12-15','2025-03-15')
        result=analysis.build(fixture(self.root,[spec('revenue',120,current),spec('revenue',100,outside)]),current_period=current)
        self.assertIsNone(one(result,'revenue')['changes']['yoy']['percent'])

    def test_year_ago_does_not_choose_nearest_or_accept_too_short_year(self):
        result=self.build([spec('revenue',120),spec('revenue',100,PY3),
                           spec('revenue',100,('duration','2025-06-29','2025-09-28'))])
        self.assertEqual(one(result,'revenue')['cells']['prior_year']['status'],'ambiguous')
        self.assertIsNone(one(result,'revenue')['changes']['yoy']['percent'])
        result=self.build([spec('revenue',120),spec('revenue',100,('duration','2025-07-15','2025-10-14'))])
        self.assertEqual(one(result,'revenue')['cells']['prior_year']['status'],'missing')

    def test_fourth_quarter_annual_less_nine_month_keeps_annual_separate(self):
        q4=('duration','2026-10-01','2026-12-31')
        specs=[spec('revenue',400,('duration','2026-01-01','2026-12-31')),
               spec('revenue',300,YTD),spec('revenue',180,H1),
               spec('revenue',320,('duration','2025-01-01','2025-12-31')),
               spec('revenue',240,('duration','2025-01-01','2025-09-30'))]
        result=analysis.build(fixture(self.root,specs),current_period=q4)
        row=one(result,'revenue')
        self.assertEqual(row['cells']['current']['value'],'100')
        self.assertEqual(row['cells']['prior_quarter']['value'],'120')
        self.assertEqual(row['cells']['prior_year']['value'],'80')
        self.assertEqual(row['changes']['yoy']['percent'],'25.00')
        self.assertEqual(one(result,'revenue','annual')['cells']['current']['value'],'400')
        self.assertEqual(one(result,'revenue','annual')['changes']['qoq']['status'],'unavailable')

    def test_artifact_is_deterministic_across_process_hash_seeds(self):
        bundle=fixture(self.root,[spec('revenue',120),spec('revenue',100,Q2),spec('revenue',80,PY3)])
        path=self.root/'bundle.json'; path.write_text(json.dumps(bundle))
        script="from research.earnings_financial_analysis import build; import sys,json,hashlib; b=json.load(open(sys.argv[1])); print(hashlib.sha256(json.dumps(build(b,current_period=('duration','2026-07-01','2026-09-30')),sort_keys=True).encode()).hexdigest())"
        outputs=[subprocess.check_output([sys.executable,'-c',script,str(path)],
                  cwd=Path(__file__).resolve().parents[1],env={**os.environ,'PYTHONHASHSEED':str(seed)},text=True)
                 for seed in (1,42)]
        self.assertEqual(outputs[0],outputs[1])

    def test_attributed_profit_is_not_total_net_income_or_net_margin(self):
        result=self.build([spec('ifrs-full:ProfitLossAttributableToOwnersOfParent',20),spec('revenue',100)])
        self.assertFalse(rows(result,'net_income'))
        self.assertIsNone(one(result,'net_margin')['cells']['current']['value'])


if __name__=='__main__': unittest.main()
