# MGE-LocalCompute

[![CI](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml/badge.svg?branch=ci)](https://github.com/MrGoulart3/MGE-LocalCompute/actions/workflows/ci.yml) · [Changelog](CHANGELOG.md)

O badge exibirá status após a publicação da branch `ci`. / The badge shows status after the `ci` branch is published.

[Verificação local / Local checks](.github/CONTRIBUTING.md)

[English](README.md) · **Português brasileiro**

Executa cálculos finitos em um PC Linux compartilhado preservando recursos para outras pessoas e para o desktop. Todos os projetos usam uma trava e um orçamento de recursos comuns. Requer Python 3.10+, Linux `/proc`, `nice` e `ionice`; sem pacotes Python adicionais.

## Instalação

Mantenha o checkout em `~/tools/MGE-LocalCompute` e acrescente `bin/` ao `PATH`. Os scripts localizam o checkout; não os copie isoladamente.

```bash
mkdir -p ~/.config/mge-localcompute
cp config.example.json ~/.config/mge-localcompute/config
chmod 600 ~/.config/mge-localcompute/config
export PATH="$HOME/tools/MGE-LocalCompute/bin:$PATH"
```

Edite o JSON: `state_dir` compartilhado, `project_root` permitido, threads e carga de dia/noite, RAM disponível, temperaturas, contagens de amostras, horários locais, intervalo de espera, idioma (`en` / `pt-BR`) e `notify_command` (lista de argumentos, exemplo `["avisar"]`). `MGE_CONFIG` escolhe outro arquivo. Padrão: cinco threads de dia, seis à noite, 3 GiB disponíveis e início até 78 °C; noite das 21h às 8h e último início da fila antes das 6h. Todos devem usar o mesmo diretório de estado. Sem sensor, novos cálculos ficam bloqueados, salvo configuração explícita de `allow_no_sensor`.

Crontab de exemplo (caminhos absolutos; fuso do sistema):

```cron
* * * * * /bin/bash "$HOME/tools/MGE-LocalCompute/bin/termico"
*/10 * * * * /bin/bash "$HOME/tools/MGE-LocalCompute/bin/fila_noturna"
```

## Uso

```bash
rodar_local 2 python3 calculation.py
rodar_local --carga
capacidade_pc
fila_noturna --add '1|proj-a|2|/caminho/projects/proj-a|python3 calculation.py'
fila_noturna --status
```

Formato: `prioridade|projeto|threads|diretório|comando shell`. Números menores vêm primeiro; empates preservam a ordem de inclusão. O diretório deve existir sob `project_root`. Comandos da fila são programas locais confiáveis, nunca entrada remota. Duplicatas têm IDs separados. Jobs destacados gravam `<id>.log` e `<id>.status.json` em `state_dir`. Se um worker cair, pode faltar o status: confira o log antes de repetir. Rode o despachante novamente para limpar registros concluídos. Execuções diretas aguardam recursos e preservam o código de saída. Encerrar o executor repassa TERM e CONT ao grupo, escalando se necessário. O orçamento depende das threads declaradas; não impõe limites reais de memória ou CPU ao programa. Comandos devem permanecer na sessão, sem virar daemons. Avisos opcionais informam a conclusão da fila sem alterar o código de saída registrado. O estado inclui cwd para o portal irmão e a proteção de sessões com jobs.

`capacidade_pc` informa OK / APERTADA / LOTADA usando `capacity_ram_ok_gb`, `capacity_ram_tight_gb`, `capacity_load_ok` e `capacity_load_tight`; calor e power-clamp impedem o veredito OK.

## Guarda térmica

Uma rodada por minuto. A partir de 85 °C por duas amostras, cria `PAUSA` automática e bloqueia novos cálculos. A partir de 90 °C, pausa um grupo por rodada, começando pela maior alocação de threads (tempo de CPU desempata). Até 75 °C por três amostras, retoma um grupo por rodada, começando pelo mais leve. Arquiva a pausa automática quando todos retornarem. Preserva pausas manuais e não retoma grupos pausados manualmente. Identidade de início do PID e sessão evitam registros obsoletos. Power-clamp também bloqueia novos jobs. Avisos configurados têm limite de um envio bem-sucedido por dia. A consulta periódica não substitui proteção térmica de hardware.

## Validação

```bash
python3 -m unittest discover -s tests -v
```

Testes usam estado isolado, processos falsos finitos e overrides explícitos: `TERMICO_TEMP`, `TERMICO_CLAMP`, `RODAR_LOCAL_TEMP`, `RODAR_LOCAL_DIR`, `TERMICO_DIR`, `FILA_FORCAR=1`, `MGE_HOUR`, `MGE_LOAD`, `MGE_RAM_GB`. Não use overrides no cron real. [Ajustes opcionais do sistema](docs/SYSTEM_TUNING.pt-BR.md) ficam separados da instalação. Exemplos químicos não foram incluídos.

Relacionados: [MGE-UAH-Orquestra](https://github.com/MrGoulart3/MGE-UAH-Orquestra), [MGE-AgentPortal](https://github.com/MrGoulart3/MGE-AgentPortal). MIT; veja [LICENSE](LICENSE).


## Guarda de RAM e capacidade por noite (2026-10-24)

Execute `guarda_ram` a cada minuto: abaixo de `guard_ram_mb` (padrão 1.500 MiB), encerra somente o grupo registrado com maior RAM residente somada. Envia TERM/CONT, espera até dez segundos e revalida identidade do PID/grupo antes de KILL. Processos não registrados ficam fora. `guarda_ram --dry-run` mostra a seleção sem sinais. Registra em `ram.log` e avisa pelo notificador configurado. A proteção térmica continua por pausas graduais.

Perfil atual: dia 5 threads/carga 6,5; noite 6/carga 7,5; RAM livre mínima de 3 GiB; partida até 78 °C. O arquivo explícito `NOITE_CHEIA` no estado compartilhado, contendo a data ISO da noite, libera `full_night_threads=7` e `full_night_load=8.5`; datas vencidas são ignoradas. A data da noite considera a subtração da hora de término noturna. Os comandos compartilham um registro único; overrides por comando só funcionam com `RODAR_LOCAL_TESTE=1`. Sem escrita no registro, o cálculo não começa.

`fila_prioridade_noite` organiza créditos de agentes separadamente dos cálculos de `fila_noturna`. Configure `NIGHT_PRIORITY_CONFIG` pelo exemplo `night-priority.example.json`, com o comando de recados seguros em lista de argumentos. Veja [filas noturnas](docs/NIGHT_QUEUES.md). A fila não abre uma IA diretamente; o recado entregue pode consumir créditos.
