"""Ordem de compra: o que precisa ser comprado, e o que já foi.

🔑 **Comprado não é recebido.** Este serviço não escreve no razão nem em custo: o estoque
só anda quando a nota é lançada. Ver `docs/ordem-de-compra-estudo.md`.

⚠️ Toda mudança de situação lê a linha com `FOR UPDATE`: duas pessoas no mercado marcando
o mesmo item é o caso normal, e a segunda precisa saber que a primeira já comprou.
"""

from datetime import date
from decimal import ROUND_CEILING, Decimal

from fastapi import HTTPException

A_COMPRAR, COMPRADO, CANCELADO = "A_COMPRAR", "COMPRADO", "CANCELADO"
# 🔑 **Aprovação** (migração 165, pedido do dono de 25/11/2026): quem não tem
# `compras.ordem_aprovar` pede em AGUARDANDO, e só o aprovado vai para A comprar.
AGUARDANDO, RECUSADO = "AGUARDANDO", "RECUSADO"
ABERTOS = (AGUARDANDO, A_COMPRAR)
SITUACOES = {AGUARDANDO: "Aguardando aprovação", A_COMPRAR: "A comprar", COMPRADO: "Comprado",
             RECUSADO: "Recusado"}

# 🔑 **Para quando** (migração 159, modelo do dono de 24/11/2026). A ordem é a de A comprar:
# o mais urgente primeiro, e dentro de cada um o que espera há mais tempo.
URGENCIAS = {"HOJE": "Urgente — hoje", "SEMANA": "Esta semana", "PODE_ESPERAR": "Pode esperar"}
_PESO = {"HOJE": 0, "SEMANA": 1, "PODE_ESPERAR": 2}

_COLUNAS = """
    i.id, i.id_unidade, i.id_produto, i.descricao_livre, i.quantidade, i.quantidade_pedida,
    i.um, i.observacao, i.status, i.urgencia, i.id_item_origem, i.id_fornecedor, i.criado_em,
    i.criado_por, i.comprado_em, i.comprado_por, i.aprovado_em, i.aprovado_por, i.recusado_em,
    i.motivo_recusa, ua.nome AS aprovado_por_nome, ur.nome AS recusado_por_nome,
    -- 🔑 "Pedido por: Cozinha" (modelo do dono): o setor de quem pediu, de `usuario_setores`.
    -- Sem setor, a tela mostra o nome.
    (SELECT string_agg(s.nome, ', ' ORDER BY s.nome) FROM usuario_setores us
       JOIN setores s ON s.id = us.id_setor WHERE us.id_usuario = i.criado_por) AS setor_pedido,
    coalesce(p.nome, i.descricao_livre) AS item, p.codigo,
    (i.id_produto IS NULL) AS fora_do_cadastro,
    uc.nome AS pedido_por, uq.nome AS comprado_por_nome,
    coalesce(f.nome_fantasia, f.nome) AS fornecedor"""

_JUNTAS = """
    FROM ordem_compra_itens i
    LEFT JOIN produtos p ON p.id = i.id_produto
    LEFT JOIN usuarios uc ON uc.id = i.criado_por
    LEFT JOIN usuarios uq ON uq.id = i.comprado_por
    LEFT JOIN usuarios ua ON ua.id = i.aprovado_por
    LEFT JOIN usuarios ur ON ur.id = i.recusado_por
    LEFT JOIN fornecedores f ON f.id = i.id_fornecedor"""


def consulta_da_lista(id_unidade: int, status: list[str], de: date | None = None,
                      ate: date | None = None, busca: str | None = None) -> tuple[str, dict]:
    """A consulta da tela e do relatório — uma só, para os dois não divergirem.

    O período é pela data da compra (ou da recusa) e, no que está aberto, pela do pedido.
    Aberto (aguardando ou a comprar) vem do mais urgente ao menos, e dentro dele o mais antigo.
    """
    termo = (busca or "").strip() or None
    sql = f"""SELECT {_COLUNAS} {_JUNTAS}
        WHERE i.id_unidade = %(u)s AND i.status = ANY(%(status)s)
          AND (%(de)s::date IS NULL OR
               coalesce(i.comprado_em, i.recusado_em, i.criado_em)::date >= %(de)s)
          AND (%(ate)s::date IS NULL OR
               coalesce(i.comprado_em, i.recusado_em, i.criado_em)::date <= %(ate)s)
          AND (%(busca)s::text IS NULL OR coalesce(p.nome, i.descricao_livre) ILIKE
               '%%' || %(busca)s || '%%' OR p.codigo ILIKE '%%' || %(busca)s || '%%')
        ORDER BY (i.status NOT IN ('AGUARDANDO', 'A_COMPRAR')),
                 CASE WHEN i.status IN ('AGUARDANDO', 'A_COMPRAR') THEN
                      CASE i.urgencia WHEN 'HOJE' THEN 0 WHEN 'SEMANA' THEN 1 ELSE 2 END END,
                 CASE WHEN i.status IN ('AGUARDANDO', 'A_COMPRAR') THEN i.criado_em END,
                 coalesce(i.comprado_em, i.recusado_em, i.criado_em) DESC, i.id DESC"""
    return sql, {"u": id_unidade, "status": status, "de": de, "ate": ate, "busca": termo}


def resumo(cur, id_unidade: int) -> dict:
    cur.execute("""SELECT count(*) FILTER (WHERE status = 'A_COMPRAR') AS a_comprar,
                          count(*) FILTER (WHERE status = 'AGUARDANDO') AS aguardando
                     FROM ordem_compra_itens
                    WHERE id_unidade = %s AND status IN ('A_COMPRAR', 'AGUARDANDO')""",
                (id_unidade,))
    r = cur.fetchone()
    return {"a_comprar": r["a_comprar"], "aguardando": r["aguardando"]}


def _unidades_do_produto(cur, produto: dict) -> list[dict]:
    """Em que unidades este produto se pede: a de compra, as embalagens e a de estoque."""
    cur.execute("""SELECT um, fator, padrao FROM produto_unidades
                    WHERE id_produto = %s ORDER BY padrao DESC, fator""", (produto["id"],))
    return _montar_unidades(produto, cur.fetchall())


def _montar_unidades(produto: dict, embalagens: list) -> list[dict]:
    """A primeira é a de pedir: a embalagem padrão, senão a de compra, senão a de estoque.
    `fator` = quantas unidades de estoque cabem em uma."""
    unidades: dict[str, dict] = {}
    for r in embalagens:
        unidades.setdefault(r["um"].upper(), {"um": r["um"], "fator": r["fator"]})
    if produto["um_compra"]:
        unidades.setdefault(produto["um_compra"].upper(),
                            {"um": produto["um_compra"], "fator": produto["fator_compra"]})
    if produto["um_estoque"]:
        unidades.setdefault(produto["um_estoque"].upper(),
                            {"um": produto["um_estoque"], "fator": Decimal(1)})
    return list(unidades.values())


def _produto(cur, id_produto: int) -> dict:
    cur.execute("""SELECT id, nome, tipo, ativo, status, um_estoque, um_compra, fator_compra,
                          producao_propria, modo_producao
                     FROM produtos WHERE id = %s""", (id_produto,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return dict(p)


# 🔑 **Só entra o que se COMPRA** (24/11/2026, pedido do dono: "listar somente os produtos que
# são comprados e deixar de fora os produzidos"). Prato, preparo e kit a casa faz: repor é a
# agenda de produção. ⚠️ É o TIPO, não `producao_propria`: há 339 PRODUZIDO sem essa marca
# (pratos do PDV), e nenhum deles se compra. O filtro `comprado` de `/produtos` usa o mesmo.
TIPOS_PRODUZIDOS = ("PRODUZIDO", "KIT")


def _exigir_comprado(produto: dict) -> None:
    if produto["tipo"] in TIPOS_PRODUZIDOS:
        raise HTTPException(
            status_code=409,
            detail=f"{produto['nome']} é produzido pela casa e não entra na ordem de compra. "
                   "Para repor, use a agenda de produção.")


def opcoes_do_produto(cur, id_unidade: int, id_produto: int) -> dict:
    """O que a tela precisa ao escolher o produto: unidades e pedidos em aberto."""
    p = _produto(cur, id_produto)
    _exigir_comprado(p)
    unidades = _unidades_do_produto(cur, p)
    cur.execute(
        """SELECT i.id, i.quantidade, i.um, i.observacao, i.status, u.nome AS pedido_por
             FROM ordem_compra_itens i LEFT JOIN usuarios u ON u.id = i.criado_por
            WHERE i.id_unidade = %s AND i.id_produto = %s
              AND i.status IN ('AGUARDANDO', 'A_COMPRAR')
            ORDER BY i.criado_em""", (id_unidade, id_produto))
    return {
        "id": p["id"], "nome": p["nome"], "unidades": unidades,
        "um_padrao": unidades[0]["um"] if unidades else None,
        "abertos": [dict(r) for r in cur.fetchall()],
    }


def _sigla(cur, um: str, produto: dict | None) -> str:
    """A sigla como está no cadastro, e só uma em que este produto se pede."""
    cur.execute("SELECT sigla FROM unidades_medida WHERE upper(sigla) = upper(%s)", (um.strip(),))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=400, detail=f"Unidade {um} não existe no cadastro.")
    if produto:
        aceitas = {u["um"].upper() for u in _unidades_do_produto(cur, produto)}
        if aceitas and linha["sigla"].upper() not in aceitas:
            raise HTTPException(
                status_code=400,
                detail=f"{produto['nome']} não é pedido em {linha['sigla']}. "
                       f"Use: {', '.join(sorted(aceitas))}.")
    return linha["sigla"]


def _texto(v: str | None) -> str | None:
    return (v or "").strip() or None


def _travar(cur, id_unidade: int, id_item: int) -> dict:
    cur.execute("""SELECT * FROM ordem_compra_itens
                    WHERE id = %s AND id_unidade = %s FOR UPDATE""", (id_item, id_unidade))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Item não encontrado nesta loja.")
    return dict(linha)


def _nome_do_item(cur, linha: dict) -> str:
    if not linha["id_produto"]:
        return linha["descricao_livre"]
    cur.execute("SELECT nome FROM produtos WHERE id = %s", (linha["id_produto"],))
    return cur.fetchone()["nome"]


def _exigir_aberto(cur, linha: dict, aceitas: tuple[str, ...] = ABERTOS) -> None:
    """A frase diz quem chegou antes: um 409 seco faria a pessoa tentar de novo.

    `aceitas` = as situações em que a ação vale. Comprar só aceita A_COMPRAR; aprovar, só
    AGUARDANDO; corrigir e cancelar, as duas abertas.
    """
    if linha["status"] in aceitas:
        return
    nome = _nome_do_item(cur, linha)
    if linha["status"] == AGUARDANDO:
        raise HTTPException(status_code=409,
                            detail=f"{nome} ainda aguarda aprovação: só se compra o aprovado.")
    if linha["status"] == A_COMPRAR:
        quem = ""
        if linha.get("aprovado_por"):
            cur.execute("SELECT nome FROM usuarios WHERE id = %s", (linha["aprovado_por"],))
            r = cur.fetchone()
            quem = f" por {r['nome']}" if r else ""
        raise HTTPException(status_code=409, detail=f"{nome} já foi aprovado{quem}.")
    if linha["status"] == RECUSADO:
        cur.execute("SELECT nome FROM usuarios WHERE id = %s", (linha["recusado_por"],))
        r = cur.fetchone()
        raise HTTPException(status_code=409,
                            detail=f"{nome} foi recusado por {r['nome'] if r else '—'}.")
    if linha["status"] == COMPRADO:
        cur.execute(
            """SELECT u.nome, to_char(i.comprado_em, 'DD/MM "às" HH24:MI') AS quando
                 FROM ordem_compra_itens i LEFT JOIN usuarios u ON u.id = i.comprado_por
                WHERE i.id = %s""", (linha["id"],))
        r = cur.fetchone()
        raise HTTPException(status_code=409,
                            detail=f"{nome} já foi comprado por {r['nome']} em {r['quando']}.")
    raise HTTPException(status_code=409, detail=f"{nome} foi cancelado e saiu da lista.")


def exigir_dono_ou_comprador(linha: dict, id_usuario: int, pode_comprar: bool) -> None:
    """`pode_comprar` aqui = compra OU aprova: os dois corrigem e cancelam qualquer pedido."""
    if not pode_comprar and linha["criado_por"] != id_usuario:
        raise HTTPException(status_code=403,
                            detail="Só quem pediu, quem aprova ou quem compra pode mexer neste item.")


def _situacao_nova(pode_aprovar: bool) -> str:
    """🔑 Quem aprova pede direto em A comprar; os outros, em Aguardando aprovação."""
    return A_COMPRAR if pode_aprovar else AGUARDANDO


def adicionar(cur, id_unidade: int, id_usuario: int, dados: dict, pode_aprovar: bool) -> dict:
    """Um item na lista.

    🔑 **Sem `compras.ordem_aprovar`, o pedido nasce AGUARDANDO** e só vai para A comprar
    quando alguém que aprova aprovar (migração 165).
    ⚠️ **Somar só na linha da MESMA situação.** Quem não aprova somando num pedido já aprovado
    aumentaria a compra sem aprovação: o que ele pede vira linha nova, aguardando. E quem aprova
    não soma no pedido de outro que ainda aguarda (aprovaria a linha inteira sem querer).
    """
    situacao = _situacao_nova(pode_aprovar)
    produto = None
    if dados.get("id_produto"):
        produto = _produto(cur, dados["id_produto"])
        if not produto["ativo"] or produto["status"] == "ARQUIVADO":
            raise HTTPException(
                status_code=409,
                detail=f"{produto['nome']} está inativo. Reative o cadastro ou escreva o item.")
        _exigir_comprado(produto)
    um = _sigla(cur, dados["um"], produto)
    observacao = _texto(dados.get("observacao"))

    alvo = None
    if dados.get("somar_em"):
        alvo = _travar(cur, id_unidade, dados["somar_em"])
        _exigir_aberto(cur, alvo)
        if not produto or alvo["id_produto"] != produto["id"] or alvo["um"].upper() != um.upper():
            raise HTTPException(status_code=400,
                                detail="Só dá para somar no mesmo produto e na mesma unidade.")
        if alvo["status"] != situacao:
            alvo = None  # vira linha nova, na situação de quem pede (ver a docstring)
    if alvo:
        juntas = " · ".join(x for x in (alvo["observacao"], observacao) if x) or None
        # Somar nunca deixa o pedido menos urgente: vale o mais urgente dos dois.
        nova = dados.get("urgencia") or "SEMANA"
        urgencia = min((alvo["urgencia"], nova), key=lambda u: _PESO[u])
        cur.execute(
            """UPDATE ordem_compra_itens SET quantidade = quantidade + %s, observacao = %s,
                      urgencia = %s
                WHERE id = %s RETURNING quantidade""",
            (dados["quantidade"], juntas[:300] if juntas else None, urgencia, alvo["id"]))
        return {"id": alvo["id"], "somado": True, "quantidade": cur.fetchone()["quantidade"],
                "item": produto["nome"], "status": situacao,
                "message": f"Somado ao pedido de {produto['nome']}"
                           + ("." if pode_aprovar else ", que aguarda aprovação.")}

    livre = None if produto else _texto(dados.get("descricao_livre"))
    cur.execute(
        """INSERT INTO ordem_compra_itens
               (id_unidade, id_produto, descricao_livre, quantidade, um, observacao, urgencia,
                criado_por, status, aprovado_em, aprovado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                   CASE WHEN %s THEN now() END, CASE WHEN %s THEN %s::int END) RETURNING id""",
        (id_unidade, produto["id"] if produto else None, livre, dados["quantidade"], um,
         observacao, dados.get("urgencia") or "SEMANA", id_usuario, situacao,
         pode_aprovar, pode_aprovar, id_usuario))
    nome = produto["nome"] if produto else livre
    return {"id": cur.fetchone()["id"], "somado": False, "quantidade": dados["quantidade"],
            "item": nome, "status": situacao,
            "message": f"{nome} na lista." if pode_aprovar
                       else f"{nome} foi para aprovação."}


def corrigir(cur, id_unidade: int, id_item: int, id_usuario: int, pode_comprar: bool,
             dados: dict, pode_aprovar: bool = False) -> dict:
    """⚠️ **Pedido já aprovado, quem só pediu não corrige** (migração 165): mudar a quantidade
    depois do sim seria comprar sem aprovação. Cancela e pede de novo. Linha de antes da
    aprovação existir (`aprovado_por` nulo) segue a regra antiga."""
    linha = _travar(cur, id_unidade, id_item)
    exigir_dono_ou_comprador(linha, id_usuario, pode_comprar or pode_aprovar)
    _exigir_aberto(cur, linha)
    if (linha["status"] == A_COMPRAR and linha["aprovado_por"]
            and not (pode_comprar or pode_aprovar)):
        raise HTTPException(
            status_code=409,
            detail="Este pedido já foi aprovado e não pode mais ser alterado por quem pediu. "
                   "Cancele e peça de novo, ou peça a quem aprova para corrigir.")
    produto = _produto(cur, linha["id_produto"]) if linha["id_produto"] else None
    um = _sigla(cur, dados["um"], produto)
    cur.execute("""UPDATE ordem_compra_itens SET quantidade = %s, um = %s, observacao = %s,
                          urgencia = coalesce(%s, urgencia)
                    WHERE id = %s""",
                (dados["quantidade"], um, _texto(dados.get("observacao")),
                 dados.get("urgencia"), id_item))
    return {"id": id_item, "antes": {"quantidade": linha["quantidade"], "um": linha["um"],
                                     "observacao": linha["observacao"],
                                     "urgencia": linha["urgencia"]},
            "message": "Pedido corrigido."}


def cancelar(cur, id_unidade: int, id_item: int, id_usuario: int, pode_comprar: bool,
             pode_aprovar: bool = False) -> dict:
    linha = _travar(cur, id_unidade, id_item)
    exigir_dono_ou_comprador(linha, id_usuario, pode_comprar or pode_aprovar)
    _exigir_aberto(cur, linha)
    cur.execute("""UPDATE ordem_compra_itens
                      SET status = 'CANCELADO', cancelado_em = now(), cancelado_por = %s
                    WHERE id = %s""", (id_usuario, id_item))
    return {"id": id_item, "item": _nome_do_item(cur, linha), "message": "Pedido cancelado."}


def comprar(cur, id_unidade: int, id_usuario: int, itens: list[dict],
            id_fornecedor: int | None = None) -> dict:
    """Marca como comprado, tudo ou nada.

    🔑 **Comprou menos que o pedido: a linha se divide.** O comprado nasce numa linha nova
    e o que falta continua na lista, na linha original.
    ⚠️ Trava em ordem de id: duas pessoas marcando os mesmos itens em ordens diferentes
    dariam deadlock.
    """
    ids = [i["id"] for i in itens]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="O mesmo item veio duas vezes.")
    if id_fornecedor is not None:
        cur.execute("SELECT 1 FROM fornecedores WHERE id = %s AND ativo", (id_fornecedor,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Fornecedor não encontrado ou inativo.")

    cur.execute("""SELECT * FROM ordem_compra_itens
                    WHERE id = ANY(%s) AND id_unidade = %s ORDER BY id FOR UPDATE""",
                (ids, id_unidade))
    linhas = {r["id"]: dict(r) for r in cur.fetchall()}
    if len(linhas) != len(ids):
        raise HTTPException(status_code=404, detail="Item não encontrado nesta loja.")
    for linha in linhas.values():
        _exigir_aberto(cur, linha, (A_COMPRAR,))

    comprados: list[int] = []
    parciais = 0
    for pedido in sorted(itens, key=lambda x: x["id"]):
        linha = linhas[pedido["id"]]
        total = linha["quantidade"]
        qtd = pedido.get("quantidade") or total
        if qtd < total:
            parciais += 1
            cur.execute("UPDATE ordem_compra_itens SET quantidade = quantidade - %s WHERE id = %s",
                        (qtd, linha["id"]))
            cur.execute(
                """INSERT INTO ordem_compra_itens
                       (id_unidade, id_produto, descricao_livre, quantidade, um, observacao,
                        urgencia, status, id_item_origem, id_fornecedor, criado_em, criado_por,
                        comprado_em, comprado_por, aprovado_em, aprovado_por)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'COMPRADO', %s, %s, %s, %s, now(), %s,
                           %s, %s)
                   RETURNING id""",
                (linha["id_unidade"], linha["id_produto"], linha["descricao_livre"], qtd,
                 linha["um"], linha["observacao"], linha["urgencia"], linha["id"], id_fornecedor,
                 linha["criado_em"], linha["criado_por"], id_usuario,
                 linha["aprovado_em"], linha["aprovado_por"]))
            comprados.append(cur.fetchone()["id"])
        else:
            cur.execute(
                """UPDATE ordem_compra_itens
                      SET status = 'COMPRADO', comprado_em = now(), comprado_por = %s,
                          id_fornecedor = %s, quantidade = %s, quantidade_pedida = %s
                    WHERE id = %s""",
                (id_usuario, id_fornecedor, qtd, total if qtd > total else None, linha["id"]))
            comprados.append(linha["id"])

    n = len(comprados)
    frase = "1 item comprado" if n == 1 else f"{n} itens comprados"
    if parciais:
        frase += " (o que faltou continua na lista)"
    return {"ids": comprados, "parciais": parciais, "message": f"{frase}."}


def voltar(cur, id_unidade: int, ids: list[int]) -> dict:
    """Devolve à lista o que foi marcado por engano.

    🔑 **A parte comprada de uma compra parcial volta para a linha de origem** enquanto ela
    estiver aberta, e os 6 + 4 viram de novo os 10 pedidos. A linha da parte fica como
    CANCELADO, sem apagar: é história de quem marcou.
    """
    unicos = sorted(set(ids))
    cur.execute("""SELECT id_item_origem FROM ordem_compra_itens
                    WHERE id = ANY(%s) AND id_unidade = %s AND id_item_origem IS NOT NULL""",
                (unicos, id_unidade))
    origens = [r["id_item_origem"] for r in cur.fetchall()]
    cur.execute("""SELECT * FROM ordem_compra_itens
                    WHERE id = ANY(%s) AND id_unidade = %s ORDER BY id FOR UPDATE""",
                (unicos + origens, id_unidade))
    linhas = {r["id"]: dict(r) for r in cur.fetchall()}
    if any(i not in linhas for i in unicos):
        raise HTTPException(status_code=404, detail="Item não encontrado nesta loja.")
    for i in unicos:
        if linhas[i]["status"] != COMPRADO:
            nome = _nome_do_item(cur, linhas[i])
            raise HTTPException(status_code=409, detail=f"{nome} não está em Comprados.")

    # ⚠️ Em ordem de id: se a origem também veio no pedido, ela reabre antes da parte.
    for i in unicos:
        linha = linhas[i]
        origem = linhas.get(linha["id_item_origem"])
        if origem and origem["status"] == A_COMPRAR and origem["um"] == linha["um"]:
            cur.execute("UPDATE ordem_compra_itens SET quantidade = quantidade + %s WHERE id = %s",
                        (linha["quantidade"], origem["id"]))
            origem["quantidade"] += linha["quantidade"]
            cur.execute("""UPDATE ordem_compra_itens
                              SET status = 'CANCELADO', cancelado_em = now(),
                                  cancelado_por = comprado_por
                            WHERE id = %s""", (i,))
            linha["status"] = CANCELADO
        else:
            cur.execute(
                """UPDATE ordem_compra_itens
                      SET status = 'A_COMPRAR', comprado_em = NULL, comprado_por = NULL,
                          id_fornecedor = NULL, quantidade = coalesce(quantidade_pedida, quantidade),
                          quantidade_pedida = NULL
                    WHERE id = %s""", (i,))
            linha["status"] = A_COMPRAR
    n = len(unicos)
    return {"ids": unicos,
            "message": "1 item voltou à lista." if n == 1 else f"{n} itens voltaram à lista."}


def _travar_varios(cur, id_unidade: int, ids: list[int]) -> list[dict]:
    """⚠️ Em ordem de id, como em `comprar`: dois aprovadores no mesmo lote não dão deadlock."""
    unicos = sorted(set(ids))
    if len(unicos) != len(ids):
        raise HTTPException(status_code=400, detail="O mesmo item veio duas vezes.")
    cur.execute("""SELECT * FROM ordem_compra_itens
                    WHERE id = ANY(%s) AND id_unidade = %s ORDER BY id FOR UPDATE""",
                (unicos, id_unidade))
    linhas = [dict(r) for r in cur.fetchall()]
    if len(linhas) != len(unicos):
        raise HTTPException(status_code=404, detail="Item não encontrado nesta loja.")
    return linhas


def aprovar(cur, id_unidade: int, id_usuario: int, ids: list[int]) -> dict:
    """Aprovado vai para A comprar. Tudo ou nada: o segundo aprovador recebe 409 com o nome
    de quem aprovou antes."""
    linhas = _travar_varios(cur, id_unidade, ids)
    for linha in linhas:
        _exigir_aberto(cur, linha, (AGUARDANDO,))
    cur.execute("""UPDATE ordem_compra_itens
                      SET status = 'A_COMPRAR', aprovado_em = now(), aprovado_por = %s
                    WHERE id = ANY(%s)""", (id_usuario, [l["id"] for l in linhas]))
    n = len(linhas)
    return {"ids": [l["id"] for l in linhas],
            "message": "1 pedido aprovado: está em A comprar." if n == 1
                       else f"{n} pedidos aprovados: estão em A comprar."}


def recusar(cur, id_unidade: int, id_usuario: int, ids: list[int], motivo: str | None) -> dict:
    """🔑 Recusado é situação própria, não cancelado: quem pediu vê na aba Recusados, e o
    motivo junto. Nada se apaga."""
    linhas = _travar_varios(cur, id_unidade, ids)
    for linha in linhas:
        _exigir_aberto(cur, linha, (AGUARDANDO,))
    cur.execute("""UPDATE ordem_compra_itens
                      SET status = 'RECUSADO', recusado_em = now(), recusado_por = %s,
                          motivo_recusa = %s
                    WHERE id = ANY(%s)""",
                (id_usuario, _texto(motivo), [l["id"] for l in linhas]))
    n = len(linhas)
    return {"ids": [l["id"] for l in linhas],
            "message": "1 pedido recusado." if n == 1 else f"{n} pedidos recusados."}


def sugestoes(cur, id_unidade: int) -> list[dict]:
    """O que está abaixo do mínimo e se compra, com a quantidade para pedir (etapa 2).

    🔑 **Parte do PRODUTO, não do saldo.** O painel parte de `estoque_saldos`, e produto com
    mínimo e nenhuma linha de saldo na loja (o que mais falta) sumia da lista. Aqui o saldo é
    LEFT JOIN, e quem nunca teve estoque aparece com zero.
    🔑 **Repõe até o máximo quando há máximo**, senão até o mínimo.
    ⚠️ Saldo negativo conta como zero: o negativo é erro de lançamento, não mercadoria a comprar.
    ⚠️ O que já está em A comprar é descontado, convertido pela embalagem. Coberto, a linha
    vem com `sugerida = 0` e a tela mostra "já na lista".
    ⚠️ O mínimo é do produto, não da loja (`produtos.estoque_minimo`): com duas lojas, as duas
    usam o mesmo número.
    """
    cur.execute(
        """SELECT p.id AS id_produto, p.codigo, p.nome, p.um_estoque, p.um_compra,
                  p.fator_compra, p.estoque_minimo, p.estoque_maximo,
                  coalesce(sum(s.quantidade), 0) AS saldo,
                  (SELECT coalesce(f.nome_fantasia, f.nome) FROM produto_fornecedor pf
                     JOIN fornecedores f ON f.id = pf.id_fornecedor
                    WHERE pf.id_produto = p.id
                    ORDER BY pf.preferencial DESC, f.nome LIMIT 1) AS fornecedor
             FROM produtos p
             LEFT JOIN estoque_saldos s ON s.id_produto = p.id AND s.id_unidade = %s
            WHERE p.ativo AND p.status <> 'ARQUIVADO' AND p.controla_estoque
              AND p.um_estoque IS NOT NULL
              AND p.estoque_minimo > 0 AND p.tipo <> ALL(%s)
            GROUP BY p.id
           HAVING coalesce(sum(s.quantidade), 0) < p.estoque_minimo
            ORDER BY coalesce(sum(s.quantidade), 0) / p.estoque_minimo, lower(p.nome)""",
        (id_unidade, list(TIPOS_PRODUZIDOS)))
    linhas = [dict(r) for r in cur.fetchall()]
    if not linhas:
        return []
    ids = [l["id_produto"] for l in linhas]
    cur.execute("""SELECT id_produto, um, fator, padrao FROM produto_unidades
                    WHERE id_produto = ANY(%s) ORDER BY padrao DESC, fator""", (ids,))
    embalagens: dict[int, list] = {}
    for r in cur.fetchall():
        embalagens.setdefault(r["id_produto"], []).append(r)
    cur.execute("""SELECT id_produto, um, sum(quantidade) AS quantidade FROM ordem_compra_itens
                    WHERE id_unidade = %s AND status IN ('AGUARDANDO', 'A_COMPRAR')
                      AND id_produto = ANY(%s)
                    GROUP BY id_produto, um ORDER BY um""", (id_unidade, ids))
    abertos: dict[int, list] = {}
    for r in cur.fetchall():
        abertos.setdefault(r["id_produto"], []).append(r)

    saida = []
    for l in linhas:
        unidades = _montar_unidades(
            {"id": l["id_produto"], "um_compra": l["um_compra"],
             "fator_compra": l["fator_compra"], "um_estoque": l["um_estoque"]},
            embalagens.get(l["id_produto"], []))
        fatores = {u["um"].upper(): Decimal(u["fator"]) for u in unidades}
        na_lista = sum((Decimal(a["quantidade"]) * fatores.get(a["um"].upper(), Decimal(1))
                        for a in abertos.get(l["id_produto"], [])), Decimal(0))
        minimo, maximo = Decimal(l["estoque_minimo"]), l["estoque_maximo"]
        alvo = Decimal(maximo) if maximo and Decimal(maximo) > minimo else minimo
        saldo = Decimal(l["saldo"])
        faltam = alvo - max(saldo, Decimal(0)) - na_lista
        um = unidades[0]["um"] if unidades else l["um_estoque"]
        fator = Decimal(unidades[0]["fator"]) if unidades else Decimal(1)
        sugerida = (faltam / fator).to_integral_value(rounding=ROUND_CEILING) \
            if faltam > 0 and fator > 0 else Decimal(0)
        saida.append({
            "id_produto": l["id_produto"], "codigo": l["codigo"], "nome": l["nome"],
            "um_estoque": l["um_estoque"], "saldo": saldo, "estoque_minimo": minimo,
            "repor_ate": alvo, "ate_o_maximo": alvo != minimo,
            "na_lista": [{"quantidade": a["quantidade"], "um": a["um"]}
                         for a in abertos.get(l["id_produto"], [])],
            "faltam": max(faltam, Decimal(0)), "um": um, "fator": fator, "sugerida": sugerida,
            "unidades": unidades, "fornecedor": l["fornecedor"],
        })
    return saida


def adicionar_lote(cur, id_unidade: int, id_usuario: int, itens: list[dict],
                   pode_aprovar: bool) -> dict:
    """Vários itens de uma vez (as sugestões), tudo ou nada.

    🔑 **O que já tem linha aberta no mesmo produto e unidade SOMA nela**, sem perguntar: a
    sugestão já descontou o que estava na lista, e duas linhas de farinha confundem quem compra.
    ⚠️ Só na linha da situação de quem pede (ver `adicionar`).
    """
    situacao = _situacao_nova(pode_aprovar)
    feitos = []
    for dados in itens:
        if dados.get("id_produto") and not dados.get("somar_em"):
            cur.execute(
                """SELECT id FROM ordem_compra_itens
                    WHERE id_unidade = %s AND id_produto = %s AND status = %s
                      AND upper(um) = upper(%s)
                    ORDER BY criado_em LIMIT 1""",
                (id_unidade, dados["id_produto"], situacao, dados["um"].strip()))
            ja = cur.fetchone()
            if ja:
                dados = {**dados, "somar_em": ja["id"]}
        feitos.append(adicionar(cur, id_unidade, id_usuario, dados, pode_aprovar))
    n = len(feitos)
    frase = "1 item" if n == 1 else f"{n} itens"
    return {"ids": [f["id"] for f in feitos], "itens": feitos,
            "message": f"{frase} na lista." if pode_aprovar else f"{frase} para aprovação."}
