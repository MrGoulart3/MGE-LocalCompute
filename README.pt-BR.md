# MGE-LocalCompute

[![CI](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml) · [Changelog](CHANGELOG.md)

[Verificação local / Local checks](.github/CONTRIBUTING.md)

[English](README.md) · **Português brasileiro**

Executa cálculos finitos em um host Linux compartilhado reservando recursos para outras atividades. Invocações com o mesmo diretório de estado usam uma trava e um orçamento de recursos comuns. Requer Python 3.10+, Linux `/proc`, `nice` e `ionice`; sem pacotes Python adicionais.

## Instalação

Mantenha o checkout em qualquer diretório e execute os comandos abaixo na raiz dele para acrescentar `bin/` ao `PATH` do shell atual. Para tornar a alteração permanente, adicione o caminho absoluto resultante à configuração do seu shell. Os scripts localizam o checkout; não os copie isoladamente.

```bash
mkdir -p ~/.config/mge-localcompute
cp config.example.json ~/.config/mge-localcompute/config
chmod 600 ~/.config/mge-localcompute/config
export PATH="$PWD/bin:$PATH"
```

Edite o JSON conforme seu hardware e sua carga de trabalho. `MGE_CONFIG` escolhe outro arquivo; chaves omitidas usam os padrões da tabela abaixo. A configuração de exemplo contém todas as chaves. Dia/noite são janelas de recursos configuráveis no fuso local do sistema. Para usar o mesmo orçamento em qualquer horário, defina limites iguais de threads e carga nas duas janelas. Invocações que coordenam jobs sob a mesma conta do sistema devem selecionar o mesmo `state_dir`; suas permissões padrão são privadas dessa conta. Cada orçamento se aplica a um único host.

| Opção | Padrão | Significado |
| --- | --- | --- |
| `day_threads`, `night_threads` | `5`, `6` | Total de threads declaradas permitido em cada janela. |
| `day_load`, `night_load` | `6.5`, `7.5` | Máximo da carga do sistema somada às threads solicitadas para admissão. |
| `full_night_threads`, `full_night_load` | `7`, `8.5` | Orçamento habilitado por `NOITE_CHEIA` com a data da noite atual. |
| `guard_ram_mb` | `1500` | Limite de RAM disponível em MiB para a guarda de processos registrados. |
| `min_ram_gb` | `3` | RAM disponível mínima em GiB para admissão. |
| `start_temp` | `78` | Temperatura máxima em °C para admissão. |
| `block_temp`, `hot_samples` | `85`, `2` | Temperatura em °C e amostras consecutivas antes de bloquear a admissão automaticamente. Atividade de power-clamp também conta como amostra quente. |
| `stop_temp` | `90` | Temperatura em °C para pausar um grupo gerenciado por invocação da guarda. |
| `resume_temp`, `cool_samples` | `75`, `3` | Temperatura máxima em °C e amostras consecutivas sem power-clamp antes de retomar grupos. |
| `warn_temp` | `92` | Temperatura em °C para avisos opcionais, limitados a uma notificação bem-sucedida por dia do calendário local. |
| `night_start`, `night_end` | `21`, `8` | Hora inicial inclusiva e final exclusiva do orçamento noturno; permite atravessar a meia-noite. Horas inicial e final iguais representam uma janela de dia inteiro. |
| `queue_end` | `6` | Hora final exclusiva para iniciar jobs da fila, a partir de `night_start`; independente de `night_end`. Horas inicial e final iguais representam uma janela de dia inteiro. |
| `poll_seconds` | `60` | Espera entre tentativas de admissão em primeiro plano; os agendamentos da guarda e do despachante são escolhidos separadamente. |
| `state_dir` | `~/.local/state/mge-localcompute` | Estado compartilhado para coordenar invocações. |
| `project_root` | `~/projects` | Diretório pai permitido para jobs da fila; escolha qualquer diretório existente. |
| `notify_command` | `[]` | Executável e argumentos opcionais, por exemplo `["notify-send"]` se instalado; título e mensagem são acrescentados como dois argumentos. |
| `language` | `"en"` | Idioma das mensagens operacionais: `"en"` ou `"pt-BR"`. |
| `allow_no_sensor` | `false` | Permite ou não admitir trabalho quando um sensor de temperatura compatível estiver indisponível. |
| `capacity_ram_ok_gb`, `capacity_ram_tight_gb` | `4`, `2.5` | Limites de RAM disponível em GiB para o relatório de capacidade. |
| `capacity_load_ok`, `capacity_load_tight` | `5`, `6.5` | Limites de carga do sistema para o relatório de capacidade. |

Esses valores são padrões iniciais, não requisitos da máquina. As temperaturas devem respeitar `resume_temp ≤ start_temp < block_temp < stop_temp ≤ warn_temp`; contagens de amostras e orçamentos de threads devem ser inteiros positivos, e horas devem ser inteiros de 0 a 23. A detecção térmica lê sensores de pacote ou Tctl do hwmon Linux; sensores indisponíveis bloqueiam a admissão por padrão.

Crontab de exemplo (substitua `/path/to/MGE-LocalCompute` pelo caminho absoluto do seu checkout; escolha frequências conforme a carga de trabalho e a refrigeração; fuso do sistema):

```cron
* * * * * /bin/bash "/path/to/MGE-LocalCompute/bin/termico"
*/10 * * * * /bin/bash "/path/to/MGE-LocalCompute/bin/fila_noturna"
```

## Uso

Os nomes existentes dos comandos são em português: `rodar_local` executa localmente, `capacidade_pc` informa a capacidade do PC, `fila_noturna` gerencia a fila noturna e `termico` executa a guarda térmica. `PAUSA` é o arquivo que bloqueia a admissão em `state_dir`.

O exemplo finito abaixo usa apenas a biblioteca padrão do Python. O diretório fictício `example-project` usa o `project_root` padrão; ajuste-o caso tenha configurado outra raiz.

```bash
rodar_local 1 python3 -c 'print(sum(range(1000000)))'
rodar_local --carga
capacidade_pc
mkdir -p "$HOME/projects/example-project"
fila_noturna --add "1|example-project|1|$HOME/projects/example-project|python3 -c 'print(sum(range(1000000)))'"
fila_noturna --status
```

Formato: `prioridade|projeto|threads|diretório|comando shell`. Números menores vêm primeiro; empates preservam a ordem de inclusão. O diretório deve existir sob `project_root`. Comandos da fila são programas locais confiáveis, nunca entrada remota. Duplicatas têm IDs separados. Jobs destacados gravam `<id>.log` e `<id>.status.json` em `state_dir`. Se um worker cair, pode faltar o status: confira o log antes de repetir. Rode o despachante novamente para limpar registros concluídos. Execuções diretas aguardam recursos e preservam o código de saída. Encerrar o executor repassa TERM e CONT ao grupo, escalando se necessário. O orçamento depende das threads declaradas; não impõe limites reais de memória ou CPU ao programa. Comandos devem permanecer na sessão, sem virar daemons. Avisos opcionais informam a conclusão da fila sem alterar o código de saída registrado. O estado inclui o diretório de trabalho (`cwd`) de cada job para integrações opcionais, como portais e verificações de sessões ociosas.

`capacidade_pc` informa OK / APERTADA / LOTADA usando `capacity_ram_ok_gb`, `capacity_ram_tight_gb`, `capacity_load_ok` e `capacity_load_tight`; calor e power-clamp impedem o veredito OK.

## Guarda térmica

Agende `termico` em um intervalo adequado à sua refrigeração; o crontab acima ilustra amostragem a cada minuto. A partir de `block_temp` por `hot_samples` amostras consecutivas, cria `PAUSA` automática e bloqueia novos cálculos. A partir de `stop_temp`, pausa um grupo por rodada, começando pela maior alocação de threads (tempo de CPU desempata). Até `resume_temp` por `cool_samples` amostras sem power-clamp, retoma um grupo por rodada, começando pelo mais leve. Arquiva a pausa automática quando todos retornarem. Preserva pausas manuais e não retoma grupos pausados manualmente. Identidade de início do PID e sessão evitam registros obsoletos. Power-clamp também bloqueia novos jobs. Avisos a partir de `warn_temp` têm limite de um envio bem-sucedido por dia. As contagens de amostras dependem da frequência de execução da guarda. A consulta periódica não substitui proteção térmica de hardware.

## Validação

```bash
python3 -m unittest discover -s tests -v
```

Testes usam estado isolado, processos falsos finitos e overrides explícitos: `TERMICO_TEMP`, `TERMICO_CLAMP`, `RODAR_LOCAL_TEMP`, `RODAR_LOCAL_DIR`, `TERMICO_DIR`, `FILA_FORCAR=1`, `MGE_HOUR`, `MGE_LOAD`, `MGE_RAM_GB`. Não use overrides no cron real. [Ajustes opcionais do sistema](docs/SYSTEM_TUNING.pt-BR.md) ficam separados da instalação.

Relacionados: [MGE-UAH-Orquestra](https://github.com/MrGoulart3/MGE-UAH-Orquestra), [MGE-AgentPortal](https://github.com/MrGoulart3/MGE-AgentPortal). MIT; veja [LICENSE](LICENSE).


## Guarda de RAM e capacidade por noite (2026-10-24)

Execute `guarda_ram` a cada minuto: abaixo de `guard_ram_mb` (padrão 1.500 MiB), encerra somente o grupo registrado com maior RAM residente somada. Envia TERM/CONT, espera até dez segundos e revalida identidade do PID/grupo antes de KILL. Processos não registrados ficam fora. `guarda_ram --dry-run` mostra a seleção sem sinais. Registra em `ram.log` e avisa pelo notificador configurado. A proteção térmica continua por pausas graduais.

Perfil atual: dia 5 threads/carga 6,5; noite 6/carga 7,5; RAM livre mínima de 3 GiB; partida até 78 °C. O arquivo explícito `NOITE_CHEIA` no estado compartilhado, contendo a data ISO da noite, libera `full_night_threads=7` e `full_night_load=8.5`; datas vencidas são ignoradas. A data da noite considera a subtração da hora de término noturna. Os comandos compartilham um registro único; overrides por comando só funcionam com `RODAR_LOCAL_TESTE=1`. Sem escrita no registro, o cálculo não começa.

`fila_prioridade_noite` organiza créditos de agentes separadamente dos cálculos de `fila_noturna`. Configure `NIGHT_PRIORITY_CONFIG` pelo exemplo `night-priority.example.json`, com o comando de recados seguros em lista de argumentos. Veja [filas noturnas](docs/NIGHT_QUEUES.md). A fila não abre uma IA diretamente; o recado entregue pode consumir créditos.
