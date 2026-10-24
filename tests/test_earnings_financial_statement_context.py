"""Fictional filed statements: qualified basis, identical facts, real arithmetic."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from research import financial_evidence
from research import earnings_financial_analysis as analysis
from research import earnings_financial_analysis_report as report
from research import earnings_financial_statement_context as statements

Q = ('2040-04-01','2040-06-30')
PY = ('2039-04-01','2039-06-30')
H = ('2040-01-01','2040-06-30')
HPY = ('2039-01-01','2039-06-30')
BASIS = 'The accompanying consolidated financial statements have been prepared in accordance with generally accepted accounting principles in the United States.'


def fixture(root, specs, declaration=BASIS, continued=False, glossary=None):
    parts=[]
    if glossary is not None: parts.append('<table><tr><td>GAAP</td><td>'+glossary+'</td></tr></table>')
    for n,row in enumerate(specs):
        period=row[2];dim=row[4] if len(row)>4 else ''
        dates=('<xbrli:instant>'+period[0]+'</xbrli:instant>') if len(period)==1 else ('<xbrli:startDate>'+period[0]+'</xbrli:startDate><xbrli:endDate>'+period[1]+'</xbrli:endDate>')
        parts.append('<xbrli:context id="c'+str(n)+'"><xbrli:entity><xbrli:identifier scheme="fictional">FAKE</xbrli:identifier>'+dim+'</xbrli:entity><xbrli:period>'+dates+'</xbrli:period></xbrli:context>')
    parts.append('<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>')
    if declaration is not None:
        if continued:
            parts.append('<ix:nonNumeric name="us-gaap:BasisOfAccounting" contextRef="c0" continuedAt="basis-detail">Basis of presentation</ix:nonNumeric><ix:continuation id="basis-detail">'+declaration+'</ix:continuation>')
        else: parts.append('<ix:nonNumeric name="us-gaap:BasisOfAccounting" contextRef="c0">'+declaration+'</ix:nonNumeric>')
    for n,(concept,value,period,label,*_) in enumerate(specs):
        parts.append('<table><tr><td>'+label+'</td><td><ix:nonFraction name="'+concept+'" contextRef="c'+str(n)+'" unitRef="usd">'+str(value)+'</ix:nonFraction></td></tr></table>')
    raw=''.join(parts);path=root/'fictional-statements.html';path.write_text(raw)
    digest=hashlib.sha256(raw.encode()).hexdigest();source={'document_id':'fictional-statements','raw_sha256':digest}
    extracted=financial_evidence.extract_inline_xbrl(raw,source)
    observations=[];contexts={};units={}
    for n,original in enumerate(extracted['observations'],1):
        item=deepcopy(original);cid=item['context']['id'];uid=item['unit']['id']
        contexts[cid]=item['context'];units[uid]=item['unit']
        item.update(id='F%03d'%n,context_id=cid,unit_id=uid,source_path=str(path),source_sha256=digest)
        observations.append(item)
    return {'manifest':{'sources':[{'kind':'filing','path':str(path),'sha256':digest,'document_id':source['document_id']}]},
            'financial':{'source':source,'observations':observations,'contexts':contexts,'units':units,'gaps':[]}}


def rows(value,metric,family='quarter'):
    return [row for table in value['tables'] if table['period_family']==family for row in table['rows'] if row['metric_id']==metric]


class FinancialStatementContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def build(self,specs,**kwargs):
        bundle=fixture(self.root,specs,**kwargs)
        return bundle,report.compile(statements.qualify(bundle),report.configuration(*Q))

    def test_explicit_statement_basis_enables_growth_and_preserves_source_spans(self):
        bundle,value=self.build([('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',100,PY,'Revenue')],continued=True)
        row=rows(value,'revenue')[0]
        self.assertEqual(row['basis'],'GAAP');self.assertEqual(row['changes']['yoy']['percent'],'20.0')
        proof=row['cells']['current']['calculation']['basis_source'][0]
        self.assertEqual(len(proof['source_spans']),2)
        source=Path(bundle['manifest']['sources'][0]['path']).read_text()
        for span in proof['source_spans']:
            self.assertEqual(hashlib.sha256(source[span['start']:span['end']].encode()).hexdigest(),span['span_sha256'])
        self.assertEqual(value['observations'],bundle['financial']['observations'])

    def test_basis_is_not_inferred_from_taxonomy_or_unrelated_gaap_mention(self):
        specs=[('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',100,PY,'Revenue')]
        for declaration in (None,'Management uses GAAP and non-GAAP metrics for comparative purposes.'):
            with self.subTest(declaration=declaration):
                _,value=self.build(specs,declaration=declaration)
                self.assertIsNone(rows(value,'revenue')[0]['basis'])
                self.assertEqual(rows(value,'revenue')[0]['changes']['yoy']['status'],'unavailable')

    def test_present_fairly_requires_exact_us_glossary_and_preserves_both_spans(self):
        declaration='The accompanying consolidated financial statements contain all adjustments necessary to present fairly, in accordance with GAAP, the financial position.'
        specs=[('us-gaap:RegulatedAndUnregulatedOperatingRevenue',120,Q,'Utility operating revenue'),
               ('us-gaap:RegulatedAndUnregulatedOperatingRevenue',100,PY,'Operating revenue')]
        bundle,value=self.build(specs,declaration=declaration,glossary='United States generally accepted accounting principles')
        found=rows(value,'revenue');self.assertEqual(len(found),1)
        self.assertEqual(found[0]['changes']['yoy']['percent'],'20.0')
        support=statements.source_support(value,bundle)
        self.assertEqual(len(support),2)
        self.assertTrue(any('United States generally accepted' in row['text'] for row in support))
        self.assertTrue(any('present fairly' in row['text'] for row in support))
        legacy=report.compile(bundle,report.configuration(*Q))
        self.assertFalse(rows(legacy,'revenue'))
        for glossary in (None,'Generally accepted accounting principles','Canadian generally accepted accounting principles'):
            with self.subTest(glossary=glossary):
                _,value=self.build(specs,declaration=declaration,glossary=glossary)
                self.assertIsNone(rows(value,'revenue')[0]['basis'])
                self.assertEqual(rows(value,'revenue')[0]['changes']['yoy']['status'],'unavailable')

    def test_glossary_alone_does_not_qualify_unrelated_or_negated_declaration(self):
        for declaration in ('Management discusses GAAP measures.',
                            'The consolidated financial statements are not presented in accordance with GAAP.'):
            _,value=self.build([('us-gaap:Revenues',120,Q,'Revenue')], declaration=declaration,
                               glossary='United States generally accepted accounting principles')
            self.assertIsNone(rows(value,'revenue')[0]['basis'])

    def test_productive_assets_requires_exact_original_capex_label(self):
        for label in ('Capital expenditures','Capital/construction expenditures','Purchases of property, plant and equipment'):
            with self.subTest(label=label):
                bundle,value=self.build([('us-gaap:PaymentsToAcquireProductiveAssets',20,H,label),
                                         ('us-gaap:NetCashProvidedByUsedInOperatingActivities',70,H,'Operating cash flow')])
                self.assertEqual(rows(value,'capital_expenditure','half')[0]['cells']['current']['value'],'20')
                self.assertEqual(rows(value,'free_cash_flow','half')[0]['cells']['current']['value'],'50')
                self.assertFalse(rows(report.compile(bundle,report.configuration(*Q)),'capital_expenditure','half'))
        for label in ('Purchases of productive assets','Capital expenditures and acquisitions','Not capital expenditures'):
            with self.subTest(label=label):
                _,value=self.build([('us-gaap:PaymentsToAcquireProductiveAssets',20,H,label)])
                self.assertFalse(rows(value,'capital_expenditure','half'))

    def test_lease_inclusive_debt_components_are_displayed_without_inferred_total(self):
        specs=[('us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent',12,('2040-06-30',),'Current debt'),
               ('us-gaap:LongTermDebtAndCapitalLeaseObligations',100,('2040-06-30',),'Long-term debt'),
               ('us-gaap:ShortTermBorrowings',8,('2040-06-30',),'Short-term debt'),
               ('us-gaap:LongTermDebtAndCapitalLeaseObligations',90,('2039-12-31',),'Long-term debt')]
        bundle,value=self.build(specs)
        selected=report.front_rows(value)['cash']
        self.assertEqual({row['metric_id'] for _,row in selected},set(report.DEBT_COMPONENT_NAMES))
        self.assertTrue(all(family=='instant' for family,_ in selected))
        for _,row in selected:
            self.assertEqual(row['cells']['current']['period'],['instant','2040-06-30'])
            self.assertEqual(row['cells']['prior_quarter']['status'],'missing')
            self.assertEqual(row['cells']['prior_year']['status'],'missing')
        self.assertFalse(rows(value,'total_debt','instant'))
        text='\n'.join(report.sections(value)['cash']+report.notes(value))
        self.assertIn('capital leases',text)
        self.assertIn('No combined total is inferred',text)
        self.assertIn('Debt total unavailable',text)
        self.assertTrue(all('[^'+row['cells']['current']['fact_ids'][0]+']' in text for _,row in selected))
        self.assertFalse(report.front_rows(report.compile(bundle,report.configuration(*Q)))['cash'])

    def test_historical_nonoptin_computation_remains_unqualified(self):
        bundle,_=self.build([('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',100,PY,'Revenue')])
        old=report.compile(bundle,report.configuration(*Q))
        self.assertNotIn('source_policy',old)
        self.assertIsNone(rows(old,'revenue')[0]['basis'])

    def test_same_concept_context_unit_deduplicates_labels_and_preserves_every_id(self):
        _,value=self.build([('us-gaap:Revenues',120,Q,'REVENUE'),('us-gaap:Revenues',120,Q,'Revenue from external customers'),('us-gaap:Revenues',100,PY,'Total revenue')])
        found=rows(value,'revenue');self.assertEqual(len(found),1)
        self.assertEqual(found[0]['cells']['current']['fact_ids'],['F001','F002'])
        self.assertEqual(found[0]['changes']['yoy']['percent'],'20.0')
        self.assertEqual(len(report.front_rows(value)['demand']),1)

    def test_conflicting_duplicate_values_are_never_selected_by_order(self):
        _,value=self.build([('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',121,Q,'Total revenue')])
        self.assertEqual(rows(value,'revenue')[0]['cells']['current']['status'],'ambiguous')
        self.assertEqual(report.front_rows(value)['demand'],[])

    def test_adjusted_label_and_segment_context_do_not_inherit_statement_basis(self):
        dimension='<xbrli:segment><xbrldi:explicitMember dimension="fake:SegmentAxis">fake:North</xbrldi:explicitMember></xbrli:segment>'
        _,value=self.build([('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',130,Q,'Adjusted revenue'),('us-gaap:Revenues',40,Q,'Revenue',dimension)])
        found=rows(value,'revenue')
        self.assertEqual(sum(row['basis']=='GAAP' for row in found),1)
        self.assertEqual(len(found),3)

    def test_compatible_profit_and_cash_inputs_compute_margins_fcf_and_debt(self):
        specs=[('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:GrossProfit',30,Q,'Gross profit'),
               ('us-gaap:NetCashProvidedByUsedInOperatingActivities',90,H,'Operating cash'),
               ('us-gaap:PaymentsToAcquirePropertyPlantAndEquipment',20,H,'Acquisition of property'),
               ('us-gaap:PaymentsToAcquirePropertyPlantAndEquipment',12,Q,'Capital expenditures'),
               ('us-gaap:DebtCurrent',10,('2040-06-30',),'Current debt'),
               ('us-gaap:LongTermDebtNoncurrent',70,('2040-06-30',),'Long-term debt, net')]
        _,value=self.build(specs)
        self.assertEqual(rows(value,'gross_margin')[0]['cells']['current']['value'],'25.00')
        self.assertEqual(rows(value,'free_cash_flow','half')[0]['cells']['current']['value'],'70')
        self.assertEqual(rows(value,'total_debt','instant')[0]['cells']['current']['value'],'80')
        self.assertIn('carrying amount',rows(value,'total_debt','instant')[0]['label'])
        capex=[(family,row) for family,row in report.front_rows(value)['cash'] if row['metric_id']=='capital_expenditure']
        self.assertEqual(len(capex),1);self.assertEqual(capex[0][0],'half')
        self.assertEqual(capex[0][1]['cells']['current']['value'],'20')

    def test_half_less_trailing_quarter_derives_only_additive_money(self):
        specs=[('us-gaap:Revenues',220,H,'Revenue'),('us-gaap:Revenues',120,Q,'Total revenue'),
               ('us-gaap:GrossProfit',45,H,'Gross profit'),('us-gaap:GrossProfit',30,Q,'Gross profit'),
               ('us-gaap:EarningsPerShareDiluted',2,H,'Diluted EPS'),('us-gaap:EarningsPerShareDiluted',1.2,Q,'Diluted EPS'),
               ('us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',50,H,'Diluted shares'),
               ('us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',52,Q,'Diluted shares')]
        bundle,value=self.build(specs)
        revenue=rows(value,'revenue')[0]
        self.assertEqual(revenue['cells']['prior_quarter']['value'],'100')
        self.assertEqual(revenue['cells']['prior_quarter']['period'],['duration','2040-01-01','2040-03-31'])
        self.assertEqual(revenue['changes']['qoq']['percent'],'20.0')
        self.assertEqual(rows(value,'gross_margin')[0]['changes']['qoq']['absolute'],'10.00')
        self.assertEqual(rows(value,'diluted_eps')[0]['cells']['prior_quarter']['status'],'missing')
        self.assertEqual(rows(value,'diluted_shares')[0]['cells']['prior_quarter']['status'],'missing')
        legacy=report.compile(bundle,report.configuration(*Q))
        self.assertTrue(all(row['cells']['prior_quarter']['status']=='missing' for row in rows(legacy,'revenue')))

    def test_inverse_quarter_conflict_with_reported_prior_is_not_ignored(self):
        _,value=self.build([('us-gaap:Revenues',220,H,'Revenue'),('us-gaap:Revenues',120,Q,'Revenue'),
                            ('us-gaap:Revenues',101,('2040-01-01','2040-03-31'),'Revenue')])
        self.assertEqual(rows(value,'revenue')[0]['cells']['prior_quarter']['status'],'ambiguous')
        self.assertEqual(rows(value,'revenue')[0]['changes']['qoq']['status'],'unavailable')

    def test_condensed_interim_basis_declaration_is_source_qualified(self):
        declaration='The Condensed Consolidated Financial Statements do not include footnotes and certain financial information normally presented annually under generally accepted accounting principles in the United States.'
        _,value=self.build([('us-gaap:Revenues',120,Q,'Revenue')],declaration=declaration,continued=True)
        self.assertEqual(rows(value,'revenue')[0]['basis'],'GAAP')

    def test_original_basis_packet_deduplicates_and_verifies_source_text(self):
        bundle,value=self.build([('us-gaap:Revenues',120,Q,'Revenue'),('us-gaap:Revenues',100,PY,'Revenue'),
                                 ('us-gaap:GrossProfit',30,Q,'Gross profit')],continued=True)
        support=statements.source_support(value,bundle)
        self.assertEqual(len(support),2)
        self.assertTrue(any(BASIS in row['text'] for row in support))
        for row in support:
            self.assertEqual(hashlib.sha256(row['text'].encode()).hexdigest(),row['provenance']['span_sha256'])
        path=Path(bundle['manifest']['sources'][0]['path']);path.write_text(path.read_text()+'tampered')
        with self.assertRaisesRegex(ValueError,'original source changed'):
            statements.source_support(value,bundle)

    def test_press_release_does_not_inherit_filing_policy(self):
        bundle,_=self.build([('us-gaap:Revenues',120,Q,'Revenue')])
        bundle['manifest']['sources'][0]['kind']='earnings_release'
        value=report.compile(statements.qualify(bundle),report.configuration(*Q))
        self.assertIsNone(rows(value,'revenue')[0]['basis'])

    def test_repair_qualifies_only_explicit_sec_interim_basis(self):
        declaration = ('The consolidated financial statements have been prepared in accordance with '
            'generally accepted accounting principles for interim financial information and pursuant to '
            'the rules and regulations of the Securities and Exchange Commission.')
        specs=[('us-gaap:Revenues',150,Q,'Revenue'),('us-gaap:Revenues',100,PY,'Revenue')]
        bundle,_=self.build(specs,declaration=declaration)
        self.assertIsNone(rows(report.compile(statements.qualify(bundle),report.configuration(*Q)),'revenue')[0]['basis'])
        repaired=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
        self.assertEqual(rows(repaired,'revenue')[0]['changes']['yoy']['percent'],'50.0')
        self.assertEqual(repaired['observations'],bundle['financial']['observations'])
        self.assertTrue(statements.source_support(repaired,bundle))
        for text in (declaration.replace('Securities and Exchange Commission','fictional local regulator'),
                     declaration.replace('have been prepared','have not been prepared'),
                     'Management discusses interim GAAP under SEC rules.'):
            bundle,_=self.build(specs,declaration=text)
            value=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
            self.assertIsNone(rows(value,'revenue')[0]['basis'])

    def test_repair_selects_only_revenue_identity_reconciled_across_all_periods(self):
        specs=[('us-gaap:Revenues',150,Q,'Revenue including special income'),
               ('us-gaap:Revenues',130,PY,'Revenue including special income'),
               ('us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',150,Q,'Sales'),
               ('us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',100,PY,'Sales'),
               ('us-gaap:GrossProfit',90,Q,'Gross profit'),('us-gaap:GrossProfit',80,PY,'Gross profit'),
               ('us-gaap:CostOfRevenue',60,Q,'Cost'),('us-gaap:CostOfRevenue',50,PY,'Cost')]
        bundle,original=self.build(specs)
        self.assertNotEqual(rows(original,'gross_margin')[0]['cells']['current']['status'],'available')
        repaired=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
        margin=rows(repaired,'gross_margin')[0]
        self.assertEqual(margin['cells']['current']['value'],'60.0')
        self.assertEqual(len(rows(repaired,'revenue')),2)  # Distinct definitions are not duplicates.
        self.assertIn('revenue_scope_reconciliation',str(margin['period_observations']))
        # Conflicting proof and indistinguishable candidates must remain ambiguous.
        for replacement in (100,130):
            modified=list(specs);modified[1]=('us-gaap:Revenues',replacement,PY,'Revenue including special income')
            modified[3]=('us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',replacement,PY,'Sales')
            bundle,_=self.build(modified)
            value=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
            self.assertNotEqual(rows(value,'gross_margin')[0]['cells']['current']['status'],'available')

    def test_repair_keeps_diluted_share_definition_separate_from_adjusted_metric(self):
        specs=[('us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',50,Q,'Diluted'),
               ('us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',50,Q,
                'Denominator for diluted net income per share – adjusted weighted-average shares and assumed conversions'),
               ('us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',60,Q,'Adjusted diluted shares')]
        bundle,_=self.build(specs)
        value=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
        qualified=[r for r in rows(value,'diluted_shares') if r['basis']=='GAAP']
        self.assertEqual(len(qualified),1)
        self.assertEqual(len(qualified[0]['cells']['current']['fact_ids']),2)
        self.assertEqual(qualified[0]['cells']['current']['value'],'50')
        self.assertEqual(len(rows(value,'diluted_shares')),2)

    def test_repair_derives_rd_prior_quarter_but_never_eps_or_share_subtraction(self):
        specs=[('us-gaap:ResearchAndDevelopmentExpense',25,H,'R&D'),
               ('us-gaap:ResearchAndDevelopmentExpense',15,Q,'R&D'),
               ('us-gaap:EarningsPerShareDiluted',3,H,'EPS'),('us-gaap:EarningsPerShareDiluted',2,Q,'EPS')]
        bundle,_=self.build(specs)
        value=report.compile(statements.qualify(bundle,repair=True),report.configuration(*Q))
        self.assertEqual(rows(value,'research_and_development')[0]['cells']['prior_quarter']['value'],'10')
        self.assertEqual(rows(value,'diluted_eps')[0]['cells']['prior_quarter']['status'],'missing')


if __name__=='__main__':unittest.main()
