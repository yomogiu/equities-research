"""Fictional declared XBRL date transformations; no issuer source data."""
import unittest
from research.earnings_sequential_stages import _PeriodEnd


class SequentialDateTests(unittest.TestCase):
    def parse(self, text, transform=None, namespace='http://www.xbrl.org/inlineXBRL/transformation/2020-02-12'):
        attribute = '' if transform is None else ' format="datefmt:'+transform+'"'
        parser = _PeriodEnd()
        parser.feed('<html xmlns:datefmt="'+namespace+'"><body><ix:nonNumeric name="dei:DocumentPeriodEndDate"'+attribute+'>'+text+'</ix:nonNumeric></body></html>')
        return parser.values

    def test_declared_english_month_name_handles_nbsp_and_nested_span(self):
        self.assertEqual(self.parse('June&#160;<span>30</span>, 2040','date-monthname-day-year-en'), ['2040-06-30'])

    def test_declared_order_resolves_ambiguous_numeric_date(self):
        self.assertEqual(self.parse('03/04/2040','date-month-day-year'), ['2040-03-04'])
        self.assertEqual(self.parse('03/04/2040','date-day-month-year'), ['2040-04-03'])

    def test_declared_abbreviated_month_and_ordinal_day(self):
        self.assertEqual(self.parse('31st-Dec-40','date-day-monthname-year-en'), ['2040-12-31'])
        self.assertEqual(self.parse('JUN. 30th, 2040','date-monthname-day-year-en'), ['2040-06-30'])

    def test_declared_numeric_year_first(self):
        self.assertEqual(self.parse('2040/6/30','date-year-month-day'), ['2040-06-30'])

    def test_no_transform_accepts_only_iso(self):
        self.assertEqual(self.parse('2040-06-30'), ['2040-06-30'])
        with self.assertRaisesRegex(ValueError, 'requires a declared'):
            self.parse('June 30, 2040')

    def test_unknown_transform_or_namespace_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported declared'):
            self.parse('June 30, 2040','fictional-transform')
        with self.assertRaisesRegex(ValueError, 'namespace'):
            self.parse('June 30, 2040','date-monthname-day-year-en','https://fiction.invalid/transform')

    def test_invalid_calendar_and_conflicting_transform_are_rejected(self):
        with self.assertRaises(ValueError): self.parse('February 30, 2040','date-monthname-day-year-en')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.parse('June 30, 2040','date-day-monthname-year-en')

    def test_source_namespace_scope_restores_after_child_rebinding(self):
        parser = _PeriodEnd()
        parser.feed('<html xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12"><div xmlns:ixt="https://fiction.invalid"></div><ix:nonNumeric name="dei:DocumentPeriodEndDate" format="ixt:date-monthname-day-year-en">June 30, 2040</ix:nonNumeric></html>')
        self.assertEqual(parser.values, ['2040-06-30'])

    def test_legacy_registry_declared_alias(self):
        self.assertEqual(self.parse('June 30, 2040','datemonthdayyearen','http://www.xbrl.org/inlineXBRL/transformation/2015-02-26'), ['2040-06-30'])

    def test_extra_prose_is_not_silently_interpreted(self):
        with self.assertRaises(ValueError):
            self.parse('June 30, 2040 or September 30, 2040','date-monthname-day-year-en')


if __name__ == '__main__': unittest.main()
