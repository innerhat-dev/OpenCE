"""Keep timer smoke reports from passing with missing or contradictory evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macos_pb_timer_smoke import JOINED, active_checks, gated_checks, parse_status


class TimerSmokeEvidenceTests(unittest.TestCase):
    def snapshot(self, role, tick=3750, flags=5):
        common = role == 'client'
        return parse_status(
            f'performance options: flags={flags} ticks={tick} markers=0/5\r\n'
            f'PB timer: prefs={7 if common else 8} countdown={12 if common else 0} '
            f'beeps={4 if common else 0} minutes={1 if common else 0} items={0 if common else 5} last=2_minutes\r\n'
            f'PB timer items: rocket={0 if common else 1} camo={0 if common else 2} overshield={0 if common else 2}\r\n')

    def test_complete_status_required(self):
        self.assertEqual(self.snapshot('host')['items'], dict(rocket=1, camo=2, overshield=2))
        with self.assertRaises(ValueError):
            parse_status('performance options: flags=5 ticks=3750 markers=0/5\n')
        with self.assertRaises(ValueError):
            parse_status('PB timer: prefs=8 countdown=0 beeps=0 minutes=0 items=5 last=rocket\n')

    def test_actual_late_join_log_uses_past_tense(self):
        self.assertEqual(int(JOINED.search('10.02.26 20:07:56  joined the game in progress at game tick #2045')[1]), 2045)

    def test_each_category_and_each_local_preference_is_required(self):
        snapshots = {role: self.snapshot(role) for role in ('host', 'client')}
        self.assertTrue(all(active_checks(snapshots).values()))
        for group, key in [('items', 'rocket'), ('items', 'camo'), ('items', 'overshield')]:
            bad = copy.deepcopy(snapshots)
            bad['host'][group][key] = 0
            self.assertFalse(all(active_checks(bad).values()))
        for key in ('countdown', 'beeps', 'minutes'):
            bad = copy.deepcopy(snapshots)
            bad['host']['cues'][key] = 1
            self.assertFalse(all(active_checks(bad).values()))
            bad = copy.deepcopy(snapshots)
            bad['client']['cues'][key] = 0
            self.assertFalse(all(active_checks(bad).values()))
        bad = copy.deepcopy(snapshots)
        bad['client']['cues']['items'] = 1
        self.assertFalse(all(active_checks(bad).values()))

    def test_gate_requires_unchanged_counters_across_real_future_opportunities(self):
        before = {role: self.snapshot(role, flags=1) for role in ('host', 'client')}
        after = {role: self.snapshot(role, tick=5550, flags=1) for role in ('host', 'client')}
        self.assertTrue(all(gated_checks(before, after).values()))
        for role in ('host', 'client'):
            for key in after[role]['cues']:
                bad = copy.deepcopy(after)
                bad[role]['cues'][key] += 1
                self.assertFalse(all(gated_checks(before, bad).values()))
        after['host']['ticks'] = 5520
        self.assertFalse(all(gated_checks(before, after).values()))


if __name__ == '__main__':
    unittest.main()
