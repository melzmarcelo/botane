"""A hora da CASA — nunca a do contêiner.

🔑 **Este erro já apareceu DUAS vezes, com dois anos de distância entre os
sintomas**, e é por isso que ele virou um módulo em vez de uma função dentro do
serviço que o descobriu primeiro:

1. **04/09/2026, o agendador do Omie**: quem configurava "buscar às 20h" tinha a
   busca disparada às 20h UTC — 17h em Brasília. A busca rodava; rodava três
   horas antes, e nunca havia registro no horário escolhido.
2. **22/09/2026, a tarja do site do cliente**: a casa fecha às 18:00, eram 15:25
   em Blumenau, e o site dizia *"Fechado · abre Qua 09:30"*. 15:25 aqui são
   18:25 em UTC, e o contêiner comparou com o relógio dele.

⚠️ **É INVISÍVEL em desenvolvimento**, e as duas vezes passaram por baterias
verdes: a máquina de casa está no mesmo fuso que o código presume, e todas as
suítes rodam local. Só aparece no ar, e só quem olha a tela percebe.

🔑 **O banco já resolvia do lado dele** desde sempre — `database.py` abre a
sessão em `America/Sao_Paulo`, então `current_date` e `now()` dentro do SQL
estão certos. O que faltava era o processo Python fazer o mesmo.
⚠️ **Por isso data em SQL não precisa vir para cá**: `current_date` no `WHERE`
já é a data da casa. Trazer a decisão para o Python seria criar o problema.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config import FUSO_DA_CASA

_avisou: list[bool] = []


def agora_da_casa() -> datetime:
    """`datetime` de agora no fuso da casa, com `tzinfo`.

    ⚠️ **Sem o banco de fusos, cai para -03:00 e AVISA.** `zoneinfo` lê a base do
    sistema operacional, e imagem enxuta não a traz. O Brasil não tem horário de
    verão desde 2019, então o deslocamento fixo acerta hoje — mas se ele voltar,
    o aviso no log é o que impede a descoberta pelo relatório errado. `tzdata`
    está no `requirements.txt` justamente para este caminho não ser usado.
    """
    try:
        return datetime.now(ZoneInfo(FUSO_DA_CASA))
    except Exception:  # noqa: BLE001 — fuso indisponível não derruba nada
        if not _avisou:
            print(f"[relogio] fuso {FUSO_DA_CASA} indisponível — usando -03:00 fixo. "
                  "Instale tzdata para o horário de verão ser respeitado.")
            _avisou.append(True)
        return datetime.now(timezone(timedelta(hours=-3)))


def hoje_da_casa() -> date:
    """A data de hoje na casa.

    ⚠️ **`date.today()` num servidor em UTC vira o dia SEGUINTE entre 21h e a
    meia-noite.** É uma janela de três horas por dia em que um catálogo entraria
    no ar cedo, um período venceria antes, e um relatório "de hoje" seria o de
    amanhã. Mais estreito que o erro da hora, e mais difícil de notar.
    """
    return agora_da_casa().date()
