"""Patrimônio, etapa 3: a CONFERÊNCIA pelas plaquetas (migração 140).

🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 3 do patrimônio"* — abrir a
conferência por setor, ler as plaquetas com o celular e fechar com transferência ou baixa.

O ciclo:
1. **Abrir** (um setor ou a loja inteira): a lista dos bens ESPERADOS ali é fotografada.
2. **Ler**: cada plaqueta lida marca o bem como visto. Bem lido que não estava na lista
   entra como "de fora" (o sistema o punha em outro setor).
3. **Fechar**: visto e esperado → CONFERIDO (e "A confirmar" passa a "Em uso"); visto e de
   fora → TRANSFERIDO para o setor da conferência; não visto → mantido (NAO_ENCONTRADO) ou
   BAIXADO, por escolha de quem fecha, bem a bem.

⚠️ **Não é inventário de estoque**: confere presença de cada item, não quantidade. Nada
aqui escreve no razão.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

import relogio
from services import patrimonio as bens

STATUS = {"ABERTA": "Aberta", "FECHADA": "Fechada", "CANCELADA": "Cancelada"}
RESULTADOS = {"CONFERIDO": "Conferido", "TRANSFERIDO": "Transferido para cá",
              "NAO_ENCONTRADO": "Não encontrado (mantido)", "BAIXADO": "Baixado"}

# 🔑 **A plaqueta tem um LINK, não só o código** (`…/patrimonio/b/PAT-0001`): o leitor de
# código de barras USB e a câmera devolvem a URL inteira. O código é o que importa.
_CODIGO = re.compile(r"PAT-\d+", re.IGNORECASE)


def codigo_lido(texto: str) -> str:
    """"https://…/patrimonio/b/PAT-0003" → "PAT-0003". Sem o padrão, devolve o texto
    como veio — pode ser o APELIDO da casa ("BAR-02"), digitado à mão."""
    m = _CODIGO.search(texto or "")
    return m.group(0).upper() if m else (texto or "").strip()


def _cabecalho(cur, id_conferencia: int, id_unidade: int) -> dict:
    cur.execute(
        """SELECT c.*, s.nome AS setor, ua.nome AS aberta_por_nome, uf.nome AS fechada_por_nome
             FROM bem_conferencias c
             LEFT JOIN setores s ON s.id = c.id_setor
             LEFT JOIN usuarios ua ON ua.id = c.aberta_por
             LEFT JOIN usuarios uf ON uf.id = c.fechada_por
            WHERE c.id = %s""", (id_conferencia,))
    c = cur.fetchone()
    if not c or c["id_unidade"] != id_unidade:
        raise HTTPException(status_code=404, detail="Conferência não encontrada nesta loja")
    c = dict(c)
    c["status_txt"] = STATUS[c["status"]]
    c["escopo"] = c["setor"] or "Loja inteira"
    return c


def _aberta(cur, id_conferencia: int, id_unidade: int) -> dict:
    c = _cabecalho(cur, id_conferencia, id_unidade)
    if c["status"] != "ABERTA":
        raise HTTPException(status_code=409,
                            detail=f"Esta conferência está {c['status_txt'].lower()} — "
                                   "abra outra para ler de novo.")
    return c


_CONTAGEM = """
    count(*) FILTER (WHERE i.esperado) AS esperados,
    count(*) FILTER (WHERE i.esperado AND i.lido_em IS NOT NULL) AS lidos,
    count(*) FILTER (WHERE i.esperado AND i.lido_em IS NULL) AS faltam,
    count(*) FILTER (WHERE NOT i.esperado) AS de_fora"""


def listar(cur, id_unidade: int, limite: int = 50) -> list[dict]:
    """As conferências da loja, a aberta primeiro, com quanto foi lido."""
    cur.execute(
        f"""SELECT c.id, c.id_setor, s.nome AS setor, c.status, c.aberta_em, c.fechada_em,
                   ua.nome AS aberta_por_nome, {_CONTAGEM}
              FROM bem_conferencias c
              LEFT JOIN setores s ON s.id = c.id_setor
              LEFT JOIN usuarios ua ON ua.id = c.aberta_por
              LEFT JOIN bem_conferencia_itens i ON i.id_conferencia = c.id
             WHERE c.id_unidade = %s
             GROUP BY c.id, s.nome, ua.nome
             ORDER BY (c.status = 'ABERTA') DESC, c.aberta_em DESC
             LIMIT %s""", (id_unidade, limite))
    return [dict(r) | {"status_txt": STATUS[r["status"]], "escopo": r["setor"] or "Loja inteira"}
            for r in cur.fetchall()]


def obter(cur, id_conferencia: int, id_unidade: int) -> dict:
    """O cabeçalho, a contagem e os itens — o bem como está AGORA e como estava antes."""
    c = _cabecalho(cur, id_conferencia, id_unidade)
    cur.execute(
        f"""SELECT {_CONTAGEM} FROM bem_conferencia_itens i WHERE i.id_conferencia = %s""",
        (id_conferencia,))
    c |= dict(cur.fetchone())
    cur.execute(
        """SELECT i.id, i.id_bem, i.esperado, i.lido_em, i.resultado, i.situacao_antes,
                  sa.nome AS setor_antes, u.nome AS lido_por_nome,
                  b.codigo, b.apelido, b.descricao, b.situacao, b.criticidade,
                  s.nome AS setor, l.nome AS local
             FROM bem_conferencia_itens i
             JOIN bens b ON b.id = i.id_bem
             LEFT JOIN setores sa ON sa.id = i.id_setor_antes
             LEFT JOIN setores s ON s.id = b.id_setor
             LEFT JOIN locais_estoque l ON l.id = b.id_local
             LEFT JOIN usuarios u ON u.id = i.lido_por
            WHERE i.id_conferencia = %s
            ORDER BY i.lido_em IS NOT NULL, lower(coalesce(s.nome, 'zzz')), b.codigo""",
        (id_conferencia,))
    c["itens"] = [dict(r) | {
        "situacao_txt": bens.SITUACOES.get(r["situacao"], r["situacao"]),
        "situacao_antes_txt": bens.SITUACOES.get(r["situacao_antes"], r["situacao_antes"]),
        "resultado_txt": RESULTADOS.get(r["resultado"]) if r["resultado"] else None,
    } for r in cur.fetchall()]
    return c


def aberta_do_bem(cur, id_bem: int) -> int | None:
    """A conferência ABERTA que procura este bem (ou a da loja inteira) — a que a leitura
    pela câmera do celular usaria. Nenhuma = None."""
    cur.execute(
        """SELECT c.id FROM bem_conferencias c JOIN bens b ON b.id_unidade = c.id_unidade
            WHERE b.id = %s AND c.status = 'ABERTA'
              AND (c.id_setor IS NULL OR c.id_setor = b.id_setor)
            ORDER BY c.id_setor IS NULL LIMIT 1""", (id_bem,))
    r = cur.fetchone()
    return r["id"] if r else None


def abrir(cur, id_unidade: int, id_usuario: int, id_setor: int | None,
          observacao: str | None) -> dict:
    """Fotografa os bens esperados no setor (ou na loja) e abre a conferência.

    ⚠️ **O baixado não entra** (saiu da casa). O desativado e o "A confirmar" entram: o
    primeiro ainda ocupa lugar, e o segundo é justamente o que a conferência confirma.
    ⚠️ **Loja inteira e setor não se sobrepõem**: com as duas abertas, o mesmo bem estaria
    em duas listas, e a leitura não saberia em qual contar.
    """
    if id_setor is not None:
        cur.execute("SELECT nome, id_unidade FROM setores WHERE id = %s", (id_setor,))
        s = cur.fetchone()
        if not s or s["id_unidade"] not in (None, id_unidade):
            raise HTTPException(status_code=400, detail="Setor que não é desta loja")
    cur.execute(
        """SELECT c.id, coalesce(s.nome, 'a loja inteira') AS escopo
             FROM bem_conferencias c LEFT JOIN setores s ON s.id = c.id_setor
            WHERE c.id_unidade = %s AND c.status = 'ABERTA'
              AND (%s::int IS NULL OR c.id_setor IS NULL OR c.id_setor = %s)
            LIMIT 1""", (id_unidade, id_setor, id_setor))
    r = cur.fetchone()
    if r:
        raise HTTPException(status_code=409,
                            detail=f"Já há uma conferência aberta de {r['escopo']} "
                                   f"(nº {r['id']}) — feche ou cancele antes.")
    cur.execute(
        """INSERT INTO bem_conferencias (id_unidade, id_setor, observacao, aberta_por)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (id_unidade, id_setor, (observacao or "").strip() or None, id_usuario))
    id_conferencia = cur.fetchone()["id"]
    cur.execute(
        """INSERT INTO bem_conferencia_itens (id_conferencia, id_bem, esperado, id_setor_antes,
                                              situacao_antes)
           SELECT %s, b.id, true, b.id_setor, b.situacao
             FROM bens b
            WHERE b.id_unidade = %s AND b.situacao <> 'BAIXADO'
              AND (%s::int IS NULL OR b.id_setor = %s)""",
        (id_conferencia, id_unidade, id_setor, id_setor))
    return obter(cur, id_conferencia, id_unidade)


def ler(cur, id_conferencia: int, id_unidade: int, id_usuario: int, texto: str) -> dict:
    """Uma plaqueta lida (o link do QR, o código digitado ou o apelido da casa).

    Devolve `{"bem", "item", "novo", "ja_lido", "de_fora", "message"}` — a tela fala
    numa linha só o que aconteceu, que é o que importa com o celular na mão.
    ⚠️ **Ler duas vezes não conta duas**: a segunda responde "já lido".
    ⚠️ Bem de OUTRA loja é recusado nomeando a loja — a plaqueta foi parar no lugar errado,
    e isso é transferência entre lojas, não conferência.
    """
    _aberta(cur, id_conferencia, id_unidade)
    codigo = codigo_lido(texto)
    if not codigo:
        raise HTTPException(status_code=400, detail="Leia ou digite o código da plaqueta")
    cur.execute(
        """SELECT b.id, b.codigo, b.descricao, b.situacao, b.id_setor, b.id_unidade,
                  u.nome AS loja
             FROM bens b JOIN unidades u ON u.id = b.id_unidade
            WHERE upper(b.codigo) = upper(%s)
               OR (b.id_unidade = %s AND lower(b.apelido) = lower(%s))
            ORDER BY (upper(b.codigo) = upper(%s)) DESC LIMIT 1""",
        (codigo, id_unidade, codigo, codigo))
    b = cur.fetchone()
    if not b:
        raise HTTPException(status_code=404, detail=f"Nenhum bem com o código “{codigo}”")
    if b["id_unidade"] != id_unidade:
        raise HTTPException(status_code=409,
                            detail=f"{b['codigo']} ({b['descricao']}) é da loja {b['loja']}.")
    if b["situacao"] == "BAIXADO":
        raise HTTPException(status_code=409,
                            detail=f"{b['codigo']} ({b['descricao']}) está BAIXADO — se ele "
                                   "existe, reabra o cadastro antes de conferir.")
    cur.execute(
        """SELECT id, esperado, lido_em FROM bem_conferencia_itens
            WHERE id_conferencia = %s AND id_bem = %s FOR UPDATE""",
        (id_conferencia, b["id"]))
    item = cur.fetchone()
    novo = ja_lido = False
    if item and item["lido_em"]:
        ja_lido = True
    elif item:
        cur.execute("UPDATE bem_conferencia_itens SET lido_em = now(), lido_por = %s WHERE id = %s",
                    (id_usuario, item["id"]))
    else:
        novo = True
        cur.execute(
            """INSERT INTO bem_conferencia_itens (id_conferencia, id_bem, esperado,
                                                  id_setor_antes, situacao_antes, lido_em,
                                                  lido_por)
               VALUES (%s, %s, false, %s, %s, now(), %s) RETURNING id, esperado""",
            (id_conferencia, b["id"], b["id_setor"], b["situacao"], id_usuario))
        item = cur.fetchone()
    de_fora = not item["esperado"]
    nome = f"{b['codigo']} — {b['descricao']}"
    if ja_lido:
        msg = f"{nome}: já tinha sido lido."
    elif de_fora:
        msg = f"{nome}: lido — o sistema o punha em outro setor; no fechamento ele vem para cá."
    else:
        msg = f"{nome}: conferido."
    c = obter(cur, id_conferencia, id_unidade)
    return {"bem": dict(b), "id_item": item["id"], "novo": novo, "ja_lido": ja_lido,
            "de_fora": de_fora, "message": msg,
            "contagem": {k: c[k] for k in ("esperados", "lidos", "faltam", "de_fora")}}


def desfazer_leitura(cur, id_conferencia: int, id_unidade: int, id_item: int) -> dict:
    """A leitura errada (a plaqueta do vizinho): volta a "falta ler". O de fora some da
    lista — ele só estava nela porque foi lido."""
    _aberta(cur, id_conferencia, id_unidade)
    cur.execute("SELECT esperado FROM bem_conferencia_itens WHERE id = %s AND id_conferencia = %s",
                (id_item, id_conferencia))
    i = cur.fetchone()
    if not i:
        raise HTTPException(status_code=404, detail="Leitura não encontrada")
    if i["esperado"]:
        cur.execute("UPDATE bem_conferencia_itens SET lido_em = NULL, lido_por = NULL WHERE id = %s",
                    (id_item,))
    else:
        cur.execute("DELETE FROM bem_conferencia_itens WHERE id = %s", (id_item,))
    return obter(cur, id_conferencia, id_unidade)


def fechar(cur, id_conferencia: int, id_unidade: int, id_usuario: int, *,
           baixar: list[int], motivo_baixa: str | None, transferir: bool = True,
           confirmar: bool = True) -> dict:
    """Aplica o resultado e fecha. ⚠️ Só o que a pessoa escolheu em `baixar` é baixado —
    o não encontrado, por padrão, é MANTIDO: equipamento emprestado ou no conserto não
    pode sumir do cadastro porque não estava na hora.

    - lido e esperado: CONFERIDO; `conferido_em` = hoje; "A confirmar" → "Em uso" (`confirmar`).
    - lido e de fora: TRANSFERIDO para o setor da conferência (`transferir`); o local sai
      quando era de outro setor (a prateleira do bar não é a da cozinha). Na conferência
      da loja inteira não existe "de fora".
    - não lido: BAIXADO (se está em `baixar`, com o motivo) ou NAO_ENCONTRADO.
    """
    c = _aberta(cur, id_conferencia, id_unidade)
    hoje = relogio.hoje_da_casa()
    cur.execute(
        """SELECT i.id, i.id_bem, i.esperado, i.lido_em, b.situacao, b.id_local, b.codigo,
                  l.id_setor AS setor_do_local
             FROM bem_conferencia_itens i
             JOIN bens b ON b.id = i.id_bem
             LEFT JOIN locais_estoque l ON l.id = b.id_local
            WHERE i.id_conferencia = %s FOR UPDATE OF i, b""", (id_conferencia,))
    itens = [dict(r) for r in cur.fetchall()]
    nao_lidos = {i["id"] for i in itens if not i["lido_em"]}
    estranhos = set(baixar) - nao_lidos
    if estranhos:
        raise HTTPException(status_code=400,
                            detail="Só se dá baixa no que NÃO foi lido nesta conferência.")
    motivo = (motivo_baixa or "").strip() or (
        f"Não encontrado na conferência nº {id_conferencia} ({hoje:%d/%m/%Y})")
    conta = {"CONFERIDO": 0, "TRANSFERIDO": 0, "NAO_ENCONTRADO": 0, "BAIXADO": 0}
    for i in itens:
        if i["lido_em"] and (i["esperado"] or c["id_setor"] is None or not transferir):
            resultado = "CONFERIDO"
        elif i["lido_em"]:
            resultado = "TRANSFERIDO"
        elif i["id"] in baixar:
            resultado = "BAIXADO"
        else:
            resultado = "NAO_ENCONTRADO"
        conta[resultado] += 1
        cur.execute("UPDATE bem_conferencia_itens SET resultado = %s WHERE id = %s",
                    (resultado, i["id"]))
        if resultado in ("CONFERIDO", "TRANSFERIDO"):
            nova = "EM_USO" if confirmar and i["situacao"] == "A_CONFIRMAR" else i["situacao"]
            if resultado == "TRANSFERIDO":
                # ⚠️ O local de outro setor sai junto: deixá-lo diria "Cozinha · Bar".
                fica_local = i["setor_do_local"] in (None, c["id_setor"])
                cur.execute(
                    """UPDATE bens SET id_setor = %s, id_local = %s, situacao = %s,
                                       conferido_em = %s, atualizado_em = now()
                        WHERE id = %s""",
                    (c["id_setor"], i["id_local"] if fica_local else None, nova, hoje,
                     i["id_bem"]))
            else:
                cur.execute(
                    """UPDATE bens SET situacao = %s, conferido_em = %s, atualizado_em = now()
                        WHERE id = %s""", (nova, hoje, i["id_bem"]))
        elif resultado == "BAIXADO":
            cur.execute(
                """UPDATE bens SET situacao = 'BAIXADO', motivo_baixa = %s, atualizado_em = now()
                    WHERE id = %s""", (motivo[:200], i["id_bem"]))
    cur.execute(
        """UPDATE bem_conferencias SET status = 'FECHADA', fechada_por = %s, fechada_em = now()
            WHERE id = %s""", (id_usuario, id_conferencia))
    partes = [f"{conta['CONFERIDO']} conferido(s)"]
    if conta["TRANSFERIDO"]:
        partes.append(f"{conta['TRANSFERIDO']} transferido(s) para {c['escopo']}")
    if conta["BAIXADO"]:
        partes.append(f"{conta['BAIXADO']} baixado(s)")
    if conta["NAO_ENCONTRADO"]:
        partes.append(f"{conta['NAO_ENCONTRADO']} não encontrado(s), mantido(s)")
    return obter(cur, id_conferencia, id_unidade) | {
        "resultado": conta, "message": "Conferência fechada: " + ", ".join(partes) + "."}


def cancelar(cur, id_conferencia: int, id_unidade: int, id_usuario: int) -> dict:
    """Desiste sem aplicar nada: nenhum bem muda. A lista fica, como registro."""
    _aberta(cur, id_conferencia, id_unidade)
    cur.execute(
        """UPDATE bem_conferencias SET status = 'CANCELADA', fechada_por = %s, fechada_em = now()
            WHERE id = %s""", (id_usuario, id_conferencia))
    return obter(cur, id_conferencia, id_unidade) | {"message": "Conferência cancelada."}
