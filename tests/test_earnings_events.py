import unittest,tempfile
from pathlib import Path
from datetime import date
from research import earnings_events as events,earnings_fresh_sources as fresh,earnings_source_case as case

BASE='https://stockanalysis.com/quote/test/FAKE/transcripts/'
def link(slug,title):return ('<a href="'+BASE+slug+'">'+title+'</a>').encode()


class EventTests(unittest.TestCase):
    def test_trading_update_is_selected_using_both_label_and_url(self):
        body=link('1-h1-2040/','Earnings Call: H1 2040')+link('2-q3-2040-tu/','Earnings Call: Q3 2040')
        result=events.select(body,BASE,date(2040,10,25))
        self.assertEqual((result['period'],result['kind']),('FY2040-Q3','trading_update'))
        events.qualify_call('Fictional Micro\nEarnings Call: Q3 2040\n','Fictional Micro',result)
        for text in ['Fictional Micro\nEarnings Call: Q2 2040\n','Other Issuer\nEarnings Call: Q3 2040\n']:
            with self.assertRaises(ValueError):events.qualify_call(text,'Fictional Micro',result)

    def test_h1_h2_keep_native_labels_and_event_durations(self):
        for label,quarter,start in [('H1',2,'2040-01-01'),('H2',4,'2040-07-01')]:
            with self.subTest(label=label):
                e=events.select(link('1-'+label.lower()+'-2040/','Earnings Call: '+label+' 2040'),BASE,date(2041,2,10))
                self.assertEqual((e['quarter'],e['start'],e['period']),(quarter,start,'FY2040-'+label))
                events.qualify_call('Fictional Micro\nEarnings Call: '+label+' 2040\n','Fictional Micro',e)
                self.assertTrue(events.excluded(e,['FY2040-'+label]))
                self.assertTrue(events.excluded(e,['FY2040-Q'+str(quarter)]))
                self.assertFalse(events.excluded(e,['FY2039-'+label]))

    def test_url_and_label_conflict_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError,'conflicts'):
            events.select(link('2-q3-2040-tu/','Earnings Call: Q2 2040'),BASE,date(2040,10,25))

    def test_exclude_media_post_call_agm_other_issuer_and_future_period(self):
        body=link('1-h1-2040/','Earnings Call: H1 2040')
        for slug,title in [('2-h1-2040-media/','Earnings Call: H1 2040'),('3-q2-2040-post-call/','Earnings Call: Q2 2040'),('4-agm-2040/','AGM 2040'),('5-q4-2040-tu/','Earnings Call: Q4 2040')]:body+=link(slug,title)
        body+=link('6-q3-2040-tu/','Earnings Call: Q3 2040').replace(b'/FAKE/',b'/OTHER/')
        self.assertEqual(events.select(body,BASE,date(2040,10,25))['label'],'H1')

    def test_ambiguous_equivalent_quarter_and_half_year_events_fail(self):
        body=link('1-h1-2040/','Earnings Call: H1 2040')+link('2-q2-2040/','Earnings Call: Q2 2040')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):events.select(body,BASE,date(2040,7,30))

    def test_release_only_route_is_limited_to_trading_updates(self):
        body=b'<a href="https://example.test/filings/2/">Earnings release</a>'
        self.assertEqual(events.attachment(body,BASE,{'quarter':3,'kind':'trading_update'})[1],'earnings_release')
        with self.assertRaises(ValueError):events.attachment(body,BASE,{'quarter':3,'kind':'earnings_call'})
        annual=b'<a href="https://example.test/filings/3/">Annual report</a>'
        self.assertEqual(events.attachment(annual,BASE,{'quarter':4,'kind':'earnings_call'})[1],'annual_report')

    def test_attachment_type_and_exact_id_must_both_match(self):
        body=b'{id:2,type:"earnings_release",fileUrl:"https://example.test/release.pdf"},{id:3,type:"quarterly_report",fileUrl:"https://example.test/report.pdf"}'
        self.assertEqual(fresh.filing_url(body,'https://example.test/filings/2/','earnings_release'),'https://example.test/release.pdf')
        with self.assertRaises(ValueError):fresh.filing_url(body,'https://example.test/filings/2/','quarterly_report')

    def test_release_identity_and_current_year_before_comparative(self):
        text='[Page 1]\nPRESS RELEASE\nFirst nine months    2040/2039 change\nRevenue 120 100 20\n'
        text+='This press release is an official information document of the Fictional Micro Group.\n'+('available evidence '*800)
        q=fresh.qualify_report(text,'Fictional Micro',(2040,3),trading_update=True)
        self.assertEqual(q['completeness'],'limited_trading_update')
        self.assertEqual((q['report_period']['basis'],q['report_period']['start']),('nine_months','2040-01-01'))
        with self.assertRaisesRegex(ValueError,'statements'):fresh.qualify_report(text,'Fictional Micro',(2040,3))
        with self.assertRaises(ValueError):fresh.qualify_report(text,'Other',(2040,3),trading_update=True)

    def test_release_case_requires_frozen_matching_trading_qualification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'release';raw.write_text('fake release');call=root/'call';call.write_text('fake call')
            qpath=root/'qualification.json';q={'issuer_id':'fake','period':'FY2040-Q3','event':{'kind':'trading_update'},'completeness':'limited_trading_update','source_gaps':['No full statements'],
                'documents':[{'document_id':'release','raw_sha256':case.sha(raw),'kind':'release'}]};case.save(qpath,q)
            sources=[{'path':str(raw),'sha256':case.sha(raw),'kind':'release','representation':'raw','document_id':'release'},
                     {'path':str(call),'sha256':case.sha(call),'kind':'transcript','representation':'text','document_id':'call'}]
            value={'schema_version':1,'scope':'one_packet_experiment','authorization':'fake test','issuer_id':'fake','period':'FY2040-Q3','sources':sources,
                   'artifacts':[{'path':str(qpath),'sha256':case.sha(qpath)}],'financial_path':str(raw),'transcript_path':str(call),'transcript_index_path':str(call),
                   'source_mode':'trading_update_release','qualification_path':str(qpath)}
            case.validate_case(value)
            for changes in [{'source_mode':'financial_report'},{'issuer_id':'other'},{'period':'FY2040-Q2'},{'artifacts':[]}]:
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):case.validate_case({**value,**changes})


if __name__=='__main__':unittest.main()
