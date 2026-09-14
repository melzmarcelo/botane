"""Reservas — a configuração da loja: janela de funcionamento e permanência.

O módulo inteiro é ligado por `parametros.reservas_ligado`, uma loja de cada
vez. Este arquivo cuida da **primeira tela**: quando a casa abre, até quando
aceita marcar, e quanto tempo cada refeição segura a mesa.

🔑 **Por que a permanência é o coração de uma tela de configuração.** Ela não
descreve a casa, ela DECIDE disponibilidade: é o que diz quando a mesa das 12h
volta a aparecer como livre. Curta demais vende mesa que ainda está ocupada;
longa demais recusa mesa vazia. Nenhum dos dois erros aparece na tela — os dois
aparecem no salão.

⚠️ **`dia_semana` é ISO: 1 = segunda … 7 = domingo.** É o mesmo formato de
`parametros.fechamento_dia_semana`, que já existia neste sistema, e o que
`extract(isodow from data)` devolve. NÃO é o `dow` do Postgres (0 = domingo) nem
o `Date.getDay()` do JavaScript. Duas convenções de dia da semana no mesmo
sistema não dão erro em lugar nenhum: só marcam no dia errado.
"""

from database import get_cursor  # noqa: F401  (re-exportado para quem importa daqui)

# 1 = segunda … 7 = domingo, na ordem em que a tela mostra.
DIAS = ((1, "Segunda"), (2, "Terça"), (3, "Quarta"), (4, "Quinta"),
        (5, "Sexta"), (6, "Sábado"), (7, "Domingo"))

# ⚠️ **Toda loja nasce FECHADA em todos os dias**, e é deliberado. O contrário —
# semear "segunda a sábado, 9h às 18h" — faria a casa ligar o módulo e a agenda
# passar a afirmar um horário que ninguém conferiu. Fechado não afirma nada e
# manda a pessoa exatamente para onde ela precisa ir: a tela de configuração,
# que diz o que falta.
_HORARIO_PADRAO = {"aberto": False, "abre": "09:00", "fecha": "18:00",
                   "ultima_reserva": "17:00"}

# ⚠️ As faixas de permanência JÁ nascem preenchidas, ao contrário dos dias. Elas
# não afirmam que a casa abre: só dizem quanto tempo uma refeição dura, o que é
# parecido em toda casa e é editável. Nascer vazio esconderia o conceito —
# ninguém procura uma tabela que não está lá.
_FAIXAS_PADRAO = (
    ("Café da manhã", "09:00", "11:00", 60),
    ("Almoço", "11:00", "15:00", 90),
    ("Lanche da tarde", "15:00", "23:59", 60),
)


def ligado(cur, id_unidade: int) -> bool:
    """Esta loja tem Reservas? Loja sem linha em `parametros` responde não.

    ⚠️ Loja sem linha não é erro: a linha nasce na primeira visita à tela de
    parâmetros. Sem ela vale o padrão do banco, que é desligado.
    """
    cur.execute("SELECT reservas_ligado FROM parametros WHERE id_unidade = %s", (id_unidade,))
    linha = cur.fetchone()
    return bool(linha and linha["reservas_ligado"])


def ligado_em_alguma_loja(cur) -> bool:
    """Alguma loja da casa tem Reservas ligado?

    🔑 **É esta a pergunta que o catálogo de permissões faz, e não "a loja
    ATUAL".** Papel é global — não tem loja —, então esconder `reservas.*`
    porque a loja do seletor não usa o módulo faria o catálogo de permissões
    mudar conforme a loja escolhida, e um papel montado numa loja pareceria
    quebrado na outra.
    """
    cur.execute("SELECT 1 FROM parametros WHERE reservas_ligado LIMIT 1")
    return cur.fetchone() is not None


def _garantir(cur, id_unidade: int) -> None:
    """Cria a configuração desta loja se ela ainda não existe.

    ⚠️ **Preguiçoso de propósito**, como `parametros`: semear na criação da loja
    obrigaria a lembrar disto em dois lugares, e o segundo lugar nasceria sem.
    Aqui, a primeira visita à tela resolve — inclusive para as lojas que já
    existiam antes do módulo.
    """
    cur.execute(
        "INSERT INTO reserva_config (id_unidade) VALUES (%s) ON CONFLICT DO NOTHING",
        (id_unidade,),
    )
    # Os sete dias sempre existem: a tela mostra a semana inteira, e dia que
    # falta na tabela seria dia que some da tela.
    for dia, _nome in DIAS:
        cur.execute(
            """INSERT INTO reserva_horarios (id_unidade, dia_semana, aberto, abre, fecha,
                                             ultima_reserva)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (id_unidade, dia, _HORARIO_PADRAO["aberto"], _HORARIO_PADRAO["abre"],
             _HORARIO_PADRAO["fecha"], _HORARIO_PADRAO["ultima_reserva"]),
        )
    # ⚠️ As faixas só são semeadas quando NÃO HÁ NENHUMA. Semear uma a uma com
    # `ON CONFLICT` faria a faixa que a casa apagou de propósito voltar sozinha
    # na visita seguinte — e ninguém entenderia por quê.
    cur.execute("SELECT count(*) AS n FROM reserva_permanencias WHERE id_unidade = %s",
                (id_unidade,))
    if cur.fetchone()["n"] == 0:
        for nome, de, ate, minutos in _FAIXAS_PADRAO:
            cur.execute(
                """INSERT INTO reserva_permanencias (id_unidade, nome, de, ate, minutos)
                   VALUES (%s, %s, %s, %s, %s)""",
                (id_unidade, nome, de, ate, minutos),
            )


def _hm(valor) -> str | None:
    """`time` do banco vira "HH:MM" — que é o que o `<input type=time>` fala."""
    return valor.strftime("%H:%M") if valor is not None else None


def obter(cur, id_unidade: int) -> dict:
    """A configuração inteira desta loja, pronta para a tela."""
    _garantir(cur, id_unidade)

    cur.execute(
        """SELECT aceita_online, confirmacao, teto_online, tolerancia_min, folga_min,
                  passo_min, antecedencia_min_horas, antecedencia_max_dias, cadastro_completo
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    config = dict(cur.fetchone())

    cur.execute(
        """SELECT dia_semana, aberto, abre, fecha, ultima_reserva
             FROM reserva_horarios WHERE id_unidade = %s ORDER BY dia_semana""",
        (id_unidade,),
    )
    nomes = dict(DIAS)
    horarios = [
        {"dia_semana": r["dia_semana"], "nome": nomes.get(r["dia_semana"], "?"),
         "aberto": r["aberto"], "abre": _hm(r["abre"]), "fecha": _hm(r["fecha"]),
         "ultima_reserva": _hm(r["ultima_reserva"])}
        for r in cur.fetchall()
    ]

    cur.execute(
        """SELECT id, nome, de, ate, minutos FROM reserva_permanencias
            WHERE id_unidade = %s ORDER BY de, id""",
        (id_unidade,),
    )
    faixas = [
        {"id": r["id"], "nome": r["nome"], "de": _hm(r["de"]), "ate": _hm(r["ate"]),
         "minutos": r["minutos"]}
        for r in cur.fetchall()
    ]

    return config | {
        "id_unidade": id_unidade,
        "ligado": ligado(cur, id_unidade),
        "horarios": horarios,
        "permanencias": faixas,
        # 🔑 **A tela precisa saber o que ainda falta**, e quem sabe é o
        # servidor. Sem nenhum dia aberto a agenda não responde nada, e a tela
        # tem de DIZER isso em vez de parecer pronta.
        "dias_abertos": sum(1 for h in horarios if h["aberto"]),
    }


def salvar(cur, id_unidade: int, body) -> dict:
    """Grava a configuração inteira — a tela manda tudo, e tudo é reescrito.

    ⚠️ **As faixas são REESCRITAS, não casadas linha a linha.** É a mesma
    decisão do `PUT /produtos/{id}/unidades` e dos itens da nota manual: casar
    linha a linha só abriria caminho para faixa órfã, e nada aqui é apontado por
    outra tabela — permanência é regra de cálculo, não é fato registrado.

    ⚠️ **Os horários são atualizados, não reescritos**: a chave é
    (loja, dia_semana) e os sete dias têm de continuar existindo. Apagar e
    reinserir faria a semana sumir por um instante dentro da transação, e
    qualquer erro no meio deixaria a loja sem horário nenhum.
    """
    _garantir(cur, id_unidade)

    cur.execute(
        """UPDATE reserva_config
              SET aceita_online = %s, confirmacao = %s, teto_online = %s,
                  tolerancia_min = %s, folga_min = %s, passo_min = %s,
                  antecedencia_min_horas = %s, antecedencia_max_dias = %s,
                  cadastro_completo = %s, atualizado_em = now()
            WHERE id_unidade = %s""",
        (body.aceita_online, body.confirmacao, body.teto_online, body.tolerancia_min,
         body.folga_min, body.passo_min, body.antecedencia_min_horas,
         body.antecedencia_max_dias, body.cadastro_completo, id_unidade),
    )

    for h in body.horarios:
        cur.execute(
            """UPDATE reserva_horarios
                  SET aberto = %s, abre = %s, fecha = %s, ultima_reserva = %s
                WHERE id_unidade = %s AND dia_semana = %s""",
            (h.aberto, h.abre, h.fecha, h.ultima_reserva, id_unidade, h.dia_semana),
        )

    cur.execute("DELETE FROM reserva_permanencias WHERE id_unidade = %s", (id_unidade,))
    for f in body.permanencias:
        cur.execute(
            """INSERT INTO reserva_permanencias (id_unidade, nome, de, ate, minutos)
               VALUES (%s, %s, %s, %s, %s)""",
            (id_unidade, f.nome.strip(), f.de, f.ate, f.minutos),
        )

    return obter(cur, id_unidade)
