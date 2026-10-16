# Optional system tuning

[Português brasileiro](SYSTEM_TUNING.pt-BR.md)

These are optional experiments, not required machine settings. Choose values for your hardware and workload, and check the actual storage device and kernel before changing settings. No commands here run during installation; an administrator makes these choices.

- **I/O:** inspect `/sys/block/<device>/queue/scheduler`. Where supported, test BFQ temporarily with `sudo modprobe bfq` and `echo bfq | sudo tee /sys/block/<device>/queue/scheduler`. Record the previous scheduler; restore it the same way. Substitute the real device locally. Persist only after measuring responsiveness.
- **Swap:** inspect `sysctl vm.swappiness` and `swapon --show`. As an example, temporarily test `sudo sysctl vm.swappiness=10`; `10` is an illustrative value to adapt to your workload. Restore the recorded value to roll back. A compressed RAM swap device can help storage latency but still consumes RAM; select its size and service for your distribution.
- **Turbo:** only test after verifying cooling under sustained load. Supported Intel systems expose `/sys/devices/system/cpu/intel_pstate/no_turbo` (1 disables, 0 enables); save and restore the previous value. Other drivers have different controls.
- **Services:** use `systemctl --type=service` to identify genuinely unused services. Disable only individually verified services; restore with `sudo systemctl enable --now <service>`.

Measure desktop responsiveness, RAM, swap and temperature before and after each change. Hardware-specific results do not transfer automatically to another PC.
