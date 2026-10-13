"""Integration tests with isolated state and finite fake computations."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocalComputeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        cfg = {'state_dir': str(self.path / 'state'), 'project_root': str(self.path),
               'hot_samples': 1, 'cool_samples': 1, 'poll_seconds': 0.05,
               'day_threads': 3, 'night_threads': 3}
        self.config = self.path / 'config'
        self.config.write_text(json.dumps(cfg))
        self.env = os.environ | {'MGE_CONFIG': str(self.config), 'MGE_HOUR': '22',
                                 'MGE_LOAD': '0', 'MGE_RAM_GB': '8',
                                 'TERMICO_TEMP': '70', 'TERMICO_CLAMP': '0'}
        self.processes = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)
        state = self.path / 'state/state.json'
        if state.exists():
            for job in json.loads(state.read_text())['jobs']:
                try:
                    os.killpg(job['pid'], signal.SIGCONT)
                    os.killpg(job['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.tmp.cleanup()

    def call(self, tool, *args, **env):
        return subprocess.run([sys.executable, str(ROOT / 'localcompute.py'), tool, *args],
                              env=self.env | env, text=True, capture_output=True, timeout=5)

    def start(self, threads, duration):
        process = subprocess.Popen([sys.executable, str(ROOT / 'localcompute.py'),
                                    'rodar_local', str(threads), sys.executable, '-c',
                                    f'import time; time.sleep({duration})'],
                                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        return process

    def state(self):
        path = self.path / 'state/state.json'
        return json.loads(path.read_text()) if path.exists() else {'jobs': []}

    def wait_for(self, predicate):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.03)
        self.fail('Timed out waiting for a fake job')

    def test_concurrent_admission_and_signal_cleanup(self):
        heavy = self.start(3, 11)
        self.wait_for(lambda: len(self.state()['jobs']) == 1)
        light = self.start(1, 12)
        time.sleep(0.15)
        self.assertEqual(3, sum(job['threads'] for job in self.state()['jobs']))
        heavy.terminate()
        heavy.communicate(timeout=5)
        self.wait_for(lambda: any(job['threads'] == 1 for job in self.state()['jobs']))
        light.terminate()
        light.communicate(timeout=5)
        self.assertEqual([], self.state()['jobs'])

    def test_thermal_steps_manual_pause_and_resume_order(self):
        self.start(2, 13)
        self.wait_for(lambda: len(self.state()['jobs']) == 1)
        self.start(1, 14)
        self.wait_for(lambda: len(self.state()['jobs']) == 2)
        directory = self.path / 'state'
        self.assertEqual(0, self.call('termico', TERMICO_TEMP='85').returncode)
        self.assertTrue((directory / 'PAUSA').exists())
        self.assertFalse(any(job['paused'] for job in self.state()['jobs']))
        self.call('termico', TERMICO_TEMP='90')
        self.assertEqual([2], [job['threads'] for job in self.state()['jobs'] if job['paused']])
        self.call('termico', TERMICO_TEMP='91')
        self.assertTrue(all(job['paused'] for job in self.state()['jobs']))
        self.call('termico', TERMICO_TEMP='75')
        self.assertEqual([2], [job['threads'] for job in self.state()['jobs'] if job['paused']])
        self.call('termico', TERMICO_TEMP='75')
        self.assertFalse((directory / 'PAUSA').exists())
        (directory / 'PAUSA').write_text('MANUAL')
        self.call('termico', TERMICO_TEMP='70')
        self.assertEqual('MANUAL', (directory / 'PAUSA').read_text())
        job = self.state()['jobs'][0]
        os.killpg(job['pid'], signal.SIGSTOP)
        self.call('termico', TERMICO_TEMP='90')
        self.assertFalse(self.state()['jobs'][0]['paused'])
        self.call('termico', TERMICO_TEMP='70')
        self.assertIn('T', Path(f'/proc/{job["pid"]}/stat').read_text().rsplit(')', 1)[1].split()[0])
        os.killpg(job['pid'], signal.SIGCONT)

    def test_queue_duplicate_jobs_and_failed_exit_status(self):
        line = f'1|proj-a|1|{self.path}|sleep 0.17; exit 7'
        for _ in range(2):
            self.assertEqual(0, self.call('fila_noturna', '--add', line).returncode)
        self.call('fila_noturna', MGE_HOUR='12')
        self.assertEqual(2, len(self.state()['queue']))
        self.call('fila_noturna', FILA_FORCAR='1')
        self.wait_for(lambda: len(list((self.path / 'state').glob('*.status.json'))) == 2)
        self.assertEqual([], self.state()['queue'])
        for path in (self.path / 'state').glob('*.status.json'):
            self.assertEqual(7, json.loads(path.read_text())['exit_code'])

    def test_thermal_notifications_are_rate_limited(self):
        notifier = self.path / 'notify'
        recorded = self.path / 'notifications.txt'
        notifier.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "' + str(recorded) + '"\n')
        notifier.chmod(0o755)
        cfg = json.loads(self.config.read_text()) | {'notify_command': [str(notifier)]}
        self.config.write_text(json.dumps(cfg))
        self.assertEqual(0, self.call('termico', TERMICO_TEMP='92').returncode)
        self.assertEqual(0, self.call('termico', TERMICO_TEMP='93').returncode)
        self.assertEqual(['CPU hot'], recorded.read_text().splitlines())

    def test_reject_paths_outside_root_and_invalid_limits(self):
        self.assertEqual(2, self.call('fila_noturna', '--add', '1|proj-a|1|/tmp|true').returncode)
        self.assertEqual(2, self.call('rodar_local', '9', 'true').returncode)
        self.config.write_text('{"hot_samples": 0}')
        self.assertEqual(2, self.call('termico').returncode)

    def test_clamp_blocks_admission_and_language(self):
        result = self.call('capacidade_pc', TERMICO_CLAMP='1')
        self.assertIn('TIGHT', result.stdout)
        self.assertIn('FULL', self.call('capacidade_pc', MGE_RAM_GB='1').stdout)
        cfg = json.loads(self.config.read_text()) | {'language': 'pt-BR'}
        self.config.write_text(json.dumps(cfg))
        self.assertIn('Capacidade: OK', self.call('capacidade_pc').stdout)


if __name__ == '__main__':
    unittest.main()
