"""Patrimônio: os bens da casa, um registro por item físico, e a manutenção deles.

🔑 **Pedido do dono (27/10/2026)**, com a planilha `Inventario_Equipamentos_Botane.xlsx`:
um processo para inventariar o patrimônio. Etapas 1 e 2 da proposta — cadastro com
plaqueta e importação da planilha; manutenção com plano, histórico e alertas.

🔑 **Não é estoque.** Nada aqui escreve no razão: o produto do tipo PATRIMONIO continua
contando quantidade onde for usado; o bem é o ITEM, com série, garantia e estado.
⚠️ **A próxima preventiva e o status dela são CALCULADOS na consulta** (`_SELECT`), nunca
gravados — gravados, mentiriam no dia em que alguém corrigisse o intervalo.
"""

from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException

import relogio
from config import WEB_URL

SITUACOES = {"A_CONFIRMAR": "A confirmar", "EM_USO": "Em uso",
             "EM_MANUTENCAO": "Em manutenção", "PARADO": "Parado",
             "DESATIVADO": "Desativado", "BAIXADO": "Baixado"}
CRITICIDADES = {"ALTA": "Alta", "MEDIA": "Média", "BAIXA": "Baixa"}
TENSOES = {"110V": "110 V", "220V": "220 V", "380V": "380 V", "GAS": "Gás",
           "NA": "Não se aplica"}
# O status da preventiva, na ordem de urgência.
PREVENTIVA = {"VENCIDA": "Vencida", "VENCE_30": "Vence em 30 dias",
              "SEM_REGISTRO": "Sem a data da última", "EM_DIA": "Em dia",
              "SEM_PLANO": "Sem plano", "FORA": "Fora de uso"}
TIPOS_MANUTENCAO = {"PREVENTIVA": "Preventiva", "CORRETIVA": "Corretiva"}
# ⚠️ Fora dos alertas e do status: o bem que não está na casa (baixado, desativado) e
# a sugestão que ninguém confirmou não cobram preventiva de ninguém.
FORA_DE_USO = ("A_CONFIRMAR", "DESATIVADO", "BAIXADO")
# Parado de verdade: o que o alerta crítico procura nos de criticidade alta.
PARADOS = ("EM_MANUTENCAO", "PARADO")
# Quantos dias antes a preventiva passa a "vence em breve" — o mesmo da planilha.
JANELA_DIAS = 30

_SELECT = f"""
    SELECT b.*, s.nome AS setor, l.nome AS local, p.nome AS produto, p.codigo AS produto_codigo,
           pv.proxima AS proxima_preventiva,
           CASE WHEN b.situacao IN {FORA_DE_USO} THEN 'FORA'
                WHEN b.preventiva_meses IS NULL THEN 'SEM_PLANO'
                WHEN b.ultima_preventiva IS NULL THEN 'SEM_REGISTRO'
                WHEN pv.proxima < current_date THEN 'VENCIDA'
                WHEN pv.proxima <= current_date + {JANELA_DIAS} THEN 'VENCE_30'
                ELSE 'EM_DIA' END AS status_preventiva,
           (b.garantia_ate IS NOT NULL AND b.garantia_ate >= current_date) AS em_garantia
      FROM bens b
      LEFT JOIN setores s ON s.id = b.id_setor
      LEFT JOIN locais_estoque l ON l.id = b.id_local
      LEFT JOIN produtos p ON p.id = b.id_produto
      CROSS JOIN LATERAL (
          SELECT CASE WHEN b.preventiva_meses IS NOT NULL AND b.ultima_preventiva IS NOT NULL
                      THEN (b.ultima_preventiva
                            + make_interval(months => b.preventiva_meses::int))::date
                 END AS proxima) pv"""


def _rotulos(d: dict) -> dict:
    """Os textos de exibição ao lado dos códigos — a tela e o relatório usam os mesmos."""
    d["situacao_txt"] = SITUACOES.get(d.get("situacao"), d.get("situacao"))
    d["criticidade_txt"] = CRITICIDADES.get(d.get("criticidade")) if d.get("criticidade") else None
    d["tensao_txt"] = TENSOES.get(d.get("tensao")) if d.get("tensao") else None
    d["preventiva_txt"] = PREVENTIVA.get(d.get("status_preventiva"), "")
    return d


# ---------------------------------------------------------------- consulta

def _filtro(f: dict) -> tuple[str, dict]:
    """O WHERE da lista — o mesmo da tela, do relatório e do conector."""
    busca = (f.get("busca") or "").strip() or None
    situacoes = [s for s in (f.get("situacao") or []) if s in SITUACOES] or None
    preventivas = [s for s in (f.get("preventiva") or []) if s in PREVENTIVA] or None
    criticidades = [c for c in (f.get("criticidade") or []) if c in CRITICIDADES] or None
    sql = """
     WHERE b.id_unidade = %(unidade)s
       AND (%(situacoes)s::varchar[] IS NULL AND b.situacao <> 'BAIXADO'
            OR b.situacao = ANY(%(situacoes)s))
       AND (%(setores)s::int[] IS NULL OR b.id_setor = ANY(%(setores)s))
       AND (%(id_local)s::int IS NULL OR b.id_local = %(id_local)s)
       AND (%(id_produto)s::int IS NULL OR b.id_produto = %(id_produto)s)
       AND (%(criticidades)s::varchar[] IS NULL OR b.criticidade = ANY(%(criticidades)s))
       AND (%(busca)s::varchar IS NULL
            OR b.descricao ILIKE '%%' || %(busca)s || '%%'
            OR b.codigo ILIKE '%%' || %(busca)s || '%%'
            OR b.apelido ILIKE '%%' || %(busca)s || '%%'
            OR b.marca ILIKE '%%' || %(busca)s || '%%'
            OR b.modelo ILIKE '%%' || %(busca)s || '%%'
            OR b.numero_serie ILIKE '%%' || %(busca)s || '%%')"""
    params = {"situacoes": situacoes, "setores": f.get("setores") or None,
              "id_local": f.get("id_local"), "id_produto": f.get("id_produto"),
              "criticidades": criticidades, "busca": busca,
              "preventivas": preventivas}
    return sql, params


def listar(cur, id_unidade: int, f: dict, *, limite: int | None = None, offset: int = 0,
           resposta=None) -> list[dict]:
    """⚠️ Sem filtro de situação, os BAIXADOS ficam de fora: saíram da casa, e a lista é
    do que existe. Pedir `situacao=BAIXADO` os traz."""
    from paginacao import pagina
    where, params = _filtro(f)
    # O status da preventiva é calculado no SELECT: filtra-se por fora, na mesma consulta.
    sql = f"""SELECT * FROM ({_SELECT} {where}) x
               WHERE (%(preventivas)s::varchar[] IS NULL
                      OR x.status_preventiva = ANY(%(preventivas)s))
               ORDER BY lower(coalesce(x.setor, 'zzz')), x.codigo"""
    params |= {"unidade": id_unidade}
    if limite is None:
        cur.execute(sql, params)
        linhas = [dict(r) for r in cur.fetchall()]
    else:
        linhas = pagina(cur, sql, params, limite=limite, offset=offset, resposta=resposta)
    return [_rotulos(l) for l in linhas]


def resumo(cur, id_unidade: int) -> dict:
    """A aba "Resumo" da planilha da casa: por setor, quantos, quantos críticos, parados,
    com preventiva vencida, vencendo em 30 dias e sem plano. Os baixados não contam."""
    cur.execute(
        f"""SELECT coalesce(x.setor, 'Sem setor') AS setor, x.id_setor,
                   count(*) AS bens,
                   count(*) FILTER (WHERE x.criticidade = 'ALTA') AS criticidade_alta,
                   count(*) FILTER (WHERE x.situacao IN {PARADOS}) AS parados,
                   count(*) FILTER (WHERE x.status_preventiva = 'VENCIDA') AS vencidas,
                   count(*) FILTER (WHERE x.status_preventiva = 'VENCE_30') AS vencendo,
                   count(*) FILTER (WHERE x.status_preventiva IN ('SEM_PLANO', 'SEM_REGISTRO'))
                       AS sem_plano,
                   count(*) FILTER (WHERE x.situacao = 'A_CONFIRMAR') AS a_confirmar,
                   coalesce(sum(x.valor_compra), 0) AS valor_compra
              FROM ({_SELECT} WHERE b.id_unidade = %s AND b.situacao <> 'BAIXADO') x
             GROUP BY x.setor, x.id_setor
             ORDER BY lower(coalesce(x.setor, 'zzz'))""", (id_unidade,))
    setores = [dict(r) for r in cur.fetchall()]
    chaves = ("bens", "criticidade_alta", "parados", "vencidas", "vencendo", "sem_plano",
              "a_confirmar")
    total = {k: sum(s[k] for s in setores) for k in chaves}
    total["valor_compra"] = sum(float(s["valor_compra"]) for s in setores)
    for s in setores:
        s["valor_compra"] = float(s["valor_compra"])
    return {"setores": setores, "total": total}


def _do_bem(cur, id_bem: int, id_unidade: int) -> dict:
    cur.execute(_SELECT + " WHERE b.id = %s", (id_bem,))
    r = cur.fetchone()
    if not r or r["id_unidade"] != id_unidade:
        raise HTTPException(status_code=404, detail="Bem não encontrado nesta loja")
    return _rotulos(dict(r))


def obter(cur, id_bem: int, id_unidade: int, *, ve_valor_estoque: bool = False) -> dict:
    """O bem, a manutenção dele (mais nova primeiro) e o estoque guardado no local."""
    bem = _do_bem(cur, id_bem, id_unidade)
    cur.execute(
        """SELECT m.*, u.nome AS registrado_por
             FROM bem_manutencoes m LEFT JOIN usuarios u ON u.id = m.id_usuario
            WHERE m.id_bem = %s ORDER BY m.data DESC, m.id DESC""", (id_bem,))
    bem["manutencoes"] = [dict(r) | {"tipo_txt": TIPOS_MANUTENCAO[r["tipo"]]}
                          for r in cur.fetchall()]
    bem["custo_manutencao"] = float(sum((m["custo"] or 0) for m in bem["manutencoes"]))
    # 🔑 **O equipamento que É um local de estoque** (a câmara fria): parado, ele avisa
    # quanto está guardado dentro. O valor só para quem vê estoque.
    bem["estoque_no_local"] = None
    if bem["id_local"]:
        cur.execute(
            """SELECT count(*) AS produtos,
                      coalesce(sum(s.quantidade * s.custo_medio), 0) AS valor
                 FROM estoque_saldos s
                WHERE s.id_local = %s AND s.quantidade > 0""", (bem["id_local"],))
        e = cur.fetchone()
        bem["estoque_no_local"] = {
            "produtos": e["produtos"],
            "valor": round(float(e["valor"]), 2) if ve_valor_estoque else None}
    return bem


def por_codigo(cur, codigo: str) -> dict:
    """O que a plaqueta abre: pelo código (PAT-0001), sem diferença de maiúscula."""
    cur.execute("SELECT id, id_unidade FROM bens WHERE upper(codigo) = upper(%s)",
                (codigo.strip(),))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Nenhum bem com este código")
    return dict(r)


# ---------------------------------------------------------------- cadastro

def _validar(cur, id_unidade: int, dados: dict, id_bem: int | None = None) -> None:
    """Local da loja, setor da loja (ou de todas), produto que existe, apelido sem dono."""
    if dados.get("id_local"):
        cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (dados["id_local"],))
        r = cur.fetchone()
        if not r or r["id_unidade"] != id_unidade:
            raise HTTPException(status_code=400, detail="Local que não é desta loja")
    if dados.get("id_setor"):
        cur.execute("SELECT id_unidade FROM setores WHERE id = %s", (dados["id_setor"],))
        r = cur.fetchone()
        if not r or r["id_unidade"] not in (None, id_unidade):
            raise HTTPException(status_code=400, detail="Setor que não é desta loja")
    if dados.get("id_produto"):
        # 🔑 **O bem nasce de um produto do tipo PATRIMÔNIO** (27/10/2026, pedido do dono:
        # *"o equipamento poderia ser um produto patrimônio … ai vinculamos todo o
        # sistema"*). Outro tipo seria vínculo com insumo, que não conta como bem.
        cur.execute("SELECT nome, tipo FROM produtos WHERE id = %s", (dados["id_produto"],))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=400, detail="Produto que não existe")
        if r["tipo"] != "PATRIMONIO":
            raise HTTPException(status_code=400,
                                detail=f"“{r['nome']}” não é do tipo Patrimônio — "
                                       "reclassifique o produto ou deixe o bem sem produto")
    apelido = (dados.get("apelido") or "").strip()
    if apelido:
        cur.execute(
            """SELECT codigo FROM bens
                WHERE id_unidade = %s AND lower(apelido) = lower(%s)
                  AND (%s::int IS NULL OR id <> %s)""",
            (id_unidade, apelido, id_bem, id_bem))
        r = cur.fetchone()
        if r:
            raise HTTPException(status_code=409,
                                detail=f"O apelido “{apelido}” já é do bem {r['codigo']}")


def _limpo(dados: dict) -> dict:
    """Texto em branco vira nulo — "" no banco é um campo que parece preenchido."""
    return {k: (v.strip() or None) if isinstance(v, str) else v for k, v in dados.items()}


def criar(cur, id_unidade: int, id_usuario: int, dados: dict) -> dict:
    dados = _limpo(dados)
    _validar(cur, id_unidade, dados)
    from models.patrimonio import CAMPOS
    campos = [c for c in CAMPOS if c in dados]
    cur.execute(
        f"""INSERT INTO bens (codigo, id_unidade, criado_por, {', '.join(campos)})
            VALUES ('PAT-' || lpad(nextval('bens_codigo_seq')::text, 4, '0'), %s, %s,
                    {', '.join(['%s'] * len(campos))})
            RETURNING id""",
        (id_unidade, id_usuario, *[dados[c] for c in campos]))
    return _do_bem(cur, cur.fetchone()["id"], id_unidade)


def atualizar(cur, id_bem: int, id_unidade: int, dados: dict) -> tuple[dict, dict]:
    """(antes, depois). Só os campos que vieram mudam."""
    antes = _do_bem(cur, id_bem, id_unidade)
    dados = _limpo(dados)
    _validar(cur, id_unidade, dados, id_bem)
    if "descricao" in dados and not dados["descricao"]:
        raise HTTPException(status_code=400, detail="O bem precisa de um nome")
    situacao = dados.get("situacao", antes["situacao"])
    motivo = dados.get("motivo_baixa", antes["motivo_baixa"])
    if situacao == "BAIXADO" and not motivo:
        raise HTTPException(status_code=400, detail="Para dar baixa, diga o motivo "
                                                    "(venda, descarte, perda, doação…).")
    if "situacao" in dados and dados["situacao"] is None:
        del dados["situacao"]
    if dados:
        cur.execute(
            f"""UPDATE bens SET {', '.join(f'{c} = %s' for c in dados)}, atualizado_em = now()
                 WHERE id = %s""", (*dados.values(), id_bem))
    return antes, _do_bem(cur, id_bem, id_unidade)


def excluir(cur, id_bem: int, id_unidade: int) -> dict:
    """⚠️ Só o bem SEM histórico: cadastro errado se apaga; bem que existiu se BAIXA —
    apagar levaria junto o que se gastou nele."""
    bem = _do_bem(cur, id_bem, id_unidade)
    cur.execute("SELECT count(*) AS n FROM bem_manutencoes WHERE id_bem = %s", (id_bem,))
    if cur.fetchone()["n"]:
        raise HTTPException(status_code=409,
                            detail="Este bem tem manutenção registrada — dê baixa em vez de "
                                   "apagar, para o histórico continuar existindo.")
    # ⚠️ A conferência FECHADA também é história (140): apagar o bem tiraria a linha dele
    # da folha assinada. A aberta não conta — a leitura ainda pode ser desfeita.
    cur.execute(
        """SELECT count(*) AS n FROM bem_conferencia_itens i
             JOIN bem_conferencias c ON c.id = i.id_conferencia
            WHERE i.id_bem = %s AND c.status = 'FECHADA'""", (id_bem,))
    if cur.fetchone()["n"]:
        raise HTTPException(status_code=409,
                            detail="Este bem já passou por uma conferência — dê baixa em vez "
                                   "de apagar, para o histórico continuar existindo.")
    cur.execute("DELETE FROM bens WHERE id = %s", (id_bem,))
    return bem


# ---------------------------------------------------------------- manutenção

def registrar_manutencao(cur, id_bem: int, id_unidade: int, id_usuario: int,
                         dados: dict) -> dict:
    """Grava a visita e, sendo preventiva mais nova que a última, anda o plano.

    ⚠️ **Data no futuro é recusada**: o registro é do que FOI feito. A preventiva marcada
    para a semana que vem é o que a "próxima" já diz.
    """
    bem = _do_bem(cur, id_bem, id_unidade)
    dados = _limpo(dados)
    if dados["data"] > relogio.hoje_da_casa():
        raise HTTPException(status_code=400, detail="A data é de quando foi feito — "
                                                    "não pode ser no futuro.")
    depois = dados.pop("situacao_depois", None)
    if depois == "BAIXADO":
        raise HTTPException(status_code=400, detail="Baixa é no cadastro do bem, com o motivo.")
    cur.execute(
        """INSERT INTO bem_manutencoes (id_bem, tipo, data, executado_por, custo, descricao,
                                        id_usuario)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_bem, dados["tipo"], dados["data"], dados.get("executado_por"), dados.get("custo"),
         dados.get("descricao"), id_usuario))
    id_manutencao = cur.fetchone()["id"]
    if dados["tipo"] == "PREVENTIVA" and (bem["ultima_preventiva"] is None
                                          or dados["data"] > bem["ultima_preventiva"]):
        cur.execute("UPDATE bens SET ultima_preventiva = %s, atualizado_em = now() WHERE id = %s",
                    (dados["data"], id_bem))
    if depois and depois != bem["situacao"]:
        cur.execute("UPDATE bens SET situacao = %s, atualizado_em = now() WHERE id = %s",
                    (depois, id_bem))
    return {"id": id_manutencao, "bem": _do_bem(cur, id_bem, id_unidade)}


def excluir_manutencao(cur, id_manutencao: int, id_unidade: int) -> dict:
    """Apaga um registro errado. ⚠️ Se era a preventiva que marcava a "última", a última
    volta para a preventiva anterior — senão o plano seguiria contando de uma visita que
    não aconteceu."""
    cur.execute(
        """SELECT m.*, b.id_unidade, b.ultima_preventiva
             FROM bem_manutencoes m JOIN bens b ON b.id = m.id_bem WHERE m.id = %s""",
        (id_manutencao,))
    m = cur.fetchone()
    if not m or m["id_unidade"] != id_unidade:
        raise HTTPException(status_code=404, detail="Registro não encontrado nesta loja")
    cur.execute("DELETE FROM bem_manutencoes WHERE id = %s", (id_manutencao,))
    if m["tipo"] == "PREVENTIVA" and m["ultima_preventiva"] == m["data"]:
        cur.execute(
            """UPDATE bens SET atualizado_em = now(),
                      ultima_preventiva = (SELECT max(data) FROM bem_manutencoes
                                            WHERE id_bem = %s AND tipo = 'PREVENTIVA')
                WHERE id = %s""", (m["id_bem"], m["id_bem"]))
    return dict(m)


# ---------------------------------------------------------------- alertas

def alertas(cur, id_unidade: int) -> dict:
    """Os números que o Início cobra: crítico parado, preventiva vencida e vencendo — e o
    produto Patrimônio que entrou e ainda não virou bem."""
    cur.execute(
        f"""SELECT count(*) FILTER (WHERE x.criticidade = 'ALTA'
                                      AND x.situacao IN {PARADOS}) AS criticos_parados,
                   count(*) FILTER (WHERE x.status_preventiva = 'VENCIDA') AS vencidas,
                   count(*) FILTER (WHERE x.status_preventiva = 'VENCE_30') AS vencendo
              FROM ({_SELECT} WHERE b.id_unidade = %s) x""", (id_unidade,))
    r = dict(cur.fetchone())
    pend = a_cadastrar(cur, id_unidade)
    r["a_cadastrar"] = len(pend)
    r["a_cadastrar_itens"] = sum(p["faltam"] for p in pend)
    return r


# ---------------------------------------------------------------- o produto Patrimônio

# 🔑 **O que entrou como Patrimônio e ainda não virou bem** (27/10/2026, pedido do dono:
# *"caso entre um produto novo como patrimônio, o usuário deverá cadastrar ele como um novo
# bem"*). A régua é o SALDO: 3 batedeiras no estoque e 1 bem ligado ao produto = faltam 2.
# ⚠️ Os baixados não contam como cadastrados (saíram da casa); o A confirmar e o
# desativado contam (existem). Saldo quebrado (0,5 UN) arredonda para baixo — patrimônio
# é coisa inteira, e cobrar meia batedeira seria alarme falso.
_A_CADASTRAR = """
    WITH s AS (SELECT es.id_produto, sum(es.quantidade) AS saldo,
                      string_agg(l.nome || ' (' || rtrim(to_char(es.quantidade, 'FM999990.####'), '.')
                                 || ')', ', ' ORDER BY es.quantidade DESC) AS onde,
                      (array_agg(es.id_local ORDER BY es.quantidade DESC))[1] AS id_local
                 FROM estoque_saldos es JOIN locais_estoque l ON l.id = es.id_local
                WHERE es.id_unidade = %(u)s AND es.quantidade > 0
                GROUP BY es.id_produto),
         b AS (SELECT id_produto, count(*) AS bens FROM bens
                WHERE id_unidade = %(u)s AND id_produto IS NOT NULL AND situacao <> 'BAIXADO'
                GROUP BY id_produto)
    SELECT p.id AS id_produto, p.codigo, p.nome AS produto, p.um_estoque, p.id_setor,
           s.saldo, s.onde, s.id_local, coalesce(b.bens, 0) AS bens,
           (floor(s.saldo)::int - coalesce(b.bens, 0)) AS faltam
      FROM produtos p
      JOIN s ON s.id_produto = p.id
      LEFT JOIN b ON b.id_produto = p.id
     WHERE p.tipo = 'PATRIMONIO' AND floor(s.saldo) > coalesce(b.bens, 0)
       AND (%(p)s::int IS NULL OR p.id = %(p)s)
     ORDER BY lower(p.nome)"""


def a_cadastrar(cur, id_unidade: int, id_produto: int | None = None) -> list[dict]:
    cur.execute(_A_CADASTRAR, {"u": id_unidade, "p": id_produto})
    return [dict(r) | {"saldo": float(r["saldo"])} for r in cur.fetchall()]


def do_produto(cur, id_unidade: int, id_produto: int, *, ve_custo: bool = False) -> dict:
    """O produto Patrimônio e os bens dele — o quadro do cadastro do produto e o
    preenchimento do "Novo bem" (`/patrimonio/novo?produto=`).

    🔑 **A sugestão vem da ÚLTIMA ENTRADA** do produto: data, nota, fornecedor e — para
    quem vê custo — o custo unitário como valor de compra. O local é o que tem mais saldo.
    """
    cur.execute("""SELECT p.id, p.codigo, p.nome, p.tipo, p.um_estoque, p.id_setor
                     FROM produtos p WHERE p.id = %s""", (id_produto,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    p = dict(p)
    cur.execute("""SELECT coalesce(sum(quantidade), 0) AS saldo FROM estoque_saldos
                    WHERE id_unidade = %s AND id_produto = %s AND quantidade > 0""",
                (id_unidade, id_produto))
    saldo = float(cur.fetchone()["saldo"])
    bens = listar(cur, id_unidade, {"id_produto": id_produto,
                                    "situacao": list(SITUACOES)})
    ativos = sum(1 for b in bens if b["situacao"] != "BAIXADO")
    pend = a_cadastrar(cur, id_unidade, id_produto)
    cur.execute(
        """SELECT m.data_movimento::date AS data, m.custo_unitario, m.documento,
                  n.numero, coalesce(f.nome, n.nome_emitente) AS fornecedor
             FROM estoque_movimentos m
             LEFT JOIN notas_entrada n ON m.origem_tipo = 'NOTA' AND n.id = m.origem_id
             LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
            WHERE m.id_produto = %s AND m.id_unidade = %s AND m.quantidade > 0
              AND m.tipo IN ('ENTRADA_NF', 'ENTRADA_MANUAL')
            ORDER BY m.data_movimento DESC, m.id DESC LIMIT 1""", (id_produto, id_unidade))
    e = cur.fetchone()
    sugestao = {"descricao": p["nome"], "id_produto": p["id"], "id_setor": p["id_setor"],
                "id_local": pend[0]["id_local"] if pend else None}
    if e:
        sugestao |= {"data_compra": e["data"], "fornecedor": e["fornecedor"],
                     "nota_fiscal": e["numero"] or e["documento"]}
        if ve_custo and e["custo_unitario"]:
            sugestao["valor_compra"] = round(float(e["custo_unitario"]), 2)
    return {"produto": p, "saldo": saldo, "bens": bens, "ativos": ativos,
            "faltam": pend[0]["faltam"] if pend else 0,
            "onde": pend[0]["onde"] if pend else None, "sugestao": sugestao}


# ---------------------------------------------------------------- plaqueta

def link(codigo: str) -> str:
    return f"{WEB_URL.rstrip('/')}/patrimonio/b/{codigo}"


def _desenhar(c, x: float, y: float, w: float, h: float, b: dict, casa: str) -> None:
    """Uma plaqueta no retângulo (x, y, w, h): QR à esquerda, código grande à direita."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.units import mm

    from services.fidelidade_qr import _quebrar

    k = min(h / (40 * mm), max(w / (60 * mm), 1))
    m = 2 * mm
    lado = min(h - 2 * m, w * 0.42)
    qr = QrCodeWidget(link(b["codigo"]), barLevel="M")
    x0, y0, x1, y1 = qr.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(qr)
    renderPDF.draw(d, c, x + m, y + (h - lado) / 2)
    tx = x + m + lado + 1.5 * mm
    largura = w - (tx - x) - m
    topo = y + h - m

    def linha(texto, fonte, tam, max_linhas=2):
        nonlocal topo
        for pedaco in _quebrar(c, texto, fonte, tam, largura)[:max_linhas]:
            topo -= tam * 1.08
            c.setFont(fonte, tam)
            c.drawString(tx, topo, pedaco)

    linha("PATRIMÔNIO" + (f" · {casa.upper()}" if casa else ""), "Helvetica", 5.5 * k, 1)
    topo -= 0.5 * k
    linha(b["codigo"], "Helvetica-Bold", 13 * k, 1)
    topo -= 0.8 * k
    linha(b["descricao"].upper(), "Helvetica-Bold", 7 * k)
    onde = " · ".join(v for v in (b.get("setor"), b.get("local")) if v)
    if onde:
        linha(onde, "Helvetica", 5.5 * k)
    if b.get("numero_serie"):
        linha(f"Série: {b['numero_serie']}", "Helvetica", 5.5 * k, 1)


def plaquetas_pdf(cur, ids: list[int], id_unidade: int) -> bytes:
    """Uma página por plaqueta no rolo da loja, ou a folha A4 de 3 × 7 — o mesmo modelo e a
    mesma impressora das etiquetas de validade (Etiquetas ▸ Configuração)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from services import etiquetas

    bens = [_do_bem(cur, i, id_unidade) for i in ids]
    cfg = etiquetas.config(cur, id_unidade)
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    casa = (e.get("nome_fantasia") or e.get("razao_social") or "").strip()
    buf = BytesIO()
    pagina = etiquetas.pagina_mm(cfg)
    if pagina is None:
        w, h = 60 * mm, 40 * mm
        c = canvas.Canvas(buf, pagesize=A4)
        colunas, linhas = 3, 7
        mx, my = (A4[0] - colunas * w) / 2, (A4[1] - linhas * h) / 2
        for n, b in enumerate(bens):
            pos = n % (colunas * linhas)
            if n and pos == 0:
                c.showPage()
            col, lin = pos % colunas, pos // colunas
            ex, ey = mx + col * w, A4[1] - my - (lin + 1) * h
            c.setDash(2, 2)
            c.setLineWidth(0.3)
            c.rect(ex, ey, w, h)
            c.setDash()
            _desenhar(c, ex, ey, w, h, b, casa)
    else:
        w, h = pagina[0] * mm, pagina[1] * mm
        c = canvas.Canvas(buf, pagesize=(w, h))
        for n, b in enumerate(bens):
            if n:
                c.showPage()
            _desenhar(c, 0, 0, w, h, b, casa)
    c.setTitle("Plaquetas de patrimônio")
    c.save()
    return buf.getvalue()


def direta(cur, id_unidade: int) -> bool:
    from services import etiquetas
    return bool(etiquetas.config(cur, id_unidade)["direta"])
