"""O que é "o período" — a única resposta do sistema.

O CMV nasceu mensal, e o mês estava escrito por dentro de quatro lugares
diferentes: o fechamento derivava o mês da competência, o painel de CMV abria
no dia 1, a tela inicial rotulava "Agosto de 2026" e o razão recusava
lançamento dizendo "o período de 08/2026 está fechado". Trocar o ritmo em um só
desses lugares faria o sistema discordar de si mesmo — a tela mostrando a
semana e o fechamento congelando o mês.

Aqui a pergunta é feita uma vez: **dado um dia, que período ele pertence?**

Três ritmos, escolhidos por loja em `parametros.ciclo_fechamento`:

* ``DIARIO``   — o período é o dia. Para quem confere o caixa toda noite.
* ``SEMANAL``  — a semana que termina no dia escolhido
  (``fechamento_dia_semana``, ISO: 1 = segunda … 7 = domingo).
* ``MENSAL``   — o mês, começando no dia ``dia_fechamento_cmv`` (1 = mês do
  calendário, que é o padrão e o comportamento de sempre).

⚠️ **A competência é sempre o PRIMEIRO DIA do período.** É o que a torna
comparável entre ritmos e o que faz a mudança não reescrever o passado: para o
mensal com dia 1, ela continua sendo o primeiro dia do mês, exatamente como
antes desta virada.
"""

from calendar import monthrange
from datetime import date, timedelta

DIARIO, SEMANAL, MENSAL = "DIARIO", "SEMANAL", "MENSAL"
CICLOS = (DIARIO, SEMANAL, MENSAL)

# Só para as frases. `date.isoweekday()` devolve 1 para segunda.
DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")

PADRAO = {"ciclo": MENSAL, "dia_semana": 7, "dia_mes": 1}


def config(cur, id_unidade: int) -> dict:
    """O ritmo desta loja. Loja sem linha de parâmetros usa o padrão.

    ⚠️ Devolve o padrão em vez de estourar: `parametros` é criada junto com a
    loja, mas uma base restaurada de backup antigo pode não ter a linha — e
    ficar sem CMV por falta de configuração seria uma punição desproporcional.
    """
    cur.execute(
        """SELECT ciclo_fechamento, fechamento_dia_semana, dia_fechamento_cmv
             FROM parametros WHERE id_unidade = %s""",
        (id_unidade,),
    )
    p = cur.fetchone()
    if not p:
        return dict(PADRAO)
    ciclo = (p["ciclo_fechamento"] or MENSAL).upper()
    return {
        "ciclo": ciclo if ciclo in CICLOS else MENSAL,
        "dia_semana": p["fechamento_dia_semana"] or 7,
        "dia_mes": p["dia_fechamento_cmv"] or 1,
    }


def periodo_do_dia(dia: date, ciclo: str = MENSAL, *,
                   dia_semana: int = 7, dia_mes: int = 1) -> tuple[date, date]:
    """O período (início, fim) que contém `dia`. Ambos inclusive."""
    if ciclo == DIARIO:
        return dia, dia

    if ciclo == SEMANAL:
        # Quantos dias faltam até o próximo dia de fechamento — zero se hoje já
        # é ele, porque o dia do fechamento pertence à semana que ele encerra.
        falta = (dia_semana - dia.isoweekday()) % 7
        fim = dia + timedelta(days=falta)
        return fim - timedelta(days=6), fim

    # MENSAL. `dia_mes` é onde o mês do CMV COMEÇA: 1 dá o mês do calendário,
    # 26 dá o ciclo 26/07–25/08 de quem fecha junto com o fornecedor.
    # ⚠️ Limitado a 28 no modelo de propósito: dia 30 não existe em fevereiro, e
    # um período que muda de tamanho conforme o mês faria a série não comparar.
    if dia.day >= dia_mes:
        inicio = dia.replace(day=dia_mes)
    else:
        anterior = dia.replace(day=1) - timedelta(days=1)
        inicio = anterior.replace(day=min(dia_mes, monthrange(anterior.year, anterior.month)[1]))
    return inicio, _proximo_inicio_mensal(inicio, dia_mes) - timedelta(days=1)


def _proximo_inicio_mensal(inicio: date, dia_mes: int) -> date:
    seguinte = (inicio.replace(day=1) + timedelta(days=32)).replace(day=1)
    return seguinte.replace(day=min(dia_mes, monthrange(seguinte.year, seguinte.month)[1]))


def periodo_anterior(inicio: date, ciclo: str = MENSAL, *,
                     dia_semana: int = 7, dia_mes: int = 1) -> tuple[date, date]:
    """O período imediatamente antes daquele que começa em `inicio`."""
    return periodo_do_dia(inicio - timedelta(days=1), ciclo,
                          dia_semana=dia_semana, dia_mes=dia_mes)


def periodos_ate_hoje(ciclo: str, quantos: int, *, dia_semana: int = 7,
                      dia_mes: int = 1, hoje: date | None = None) -> list[tuple[date, date]]:
    """Os últimos `quantos` períodos, do mais recente para o mais antigo.

    É o que a tela oferece para fechar. Inclui o período CORRENTE — que ainda
    não terminou e não pode ser fechado, mas precisa aparecer: é o que a pessoa
    está olhando, e uma lista que começa no período passado parece atrasada.
    """
    hoje = hoje or date.today()
    atual = periodo_do_dia(hoje, ciclo, dia_semana=dia_semana, dia_mes=dia_mes)
    lista = [atual]
    while len(lista) < quantos:
        lista.append(periodo_anterior(lista[-1][0], ciclo,
                                      dia_semana=dia_semana, dia_mes=dia_mes))
    return lista


def rotulo(inicio: date, fim: date, ciclo: str = MENSAL) -> str:
    """Como o período se chama na tela.

    ⚠️ O rótulo é do PERÍODO, não da data: "semana de 18 a 24/08" diz o que
    "24/08" não diz. Um mês que não começa no dia 1 também não pode se chamar
    só "agosto" — quem lê precisa ver de onde até onde.
    """
    if inicio == fim:
        return inicio.strftime("%d/%m/%Y")

    # ⚠️ **O nome curto só vale para o período INTEIRO.** Um recorte de dez dias
    # dentro de agosto chamado "agosto de 2026" é a mesma mentira que a
    # movimentação já evita ao dizer se o número é congelado ou não: quem lê
    # manda adiante um pedaço achando que é o mês. Quando o intervalo não fecha
    # um ciclo, o rótulo mostra as duas pontas e deixa a conclusão com quem lê.
    inteiro = periodo_do_dia(inicio, ciclo, dia_semana=fim.isoweekday(),
                             dia_mes=inicio.day) == (inicio, fim)
    if ciclo == SEMANAL and inteiro:
        if inicio.month == fim.month:
            return f"semana de {inicio.strftime('%d')} a {fim.strftime('%d/%m/%Y')}"
        return f"semana de {inicio.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}"
    if ciclo == MENSAL and inteiro and inicio.day == 1:
        return f"{MESES[inicio.month - 1]} de {inicio.year}"
    return f"{inicio.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}"


def descricao_do_ciclo(ciclo: str, *, dia_semana: int = 7, dia_mes: int = 1) -> str:
    """Uma frase que confirma a configuração — o que a tela mostra ao escolher."""
    if ciclo == DIARIO:
        return "Fecha todo dia; cada período é um dia."
    if ciclo == SEMANAL:
        nome = DIAS_DA_SEMANA[(dia_semana - 1) % 7]
        # "todo domingo", mas "toda quarta": os cinco primeiros são femininos
        # (subentendem "feira"), sábado e domingo não.
        todo = "todo" if dia_semana >= 6 else "toda"
        return f"Fecha {todo} {nome}; cada período vai de {DIAS_DA_SEMANA[dia_semana % 7]} a {nome}."
    if dia_mes == 1:
        return "Fecha no fim do mês; cada período é o mês do calendário."
    return f"Fecha no dia {dia_mes - 1}; cada período vai do dia {dia_mes} ao dia {dia_mes - 1}."
