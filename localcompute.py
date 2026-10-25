#!/usr/bin/env python3
"""Resource admission, a persistent local queue and gradual thermal protection."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

DEFAULTS = {
    'day_threads': 5, 'night_threads': 6, 'day_load': 6.5, 'night_load': 7.5,
    'min_ram_gb': 3, 'start_temp': 78, 'block_temp': 85, 'stop_temp': 90,
    'resume_temp': 75, 'warn_temp': 92, 'hot_samples': 2, 'cool_samples': 3,
    'night_start': 21, 'night_end': 8, 'queue_end': 6, 'poll_seconds': 60,
    'capacity_ram_ok_gb': 4, 'capacity_ram_tight_gb': 2.5,
    'capacity_load_ok': 5, 'capacity_load_tight': 6.5,
    'full_night_threads': 7, 'full_night_load': 8.5, 'guard_ram_mb': 1500,
    'state_dir': '~/.local/state/mge-localcompute', 'project_root': '~/projects',
    'notify_command': [], 'language': 'en', 'allow_no_sensor': False,
}


def config() -> dict:
    """Reads JSON configuration without executing shell fragments."""
    path = Path(os.environ.get('MGE_CONFIG', '~/.config/mge-localcompute/config')).expanduser()
    cfg = DEFAULTS | (json.loads(path.read_text()) if path.exists() else {})
    for key in ('day_threads', 'night_threads', 'full_night_threads', 'hot_samples', 'cool_samples'):
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(f'Invalid configuration / Configuração inválida: {key}')
    for key in ('night_start', 'night_end', 'queue_end'):
        if not isinstance(cfg[key], int) or not 0 <= cfg[key] <= 23:
            raise ValueError(f'Invalid hour / Hora inválida: {key}')
    for key in ('day_load', 'night_load', 'full_night_load', 'guard_ram_mb', 'min_ram_gb', 'poll_seconds'):
        if not isinstance(cfg[key], (int, float)) or cfg[key] <= 0:
            raise ValueError(f'Invalid limit / Limite inválido: {key}')
    if not all(isinstance(cfg[key], (int, float)) for key in ('resume_temp', 'start_temp', 'block_temp', 'stop_temp', 'warn_temp')):
        raise ValueError('Invalid temperatures / Temperaturas inválidas')
    if not cfg['capacity_ram_tight_gb'] <= cfg['capacity_ram_ok_gb'] or not cfg['capacity_load_ok'] <= cfg['capacity_load_tight']:
        raise ValueError('Invalid capacity thresholds / Limites de capacidade inválidos')
    if not cfg['resume_temp'] <= cfg['start_temp'] < cfg['block_temp'] < cfg['stop_temp'] <= cfg['warn_temp']:
        raise ValueError('Invalid temperature thresholds / Limites térmicos inválidos')
    if not isinstance(cfg['notify_command'], list) or not all(isinstance(x, str) for x in cfg['notify_command']):
        raise ValueError('notify_command must be an argv list / deve ser lista de argumentos')
    return cfg


def say(cfg: dict, en: str, pt: str) -> None:
    """Prints a localized operational message."""
    print(pt if cfg['language'] == 'pt-BR' else en, flush=True)


def state_dir(cfg: dict) -> Path:
    """Returns the private runtime directory, including legacy test overrides."""
    override = (os.environ.get('TERMICO_DIR') or os.environ.get('RODAR_LOCAL_DIR')) if os.environ.get('RODAR_LOCAL_TESTE') == '1' else None
    path = Path(override or cfg['state_dir']).expanduser()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def write_json(path: Path, data: object) -> None:
    """Replaces a state file atomically."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.replace(path)


def identity(pid: int) -> tuple[str, str] | None:
    """Reads process state and start time, rejecting stale PID reuse."""
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0], fields[19]
    except (OSError, IndexError):
        return None


def valid(job: dict) -> bool:
    """Checks that a job is still the session leader we launched."""
    current = identity(job['pid'])
    try:
        return bool(current and current[0] != 'Z' and current[1] == job['start']
                    and job['pid'] > 1 and os.getpgid(job['pid']) == job['pid'])
    except ProcessLookupError:
        return False


@contextlib.contextmanager
def locked(cfg: dict):
    """Serializes admission, queue updates and thermal signals."""
    directory = state_dir(cfg)
    with (directory / 'lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        path = directory / 'state.json'
        state = json.loads(path.read_text()) if path.exists() else {'jobs': [], 'queue': [], 'hot': 0, 'cool': 0}
        state['jobs'] = [job for job in state['jobs'] if valid(job)]
        yield directory, state
        write_json(path, state)


def hour() -> int:
    """Gets the local hour or the explicit test override."""
    return int(os.environ.get('MGE_HOUR', datetime.datetime.now().hour))


def window(start: int, end: int) -> bool:
    """Handles windows spanning midnight."""
    return start <= hour() < end if start < end else hour() >= start or hour() < end


def temperature() -> float | None:
    """Reads maximum package temperature, never substituting zero for missing sensors."""
    override = os.environ.get('TERMICO_TEMP', os.environ.get('RODAR_LOCAL_TEMP'))
    if override is not None:
        return float(override)
    readings = []
    for label in Path('/sys/class/hwmon').glob('hwmon*/temp*_label'):
        try:
            if 'package' in label.read_text().lower() or 'tctl' in label.read_text().lower():
                readings.append(float(label.with_name(label.name.replace('_label', '_input')).read_text()) / 1000)
        except (OSError, ValueError):
            continue
    return max(readings) if readings else None


def metrics() -> dict:
    """Reads available memory, load, temperature and power-clamp state."""
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    clamp = 0
    for path in Path('/sys/class/thermal').glob('cooling_device*/type'):
        try:
            if path.read_text().strip() == 'intel_powerclamp':
                clamp = max(clamp, int(path.with_name('cur_state').read_text()))
        except (OSError, ValueError):
            continue
    return {'load': float(os.environ.get('MGE_LOAD', os.getloadavg()[0])),
            'ram_gb': float(os.environ.get('MGE_RAM_GB', int(memory['MemAvailable'].split()[0]) / 1048576)),
            'temp': temperature(), 'clamp': int(os.environ.get('TERMICO_CLAMP', clamp))}


def fits(cfg: dict, directory: Path, state: dict, threads: int) -> bool:
    """Checks all resource gates while the admission lock is held."""
    night = window(cfg['night_start'], cfg['night_end'])
    maximum = cfg['night_threads' if night else 'day_threads']
    maximum_load = cfg['night_load' if night else 'day_load']
    stamp = (datetime.datetime.now() - datetime.timedelta(hours=cfg['night_end'])).date().isoformat()
    full = directory / 'NOITE_CHEIA'
    if night and full.exists() and full.read_text().strip() == stamp:
        maximum, maximum_load = cfg['full_night_threads'], cfg['full_night_load']
    data = metrics()
    return (not (directory / 'PAUSA').exists()
            and sum(job['threads'] for job in state['jobs']) + threads <= maximum
            and data['load'] + threads <= maximum_load and data['ram_gb'] >= cfg['min_ram_gb']
            and not data['clamp'] and (data['temp'] is not None and data['temp'] <= cfg['start_temp']
                                      or data['temp'] is None and cfg['allow_no_sensor']))


def spawn(cfg: dict, state: dict, threads: int, command: list[str], cwd: str | None = None,
          output=None) -> tuple[subprocess.Popen, dict]:
    """Starts and reserves an isolated process group inside the admission lock."""
    env = os.environ | {name: str(threads) for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')}
    process = subprocess.Popen(['nice', '-n', '19', 'ionice', '-c', '3', *command],
                               cwd=cwd, env=env, start_new_session=True, stdout=output,
                               stderr=subprocess.STDOUT if output else None)
    job = {'pid': process.pid, 'start': identity(process.pid)[1], 'threads': threads,
           'paused': False, 'cwd': str(Path(cwd or Path.cwd()).resolve())}
    state['jobs'].append(job)
    return process, job


def run(cfg: dict, threads: int, command: list[str]) -> int:
    """Waits for capacity, forwards termination and releases the reservation."""
    if not command or not 1 <= threads <= max(cfg['day_threads'], cfg['night_threads'], cfg['full_night_threads']):
        raise ValueError('Invalid command or thread count / Comando ou threads inválidos')
    while True:
        with locked(cfg) as (directory, state):
            if fits(cfg, directory, state, threads):
                process, job = spawn(cfg, state, threads, command)
                break
        say(cfg, 'Waiting for shared resources.', 'Aguardando recursos compartilhados.')
        time.sleep(cfg['poll_seconds'])

    def terminate(signum: int, _frame) -> None:
        if valid(job):
            os.killpg(process.pid, signal.SIGTERM)
            os.killpg(process.pid, signal.SIGCONT)
        raise SystemExit(128 + signum)

    previous = {sig: signal.signal(sig, terminate) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        return process.wait()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if valid(job):
            os.killpg(process.pid, signal.SIGTERM)
            os.killpg(process.pid, signal.SIGCONT)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        with locked(cfg) as (_, state):
            state['jobs'] = [item for item in state['jobs'] if item['pid'] != job['pid']]


def thermal(cfg: dict) -> None:
    """Blocks admission and pauses/resumes one owned group per invocation."""
    data = metrics()
    if data['temp'] is None:
        say(cfg, 'Temperature unavailable; no signals sent.', 'Temperatura indisponível; nenhum sinal enviado.')
        return
    with locked(cfg) as (directory, state):
        temp = data['temp']
        state['hot'] = state['hot'] + 1 if temp >= cfg['block_temp'] or data['clamp'] else 0
        state['cool'] = state['cool'] + 1 if temp <= cfg['resume_temp'] and not data['clamp'] else 0
        pause = directory / 'PAUSA'
        if state['hot'] >= cfg['hot_samples'] and not pause.exists():
            pause.write_text('AUTO thermal / térmico\n')
        running = [job for job in state['jobs'] if not job['paused'] and identity(job['pid'])[0] not in ('T', 't')]
        paused = [job for job in state['jobs'] if job['paused']]
        action = None
        if temp >= cfg['stop_temp'] and running:
            job = max(running, key=lambda item: (item['threads'], cpu_ticks(item['pid'])))
            action = signal.SIGSTOP
        elif state['cool'] >= cfg['cool_samples'] and paused:
            job = min(paused, key=lambda item: (item['threads'], cpu_ticks(item['pid'])))
            action = signal.SIGCONT
        if action is not None:
            try:
                os.killpg(job['pid'], action)
                job['paused'] = action == signal.SIGSTOP
                with (directory / 'thermal.log').open('a') as log:
                    log.write(f'{datetime.datetime.now().isoformat()} {action.name} {job["pid"]}\n')
            except ProcessLookupError:
                pass
        if state['cool'] >= cfg['cool_samples'] and not any(job['paused'] for job in state['jobs']) and pause.exists() and pause.read_text().startswith('AUTO '):
            archive = directory / 'pause-archive'
            archive.mkdir(exist_ok=True)
            pause.rename(archive / f'{time.time_ns()}.txt')
        today = datetime.date.today().isoformat()
        if temp >= cfg['warn_temp'] and state.get('warn_day') != today and cfg['notify_command']:
            if notify(cfg, 'CPU hot', 'CPU quente', f'{temp} C'):
                state['warn_day'] = today
    say(cfg, f'Temperature: {temp} C', f'Temperatura: {temp} C')


def cpu_ticks(pid: int) -> int:
    """Gets accumulated CPU time across a managed process group for tie-breaking."""
    total = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == pid:
                total += int(fields[11]) + int(fields[12])
        except (OSError, ValueError, IndexError):
            continue
    return total


def queue(cfg: dict, line: str | None, status: bool) -> None:
    """Adds or dispatches prioritized entries without dropping duplicates."""
    with locked(cfg) as (directory, state):
        if line is not None:
            priority, project, threads, cwd, command = line.split('|', 4)
            root = Path(cfg['project_root']).expanduser().resolve()
            folder = Path(cwd).expanduser().resolve()
            if not folder.is_dir() or not folder.is_relative_to(root) or not project or not command or int(priority) < 0 or not 1 <= int(threads) <= max(cfg['day_threads'], cfg['night_threads'], cfg['full_night_threads']):
                raise ValueError('Invalid queue entry / Entrada inválida')
            state['queue'].append({'priority': int(priority), 'project': project,
                                   'threads': int(threads), 'cwd': str(folder), 'command': command,
                                   'id': uuid.uuid4().hex})
            say(cfg, 'Queued.', 'Adicionado à fila.')
            return
        if status:
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return
        if not (window(cfg['night_start'], cfg['queue_end']) or os.environ.get('FILA_FORCAR') == '1'):
            return
        state['queue'].sort(key=lambda item: item['priority'])
        while state['queue']:
            entry = state['queue'][0]
            if not fits(cfg, directory, state, entry['threads']):
                break
            write_json(directory / f'{entry["id"]}.request.json', entry)
            with (directory / f'{entry["id"]}.log').open('w') as output:
                spawn(cfg, state, entry['threads'], [sys.executable, str(Path(__file__).resolve()), '_worker', str(directory / f'{entry["id"]}.request.json')], cwd=entry['cwd'], output=output)
            state['queue'].pop(0)


def notify(cfg: dict, en: str, pt: str, message: str) -> bool:
    """Sends bounded optional notifications without changing a computation status."""
    if not cfg['notify_command']:
        return False
    title = pt if cfg['language'] == 'pt-BR' else en
    try:
        subprocess.run([*cfg['notify_command'], title, message], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        say(cfg, 'Notification failed.', 'Falha no aviso.')
        return False


def worker(path: str) -> int:
    """Runs a detached queue command and records its exit code, even on failure."""
    request = Path(path)
    entry = json.loads(request.read_text())
    try:
        result = subprocess.run(['bash', '-c', entry['command']], cwd=entry['cwd'], check=False).returncode
    except OSError:
        result = 127
    write_json(request.with_name(f'{entry["id"]}.status.json'), {'exit_code': result})
    request.unlink()
    notify(config(), 'Queue job finished', 'Job da fila concluído', f'{entry["id"]}: exit_code={result}')
    return result


def group_rss(pid: int) -> int:
    """Sums resident memory in KiB for a registered process group."""
    total = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == pid:
                total += int(fields[21]) * os.sysconf('SC_PAGE_SIZE') // 1024
        except (OSError, ValueError, IndexError):
            continue
    return total


def ram_guard(cfg: dict, dry_run: bool = False) -> None:
    """Terminates only the largest owned group when available RAM is critical."""
    if metrics()['ram_gb'] * 1024 >= cfg['guard_ram_mb']:
        return
    with locked(cfg) as (directory, state):
        if not state['jobs']:
            return
        job = max(state['jobs'], key=lambda item: group_rss(item['pid']))
        print(json.dumps({'pid': job['pid'], 'rss_kib': group_rss(job['pid']), 'dry_run': dry_run}))
        if dry_run:
            return
        if valid(job):
            os.killpg(job['pid'], signal.SIGTERM)
            os.killpg(job['pid'], signal.SIGCONT)
            with (directory / 'ram.log').open('a') as stream:
                stream.write(f"{datetime.datetime.now().isoformat()} TERM {job['pid']} {job['cwd']}\n")
    deadline = time.monotonic() + 10
    while valid(job) and time.monotonic() < deadline:
        time.sleep(0.1)
    with locked(cfg) as (_, state):
        if valid(job):
            os.killpg(job['pid'], signal.SIGKILL)
    notify(cfg, 'RAM guard', 'Guarda de RAM', f"Local job terminated: {job['cwd']}")


def priority_night(cfg: dict, arguments: list[str]) -> int:
    """Uses the shared orchestration scheduler for the agent credit queue."""
    return subprocess.run([sys.executable, str(Path(__file__).with_name('night_priority.py')), *arguments], check=False).returncode


def main() -> int:
    """Dispatches the four public command wrappers."""
    parser = argparse.ArgumentParser(description='Shared PC tools / Ferramentas para PC compartilhado')
    parser.add_argument('tool', choices=['rodar_local', 'fila_noturna', 'termico', 'capacidade_pc', 'guarda_ram', 'fila_prioridade_noite', '_worker'])
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.tool == '_worker':
            return worker(args.args[0])
        cfg = config()
        if args.tool == 'guarda_ram':
            ram_guard(cfg, '--dry-run' in args.args or os.environ.get('DRYRUN') == '1')
        elif args.tool == 'fila_prioridade_noite':
            return priority_night(cfg, args.args)
        elif args.tool == 'termico':
            thermal(cfg)
        elif args.tool == 'fila_noturna':
            queue(cfg, args.args[1] if args.args and args.args[0] == '--add' else None, '--status' in args.args)
        elif args.tool == 'capacidade_pc' or args.args == ['--carga']:
            with locked(cfg) as (_, state):
                data = metrics() | {'threads': sum(job['threads'] for job in state['jobs'])}
            print(json.dumps(data))
            healthy = data['ram_gb'] >= cfg['capacity_ram_ok_gb'] and data['load'] <= cfg['capacity_load_ok'] and data['temp'] is not None and data['temp'] < cfg['block_temp'] and not data['clamp']
            tight = data['ram_gb'] >= cfg['capacity_ram_tight_gb'] and data['load'] <= cfg['capacity_load_tight']
            verdict = 'OK' if healthy else 'TIGHT' if tight else 'FULL'
            localized = {'OK': 'OK', 'TIGHT': 'APERTADA', 'FULL': 'LOTADA'}[verdict]
            say(cfg, f'Capacity: {verdict}', f'Capacidade: {localized}')
        else:
            return run(cfg, int(args.args[0]), args.args[1:])
    except (ValueError, IndexError, OSError) as error:
        print(f'Error / Erro: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
