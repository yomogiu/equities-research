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
