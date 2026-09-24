"""Reservas — a configuração da loja e o salão: horários, permanência e mesas.

O módulo inteiro é ligado por `parametros.reservas_ligado`, uma loja de cada
vez. Este arquivo cuida das duas telas que descrevem a casa: **quando** ela
atende (janela de funcionamento e permanência) e **onde** as pessoas sentam
(salões, mesas e lugares). A regra de disponibilidade, que consome as duas, vem
a seguir.

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

from fastapi import HTTPException

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


# ---------------------------------------------------------------- o salão


def _mesas_vivas(cur, id_unidade: int) -> list[dict]:
    """As mesas que contam: ativas, em salão ativo.

    ⚠️ **As duas condições, e não só a da mesa.** Desligar o salão é o jeito de
    tirar a Varanda do inverno sem mexer em mesa por mesa — se a consulta
    olhasse só `mesas.ativo`, o salão desligado continuaria recebendo reserva e
    ninguém entenderia por quê.
    """
    cur.execute(
        """SELECT m.id, m.nome, m.lugares, m.capacidade_max, m.junta_com
             FROM mesas m JOIN saloes s ON s.id = m.id_salao
            WHERE m.id_unidade = %s AND m.ativo AND s.ativo
            ORDER BY s.ordem, s.nome, m.nome""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def maior_grupo(cur, id_unidade: int) -> int:
    """Quantas pessoas a maior mesa — ou a maior junta — acomoda.

    🔑 **É o número que diz se o teto do site cabe no salão.** Se
    `reserva_config.teto_online` passar dele, quem pedir mais não vai achar
    horário nenhum e **não vai saber por quê**: a tela de disponibilidade não
    tem como explicar que o problema é o cadastro. Foi uma das duas descobertas
    do protótipo, e por isso o servidor devolve este número às duas telas que
    mexem nos termos do problema.

    ⚠️ Usa `capacidade_max`, não `lugares`: é o que a alocação vai usar.
    """
    vivas = _mesas_vivas(cur, id_unidade)
    por_id = {m["id"]: m for m in vivas}
    maior = 0
    for m in vivas:
        maior = max(maior, m["capacidade_max"])
        par = por_id.get(m["junta_com"])
        if par:
            maior = max(maior, m["capacidade_max"] + par["capacidade_max"])
    return maior


def salao(cur, id_unidade: int) -> dict:
    """Os salões desta loja, com as mesas de cada um e os totais."""
    cur.execute(
        "SELECT id, nome, ativo, ordem FROM saloes WHERE id_unidade = %s ORDER BY ordem, nome",
        (id_unidade,),
    )
    saloes = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """SELECT m.id, m.id_salao, m.nome, m.lugares, m.capacidade_max, m.ativo,
                  m.junta_com, j.nome AS junta_com_nome
             FROM mesas m LEFT JOIN mesas j ON j.id = m.junta_com
            WHERE m.id_unidade = %s ORDER BY m.nome""",
        (id_unidade,),
    )
    mesas = [dict(r) for r in cur.fetchall()]

    ativos = {s["id"] for s in saloes if s["ativo"]}
    for s in saloes:
        suas = [m for m in mesas if m["id_salao"] == s["id"]]
        s["mesas"] = len([m for m in suas if m["ativo"]])
        s["lugares"] = sum(m["lugares"] for m in suas if m["ativo"])

    vivas = [m for m in mesas if m["ativo"] and m["id_salao"] in ativos]
    return {
        "saloes": saloes,
        "mesas": mesas,
        "mesas_ativas": len(vivas),
        "lugares": sum(m["lugares"] for m in vivas),
        "capacidade_max": sum(m["capacidade_max"] for m in vivas),
        "maior_grupo": maior_grupo(cur, id_unidade),
    }


def casar_junta(cur, id_unidade: int, id_mesa: int, id_par: int | None) -> None:
    """Grava a junta **nos dois sentidos**, desfazendo a anterior.

    🔑 **Juntar mesa é relação, não atributo.** Gravar só de um lado deixaria a
    alocação achando um par que a outra mesa não conhece: a 07 diria "encosto na
    08" e a 08 diria "não encosto em ninguém", e qual das duas vale dependeria de
    por onde a consulta entrou.

    ⚠️ **Desfaz a junta ANTERIOR dos dois lados antes de criar a nova**, senão
    trocar o par da 07 da 08 para a 09 deixaria a 08 apontando para a 07 e a 07
    para a 09 — um triângulo que nenhuma das três descreve.
    """
    cur.execute(
        "SELECT junta_com FROM mesas WHERE id = %s AND id_unidade = %s",
        (id_mesa, id_unidade),
    )
    atual = cur.fetchone()
    if atual is None:
        raise HTTPException(status_code=404, detail="Mesa não encontrada")

    # Solta quem estava preso: o par antigo desta mesa, e o par antigo do novo.
    for solta in (atual["junta_com"], id_par):
        if solta:
            cur.execute(
                "UPDATE mesas SET junta_com = NULL WHERE junta_com = %s OR id = %s",
                (solta, solta),
            )
    cur.execute("UPDATE mesas SET junta_com = NULL WHERE junta_com = %s", (id_mesa,))
    cur.execute("UPDATE mesas SET junta_com = %s WHERE id = %s", (id_par, id_mesa))
    if id_par:
        cur.execute("UPDATE mesas SET junta_com = %s WHERE id = %s", (id_mesa, id_par))


def obter(cur, id_unidade: int) -> dict:
    """A configuração inteira desta loja, pronta para a tela."""
    _garantir(cur, id_unidade)

    cur.execute(
        """SELECT aceita_online, confirmacao, teto_online, tolerancia_min, folga_min,
                  passo_min, antecedencia_min_horas, antecedencia_max_dias, cadastro_completo,
                  fidelidade_ligada,
                  whatsapp_texto, whatsapp_texto_reserva
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
        # 🔑 **O maior grupo que o salão acomoda vem JUNTO com o teto do site**,
        # porque os dois só fazem sentido comparados: teto maior que isto é uma
        # promessa que o salão não cumpre, e quem pedir mais não acha horário
        # nenhum sem saber por quê. A tela de configuração é onde o teto se
        # edita, então é onde o aviso precisa aparecer.
        "maior_grupo": maior_grupo(cur, id_unidade),
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
                  cadastro_completo = %s, fidelidade_ligada = %s,
                  whatsapp_texto = %s, whatsapp_texto_reserva = %s,
                  atualizado_em = now()
            WHERE id_unidade = %s""",
        (body.aceita_online, body.confirmacao, body.teto_online, body.tolerancia_min,
         body.folga_min, body.passo_min, body.antecedencia_min_horas,
         body.antecedencia_max_dias, body.cadastro_completo, body.fidelidade_ligada,
         # ⚠️ **Vazio vira NULO, não string vazia.** Nulo quer dizer "usa o
         # padrão"; `''` mandaria o cliente abrir o WhatsApp com a caixa em
         # branco, e quem apagou o campo sem querer não saberia por quê.
         (body.whatsapp_texto or "").strip() or None,
         (body.whatsapp_texto_reserva or "").strip() or None,
         id_unidade),
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
