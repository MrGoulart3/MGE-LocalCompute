"""Serial agent credit queue, independent from the local computation queue."""
from __future__ import annotations

import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def tick(cfg: dict, status: bool = False, dry: bool = False) -> None:
    """Dispatches at most one idle agent and waits for its completion marker."""
    directory = Path(cfg['state_dir']).expanduser() / 'night-priority'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        path = directory / 'queue.json'
        queue = json.loads(path.read_text()) if path.exists() else []
        active = directory / 'active.json'
        if status:
            print(json.dumps({'queue': queue, 'active': json.loads(active.read_text()) if active.exists() else None}))
            return
        if active.exists():
            job = json.loads(active.read_text())
            if not re.fullmatch(r'[A-Za-z0-9_-]+', job['space']):
                raise ValueError('Invalid active space')
            if not (directory / f"{job['space']}.feito").exists():
                # Timeout never frees an agent still running: prevent overlap.
                return
            if dry:
                return
            active.unlink()
        now = datetime.datetime.now()
        start, end = cfg.get('start_hour', 21), cfg.get('end_hour', 5)
        if not (start <= now.hour < end if start < end else now.hour >= start or now.hour < end):
            return
        state_root = directory.parent
        economy = state_root / 'ECONOMIA_ATE'
        paused = economy.exists() and float(economy.read_text()) > time.time()
        if paused or (state_root / 'PORTA_FECHADA').exists() or (directory / 'PAUSA').exists() or not queue:
            return
        meter = json.loads(Path(cfg['usage_cache']).expanduser().read_text())
        if not 0 <= time.time() - meter['timestamp'] / 1000 <= 1200 or meter['data']['fiveHourPercent'] >= cfg.get('max_percent', 95):
            return
        job = queue[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', job['space']) or not re.fullmatch(r'w[A-Za-z0-9]+:p[0-9]+', job['pane']):
            raise ValueError('Invalid queue entry')
        result = subprocess.run([cfg.get('herdr', 'herdr'), 'agent', 'list'], capture_output=True, text=True, timeout=30, check=True)
        agents = json.loads(result.stdout)['result']['agents']
        if not any(a['pane_id'] == job['pane'] and a.get('agent_status') in ('idle', 'done') for a in agents):
            return
        message = f"NIGHT PRIORITY: continue authorized pending tasks. When done, write {directory / (job['space'] + '.feito')}; no reply to the coordinator."
        print('DRYRUN' if dry else 'DISPATCH', job['space'])
        if dry:
            return
        command = cfg['send_command']
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError('send_command must be an argv list')
        result = subprocess.run([*command, job['pane'], message, '0'], env=os.environ | {'NAO_GUARDAR': '1'}, timeout=15, check=False)
        if result.returncode:
            return
        (directory / f"{job['space']}.feito").unlink(missing_ok=True)
        temporary = active.with_suffix('.tmp')
        temporary.write_text(json.dumps(job | {'started': time.time()}))
        temporary.replace(active)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(queue[1:]))
        temporary.replace(path)


def main() -> int:
    """Reads the operator-owned JSON configuration without loading credentials."""
    try:
        cfg = json.loads(Path(os.environ['NIGHT_PRIORITY_CONFIG']).expanduser().read_text())
        tick(cfg, '--status' in sys.argv, '--dry-run' in sys.argv or os.environ.get('DRYRUN') == '1')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
