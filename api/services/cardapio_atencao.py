"""O painel Atenção × Vendas do Cardápio Vivo (fase 2, migração 115).

🔑 **Pedido do dono (14/10/2026)**: medir a atenção dada a cada prato no feed e cruzá-la
com o que o PDV vendeu e com a margem da ficha — e sugerir o que fazer com cada um.
Estudo em `docs/cardapio-vivo-estudo.md` (seções 0b e 6).

🔑 **As definições moram AQUI e saem na resposta** (`DEFINICOES`), para a tela dizer
exatamente o que cada número é — e não inventar uma segunda versão delas:
* **Sessão engajada**: ≥ 3 itens diferentes vistos OU 1 interação (favorito,
  personalização, adição). Os indicadores por item usam SÓ estas.
* **Atenção estimada**: o tempo em que o item ficou ≥ 50% visível, com teto de 60 s por
  visualização. Não é rastreamento ocular nem intenção de compra.
* **Deslize para trás**: o cliente voltou a um item já visto — sinal de interesse.

⚠️ **Lê o evento BRUTO**, que é o único que aceita todos os filtros (salão, dia da semana,
faixa de horário). Período mais antigo que a retenção da loja não tem bruto — a resposta
diz desde quando há dado.
⚠️ **A venda é a do PDV** (`venda_itens`), pelo produto: o salão não filtra a venda (o
cupom não diz em que salão a mesa fica), e a resposta avisa.
"""

from datetime import date, time
from decimal import Decimal
from statistics import median

from fastapi import HTTPException

from services import cardapio_vivo as cv
from services import cmv as motor_cmv
from services import precificacao
from services.custos import dec

DEFINICOES = {
    "sessao_engajada": "Sessão com pelo menos 3 pratos diferentes vistos, ou 1 interação "
                       "(favorito, personalização ou adição). Os números por prato usam só estas; "
                       "o total de sessões abertas aparece à parte.",
    "atencao_estimada": "Tempo em que o prato ficou visível (pelo menos metade da tela), com "
                        "limite de 60 s por visualização para descartar telas esquecidas abertas. "
                        "Não é rastreamento do olhar nem intenção de compra.",
    "deslize_tras": "O cliente voltou a um prato que já tinha visto — sinal de interesse.",
    "quase_pediu": "Adicionou e depois tirou; ou adicionou ao carrinho e não enviou; ou olhou "
                   "por mais tempo que 90% das visualizações daquele prato e não adicionou.",
    "desistencia": "Remoções ÷ adições do prato.",
    "quadrante": "Atenção e vendas comparadas com a MEDIANA dos pratos do cardápio no período.",
}

OBJETIVOS = {"AUMENTAR_VENDA": "Aumentar venda", "GIRAR_ESTOQUE": "Girar estoque",
             "LANCAMENTO": "Lançamento", "MANTER": "Manter"}
SUGESTOES = {
    "REVISAR": "Revisar preço, descrição ou foto",
    "DESTACAR": "Colocar em destaque ou subir na ordem",
    "SAIR": "Candidato a sair do cardápio",
    "PROTEGER": "Manter e proteger o estoque",
}


def _filtros_eventos(id_unidade, de, ate, id_salao, dias, hora_de, hora_ate,
                     id_catalogo: int | None = None) -> tuple[str, list]:
    onde = ["e.id_unidade = %s", "e.quando >= %s::date", "e.quando < %s::date + 1"]
    valores: list = [id_unidade, de, ate]
    if id_catalogo:
        # 🔑 Só o que veio DESTE Cardápio Vivo (122). O evento sem cardápio é anterior à 122 e
        # não se sabe de onde veio: conta, como contava.
        onde.append("coalesce(e.id_catalogo, %s) = %s")
        valores += [id_catalogo, id_catalogo]
    if id_salao:
        onde.append("e.id_mesa IN (SELECT id FROM mesas WHERE id_salao = %s)")
        valores.append(id_salao)
    if dias:
        onde.append("extract(isodow FROM e.quando)::int = ANY(%s)")
        valores.append(dias)
    if hora_de is not None and hora_ate is not None:
        if hora_de < hora_ate:
            onde.append("e.quando::time >= %s AND e.quando::time < %s")
        else:  # a faixa vira a meia-noite
            onde.append("(e.quando::time >= %s OR e.quando::time < %s)")
        valores += [hora_de, hora_ate]
    return " AND ".join(onde), valores


def _nivel_de_margem(lucro_pct: Decimal | None, alvo: Decimal) -> str | None:
    """🔑 Pela margem-alvo da Precificação (decisão do dono, 15/10/2026): na meta ou acima =
    ALTA; até 10 pontos abaixo = MEDIA; abaixo disso = BAIXA. Sem meta ou sem custo: nulo."""
    if lucro_pct is None or not alvo:
        return None
    if lucro_pct >= alvo:
        return "ALTA"
    if lucro_pct >= alvo - 10:
        return "MEDIA"
    return "BAIXA"


def margens(cur, id_unidade: int, produtos: list[dict]) -> dict[int, dict]:
    """A margem de cada produto HOJE: custo da ficha × preço da loja × regras da Precificação."""
    k = precificacao.config(cur, id_unidade)
    saida = {}
    for p in produtos:
        custo, _origem = motor_cmv.custo_teorico_do_produto(cur, p["id_produto"], id_unidade=id_unidade)
        regra = precificacao.resolver(k.get("_linhas", []), p["id_categoria"], p["id_setor"])
        conta = precificacao.calcular(custo, p["preco"], regra, k.get("arredondamento") or "CENTAVO")
        lucro = conta["leitura"]["lucro_pct"] if conta["leitura"] else None
        saida[p["id_produto"]] = {
            "margem_pct": float(lucro) if lucro is not None else None,
            "margem_alvo_pct": float(regra["margem"]) if regra["margem"] else None,
            "margem_calculada": _nivel_de_margem(lucro, regra["margem"]),
        }
    return saida


def _sugestao(atencao_alta: bool, venda_alta: bool, margem: str | None,
              objetivo: str | None) -> tuple[str | None, int]:
    """A sugestão do item e a prioridade dela na lista (maior primeiro).

    🔑 **O objetivo de negócio reordena** (complemento do dono): item em LANÇAMENTO ou para
    GIRAR ESTOQUE com pouca atenção sobe na lista de destaque; AUMENTAR VENDA puxa para cima
    o que vende pouco; MANTER desce e não vira candidato a sair.
    """
    if atencao_alta and not venda_alta:
        chave, prioridade = "REVISAR", 3
    elif not atencao_alta and margem == "ALTA":
        chave, prioridade = "DESTACAR", 3
    elif not atencao_alta and not venda_alta:
        chave, prioridade = "SAIR", 2
    elif atencao_alta and venda_alta:
        chave, prioridade = "PROTEGER", 1
    else:
        chave, prioridade = None, 0  # pouca atenção e muita venda: vende sem precisar do feed
    if objetivo in ("LANCAMENTO", "GIRAR_ESTOQUE") and not atencao_alta:
        chave = "DESTACAR"
        prioridade += 3 if objetivo == "LANCAMENTO" else 2
    elif objetivo == "AUMENTAR_VENDA" and not venda_alta:
        prioridade += 2
    elif objetivo == "MANTER":
        if chave == "SAIR":
            chave = None
        prioridade -= 1
    return chave, prioridade


def painel(cur, id_unidade: int, de: date, ate: date, id_salao: int | None = None,
           dias: list[int] | None = None, hora_de: time | None = None,
           hora_ate: time | None = None) -> dict:
    if ate < de:
        raise HTTPException(status_code=422, detail="O fim do período é antes do começo.")
    if (ate - de).days > 400:
        raise HTTPException(status_code=422, detail="Período de no máximo 400 dias.")
    cfg = cv.config(cur, id_unidade)
    onde, valores = _filtros_eventos(id_unidade, de, ate, id_salao, dias, hora_de, hora_ate,
                                     cfg["id_catalogo"])
    teto = cv.ATENCAO_MAX_MS

    # ---------------------------------------------------------------- topo e funil
    cur.execute(
        f"""WITH ev AS (SELECT e.* FROM cardapio_eventos e WHERE {onde}),
                 s AS (SELECT id_sessao, {cv.SQL_SESSAO_ENGAJADA} AS engajada,
                              bool_or(tipo = 'viu_item') AS viu, bool_or(tipo = 'adicionou') AS ad,
                              bool_or(tipo = 'enviou_pedido') AS env
                         FROM ev GROUP BY id_sessao)
            SELECT (SELECT count(*) FROM s) AS sessoes,
                   (SELECT count(*) FROM s WHERE engajada) AS engajadas,
                   (SELECT count(*) FROM s WHERE viu) AS viram,
                   (SELECT count(*) FROM s WHERE ad) AS adicionaram,
                   (SELECT count(*) FROM s WHERE env) AS enviaram,
                   (SELECT count(*) FROM ev WHERE tipo = 'abriu_hub') AS hubs,
                   (SELECT count(*) FROM ev WHERE tipo = 'clicou_avaliacao') AS cliques_avaliacao,
                   (SELECT count(*) FROM ev WHERE tipo = 'clicou_wifi') AS cliques_wifi,
                   (SELECT min(quando) FROM cardapio_eventos WHERE id_unidade = %s) AS bruto_desde""",
        [*valores, id_unidade])  # noqa: S608 - filtros montados com marcadores
    topo = dict(cur.fetchone())

    # ---------------------------------------------------------------- por produto
    cur.execute(
        f"""WITH ev AS (SELECT e.* FROM cardapio_eventos e WHERE {onde}),
                 eng AS (SELECT id_sessao FROM ev GROUP BY id_sessao HAVING {cv.SQL_SESSAO_ENGAJADA}),
                 e2 AS (SELECT * FROM ev WHERE id_sessao IN (SELECT id_sessao FROM eng)
                          AND id_produto IS NOT NULL),
                 p90 AS (SELECT id_produto,
                                percentile_cont(0.9) WITHIN GROUP (ORDER BY least(duracao_ms, %s)) AS p90
                           FROM e2 WHERE tipo = 'viu_item' GROUP BY id_produto),
                 envio AS (SELECT id_sessao, bool_or(tipo = 'enviou_pedido') AS env FROM ev GROUP BY id_sessao),
                 si AS (SELECT id_sessao, id_produto, max(modo) AS modo,
                               bool_or(tipo = 'adicionou') AS ad, bool_or(tipo = 'removeu') AS rem,
                               max(least(duracao_ms, %s)) FILTER (WHERE tipo = 'viu_item') AS maxv
                          FROM e2 GROUP BY id_sessao, id_produto),
                 quase AS (SELECT si.id_produto, count(*) AS n FROM si
                             JOIN envio USING (id_sessao) LEFT JOIN p90 USING (id_produto)
                            WHERE (si.ad AND si.rem)
                               OR (si.ad AND si.modo = 'PEDIDO' AND NOT envio.env)
                               OR (NOT si.ad AND si.maxv > p90.p90)
                            GROUP BY si.id_produto)
            SELECT e2.id_produto,
                   count(*) FILTER (WHERE tipo = 'viu_item') AS visualizacoes,
                   coalesce(sum(least(duracao_ms, %s)) FILTER (WHERE tipo = 'viu_item'), 0) AS atencao_ms,
                   count(*) FILTER (WHERE tipo = 'adicionou') AS adicoes,
                   count(*) FILTER (WHERE tipo = 'removeu') AS remocoes,
                   count(*) FILTER (WHERE tipo = 'favoritou') AS favoritos,
                   count(*) FILTER (WHERE tipo = 'deslizou_tras') AS deslizes_tras,
                   count(*) FILTER (WHERE tipo = 'abriu_detalhe') AS detalhes,
                   max(quase.n) AS quase_pediu
              FROM e2 LEFT JOIN quase USING (id_produto)
             GROUP BY e2.id_produto""",
        [*valores, teto, teto, teto])  # noqa: S608
    atencao = {r["id_produto"]: dict(r) for r in cur.fetchall()}

    # Os pratos do cardápio apontado (um por produto: o primeiro na ordem do cardápio).
    produtos: list[dict] = []
    if cfg["id_catalogo"]:
        cur.execute(
            f"""SELECT DISTINCT ON (p.id) p.id AS id_produto, i.id AS id_item,
                       coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome) AS nome,
                       p.id_categoria, p.id_setor, i.objetivo, i.margem_nivel, i.destaque,
                       p.video_url IS NOT NULL AS tem_video, g.nome AS secao,
                       {cv._preco_sql('p')} AS preco
                  FROM catalogo_itens i
                  JOIN catalogo_categorias g ON g.id = i.id_categoria
                  JOIN produtos p ON p.id = i.id_produto
                 WHERE g.id_catalogo = %(c)s AND p.ativo
                 ORDER BY p.id, g.ordem, i.ordem""",
            {"c": cfg["id_catalogo"], "u": id_unidade})  # noqa: S608
        produtos = [dict(r) for r in cur.fetchall()]

    # A venda do PDV no mesmo recorte (sem o salão — o cupom não o diz).
    vf, vv = ["v.id_unidade = %s", "NOT v.cancelada", "NOT v.consumo_interno",
              "v.data BETWEEN %s AND %s", "vi.id_produto = ANY(%s)"], \
        [id_unidade, de, ate, [p["id_produto"] for p in produtos] or [0]]
    if dias:
        vf.append("extract(isodow FROM v.data)::int = ANY(%s)")
        vv.append(dias)
    if hora_de is not None and hora_ate is not None:
        vf.append("v.hora::time >= %s AND v.hora::time < %s" if hora_de < hora_ate
                  else "(v.hora::time >= %s OR v.hora::time < %s)")
        vv += [hora_de, hora_ate]
    cur.execute(
        f"""SELECT vi.id_produto, sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita
              FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
             WHERE {' AND '.join(vf)} GROUP BY vi.id_produto""", vv)  # noqa: S608
    vendas = {r["id_produto"]: r for r in cur.fetchall()}
    m = margens(cur, id_unidade, produtos)

    linhas = []
    for p in produtos:
        a = atencao.get(p["id_produto"], {})
        v = vendas.get(p["id_produto"])
        vis, ad = int(a.get("visualizacoes") or 0), int(a.get("adicoes") or 0)
        mg = m[p["id_produto"]]
        linhas.append({
            "id_item": p["id_item"], "id_produto": p["id_produto"], "nome": p["nome"],
            "secao": p["secao"], "destaque": p["destaque"], "tem_video": p["tem_video"],
            "objetivo": p["objetivo"], "objetivo_rotulo": OBJETIVOS.get(p["objetivo"]),
            "visualizacoes": vis,
            "atencao_ms": int(a.get("atencao_ms") or 0),
            "atencao_media_ms": round(int(a.get("atencao_ms") or 0) / vis) if vis else None,
            "taxa_adicao": round(ad / vis, 4) if vis else None,
            "desistencia": round(int(a.get("remocoes") or 0) / ad, 4) if ad else None,
            "quase_pediu": int(a.get("quase_pediu") or 0),
            "favoritos": int(a.get("favoritos") or 0),
            "deslizes_tras": int(a.get("deslizes_tras") or 0),
            "vendas_qtd": float(dec(v["quantidade"])) if v else 0.0,
            "receita": float(dec(v["receita"])) if v else 0.0,
            "margem_pct": mg["margem_pct"], "margem_alvo_pct": mg["margem_alvo_pct"],
            # 🔑 O ajuste manual ganha do calculado; a tela mostra os dois.
            "margem_nivel": p["margem_nivel"] or mg["margem_calculada"],
            "margem_calculada": mg["margem_calculada"], "margem_manual": p["margem_nivel"],
        })

    if linhas:
        med_atencao = median(l["atencao_ms"] for l in linhas)
        med_venda = median(l["vendas_qtd"] for l in linhas)
        for l in linhas:
            # ⚠️ "≥ mediana E acima de zero": num período sem evento nenhum, a mediana é 0 e
            # todo prato seria "muita atenção".
            at_alta = l["atencao_ms"] >= med_atencao and l["atencao_ms"] > 0
            ve_alta = l["vendas_qtd"] >= med_venda and l["vendas_qtd"] > 0
            chave, prioridade = _sugestao(at_alta, ve_alta, l["margem_nivel"], l["objetivo"])
            l["quadrante"] = ("ALTA" if at_alta else "BAIXA") + "_ATENCAO_" + ("ALTA" if ve_alta else "BAIXA") + "_VENDA"
            l["sugestao"] = chave
            l["sugestao_rotulo"] = SUGESTOES.get(chave)
            l["prioridade"] = prioridade
        linhas.sort(key=lambda l: (-l["prioridade"], -l["atencao_ms"], l["nome"]))

    # ---------------------------------------------------------------- vídeo × foto
    cur.execute(
        f"""WITH ev AS (SELECT e.* FROM cardapio_eventos e WHERE {onde}),
                 eng AS (SELECT id_sessao FROM ev GROUP BY id_sessao HAVING {cv.SQL_SESSAO_ENGAJADA})
            SELECT midia, count(*) FILTER (WHERE tipo = 'viu_item') AS visualizacoes,
                   avg(least(duracao_ms, %s)) FILTER (WHERE tipo = 'viu_item') AS atencao_media_ms,
                   count(*) FILTER (WHERE tipo = 'adicionou') AS adicoes
              FROM ev WHERE id_sessao IN (SELECT id_sessao FROM eng) AND midia IN ('VIDEO', 'FOTO')
             GROUP BY midia""", [*valores, teto])  # noqa: S608
    midia = {r["midia"]: {"visualizacoes": r["visualizacoes"],
                          "atencao_media_ms": round(float(r["atencao_media_ms"])) if r["atencao_media_ms"] else None,
                          "taxa_adicao": round(r["adicoes"] / r["visualizacoes"], 4) if r["visualizacoes"] else None}
             for r in cur.fetchall()}

    # ---------------------------------------------------------------- mapa mesa × hora
    cur.execute(
        f"""SELECT m.nome AS mesa, s.nome AS salao, extract(hour FROM e.quando)::int AS hora,
                   count(DISTINCT e.id_sessao) AS sessoes
              FROM cardapio_eventos e JOIN mesas m ON m.id = e.id_mesa JOIN saloes s ON s.id = m.id_salao
             WHERE {onde}
             GROUP BY m.nome, s.nome, hora ORDER BY s.nome, m.nome, hora""", valores)  # noqa: S608
    mapa = [dict(r) for r in cur.fetchall()]

    # ---------------------------------------------------------------- chamados
    cf, cvv = ["c.id_unidade = %s", "c.criado_em >= %s::date", "c.criado_em < %s::date + 1"], [id_unidade, de, ate]
    if id_salao:
        cf.append("m.id_salao = %s")
        cvv.append(id_salao)
    cur.execute(
        f"""SELECT c.tipo, count(*) AS total, count(c.atendido_em) AS atendidos,
                   avg(extract(epoch FROM c.atendido_em - c.criado_em)) / 60 AS minutos
              FROM cardapio_chamados c JOIN mesas m ON m.id = c.id_mesa
             WHERE {' AND '.join(cf)} GROUP BY c.tipo""", cvv)  # noqa: S608
    chamados = {r["tipo"]: {"total": r["total"], "atendidos": r["atendidos"],
                            "tempo_medio_min": round(float(r["minutos"]), 1) if r["minutos"] is not None else None}
                for r in cur.fetchall()}

    return {
        "definicoes": DEFINICOES,
        "topo": {k: topo[k] for k in ("sessoes", "engajadas", "hubs", "cliques_avaliacao", "cliques_wifi")},
        "funil": {k: topo[k] for k in ("sessoes", "viram", "adicionaram", "enviaram")},
        "bruto_desde": topo["bruto_desde"].date().isoformat() if topo["bruto_desde"] else None,
        "itens": linhas, "midia": midia, "mapa": mapa, "chamados": chamados,
        "avisos": ["As vendas vêm do PDV e não são filtradas por salão (o cupom não diz o salão)."]
                  if id_salao else [],
    }
