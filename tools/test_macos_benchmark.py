"""Ensure failed workloads cannot be reported as successful benchmarks."""
import io
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from tools.macos_benchmark import Console, prepare, summarize


class Connection:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.sent = []

    def settimeout(self, value):
        pass

    def recv(self, size):
        return next(self.replies, b'')

    def sendall(self, data):
        self.sent.append(data)


class WorkloadVerification(unittest.TestCase):
    def test_echo_is_not_an_execution_acknowledgement(self):
        console = Console(Connection([b'(print "bench_test")\r\n']), io.StringIO())
        with self.assertRaisesRegex(RuntimeError, 'disconnected'):
            console.wait('bench_test')

    def test_split_execution_acknowledgement_is_accepted(self):
        console = Console(Connection([b'(print "bench_test")\r\nbench_', b'test\r\n']), io.StringIO())
        console.wait('bench_test')

    def test_script_rejection_fails_even_if_marker_arrives(self):
        console = Console(Connection([b'not a valid function\r\nbench_test\r\n']), io.StringIO())
        with self.assertRaisesRegex(RuntimeError, 'rejected'):
            console.wait('bench_test')

    def test_console_buffer_overflow_is_refused_before_sending(self):
        connection = Connection([])
        console = Console(connection, io.StringIO())
        with self.assertRaises(ValueError):
            console.send('x' * 128)
        self.assertEqual(connection.sent, [])

    def test_run_uses_enabled_private_console_and_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maps = root / 'assets/maps'
            maps.mkdir(parents=True)
            for name in ('ui', 'a30'):
                (maps / (name + '.map')).write_bytes(b'authored fixture')
            output = root / 'run'
            with patch('tools.macos_benchmark.ROOT', root), patch.dict('os.environ', {'HALO_NETWORK_TEST': 'host'}):
                env = prepare(output, ['a30'], 70, False, True, 43210)
                config = tomllib.loads((output / 'saves/config.toml').read_text())
                self.assertTrue(config['debug']['telnet_console'])
                self.assertEqual(config['debug']['telnet_console_port'], 43210)
                self.assertNotIn('HALO_NETWORK_TEST', env)
                self.assertFalse(config['network']['online'])
                self.assertFalse((output / 'data/maps').is_symlink())
                with self.assertRaises(FileExistsError):
                    prepare(output, ['a30'], 70, False, True, 43210)

    def test_empty_render_workload_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            frames = Path(temporary) / 'frames.csv'
            frames.write_text('frame_ms,draws,upload_bytes,footprint_mb,draw_ms\n16.6,0,0,10,0\n')
            with self.assertRaisesRegex(RuntimeError, 'No rendered frames'):
                summarize(frames)


if __name__ == '__main__':
    unittest.main()
