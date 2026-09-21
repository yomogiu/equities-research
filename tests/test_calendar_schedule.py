from datetime import datetime
import unittest
from research.calendar_schedule import due, quarter_key


class ScheduleTests(unittest.TestCase):
    def test_dst_and_delayed_runs_and_duplicate_trigger(self):
        # January 11 UTC is too early; July 11 UTC is 7 Eastern.
        self.assertFalse(due(datetime.fromisoformat('2027-01-01T11:00:00+00:00')))
        self.assertTrue(due(datetime.fromisoformat('2027-01-01T12:20:00+00:00')))
        summer = datetime.fromisoformat('2027-07-01T11:30:00+00:00')
        self.assertTrue(due(summer))
        self.assertEqual(quarter_key(summer), '2027-Q3')
        self.assertFalse(due(summer, '2027-Q3'))
        self.assertTrue(due(datetime.fromisoformat('2027-07-01T15:30:00+00:00')))
        self.assertFalse(due(datetime.fromisoformat('2027-07-02T12:30:00+00:00')))
        self.assertTrue(due(summer, '2027-Q3', manual=True))
