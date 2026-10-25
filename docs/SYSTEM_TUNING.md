# Optional system tuning

[Português brasileiro](SYSTEM_TUNING.pt-BR.md)

Check the actual storage device and kernel before changing settings. No commands here run during installation; an administrator makes these choices.

- **I/O:** inspect `/sys/block/<device>/queue/scheduler`. Where supported, test BFQ temporarily with `sudo modprobe bfq` and `echo bfq | sudo tee /sys/block/<device>/queue/scheduler`. Record the previous scheduler; restore it the same way. Substitute the real device locally. Persist only after measuring responsiveness.
- **Swap:** inspect `sysctl vm.swappiness` and `swapon --show`. Test `sudo sysctl vm.swappiness=10`; restore the recorded value to roll back. A compressed RAM swap device can help storage latency but still consumes RAM; select its size and service for your distribution.
- **Turbo:** only test after verifying cooling under sustained load. Supported Intel systems expose `/sys/devices/system/cpu/intel_pstate/no_turbo` (1 disables, 0 enables); save and restore the previous value. Other drivers have different controls.
- **Services:** use `systemctl --type=service` to identify genuinely unused services. Disable only individually verified services; restore with `sudo systemctl enable --now <service>`.

Measure desktop responsiveness, RAM, swap and temperature before and after each change. Hardware-specific results do not transfer automatically to another PC.


## Runtime protection updated 2026-10-24

Calibrated defaults are configurable, not hardware recommendations for every machine: day 5 threads/load 6.5, night 6/load 7.5, startup ≤78 °C and at least 3 GiB available. A dated NOITE_CHEIA explicitly enables the configured 7-thread/load-8.5 profile. Keep exactly one shared state directory; production overrides must use a common configuration rather than environment-specific registries. Without write access, admission must fail.

Schedule `termico` and `guarda_ram` once per minute. The former pauses/resumes owned process groups gradually; the latter terminates the largest registered resident-memory consumer below 1,500 MiB available. Both validate ownership through PID start time and session identity. Configure notifications through an argv command that routes to the owning space and a quiet-hours notifier when desired. No real pane, topic or account is bundled. The RAM guard is a last resort and does not replace cgroup limits: lightweight ML jobs can additionally use `systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0` inside `rodar_local` when supported locally.

Production calculations remain remote. Independent long jobs can use `setsid nohup ... < /dev/null` with explicit logs, but never bypass resource admission. Keep the agent credit queue in [NIGHT_QUEUES.md](NIGHT_QUEUES.md) separate from local compute admission.
