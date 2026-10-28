"""Fictional regressions for varied event links and issuer-defined fiscal years."""
import hashlib
import unittest
from datetime import date
from unittest.mock import Mock
from research import earnings_events as events, earnings_report_identity as identity
from research import earnings_source_verification as verification
from research import earnings_financial_analysis_report as finance

BASE='https://stockanalysis.com/stocks/fictional/transcripts/'

def card(slug,title,when):
    return f'<div><a href="{BASE}{slug}/">{title}</a><button><span>{when}</span></button></div>'.encode()

class FiscalDiscoveryTests(unittest.TestCase):
    def test_investor_call_wins_over_video_and_old_unsuffixed_event(self):
        body=card('10-q3-2040-investor-call','Earnings Call: Q3 2040','Oct 14, 2040')
        body+=card('11-q3-2040-pre-recorded','Earnings Call: Q3 2040','Oct 14, 2040')
        body+=card('12-q4-2039','Earnings Call: Q4 2039','Jan 25, 2040')
        e=events.select(body,BASE,date(2040,10,28),fiscal_calendar='document_defined')
        self.assertEqual(e['period'],'FY2040-Q3')
        self.assertEqual(e['published_on'],'2040-10-14')
        self.assertIsNone(e['end'])

    def test_fiscal_year_ahead_of_wall_calendar_uses_publication_date(self):
        e=events.select(card('32-results-webcast','Earnings Call: Q2 2041','Sep 2, 2040'),BASE,date(2040,10,28),fiscal_calendar='document_defined')
        self.assertEqual(e['period'],'FY2041-Q2')
        self.assertIsNone(e['start'])

    def test_future_publication_is_not_eligible(self):
        with self.assertRaisesRegex(ValueError,'No completed'):
            events.select(card('32-q1-2041-investor-call','Earnings Call: Q1 2041','Dec 1, 2040'),BASE,date(2040,10,28),fiscal_calendar='document_defined')

    def test_missing_publication_does_not_guess_fiscal_date(self):
        with self.assertRaisesRegex(ValueError,'published call date'):
            events.select(card('32-q1-2041','Earnings Call: Q1 2041',''),BASE,date(2040,10,28),fiscal_calendar='document_defined')

    def test_conflicting_labels_on_suffix_still_fail(self):
        with self.assertRaisesRegex(ValueError,'conflicts'):
            events.select(card('32-q2-2041-investor-call','Earnings Call: Q1 2041','Sep 2, 2040'),BASE,date(2040,10,28),fiscal_calendar='document_defined')

    def test_non_calendar_report_does_not_acquire_september_dates(self):
        text='[Page 1]\nFictional Micro\nQ3 2040\nFor the quarterly period ended August 2, 2040\n'
        b=identity.period_evidence(text,(2040,3),'Fictional Micro',fiscal_calendar='document_defined')
        self.assertEqual(b['end'],'2040-08-02');self.assertIsNone(b['start'])
        with self.assertRaisesRegex(ValueError,'differs'):
            identity.period_evidence(text,(2040,2),'Fictional Micro',fiscal_calendar='document_defined')
        p={'verified_issuer_index':True,'matched_call':True,'exact_attachment':True,'event':{'fiscal_calendar':'document_defined'},'report_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        cb=Mock(side_effect=AssertionError('No extra model needed'))
        self.assertEqual(verification.qualify(text,'Fictional Micro',(2040,3),p,cb)['report_period'],b)

    def test_results_headline_precedes_forecast_and_comparison_columns(self):
        text='[Page 1]\nFictional Micro reports record revenue in Q3 2040\nFull-year 2040 sales expected to rise\nQ2 2040        Q3 2040\nFor the quarter ended September 27, 2040\n'
        b=identity.period_evidence(text,(2040,3),'Fictional Micro',fiscal_calendar='document_defined')
        self.assertEqual(b['basis'],'quarter');self.assertEqual(b['end'],'2040-09-27')
        with self.assertRaisesRegex(ValueError,'differs'):
            identity.period_evidence(text.replace('in Q3 2040','in Q2 2040'),(2040,3),'Fictional Micro',fiscal_calendar='document_defined')

    def test_attached_regulator_cover_uses_real_endpoint_without_model(self):
        text='[Page 1]\nFORM 10-Q\nFor the quarterly period ended August 2, 2040\nFictional Micro Inc.\n(Exact name of registrant)\n'
        p={'verified_issuer_index':True,'matched_call':True,'exact_attachment':True,'event':{'fiscal_calendar':'document_defined','published_on':'2040-09-02'},'report_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        cb=Mock(side_effect=AssertionError('No source model needed'))
        result=verification.qualify(text,'Fictional Micro',(2040,3),p,cb)
        self.assertEqual(result['decision_method'],'deterministic')
        self.assertEqual(result['report_period']['end'],'2040-08-02')
        self.assertIsNone(result['report_period']['start'])
        with self.assertRaisesRegex(ValueError,'bounded verification'):
            verification.qualify(text,'Fictional Micro',(2040,3),{**p,'event':{**p['event'],'published_on':'2040-07-01'}})

    def test_empty_pdf_normalization_can_keep_dates_unknown(self):
        for end in (None,'2040-08-02'):
            config=finance.unresolved_configuration(end)
            bundle={'manifest':{'sources':[]},'financial':{'observations':[],'contexts':{},'units':{}}}
            result=finance.compile(bundle,config)
            self.assertEqual(result['as_of'],end);self.assertIsNone(result['current_period']);self.assertEqual(result['tables'],[])
            bundle['financial']['observations']=[{'id':'fake'}]
            with self.assertRaisesRegex(ValueError,'explicit quarter dates'):finance.compile(bundle,config)

    def test_model_fallback_does_not_manufacture_calendar_dates(self):
        text='[Page 1]\nThis document covers Fictional Micro operations.\nFor the quarterly period ended August 2, 2040\n'
        p={'verified_issuer_index':True,'matched_call':True,'exact_attachment':True,'event':{'fiscal_calendar':'document_defined'},'report_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        cb=Mock(return_value={'verdict':'accept','reason':'Source fiscal period matches.','issuer_quote':'Fictional Micro','period_quote':'For the quarterly period ended August 2, 2040','basis':'quarter'})
        b=verification.qualify(text,'Fictional Micro',(2040,3),p,cb)['report_period']
        self.assertIsNone(b['start']);self.assertEqual(b['end'],'2040-08-02')

if __name__=='__main__':unittest.main()
