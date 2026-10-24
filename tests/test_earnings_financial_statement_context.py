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


def fixture(root, specs, declaration=BASIS, continued=False):
    parts=[]
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


if __name__=='__main__':unittest.main()
