"""Pedidos pelo catálogo do site — do carrinho à entrega.

🔑 **Pedido do dono (28/09/2026):** *"o cliente poder realizar pedidos diretamente na tela de
catálogo … um carrinho … uma tela com pedidos, um painel e aviso na tela inicial. O pagamento
não será pelo sistema."* Decisões em `docs/pedidos-estudo.md`, seção 0.

Quatro regras seguram o módulo:

* **O pedido NÃO vira venda.** A casa lança no PDV e a venda chega pela busca de sempre; aqui
  se registra "lançado no PDV" (+ cupom). Uma segunda venda seria estoque, receita e CMV em
  dobro, calados.
* **Preço é do SERVIDOR.** O site manda o item do catálogo e a quantidade; o valor sai da
  mesma cascata do cardápio (preço da loja → da casa). Nome e preço ficam congelados no item.
* **A casa sempre confirma**, e pode trocar produtos antes — o que o cliente pediu fica no
  histórico.
* **Enviar duas vezes não cria dois** (regra 8): a chave do carrinho tem índice único.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from config import FUSO_DA_CASA
from services.custos import dec

ORIGEM_PRODUTOS = "PRODUTOS"
MODOS = {"RETIRADA": "Retirar na loja", "ENTREGA": "Entrega"}
PAGAMENTOS = {"RETIRADA": "Na retirada", "ENTREGA": "Na entrega", "WHATSAPP": "Combinar pelo WhatsApp"}
SITUACOES = ("NOVO", "CONFIRMADO", "ENTREGUE", "RECUSADO", "CANCELADO")
_CENTAVO = Decimal("0.01")

_PADRAO = {"aceita": False, "retirada": True, "entrega": False, "taxa_entrega": 0.0,
           "pedido_minimo": 0.0, "antecedencia_min": 30, "antecedencia_max_dias": 7,
           "pagamentos": ["RETIRADA"], "texto_pagamento": None}

# O preço vigente: o da LOJA primeiro, o da casa depois — a MESMA cascata do cardápio
# público (`routers/publico._montar_cardapio`). Uma segunda regra cobraria diferente do site.
_PRECO = """(SELECT pr.preco_venda FROM produto_precos pr
              WHERE pr.id_produto = p.id AND pr.vigente_ate IS NULL
                AND (pr.id_unidade = %(u)s OR pr.id_unidade IS NULL)
              ORDER BY pr.id_unidade NULLS LAST LIMIT 1)"""
_NOME = "coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome)"


def _fuso():
    return ZoneInfo(FUSO_DA_CASA)


def _agora(cur) -> datetime:
    cur.execute("SELECT now() AS agora")
    return cur.fetchone()["agora"].astimezone(_fuso())


def _num(v) -> float:
    return float(v) if v is not None else 0.0


# ---------------------------------------------------------------- configuração

def config(cur, id_catalogo: int) -> dict:
    cur.execute("SELECT * FROM catalogo_pedidos_config WHERE id_catalogo = %s", (id_catalogo,))
    linha = cur.fetchone()
    if not linha:
        return dict(_PADRAO)
    c = dict(linha)
    c.pop("id_catalogo", None)
    c.pop("atualizado_em", None)
    c["taxa_entrega"] = _num(c["taxa_entrega"])
    c["pedido_minimo"] = _num(c["pedido_minimo"])
    c["pagamentos"] = list(c["pagamentos"] or [])
    return c


def salvar_config(cur, id_catalogo: int, dados: dict) -> dict:
    """⚠️ Só catálogo de origem PRODUTOS aceita pedido (decisão do dono): o PDF não tem item
    para pôr no carrinho."""
    cur.execute("SELECT origem FROM catalogos WHERE id = %s", (id_catalogo,))
    cat = cur.fetchone()
    if not cat:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado")
    if cat["origem"] != ORIGEM_PRODUTOS and dados.get("aceita"):
        raise HTTPException(status_code=400,
                            detail="Só o catálogo montado por produtos aceita pedidos — o PDF não tem itens.")
    cur.execute(
        """INSERT INTO catalogo_pedidos_config
               (id_catalogo, aceita, retirada, entrega, taxa_entrega, pedido_minimo,
                antecedencia_min, antecedencia_max_dias, pagamentos, texto_pagamento)
           VALUES (%(c)s, %(aceita)s, %(retirada)s, %(entrega)s, %(taxa_entrega)s,
                   %(pedido_minimo)s, %(antecedencia_min)s, %(antecedencia_max_dias)s,
                   %(pagamentos)s, %(texto_pagamento)s)
           ON CONFLICT (id_catalogo) DO UPDATE SET
               aceita = EXCLUDED.aceita, retirada = EXCLUDED.retirada,
               entrega = EXCLUDED.entrega, taxa_entrega = EXCLUDED.taxa_entrega,
               pedido_minimo = EXCLUDED.pedido_minimo,
               antecedencia_min = EXCLUDED.antecedencia_min,
               antecedencia_max_dias = EXCLUDED.antecedencia_max_dias,
               pagamentos = EXCLUDED.pagamentos, texto_pagamento = EXCLUDED.texto_pagamento,
               atualizado_em = now()""",
        dados | {"c": id_catalogo,
                 "texto_pagamento": (dados.get("texto_pagamento") or "").strip() or None},
    )
    return config(cur, id_catalogo)


# ---------------------------------------------------------------- o horário

def _dias_abertos(cur, id_unidade: int, de: date, ate: date) -> list[dict]:
    """Os dias em que a casa atende, com abre e fecha — para o site montar o seletor."""
    from services import reservas_agenda as agenda
    dias = []
    d = de
    while d <= ate:
        if not agenda.bloqueio_do_dia(cur, id_unidade, d):
            j = agenda.janela_do_dia(cur, id_unidade, d)
            if j:
                dias.append({"dia": d.isoformat(), "abre": j["abre"].strftime("%H:%M"),
                             "fecha": j["fecha"].strftime("%H:%M")})
        d += timedelta(days=1)
    return dias


def _conferir_quando(cur, id_unidade: int, cfg: dict, pedido_para: datetime | None) -> datetime:
    """Quando o pedido é para — e se a casa atende nessa hora.

    🔑 Nulo é "o quanto antes": agora + a antecedência mínima, e só se a casa estiver aberta
    até lá. ⚠️ Hora sem fuso vem do SITE e é a hora da CASA — nunca a do servidor.
    """
    from services import reservas_agenda as agenda
    agora = _agora(cur)
    cedo = agora + timedelta(minutes=int(cfg["antecedencia_min"]))
    if pedido_para is None:
        quando = cedo
    else:
        quando = (pedido_para.replace(tzinfo=_fuso()) if pedido_para.tzinfo is None
                  else pedido_para.astimezone(_fuso()))
        if quando < cedo - timedelta(minutes=1):
            raise HTTPException(
                status_code=400,
                detail=(f"Esse horário é cedo demais: a casa precisa de "
                        f"{int(cfg['antecedencia_min'])} minutos. Escolha a partir de "
                        f"{cedo:%d/%m às %H:%M}."))
    if quando.date() > agora.date() + timedelta(days=int(cfg["antecedencia_max_dias"])):
        raise HTTPException(
            status_code=400,
            detail=f"Pedidos só até {int(cfg['antecedencia_max_dias'])} dia(s) à frente.")
    motivo = agenda.bloqueio_do_dia(cur, id_unidade, quando.date())
    if motivo:
        raise HTTPException(status_code=400, detail=f"A casa não atende nesse dia: {motivo}.")
    janela = agenda.janela_do_dia(cur, id_unidade, quando.date())
    hora = quando.time().replace(tzinfo=None)
    if not janela or not (janela["abre"] <= hora <= janela["fecha"]):
        if pedido_para is None:
            raise HTTPException(status_code=400,
                                detail="A casa está fechada agora — escolha o dia e a hora do pedido.")
        detalhe = (f"Nesse dia a casa atende das {janela['abre']:%H:%M} às {janela['fecha']:%H:%M}."
                   if janela else "A casa não atende nesse dia.")
        raise HTTPException(status_code=400, detail=detalhe)
    return quando


def config_publica(cur, id_unidade: int, id_catalogo: int) -> dict | None:
    """O que o site precisa para montar o carrinho — ou None se o catálogo não aceita."""
    cfg = config(cur, id_catalogo)
    if not cfg["aceita"]:
        return None
    agora = _agora(cur)
    modos = [m for m in ("RETIRADA", "ENTREGA") if cfg[m.lower()]]
    return {
        "modos": [{"valor": m, "rotulo": MODOS[m]} for m in modos],
        "taxa_entrega": cfg["taxa_entrega"] if cfg["entrega"] else 0.0,
        "pedido_minimo": cfg["pedido_minimo"],
        "antecedencia_min": cfg["antecedencia_min"],
        "antecedencia_max_dias": cfg["antecedencia_max_dias"],
        "pagamentos": [{"valor": p, "rotulo": PAGAMENTOS[p]} for p in cfg["pagamentos"]],
        "texto_pagamento": cfg["texto_pagamento"],
        "dias": _dias_abertos(cur, id_unidade, agora.date(),
                              agora.date() + timedelta(days=int(cfg["antecedencia_max_dias"]))),
        "agora": agora.isoformat(),
    }


# ---------------------------------------------------------------- os itens

def _itens_do_catalogo(cur, id_unidade: int, id_catalogo: int, ids: list[int] | None = None) -> dict:
    """Os itens do catálogo, com o produto e o preço vigente — por id do item."""
    cur.execute(
        f"""SELECT i.id AS id_item, p.id AS id_produto, {_NOME} AS nome, p.ativo,
                   {_PRECO} AS preco
              FROM catalogo_itens i
              JOIN catalogo_categorias g ON g.id = i.id_categoria
              JOIN produtos p ON p.id = i.id_produto
             WHERE g.id_catalogo = %(c)s
               AND (%(ids)s::int[] IS NULL OR i.id = ANY(%(ids)s::int[]))""",
        {"c": id_catalogo, "u": id_unidade, "ids": ids},
    )
    return {r["id_item"]: dict(r) for r in cur.fetchall()}


def catalogo_para_troca(cur, id_unidade: int, id_pedido: int) -> list[dict]:
    """O que a casa pode pôr no lugar: os itens vivos e com preço do mesmo catálogo."""
    p = _pedido(cur, id_unidade, id_pedido)
    if not p["id_catalogo"]:
        return []
    itens = _itens_do_catalogo(cur, id_unidade, p["id_catalogo"])
    vistos, saida = set(), []
    for i in sorted(itens.values(), key=lambda x: x["nome"]):
        if i["ativo"] and i["preco"] is not None and i["id_produto"] not in vistos:
            vistos.add(i["id_produto"])
            saida.append({"id_item": i["id_item"], "id_produto": i["id_produto"],
                          "nome": i["nome"], "preco": _num(i["preco"])})
    return saida


def _totais(itens: list[dict], taxa: Decimal) -> dict:
    sub = sum((dec(i["total"]) for i in itens), Decimal(0)).quantize(_CENTAVO)
    return {"subtotal": sub, "total": (sub + taxa).quantize(_CENTAVO)}


# ---------------------------------------------------------------- o envio (site)

def _proximo_numero(cur, id_unidade: int) -> int:
    # ⚠️ Trava por LOJA na transação: dois envios ao mesmo tempo não disputam o mesmo número.
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('pedido_numero'), %s)", (id_unidade,))
    cur.execute("SELECT coalesce(max(numero), 0) + 1 AS n FROM pedidos WHERE id_unidade = %s",
                (id_unidade,))
    return cur.fetchone()["n"]


def enviar(cur, id_unidade: int, id_catalogo: int, cliente: dict, dados: dict) -> dict:
    """Grava o pedido que o site mandou. Devolve o resumo público."""
    cur.execute("SELECT id FROM pedidos WHERE id_unidade = %s AND chave = %s",
                (id_unidade, dados["chave"]))
    ja = cur.fetchone()
    if ja:
        return publico(cur, ja["id"]) | {"repetido": True}

    cfg = config(cur, id_catalogo)
    if not cfg["aceita"]:
        raise HTTPException(status_code=409, detail="Este cardápio não recebe pedidos pelo site.")
    modo = dados["modo"]
    if not cfg[modo.lower()]:
        raise HTTPException(status_code=400, detail=f"{MODOS[modo]} não está disponível.")
    if modo == "ENTREGA" and not dados.get("endereco"):
        raise HTTPException(status_code=400, detail="Informe o endereço de entrega.")
    if dados["forma_pagamento"] not in cfg["pagamentos"]:
        raise HTTPException(status_code=400, detail="Forma de pagamento não disponível.")
    quando = _conferir_quando(cur, id_unidade, cfg, dados.get("para_quando"))

    ids = [int(i["id_item"]) for i in dados["itens"]]
    catalogo = _itens_do_catalogo(cur, id_unidade, id_catalogo, ids)
    linhas = []
    for n, i in enumerate(dados["itens"]):
        c = catalogo.get(int(i["id_item"]))
        if not c or not c["ativo"]:
            raise HTTPException(status_code=409,
                                detail="Um item do carrinho saiu do cardápio. Atualize a página.")
        if c["preco"] is None:
            raise HTTPException(status_code=409, detail=f"{c['nome']} está sem preço e não pode ser pedido.")
        qtd = dec(i["quantidade"])
        linhas.append({"id_produto": c["id_produto"], "nome": c["nome"], "quantidade": qtd,
                       "preco_unitario": dec(c["preco"]),
                       "total": (qtd * dec(c["preco"])).quantize(_CENTAVO),
                       "observacao": (i.get("observacao") or "").strip() or None, "ordem": n})
    taxa = dec(cfg["taxa_entrega"]) if modo == "ENTREGA" else Decimal(0)
    tot = _totais(linhas, taxa)
    if tot["subtotal"] < dec(cfg["pedido_minimo"]):
        raise HTTPException(
            status_code=400,
            detail=f"O pedido mínimo é R$ {cfg['pedido_minimo']:.2f}".replace(".", ",") + ".")

    numero = _proximo_numero(cur, id_unidade)
    cur.execute(
        """INSERT INTO pedidos (id_unidade, numero, id_catalogo, id_cliente, nome, telefone,
                                modo, endereco, para_quando, forma_pagamento, observacao,
                                subtotal, taxa_entrega, total, chave)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (id_unidade, numero, id_catalogo, cliente["id"], cliente["nome"], cliente["telefone"],
         modo, dados.get("endereco") if modo == "ENTREGA" else None, quando,
         dados["forma_pagamento"], dados.get("observacao"), tot["subtotal"], taxa,
         tot["total"], dados["chave"]),
    )
    id_pedido = cur.fetchone()["id"]
    _gravar_itens(cur, id_pedido, linhas)
    _historico(cur, id_pedido, "CRIADO", None, "NOVO", None, None)
    return publico(cur, id_pedido) | {"repetido": False}


def _gravar_itens(cur, id_pedido: int, linhas: list[dict]) -> None:
    cur.execute("DELETE FROM pedido_itens WHERE id_pedido = %s", (id_pedido,))
    for l in linhas:
        cur.execute(
            """INSERT INTO pedido_itens (id_pedido, id_produto, nome, quantidade, preco_unitario,
                                         total, observacao, ordem)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (id_pedido, l["id_produto"], l["nome"], l["quantidade"], l["preco_unitario"],
             l["total"], l.get("observacao"), l.get("ordem", 0)),
        )


def _historico(cur, id_pedido: int, acao: str, de: str | None, para: str | None,
               detalhe: dict | None, id_usuario: int | None) -> None:
    import json
    cur.execute(
        """INSERT INTO pedido_historico (id_pedido, acao, de, para, detalhe, id_usuario)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (id_pedido, acao, de, para, json.dumps(detalhe, default=str) if detalhe else None,
         id_usuario),
    )


def _itens(cur, id_pedido: int) -> list[dict]:
    cur.execute(
        """SELECT id, id_produto, nome, quantidade, preco_unitario, total, observacao
             FROM pedido_itens WHERE id_pedido = %s ORDER BY ordem, id""", (id_pedido,))
    return [{**dict(r), "quantidade": _num(r["quantidade"]),
             "preco_unitario": _num(r["preco_unitario"]), "total": _num(r["total"])}
            for r in cur.fetchall()]


def publico(cur, id_pedido: int) -> dict:
    """O pedido como o CLIENTE o vê — sem id interno, sem quem confirmou."""
    cur.execute("SELECT * FROM pedidos WHERE id = %s", (id_pedido,))
    p = dict(cur.fetchone())
    return {
        "numero": p["numero"], "situacao": p["situacao"], "motivo": p["motivo"],
        "alterado": p["alterado"], "modo": p["modo"], "modo_rotulo": MODOS[p["modo"]],
        "endereco": p["endereco"],
        "para_quando": p["para_quando"].astimezone(_fuso()).isoformat(),
        "forma_pagamento": PAGAMENTOS[p["forma_pagamento"]],
        "subtotal": _num(p["subtotal"]), "taxa_entrega": _num(p["taxa_entrega"]),
        "total": _num(p["total"]), "observacao": p["observacao"],
        "criado_em": p["criado_em"].astimezone(_fuso()).isoformat(),
        "itens": [{"nome": i["nome"], "quantidade": i["quantidade"],
                   "preco_unitario": i["preco_unitario"], "total": i["total"],
                   "observacao": i["observacao"]} for i in _itens(cur, id_pedido)],
    }


def meus(cur, id_unidade: int, id_cliente: int) -> list[dict]:
    """Os pedidos do cliente: os em aberto e os dos últimos 30 dias."""
    cur.execute(
        """SELECT id FROM pedidos
            WHERE id_unidade = %s AND id_cliente = %s
              AND (situacao IN ('NOVO', 'CONFIRMADO') OR criado_em >= now() - interval '30 days')
            ORDER BY criado_em DESC LIMIT 20""",
        (id_unidade, id_cliente),
    )
    return [publico(cur, r["id"]) for r in cur.fetchall()]


def cancelar_pelo_cliente(cur, id_unidade: int, id_cliente: int, numero: int) -> dict:
    """⚠️ Só enquanto NOVO: depois de a casa confirmar, o cliente fala com a casa."""
    cur.execute(
        """SELECT id, situacao FROM pedidos
            WHERE id_unidade = %s AND id_cliente = %s AND numero = %s FOR UPDATE""",
        (id_unidade, id_cliente, numero),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if p["situacao"] != "NOVO":
        raise HTTPException(status_code=409,
                            detail="A casa já confirmou este pedido — para cancelar, fale com a casa.")
    cur.execute("""UPDATE pedidos SET situacao = 'CANCELADO', motivo = 'Cancelado pelo cliente no site',
                          atualizado_em = now() WHERE id = %s""", (p["id"],))
    _historico(cur, p["id"], "CANCELADO", "NOVO", "CANCELADO", {"por": "cliente"}, None)
    return publico(cur, p["id"])


# ---------------------------------------------------------------- a casa

def _pedido(cur, id_unidade: int, id_pedido: int, travar: bool = False) -> dict:
    cur.execute("SELECT * FROM pedidos WHERE id = %s AND id_unidade = %s"
                + (" FOR UPDATE" if travar else ""), (id_pedido, id_unidade))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Pedido não encontrado nesta loja")
    return dict(p)


def _ligar_venda(cur, p: dict) -> dict:
    """🔑 Com o cupom informado, o pedido acha a VENDA que a busca do PDV trouxe — só para
    conferir. Nada muda em estoque, receita ou CMV."""
    if p.get("cupom_pdv") and not p.get("id_venda"):
        cur.execute(
            """SELECT id FROM vendas WHERE id_unidade = %s AND documento = %s
                ORDER BY id DESC LIMIT 1""", (p["id_unidade"], p["cupom_pdv"]))
        v = cur.fetchone()
        if v:
            cur.execute("UPDATE pedidos SET id_venda = %s WHERE id = %s", (v["id"], p["id"]))
            p["id_venda"] = v["id"]
    return p


_LISTA = """
    SELECT p.id, p.numero, p.nome, p.telefone, p.modo, p.endereco, p.para_quando,
           p.forma_pagamento, p.total, p.situacao, p.motivo, p.alterado, p.lancado_pdv_em,
           p.cupom_pdv, p.id_venda, p.pago_em, p.pago_como, p.entregue_em, p.criado_em,
           c.nome AS catalogo,
           (SELECT count(*) FROM pedido_itens i WHERE i.id_pedido = p.id) AS itens
      FROM pedidos p
      LEFT JOIN catalogos c ON c.id = p.id_catalogo
"""

_FILTROS = {
    "abertos": "p.situacao IN ('NOVO', 'CONFIRMADO')",
    "novos": "p.situacao = 'NOVO'",
    "sem_pdv": "p.situacao IN ('CONFIRMADO', 'ENTREGUE') AND p.lancado_pdv_em IS NULL",
    "confirmados": "p.situacao = 'CONFIRMADO'",
    "entregues": "p.situacao = 'ENTREGUE'",
    "recusados": "p.situacao IN ('RECUSADO', 'CANCELADO')",
    "todos": "true",
}


def _linha(r: dict) -> dict:
    return {**r, "total": _num(r["total"]),
            "modo_rotulo": MODOS[r["modo"]],
            "pagamento_rotulo": PAGAMENTOS[r["forma_pagamento"]]}


def listar(cur, id_unidade: int, situacao: str, dia: date | None, busca: str | None,
           limite: int, offset: int, resposta) -> list[dict]:
    from paginacao import pagina
    if situacao not in _FILTROS:
        raise HTTPException(status_code=400, detail="Situação inválida")
    termo = f"%{busca.strip()}%" if busca and busca.strip() else None
    numero = int(busca) if busca and busca.strip().isdigit() else None
    ordem = ("p.para_quando, p.numero" if situacao in ("abertos", "novos", "confirmados", "sem_pdv")
             else "p.criado_em DESC")
    linhas = pagina(
        cur,
        _LISTA + f"""
         WHERE p.id_unidade = %s AND {_FILTROS[situacao]}
           AND (%s::date IS NULL OR (p.para_quando AT TIME ZONE %s)::date = %s::date)
           AND (%s::text IS NULL OR p.nome ILIKE %s OR p.telefone ILIKE %s OR p.numero = %s)
         ORDER BY {ordem}""",
        (id_unidade, dia, FUSO_DA_CASA, dia, termo, termo, termo, numero),
        limite=limite, offset=offset, resposta=resposta)
    return [_linha(l) for l in linhas]


def obter(cur, id_unidade: int, id_pedido: int) -> dict:
    p = _ligar_venda(cur, _pedido(cur, id_unidade, id_pedido))
    cur.execute(
        """SELECT h.acao, h.de, h.para, h.detalhe, h.criado_em, u.nome AS quem
             FROM pedido_historico h LEFT JOIN usuarios u ON u.id = h.id_usuario
            WHERE h.id_pedido = %s ORDER BY h.criado_em, h.id""", (id_pedido,))
    historico = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT nome FROM catalogos WHERE id = %s", (p["id_catalogo"],))
    cat = cur.fetchone()
    return _linha(p | {"catalogo": cat["nome"] if cat else None}) | {
        "subtotal": _num(p["subtotal"]), "taxa_entrega": _num(p["taxa_entrega"]),
        "itens": _itens(cur, id_pedido), "historico": historico,
    }


def confirmar(cur, id_unidade: int, id_pedido: int, id_usuario: int, dados: dict) -> dict:
    """A casa confirma — do jeito que veio, ou com os produtos trocados.

    ⚠️ Item que já estava no pedido mantém o preço congelado no envio; item NOVO entra pelo
    preço vigente do catálogo. O que o cliente pediu fica no histórico.
    """
    p = _pedido(cur, id_unidade, id_pedido, travar=True)
    if p["situacao"] != "NOVO":
        raise HTTPException(status_code=409, detail="Só pedido NOVO se confirma.")
    antes = _itens(cur, id_pedido)
    alterado = False
    if dados.get("itens"):
        do_pedido = {i["id_produto"]: i for i in antes}
        ids_cat = [int(i["id_item_catalogo"]) for i in dados["itens"] if i.get("id_item_catalogo")]
        catalogo = (_itens_do_catalogo(cur, id_unidade, p["id_catalogo"], ids_cat)
                    if ids_cat and p["id_catalogo"] else {})
        linhas = []
        for n, i in enumerate(dados["itens"]):
            qtd = dec(i["quantidade"])
            if i.get("id_item_catalogo"):
                c = catalogo.get(int(i["id_item_catalogo"]))
                if not c or c["preco"] is None or not c["ativo"]:
                    raise HTTPException(status_code=400,
                                        detail="Um produto escolhido não está no cardápio ou está sem preço.")
                ja = do_pedido.get(c["id_produto"])
                nome, preco, idp = ((ja["nome"], dec(ja["preco_unitario"]), ja["id_produto"]) if ja
                                    else (c["nome"], dec(c["preco"]), c["id_produto"]))
            else:
                ja = do_pedido.get(int(i["id_produto"]))
                if not ja:
                    raise HTTPException(status_code=400,
                                        detail="Para pôr um produto novo, escolha-o do cardápio.")
                nome, preco, idp = ja["nome"], dec(ja["preco_unitario"]), ja["id_produto"]
            linhas.append({"id_produto": idp, "nome": nome, "quantidade": qtd,
                           "preco_unitario": preco, "total": (qtd * preco).quantize(_CENTAVO),
                           "observacao": (i.get("observacao") or "").strip() or None,
                           "ordem": n})
        def assinatura(ls):
            return sorted((l["id_produto"], float(l["quantidade"])) for l in ls)
        alterado = assinatura(linhas) != assinatura(antes)
        if alterado:
            _gravar_itens(cur, id_pedido, linhas)
            tot = _totais(linhas, dec(p["taxa_entrega"]))
            cur.execute("UPDATE pedidos SET subtotal = %s, total = %s, alterado = true WHERE id = %s",
                        (tot["subtotal"], tot["total"], id_pedido))
    cur.execute(
        """UPDATE pedidos SET situacao = 'CONFIRMADO', confirmado_em = now(), confirmado_por = %s,
                  atualizado_em = now() WHERE id = %s""", (id_usuario, id_pedido))
    _historico(cur, id_pedido, "CONFIRMADO", "NOVO", "CONFIRMADO",
               {"trocado": True, "pedido_pelo_cliente": antes,
                "observacao": dados.get("observacao")} if alterado
               else ({"observacao": dados.get("observacao")} if dados.get("observacao") else None),
               id_usuario)
    from services import whatsapp
    whatsapp.pedido_confirmado(cur, id_unidade, id_pedido)
    return obter(cur, id_unidade, id_pedido)


def _mudar(cur, id_unidade: int, id_pedido: int, id_usuario: int, de: tuple, para: str,
           motivo: str | None = None) -> dict:
    p = _pedido(cur, id_unidade, id_pedido, travar=True)
    if p["situacao"] not in de:
        raise HTTPException(status_code=409,
                            detail=f"Pedido {p['situacao'].lower()} não pode ir para {para.lower()}.")
    extra = ", entregue_em = now()" if para == "ENTREGUE" else ""
    cur.execute(f"""UPDATE pedidos SET situacao = %s, motivo = coalesce(%s, motivo),
                           atualizado_em = now(){extra} WHERE id = %s""",
                (para, motivo, id_pedido))
    _historico(cur, id_pedido, para, p["situacao"], para, {"motivo": motivo} if motivo else None,
               id_usuario)
    return obter(cur, id_unidade, id_pedido)


def recusar(cur, id_unidade, id_pedido, id_usuario, motivo) -> dict:
    return _mudar(cur, id_unidade, id_pedido, id_usuario, ("NOVO",), "RECUSADO", motivo)


def cancelar(cur, id_unidade, id_pedido, id_usuario, motivo) -> dict:
    return _mudar(cur, id_unidade, id_pedido, id_usuario, ("NOVO", "CONFIRMADO"), "CANCELADO", motivo)


def entregar(cur, id_unidade, id_pedido, id_usuario) -> dict:
    return _mudar(cur, id_unidade, id_pedido, id_usuario, ("CONFIRMADO",), "ENTREGUE")


def lancado_no_pdv(cur, id_unidade: int, id_pedido: int, id_usuario: int, cupom: str | None) -> dict:
    """🔑 A casa lançou no PDV. Marca — não situação —, e o cupom pode ser informado depois."""
    p = _pedido(cur, id_unidade, id_pedido, travar=True)
    if p["situacao"] not in ("CONFIRMADO", "ENTREGUE"):
        raise HTTPException(status_code=409, detail="Confirme o pedido antes de lançá-lo no PDV.")
    cupom = (cupom or "").strip() or None
    cur.execute(
        """UPDATE pedidos SET lancado_pdv_em = coalesce(lancado_pdv_em, now()),
                  lancado_por = coalesce(lancado_por, %s), cupom_pdv = coalesce(%s, cupom_pdv),
                  id_venda = CASE WHEN %s::text IS NOT NULL AND %s::text IS DISTINCT FROM cupom_pdv
                                  THEN NULL ELSE id_venda END,
                  atualizado_em = now() WHERE id = %s""",
        (id_usuario, cupom, cupom, cupom, id_pedido))
    _historico(cur, id_pedido, "LANCADO_PDV", None, None, {"cupom": cupom}, id_usuario)
    return obter(cur, id_unidade, id_pedido)


def pago(cur, id_unidade: int, id_pedido: int, id_usuario: int, como: str) -> dict:
    p = _pedido(cur, id_unidade, id_pedido, travar=True)
    if p["situacao"] in ("RECUSADO", "CANCELADO"):
        raise HTTPException(status_code=409, detail="Pedido recusado ou cancelado não recebe pagamento.")
    cur.execute("UPDATE pedidos SET pago_em = now(), pago_como = %s, atualizado_em = now() WHERE id = %s",
                (como, id_pedido))
    _historico(cur, id_pedido, "PAGO", None, None, {"como": como}, id_usuario)
    return obter(cur, id_unidade, id_pedido)


def painel(cur, id_unidade: int) -> dict:
    """As três colunas: confirmar, lançar no PDV, e o que é para hoje e depois."""
    def colunas(onde: str, ordem: str = "p.para_quando, p.numero") -> list[dict]:
        cur.execute(_LISTA + f" WHERE p.id_unidade = %s AND {onde} ORDER BY {ordem} LIMIT 60",
                    (id_unidade,))
        return [_linha(dict(r)) for r in cur.fetchall()]
    novos = colunas("p.situacao = 'NOVO'")
    sem_pdv = colunas("p.situacao IN ('CONFIRMADO', 'ENTREGUE') AND p.lancado_pdv_em IS NULL")
    agenda = colunas("p.situacao = 'CONFIRMADO'")
    for l in sem_pdv:
        _ligar_venda(cur, {"id": l["id"], "id_unidade": id_unidade, "cupom_pdv": l["cupom_pdv"],
                           "id_venda": l["id_venda"]})
    return {"novos": novos, "sem_pdv": sem_pdv, "confirmados": agenda,
            "agora": _agora(cur).isoformat()}


def inicio(cur, id_unidade: int) -> dict | None:
    """O bloco do Início: nulo quando a loja nunca recebeu pedido."""
    cur.execute(
        """SELECT count(*) FILTER (WHERE situacao = 'NOVO') AS novos,
                  count(*) FILTER (WHERE situacao IN ('NOVO', 'CONFIRMADO')) AS abertos,
                  count(*) FILTER (WHERE situacao IN ('CONFIRMADO', 'ENTREGUE')
                                     AND lancado_pdv_em IS NULL) AS sem_pdv,
                  count(*) FILTER (WHERE situacao = 'CONFIRMADO'
                                     AND (para_quando AT TIME ZONE %s)::date
                                         = (now() AT TIME ZONE %s)::date) AS hoje,
                  count(*) AS todos
             FROM pedidos WHERE id_unidade = %s""", (FUSO_DA_CASA, FUSO_DA_CASA, id_unidade))
    r = dict(cur.fetchone())
    if not r["todos"]:
        return None
    cur.execute(_LISTA + """ WHERE p.id_unidade = %s AND p.situacao IN ('NOVO', 'CONFIRMADO')
                             ORDER BY (p.situacao = 'NOVO') DESC, p.para_quando LIMIT 10""",
                (id_unidade,))
    return r | {"linhas": [_linha(dict(x)) for x in cur.fetchall()]}


def alertas(cur, id_unidade: int) -> dict:
    cur.execute(
        """SELECT count(*) FILTER (WHERE situacao = 'NOVO'
                                     AND criado_em < now() - interval '15 minutes') AS parados,
                  count(*) FILTER (WHERE situacao IN ('CONFIRMADO', 'ENTREGUE')
                                     AND lancado_pdv_em IS NULL) AS sem_pdv
             FROM pedidos WHERE id_unidade = %s""", (id_unidade,))
    return dict(cur.fetchone())


# ---------------------------------------------------------------- o papel

def pdf(cur, id_unidade: int, id_pedido: int) -> bytes:
    """O pedido numa folha — para a cozinha, se precisar (a comanda de verdade é a do PDV)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    p = obter(cur, id_unidade, id_pedido)
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Pedido {p['numero']}")
    x, y = 18 * mm, A4[1] - 22 * mm

    def linha(texto, fonte="Helvetica", tam=11, pula=6):
        nonlocal y
        c.setFont(fonte, tam)
        c.drawString(x, y, texto)
        y -= pula * mm

    quando = p["para_quando"].astimezone(_fuso())
    linha(f"PEDIDO {p['numero']}", "Helvetica-Bold", 20, 10)
    linha(f"{p['modo_rotulo']} · {quando:%d/%m/%Y às %H:%M}", "Helvetica-Bold", 13, 8)
    linha(f"Cliente: {p['nome']} · {p['telefone']}")
    if p["endereco"]:
        linha(f"Endereço: {p['endereco']}")
    linha(f"Pagamento: {p['pagamento_rotulo']}" + (f" · pago ({p['pago_como']})" if p["pago_em"] else ""))
    if p["cupom_pdv"]:
        linha(f"Cupom no PDV: {p['cupom_pdv']}")
    y -= 3 * mm
    for i in p["itens"]:
        q = f"{i['quantidade']:g}".replace(".", ",")
        linha(f"{q} x {i['nome']}", "Helvetica-Bold", 12, 6)
        if i["observacao"]:
            linha(f"     obs.: {i['observacao']}", "Helvetica-Oblique", 10, 6)
    y -= 3 * mm
    if p["observacao"]:
        linha(f"Observação: {p['observacao']}", "Helvetica-Oblique", 11, 8)
    total = f"{p['total']:.2f}".replace(".", ",")
    linha(f"Total: R$ {total}", "Helvetica-Bold", 13, 8)
    c.save()
    return buf.getvalue()
