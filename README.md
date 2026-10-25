# MGE-LocalCompute

[![CI](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml) · [Changelog](CHANGELOG.md)

[Verificação local / Local checks](.github/CONTRIBUTING.md)

**English** · [Português brasileiro](README.pt-BR.md)

Run finite computations on a shared Linux host while reserving resources for other work. Invocations using the same state directory share one admission lock and one resource budget. Requires Python 3.10+, Linux `/proc`, `nice` and `ionice`; no Python packages.

## Install

Keep the checkout in any directory and run the following from its root to add `bin/` to the current shell's `PATH`. To make this permanent, add the resulting absolute path to your shell configuration. Wrappers resolve the checkout directory: do not copy them separately.

```bash
mkdir -p ~/.config/mge-localcompute
cp config.example.json ~/.config/mge-localcompute/config
chmod 600 ~/.config/mge-localcompute/config
export PATH="$PWD/bin:$PATH"
```

Edit the JSON configuration to suit your hardware and workload. `MGE_CONFIG` selects another file; omitted keys use the defaults in the table below. The example configuration contains all keys. Day/night are configurable resource windows in the system's local timezone. To use the same budget at all hours, give both windows the same thread and load limits. Invocations coordinating jobs under the same OS account must select the same `state_dir`; its default permissions are private to that account. A budget is local to one host.

| Option | Default | Meaning |
| --- | --- | --- |
| `day_threads`, `night_threads` | `5`, `6` | Total declared threads allowed in each window. |
| `day_load`, `night_load` | `6.5`, `7.5` | Maximum system load plus requested threads for admission. |
| `full_night_threads`, `full_night_load` | `7`, `8.5` | Budget enabled by a current dated `NOITE_CHEIA` file. |
| `guard_ram_mb` | `1500` | Available RAM threshold in MiB for the registered-process RAM guard. |
| `min_ram_gb` | `3` | Minimum available RAM in GiB for admission. |
| `start_temp` | `78` | Maximum temperature in °C for admission. |
| `block_temp`, `hot_samples` | `85`, `2` | Temperature in °C and consecutive samples before automatically blocking admission. Power-clamp activity also counts as a hot sample. |
| `stop_temp` | `90` | Temperature in °C at which to pause one managed process group per guard invocation. |
| `resume_temp`, `cool_samples` | `75`, `3` | Maximum temperature in °C and consecutive samples without power-clamp before resuming groups. |
| `warn_temp` | `92` | Temperature in °C for optional warnings, limited to one successful notification per local calendar day. |
| `night_start`, `night_end` | `21`, `8` | Start hour (inclusive) and end hour (exclusive) of the night budget; supports crossing midnight. Equal start/end hours mean a full-day window. |
| `queue_end` | `6` | Exclusive end hour for queued job starts, beginning at `night_start`; independent of `night_end`. Equal start/end hours mean a full-day window. |
| `poll_seconds` | `60` | Wait between foreground admission attempts; guard and dispatcher schedules are chosen separately. |
| `state_dir` | `~/.local/state/mge-localcompute` | Shared runtime state for coordinating invocations. |
| `project_root` | `~/projects` | Permitted parent directory for queued jobs; choose any existing directory. |
| `notify_command` | `[]` | Optional executable and arguments, e.g. `["notify-send"]` if installed; title and message are appended as two arguments. |
| `language` | `"en"` | Operational message language: `"en"` or `"pt-BR"`. |
| `allow_no_sensor` | `false` | Whether to admit work when a supported temperature sensor is unavailable. |
| `capacity_ram_ok_gb`, `capacity_ram_tight_gb` | `4`, `2.5` | Available RAM thresholds in GiB for the capacity report. |
| `capacity_load_ok`, `capacity_load_tight` | `5`, `6.5` | System load thresholds for the capacity report. |

These values are starting defaults, not machine requirements. Temperatures must satisfy `resume_temp ≤ start_temp < block_temp < stop_temp ≤ warn_temp`; sampling counts and thread budgets must be positive integers, and hours must be integers from 0 to 23. Temperature detection reads Linux hwmon package or Tctl sensors; unavailable sensors block admission by default.

Example crontab (replace `/path/to/MGE-LocalCompute` with your absolute checkout path; choose frequencies for your workload and cooling; cron uses the system timezone):

```cron
* * * * * /bin/bash "/path/to/MGE-LocalCompute/bin/termico"
*/10 * * * * /bin/bash "/path/to/MGE-LocalCompute/bin/fila_noturna"
```

## Use

The existing command names are Portuguese: `rodar_local` means “run locally”, `capacidade_pc` means “PC capacity”, `fila_noturna` means “night queue”, and `termico` means “thermal”. `PAUSA` means “pause” and is the admission-blocking marker file in `state_dir`.

The following finite example uses only Python's standard library. The fictitious `example-project` directory uses the default `project_root`; adjust it if you configured a different root.

```bash
rodar_local 1 python3 -c 'print(sum(range(1000000)))'
rodar_local --carga
capacidade_pc
mkdir -p "$HOME/projects/example-project"
fila_noturna --add "1|example-project|1|$HOME/projects/example-project|python3 -c 'print(sum(range(1000000)))'"
fila_noturna --status
```

A queue record is `priority|project|threads|directory|shell command`; lower priority numbers go first, equal priorities preserve insertion order. The directory must exist under `project_root`. Queue commands are trusted local shell programs, never remote input. Duplicate entries retain separate IDs. Detached jobs write `<id>.log` and `<id>.status.json` in `state_dir`. A crashed queue worker may lack a status file: inspect its log before retrying. Run the dispatcher again to prune completed jobs. Manual foreground runs wait for resources and propagate the command's exit status. Termination forwards TERM and CONT to the managed group, then escalates if needed. The budget depends on declared threads; tools cannot enforce a program's actual memory or CPU consumption. Commands must remain within their session and not daemonize. Optional notifications report queue completion without changing its recorded exit code. Managed state includes each job's working directory (`cwd`) for optional integrations such as portals and idle-session checks.

`capacidade_pc` reports OK / TIGHT / FULL using `capacity_ram_ok_gb`, `capacity_ram_tight_gb`, `capacity_load_ok` and `capacity_load_tight`; heat and power-clamp prevent an OK verdict.

## Thermal guard

Schedule `termico` at an interval appropriate for your cooling; the crontab above illustrates one-minute sampling. At `block_temp` or above for `hot_samples` consecutive samples, create an automatic `PAUSA` blocking new jobs. At `stop_temp` or above, pause one owned process group per invocation, heaviest thread allocation first (CPU time breaks ties). At `resume_temp` or below for `cool_samples` samples without power-clamp, resume one group per invocation, lightest first. Archive the automatic pause after all managed groups resume. Never remove manual `PAUSA` or resume groups stopped manually. PID start times and session IDs protect against stale records. Power-clamp activity also blocks admission. Warnings at `warn_temp` or above are rate limited to one successful notification per day. Sampling counts depend on how often you run the guard. These are polling tools: they do not replace hardware thermal protection.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

Tests use isolated runtime state, finite fake jobs and explicit overrides: `TERMICO_TEMP`, `TERMICO_CLAMP`, `RODAR_LOCAL_TEMP`, `RODAR_LOCAL_DIR`, `TERMICO_DIR`, `FILA_FORCAR=1`, `MGE_HOUR`, `MGE_LOAD`, `MGE_RAM_GB`. Overrides are for testing; keep them out of production cron. Optional [system tuning](docs/SYSTEM_TUNING.md) is separate from installation.

Related: [MGE-UAH-Orquestra](https://github.com/MrGoulart3/MGE-UAH-Orquestra), [MGE-AgentPortal](https://github.com/MrGoulart3/MGE-AgentPortal). MIT; see [LICENSE](LICENSE).


## RAM protection and dated night capacity (2026-10-24)

Run `guarda_ram` once a minute: below `guard_ram_mb` (default 1,500 MiB), it terminates the registered group with the largest aggregate resident memory, resumes a stopped group to deliver termination, waits up to ten seconds, then revalidates PID start time/group identity before escalation. It never targets an unregistered process. Use `guarda_ram --dry-run` to inspect selection without signals. Events go to `ram.log` and the configured notifier. Thermal behavior remains staged, not destructive.

Admission defaults now match the current profile: day 5 threads/load 6.5; night 6/load 7.5; minimum free RAM 3 GiB; start ≤78 °C. An explicit `NOITE_CHEIA` file in the shared state root, containing that night's ISO date, permits `full_night_threads=7` and `full_night_load=8.5`; stale dates are ignored. The night date is calculated after subtracting the night-end hour. All wrappers share one registry; per-command registry overrides are ignored unless `RODAR_LOCAL_TESTE=1`. A nonwritable registry fails rather than starting untracked work.

`fila_prioridade_noite` schedules agent credit usage separately from `fila_noturna` computation. Set `NIGHT_PRIORITY_CONFIG` to a copy of `night-priority.example.json`, including the safe message sender's argv. See [night queues](docs/NIGHT_QUEUES.md). It does not start an AI process itself; its delivered prompt may consume credits.
