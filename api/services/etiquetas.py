"""Etiquetas de validade: o que se PRODUZ e o que se ABRE para consumo.

🔑 **Pedido do dono (28/09/2026):** *"um novo módulo, o de Etiquetas: etiquetas para
controlar validade, quantidade e demais coisas úteis, em produtos produzidos e abertos
para consumo. Algo integrado, que controlamos de forma simples e rápida."* Estudo em
`docs/etiquetas-estudo.md`.

Três ideias seguram o módulo:

* **A validade depende do evento e da conservação** (`produto_validades`): o mesmo
  molho dura 3 dias refrigerado e 60 congelado. Sem regra, a produção cai no
  `produtos.validade_dias` de sempre; sem nenhum dos dois, alguém diz a data.
* **A etiqueta é um registro** — código curto, QR, situação. É o que faz "o que vence
  hoje" ser uma consulta e não uma volta pela câmara fria.
* **Descartar é perda no razão** (regra 1): quem joga fora pela etiqueta lança a
  `SAIDA_PERDA` com o valor, e o "jogamos fora" vira número.
"""

import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException

from config import WEB_URL
from services.custos import dec

EVENTOS = {"PRODUCAO": "Produzido", "ABERTURA": "Aberto", "DESCONGELAMENTO": "Descongelado"}
CONSERVACOES = {"REFRIGERADO": "Refrigerado", "CONGELADO": "Congelado", "AMBIENTE": "Ambiente"}
# 🔑 Sem letras que se confundem (0/O, 1/I/L): o código é digitado quando o QR não lê.
_ALFABETO = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

TAMANHOS = {  # largura x altura, em mm
    "40x40": (40, 40), "50x30": (50, 30), "60x40": (60, 40), "100x50": (100, 50),
}

_CONFIG_PADRAO = {"tamanho": "60x40", "mostrar_alergenos": True, "mostrar_lote": True,
                  "mostrar_quantidade": True, "mostrar_qr": True, "texto_extra": None}


# ---------------------------------------------------------------- configuração

def config(cur, id_unidade: int) -> dict:
    cur.execute(
        """SELECT tamanho, mostrar_alergenos, mostrar_lote, mostrar_quantidade, mostrar_qr,
                  texto_extra FROM etiqueta_config WHERE id_unidade = %s""", (id_unidade,))
    linha = cur.fetchone()
    return dict(linha) if linha else dict(_CONFIG_PADRAO)


def salvar_config(cur, id_unidade: int, dados: dict) -> dict:
    cur.execute(
        """INSERT INTO etiqueta_config (id_unidade, tamanho, mostrar_alergenos, mostrar_lote,
                                        mostrar_quantidade, mostrar_qr, texto_extra)
           VALUES (%(u)s, %(tamanho)s, %(mostrar_alergenos)s, %(mostrar_lote)s,
                   %(mostrar_quantidade)s, %(mostrar_qr)s, %(texto_extra)s)
           ON CONFLICT (id_unidade) DO UPDATE SET
               tamanho = EXCLUDED.tamanho, mostrar_alergenos = EXCLUDED.mostrar_alergenos,
               mostrar_lote = EXCLUDED.mostrar_lote,
               mostrar_quantidade = EXCLUDED.mostrar_quantidade,
               mostrar_qr = EXCLUDED.mostrar_qr, texto_extra = EXCLUDED.texto_extra,
               atualizado_em = now()""",
        dados | {"u": id_unidade, "texto_extra": (dados.get("texto_extra") or "").strip() or None},
    )
    return config(cur, id_unidade)


# ---------------------------------------------------------------- validades

def validades(cur, id_produto: int) -> list[dict]:
    cur.execute(
        """SELECT evento, conservacao, prazo, unidade, padrao FROM produto_validades
            WHERE id_produto = %s
            ORDER BY array_position(ARRAY['PRODUCAO','ABERTURA','DESCONGELAMENTO'], evento::text),
                     array_position(ARRAY['REFRIGERADO','CONGELADO','AMBIENTE'], conservacao::text)""",
        (id_produto,))
    return [dict(r) for r in cur.fetchall()]


def salvar_validades(cur, id_produto: int, regras: list[dict]) -> list[dict]:
    """Troca o conjunto inteiro. ⚠️ Um padrão por evento: o primeiro marcado vence; sem
    nenhum marcado, a primeira regra do evento vira o padrão — a tela precisa trazer UMA
    conservação já escolhida."""
    cur.execute("SELECT 1 FROM produtos WHERE id = %s", (id_produto,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    por_evento: dict[str, list[dict]] = {}
    for r in regras:
        por_evento.setdefault(r["evento"], []).append(dict(r))
    for lista in por_evento.values():
        marcados = [r for r in lista if r.get("padrao")]
        escolhido = marcados[0] if marcados else lista[0]
        for r in lista:
            r["padrao"] = r is escolhido
    cur.execute("DELETE FROM produto_validades WHERE id_produto = %s", (id_produto,))
    for lista in por_evento.values():
        for r in lista:
            cur.execute(
                """INSERT INTO produto_validades (id_produto, evento, conservacao, prazo,
                                                  unidade, padrao)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (id_produto, r["evento"], r["conservacao"], r["prazo"], r["unidade"],
                 r["padrao"]))
    return validades(cur, id_produto)


def produtos_com_regra(cur, busca: str | None, limite: int, offset: int, resposta) -> list[dict]:
    """Os produtos que já têm validade cadastrada — a lista da configuração."""
    from paginacao import pagina
    termo = f"%{busca.strip()}%" if busca and busca.strip() else None
    return pagina(
        cur,
        """SELECT p.id, p.codigo, p.nome, p.um_estoque,
                  json_agg(json_build_object('evento', v.evento, 'conservacao', v.conservacao,
                                             'prazo', v.prazo, 'unidade', v.unidade,
                                             'padrao', v.padrao)
                           ORDER BY v.evento, v.conservacao) AS regras
             FROM produtos p JOIN produto_validades v ON v.id_produto = p.id
            WHERE (%s::text IS NULL OR p.nome ILIKE %s OR p.codigo ILIKE %s)
            GROUP BY p.id ORDER BY p.nome""",
        (termo, termo, termo), limite=limite, offset=offset, resposta=resposta)


def _regra(cur, id_produto: int, evento: str, conservacao: str | None) -> dict | None:
    """A regra pedida; sem conservação, a padrão do evento."""
    cur.execute(
        """SELECT evento, conservacao, prazo, unidade, padrao FROM produto_validades
            WHERE id_produto = %s AND evento = %s AND (%s::text IS NULL OR conservacao = %s)
            ORDER BY padrao DESC, conservacao LIMIT 1""",
        (id_produto, evento, conservacao, conservacao))
    linha = cur.fetchone()
    return dict(linha) if linha else None


def _prazo(regra: dict) -> timedelta:
    return (timedelta(hours=regra["prazo"]) if regra["unidade"] == "HORAS"
            else timedelta(days=regra["prazo"]))


def _validade_dias(cur, id_produto: int) -> int | None:
    cur.execute("SELECT validade_dias FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    return linha["validade_dias"] if linha and linha["validade_dias"] else None


def validade_da_producao(cur, id_produto: int, quando: datetime) -> date | None:
    """A validade do LOTE que a produção cria (chamada por `estoque.produzir`).

    🔑 **Este é o furo que o módulo fecha**: a produção entrava no estoque sem data, e
    o FEFO e o alerta de vencimento só enxergavam o que veio de nota. A regra padrão da
    produção manda; sem ela, o `validade_dias` do cadastro; sem nenhum, lote sem data.
    """
    regra = _regra(cur, id_produto, "PRODUCAO", None)
    if regra:
        return (quando + _prazo(regra)).date()
    dias = _validade_dias(cur, id_produto)
    return quando.date() + timedelta(days=dias) if dias else None


def _fim_do_dia(d: date, tz) -> datetime:
    return datetime.combine(d, time(23, 59), tzinfo=tz)


def calcular_vencimento(cur, id_produto: int, evento: str, conservacao: str | None,
                        feito_em: datetime, validade_fabricante: date | None = None,
                        manual: datetime | None = None) -> dict:
    """Quando vence, e de onde saiu a resposta — a tela mostra a origem.

    ⚠️ **Aberto nunca vale mais que o fabricante**: o "3 dias depois de aberto" de um
    creme de leite que vence amanhã é amanhã.
    """
    regra = _regra(cur, id_produto, evento, conservacao)
    origem, vence = None, None
    if manual is not None:
        vence = manual if manual.tzinfo else manual.replace(tzinfo=feito_em.tzinfo)
        origem = "informada"
    elif regra:
        vence = feito_em + _prazo(regra)
        origem = "regra"
    elif evento == "PRODUCAO" and _validade_dias(cur, id_produto):
        vence = feito_em + timedelta(days=_validade_dias(cur, id_produto))
        origem = "cadastro"
    if validade_fabricante is not None:
        limite = _fim_do_dia(validade_fabricante, feito_em.tzinfo)
        if vence is None or limite < vence:
            vence, origem = limite, "fabricante"
    return {"vence_em": vence, "origem": origem, "regra": regra}


def _alergenos(cur, id_produto: int) -> str | None:
    cur.execute(
        """SELECT alergenos FROM fichas_tecnicas
            WHERE id_produto = %s AND status <> 'ARQUIVADA'
            ORDER BY (status = 'HOMOLOGADA' AND vigente_ate IS NULL) DESC, versao DESC
            LIMIT 1""", (id_produto,))
    linha = cur.fetchone()
    texto = (linha or {}).get("alergenos")
    return texto.strip() if texto and texto.strip() else None


def _agora(cur) -> datetime:
    cur.execute("SELECT now() AS agora")
    return cur.fetchone()["agora"]


def sugestao(cur, id_unidade: int, id_produto: int, evento: str,
             conservacao: str | None) -> dict:
    """O que a tela mostra ANTES de imprimir: validade calculada, conservações que o
    produto tem para o evento, alergênicos e unidade."""
    cur.execute("SELECT id, codigo, nome, um_estoque, controla_estoque FROM produtos WHERE id = %s",
                (id_produto,))
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    regras = [r for r in validades(cur, id_produto) if r["evento"] == evento]
    if conservacao is None and regras:
        conservacao = next((r["conservacao"] for r in regras if r["padrao"]),
                           regras[0]["conservacao"])
    agora = _agora(cur)
    calc = calcular_vencimento(cur, id_produto, evento, conservacao, agora)
    return {
        "produto": dict(produto), "evento": evento,
        "conservacao": conservacao or "REFRIGERADO",
        "regras": regras, "vence_em": calc["vence_em"], "origem": calc["origem"],
        "alergenos": _alergenos(cur, id_produto),
    }


# ---------------------------------------------------------------- emissão

def _codigo(cur) -> str:
    while True:
        codigo = "".join(secrets.choice(_ALFABETO) for _ in range(6))
        cur.execute("SELECT 1 FROM etiquetas WHERE codigo = %s", (codigo,))
        if not cur.fetchone():
            return codigo


def da_producao(cur, id_producao: int, id_unidade: int) -> dict:
    """O que a produção diz à etiqueta: produto, quanto, onde entrou e com que lote."""
    cur.execute(
        """SELECT pr.id, pr.id_unidade, pr.id_produto, pr.quantidade, pr.data,
                  p.nome AS produto, p.um_estoque,
                  m.id_local, l.nome AS local, el.lote, el.validade AS validade_lote
             FROM producoes pr
             JOIN produtos p ON p.id = pr.id_produto
             LEFT JOIN estoque_movimentos m
                    ON m.origem_tipo = 'PRODUCAO' AND m.origem_id = pr.id
                   AND m.tipo = 'ENTRADA_PRODUCAO'
             LEFT JOIN locais_estoque l ON l.id = m.id_local
             LEFT JOIN movimento_lotes ml ON ml.id_movimento = m.id
             LEFT JOIN estoque_lotes el ON el.id = ml.id_lote
            WHERE pr.id = %s
            ORDER BY m.id LIMIT 1""", (id_producao,))
    linha = cur.fetchone()
    if not linha or linha["id_unidade"] != id_unidade:
        raise HTTPException(status_code=404, detail="Produção não encontrada nesta loja")
    cur.execute("SELECT count(*) AS n FROM etiquetas WHERE id_producao = %s", (id_producao,))
    return dict(linha) | {"etiquetas": cur.fetchone()["n"]}


def _local(cur, id_unidade: int, id_local: int | None, id_produto: int) -> int | None:
    from services import estoque
    if id_local is None:
        cur.execute("SELECT id_local_padrao FROM produtos WHERE id = %s", (id_produto,))
        id_local = (cur.fetchone() or {}).get("id_local_padrao")
    try:
        padrao = estoque.local_padrao(cur, id_unidade)
    except HTTPException:
        padrao = None
    return estoque._local_desta_loja(cur, id_local, id_unidade, padrao) if padrao else id_local


def emitir(cur, *, id_unidade: int, id_usuario: int, nome_usuario: str, dados: dict) -> list[dict]:
    """Grava as etiquetas e devolve as linhas prontas para imprimir."""
    evento = dados["evento"]
    feito_em = _agora(cur)
    id_produto = dados.get("id_produto")
    lote, validade_lote = dados.get("lote"), None
    id_local = dados.get("id_local")
    quantidade = dados.get("quantidade")
    origem = None

    if dados.get("id_producao"):
        pr = da_producao(cur, dados["id_producao"], id_unidade)
        id_produto = pr["id_produto"]
        feito_em = pr["data"]
        lote, validade_lote = pr["lote"] or lote, pr["validade_lote"]
        id_local = id_local or pr["id_local"]
        if quantidade is None:
            # O porcionamento: 10 L em 5 potes são 5 etiquetas de 2 L.
            quantidade = (dec(pr["quantidade"]) / dados["copias"]).quantize(Decimal("0.0001"))
        evento = "PRODUCAO"

    if dados.get("id_origem"):
        cur.execute("SELECT * FROM etiquetas WHERE id = %s FOR UPDATE", (dados["id_origem"],))
        origem = cur.fetchone()
        if not origem or origem["id_unidade"] != id_unidade:
            raise HTTPException(status_code=404, detail="Etiqueta de origem não encontrada")
        if origem["status"] != "ATIVA":
            raise HTTPException(status_code=400,
                                detail="A etiqueta de origem já foi baixada — não há o que reetiquetar.")
        if origem["vence_em"] <= feito_em:
            raise HTTPException(status_code=400,
                                detail="Este pote já venceu — o caminho é descartar, não reetiquetar.")
        id_produto = origem["id_produto"]
        lote = lote or origem["lote"]
        validade_lote = origem["validade_lote"]
        id_local = id_local or origem["id_local"]
        if quantidade is None and origem["quantidade"] is not None:
            quantidade = (dec(origem["quantidade"]) / dados["copias"]).quantize(Decimal("0.0001"))

    cur.execute("SELECT id, nome, um_estoque, ativo FROM produtos WHERE id = %s", (id_produto,))
    produto = cur.fetchone()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    fab = dados.get("validade_fabricante")
    if fab and fab < feito_em.date():
        raise HTTPException(status_code=400,
                            detail="A validade do fabricante já passou — a embalagem está vencida.")

    # 🔑 **Reetiquetar (dividir o pote, trocar de lugar) NÃO renova a validade**: a nova
    # etiqueta herda o evento, a data e o vencimento da antiga. Só o descongelamento
    # começa um prazo novo — e mesmo ele nunca passa do antigo (ver abaixo).
    if origem is not None and evento != "DESCONGELAMENTO":
        evento, feito_em = origem["evento"], origem["feito_em"]
        dados = dados | {"conservacao": origem["conservacao"], "vence_em": origem["vence_em"]}

    conservacao = dados.get("conservacao")
    if conservacao is None:
        regra = _regra(cur, id_produto, evento, None)
        conservacao = regra["conservacao"] if regra else (
            origem["conservacao"] if origem else "REFRIGERADO")
    calc = calcular_vencimento(cur, id_produto, evento, conservacao, feito_em, fab,
                               dados.get("vence_em"))
    vence_em = calc["vence_em"]
    if vence_em is None:
        raise HTTPException(
            status_code=400,
            detail=(f"{produto['nome']} não tem validade cadastrada para "
                    f"{EVENTOS[evento].lower()} em {CONSERVACOES[conservacao].lower()}. "
                    "Informe a validade, ou cadastre a regra em Etiquetas ▸ Configuração."))
    if vence_em <= feito_em or (origem is None and vence_em <= _agora(cur)):
        raise HTTPException(status_code=400, detail="A validade precisa ser depois de agora.")
    # ⚠️ Descongelado não volta a durar mais que a etiqueta de onde saiu.
    if origem is not None and evento == "DESCONGELAMENTO" and origem["vence_em"] < vence_em:
        vence_em = origem["vence_em"]

    id_local = _local(cur, id_unidade, id_local, id_produto)
    responsavel = (dados.get("responsavel") or "").strip() or nome_usuario
    ids = []
    for _ in range(dados["copias"]):
        cur.execute(
            """INSERT INTO etiquetas (codigo, id_unidade, id_produto, evento, conservacao,
                                      feito_em, vence_em, quantidade, um, id_producao,
                                      id_local, lote, validade_lote, validade_fabricante,
                                      id_origem, responsavel, id_usuario, observacao)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (_codigo(cur), id_unidade, id_produto, evento, conservacao, feito_em, vence_em,
             quantidade, produto["um_estoque"], dados.get("id_producao"), id_local, lote,
             validade_lote, fab, origem["id"] if origem else None, responsavel, id_usuario,
             (dados.get("observacao") or "").strip() or None))
        ids.append(cur.fetchone()["id"])

    if origem is not None:
        # A etiqueta antiga deixa de valer: o pote agora é o da nova.
        cur.execute(
            """UPDATE etiquetas SET status = 'SUBSTITUIDA', baixada_em = now(),
                      baixada_por = %s, motivo = %s WHERE id = %s""",
            (id_usuario, f"{EVENTOS[evento]} — nova etiqueta", origem["id"]))
    return [obter(cur, i) for i in ids]


# ---------------------------------------------------------------- consulta

_SELECT = """
    SELECT e.id, e.codigo, e.id_unidade, e.id_produto, p.codigo AS produto_codigo,
           p.nome AS produto, e.evento, e.conservacao, e.feito_em, e.vence_em,
           e.quantidade, e.um, e.id_producao, e.id_local, l.nome AS local, e.lote,
           e.validade_lote, e.validade_fabricante, e.id_origem, e.responsavel,
           e.observacao, e.status, e.baixada_em, ub.nome AS baixada_por, e.motivo,
           e.id_movimento, e.impressoes, e.criado_em,
           CASE WHEN e.status <> 'ATIVA' THEN e.status
                WHEN e.vence_em < now() THEN 'VENCIDA'
                WHEN e.vence_em::date = current_date THEN 'HOJE'
                WHEN e.vence_em::date = current_date + 1 THEN 'AMANHA'
                ELSE 'EM_DIA' END AS situacao
      FROM etiquetas e
      JOIN produtos p ON p.id = e.id_produto
      LEFT JOIN locais_estoque l ON l.id = e.id_local
      LEFT JOIN usuarios ub ON ub.id = e.baixada_por
"""

_SITUACOES = {
    "ativas": "e.status = 'ATIVA'",
    "vencidas": "e.status = 'ATIVA' AND e.vence_em < now()",
    "hoje": "e.status = 'ATIVA' AND e.vence_em >= now() AND e.vence_em::date = current_date",
    "amanha": "e.status = 'ATIVA' AND e.vence_em::date = current_date + 1",
    "baixadas": "e.status <> 'ATIVA'",
    "todas": "true",
}


def obter(cur, id_etiqueta: int) -> dict:
    cur.execute(_SELECT + " WHERE e.id = %s", (id_etiqueta,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada")
    return dict(linha)


def por_codigo(cur, codigo: str, id_unidade: int | None = None) -> dict:
    cur.execute(_SELECT + " WHERE e.codigo = %s", (codigo.strip().upper(),))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada")
    etq = dict(linha)
    etq["alergenos"] = _alergenos(cur, etq["id_produto"])
    return etq


def consulta(cur, id_unidade: int, situacao: str, busca: str | None, id_local: int | None,
             evento: str | None, limite: int, offset: int, resposta) -> list[dict]:
    from paginacao import pagina
    if situacao not in _SITUACOES:
        raise HTTPException(status_code=400, detail="Situação inválida")
    termo = f"%{busca.strip()}%" if busca and busca.strip() else None
    ordem = "e.baixada_em DESC" if situacao == "baixadas" else "e.vence_em, e.id"
    return pagina(
        cur,
        _SELECT + f"""
         WHERE e.id_unidade = %s AND {_SITUACOES[situacao]}
           AND (%s::text IS NULL OR p.nome ILIKE %s OR e.codigo ILIKE %s OR e.lote ILIKE %s)
           AND (%s::int IS NULL OR e.id_local = %s)
           AND (%s::text IS NULL OR e.evento = %s)
         ORDER BY {ordem}""",
        (id_unidade, termo, termo, termo, termo, id_local, id_local, evento, evento),
        limite=limite, offset=offset, resposta=resposta)


def painel(cur, id_unidade: int) -> dict:
    """Os números da checagem da manhã."""
    cur.execute(
        """SELECT count(*) FILTER (WHERE status = 'ATIVA') AS ativas,
                  count(*) FILTER (WHERE status = 'ATIVA' AND vence_em < now()) AS vencidas,
                  count(*) FILTER (WHERE status = 'ATIVA' AND vence_em >= now()
                                     AND vence_em::date = current_date) AS hoje,
                  count(*) FILTER (WHERE status = 'ATIVA'
                                     AND vence_em::date = current_date + 1) AS amanha,
                  count(*) FILTER (WHERE status = 'DESCARTADA'
                                     AND baixada_em >= current_date - 30) AS descartadas_30d
             FROM etiquetas WHERE id_unidade = %s""", (id_unidade,))
    r = dict(cur.fetchone())
    cur.execute(
        """SELECT coalesce(sum(m.custo_total), 0) AS valor
             FROM etiquetas e JOIN estoque_movimentos m ON m.id = e.id_movimento
            WHERE e.id_unidade = %s AND e.status = 'DESCARTADA'
              AND e.baixada_em >= current_date - 30""", (id_unidade,))
    r["valor_descartado_30d"] = float(cur.fetchone()["valor"])
    return r


# ---------------------------------------------------------------- baixa

def _ativa(cur, id_etiqueta: int, id_unidade: int) -> dict:
    cur.execute("SELECT * FROM etiquetas WHERE id = %s FOR UPDATE", (id_etiqueta,))
    etq = cur.fetchone()
    if not etq or etq["id_unidade"] != id_unidade:
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada nesta loja")
    if etq["status"] != "ATIVA":
        raise HTTPException(status_code=400, detail="Esta etiqueta já foi baixada.")
    return dict(etq)


def usar(cur, id_etiqueta: int, id_unidade: int, id_usuario: int,
         observacao: str | None = None) -> dict:
    """"Usei tudo": a etiqueta sai das ativas. ⚠️ Não mexe no estoque — o consumo já
    entra pela venda ou pela produção que usou o pote."""
    _ativa(cur, id_etiqueta, id_unidade)
    cur.execute(
        """UPDATE etiquetas SET status = 'USADA', baixada_em = now(), baixada_por = %s,
                  motivo = %s WHERE id = %s""",
        (id_usuario, (observacao or "").strip() or None, id_etiqueta))
    return obter(cur, id_etiqueta)


def descartar(cur, id_etiqueta: int, id_unidade: int, id_usuario: int, dados: dict) -> dict:
    """Jogar fora pela etiqueta = perda no razão, com o valor.

    ⚠️ **Só o service de estoque escreve no razão** (regra 3): a perda passa por
    `estoque.lancar`, com a mesma trava de saldo e o mesmo motivo obrigatório.
    ⚠️ O lote da produção só é usado se ainda tem a quantidade — senão o FEFO escolhe:
    lote negativo seria controle mentindo.
    """
    from services import estoque
    etq = _ativa(cur, id_etiqueta, id_unidade)
    qtd = dados.get("quantidade")
    qtd = dec(qtd) if qtd is not None else dec(etq["quantidade"] or 0)
    id_movimento = None
    cur.execute("SELECT controla_estoque FROM produtos WHERE id = %s", (etq["id_produto"],))
    controla = (cur.fetchone() or {}).get("controla_estoque")
    if dados.get("lancar_perda", True) and qtd > 0 and controla:
        id_local = etq["id_local"] or estoque.local_padrao(cur, id_unidade)
        lote = validade = None
        if etq["lote"] and etq["validade_lote"]:
            cur.execute(
                """SELECT quantidade FROM estoque_lotes
                    WHERE id_unidade = %s AND id_local = %s AND id_produto = %s
                      AND lote = %s AND validade = %s""",
                (id_unidade, id_local, etq["id_produto"], etq["lote"], etq["validade_lote"]))
            linha = cur.fetchone()
            if linha and dec(linha["quantidade"]) >= qtd:
                lote, validade = etq["lote"], etq["validade_lote"]
        motivo = (dados.get("motivo") or "").strip()
        r = estoque.lancar(
            cur, id_unidade=id_unidade, id_produto=etq["id_produto"], tipo="SAIDA_PERDA",
            quantidade=qtd, id_local=id_local, origem_tipo="ETIQUETA", origem_id=etq["id"],
            id_motivo_perda=dados.get("id_motivo_perda"), id_usuario=id_usuario,
            observacao=f"Etiqueta {etq['codigo']}" + (f" · {motivo}" if motivo else ""),
            lote=lote, validade=validade)
        id_movimento = r["id"]
    motivo_txt = (dados.get("motivo") or "").strip() or None
    if not motivo_txt and dados.get("id_motivo_perda"):
        cur.execute("SELECT nome FROM perda_motivos WHERE id = %s", (dados["id_motivo_perda"],))
        motivo_txt = (cur.fetchone() or {}).get("nome")
    cur.execute(
        """UPDATE etiquetas SET status = 'DESCARTADA', baixada_em = now(), baixada_por = %s,
                  motivo = %s, id_movimento = %s WHERE id = %s""",
        (id_usuario, motivo_txt, id_movimento, id_etiqueta))
    return obter(cur, id_etiqueta)


def alertas(cur, id_unidade: int) -> dict:
    cur.execute(
        """SELECT count(*) FILTER (WHERE vence_em < now()) AS vencidas,
                  count(*) FILTER (WHERE vence_em >= now()
                                     AND vence_em::date = current_date) AS hoje
             FROM etiquetas WHERE id_unidade = %s AND status = 'ATIVA'""", (id_unidade,))
    return dict(cur.fetchone())


# ---------------------------------------------------------------- impressão

def link(codigo: str) -> str:
    return f"{WEB_URL.rstrip('/')}/etiquetas/e/{codigo}"


def _fmt(d: datetime | None) -> str:
    return d.strftime("%d/%m/%y %H:%M") if d else "—"


def _num(v) -> str:
    d = Decimal(str(v)).normalize()
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    return f"{d:f}".replace(".", ",")


def _desenhar(c, x: float, y: float, w: float, h: float, e: dict, cfg: dict) -> None:
    """Uma etiqueta no retângulo (x, y, w, h) — y é a base. Tudo escala com a altura."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.units import mm

    from services.fidelidade_qr import _quebrar

    k = h / (40 * mm)  # 1.0 na etiqueta de 40 mm de altura
    m = 2 * mm
    qr_lado = 0
    if cfg["mostrar_qr"]:
        qr_lado = min(h * 0.5, w * 0.34)
        qr = QrCodeWidget(link(e["codigo"]), barLevel="M")
        x0, y0, x1, y1 = qr.getBounds()
        d = Drawing(qr_lado, qr_lado,
                    transform=[qr_lado / (x1 - x0), 0, 0, qr_lado / (y1 - y0), 0, 0])
        d.add(qr)
        qx, qy = x + w - m - qr_lado, y + h - m - qr_lado
        renderPDF.draw(d, c, qx, qy)
        c.setFont("Helvetica-Bold", 6.5 * k)
        c.drawCentredString(qx + qr_lado / 2, qy - 6.5 * k, e["codigo"])
    largura = w - 2 * m - (qr_lado + 1.5 * mm if qr_lado else 0)
    topo = y + h - m

    def linha(texto, fonte, tam, larg=largura):
        nonlocal topo
        for pedaco in _quebrar(c, texto, fonte, tam, larg)[:2]:
            topo -= tam * 1.05
            c.setFont(fonte, tam)
            c.drawString(x + m, topo, pedaco)

    linha(e["produto"].upper(), "Helvetica-Bold", 8.5 * k)
    topo -= 1 * k
    linha(f"{EVENTOS[e['evento']].upper()} {_fmt(e['feito_em'])}", "Helvetica", 6.5 * k)
    linha(CONSERVACOES[e["conservacao"]].upper(), "Helvetica", 6.5 * k)
    topo -= 1.5 * k
    linha("VALIDADE", "Helvetica", 6 * k)
    linha(_fmt(e["vence_em"]), "Helvetica-Bold", 11 * k)
    # O resto ocupa a largura toda: abaixo do QR.
    topo = min(topo, y + h - m - qr_lado - 8 * k) if qr_lado else topo
    detalhes = [f"Resp.: {e['responsavel']}"]
    if cfg["mostrar_lote"] and e.get("lote"):
        detalhes.append(f"Lote: {e['lote']}")
    if cfg["mostrar_quantidade"] and e.get("quantidade") is not None:
        detalhes.append(f"Qtd: {_num(e['quantidade'])} {e.get('um') or ''}".strip())
    if e.get("validade_fabricante"):
        detalhes.append(f"Val. fabricante: {e['validade_fabricante'].strftime('%d/%m/%y')}")
    linha("  ·  ".join(detalhes), "Helvetica", 6 * k, w - 2 * m)
    if cfg["mostrar_alergenos"] and e.get("alergenos"):
        linha(f"Alérgenos: {e['alergenos']}", "Helvetica-Bold", 5.5 * k, w - 2 * m)
    if cfg.get("texto_extra"):
        linha(cfg["texto_extra"], "Helvetica-Oblique", 5.5 * k, w - 2 * m)


def pdf(cur, ids: list[int], id_unidade: int, reimpressao: bool = False) -> bytes:
    """Uma página por etiqueta no tamanho do rolo — ou a folha A4 cheia de 60x40.

    🔑 **O rolo térmico imprime página a página**: com o driver da impressora
    configurado no mesmo tamanho, cada página do PDF é uma etiqueta.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    cfg = config(cur, id_unidade)
    etiquetas = []
    for i in ids:
        e = obter(cur, i)
        if e["id_unidade"] != id_unidade:
            raise HTTPException(status_code=404, detail="Etiqueta não encontrada nesta loja")
        e["alergenos"] = _alergenos(cur, e["id_produto"])
        etiquetas.append(e)
    buf = BytesIO()
    if cfg["tamanho"] == "A4":
        w, h = 60 * mm, 40 * mm
        c = canvas.Canvas(buf, pagesize=A4)
        colunas, linhas = 3, 7
        mx = (A4[0] - colunas * w) / 2
        my = (A4[1] - linhas * h) / 2
        for n, e in enumerate(etiquetas):
            pos = n % (colunas * linhas)
            if n and pos == 0:
                c.showPage()
            col, lin = pos % colunas, pos // colunas
            ex, ey = mx + col * w, A4[1] - my - (lin + 1) * h
            c.setDash(2, 2)
            c.setLineWidth(0.3)
            c.rect(ex, ey, w, h)
            c.setDash()
            _desenhar(c, ex, ey, w, h, e, cfg)
    else:
        lw, lh = TAMANHOS[cfg["tamanho"]]
        w, h = lw * mm, lh * mm
        c = canvas.Canvas(buf, pagesize=(w, h))
        for n, e in enumerate(etiquetas):
            if n:
                c.showPage()
            _desenhar(c, 0, 0, w, h, e, cfg)
    c.setTitle("Etiquetas")
    c.save()
    if reimpressao and ids:
        # Quantas vezes saiu: etiqueta reimpressa demais é pote duplicado na câmara.
        cur.execute("UPDATE etiquetas SET impressoes = impressoes + 1 WHERE id = ANY(%s)",
                    (ids,))
    return buf.getvalue()
