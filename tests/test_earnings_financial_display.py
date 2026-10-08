"""Fictional regression cases; no research data or provider calls."""
import copy
import unittest
from research import earnings_financial_display as display


def fixture():
    contexts = {p: {'entity':'FAKE','entity_scheme':'fictional','dimensions':[],
                   'instant':None,'start_date':year+'-01-01','end_date':year+'-03-31'}
                for p,year in [('a','2040'),('b','2039')]}
    observations = [
        {'id':fid,'concept':concept,'value':value,'context_id':period,'unit_id':'USD',
         'status':'extracted','nil':False}
        for fid,concept,value,period in [
            ('F1','us-gaap:Revenues','1250000000','a'),('F2','us-gaap:Revenues','1000000000','b'),
            ('F3','us-gaap:NetIncomeLoss','22500000','a'),('F4','us-gaap:NetIncomeLoss','-5500000','b')]]
    return {'rows':[{'label':'Wrong label: net income / revenue, USD billions','fact_ids':['F1','F3','F2','F4']}]}, {
        'financial':{'observations':observations,'contexts':contexts,
                     'units':{'USD':{'numerator':['iso4217:USD'],'denominator':[]}}}}


class FinancialDisplayTests(unittest.TestCase):
    def test_code_owns_scale_metric_and_comparison_columns(self):
        sheet,bundle=fixture(); table=display.build(sheet,bundle)
        group=table['groups'][0]
        self.assertEqual(group['unit'],'USD millions')
        self.assertEqual([r['metric'] for r in group['rows']],['Revenue','Net income (loss)'])
        self.assertEqual([[c['value'] for c in r['cells']] for r in group['rows']], [['1,250','1,000'],['22.5','-5.5']])
        self.assertEqual(group['periods'][0]['key'],['duration','2040-01-01','2040-03-31'])
        self.assertEqual(set(table['selected_fact_ids']),{'F1','F2','F3','F4'})
        sheet['rows'][0]['label']='Completely different invented label'
        self.assertEqual(display.build(sheet,bundle),table)

    def test_currency_per_share_ratios_and_precision(self):
        for unit,value,expected in [
            ({'numerator':['iso4217:USD'],'denominator':['xbrli:shares']},'1.2345',('1.2345','USD/share','1')),
            ({'numerator':['xbrli:pure'],'denominator':[]},'0.54',('0.54','ratio','1')),
            ({'numerator':['xbrli:shares'],'denominator':[]},'2000000000',('2,000','million shares','1000000')),
            ({'numerator':['iso4217:EUR'],'denominator':[]},'1',('0.000001','EUR millions','1000000'))]:
            self.assertEqual(display.scaled_value({'value':value},unit),expected)
        with self.assertRaises(ValueError):
            display.scaled_value({'value':'NaN'},unit)

    def test_dimensions_and_duration_families_stay_separate(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        facts['contexts']['s']=copy.deepcopy(facts['contexts']['a'])
        facts['contexts']['s']['dimensions']=[{'dimension':'us-gaap:StatementBusinessSegmentsAxis','member':'fake:WidgetsMember','type':'explicitmember'}]
        facts['observations'][2].update(concept='us-gaap:Revenues',context_id='s')
        facts['contexts']['h']=dict(facts['contexts']['a'],end_date='2040-06-30')
        facts['observations'][3].update(concept='us-gaap:Revenues',context_id='h')
        groups=display.build(sheet,bundle)['groups']
        rows=[r for g in groups for r in g['rows']]
        self.assertEqual(len(rows),3)
        self.assertIn('Widgets segment',[r['dimensions'] for r in rows])

    def test_duplicates_preserve_ids_and_conflicting_values_fail(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        facts['observations'][2].update(concept='us-gaap:Revenues',value='1250000000')
        table=display.build(sheet,bundle)
        self.assertEqual(table['groups'][0]['rows'][0]['cells'][0]['fact_ids'],['F1','F3'])
        facts['observations'][2]['value']='1250000001'
        with self.assertRaisesRegex(ValueError,'Conflicting values'):
            display.build(sheet,bundle)

    def test_instant_context_and_payment_horizon_preserve_source_meaning(self):
        sheet,bundle=fixture();sheet['rows'][0]['fact_ids']=['F1']
        bundle['financial']['observations'][0]['concept']='us-gaap:OtherCommitmentDueInNextTwelveMonths'
        bundle['financial']['contexts']['a'].update(instant='2040-03-31',start_date=None,end_date=None)
        text=display.text_table(sheet,bundle)
        self.assertIn('next twelve months',text)
        self.assertNotIn('FY2041',text)
        self.assertIn('As filed: Mar 31, 2040',text)

    def test_html_links_every_fact_and_no_raw_taxonomy_or_model_label(self):
        sheet,bundle=fixture();seen=[]
        html=display.html_table(sheet,bundle,lambda ids:seen.extend(ids) or ', '.join(ids))
        self.assertEqual(set(seen),{'F1','F2','F3','F4'})
        self.assertIn('<caption>USD millions</caption>',html)
        self.assertNotIn('us-gaap:',html)
        self.assertNotIn('Wrong label',html)
        self.assertEqual(html.count('<table>'),html.count('</table>'))

    def test_issuer_attribution_and_local_basis_survive_rendering(self):
        sheet,bundle=fixture()
        sheet['rows']=[{'label':'GAAP net income, quarter','fact_ids':['F3','F4']}]
        for obs in bundle['financial']['observations'][2:]:
            obs['support']={'table_row':{'text':'Net income (loss) attributable to Example Holdings$22.5$(5.5)', 'truncated':False}}
        sheet['context']=[{'text':'Quarter comparisons are unaudited U.S. GAAP.', 'citations':['F3','F4']}]
        result=display.build(sheet,bundle)
        row=result['groups'][0]['rows'][0]
        self.assertEqual(row['metric'],'Net income (loss) attributable to Example Holdings (GAAP)')
        text=display.text_table(sheet,bundle)
        self.assertIn('unaudited U.S. GAAP',text)
        self.assertIn('22.5 [F3] | -5.5 [F4]',text)
        rendered=display.html_table(sheet,bundle,lambda ids:' '.join(ids))
        self.assertIn('financial-basis',rendered)
        self.assertIn('Example Holdings (GAAP)',rendered)

    def test_qualified_segment_measure_stays_distinct_from_plain_measure(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        sheet['rows']=[{'label':'Invented label','fact_ids':['F1','F2','F3','F4']}]
        for obs in facts['observations']:
            obs['concept']='fake:EarningsBeforeInterestTaxesDepreciationAndAmortization'
            source_label='Total segment EBITDA As Defined' if obs['id'] in ('F1','F2') else 'EBITDA'
            obs['support']={'table_row':{'text':source_label+'120 100','truncated':False}}
        rows=display.build(sheet,bundle)['groups'][0]['rows']
        self.assertEqual([r['metric'] for r in rows],['Total segment EBITDA As Defined','EBITDA'])
        self.assertEqual(rows[0]['cells'][0]['fact_ids'],['F1'])
        self.assertEqual(rows[1]['cells'][0]['fact_ids'],['F3'])

    def test_source_channel_label_preserves_broader_category(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        sheet['rows']=[{'label':'Commercial aftermarket','fact_ids':['F1','F2']}]
        for ctx in facts['contexts'].values():
            ctx['dimensions']=[{'dimension':'fake:SalesMarketTypeAxis','member':'fake:CommercialAftermarketMember'}]
        for obs in facts['observations'][:2]:
            obs['support']={'table_row':{'text':'Commercial and non-aerospace aftermarket48 42 90','truncated':False}}
        row=display.build(sheet,bundle)['groups'][0]['rows'][0]
        self.assertEqual(row['metric'],'Revenue')
        self.assertEqual(row['dimensions'],'Commercial and non-aerospace aftermarket')

    def test_comparable_nine_month_periods_align_but_stub_period_does_not(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        sheet['rows']=[{'label':'YTD','fact_ids':['F1','F2']}]
        facts['contexts']['a'].update(start_date='2039-10-01',end_date='2040-06-28')
        facts['contexts']['b'].update(start_date='2038-10-01',end_date='2039-06-27')
        table=display.build(sheet,bundle)
        self.assertEqual(len(table['groups']),1)
        self.assertEqual(len(table['groups'][0]['periods']),2)
        self.assertEqual([c['fact_ids'] for c in table['groups'][0]['rows'][0]['cells']],[['F1'],['F2']])
        facts['contexts']['b']['start_date']='2039-02-01'
        self.assertEqual(len(display.build(sheet,bundle)['groups']),2)

    def test_incomplete_source_label_cannot_override_identity_or_make_gaap_segment(self):
        sheet,bundle=fixture(); facts=bundle['financial']
        sheet['rows']=[{'label':'GAAP issuer earnings','fact_ids':['F3']}]
        facts['contexts']['a']['dimensions']=[{'dimension':'fake:AdjustmentAxis','member':'fake:AdjustedMember'}]
        facts['observations'][2]['support']={'table_row':{'text':'Net income attributable to Example', 'truncated':True}}
        metric=display.build(sheet,bundle)['groups'][0]['rows'][0]['metric']
        self.assertEqual(metric,'Net income (loss)')

    def test_digits_inside_source_name_are_not_truncated_attribution(self):
        obs={'support':{'table_row':{'text':'Net income attributable to Example 3M$20', 'truncated':False}}}
        self.assertEqual(display.source_row_label(obs),'')

    def test_source_channel_label_preserves_other_material_dimensions(self):
        obs={'concept':'us-gaap:Revenues','support':{'table_row':{
            'text':'Commercial and industrial aftermarket48 42','truncated':False}}}
        dims=[{'dimension':'fake:SalesMarketTypeAxis','member':'fake:CommercialAftermarketMember'},
              {'dimension':'us-gaap:StatementBusinessSegmentsAxis','member':'fake:AviationMember'},
              {'dimension':'fake:GeographicalAxis','member':'fake:EuropeMember'}]
        label,detail=display.metric_identity(obs,dims)
        self.assertEqual(label,'Revenue')
        self.assertEqual(detail,'Commercial and industrial aftermarket; Aviation segment; Geographical: Europe')

    def test_ebitda_name_requires_explicit_source_accounting_basis(self):
        dims=[{'dimension':'us-gaap:StatementBusinessSegmentsAxis','member':'fake:ExampleMember'}]
        obs={'concept':'fake:EarningsBeforeInterestTaxesDepreciationAndAmortization',
             'support':{'table_row':{'text':'Segment EBITDA100 90','truncated':False}}}
        self.assertEqual(display.accounting_basis(obs,dims,{'label':'Non-GAAP segment earnings'}),'')
        obs['support']['table_row']['text']='Non-GAAP segment EBITDA100 90'
        self.assertEqual(display.accounting_basis(obs,dims,{'label':'Segment earnings'}),'non-GAAP')
        obs['support']['table_row']['truncated']=True
        self.assertEqual(display.accounting_basis(obs,dims,{'label':'Non-GAAP segment earnings'}),'')
