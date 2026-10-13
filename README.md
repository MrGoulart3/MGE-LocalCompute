# MGE-LocalCompute

**English** · [Português brasileiro](README.pt-BR.md)

Run finite computations on a shared Linux PC without consuming every thread or making the desktop unresponsive. All projects share one admission lock and one resource budget. Requires Python 3.10+, Linux `/proc`, `nice` and `ionice`; no Python packages.

## Install

Keep the checkout at `~/tools/MGE-LocalCompute`; add its `bin/` to `PATH`. Wrappers resolve the checkout directory: do not copy them separately.

```bash
mkdir -p ~/.config/mge-localcompute
cp config.example.json ~/.config/mge-localcompute/config
chmod 600 ~/.config/mge-localcompute/config
export PATH="$HOME/tools/MGE-LocalCompute/bin:$PATH"
```

Edit the JSON configuration: shared `state_dir`, permitted `project_root`, day/night thread and load limits, available RAM, temperatures, sampling counts, local hours, polling interval, language (`en` / `pt-BR`) and `notify_command` (argv array, e.g. `["avisar"]`). `MGE_CONFIG` selects another file. Defaults: four daytime threads, six nighttime threads, 3 GiB available RAM, admission at ≤75 °C; night 21:00–08:00, queue starts before 06:00. All users of the tools must select the same state directory. Missing temperature sensors block admission unless explicitly allowed by `allow_no_sensor`.

Example crontab (use absolute checkout paths; cron uses the system timezone):

```cron
* * * * * /bin/bash "$HOME/tools/MGE-LocalCompute/bin/termico"
*/10 * * * * /bin/bash "$HOME/tools/MGE-LocalCompute/bin/fila_noturna"
```

## Use

```bash
rodar_local 2 python3 calculation.py
rodar_local --carga
capacidade_pc
fila_noturna --add '1|proj-a|2|/path/to/projects/proj-a|python3 calculation.py'
fila_noturna --status
```

A queue record is `priority|project|threads|directory|shell command`; lower priority numbers go first, equal priorities preserve insertion order. The directory must exist under `project_root`. Queue commands are trusted local shell programs, never remote input. Duplicate entries retain separate IDs. Detached jobs write `<id>.log` and `<id>.status.json` in `state_dir`. A crashed queue worker may lack a status file: inspect its log before retrying. Run the dispatcher again to prune completed jobs. Manual foreground runs wait for resources and propagate the command's exit status. Termination forwards TERM and CONT to the managed group, then escalates if needed. The budget depends on declared threads; tools cannot enforce a program's actual memory or CPU consumption. Commands must remain within their session and not daemonize.

## Thermal guard

Run once per minute. At ≥85 °C for two consecutive samples, create an automatic `PAUSA` blocking new jobs. At ≥90 °C pause one owned process group per invocation, heaviest thread allocation first (CPU time breaks ties). At ≤75 °C for three samples, resume one group per invocation, lightest first. Archive the automatic pause after all managed groups resume. Never remove manual `PAUSA` or resume groups stopped manually. PID start times and session IDs protect against stale records. Power-clamp activity also blocks admission. Configured warnings are rate limited to one successful notification per day. These are polling tools: they do not replace hardware thermal protection.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

Tests use isolated runtime state, finite fake jobs and explicit overrides: `TERMICO_TEMP`, `TERMICO_CLAMP`, `RODAR_LOCAL_TEMP`, `RODAR_LOCAL_DIR`, `TERMICO_DIR`, `FILA_FORCAR=1`, `MGE_HOUR`, `MGE_LOAD`, `MGE_RAM_GB`. Overrides are for testing; keep them out of production cron. Optional [system tuning](docs/SYSTEM_TUNING.md) is separate from installation. No chemistry examples are bundled.

Related: [MGE-UAH-Orquestra](https://github.com/MrGoulart3/MGE-UAH-Orquestra), [MGE-AgentPortal](https://github.com/MrGoulart3/MGE-AgentPortal). MIT; see [LICENSE](LICENSE).
