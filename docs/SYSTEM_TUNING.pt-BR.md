# Ajustes opcionais do sistema

[English](SYSTEM_TUNING.md)

Estes são experimentos opcionais, não configurações obrigatórias da máquina. Escolha valores para seu hardware e sua carga de trabalho e confira o dispositivo de armazenamento e o kernel antes de alterar configurações. A instalação não executa estes comandos; cabe ao administrador decidir.

- **I/O:** consulte `/sys/block/<dispositivo>/queue/scheduler`. Se suportado, teste BFQ temporariamente com `sudo modprobe bfq` e `echo bfq | sudo tee /sys/block/<dispositivo>/queue/scheduler`. Anote o escalonador anterior e restaure da mesma forma. Substitua pelo dispositivo real localmente. Só torne permanente após medir a resposta do desktop.
- **Swap:** confira `sysctl vm.swappiness` e `swapon --show`. Como exemplo, teste temporariamente `sudo sysctl vm.swappiness=10`; `10` é um valor ilustrativo a adaptar à sua carga de trabalho. Restaure o valor anotado para desfazer. Swap comprimida em RAM pode reduzir latência do armazenamento, mas consome memória; escolha tamanho e serviço adequados à distribuição.
- **Turbo:** teste somente após verificar a refrigeração sob carga sustentada. Sistemas Intel compatíveis expõem `/sys/devices/system/cpu/intel_pstate/no_turbo` (1 desliga, 0 liga); anote e restaure o valor anterior. Outros drivers têm controles diferentes.
- **Serviços:** use `systemctl --type=service` para identificar os desnecessários. Desative somente serviços verificados individualmente; reverta com `sudo systemctl enable --now <serviço>`.

Meça resposta do desktop, RAM, swap e temperatura antes e depois de cada mudança. Resultados específicos de um PC não se transferem automaticamente a outro.
