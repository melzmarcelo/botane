"""Remessa entre lojas — sai daqui, chega lá, e alguém confere no meio.

🔑 **O envio NÃO escreve no razão.** A quantidade continua contando no estoque
da ORIGEM, marcada como em trânsito; os dois movimentos nascem juntos no
recebimento. A alternativa — dar baixa no envio e entrada no recebimento —
faria o valor desaparecer das duas lojas enquanto a mercadoria estivesse no
caminho, inflando o CMV de quem mandou. Aqui o dinheiro nunca fica sem dono.

⚠️ **Dentro da mesma loja não há trânsito**: prateleira para prateleira alguém
carrega a caixa. Esse caso continua no `estoque.transferir`, imediato.

⚠️ **O custo é o do RECEBIMENTO, não o do envio.** A mercadoria foi da origem
até chegar, então quem responde por ela é o médio da origem no dia em que ela
sai de lá. Congelar o custo no envio criaria um terceiro número, que não seria
nem o de quem mandou nem o de quem recebeu.
"""

from fastapi import HTTPException

from services import estoque as motor
from services.custos import dec

ABERTA = "EM_TRANSITO"


def _local(cur, id_local: int) -> dict:
    cur.execute(
        """SELECT l.id, l.nome, l.id_unidade, u.nome AS loja
             FROM locais_estoque l
             JOIN unidades u ON u.id = l.id_unidade
            WHERE l.id = %s""", (id_local,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Local não encontrado")
    return linha


def enviar(cur, *, id_local_origem: int, id_local_destino: int, itens: list[dict],
           id_usuario: int, observacao: str | None = None) -> dict:
    """Cria a remessa. Nenhum movimento de estoque nasce aqui."""
    origem, destino = _local(cur, id_local_origem), _local(cur, id_local_destino)
    if origem["id_unidade"] == destino["id_unidade"]:
        # Quem chama é que decide o caminho; chegar aqui é erro de programação,
        # e uma remessa dentro da mesma loja ficaria esperando um recebimento
        # que ninguém faria.
        raise HTTPException(
            status_code=400,
            detail="Remessa é entre LOJAS. Dentro da mesma loja a transferência é imediata.")
    if not itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto.")

    cur.execute(
        """INSERT INTO transferencias
               (id_unidade_origem, id_local_origem, id_unidade_destino, id_local_destino,
                observacao, id_usuario_envio)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (origem["id_unidade"], id_local_origem, destino["id_unidade"], id_local_destino,
         observacao, id_usuario))
    id_transferencia = cur.fetchone()["id"]

    vistos: set[int] = set()
    for item in itens:
        id_produto, qtd = int(item["id_produto"]), dec(item["quantidade"])
        if qtd <= 0:
            raise HTTPException(status_code=400, detail="Quantidade precisa ser maior que zero.")
        if id_produto in vistos:
            # A unicidade é do banco; conferir antes devolve uma frase em vez
            # de deixar a constraint estourar como 500.
            raise HTTPException(
                status_code=400,
                detail="O mesmo produto aparece duas vezes na remessa. Some as quantidades.")
        vistos.add(id_produto)
        cur.execute("SELECT nome, controla_estoque FROM produtos WHERE id = %s", (id_produto,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        if not p["controla_estoque"]:
            nome = p["nome"]
            raise HTTPException(
                status_code=400,
                detail=f"{nome} não controla estoque — não há o que transferir.")
        cur.execute(
            """INSERT INTO transferencia_itens
                   (id_transferencia, id_produto, qtd_enviada, observacao)
               VALUES (%s, %s, %s, %s)""",
            (id_transferencia, id_produto, qtd, item.get("observacao")))

    return {"id": id_transferencia, "status": ABERTA,
            "id_unidade_origem": origem["id_unidade"],
            "id_unidade_destino": destino["id_unidade"],
            "origem": f"{origem['nome']} · {origem['loja']}",
            "destino": f"{destino['nome']} · {destino['loja']}"}


def _remessa(cur, id_transferencia: int, travar: bool = False) -> dict:
    """A remessa, opcionalmente TRAVADA até o fim da transação.

    🔑 **Sem a trava, dois recebimentos simultâneos passam os dois pela
    conferência de status e lançam o dobro no razão** — que é append-only, então
    o conserto seria um estorno para cada movimento. É a mesma razão do
    `SELECT … FOR UPDATE` no saldo: a pergunta "isto ainda está aberto?" só vale
    se ninguém puder responder ao mesmo tempo.
    """
    cur.execute(
        "SELECT * FROM transferencias WHERE id = %s" + (" FOR UPDATE" if travar else ""),
        (id_transferencia,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Remessa não encontrada")
    return r


def receber(cur, *, id_transferencia: int, conferido: dict[int, dict], id_usuario: int,
            observacao: str | None = None) -> dict:
    """Confere e dá entrada. É AQUI que o razão se mexe, nas duas lojas.

    `conferido` é `{id_item: {"qtd_recebida": …, "id_motivo_perda": …}}`. Item
    que não vier na lista é recebido pelo que foi enviado — quem confere marca
    a exceção, não o caso comum.
    """
    r = _remessa(cur, id_transferencia, travar=True)
    if r["status"] != ABERTA:
        # ⚠️ Receber duas vezes lançaria a mercadoria duas vezes, e o razão é
        # append-only: o conserto seria um estorno para cada movimento.
        raise HTTPException(
            status_code=409,
            detail=("Esta remessa já foi recebida." if r["status"] == "RECEBIDA"
                    else "Esta remessa foi cancelada."))

    cur.execute(
        """SELECT i.*, p.nome, p.um_estoque
             FROM transferencia_itens i JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_transferencia = %s ORDER BY p.nome""", (id_transferencia,))
    itens = cur.fetchall()

    resultado, faltas = [], []
    for item in itens:
        escolha = conferido.get(item["id"]) or {}
        enviada = dec(item["qtd_enviada"])
        bruto = escolha.get("qtd_recebida")
        recebida = enviada if bruto is None else dec(bruto)
        if recebida < 0:
            raise HTTPException(status_code=400,
                                detail="Quantidade recebida não pode ser negativa.")

        saida = entrada = perda = None
        # A observação do razão nomeia a remessa: quem cai no movimento pelo
        # razão precisa chegar ao documento, não deduzir que existe um.
        nota = observacao or r["observacao"] or f"Remessa {id_transferencia}"
        if recebida > 0:
            saida = motor.lancar(
                cur, id_unidade=r["id_unidade_origem"], id_local=r["id_local_origem"],
                id_produto=item["id_produto"], tipo="TRANSFERENCIA_SAIDA", quantidade=recebida,
                origem_tipo="TRANSFERENCIA",
                observacao=nota, id_usuario=id_usuario)
            entrada = motor.lancar(
                cur, id_unidade=r["id_unidade_destino"], id_local=r["id_local_destino"],
                id_produto=item["id_produto"], tipo="TRANSFERENCIA_ENTRADA", quantidade=recebida,
                # 🔑 O custo ATRAVESSA a fronteira: a entrada usa o médio que a
                # saída apurou. É o que faz a origem perder exatamente o valor
                # que o destino ganha — transferência não cria dinheiro, e
                # entre lojas também não pode criar.
                custo_unitario=saida["custo_unitario"],
                origem_tipo="TRANSFERENCIA", origem_id=saida["id"],
                observacao=nota, id_usuario=id_usuario)
            # 🔑 **Os dois movimentos apontam UM PARA O OUTRO**, e não para a
            # remessa. É a convenção que o razão já tinha, e dela depende a
            # apuração: `_transferencia_entre_lojas` acha o outro lado por
            # `JOIN estoque_movimentos o ON o.id = m.origem_id` para saber se a
            # mercadoria atravessou a fronteira. Apontar para a remessa faria
            # esse JOIN cair num movimento QUALQUER de mesmo id — e o CMV das
            # duas lojas passaria a depender de uma coincidência de numeração.
            # Quem liga o movimento à remessa é `transferencia_itens`.
            cur.execute("UPDATE estoque_movimentos SET origem_id = %s WHERE id = %s",
                        (entrada["id"], saida["id"]))

        falta = enviada - recebida
        if falta > 0:
            # 🔑 **O que não chegou saiu da prateleira do mesmo jeito.**
            # Transferir só o que chegou deixaria a origem com um saldo que ela
            # não tem — e a próxima contagem cobriria o buraco como ajuste de
            # inventário, que é onde a diferença some sem nome. Como PERDA ela
            # tem nome, dono e uma linha própria no CMV de quem mandou.
            perda = motor.lancar(
                cur, id_unidade=r["id_unidade_origem"], id_local=r["id_local_origem"],
                id_produto=item["id_produto"], tipo="SAIDA_PERDA", quantidade=falta,
                id_motivo_perda=escolha.get("id_motivo_perda"),
                # ⚠️ **`REMESSA`, não `TRANSFERENCIA`.** Naquele vocabulário o
                # `origem_id` é o movimento do outro lado; aqui não existe outro
                # lado — a mercadoria não chegou. Reusar a mesma palavra poria
                # um id de remessa onde a apuração espera um id de movimento.
                origem_tipo="REMESSA", origem_id=id_transferencia,
                observacao=f"Não chegou na remessa {id_transferencia}",
                id_usuario=id_usuario)
            faltas.append({"produto": item["nome"], "quantidade": float(falta),
                           "um": item["um_estoque"]})

        cur.execute(
            """UPDATE transferencia_itens
                  SET qtd_recebida = %s, id_movimento_saida = %s,
                      id_movimento_entrada = %s, id_movimento_perda = %s,
                      observacao = coalesce(%s, observacao)
                WHERE id = %s""",
            (recebida, saida and saida["id"], entrada and entrada["id"],
             perda and perda["id"], escolha.get("observacao"), item["id"]))
        resultado.append({"id_produto": item["id_produto"], "produto": item["nome"],
                          "enviada": float(enviada), "recebida": float(recebida),
                          "falta": float(falta)})

    cur.execute(
        """UPDATE transferencias
              SET status = 'RECEBIDA', recebida_em = now(),
                  id_usuario_recebimento = %s, observacao_recebimento = %s
            WHERE id = %s""", (id_usuario, observacao, id_transferencia))
    return {"id": id_transferencia, "itens": resultado, "faltas": faltas}


def cancelar(cur, *, id_transferencia: int, id_usuario: int) -> dict:
    """Desiste da remessa. **Não estorna nada** — nada foi lançado."""
    r = _remessa(cur, id_transferencia, travar=True)
    if r["status"] != ABERTA:
        raise HTTPException(
            status_code=409,
            detail=("Remessa já recebida — o caminho agora é estornar os movimentos."
                    if r["status"] == "RECEBIDA" else "Remessa já cancelada."))
    cur.execute(
        """UPDATE transferencias SET status = 'CANCELADA', cancelada_em = now(),
                  id_usuario_cancelamento = %s WHERE id = %s""",
        (id_usuario, id_transferencia))
    return {"id": id_transferencia, "status": "CANCELADA"}


def consulta_da_lista(*, id_unidade: int, status: str | None = None) -> tuple[str, tuple]:
    """O SQL **sem LIMIT** — o total usa o mesmo texto e os mesmos parâmetros.

    ⚠️ Uma cópia do filtro escrita à mão divergiria no primeiro `WHERE` novo, e
    o rodapé passaria a contar outra coisa que não a lista.
    ⚠️ Parâmetros POSICIONAIS porque `paginacao.pagina` faz `tuple(params)` —
    um dicionário viraria a tupla das CHAVES, calada, e a consulta falharia
    dizendo que falta argumento.
    """
    sql = """
SELECT t.id, t.status, t.enviada_em, t.recebida_em, t.observacao,
       t.id_unidade_origem, t.id_unidade_destino,
       uo.nome AS loja_origem, ud.nome AS loja_destino,
       lo.nome AS local_origem, ld.nome AS local_destino,
       ue.nome AS enviada_por,
       (SELECT count(*) FROM transferencia_itens i WHERE i.id_transferencia = t.id) AS itens,
       (SELECT coalesce(sum(i.qtd_enviada), 0) FROM transferencia_itens i
         WHERE i.id_transferencia = t.id) AS quantidade
  FROM transferencias t
  JOIN unidades uo ON uo.id = t.id_unidade_origem
  JOIN unidades ud ON ud.id = t.id_unidade_destino
  JOIN locais_estoque lo ON lo.id = t.id_local_origem
  JOIN locais_estoque ld ON ld.id = t.id_local_destino
  LEFT JOIN usuarios ue ON ue.id = t.id_usuario_envio
 WHERE (%s::text IS NULL OR t.status = %s)
   -- ⚠️ **A loja atual vê os dois lados**: o que ela mandou e o que ela
   -- espera. Filtrar só pela origem esconderia da filial justamente a remessa
   -- que ela precisa receber.
   AND (t.id_unidade_origem = %s OR t.id_unidade_destino = %s)
 ORDER BY t.enviada_em DESC, t.id DESC
"""
    return sql, (status, status, id_unidade, id_unidade)


def obter(cur, id_transferencia: int) -> dict:
    r = _remessa(cur, id_transferencia)
    cur.execute(
        """SELECT t.*, uo.nome AS loja_origem, ud.nome AS loja_destino,
                  lo.nome AS local_origem, ld.nome AS local_destino,
                  ue.nome AS enviada_por, ur.nome AS recebida_por
             FROM transferencias t
             JOIN unidades uo ON uo.id = t.id_unidade_origem
             JOIN unidades ud ON ud.id = t.id_unidade_destino
             JOIN locais_estoque lo ON lo.id = t.id_local_origem
             JOIN locais_estoque ld ON ld.id = t.id_local_destino
             LEFT JOIN usuarios ue ON ue.id = t.id_usuario_envio
             LEFT JOIN usuarios ur ON ur.id = t.id_usuario_recebimento
            WHERE t.id = %s""", (id_transferencia,))
    cabecalho = cur.fetchone()
    cur.execute(
        """SELECT i.id, i.id_produto, i.qtd_enviada, i.qtd_recebida, i.observacao,
                  i.id_movimento_saida, i.id_movimento_entrada, i.id_movimento_perda,
                  p.nome, p.codigo, p.um_estoque,
                  -- O saldo de HOJE na prateleira de onde vai sair: quem
                  -- confere precisa saber se a baixa vai deixar a origem
                  -- negativa antes de apertar o botão.
                  coalesce((SELECT s.quantidade FROM estoque_saldos s
                             WHERE s.id_produto = i.id_produto
                               AND s.id_local = %(lo)s), 0) AS saldo_origem
             FROM transferencia_itens i JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_transferencia = %(t)s ORDER BY p.nome""",
        {"t": id_transferencia, "lo": r["id_local_origem"]})
    return {**cabecalho, "itens": cur.fetchall()}


def em_transito_por_local(cur, id_unidade: int) -> dict[tuple[int, int], float]:
    """Quanto de cada produto já foi despachado desta loja e ainda não chegou.

    🔑 **Ele continua no saldo, e é por isso que precisa aparecer.** A tela de
    saldos mostraria 12 KG numa prateleira de onde 10 já saíram no carro —
    verdade contábil e mentira operacional. Sem este número, a segunda remessa
    do dia despacharia mercadoria que já está na estrada.
    """
    cur.execute(
        """SELECT i.id_produto, t.id_local_origem, sum(i.qtd_enviada) AS qtd
             FROM transferencia_itens i JOIN transferencias t ON t.id = i.id_transferencia
            WHERE t.status = %s AND t.id_unidade_origem = %s
            GROUP BY 1, 2""", (ABERTA, id_unidade))
    return {(l["id_produto"], l["id_local_origem"]): float(l["qtd"]) for l in cur.fetchall()}
