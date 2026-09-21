"""Offline source recency boundaries, using fictitious evidence."""
from datetime import datetime, timedelta, timezone
import unittest

from research.freshness import assess_packet, policy, timestamp


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 21, tzinfo=timezone.utc)

    def packet(self, hours, kind='release', **changes):
        doc = {'source_url': 'https://example.com/fictitious', 'kind': kind,
               'retrieved_at': (self.now - timedelta(hours=hours)).isoformat()}
        doc.update(changes)
        return {'documents': [doc], 'freshness_policy': policy()}

    def state(self, packet):
        return assess_packet(packet, now=self.now)['documents'][0]['status']

    def test_event_and_annual_background_boundaries(self):
        self.assertEqual(self.state(self.packet(24)), 'fresh')
        self.assertEqual(self.state(self.packet(24.01)), 'stale')
        self.assertEqual(self.state(self.packet(720, 'annual_background')), 'fresh')
        self.assertEqual(self.state(self.packet(720.01, 'annual_background')), 'stale')
        self.assertEqual(self.state(self.packet(-1)), 'future_timestamp')

    def test_checked_time_precedes_local_save_and_does_not_get_reset_by_it(self):
        p = self.packet(0, checked_at=(self.now - timedelta(hours=25)).isoformat())
        self.assertEqual(self.state(p), 'stale')
        p['documents'][0]['checked_at'] = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(self.state(p), 'fresh')

    def test_invalid_missing_naive_and_timezone_normalization(self):
        for value in [None, '', 'invalid', '2026-09-21T00:00:00', True, float('nan')]:
            with self.subTest(value=value):
                self.assertIsNone(timestamp(value))
                self.assertEqual(self.state(self.packet(0, retrieved_at=value)), 'unknown')
        self.assertEqual(timestamp('2026-09-20T20:00:00-04:00'), self.now.isoformat())
        self.assertEqual(timestamp(self.now.timestamp()), self.now.isoformat())

    def test_current_policy_can_tighten_but_cannot_loosen_packet(self):
        p = self.packet(2)
        self.assertEqual(assess_packet(p, {'event_max_age_hours': 1}, self.now)['status'], 'recheck_required')
        p = self.packet(25)
        self.assertEqual(assess_packet(p, {'event_max_age_hours': 48}, self.now)['status'], 'recheck_required')
        for value in [[], {'unknown': 1}, {'event_max_age_hours': 0},
                      {'event_max_age_hours': True}, {'event_max_age_hours': float('inf')}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy(value)

    def test_empty_or_legacy_packet_never_ready(self):
        self.assertEqual(assess_packet({'documents': []}, now=self.now)['status'], 'recheck_required')
        p = self.packet(0)
        p.pop('freshness_policy')
        self.assertEqual(assess_packet(p, now=self.now)['status'], 'recheck_required')
