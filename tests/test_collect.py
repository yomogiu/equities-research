import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from research.collect import Collector, select_filings, validate_registry
from research.fetch import Client, FetchError, check_url
from research.source_parse import calendar_events, extract, feed_links, kind_for, page

ROW = {'symbol': 'FAKE', 'issuer': 'Example Corporation', 'exchange': 'Nasdaq', 'regulator_id': '0000000001'}
URL = 'https://ir.example.test/results'
REGISTRY = {'schema_version': 1, 'issuers': {'FAKE': {'cik': '1', 'documents': [{'url': URL, 'kind': 'release'}]}}}
BODY = ('<html><p>' + 'Revenue and earnings figures for the quarter. ' * 20 + '</p></html>').encode()

class CollectionTests(unittest.TestCase):
    def test_idempotent_download_and_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def transport(url, headers):
                calls.append(url)
                return 200, {'Content-Type': 'text/html', 'ETag': 'v1'}, BODY, url
            client = Client(tmp, {'ir.example.test'}, 'test', transport=transport, sleep=lambda _: None)
            first = Collector([ROW], REGISTRY, tmp, client=client).run()
            second = Collector([ROW], REGISTRY, tmp, client=client).run()
            self.assertEqual(first['new_documents'], 1)
            self.assertEqual(second['new_documents'], 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(json.loads((Path(tmp) / 'analysis-queue.json').read_text())), 1)
            self.assertEqual(second['model_calls'], 0)
            self.assertEqual(second['status'], 'partial')

    def test_identical_document_at_two_urls_is_one_queue_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, 'test', transport=lambda u,h:(200,{'Content-Type':'text/html'},BODY,u),sleep=lambda _:None)
            collector = Collector([ROW], REGISTRY, tmp, client=client)
            a = collector.fetch_document(ROW, URL, 'release')
            b = collector.fetch_document(ROW, URL + '/alias', 'release')
            self.assertEqual(a['document_id'], b['document_id'])
            self.assertEqual(len(collector.queue), 1)

    def test_markup_only_change_does_not_requeue(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, 'test', transport=lambda u,h:(200,{'Content-Type':'text/html'},BODY if u == URL else BODY.replace(b'<p>',b'<p id="new-tracking-id">'),u),sleep=lambda _:None)
            collector = Collector([ROW], REGISTRY, tmp, client=client)
            a = collector.fetch_document(ROW, URL, 'release')
            b = collector.fetch_document(ROW, URL + '/alias', 'release')
            self.assertEqual(a['document_id'], b['document_id'])
            self.assertEqual(len(collector.queue), 1)
            self.assertNotEqual(a['manifest_path'], b['manifest_path'])
            self.assertNotEqual(a['raw_sha256'], b['raw_sha256'])
            self.assertTrue((Path(tmp) / a['manifest_path']).exists())
            self.assertTrue((Path(tmp) / b['manifest_path']).exists())

    def test_conditional_cache_and_missing_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            headers_seen = []
            def transport(url, headers):
                headers_seen.append(headers)
                return (304, {}, b'', url) if 'If-None-Match' in headers else (200, {'ETag': 'v1'}, BODY, url)
            client = Client(tmp, {'ir.example.test'}, 'test', transport=transport, sleep=lambda _: None)
            _, entry = client.get(URL, 0)
            self.assertEqual(client.get(URL, 0)[0], BODY)
            self.assertEqual(headers_seen[-1]['If-None-Match'], 'v1')
            (Path(tmp) / entry['body_path']).unlink()
            self.assertEqual(client.get(URL, 0)[0], BODY)
            self.assertNotIn('If-None-Match', headers_seen[-1])

    def test_rate_limit_and_host_backoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, 'test', transport=lambda u,h:(429, {'Retry-After':'120'},b'',u), sleep=lambda _:None)
            collector = Collector([ROW], REGISTRY, tmp, client=client)
            for expected in ('retry_later', 'host_backoff'):
                with self.assertRaisesRegex(FetchError, expected):
                    collector.get(ROW, URL)
            self.assertEqual(client.requests, 1)

    def test_sec_contact_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'data.sec.gov'}, 'test', transport=lambda u,h:(200, {}, b'{"cik":2}',u), sleep=lambda _:None)
            collector = Collector([ROW], REGISTRY, tmp, client=client)
            collector.sec(ROW)
            self.assertEqual(client.requests, 0)
            collector.sec_user_agent = 'test contact@example.test'
            collector.sec(ROW)
            self.assertEqual(collector.gaps[-1]['code'], 'invalid_submissions_response')

    def test_public_compatibility_and_sec_contact_headers_stay_separate(self):
        from research.earnings_calendar import CalendarClient, USER_AGENT
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            def transport(url, headers):
                ua = headers['User-Agent']
                seen.append((url, ua))
                if 'data.sec.gov' in url:
                    return 403, {}, b'', url
                supported = ua.startswith('Mozilla/5.0 (compatible; equities-research/')
                return (200 if supported else 403), {'Content-Type':'text/html'}, BODY, url
            collector = Collector([ROW], REGISTRY, tmp, sec_user_agent='Research contact@example.test')
            collector.client.transport = transport
            collector.client.sleep = lambda _: None
            self.assertEqual(collector.get(ROW, URL)[0], BODY)
            with self.assertRaisesRegex(FetchError, 'access_blocked'):
                collector.get(ROW, 'https://data.sec.gov/submissions/example.json')
            self.assertEqual(collector.get(ROW, URL + '/next')[0], BODY)
            self.assertEqual(seen[1][1], 'Research contact@example.test')
            self.assertEqual(seen[0][1], seen[2][1])
            calendar = CalendarClient(Path(tmp)/'calendar', {'ir.example.test'}, USER_AGENT,
                                      transport=transport, sleep=lambda _: None)
            with patch.object(calendar, '_request', side_effect=transport):
                self.assertEqual(calendar.get(URL)[0], BODY)

    def test_compatibility_header_does_not_accept_a_block_page(self):
        from research.fetch import PUBLIC_USER_AGENT
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, PUBLIC_USER_AGENT,
                            transport=lambda u,h:(200, {}, b'<title>Access Denied</title>',u),
                            sleep=lambda _:None)
            with self.assertRaisesRegex(FetchError, 'access_blocked'):
                client.get(URL)
            self.assertFalse(client.cache)

    def test_source_boundaries(self):
        for url in ('http://ir.example.test', 'https://other.test', 'https://a:b@ir.example.test', 'https://ir.example.test:99', 'https://ir.example.test/?token=x'):
            with self.assertRaises(FetchError):
                check_url(url, {'ir.example.test'}, resolve=False)
        with patch('research.fetch.socket.getaddrinfo', return_value=[(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaisesRegex(FetchError, 'non_public_address'):
                check_url(URL, {'ir.example.test'})
        with self.assertRaises(ValueError):
            validate_registry({'schema_version':1,'issuers':{'FAKE':{'cik':'2'}}}, [ROW])

    def test_budget_and_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, 'test', max_requests=1, transport=lambda u,h:(200, {}, BODY,u), sleep=lambda _:None)
            _, entry = client.get(URL)
            with self.assertRaisesRegex(FetchError, 'run_budget_exhausted'):
                client.get(URL + '/next')
            (Path(tmp) / entry['body_path']).write_bytes(b'changed')
            with self.assertRaisesRegex(FetchError, 'cache_integrity_error'):
                client.get(URL)

    def test_filings_selection(self):
        rows = [
            ('8-K','2026-09-19','5.02'), ('8-K','2026-09-18','2.02'),
            ('10-Q','2026-08-01',''), ('10-K','2026-02-01',''),
            ('10-K','2025-02-01',''), ('10-Q','2026-12-01','')]
        data = {'filings':{'recent':{'form':[r[0] for r in rows], 'filingDate':[r[1] for r in rows],
            'items':[r[2] for r in rows], 'accessionNumber':[str(i) for i in range(len(rows))]}}}
        self.assertEqual([r['form'] for r in select_filings(data,date(2026,9,20))], ['8-K','10-Q','10-K'])

    def test_calendar_explicit_dates(self):
        body = b'<html><script type="application/ld+json">{"@type":"Event","name":"Q3 earnings","startDate":"2026-10-22T16:30:00-04:00"}</script><table><tr><td>2026/10/15</td><td>Quarterly financial results</td></tr></table></html>'
        events = calendar_events(body, URL)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]['start'], '2026-10-15')
        self.assertIsNone(events[1]['fiscal_period'])
        self.assertEqual(calendar_events(b'<p>Published October 1, 2026. Earnings soon.</p>',URL), [])
        ics = b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Q3 Earnings\nDTSTART;TZID=America/New_York:20261022T163000\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(calendar_events(ics,URL,'ics')[0]['timezone_label'], 'America/New_York')

    def test_opt_in_date_blocks(self):
        body = b'<html><div>October 15, 2026 (Thu)</div><div>Example Q3 Earnings</div><div>November 10, 2026 (Tue)</div><div>Monthly sales</div></html>'
        self.assertEqual(len(calendar_events(body, URL, 'dated_lines')), 1)
        self.assertEqual(calendar_events(body, URL, 'dated_lines')[0]['start'], '2026-10-15')
        self.assertEqual(calendar_events(body, URL), [])

    def test_table_fiscal_and_exhibit_links(self):
        p = page(b'<html><ix:nonnumeric name="dei:DocumentPeriodEndDate">2026-06-30</ix:nonnumeric><table><tr><td>Release</td><td><a href="release.htm">exhibit</a></td><td>EX-99.1</td></tr></table></html>', URL)
        self.assertIn('\t', p.text)
        self.assertEqual(p.rows[0]['links'][0]['url'], 'https://ir.example.test/release.htm')
        self.assertEqual(p.fiscal['DocumentPeriodEndDate'], '2026-06-30')

    def test_pdf_and_announcement_are_not_full_transcripts(self):
        with patch('research.source_parse.shutil.which', return_value=None):
            self.assertEqual(extract(b'%PDF-fake','application/pdf',URL)[2], 'pdf_extractor_unavailable')
        self.assertEqual(kind_for('Company to report financial results', URL), 'earnings_page')
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, {'ir.example.test'}, 'test', transport=lambda u,h:(200,{'Content-Type':'text/html'},BODY,u),sleep=lambda _:None)
            collector = Collector([ROW], REGISTRY, tmp, client=client)
            doc = collector.fetch_document(ROW, URL, 'transcript', 'Prepared remarks')
            self.assertEqual(doc['kind'], 'prepared_remarks')

    def test_rss_does_not_assign_publication_date_as_event_date(self):
        body = b'<rss><channel><item><title>Q3 earnings</title><link>/call</link><pubDate>today</pubDate></item></channel></rss>'
        links = feed_links(body, URL)
        self.assertEqual(links[0]['url'],'https://ir.example.test/call')
        self.assertNotIn('start', links[0])

if __name__ == '__main__':
    unittest.main()
