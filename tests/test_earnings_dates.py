"""Fictitious earnings calendar fixtures, never real company research."""
import unittest

from research.earnings_dates import parse_events

URL = 'https://example.invalid/investors/calendar'


class EarningsDatesTests(unittest.TestCase):
    def parse(self, text, format='html'):
        return parse_events(text, URL, format)

    def test_structured_offset_and_explicit_period(self):
        events = self.parse('''<script type="application/ld+json">{"@graph":[
        {"@type":"Event","name":"Example FY2026-Q3 earnings call","startDate":"2026-10-28T17:00:00-04:00"},
        {"@type":"Event","name":"Investor conference","startDate":"2026-10-22"}]}</script>''')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['fiscal_period'], 'FY2026-Q3')
        self.assertEqual(events[0]['start'], '2026-10-28T17:00:00-04:00')
        self.assertIn('startDate', events[0]['evidence_excerpt'])

    def test_publication_and_quarter_end_are_not_event_dates(self):
        events = self.parse('''<p>September 12, 2026 — Example will report financial results for the quarter ended September 30, 2026 on October 28, 2026.</p>''')
        self.assertEqual([e['start'] for e in events], ['2026-10-28'])
        self.assertIsNone(events[0]['fiscal_period'])
        self.assertEqual(self.parse('<p>Example reports financial results for the quarter ended September 30, 2026.</p>'), [])
        self.assertEqual(self.parse('<p>Example will report financial results for the quarter ended on September 30, 2026.</p>'), [])

    def test_announcement_without_date_is_not_bound_to_dateline(self):
        self.assertEqual(self.parse('<h1>Example to announce financial results</h1><p>October 1, 2026</p>'), [])
        self.assertEqual(self.parse('<p>October 1, 2026 — Example will report financial results shortly.</p>'), [])

    def test_two_dates_are_explicitly_uncertain(self):
        events = self.parse('<p>Example will report financial results on October 28, 2026 and host an earnings call on October 29, 2026.</p>')
        self.assertEqual({e['start'] for e in events}, {'2026-10-28', '2026-10-29'})
        self.assertTrue(all(e['date_status'] == 'candidate_multiple_dates' for e in events))

    def test_separate_scoped_sentences_confirm_two_events(self):
        events = self.parse('<p>Example will report financial results on October 28, 2026. Example will host an earnings call on October 29, 2026.</p>')
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e['date_status'] == 'issuer_published_announcement' for e in events))

    def test_ics_timezone_utc_all_day_and_cancelled(self):
        events = self.parse('''BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Example earnings call
DTSTART;TZID=America/New_York:20261103T170000
END:VEVENT
BEGIN:VEVENT
SUMMARY:Example annual financial results
DTSTART;VALUE=DATE:20261104
END:VEVENT
BEGIN:VEVENT
SUMMARY:Example earnings webcast
DTSTART:20261105T170000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Example earnings call cancelled
DTSTART:20261106T170000Z
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR''', 'ics')
        self.assertEqual([e['start'] for e in events], ['2026-11-03T17:00:00-05:00', '2026-11-04', '2026-11-05T17:00:00Z'])

    def test_table_rows_require_one_date_and_earnings_not_generic_quarter(self):
        events = self.parse('''<table><tr><td>October 28, 2026</td><td>Example earnings call</td></tr>
        <tr><td>September 30, 2026</td><td>Quarter ended financial results</td></tr>
        <tr><td>October 2, 2026</td><td>Q3 investor conference</td></tr>
        <tr><td>October 3, 2026 and October 4, 2026</td><td>Earnings results</td></tr></table>''')
        self.assertEqual([e['start'] for e in events], ['2026-10-28'])

    def test_calendar_blocks_english_chinese_japanese(self):
        events = self.parse('''<title>Financial calendar</title><div>28 October 2026</div><h3>Example earnings call</h3>
        <div>2026年11月5日</div><h3>第三季法人說明會</h3>
        <div>2026年11月6日 決算発表予定</div>''')
        self.assertEqual({e['start'] for e in events}, {'2026-10-28', '2026-11-05', '2026-11-06'})
        jp = next(e for e in events if e['start'] == '2026-11-06')
        self.assertEqual(jp['date_status'], 'issuer_published_tentative')

    def test_unscoped_nearby_dates_not_bound(self):
        self.assertEqual(self.parse('<p>October 28, 2026</p><h2>Earnings call</h2>'), [])
        self.assertEqual(self.parse('<title>Financial calendar</title><p>Published October 28, 2026</p><h2>Earnings call</h2>'), [])

    def test_calendar_published_date_inline_rejected(self):
        self.assertEqual(self.parse('<title>Financial calendar</title><p>Published October 28, 2026: Example earnings call</p>'), [])

    def test_ambiguous_card_adjacency_is_candidate(self):
        events = self.parse('<title>Financial calendar</title><h3>Example annual earnings call</h3><p>October 28, 2026</p><h3>Example interim earnings call</h3>')
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e['date_status'] == 'candidate_ambiguous_calendar_block' for e in events))

    def test_results_table_without_event_qualifier_is_candidate(self):
        events = self.parse('<table><tr><td>September 30, 2026</td><td>Financial results</td></tr></table>')
        self.assertEqual(events[0]['date_status'], 'candidate_unqualified_table_date')

    def test_no_year_no_date_inference(self):
        self.assertEqual(self.parse('<title>Financial calendar</title><p>October 28</p><h2>Q3 earnings call</h2>'), [])
        self.assertEqual(self.parse('<p>Example will report financial results tomorrow.</p>'), [])

    def test_tentative_and_weekday(self):
        events = self.parse('<p>Example plans to announce financial results on Wednesday, October 28, 2026 (tentative).</p>')
        self.assertEqual(events[0]['date_status'], 'issuer_published_tentative')

    def test_invalid_dates_fail_closed(self):
        self.assertEqual(self.parse('<p>Example will report financial results on February 30, 2026.</p>'), [])
        self.assertEqual(self.parse('<script type="application/ld+json">{"@type":"Event","name":"Earnings","startDate":"2026-02-30"}</script>'), [])


if __name__ == '__main__':
    unittest.main()
