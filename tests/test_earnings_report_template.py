"""Fictional layout, period math, source retention and legacy compatibility."""
import copy
import unittest
from test_earnings_passages import PassageFixture
import test_earnings_signals as signal_fixture
from research import earnings_report_template as template, earnings_markdown as md
from research import earnings_batch_review as batch, earnings_visual_signals as visual
from research import earnings_file_pipeline as pipeline
from research import earnings_mixed_runner as base


def group(periods, values, unit='USD millions'):
    return {'periods': [{'key': p} for p in periods], 'unit': unit}, {
        'cells': [{'original_value': str(v), 'fact_ids': ['F'+str(i)]} for i, v in enumerate(values)]}


class ComparisonTests(unittest.TestCase):
    def test_shifted_fiscal_quarter_retains_growth(self):
        g,r=group([['duration','2026-04-27','2026-07-26'],
                   ['duration','2025-04-28','2025-07-27']],[9115,7302])
        self.assertEqual(template.comparisons(g,r)['YoY'],'+24.8% [^F0] [^F1]')

    def test_53_week_calendar_allowed_but_wrong_period_rejected(self):
        from research.earnings_period_comparisons import year_ago
        current=['duration','2026-04-27','2026-07-26']
        self.assertTrue(year_ago(current,['duration','2025-04-21','2025-07-20']))
        self.assertFalse(year_ago(current,['duration','2025-01-27','2025-07-27']))
        self.assertFalse(year_ago(current,['duration','2025-04-07','2025-07-06']))
        self.assertFalse(year_ago(current,['duration','2024-04-28','2024-07-27']))
        self.assertFalse(year_ago(current,['instant','2025-07-27']))

    def test_quarters_calculate_both_changes_and_keep_input_citations(self):
        g, r = group([['duration','2026-07-01','2026-09-30'],
                      ['duration','2026-04-01','2026-06-30'],
                      ['duration','2025-07-01','2025-09-30']], [120,100,80])
        before=copy.deepcopy((g,r));changes=template.comparisons(g,r)
        self.assertEqual(changes['QoQ'],'+20.0% [^F0] [^F1]')
        self.assertEqual(changes['YoY'],'+50.0% [^F0] [^F2]')
        self.assertEqual((g,r),before)

    def test_ytd_ratios_zero_and_losses_do_not_become_growth(self):
        g,r=group([['duration','2026-01-01','2026-09-30'],['duration','2025-01-01','2025-09-30']],[120,80])
        self.assertEqual(template.comparisons(g,r),{'QoQ':'—','YoY':'—'})
        g,r=group([['duration','2026-07-01','2026-09-30'],['duration','2026-04-01','2026-06-30']],[10,0])
        self.assertTrue(template.comparisons(g,r)['QoQ'].startswith('n/m'))
        r['cells'][1]['original_value']='-5'
        self.assertTrue(template.comparisons(g,r)['QoQ'].startswith('n/m'))
        g['unit']='ratio';self.assertEqual(template.comparisons(g,r)['QoQ'],'—')

    def test_colour_is_semantic_and_unknown_or_context_dependent_stays_neutral(self):
        headers=['Metric','This quarter','QoQ','YoY']
        for label in ('Inventory, net','Current debt','Capital expenditure','Revenue cost','Custom revenue'):
            result=visual.comparison_badges(headers,[label,'100','+20.0% [^F1]','-5.0%'])
            self.assertIn('direction flat',result[2]);self.assertIn('direction flat',result[3])
        result=visual.comparison_badges(headers,['Revenue','100','+20.0%','-5.0%'])
        self.assertIn('direction up',result[2]);self.assertIn('direction down',result[3])

    def test_missing_periods_and_instant_balances(self):
        g,r=group([['instant','2026-09-30'],['instant','2026-06-30'],['instant','2025-09-30']],[120,100,80])
        self.assertIn('+20.0%',template.comparisons(g,r)['QoQ'])
        self.assertIn('+50.0%',template.comparisons(g,r)['YoY'])
        g,r=group([['instant','2026-09-30']],[100]);self.assertEqual(template.comparisons(g,r)['QoQ'],'—')


class TemplateTests(PassageFixture, unittest.TestCase):
    def state(self):
        analysis=copy.deepcopy(self.report);analysis['report_template']=template.VERSION
        for f,section in zip(analysis['findings'],('demand','earnings','outlook','qa')):f['section']=section
        analysis['findings'][-1]['text']="Asked: Fictional question.\n\nManagement's answer: Fictional answer.\n\nInterpretation: No further quantified detail."
        return {'artifacts':{'financial':self.financial,'retrieval':self.retrieval,'analysis':analysis},
                'format':{'rows':{},'basis':{'text':'','citations':[]}}}

    def test_sections_sources_quotes_signals_and_review_roundtrip(self):
        state=self.state();pack=signal_fixture.SignalTests.pack(self,state)
        text=md.report(state,self.bundle,self.catalog,pack)
        headings=[line for line in text.splitlines() if line.startswith('## ')]
        self.assertEqual(headings[:6],['## Quarter in Focus',*['## '+x for x in template.SECTIONS.values()]])
        for omitted in ('## Next tests','## Business signals','## Valuation','## What to Watch'):self.assertNotIn(omitted,text)
        self.assertEqual(text.count("Asked: Fictional question."),1)
        self.assertIn('F002',text)
        items=batch.units(state,pack);replayed,rebound=batch.materialize(items)
        self.assertEqual(replayed,state)
        self.assertEqual(md.report(replayed,self.bundle,self.catalog,rebound),text)
        page=md.render(text)
        self.assertIn('scope="row"',page);self.assertIn('table-scroll',page)
        self.assertIn('Earnings-Call Q&amp;A',page)

    def test_marker_unknown_sections_and_next_tests_rejected(self):
        a=self.state()['artifacts']['analysis']
        for field,value in [('report_template','unknown'),('next_tests',[{'text':'New question'}])]:
            bad=copy.deepcopy(a);bad[field]=value
            with self.assertRaises(ValueError):template.validate(bad)
        a['findings'][0]['section']='watchlist'
        with self.assertRaises(ValueError):template.validate(a)

    def test_legacy_rendering_and_new_protocol_freeze(self):
        state=self.state();state['artifacts']['analysis'].pop('report_template')
        self.assertIn('## Next tests',md.report(state,self.bundle,self.catalog))
        writing=self.root/'writing.md';writing.write_text('Fictional writing standard.')
        protocol=pipeline.initialize(self.casepath,self.root/'new',writing)
        self.assertEqual(protocol['report_template'],template.VERSION)
        index=pipeline.context.assemble(protocol['evidence_manifest'],self.catalog,self.root/'prompt-context')
        text=pipeline.instruction('analysis',index,self.root/'job',protocol)
        self.assertIn('Return next_tests: []',text)
        self.assertIn('no broader market',text)
        self.assertIn('Preserve a substantive textual summary',text)
        self.assertIn('Tables\nsupport the prose; they do not replace it.',text)
        self.assertIn('multiple paragraphs',text)
        self.assertNotIn('Questions That Matter',text)
        self.assertLess(len(text.encode()),24000)
        legacy=pipeline.initialize(self.casepath,self.root/'legacy',writing,report_template=None)
        self.assertNotIn('report_template',legacy)

    def test_marker_cannot_be_stripped_by_a_correction(self):
        state=self.state();items=batch.units(state,signal_fixture.SignalTests.pack(self,state))
        value=copy.deepcopy(items['analysis:opening']['value']);value.pop('report_template')
        plan={'before_sha256':base.digest(items),'changes':[{'unit_id':'analysis:opening',
              'before_sha256':base.digest(items['analysis:opening']['value']),'value':value,'reason':'Fictional change'}]}
        with self.assertRaisesRegex(ValueError,'template cannot change'):batch.apply(items,plan)

    def test_comparison_html_keeps_references_and_escapes_source_markup(self):
        text='# Fictional\n\n| Metric | Current | QoQ | YoY |\n| --- | --- | --- | --- |\n| Revenue | 120 | +20.0% [^F1] | n/m |\n\n[^F1]: <script>bad()</script>\n'
        page=md.render(text)
        self.assertIn('direction up',page);self.assertIn('href="#source-F1"',page)
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)

    def test_original_exchange_is_exact_source_text_and_does_not_expand_review_markdown(self):
        state=self.state();index=self.bundle['transcript_index']
        exchange=index['exchanges'][0]
        finding=state['artifacts']['analysis']['findings'][-1]
        finding['citations']=[exchange['id']]
        finding['quotes']=[]
        before=copy.deepcopy(state)
        text=md.report(state,self.bundle,self.catalog)
        self.assertIn(':::original-qa '+exchange['id'],text)
        copied=template.original_exchanges(state,self.bundle)
        from research import earnings_compact_evidence as evidence
        source=evidence.transcript_view(self.bundle['manifest'])['text']
        for turn in copied[exchange['id']]['turns']:
            self.assertEqual(turn['text'],source[turn['start']:turn['end']])
        page=md.render(text,original_exchanges=copied)
        self.assertIn('<details class="original-qa">',page)
        self.assertIn('Read the original exchange',page)
        self.assertEqual(state,before)
        with self.assertRaisesRegex(ValueError,'verified source bundle'):md.render(text)

    def test_turn_citations_and_followups_resolve_without_topic_guessing(self):
        index={'exchanges':[
            {'id':'e1','turn_ids':['q1','a1'],'followup_of':None},
            {'id':'e2','turn_ids':['q2','a2'],'followup_of':'e1'},
            {'id':'e3','turn_ids':['q3','a3'],'followup_of':None}]}
        self.assertEqual(template.exchange_ids({'citations':['a2'],'quotes':[]},index),['e1','e2'])
        self.assertEqual(template.exchange_ids({'citations':['D001'],'quotes':[]},index),[])

    def test_original_source_markup_is_escaped(self):
        page=md.render('# Fictional\n\n:::original-qa e1\n',original_exchanges={
            'e1':{'turns':[{'speaker':'<speaker>','role':'analyst','text':'<script>bad()</script>'}]}})
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)


if __name__=='__main__':unittest.main()
