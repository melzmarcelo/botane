"""Os anúncios do Cardápio Vivo (121, fase 1): cadastro, regras da casa, feed e relatório.

🔑 Pedido do dono (16/10/2026): anúncios no meio do cardápio — da casa (o catálogo do Dia dos
Namorados) ou de outra marca —, com período, dias e links; formas e tempo de exibição; métricas;
e "nada pesado": algo orgânico. A casa cadastra; o parceiro recebe o RELATÓRIO, sem acesso.
🔑 **Quem decide ONDE e QUAL é a tela**, pelas regras da casa (5º prato, 8 de distância,
máximo 2 — 1 na mesa): o servidor manda só os anúncios que valem AGORA neste cardápio.
⚠️ O que o cliente fez fica na sessão anônima de sempre; nada liga anúncio a pessoa.
🔑 **Fases 2 e 3 (125, 20/10/2026)**: o ritmo que aprende (na tela, `sequencia.ts`), a relevância
pelas `secoes`, o **grupo de controle** (a fatia das visitas sem anúncio, gravada em cada evento) e
as **variações** do texto, com a vencedora escolhida pela taxa de toque — as duas contas de
sorteio são do banco (`hashtext` da sessão), como os testes A/B (116).
"""

from datetime import date, datetime, timedelta
import re

import arquivos
from fastapi import HTTPException
from relogio import agora_da_casa
from services import traducao

ORIGENS = ("CASA", "EXTERNO")
ACOES = ("NENHUMA", "CATALOGO", "PRATO", "LINK")
CANAIS = ("AMBOS", "MESA", "LINK")
# Abaixo disto, o anúncio passou na rolagem: a pessoa NÃO parou para ver ("pulou").
PULOU_MS = 1500
_REGRAS = ("anuncio_depois_de", "anuncio_intervalo", "anuncio_maximo", "anuncio_maximo_mesa",
           "anuncio_controle", "anuncio_recuo")
_REGRAS_PADRAO = {"anuncio_depois_de": 5, "anuncio_intervalo": 8, "anuncio_maximo": 2, "anuncio_maximo_mesa": 1,
                  "anuncio_controle": 10, "anuncio_recuo": True}
# 🔑 125: as duas contas de sorteio, no banco. ⚠️ `mod(…)` e não `%`: o `%` solto conflita com os
# marcadores do psycopg2. Sufixos diferentes: o grupo e a variação não andam juntos.
SQL_CONTROLE = "mod(abs(hashtext({sessao}::text || ':anuncios')), 100)"
SQL_VARIACAO = "mod(abs(hashtext({sessao}::text || ':variacao:' || {anuncio}::text)), {total})"
MAX_VARIANTES = 3
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)

_COLUNAS = """a.id, a.id_unidade, a.nome, a.origem, a.anunciante, a.titulo, a.texto, a.foto_url,
              a.video_url, a.video_capa_url, a.video_segundos, a.acao, a.acao_catalogo,
              a.acao_item, a.acao_url, a.acao_rotulo, a.inicio, a.fim, a.dias, a.hora_de,
              a.hora_ate, a.horario_especial, a.cardapios, a.canal, a.peso, a.ativo, a.criado_em,
              a.secoes"""


def _anuncio(cur, id_unidade: int, id_anuncio: int) -> dict:
    cur.execute(f"SELECT {_COLUNAS} FROM cardapio_anuncios a WHERE a.id = %s AND a.id_unidade = %s",  # noqa: S608
                (id_anuncio, id_unidade))
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado.")
    return dict(achado)


def _texto(v: str | None) -> str | None:
    return (v or "").strip() or None


def _conferir(cur, id_unidade: int, d: dict) -> None:
    """O que o anúncio aponta tem de ser DESTA loja, e o botão tem de ter destino."""
    if d["origem"] == "EXTERNO" and not _texto(d.get("anunciante")):
        raise HTTPException(status_code=422, detail="Anúncio de outra marca precisa do nome do anunciante — "
                                                    "é ele que aparece no “Patrocinado”.")
    if d.get("inicio") and d.get("fim") and d["inicio"] > d["fim"]:
        raise HTTPException(status_code=422, detail="O período termina antes de começar.")
    if (d.get("hora_de") is None) != (d.get("hora_ate") is None):
        raise HTTPException(status_code=422, detail="Informe as duas pontas do horário, ou nenhuma.")
    visivel = """EXISTS (SELECT 1 FROM catalogo_lojas l WHERE l.id_catalogo = c.id AND l.id_unidade = %s)"""
    if d["acao"] == "CATALOGO":
        cur.execute(f"SELECT 1 FROM catalogos c WHERE c.id = %s AND {visivel}", (d.get("acao_catalogo"), id_unidade))  # noqa: S608
        if not d.get("acao_catalogo") or not cur.fetchone():
            raise HTTPException(status_code=422, detail="Escolha o catálogo da casa que o botão abre.")
    if d["acao"] == "PRATO":
        cur.execute(f"""SELECT 1 FROM catalogo_itens i JOIN catalogo_categorias g ON g.id = i.id_categoria
                          JOIN catalogos c ON c.id = g.id_catalogo
                         WHERE i.id = %s AND {visivel}""", (d.get("acao_item"), id_unidade))  # noqa: S608
        if not d.get("acao_item") or not cur.fetchone():
            raise HTTPException(status_code=422, detail="Escolha o prato que o botão mostra.")
    if d["acao"] == "LINK" and not _URL.match((d.get("acao_url") or "").strip()):
        raise HTTPException(status_code=422, detail="O link precisa começar com https:// (ou http://).")
    for idc in d.get("cardapios") or []:
        cur.execute(f"SELECT 1 FROM catalogos c WHERE c.id = %s AND {visivel}", (idc, id_unidade))  # noqa: S608
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="Um dos cardápios escolhidos não é desta loja.")
    # 🔑 125: as seções em que combina — de um catálogo desta loja.
    if d.get("secoes"):
        cur.execute(f"""SELECT count(*) AS n FROM catalogo_categorias g JOIN catalogos c ON c.id = g.id_catalogo
                         WHERE g.id = ANY(%s) AND {visivel}""", (list(set(d["secoes"])), id_unidade))  # noqa: S608
        if cur.fetchone()["n"] != len(set(d["secoes"])):
            raise HTTPException(status_code=422, detail="Uma das seções escolhidas não é de um cardápio desta loja.")


def _valores(d: dict) -> tuple:
    acao = d["acao"]
    return (_texto(d.get("nome")) or "Anúncio", d["origem"], _texto(d.get("anunciante")),
            _texto(d.get("titulo")), _texto(d.get("texto")), acao,
            d.get("acao_catalogo") if acao == "CATALOGO" else None,
            d.get("acao_item") if acao == "PRATO" else None,
            (d.get("acao_url") or "").strip() or None if acao == "LINK" else None,
            _texto(d.get("acao_rotulo")) if acao != "NENHUMA" else None,
            d.get("inicio"), d.get("fim"), d.get("dias") or None, d.get("hora_de"), d.get("hora_ate"),
            bool(d.get("horario_especial")), d.get("cardapios") or None, d.get("canal", "AMBOS"),
            d.get("peso", 1), d.get("ativo", True), sorted(set(d["secoes"])) if d.get("secoes") else None)


_CAMPOS = """nome, origem, anunciante, titulo, texto, acao, acao_catalogo, acao_item, acao_url,
             acao_rotulo, inicio, fim, dias, hora_de, hora_ate, horario_especial, cardapios, canal,
             peso, ativo, secoes"""


def criar(cur, id_unidade: int, dados: dict, id_usuario: int | None) -> dict:
    _conferir(cur, id_unidade, dados)
    cur.execute(f"""INSERT INTO cardapio_anuncios (id_unidade, {_CAMPOS}, criado_por)
                    VALUES (%s, {', '.join(['%s'] * 21)}, %s) RETURNING id""",  # noqa: S608
                (id_unidade, *_valores(dados), id_usuario))
    novo = cur.fetchone()["id"]
    traducao.tentar(cur, "anuncio", novo)
    return _anuncio(cur, id_unidade, novo)


def atualizar(cur, id_unidade: int, id_anuncio: int, dados: dict) -> dict:
    _anuncio(cur, id_unidade, id_anuncio)
    _conferir(cur, id_unidade, dados)
    sets = ", ".join(f"{c.strip()} = %s" for c in _CAMPOS.split(","))
    cur.execute(f"UPDATE cardapio_anuncios SET {sets} WHERE id = %s",  # noqa: S608
                (*_valores(dados), id_anuncio))
    traducao.tentar(cur, "anuncio", id_anuncio)
    return _anuncio(cur, id_unidade, id_anuncio)


def remover(cur, id_unidade: int, id_anuncio: int) -> dict:
    """Apaga o anúncio e a mídia dele. ⚠️ Os EVENTOS ficam (o relatório de um anúncio apagado
    some da tela, mas a atenção medida continua no agregado da loja)."""
    atual = _anuncio(cur, id_unidade, id_anuncio)
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        arquivos.remover(velho, cur)
    cur.execute("DELETE FROM cardapio_anuncios WHERE id = %s", (id_anuncio,))
    return {"message": f"Anúncio “{atual['nome']}” removido."}


# ------------------------------------------------------------------ a mídia (foto OU vídeo)

def guardar_foto(cur, id_unidade: int, id_anuncio: int, conteudo: bytes, mime: str, extensao: str) -> dict:
    atual = _anuncio(cur, id_unidade, id_anuncio)
    url = arquivos.gravar(cur, conteudo, mime, extensao, f"anuncio-{id_anuncio}")
    cur.execute("""UPDATE cardapio_anuncios SET foto_url = %s, video_url = NULL, video_capa_url = NULL,
                          video_segundos = NULL WHERE id = %s""", (url, id_anuncio))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho and velho != url:
            arquivos.remover(velho, cur)
    return _anuncio(cur, id_unidade, id_anuncio)


def guardar_video(cur, id_unidade: int, id_anuncio: int, mp4: bytes, capa: bytes, segundos: float) -> dict:
    atual = _anuncio(cur, id_unidade, id_anuncio)
    url = arquivos.gravar(cur, mp4, arquivos.VIDEO_TIPO, ".mp4", f"anuncio-video-{id_anuncio}")
    url_capa = arquivos.gravar(cur, capa, "image/webp", ".webp", f"anuncio-capa-{id_anuncio}")
    cur.execute("""UPDATE cardapio_anuncios SET video_url = %s, video_capa_url = %s, video_segundos = %s,
                          foto_url = NULL WHERE id = %s""", (url, url_capa, segundos, id_anuncio))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho:
            arquivos.remover(velho, cur)
    return _anuncio(cur, id_unidade, id_anuncio)


def remover_midia(cur, id_unidade: int, id_anuncio: int) -> dict:
    atual = _anuncio(cur, id_unidade, id_anuncio)
    cur.execute("""UPDATE cardapio_anuncios SET foto_url = NULL, video_url = NULL, video_capa_url = NULL,
                          video_segundos = NULL WHERE id = %s""", (id_anuncio,))
    for velho in (atual["foto_url"], atual["video_url"], atual["video_capa_url"]):
        if velho:
            arquivos.remover(velho, cur)
    return _anuncio(cur, id_unidade, id_anuncio)


# ------------------------------------------------------------------ as regras da casa

def regras(cur, id_unidade: int) -> dict:
    cur.execute(f"SELECT {', '.join(_REGRAS)} FROM cardapio_config WHERE id_unidade = %s", (id_unidade,))  # noqa: S608
    linha = cur.fetchone()
    return dict(linha) if linha else dict(_REGRAS_PADRAO)


def salvar_regras(cur, id_unidade: int, dados: dict) -> dict:
    """⚠️ Só as quatro colunas: o resto da configuração da casa não é tocado (e uma loja que
    nunca gravou a aparência nasce com o padrão dela)."""
    valores = [dados[c] for c in _REGRAS]
    cur.execute(
        f"""INSERT INTO cardapio_config (id_unidade, {', '.join(_REGRAS)})
            VALUES (%s, {', '.join(['%s'] * len(_REGRAS))})
            ON CONFLICT (id_unidade) DO UPDATE SET
              {', '.join(f'{c} = EXCLUDED.{c}' for c in _REGRAS)}""",  # noqa: S608
        (id_unidade, *valores))
    return regras(cur, id_unidade)


# ------------------------------------------------------------------ a lista, com a atenção

def _metricas_sql(filtro: str) -> str:
    return f"""count(e.id) FILTER (WHERE e.tipo = 'viu_anuncio' {filtro}) AS aparicoes,
               count(DISTINCT e.id_sessao) FILTER (WHERE e.tipo = 'viu_anuncio' {filtro}) AS sessoes,
               round(avg(e.duracao_ms) FILTER (WHERE e.tipo = 'viu_anuncio' {filtro}) / 1000.0, 1) AS segundos,
               count(e.id) FILTER (WHERE e.tipo = 'viu_anuncio' AND e.duracao_ms < {PULOU_MS} {filtro}) AS pulados,
               count(e.id) FILTER (WHERE e.tipo = 'clicou_anuncio' {filtro}) AS toques,
               count(DISTINCT e.id_sessao) FILTER (WHERE e.tipo = 'clicou_anuncio' {filtro}) AS sessoes_tocaram"""


def listar(cur, id_unidade: int) -> dict:
    """Os anúncios da loja com a atenção dos últimos 30 dias, e as regras de exibição."""
    cur.execute(
        f"""SELECT {_COLUNAS}, {_metricas_sql("AND e.quando > now() - interval '30 days'")},
                   (SELECT count(*) FROM cardapio_anuncio_variantes v
                     WHERE v.id_anuncio = a.id AND v.ativo) AS variantes
              FROM cardapio_anuncios a
              LEFT JOIN cardapio_eventos e ON e.id_anuncio = a.id AND e.id_unidade = a.id_unidade
             WHERE a.id_unidade = %s
             GROUP BY a.id
             ORDER BY a.ativo DESC, a.criado_em DESC""",  # noqa: S608
        (id_unidade,))
    linhas = [dict(r) for r in cur.fetchall()]
    agora = agora_da_casa().replace(tzinfo=None)
    hoje = agora.date()
    contexto = _contexto_dos_avisos(cur, id_unidade, linhas, hoje)
    from services.cardapio_vivo import _secao_visivel  # ⚠️ aqui dentro: aquele importa este
    saida = []
    for d in linhas:
        d["situacao"] = ("DESLIGADO" if not d["ativo"] else "ENCERRADO" if d["fim"] and d["fim"] < hoje
                         else "AGENDADO" if d["inicio"] and d["inicio"] > hoje else "NO_AR")
        d["avisos"] = _avisos(d, contexto) if d["situacao"] in ("NO_AR", "AGENDADO") else []
        if d["avisos"]:
            d["situacao"] = "COM_PROBLEMA"
        # Informativo: no período, mas fora do dia ou do horário DESTE momento.
        d["fora_do_horario_agora"] = d["situacao"] == "NO_AR" and not _secao_visivel(
            {"dias": d["dias"], "hora_de": d["hora_de"], "hora_ate": d["hora_ate"],
             "horario_especial": d["horario_especial"]}, agora, contexto["especial"])
        saida.append(d)
    return {"anuncios": saida, "regras": regras(cur, id_unidade), "pulou_ms": PULOU_MS}


def _contexto_dos_avisos(cur, id_unidade: int, anuncios: list[dict], hoje: date) -> dict:
    """O que os avisos precisam saber da loja, buscado UMA vez para a lista inteira."""
    cur.execute("SELECT id_catalogo, principal FROM cardapio_vivos WHERE id_unidade = %s", (id_unidade,))
    vivos = {r["id_catalogo"]: r["principal"] for r in cur.fetchall()}
    cur.execute(
        """SELECT c.id, c.nome, c.situacao = 'ATIVO' AND (c.publica_de IS NULL OR c.publica_de <= %s)
                  AND (c.publica_ate IS NULL OR c.publica_ate >= %s) AS no_ar
             FROM catalogos c
            WHERE EXISTS (SELECT 1 FROM catalogo_lojas l WHERE l.id_catalogo = c.id AND l.id_unidade = %s)""",
        (hoje, hoje, id_unidade))
    catalogos = {r["id"]: dict(r) for r in cur.fetchall()}
    itens = sorted({a["acao_item"] for a in anuncios if a["acao_item"]})
    item_catalogo: dict[int, int] = {}
    if itens:
        cur.execute("""SELECT i.id, g.id_catalogo FROM catalogo_itens i
                         JOIN catalogo_categorias g ON g.id = i.id_categoria WHERE i.id = ANY(%s)""", (itens,))
        item_catalogo = {r["id"]: r["id_catalogo"] for r in cur.fetchall()}
    cur.execute("SELECT 1 FROM reserva_dias_especiais WHERE id_unidade = %s AND data = %s", (id_unidade, hoje))
    return {"vivos": vivos, "catalogos": catalogos, "item_catalogo": item_catalogo,
            "especial": cur.fetchone() is not None}


def _avisos(a: dict, ctx: dict) -> list[str]:
    """Por que um anúncio ligado e no período NÃO aparece, ou aparece pela metade.

    🔑 **Achado da análise de 17/10/2026**: o anúncio cujo destino sumiu (catálogo apagado ou
    fora do ar, prato tirado do cardápio — as chaves são `SET NULL`) continuava "no ar", e o
    feed o mostrava sem botão. As regras abaixo são as MESMAS de `do_feed` e de
    `acaoDoAnuncio` (na tela), lidas do lado de quem cadastra.
    """
    avisos: list[str] = []
    cat, vivos = ctx["catalogos"], ctx["vivos"]
    nome = lambda c: f"“{cat[c]['nome']}”" if c in cat else "o catálogo"  # noqa: E731
    if not (_texto(a["titulo"]) or _texto(a["texto"]) or a["foto_url"] or a["video_url"]):
        avisos.append("Sem título, texto, foto nem vídeo — não aparece no cardápio.")
    if a["acao"] == "CATALOGO":
        if not a["acao_catalogo"] or a["acao_catalogo"] not in cat:
            avisos.append("O catálogo do botão foi apagado ou saiu desta loja — o anúncio aparece sem botão.")
        elif not cat[a["acao_catalogo"]]["no_ar"]:
            avisos.append(f"O catálogo do botão ({nome(a['acao_catalogo'])}) está fora do ar — "
                          "quem tocar não vai achar o cardápio.")
    if a["acao"] == "PRATO":
        dono = ctx["item_catalogo"].get(a["acao_item"]) if a["acao_item"] else None
        if not dono:
            avisos.append("O prato do botão saiu do cardápio — o anúncio aparece sem botão.")
        elif dono not in vivos:
            avisos.append(f"O prato do botão é de {nome(dono)}, que não é Cardápio Vivo — o botão não aparece.")
    # Onde ele pode aparecer: os Cardápios Vivos da loja (os escolhidos, se houver escolha), menos
    # o que o próprio botão abre, e — só na mesa — o principal.
    onde = set(vivos) & set(a["cardapios"]) if a["cardapios"] else set(vivos)
    if a["acao"] == "CATALOGO":
        onde.discard(a["acao_catalogo"])
    if not vivos:
        avisos.append("A loja não tem nenhum Cardápio Vivo — não há onde aparecer.")
    elif not onde:
        avisos.append("Nenhum dos cardápios escolhidos é Cardápio Vivo (ou é o mesmo que o botão abre) — "
                      "não há onde aparecer.")
    elif a["canal"] == "MESA" and not any(vivos[c] for c in onde):
        avisos.append("Só na mesa, mas a mesa abre o cardápio principal, que não está entre os escolhidos.")
    return avisos


# ------------------------------------------------------------------ o relatório

def relatorio(cur, id_unidade: int, id_anuncio: int, de: date, ate: date) -> dict:
    """Os números de UM anúncio num período — para a casa apresentar ao parceiro.

    🔑 Pessoas = sessões anônimas que viram (uma visita ao cardápio); "pularam" = passou em
    menos de 1,5 s; taxa de toque = sessões que tocaram ÷ sessões que viram.
    🔑 **O que passou da retenção vem do resumo do dia** (124, 1.1.109): os dias que o bruto já
    não tem saem de `cardapio_conteudo_dia`. ⚠️ Ali as pessoas são contadas por DIA — quem
    voltou noutro dia conta duas vezes — e não há hora; a resposta diz até quando foi assim.
    """
    a = _anuncio(cur, id_unidade, id_anuncio)
    if de > ate:
        raise HTTPException(status_code=422, detail="O período termina antes de começar.")
    janela = """AND e.quando >= %(de)s::date AND e.quando < (%(ate)s::date + 1)"""
    p = {"a": id_anuncio, "u": id_unidade, "de": de, "ate": ate}
    cur.execute(f"""SELECT {_metricas_sql(janela)} FROM cardapio_eventos e
                     WHERE e.id_anuncio = %(a)s AND e.id_unidade = %(u)s""", p)  # noqa: S608
    total = dict(cur.fetchone())
    cur.execute(f"""SELECT (e.quando AT TIME ZONE 'America/Sao_Paulo')::date AS dia, {_metricas_sql('')}
                      FROM cardapio_eventos e
                     WHERE e.id_anuncio = %(a)s AND e.id_unidade = %(u)s {janela}
                     GROUP BY 1 ORDER BY 1""", p)  # noqa: S608
    por_dia = [dict(r) for r in cur.fetchall()]
    cur.execute(f"""SELECT CASE WHEN e.id_mesa IS NULL THEN 'LINK' ELSE 'MESA' END AS canal, {_metricas_sql('')}
                      FROM cardapio_eventos e
                     WHERE e.id_anuncio = %(a)s AND e.id_unidade = %(u)s {janela}
                     GROUP BY 1 ORDER BY 1""", p)  # noqa: S608
    por_canal = [dict(r) for r in cur.fetchall()]
    # 🔑 Em qual Cardápio Vivo (122): o mesmo anúncio na cafeteria e no catering.
    cur.execute(f"""SELECT e.id_catalogo, c.nome AS cardapio, {_metricas_sql('')}
                      FROM cardapio_eventos e LEFT JOIN catalogos c ON c.id = e.id_catalogo
                     WHERE e.id_anuncio = %(a)s AND e.id_unidade = %(u)s {janela}
                     GROUP BY 1, 2 ORDER BY 3 DESC""", p)  # noqa: S608
    por_cardapio = [dict(r) for r in cur.fetchall()]
    cur.execute(f"""SELECT extract(hour FROM e.quando AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
                           count(*) FILTER (WHERE e.tipo = 'viu_anuncio') AS aparicoes
                      FROM cardapio_eventos e
                     WHERE e.id_anuncio = %(a)s AND e.id_unidade = %(u)s {janela}
                     GROUP BY 1 ORDER BY 1""", p)  # noqa: S608
    por_hora = [dict(r) for r in cur.fetchall()]
    resumido = _somar_resumo(cur, id_unidade, id_anuncio, de, ate, total, por_dia, por_canal, por_cardapio)
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    sessoes = total["sessoes"] or 0
    return {
        "anuncio": a, "de": de, "ate": ate,
        "casa": e.get("nome_fantasia") or e.get("razao_social"),
        "total": total | {"taxa_toque": round(total["sessoes_tocaram"] / sessoes, 4) if sessoes else None,
                          "taxa_pulou": round(total["pulados"] / total["aparicoes"], 4) if total["aparicoes"] else None},
        "por_dia": por_dia, "por_canal": por_canal, "por_cardapio": por_cardapio,
        "por_hora": por_hora, "pulou_ms": PULOU_MS, "resumido": resumido,
        "variantes": _por_variante(cur, id_unidade, id_anuncio, de, ate),
    }


_SOMAVEIS = ("aparicoes", "sessoes", "pulados", "toques", "sessoes_tocaram")


def _juntar(alvo: dict, r: dict) -> None:
    """Soma uma linha do resumo (124) a uma linha de métricas do bruto."""
    vistas_antes = alvo.get("aparicoes") or 0
    seg_antes = float(alvo.get("segundos") or 0) * vistas_antes
    for c in _SOMAVEIS:
        alvo[c] = (alvo.get(c) or 0) + (r[c] or 0)
    alvo["segundos"] = (round((seg_antes + r["soma_ms"] / 1000) / alvo["aparicoes"], 1)
                        if alvo["aparicoes"] else None)


def _somar_resumo(cur, id_unidade: int, id_anuncio: int, de: date, ate: date, total: dict,
                  por_dia: list, por_canal: list, por_cardapio: list) -> dict | None:
    """Os dias do período que o bruto já não tem, lidos do resumo e somados às listas."""
    cur.execute("SELECT min(quando)::date AS desde FROM cardapio_eventos WHERE id_unidade = %s", (id_unidade,))
    desde = cur.fetchone()["desde"]
    corte = min(desde, ate + timedelta(days=1)) if desde else ate + timedelta(days=1)
    if de >= corte:
        return None
    cur.execute(
        """SELECT r.dia, r.canal, r.id_catalogo, c.nome AS cardapio, r.vistas AS aparicoes, r.sessoes,
                  r.soma_ms, r.pulados, r.cliques AS toques, r.sessoes_clicaram AS sessoes_tocaram
             FROM cardapio_conteudo_dia r LEFT JOIN catalogos c ON c.id = r.id_catalogo
            WHERE r.tipo = 'ANUNCIO' AND r.id_ref = %s AND r.id_unidade = %s
              AND r.dia >= %s AND r.dia < %s ORDER BY r.dia""",
        (id_anuncio, id_unidade, de, corte))
    linhas = [dict(r) for r in cur.fetchall()]
    if not linhas:
        return None
    dias: dict = {}
    for r in linhas:
        _juntar(total, r)
        _juntar(dias.setdefault(r["dia"], {"dia": r["dia"]}), r)
        canal = next((x for x in por_canal if x["canal"] == r["canal"]), None)
        if canal is None:
            canal = {"canal": r["canal"]}
            por_canal.append(canal)
        _juntar(canal, r)
        id_cat = r["id_catalogo"] or None
        cardapio = next((x for x in por_cardapio if x["id_catalogo"] == id_cat), None)
        if cardapio is None:
            cardapio = {"id_catalogo": id_cat, "cardapio": r["cardapio"]}
            por_cardapio.append(cardapio)
        _juntar(cardapio, r)
    por_dia[:0] = list(dias.values())
    por_cardapio.sort(key=lambda x: -(x.get("aparicoes") or 0))
    return {"ate": corte - timedelta(days=1), "dias": len(dias),
            "aviso": "Os dias até {} vêm do resumo diário: as pessoas são contadas por dia (quem "
                     "voltou noutro dia conta de novo) e não entram na distribuição por hora."
                     .format((corte - timedelta(days=1)).strftime("%d/%m/%Y"))}


# ------------------------------------------------------------------ o que o feed recebe

def do_feed(cur, id_unidade: int, id_catalogo: int, mesa: bool, idioma: str | None,
            agora: datetime | None = None, sessao: str | None = None) -> dict:
    """Os anúncios que valem AGORA neste Cardápio Vivo, e as regras de exibição da casa.

    🔑 Na mesa o teto é o da mesa (1, por padrão): quem está sentado quer achar o prato.
    ⚠️ O anúncio que leva a ESTE mesmo catálogo não aparece aqui (seria um convite para onde a
    pessoa já está).
    🔑 125: com a sessão anônima, a visita cai no **grupo de controle** (sem anúncio nenhum) ou no
    exposto, e cada anúncio com variações mostra a DELA. Sem sessão (quem recusou a medição, a
    prévia): exposto à original, e fora da comparação (`grupo` nulo).
    """
    from services.cardapio_vivo import _secao_visivel  # ⚠️ aqui dentro: aquele importa este
    agora = agora or agora_da_casa().replace(tzinfo=None)
    cur.execute("SELECT 1 FROM reserva_dias_especiais WHERE id_unidade = %s AND data = %s",
                (id_unidade, agora.date()))
    especial = cur.fetchone() is not None
    cur.execute(
        """SELECT a.*, v.slug AS acao_slug
             FROM cardapio_anuncios a
             LEFT JOIN cardapio_vivos v ON v.id_unidade = a.id_unidade AND v.id_catalogo = a.acao_catalogo
            WHERE a.id_unidade = %(u)s AND a.ativo
              AND (a.inicio IS NULL OR a.inicio <= %(hoje)s) AND (a.fim IS NULL OR a.fim >= %(hoje)s)
              AND (a.cardapios IS NULL OR %(c)s = ANY(a.cardapios))
              AND a.canal IN ('AMBOS', %(canal)s)
              AND (a.acao <> 'CATALOGO' OR a.acao_catalogo IS DISTINCT FROM %(c)s)
              AND (coalesce(btrim(a.titulo), '') <> '' OR coalesce(btrim(a.texto), '') <> ''
                   OR a.foto_url IS NOT NULL OR a.video_url IS NOT NULL)
            ORDER BY a.id""",
        {"u": id_unidade, "hoje": agora.date(), "c": id_catalogo, "canal": "MESA" if mesa else "LINK"})
    validos = [r for r in cur.fetchall()
               if _secao_visivel({"dias": r["dias"], "hora_de": r["hora_de"], "hora_ate": r["hora_ate"],
                                  "horario_especial": r["horario_especial"]}, agora, especial)]
    rg = regras(cur, id_unidade)
    grupo = None
    if sessao and validos:
        cur.execute(f"SELECT {SQL_CONTROLE.format(sessao='%s')} AS fatia", (sessao,))  # noqa: S608
        grupo = "CONTROLE" if cur.fetchone()["fatia"] < int(rg["anuncio_controle"] or 0) else "EXPOSTO"
        if grupo == "CONTROLE":
            validos = []
    variantes = _variantes_da_sessao(cur, [r["id"] for r in validos], sessao)
    anuncios = []
    for r in validos:
        v = variantes.get(r["id"])
        if r["video_url"]:
            midia = {"tipo": "VIDEO", "video": r["video_url"], "capa": r["video_capa_url"]}
        elif r["foto_url"]:
            midia = {"tipo": "FOTO", "foto": r["foto_url"]}
        else:
            midia = {"tipo": "NENHUMA"}
        texto = v or r
        acao = {"tipo": r["acao"], "rotulo": (v["acao_rotulo"] if v and v["acao_rotulo"] else r["acao_rotulo"]),
                "catalogo": r["acao_catalogo"], "slug": r["acao_slug"], "item": r["acao_item"], "url": r["acao_url"]}
        anuncios.append({
            "id": r["id"], "origem": r["origem"], "anunciante": r["anunciante"], "peso": r["peso"],
            "titulo": traducao.escolher(texto["titulo"], texto["titulo_en"], texto["titulo_de"], idioma),
            "texto": traducao.escolher(texto["texto"], texto["texto_en"], texto["texto_de"], idioma),
            "midia": midia, "acao": acao,
            # 125: a variação desta visita (nulo = a original) e as seções em que combina.
            "variante": v["id"] if v else None, "secoes": r["secoes"],
        })
    return {"anuncios": anuncios, "grupo_anuncio": grupo,
            "regras_anuncio": {"depois_de": rg["anuncio_depois_de"], "intervalo": rg["anuncio_intervalo"],
                               "maximo": rg["anuncio_maximo_mesa"] if mesa else rg["anuncio_maximo"],
                               "recuo": bool(rg["anuncio_recuo"])}}


def _variantes_da_sessao(cur, ids: list[int], sessao: str | None) -> dict[int, dict]:
    """A variação que ESTA visita vê de cada anúncio — ausente = a original.

    🔑 A original é uma das opções (posição 0): com uma variação, metade das visitas vê cada
    texto; com duas, um terço. A conta é do banco, a mesma da análise.
    """
    if not ids or not sessao:
        return {}
    cur.execute("""SELECT * FROM cardapio_anuncio_variantes
                    WHERE id_anuncio = ANY(%s) AND ativo ORDER BY id_anuncio, id""", (ids,))
    por_anuncio: dict[int, list[dict]] = {}
    for v in cur.fetchall():
        por_anuncio.setdefault(v["id_anuncio"], []).append(dict(v))
    saida = {}
    for id_anuncio, lista in por_anuncio.items():
        cur.execute(f"SELECT {SQL_VARIACAO.format(sessao='%s', anuncio='%s', total='%s')} AS pos",  # noqa: S608
                    (sessao, id_anuncio, len(lista) + 1))
        pos = cur.fetchone()["pos"]
        if pos:
            saida[id_anuncio] = lista[pos - 1]
    return saida


# ------------------------------------------------------------------ fase 3: as variações

_COLUNAS_VARIANTE = "id, id_anuncio, titulo, texto, acao_rotulo, ativo, criado_em"


def _variante(cur, id_unidade: int, id_variante: int) -> dict:
    cur.execute(f"""SELECT {', '.join('v.' + c.strip() for c in _COLUNAS_VARIANTE.split(','))}
                      FROM cardapio_anuncio_variantes v JOIN cardapio_anuncios a ON a.id = v.id_anuncio
                     WHERE v.id = %s AND a.id_unidade = %s""", (id_variante, id_unidade))  # noqa: S608
    achado = cur.fetchone()
    if not achado:
        raise HTTPException(status_code=404, detail="Variação não encontrada.")
    return dict(achado)


def variantes(cur, id_unidade: int, id_anuncio: int) -> list[dict]:
    _anuncio(cur, id_unidade, id_anuncio)
    cur.execute(f"SELECT {_COLUNAS_VARIANTE} FROM cardapio_anuncio_variantes WHERE id_anuncio = %s ORDER BY id",  # noqa: S608
                (id_anuncio,))
    return [dict(r) for r in cur.fetchall()]


def _conferir_variante(d: dict) -> None:
    if not (_texto(d.get("titulo")) or _texto(d.get("texto"))):
        raise HTTPException(status_code=422, detail="A variação precisa de um título ou de um texto.")


def criar_variante(cur, id_unidade: int, id_anuncio: int, dados: dict) -> dict:
    """⚠️ No máximo `MAX_VARIANTES` além da original: cada uma divide as visitas, e com pouca
    gente em cada braço o teste nunca conclui."""
    _anuncio(cur, id_unidade, id_anuncio)
    _conferir_variante(dados)
    cur.execute("SELECT count(*) AS n FROM cardapio_anuncio_variantes WHERE id_anuncio = %s", (id_anuncio,))
    if cur.fetchone()["n"] >= MAX_VARIANTES:
        raise HTTPException(status_code=422, detail=f"No máximo {MAX_VARIANTES} variações além da original — "
                                                    "cada uma divide as visitas, e o teste demora a concluir.")
    cur.execute("""INSERT INTO cardapio_anuncio_variantes (id_anuncio, titulo, texto, acao_rotulo, ativo)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (id_anuncio, _texto(dados.get("titulo")), _texto(dados.get("texto")),
                 _texto(dados.get("acao_rotulo")), dados.get("ativo", True)))
    nova = cur.fetchone()["id"]
    traducao.tentar(cur, "anuncio_variante", nova)
    return _variante(cur, id_unidade, nova)


def atualizar_variante(cur, id_unidade: int, id_variante: int, dados: dict) -> dict:
    _variante(cur, id_unidade, id_variante)
    _conferir_variante(dados)
    cur.execute("""UPDATE cardapio_anuncio_variantes SET titulo = %s, texto = %s, acao_rotulo = %s, ativo = %s
                    WHERE id = %s""",
                (_texto(dados.get("titulo")), _texto(dados.get("texto")), _texto(dados.get("acao_rotulo")),
                 dados.get("ativo", True), id_variante))
    traducao.tentar(cur, "anuncio_variante", id_variante)
    return _variante(cur, id_unidade, id_variante)


def remover_variante(cur, id_unidade: int, id_variante: int) -> dict:
    """⚠️ Os eventos ficam com o id (sem chave estrangeira): o relatório mostra "(apagada)"."""
    _variante(cur, id_unidade, id_variante)
    cur.execute("DELETE FROM cardapio_anuncio_variantes WHERE id = %s", (id_variante,))
    return {"message": "Variação removida."}


def aplicar_variante(cur, id_unidade: int, id_anuncio: int, id_variante: int | None) -> dict:
    """Leva o texto escolhido (normalmente o vencedor) ao anúncio e encerra o teste.

    🔑 Aplicar = o texto (e as traduções) da variação passa a ser o do anúncio, e TODAS as
    variações saem. `id_variante` nulo = fica a original. O relatório antigo continua: os eventos
    guardam o id da variação que cada visita viu.
    """
    _anuncio(cur, id_unidade, id_anuncio)
    if id_variante is not None:
        cur.execute("""SELECT * FROM cardapio_anuncio_variantes WHERE id = %s AND id_anuncio = %s""",
                    (id_variante, id_anuncio))
        v = cur.fetchone()
        if not v:
            raise HTTPException(status_code=404, detail="Variação não encontrada neste anúncio.")
        cur.execute("""UPDATE cardapio_anuncios
                          SET titulo = %s, texto = %s, acao_rotulo = coalesce(%s, acao_rotulo),
                              titulo_en = %s, titulo_de = %s, texto_en = %s, texto_de = %s,
                              traducao_editada = %s, traducao_origem = %s, traducao_em = %s
                        WHERE id = %s""",
                    (v["titulo"], v["texto"], v["acao_rotulo"], v["titulo_en"], v["titulo_de"],
                     v["texto_en"], v["texto_de"], v["traducao_editada"], v["traducao_origem"],
                     v["traducao_em"], id_anuncio))
    cur.execute("DELETE FROM cardapio_anuncio_variantes WHERE id_anuncio = %s", (id_anuncio,))
    return _anuncio(cur, id_unidade, id_anuncio) | {
        "message": "Texto vencedor aplicado; as variações saíram." if id_variante else
                   "Fica a original; as variações saíram."}


def _por_variante(cur, id_unidade: int, id_anuncio: int, de: date, ate: date) -> dict | None:
    """Os números de cada texto no período, e qual vence pela TAXA DE TOQUE.

    🔑 Exposta = a visita que VIU o anúncio naquela variação; tocou = tocou no botão. Cada
    variação é comparada com a original (o mesmo teste de duas proporções dos A/B, 116).
    ⚠️ Só o bruto: o resumo do dia (124) não separa por variação.
    """
    from services.cardapio_testes import MIN_POR_BRACO, _proporcoes  # ⚠️ aqui dentro: evita o ciclo
    cur.execute(
        """SELECT coalesce(e.id_variante, 0) AS variante,
                  count(DISTINCT e.id_sessao) FILTER (WHERE e.tipo = 'viu_anuncio') AS sessoes,
                  count(DISTINCT e.id_sessao) FILTER (WHERE e.tipo = 'clicou_anuncio') AS tocaram
             FROM cardapio_eventos e
            WHERE e.id_anuncio = %s AND e.id_unidade = %s
              AND e.quando >= %s::date AND e.quando < (%s::date + 1)
            GROUP BY 1""", (id_anuncio, id_unidade, de, ate))
    medidas = {r["variante"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, titulo, texto, ativo FROM cardapio_anuncio_variantes WHERE id_anuncio = %s ORDER BY id",
                (id_anuncio,))
    atuais = {r["id"]: dict(r) for r in cur.fetchall()}
    if not atuais and not any(k for k in medidas):
        return None
    a = _anuncio(cur, id_unidade, id_anuncio)
    base = medidas.get(0, {"sessoes": 0, "tocaram": 0})
    linhas = [{"id_variante": None, "rotulo": "Original", "titulo": a["titulo"], "texto": a["texto"],
               "sessoes": base["sessoes"], "tocaram": base["tocaram"],
               "taxa": round(base["tocaram"] / base["sessoes"], 4) if base["sessoes"] else None,
               "comparacao": None, "existe": True}]
    for n, idv in enumerate(sorted(set(atuais) | {k for k in medidas if k}), start=1):
        m = medidas.get(idv, {"sessoes": 0, "tocaram": 0})
        v = atuais.get(idv)
        comp = _proporcoes(base["sessoes"], base["tocaram"], m["sessoes"], m["tocaram"])
        linhas.append({"id_variante": idv, "rotulo": f"Variação {chr(65 + n)}",
                       "titulo": v["titulo"] if v else None, "texto": v["texto"] if v else None,
                       "sessoes": m["sessoes"], "tocaram": m["tocaram"],
                       "taxa": round(m["tocaram"] / m["sessoes"], 4) if m["sessoes"] else None,
                       "comparacao": {"p_valor": comp["p_valor"], "conclusao": comp["conclusao"]},
                       "existe": v is not None})
    # 🔑 A vencedora: a variação que bate a original com significância e tem a maior taxa. Sem
    # ninguém batendo e com amostra suficiente em todas, a original vence quando alguém PERDE dela.
    vencem = [l for l in linhas[1:] if l["existe"] and l["comparacao"]["conclusao"] == "B_VENCE"]
    perdem = [l for l in linhas[1:] if l["comparacao"]["conclusao"] == "A_VENCE"]
    if vencem:
        vencedora = max(vencem, key=lambda l: l["taxa"] or 0)["id_variante"]
        conclusao = "VARIACAO_VENCE"
    elif perdem and all(l["comparacao"]["conclusao"] != "AMOSTRA_PEQUENA" for l in linhas[1:]):
        vencedora, conclusao = None, "ORIGINAL_VENCE"
    elif any(l["comparacao"]["conclusao"] == "AMOSTRA_PEQUENA" for l in linhas[1:]):
        vencedora, conclusao = None, "AMOSTRA_PEQUENA"
    else:
        vencedora, conclusao = None, "SEM_DIFERENCA"
    return {"linhas": linhas, "vencedora": vencedora, "conclusao": conclusao,
            "minimo_por_braco": MIN_POR_BRACO, "em_teste": bool(atuais)}


# ------------------------------------------------------------------ fase 2: o efeito (grupo de controle)

def efeito(cur, id_unidade: int, de: date, ate: date) -> dict:
    """As visitas que NÃO viram anúncio (controle) × as que podiam ver (expostas), no período.

    🔑 É o que responde "os anúncios atrapalham quem está escolhendo o prato?": quantas visitas
    se envolveram com o cardápio e quantas adicionaram um prato, em cada grupo. O grupo vem
    GRAVADO no evento (125), então mudar o percentual não reescreve o passado.
    ⚠️ Exposta = podia ver: a visita que parou antes do 5º prato está no grupo sem ter visto.
    """
    from services.cardapio_testes import MIN_POR_BRACO, _proporcoes  # ⚠️ aqui dentro: evita o ciclo
    from services.cardapio_vivo import SQL_SESSAO_ENGAJADA
    if de > ate:
        raise HTTPException(status_code=422, detail="O período termina antes de começar.")
    cur.execute(
        f"""WITH s AS (
                SELECT id_sessao, max(grupo_anuncio) AS grupo, {SQL_SESSAO_ENGAJADA} AS engajada,
                       bool_or(tipo = 'adicionou') AS adicionou,
                       count(DISTINCT id_item) FILTER (WHERE tipo = 'viu_item') AS pratos
                  FROM cardapio_eventos
                 WHERE id_unidade = %s AND quando >= %s::date AND quando < (%s::date + 1)
                   AND grupo_anuncio IS NOT NULL
                 GROUP BY id_sessao)
            SELECT grupo, count(*) AS sessoes, count(*) FILTER (WHERE engajada) AS engajadas,
                   count(*) FILTER (WHERE adicionou) AS adicionaram,
                   round(avg(pratos), 1) AS pratos_por_sessao
              FROM s GROUP BY grupo""",  # noqa: S608 - a regra é constante do módulo
        (id_unidade, de, ate))
    g = {r["grupo"]: dict(r) for r in cur.fetchall()}
    vazio = {"sessoes": 0, "engajadas": 0, "adicionaram": 0, "pratos_por_sessao": None}
    ctl, exp = g.get("CONTROLE", vazio), g.get("EXPOSTO", vazio)
    adicao = _proporcoes(ctl["sessoes"], ctl["adicionaram"], exp["sessoes"], exp["adicionaram"])
    envolv = _proporcoes(ctl["sessoes"], ctl["engajadas"], exp["sessoes"], exp["engajadas"])
    return {"de": de, "ate": ate, "controle": ctl, "expostas": exp, "minimo_por_braco": MIN_POR_BRACO,
            "percentual": int(regras(cur, id_unidade)["anuncio_controle"]),
            # A/B na ordem (controle, expostas): "B_VENCE" = as expostas adicionaram MAIS.
            "adicao": {"p_valor": adicao["p_valor"], "conclusao": adicao["conclusao"]},
            "engajamento": {"p_valor": envolv["p_valor"], "conclusao": envolv["conclusao"]}}


def periodo_padrao() -> tuple[date, date]:
    hoje = agora_da_casa().date()
    return hoje - timedelta(days=29), hoje
