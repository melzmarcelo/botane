"""Cardápio Vivo, fase 2: o pedido pela MESA, chamar garçom/pedir a conta e a identificação.

🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`.

🔑 **O pedido da mesa é um pedido como os do site** (decisão 3): mesma tabela, mesmo
painel, mesma numeração, mesmo "lançado no PDV". O que muda é a origem (`CARDAPIO`), o
modo (`MESA`) e o que NÃO se pede — telefone, endereço, forma de pagamento.
⚠️ **Não vira venda nem vai ao PDV sozinho** (decisão 1): a casa lança no PDV, como sempre.

⚠️ **O que o cliente PODE pedir é o que o FEED mostra agora**: item no catálogo apontado,
seção no dia e no horário, não esgotado, com preço. A conferência usa o próprio feed, para
não existir uma segunda regra de "está no cardápio".
"""

from decimal import Decimal

from fastapi import HTTPException

from services.custos import dec
from services import cardapio_vivo as cv
from services import fidelidade
from services import item_do_pedido
from services import pedidos as pedidos_servico
from services import reserva_clientes as clientes
from services import termo_consentimento as termo

_CENTAVO = Decimal("0.01")
PEDIDOS_POR_SESSAO_HORA = 12
ITENS_POR_PEDIDO = 40


# ---------------------------------------------------------------- o pedido da mesa

def enviar(cur, mesa: dict, dados: dict, telefone: str | None) -> dict:
    """Grava o pedido que a mesa mandou. Devolve o resumo público.

    🔑 **Idempotente pela chave** (regra 8): o mesmo envio repetido (rede ruim, toque duplo)
    devolve o pedido que já existe.
    """
    id_unidade = mesa["id_unidade"]
    cur.execute("SELECT id FROM pedidos WHERE id_unidade = %s AND chave = %s",
                (id_unidade, dados["chave"]))
    ja = cur.fetchone()
    if ja:
        return pedidos_servico.publico(cur, ja["id"]) | {"repetido": True}

    modo = cv.modo_efetivo(cur, id_unidade, mesa["id"])
    if modo["modo"] != "PEDIDO":
        raise HTTPException(status_code=409,
                            detail=modo["aviso"] or "Nesta mesa, os pedidos são com o garçom.")
    cur.execute("""SELECT count(*) AS n FROM pedidos
                    WHERE id_sessao = %s AND criado_em > now() - interval '1 hour'""",
                (dados["sessao"],))
    if cur.fetchone()["n"] >= PEDIDOS_POR_SESSAO_HORA:
        raise HTTPException(status_code=429, detail="Muitos pedidos seguidos. Chame o garçom.")
    if not dados["itens"] or len(dados["itens"]) > ITENS_POR_PEDIDO:
        raise HTTPException(status_code=422, detail="O pedido precisa ter de 1 a 40 itens.")

    cfg = cv.config(cur, id_unidade)
    feed = cv.feed(cur, id_unidade, cfg["id_catalogo"])
    do_feed = {i["id"]: i for i in feed["itens"]}
    cur.execute("SELECT id, id_produto FROM catalogo_itens WHERE id = ANY(%s)",
                ([int(i["item"]) for i in dados["itens"]],))
    produto_do_item = {r["id"]: r["id_produto"] for r in cur.fetchall()}
    cur.execute("SELECT id, id_produto FROM catalogo_item_escolhas WHERE id_item = ANY(%s)",
                (list(produto_do_item),))
    produto_da_opcao = {r["id"]: r["id_produto"] for r in cur.fetchall()}

    linhas = []
    for n, i in enumerate(dados["itens"]):
        item = do_feed.get(int(i["item"]))
        if not item:
            raise HTTPException(status_code=409,
                                detail="Um item do carrinho saiu do cardápio. Atualize a página.")
        if item["esgotado"]:
            raise HTTPException(status_code=409, detail=f"{item['nome']} esgotou.")
        if item["preco"] is None:
            raise HTTPException(status_code=409, detail=f"{item['nome']} está sem preço — peça ao garçom.")
        # 🔑 142: a escolha (item de escolha) e os adicionais seguem a regra única do site e
        # da mesa, em `item_do_pedido`.
        if item.get("escolhas"):
            # O feed é público e não leva o produto da opção: ele sai daqui, pelo id da opção.
            item = {**item, "escolhas": [{**o, "id_produto": produto_da_opcao.get(o["id"])}
                                         for o in item["escolhas"]]}
        linha = item_do_pedido.resolver({**item, "id_produto": produto_do_item[item["id"]]},
                                        i.get("escolha"), [int(x) for x in i.get("adicionais") or []])
        qtd = dec(i["quantidade"])
        linhas.append({**linha, "quantidade": qtd,
                       "total": (qtd * linha["preco_unitario"]).quantize(_CENTAVO),
                       "observacao": (i.get("observacao") or "").strip()[:200] or None,
                       "ordem": n})

    cliente = clientes.conferir(cur, id_unidade, clientes.telefone_valido(telefone)) if telefone else None
    tot = pedidos_servico._totais(linhas, Decimal(0))
    numero = pedidos_servico._proximo_numero(cur, id_unidade)
    situacao = "NOVO" if modo["exige_confirmacao"] else "CONFIRMADO"
    nome = (cliente["nome"] if cliente else None) or f"Mesa {mesa['nome']}"
    cur.execute(
        """INSERT INTO pedidos (id_unidade, numero, id_catalogo, id_cliente, nome, telefone, modo,
                                para_quando, observacao, subtotal, taxa_entrega, total, chave,
                                origem, id_mesa, mesa_nome, id_sessao, situacao, confirmado_em)
           VALUES (%s, %s, %s, %s, %s, %s, 'MESA', now(), %s, %s, 0, %s, %s, 'CARDAPIO', %s, %s, %s,
                   %s, CASE WHEN %s = 'CONFIRMADO' THEN now() END)
           RETURNING id""",
        (id_unidade, numero, cfg["id_catalogo"], cliente["id"] if cliente else None, nome,
         clientes.telefone_valido(telefone) if cliente else None,
         (dados.get("observacao") or "").strip()[:500] or None, tot["subtotal"], tot["total"],
         dados["chave"], mesa["id"], mesa["nome"], dados["sessao"], situacao, situacao))
    id_pedido = cur.fetchone()["id"]
    pedidos_servico._gravar_itens(cur, id_pedido, linhas)
    pedidos_servico._historico(cur, id_pedido, "CRIADO", None, "NOVO",
                               {"origem": "cardapio", "mesa": mesa["nome"]}, None)
    if situacao == "CONFIRMADO":
        # 🔑 Sem confirmação da equipe (opção da loja): nasce confirmado e vai direto para
        # "lançar no PDV" — quem lança continua sendo a casa (decisão 1).
        pedidos_servico._historico(cur, id_pedido, "CONFIRMADO", "NOVO", "CONFIRMADO",
                                   {"automatico": True}, None)
    return pedidos_servico.publico(cur, id_pedido) | {"repetido": False}


def da_sessao(cur, mesa: dict, sessao: str) -> list[dict]:
    """Os pedidos desta sessão nesta mesa (últimas 12 h) — o "acompanhar" do cliente."""
    cur.execute(
        """SELECT id FROM pedidos WHERE id_mesa = %s AND id_sessao = %s
              AND criado_em > now() - interval '12 hours' ORDER BY criado_em DESC LIMIT 20""",
        (mesa["id"], sessao))
    return [pedidos_servico.publico(cur, r["id"]) for r in cur.fetchall()]


# ---------------------------------------------------------------- chamar garçom / a conta

def chamar(cur, mesa: dict, tipo: str, sessao: str | None) -> dict:
    """Abre o chamado — ou devolve o que já está aberto (um por mesa e tipo).

    ⚠️ Só com a opção ligada na loja: botão que ninguém atende é pior que botão nenhum.
    """
    # A mesa é do Cardápio Vivo PRINCIPAL (117): é ele que diz se há garçom a chamar.
    principal = cv.vivo(cur, mesa["id_unidade"])
    if not (principal and principal["chamar_garcom"]):
        raise HTTPException(status_code=409, detail="Nesta casa, chame o garçom pessoalmente.")
    cur.execute(
        """INSERT INTO cardapio_chamados (id_unidade, id_mesa, id_sessao, tipo)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (id_mesa, tipo) WHERE atendido_em IS NULL DO NOTHING
           RETURNING id""",
        (mesa["id_unidade"], mesa["id"], sessao, tipo))
    novo = cur.fetchone() is not None
    return {"aberto": True, "novo": novo,
            "message": ("Pedimos a conta para você." if tipo == "CONTA" else "O garçom já vem.")
            if novo else "Já avisamos — o garçom já vem."}


def chamados_abertos(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT c.id, c.tipo, c.criado_em, m.nome AS mesa, s.nome AS salao
             FROM cardapio_chamados c JOIN mesas m ON m.id = c.id_mesa
             JOIN saloes s ON s.id = m.id_salao
            WHERE c.id_unidade = %s AND c.atendido_em IS NULL
            ORDER BY c.criado_em""",
        (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def atender(cur, id_unidade: int, id_chamado: int, id_usuario: int) -> dict:
    """Marca atendido. 🔑 É este clique que mede o tempo de atendimento do painel."""
    cur.execute(
        """UPDATE cardapio_chamados SET atendido_em = now(), atendido_por = %s
            WHERE id = %s AND id_unidade = %s AND atendido_em IS NULL
        RETURNING id""",
        (id_usuario, id_chamado, id_unidade))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou já atendido.")
    return {"message": "Chamado atendido."}


# ---------------------------------------------------------------- identificação e fidelidade

def identificar(cur, mesa: dict, corpo, posicao: dict | None, exige_completo: bool) -> dict:
    """Quem está na mesa — o cadastro que existe, ou um novo (decisão do dono, 15/10/2026).

    🔑 **A fidelidade segue o MÉTODO da casa** (decisão 7): no QR da mesa, a identificação
    marca a visita; no código do caixa, abre o pedido de código que o atendente passa.
    ⚠️ **Identificar nunca falha por causa da fidelidade**: dia que não conta, visita já
    feita hoje ou casa fora do programa viram uma frase, e o cliente segue identificado.
    """
    id_unidade = mesa["id_unidade"]
    cliente = clientes.identificar(cur, id_unidade, corpo, exige_completo)
    resposta = {"nome": clientes._primeiro_nome_exibido(cliente["nome"]), "novo": cliente["novo"],
                "telefone": cliente["telefone"], "fidelidade": None}
    if not fidelidade.ligada(cur, id_unidade):
        return resposta
    cur.execute("SELECT termo_versao FROM reserva_clientes WHERE id = %s", (cliente["id"],))
    if cur.fetchone()["termo_versao"] != termo.VERSAO:
        if not getattr(corpo, "aceite_termo", False):
            resposta["fidelidade"] = {"precisa_termo": True}
            return resposta
        clientes.aceitar_termo(cur, cliente["id"])
    cfg = fidelidade.config(cur)
    cur.execute("SAVEPOINT fidelidade_mesa")
    try:
        if cfg["metodo"] == "QRCODE_MESA":
            # 🔑 O token da MESA prova a presença, como o QR de check-in provaria: o segredo
            # do programa é passado aqui dentro, e nunca chega ao celular.
            r = fidelidade.checkin(cur, id_unidade, cliente["id"], cfg["token"], posicao=posicao)
            resposta["fidelidade"] = {"metodo": "QRCODE_MESA", "marcou": True, **r}
        else:
            fidelidade.solicitar(cur, id_unidade, cliente["id"], cfg["token"])
            resposta["fidelidade"] = {"metodo": "CODIGO_CAIXA", "aguardando_codigo": True}
        cur.execute("RELEASE SAVEPOINT fidelidade_mesa")
    except HTTPException as e:
        cur.execute("ROLLBACK TO SAVEPOINT fidelidade_mesa")
        resposta["fidelidade"] = {"metodo": cfg["metodo"], "marcou": False, "motivo": e.detail}
    return resposta
