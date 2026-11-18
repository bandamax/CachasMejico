import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class NetworkRecovery(unittest.TestCase):
    def setUp(self):
        self.previous = server.job.copy()
        server.cancel_import.clear()
        server.job.update(running=True, errors=[], message='')

    def tearDown(self):
        server.job.clear()
        server.job.update(self.previous)
        server.cancel_import.clear()

    def test_failed_servers_stop_national_import_at_first_state(self):
        with patch.object(server, 'import_state', side_effect=server.OverpassUnavailable('No disponible')) as importer:
            server.run_import('ALL')
        self.assertEqual(importer.call_count, 1)
        self.assertFalse(server.job['running'])
        self.assertIn('detenida', server.job['message'])
        self.assertEqual(server.job['errors'], ['No disponible'])

    def test_overpass_fallback_uses_bounded_timeout(self):
        with patch.object(server, 'remote', side_effect=[TimeoutError(), {'elements': []}]) as remote:
            self.assertEqual(server.overpass('query'), [])
        self.assertEqual(remote.call_count, 2)
        for call in remote.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 80)
            self.assertTrue(call.kwargs['cancellable'])

    def test_cancel_does_not_attempt_connection(self):
        server.cancel_import.set()
        with patch.object(server.subprocess, 'Popen') as process:
            with self.assertRaises(server.ImportCancelled):
                server.remote_bytes('https://example.invalid', cancellable=True)
        process.assert_not_called()

    def test_inegi_is_independent_of_overpass(self):
        with patch.object(server, 'download_denue') as denue, patch.object(server, 'import_state') as osm:
            server.run_import('ALL', source='denue')
        denue.assert_called_once()
        osm.assert_not_called()
        self.assertFalse(server.job['running'])

    def test_invalid_download_does_not_touch_existing_base(self):
        with patch.object(server, 'remote_bytes', return_value=b'<html>Unavailable</html>'), patch.object(server, 'import_denue') as importer:
            with self.assertRaisesRegex(ValueError, 'ZIP'):
                server.download_denue()
        importer.assert_not_called()

    def test_curl_process_is_killed_when_cancelled(self):
        class Process:
            killed = False
            returncode = None
            def communicate(self, input=None, timeout=None):
                if timeout is None: return b'', b''
                server.cancel_import.set()
                raise server.subprocess.TimeoutExpired('curl', timeout)
            def poll(self): return self.returncode
            def kill(self): self.killed = True; self.returncode = -1
        fake = Process()
        with patch.object(server.shutil, 'which', return_value='curl.exe'), patch.object(server.subprocess, 'Popen', return_value=fake):
            with self.assertRaises(server.ImportCancelled):
                server.remote_bytes('https://example.invalid', cancellable=True)
        self.assertTrue(fake.killed)

if __name__ == '__main__': unittest.main()
