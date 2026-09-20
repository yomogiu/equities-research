import copy
import json
from pathlib import Path
import tempfile
import unittest

from research.cli import ROOT, private_output, read, render
from research.contracts import (KINDS, event_id, packet_id, validate_calendar,
    validate_packet, validate_extraction, validate_review, watchlist)


def source():
    return {'documents':[{'kind':'release','title':'Fictitious release',
        'source_url':'https://example.com/release','published_at':None,'period':'FY2026-Q3',
        'text':'Revenue was USD 100 million. '+'Fictitious example, not financial data. '*5,
        'publisher_type':'issuer','completeness':'full','limitation':''}],
        'availability':{k:('available' if k=='release' else 'pending') for k in KINDS},
        'report_markdown':'Fictitious packet'}


def artifacts():
    packet=validate_packet(source())
    doc=packet['documents'][0]['document_id']
    extraction={'quotes':[{'document_id':doc,'text':'Revenue was USD 100 million.',
        'speaker':'Issuer release','locator':'paragraph 1','topic':'revenue'}],
        'data':[{'document_id':doc,'metric':'revenue','value':100,'unit':'million','currency':'USD',
        'period':'FY2026-Q3','basis':'GAAP','locator':'paragraph 1',
        'source_text':'Revenue was USD 100 million.'}], 'gaps':['Transcript pending'],
        'report_markdown':'Fictitious revenue of USD 100 million.'}
    commentary={'commentary':[{'claim':'Issuer revenue claim','classification':'company_claim',
        'document_ids':[doc],'locators':['paragraph 1'],'counterevidence':'None retrieved',
        'uncertainty':'Filing not yet retrieved'}], 'contradictions':[], 'questions':['Filing reconciliation?'],
        'framework_coverage':{'valuation':'unavailable'},'report_markdown':'Incomplete event update.'}
    review={'verdict':'pass','findings':[],'report_markdown':'Fictitious reviewer result.'}
    return packet,extraction,commentary,review


class Contracts(unittest.TestCase):
    def test_public_watchlist_contract_rejects_portfolio_fields(self):
        sample={'symbol':'FAKE','issuer':'Fictitious Example','exchange':'TEST'}
        watchlist([sample])
        for field in ('weight_pct','account','balance'):
            with self.assertRaises(ValueError):
                watchlist([{**sample,field:42}])

    def test_unknown_exchange_is_not_research_ready(self):
        with self.assertRaises(ValueError):
            watchlist([{'symbol':'FAKE','issuer':'Fictitious','exchange':'UNRESOLVED'}])

    def test_partial_packet_retains_corrected_versions(self):
        old=validate_packet(source())
        changed=source()
        changed['documents'][0]['text']+=' Corrected text.'
        new=validate_packet(changed,old)
        self.assertEqual(len(new['documents']),2)
        self.assertNotEqual(packet_id(old),packet_id(new))

    def test_document_status_needs_actual_document(self):
        packet=source()
        packet['availability']['transcript']='available'
        with self.assertRaises(ValueError):
            validate_packet(packet)

    def test_fake_quotation_fails(self):
        p,e,c,r=artifacts()
        e['quotes'][0]['text']='Fabricated words.'
        with self.assertRaises(ValueError):
            validate_extraction(e,p)

    def test_changed_units_or_basis_are_checked(self):
        p,e,c,r=artifacts()
        e['data'][0]['basis']='unknown'
        with self.assertRaises(ValueError):
            validate_extraction(e,p)

    def test_material_review_cannot_pass(self):
        r={'verdict':'pass','findings':[{'target':'commentator','severity':'material',
            'claim':'Overstatement','evidence':'Missing evidence','document_ids':[],
            'required_change':'State limitation'}]}
        with self.assertRaises(ValueError):
            validate_review(r)

    def test_calendar_covers_every_issuer(self):
        with self.assertRaises(ValueError):
            validate_calendar({'events':[],'coverage':[],'report_markdown':'No dates'},
                [{'symbol':'FAKE','issuer':'Fictitious','exchange':'TEST'}])

    def test_report_keeps_source_and_missing_document_states(self):
        report=render(*artifacts())
        self.assertIn('https://example.com/release',report)
        self.assertIn('transcript: pending',report)
        self.assertIn('not a completed position review',report)

    def test_output_cannot_be_in_public_checkout(self):
        with self.assertRaises(ValueError):
            private_output(ROOT/'reports'/'private.md')

    def test_output_cannot_overwrite_earlier_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.md'
            path.write_text('Earlier report')
            with self.assertRaises(ValueError):
                private_output(path)

    def test_invalid_json_number_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            path.write_text('{"value":NaN}')
            with self.assertRaises(ValueError):
                read(path)


if __name__=='__main__':
    unittest.main()
