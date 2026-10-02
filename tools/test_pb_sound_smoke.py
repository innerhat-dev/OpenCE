"""Verify the sound-runner evidence parser and opt-in controller workload."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from macos_pb_sound_smoke import counter_delta, network_samples, parse_status, phase_checks


INPUT_FIXTURE = r'''
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned long long Uint64;
typedef short SHORT;
typedef struct { short sThumbLX,sThumbLY,sThumbRX,sThumbRY; unsigned char bAnalogButtons[8]; } XINPUT_GAMEPAD;
enum { XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_B, XINPUT_GAMEPAD_X, XINPUT_GAMEPAD_Y,
       XINPUT_GAMEPAD_WHITE, XINPUT_GAMEPAD_BLACK, XINPUT_GAMEPAD_LEFT_TRIGGER, XINPUT_GAMEPAD_RIGHT_TRIGGER };
static Uint64 ticks;
static const char *setting;
static int test_input_holding_action;
static Uint64 test_input_holding_action_since;
static Uint64 SDL_GetTicks(void) { return ticks; }
static const char *config_string(const char *name) { (void)name; return setting; }
/* FUNCTIONS */
int main(int argc,char **argv) {
    if(argc!=3) return 1; setting=argv[1]; test_input_hold_action(atoi(argv[2]));
    for(ticks=0;ticks<60000;ticks+=16) {
        XINPUT_GAMEPAD pad={0}; test_input_gamepad(&pad);
        printf("%llu %d %d %d %d",ticks,pad.sThumbLY,pad.sThumbLX,pad.sThumbRX,pad.sThumbRY);
        for(int i=0;i<8;i++) printf(" %u",pad.bAnalogButtons[i]);
        putchar('\n');
    }
    return 0;
}
'''


class SoundInputWorkloadTests(unittest.TestCase):
    def test_original_bot_with_only_extra_switch_reload_presses(self):
        source = (ROOT / "port/linux/src/xinput_sdl.c").read_text()
        functions = "\n".join(block(source, signature) for signature in (
            "void test_input_hold_action(", "static void test_input_gamepad("))
        with tempfile.TemporaryDirectory(prefix="halo-sound-input-") as directory:
            path = Path(directory)
            fixture = path / "input.c"
            fixture.write_text(INPUT_FIXTURE.replace("/* FUNCTIONS */", functions))
            executable = path / "input"
            subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(fixture), "-o", str(executable)], check=True)

            def samples(mode, hold=0):
                result = subprocess.run([str(executable), mode, str(hold)], check=True, capture_output=True, text=True)
                return [list(map(int, line.split())) for line in result.stdout.splitlines()]

            bot, sound = samples("bot:17"), samples("sound:17")
            self.assertEqual(len(bot), len(sound))
            for original, extra in zip(bot, sound):
                self.assertEqual(original[:7] + original[9:], extra[:7] + extra[9:])
                self.assertEqual(original[7:9], [0, 0])
            for button in (5, 11, 12):  # Ordinary jump, grenade and fire remain exercised.
                self.assertTrue(any(row[button] for row in bot))
            for button, expected_range in ((7, range(4, 6)), (8, range(5, 7))):
                edges = sum(row[button] and (index == 0 or not sound[index - 1][button])
                            for index, row in enumerate(sound))
                self.assertIn(edges, expected_range)
            for row in samples("sound:17", hold=1):
                self.assertEqual(row[7], 255 if row[0] >= 1000 else 0)
                self.assertFalse(any(row[1:7] + row[8:]))
            self.assertTrue(all(not any(row[1:]) for row in samples("")))
            look = samples("look:17")
            self.assertTrue(any(row[3] or row[4] for row in look))
            self.assertTrue(all(not any(row[1:3] + row[5:]) for row in look))


class SoundSmokeEvidenceTests(unittest.TestCase):
    def test_complete_response_and_counter_checks(self):
        text = ("performance options: flags=8 ticks=100 markers=0/24\n"
                "PB sound voices: normal=100 movement=50 ready=4 | muted: movement=90 ready=0\n"
                "PB sound effects=2 particles=5 last_voice=12340001 last_tag=45670001 last_role=1\n")
        before = parse_status(text)
        after = parse_status(text.replace("ticks=100", "ticks=550").replace("normal=100", "normal=110")
                             .replace("movement=50", "movement=75").replace("ready=4", "ready=7")
                             .replace("movement=90", "movement=190"))
        delta, checks = phase_checks(before, after, 8)
        self.assertEqual(delta, {'voices': {'normal': 10, 'movement': 25, 'ready': 3},
                                 'muted': {'movement': 100, 'ready': 0}})
        self.assertTrue(all(checks.values()))
        after['muted']['ready'] = 1
        self.assertFalse(phase_checks(before, after, 8)[1]['ready_mute_correct'])
        after['voices']['normal'] = 0
        with self.assertRaises(ValueError):
            counter_delta(before, after)
        with self.assertRaises(ValueError):
            parse_status(text.split("PB sound effects=")[0])

    def test_tick_ammo_and_death_evidence(self):
        text = ("network test: tick 30 player 0: (1.000 2.000 3.000) h1.00/1.00 g2/2 w a0/0 f0 l0/0 as1/1 st0 thr0.90 2af:120 32b:72 s0 k0 d0 f0 t0 m0"
                " player 1: dead s0 k0 d1 f0 t0 m1 | items 12 | sent 30 received 25 corrected 0\n"
                "network test: tick 60 player 0: (2.000 2.000 3.000) h1.00/1.00 g2/2 w 2af:117 s0 k0 d0 f0 t0 m0"
                " player 1: (4.000 5.000 6.000) h1.00/1.00 g2/2 w 32b:72 s0 k0 d1 f0 t0 m1 | items 12 | sent 60 received 55 corrected 0\n")
        samples = network_samples(text + text)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]['players'][0]['weapons'], {'2af': 120, '32b': 72})
        self.assertTrue(samples[0]['players'][1]['dead'])
        self.assertFalse(samples[1]['players'][1]['dead'])
        self.assertEqual([sample['tick'] for sample in network_samples(text, 30)], [60])


if __name__ == '__main__':
    unittest.main()
