"""Fictitious event-source route: no real sources, networks or model calls."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_event_preparation as event, earnings_report_flow as flow
from research import library
from research.source_parse import extract
from test_financial_html_tables import fixture, authorize
from test_publisher_transcript import fixture as call_fixture


class EventPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.output = self.root/'prepared'
        self.writing = self.root/'writing.txt'; self.writing.write_text('Fictitious writing standard')
        self.iid = 'sec:0000000042'; self.url = 'https://www.sec.gov/Archives/edgar/data/42/'+'0'*18+'/release.htm'
        library.save(self.root/'library/catalog.json', {'catalog_id':'fake-catalog',
            'issuers':{self.iid:{'issuer':'Fictional Example plc'}}})
        library.save(self.root/'config.json', {})
        self.period = 'FY2040-Q2'
        raw, source, profile = fixture(); source.update(issuer_id=self.iid, document_id='fake-release')
        profile['source'] = source
        for observation in profile['observations']: observation['context']['entity'] = self.iid
        pb, rb, authorization = authorize(source, profile)
        self.write('release.bin', raw); self.write('release.txt', b'Fictional text')
        self.write('profile.json', pb); self.write('financial-review.json', rb)
        self.financial = {'profile_path':'profile.json','review_path':'financial-review.json','authorization':authorization}
        self.release = dict(source, kind='release', period=self.period, completeness='full',
                            source_url=self.url, raw_path='release.bin', text_path='release.txt')
        callraw, calltext, _ = call_fixture()
        self.write('call.bin',callraw);self.write('call.txt',calltext.encode())
        self.call={'document_id':'fake-call','raw_path':'call.bin','text_path':'call.txt',
                   'raw_sha256':self.sha(callraw),'text_sha256':self.sha(calltext.encode()),
                   'kind':'transcript','period':self.period,'completeness':'full','source_url':'https://calls.example/fake'}
        report = ('<html><body><ix:nonNumeric name="dei:DocumentType">8-K</ix:nonNumeric>'
                  '<ix:nonNumeric name="dei:TradingSymbol">FAKE</ix:nonNumeric>'
                  '<ix:nonNumeric name="dei:EntityRegistrantName">Fictional Example plc</ix:nonNumeric>'
                  '<p>Results for the quarter ended June 30, 2040.</p><a href="release.htm">Exhibit99.1</a></body></html>').encode()
        currenturl = self.url.replace('release.htm','current.htm')
        text, fiscal, _ = extract(report,'text/html',currenturl)
        self.write('current.bin',report);self.write('current.txt',text.encode())
        self.manifest={'document_id':'fake-current-report','issuer_id':'cik-0000000042','symbol':'FAKE',
                       'kind':'current_report','source_url':currenturl,'raw_path':'current.bin','text_path':'current.txt',
                       'raw_sha256':self.sha(report),'text_sha256':self.sha(text.encode()),'fiscal_tags':fiscal,
                       'metadata':{'form':'8-K','filingDate':'2040-07-20'}}
        library.save(self.root/'current.json',self.manifest)
        self.observed={currenturl:{'sha256':self.sha(report),'final_url':currenturl,
                                  'checked_at':datetime.now(timezone.utc).isoformat()}}
        library.save(self.root/'http-cache.json',self.observed)
        self.packet={'packet_id':'fake-packet','issuer_id':self.iid,'period':self.period,'documents':[self.release,self.call]}
        start=text.index('June 30, 2040')
        self.selection={'version':event.VERSION,'enabled':True,'packet_id':'fake-packet','issuer_id':self.iid,
                        'period':self.period,'release_document_id':'fake-release','current_report_path':'current.json',
                        'current_report_sha256':self.sha((self.root/'current.json').read_bytes()),'review_path':'event-review.json',
                        'review_sha256':'','author_id':'fake-source-author','reviewer_id':'fake-source-reviewer',
                        'period_end':'2040-06-30','period_evidence':{'start':start,'end':start+len('June 30, 2040'),'text':'June 30, 2040'},
                        'observation_path':'http-cache.json','observation_sha256':self.sha((self.root/'http-cache.json').read_bytes())}
        self.review()

    def write(self,name,data): (self.root/name).write_bytes(data)
    def sha(self,value): return hashlib.sha256(value).hexdigest()
    def review(self):
        review={k:self.selection[k] for k in event.REVIEW_FIELDS if k!='verdict'}
        review['verdict']='pass_event_sources_only';library.save(self.root/'event-review.json',review)
        self.selection['review_sha256']=self.sha((self.root/'event-review.json').read_bytes())
    def authenticate(self): return event.authenticate(self.root,self.packet,self.selection)

    def test_exact_event_does_not_relabel_prior_or_current_sources(self):
        prior=copy.deepcopy((self.packet,self.manifest,self.selection));release,call,manifest=self.authenticate()
        self.assertEqual(release['kind'],'release');self.assertEqual(manifest['kind'],'current_report')
        self.assertEqual((self.packet,self.manifest,self.selection),prior)
        self.assertFalse(self.output.exists())

    def test_default_periodic_filing_guard_is_unchanged(self):
        with patch.object(flow,'validate_packet',return_value=self.packet):
            with self.assertRaisesRegex(ValueError,'full current-period filing'):
                flow.prepare(self.root,'fake-packet',self.output,self.writing,'fake authorization')
        self.assertFalse(self.output.exists())

    def test_source_review_and_selection_changes_reject(self):
        for key,value in [('enabled',False),('issuer_id','sec:0000000043'),('period','FY2040-Q3'),
                          ('release_document_id','different'),('reviewer_id','fake-source-author'),
                          ('current_report_sha256','0'*64),('review_sha256','0'*64),
                          ('period_end','2040-07-01')]:
            with self.subTest(key=key):
                original=copy.deepcopy(self.selection);self.selection[key]=value
                with self.assertRaises(ValueError):self.authenticate()
                self.selection=original

    def test_unapproved_or_stale_review_rejects(self):
        r=json.loads((self.root/'event-review.json').read_text());r['verdict']='pending'
        library.save(self.root/'event-review.json',r);self.selection['review_sha256']=self.sha((self.root/'event-review.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'review pending'):self.authenticate()

    def test_original_source_mutation_and_missing_call_reject(self):
        self.write('current.bin',(self.root/'current.bin').read_bytes()+b' ')
        with self.assertRaises(ValueError):self.authenticate()
        self.packet['documents']=[self.release]
        with self.assertRaisesRegex(ValueError,'release and transcript'):self.authenticate()

    def test_non_sec_or_wrong_issuer_companion_rejects_even_with_new_review(self):
        for url in [self.url.replace('www.sec.gov','other.example'),self.url.replace('/42/','/43/')]:
            self.manifest['source_url']=url;library.save(self.root/'current.json',self.manifest)
            self.selection['current_report_sha256']=self.sha((self.root/'current.json').read_bytes());self.review()
            with self.assertRaisesRegex(ValueError,'SEC archive URL'):self.authenticate()

    def test_event_prepare_requires_independent_financial_profile(self):
        with self.assertRaisesRegex(ValueError,'reviewed release financial'):
            event.prepare(self.root,'fake-packet',self.output,self.writing,'authorized',selection=self.selection,reviewed_financial=None)
        self.assertFalse(self.output.exists())

    def test_actual_reviewed_cells_prepare_with_current_report_and_release(self):
        cat={'catalog_id':'fake-catalog','issuers':{self.iid:{'issuer':'Fictional Example plc'}}}
        with patch.object(flow,'validate_packet',return_value=self.packet),patch.object(library,'catalog',return_value=cat):
            casepath=event.prepare(self.root,'fake-packet',self.output,self.writing,'fictitious explicit event authorization',selection=self.selection,reviewed_financial=self.financial)
        case=json.loads(casepath.read_text());facts=json.loads((self.output/'financial.json').read_text())
        self.assertEqual(facts['observations'][0]['value'],'1234500000.00')
        self.assertEqual(facts['observations'][0]['source_document_id'],'fake-release')
        self.assertTrue(any(s['kind']=='filing' and s.get('original_kind')=='current_report' for s in case['sources']))
        self.assertTrue(any(s['kind']=='release' for s in case['sources']))
        self.assertIn('not a periodic filing',' '.join(case['scope_notes']))
        flow.base.validate_case(case)

    def test_self_reviewed_financial_profile_is_not_accepted(self):
        self.financial['authorization']['reviewer_id']='fake-author'
        cat={'catalog_id':'fake-catalog','issuers':{self.iid:{'issuer':'Fictional Example plc'}}}
        with patch.object(flow,'validate_packet',return_value=self.packet),patch.object(library,'catalog',return_value=cat):
            with self.assertRaisesRegex(ValueError,'Distinct authorized profile'):
                event.prepare(self.root,'fake-packet',self.output,self.writing,'authorized',selection=self.selection,reviewed_financial=self.financial)

    def test_stale_or_different_http_observation_rejects_even_if_reviewed(self):
        for mutation in ('stale','hash','redirect'):
            with self.subTest(mutation=mutation):
                value=copy.deepcopy(self.observed);row=next(iter(value.values()))
                if mutation=='stale':row['checked_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
                elif mutation=='hash':row['sha256']='0'*64
                else:row['final_url']='https://other.example/fake'
                library.save(self.root/'http-cache.json',value)
                self.selection['observation_sha256']=self.sha((self.root/'http-cache.json').read_bytes());self.review()
                with self.assertRaises(ValueError):self.authenticate()
