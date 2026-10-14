"""Generate, parse, save and reload the real Apple configuration defaults."""
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from tools.test_input_bindings import PREFIX, PORT, ROOT, SDL

HARNESS = r'''
#include <stdio.h>
#include "port_config.h"
void platform_log(const char *format, ...) { (void)format; }
int main(int argc, char **argv) {
    const char *key = "input.mouse_sensitivity";
    double value = 0.225;
    if (argc > 1 && !config_write_numbers(&key, &value, 1)) return 2;
    printf("%.3f\n", config_real("input.mouse_sensitivity"));
    return 0;
}
'''

class AppleDefaults(unittest.TestCase):
    def test_defaults_and_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory/'prefix.h').write_text(PREFIX)
            (directory/'probe.c').write_text(HARNESS)
            for platform in ('mac', 'ios'):
                with self.subTest(platform=platform):
                    binary = directory/platform
                    flags = ['-DHALO_ANDROID=1', '-DHALO_MACOS=1']
                    if platform == 'ios': flags += ['-DHALO_IOS=1']
                    subprocess.run(['clang', '-std=gnu11', *flags, '-include', str(directory/'prefix.h'),
                        '-I'+str(PORT), '-I'+str(SDL/'include'), '-I'+str(ROOT/'port/third_party/tomlc17'),
                        str(directory/'probe.c'), str(PORT/'port_config.c'), str(ROOT/'port/third_party/tomlc17/tomlc17.c'),
                        '-L'+str(SDL/'lib'), '-lSDL3', '-o', str(binary)], check=True)
                    saves = directory/(platform+'-saves'); saves.mkdir()
                    env = {k:v for k,v in os.environ.items() if not k.startswith('HALO_')}
                    env.update(HALO_SAVE_ROOT=str(saves), HALO_CONFIG_ROOT=str(saves))
                    def run(*args):
                        return subprocess.check_output([str(binary), *args], env=env, text=True).strip()
                    self.assertEqual(run(), '0.100')
                    data = tomllib.loads((saves/'config.toml').read_text())
                    self.assertFalse(data['display']['viewmodel_shield'])
                    self.assertEqual(run('save'), '0.225')
                    self.assertEqual(run(), '0.225')
