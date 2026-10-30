"""Cardápio Vivo — o cardápio da mesa como feed, e a atenção que cada prato recebe.

🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`. Fase 1:
acesso por mesa, feed com vídeo/foto, modo VITRINE com seleção, cadastro e eventos.

🔑 **Nada de cadastro novo de prato.** O feed é o catálogo de origem PRODUTOS que a
loja aponta em `cardapio_config` — as mesmas seções, itens, ordem, nome de vitrine,
foto e preço da loja que o site já mostra. Duas fontes para o mesmo cardápio
divergiriam caladas, e o cliente veria um preço na mesa e outro no site.

⚠️ **O feed é PÚBLICO.** Nada de custo, saldo ou id de produto: o item vai pelo id do
ITEM (como o carrinho do 101), e o evento descobre o produto no servidor.
"""

import re
import secrets
import unicodedata
import time as _tempo
from collections import deque
from datetime import datetime, time, timedelta

from fastapi import HTTPException

from relogio import agora_da_casa
from services import cardapio_anuncios as catalogo_anuncios
from services import catalogo_cartoes
from services import catalogo_conteudo
from services import reservas as reservas_servico
from services import traducao

MODOS = ("VITRINE", "PEDIDO")
FONTES = ("FRAUNCES", "NEWSREADER", "PLAYFAIR", "LORA", "CORMORANT")
RESTRICOES = {"VEGANO": "Vegano", "SEM_GLUTEN": "Sem glúten", "SEM_LACTOSE": "Sem lactose"}
DISPOSITIVOS = ("CELULAR", "TABLET", "DESKTOP", "OUTRO")
TIPOS_EVENTO = ("abriu_cardapio", "viu_item", "tocou_categoria", "abriu_detalhe",
                "adicionou", "removeu", "enviou_pedido", "chamou_garcom", "pediu_conta", "saiu",
                # O complemento do dono (114).
                "deslizou_frente", "deslizou_tras", "favoritou", "desfavoritou",
                "abriu_personalizacao", "escolheu_opcao", "abriu_hub", "clicou_avaliacao",
                "clicou_wifi")

# 🔑 **"Atenção estimada"**: o tempo VISÍVEL na tela, com teto de 60 s por visualização —
# acima disso é tela esquecida aberta na mesa, não atenção. Não é rastreamento ocular nem
# intenção de compra. O bruto guarda o tempo medido; o teto vale em toda soma.
ATENCAO_MAX_MS = 60_000
MIDIAS = ("VIDEO", "FOTO", "NENHUMA")

# 🔑 O modo PEDIDO chegou na fase 2 (migração 115): carrinho, coluna Mesas no painel e
# chamados. A tupla continua existindo para o dia de um terceiro modo.
MODOS_LIBERADOS = ("VITRINE", "PEDIDO")

# 🔑 **O que é da CASA** (117): a aparência do site inteiro, o Hub, esconder esgotado e a
# retenção. Decisão do dono (15/10/2026): um layout só — o catering não pode ter cara de
# outro lugar. O comportamento de cada cardápio mora em `cardapio_vivos`.
_PADRAO = {
    "esconder_esgotado": False, "cor_principal": None, "cor_fundo": None,
    "fonte": "FRAUNCES", "logo_url": None, "retencao_meses": 13,
    "hub_avaliacao": False, "hub_wifi": False,
}

# O comportamento de UM Cardápio Vivo (117).
_VIVO_PADRAO = {
    "slug": None, "principal": False, "modo": "VITRINE", "exige_confirmacao": True,
    "pedido_hora_de": None, "pedido_hora_ate": None, "chamar_garcom": False,
    # 119: na vitrine, False = só consulta (sem "minha seleção").
    "selecao": True,
    # 121: AUTOMATICA (seção com foto ou vídeo abre), SO_VIDEO ou NUNCA.
    "aberturas": "AUTOMATICA",
}
_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


# ---------------------------------------------------------------------------
# Configuração da casa, os Cardápios Vivos e as exceções
# ---------------------------------------------------------------------------

def config(cur, id_unidade: int) -> dict:
    """A configuração da casa — com o padrão quando ela nunca foi gravada.

    ⚠️ `id_catalogo` aqui é o do Cardápio Vivo PRINCIPAL, calculado: o painel de atenção e
    os testes A/B olham o cardápio da mesa, como antes da 117. A coluna antiga de
    `cardapio_config` não é mais lida.
    """
    cur.execute("SELECT * FROM cardapio_config WHERE id_unidade = %s", (id_unidade,))
    linha = dict(cur.fetchone() or {})
    cfg = dict(_PADRAO) | {k: v for k, v in linha.items() if k in _PADRAO}
    cfg["id_unidade"] = id_unidade
    principal = vivo(cur, id_unidade)
    cfg["id_catalogo"] = principal["id_catalogo"] if principal else None
    return cfg


def salvar_config(cur, id_unidade: int, dados: dict, id_usuario: int | None) -> dict:
    if dados.get("fonte") not in FONTES:
        raise HTTPException(status_code=422, detail="Fonte desconhecida.")
    campos = [c for c in _PADRAO if c != "logo_url"]
    valores = [dados.get(c, _PADRAO[c]) for c in campos]
    cur.execute(
        f"""INSERT INTO cardapio_config (id_unidade, {', '.join(campos)}, atualizado_por)
            VALUES (%s, {', '.join(['%s'] * len(campos))}, %s)
            ON CONFLICT (id_unidade) DO UPDATE SET
              {', '.join(f'{c} = EXCLUDED.{c}' for c in campos)},
              atualizado_por = EXCLUDED.atualizado_por, atualizado_em = now()""",  # noqa: S608
        [id_unidade, *valores, id_usuario],
    )
    return config(cur, id_unidade)


_SQL_VIVO = """SELECT v.id_unidade, v.id_catalogo, v.slug, v.principal, v.modo,
                      v.exige_confirmacao, v.pedido_hora_de, v.pedido_hora_ate,
                      v.chamar_garcom, v.selecao, v.aberturas, c.nome, c.situacao
                 FROM cardapio_vivos v JOIN catalogos c ON c.id = v.id_catalogo
                WHERE v.id_unidade = %s"""


def vivos(cur, id_unidade: int) -> list[dict]:
    """Os Cardápios Vivos da loja: o principal primeiro, depois pelo nome."""
    cur.execute(_SQL_VIVO + " ORDER BY v.principal DESC, lower(c.nome)", (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def vivo(cur, id_unidade: int, slug: str | None = None,
         id_catalogo: int | None = None) -> dict | None:
    """Um Cardápio Vivo da loja: pelo nome no link, pelo catálogo, ou o PRINCIPAL."""
    if slug:
        cur.execute(_SQL_VIVO + " AND v.slug = %s", (id_unidade, slug))
    elif id_catalogo:
        cur.execute(_SQL_VIVO + " AND v.id_catalogo = %s", (id_unidade, id_catalogo))
    else:
        cur.execute(_SQL_VIVO + " AND v.principal", (id_unidade,))
    linha = cur.fetchone()
    return dict(linha) if linha else None


def sugerir_slug(nome: str) -> str:
    """"Catering da Cafeteria" vira "catering-da-cafeteria": sem acento, minúsculas e hífen."""
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40].strip("-") or "cardapio"


def salvar_vivo(cur, id_unidade: int, id_catalogo: int, dados: dict, id_usuario: int | None) -> dict:
    """Liga (ou regrava) um catálogo como Cardápio Vivo da loja.

    🔑 **O primeiro da loja nasce PRINCIPAL**: sem principal o QR da mesa não abre nada, e
    quem liga o primeiro cardápio espera que a mesa já o mostre.
    🔑 **Marcar um como principal desmarca o outro** — um por loja; o índice único garante.
    """
    cur.execute(
        """SELECT c.nome, c.origem FROM catalogos c
            WHERE c.id = %s AND EXISTS (SELECT 1 FROM catalogo_lojas l
                                         WHERE l.id_catalogo = c.id AND l.id_unidade = %s)""",
        (id_catalogo, id_unidade))
    cat = cur.fetchone()
    if not cat:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado nesta loja.")
    if cat["origem"] != "PRODUTOS":
        raise HTTPException(status_code=409,
                            detail="O Cardápio Vivo monta o feed item a item: escolha um "
                                   "catálogo de origem PRODUTOS, não um PDF.")
    if dados.get("modo", "VITRINE") not in MODOS_LIBERADOS:
        raise HTTPException(status_code=422, detail="Modo desconhecido.")
    atual = vivo(cur, id_unidade, id_catalogo=id_catalogo)
    slug = (dados.get("slug") or (atual or {}).get("slug") or sugerir_slug(cat["nome"])).strip().lower()
    if len(slug) > 40 or not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=422,
                            detail="O nome no link usa só letras minúsculas sem acento, números e "
                                   "hífen — como “catering” ou “cafe-da-manha”.")
    cur.execute("""SELECT c.nome FROM cardapio_vivos v JOIN catalogos c ON c.id = v.id_catalogo
                    WHERE v.id_unidade = %s AND v.slug = %s AND v.id_catalogo <> %s""",
                (id_unidade, slug, id_catalogo))
    outro = cur.fetchone()
    if outro:
        raise HTTPException(status_code=409,
                            detail=f"O link “{slug}” já é do Cardápio Vivo “{outro['nome']}”.")
    cur.execute("SELECT count(*) AS n FROM cardapio_vivos WHERE id_unidade = %s AND id_catalogo <> %s",
                (id_unidade, id_catalogo))
    primeiro = cur.fetchone()["n"] == 0
    principal = True if primeiro else bool(dados.get("principal", (atual or {}).get("principal", False)))
    campos = {k: dados.get(k, _VIVO_PADRAO[k]) for k in _VIVO_PADRAO if k not in ("slug", "principal")}
    if (campos["pedido_hora_de"] is None) != (campos["pedido_hora_ate"] is None):
        raise HTTPException(status_code=422,
                            detail="Informe as duas pontas do horário do pedido, ou nenhuma.")
    if principal:
        cur.execute("UPDATE cardapio_vivos SET principal = false WHERE id_unidade = %s AND principal "
                    "AND id_catalogo <> %s", (id_unidade, id_catalogo))
    cur.execute(
        """INSERT INTO cardapio_vivos (id_unidade, id_catalogo, slug, principal, modo,
                                       exige_confirmacao, pedido_hora_de, pedido_hora_ate,
                                       chamar_garcom, selecao, aberturas, atualizado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id_unidade, id_catalogo) DO UPDATE SET
             slug = EXCLUDED.slug, principal = EXCLUDED.principal, modo = EXCLUDED.modo,
             exige_confirmacao = EXCLUDED.exige_confirmacao,
             pedido_hora_de = EXCLUDED.pedido_hora_de, pedido_hora_ate = EXCLUDED.pedido_hora_ate,
             chamar_garcom = EXCLUDED.chamar_garcom, selecao = EXCLUDED.selecao,
             aberturas = EXCLUDED.aberturas,
             atualizado_por = EXCLUDED.atualizado_por,
             atualizado_em = now()""",
        (id_unidade, id_catalogo, slug, principal, campos["modo"], campos["exige_confirmacao"],
         campos["pedido_hora_de"], campos["pedido_hora_ate"], campos["chamar_garcom"],
         bool(campos["selecao"]), campos["aberturas"], id_usuario))
    return vivo(cur, id_unidade, id_catalogo=id_catalogo) | {"antes": atual}


def remover_vivo(cur, id_unidade: int, id_catalogo: int) -> dict:
    """Desliga o catálogo como Cardápio Vivo. O catálogo continua; o link deixa de abrir.

    ⚠️ Tirar o PRINCIPAL deixa a mesa sem cardápio — a frase diz, para a casa marcar outro.
    """
    atual = vivo(cur, id_unidade, id_catalogo=id_catalogo)
    if not atual:
        raise HTTPException(status_code=404, detail="Este catálogo não é um Cardápio Vivo da loja.")
    cur.execute("DELETE FROM cardapio_vivos WHERE id_unidade = %s AND id_catalogo = %s",
                (id_unidade, id_catalogo))
    msg = f"“{atual['nome']}” deixou de ser Cardápio Vivo."
    if atual["principal"]:
        msg += " Era o principal: a mesa fica sem cardápio até outro ser marcado como principal."
    return {"message": msg, "antes": atual}


def listar_excecoes(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT e.id, e.id_salao, e.id_mesa, e.modo, e.exige_confirmacao,
                  e.pedido_hora_de, e.pedido_hora_ate,
                  coalesce(s.nome, sm.nome) AS salao, m.nome AS mesa
             FROM cardapio_excecoes e
             LEFT JOIN saloes s ON s.id = e.id_salao
             LEFT JOIN mesas m ON m.id = e.id_mesa
             LEFT JOIN saloes sm ON sm.id = m.id_salao
            WHERE e.id_unidade = %s
            ORDER BY coalesce(s.nome, sm.nome), m.nome NULLS FIRST""",
        (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def salvar_excecao(cur, id_unidade: int, dados: dict) -> dict:
    """Grava a exceção de um salão OU de uma mesa (uma por alvo: regrava a existente)."""
    id_salao, id_mesa = dados.get("id_salao"), dados.get("id_mesa")
    if bool(id_salao) == bool(id_mesa):
        raise HTTPException(status_code=422, detail="A exceção é de um salão OU de uma mesa.")
    if dados.get("modo") and dados["modo"] not in MODOS_LIBERADOS:
        raise HTTPException(status_code=409,
                            detail="O modo PEDIDO chega na fase 2. Por enquanto, só VITRINE.")
    tabela, alvo = ("saloes", id_salao) if id_salao else ("mesas", id_mesa)
    cur.execute(f"SELECT 1 FROM {tabela} WHERE id = %s AND id_unidade = %s",  # noqa: S608
                (alvo, id_unidade))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Salão ou mesa não encontrado nesta loja.")
    coluna = "id_salao" if id_salao else "id_mesa"
    cur.execute(f"DELETE FROM cardapio_excecoes WHERE {coluna} = %s", (alvo,))  # noqa: S608
    cur.execute(
        """INSERT INTO cardapio_excecoes (id_unidade, id_salao, id_mesa, modo,
                                          exige_confirmacao, pedido_hora_de, pedido_hora_ate)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, id_salao, id_mesa, dados.get("modo"), dados.get("exige_confirmacao"),
         dados.get("pedido_hora_de"), dados.get("pedido_hora_ate")))
    return {"id": cur.fetchone()["id"], "message": "Exceção gravada."}


def excluir_excecao(cur, id_unidade: int, id_excecao: int) -> dict:
    cur.execute("DELETE FROM cardapio_excecoes WHERE id = %s AND id_unidade = %s RETURNING id",
                (id_excecao, id_unidade))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Exceção não encontrada.")
    return {"message": "Exceção removida — vale a regra da loja."}


def _na_faixa(agora: time, de: time | None, ate: time | None) -> bool:
    """Se a hora está na faixa. ⚠️ A faixa pode virar a meia-noite (22:00 → 02:00)."""
    if de is None or ate is None:
        return True
    if de < ate:
        return de <= agora < ate
    return agora >= de or agora < ate


def modo_efetivo(cur, id_unidade: int, id_mesa: int | None, agora: datetime | None = None,
                 cv: dict | None = None) -> dict:
    """O modo que vale AGORA para esta mesa: loja ← salão ← mesa, e o horário do pedido.

    🔑 **A mais específica vence**, campo a campo: uma exceção de mesa que só diz
    o modo herda o horário do salão ou da loja.
    ⚠️ Fora do horário do pedido, cai para VITRINE com o aviso "pedidos com o garçom" —
    o cardápio continua abrindo; o que fecha é o envio.
    """
    # 🔑 O comportamento é do Cardápio Vivo aberto (117); sem nenhum, o da mesa — o principal.
    cv = cv if cv is not None else (vivo(cur, id_unidade) or dict(_VIVO_PADRAO))
    efetivo = {k: cv[k] for k in ("modo", "exige_confirmacao", "pedido_hora_de", "pedido_hora_ate")}
    if id_mesa:
        cur.execute(
            """SELECT e.* FROM cardapio_excecoes e
                 JOIN mesas m ON m.id = %s
                WHERE e.id_unidade = %s AND (e.id_salao = m.id_salao OR e.id_mesa = m.id)
                ORDER BY e.id_mesa NULLS FIRST""",  # o salão primeiro, a mesa por cima
            (id_mesa, id_unidade))
        for exc in cur.fetchall():
            for k in ("modo", "exige_confirmacao"):
                if exc[k] is not None:
                    efetivo[k] = exc[k]
            if exc["pedido_hora_de"] is not None:
                efetivo["pedido_hora_de"] = exc["pedido_hora_de"]
                efetivo["pedido_hora_ate"] = exc["pedido_hora_ate"]
    efetivo["aviso"] = None
    # ⚠️ **Sem mesa não há pedido**: a URL da loja (vitrine, balcão) não diz para onde levar.
    if not id_mesa:
        efetivo["modo"] = "VITRINE"
        return efetivo
    agora = agora or agora_da_casa().replace(tzinfo=None)
    if efetivo["modo"] == "PEDIDO" and not _na_faixa(
            agora.time(), efetivo["pedido_hora_de"], efetivo["pedido_hora_ate"]):
        efetivo["modo"] = "VITRINE"
        efetivo["aviso"] = "Pedidos com o garçom."
    return efetivo


# ---------------------------------------------------------------------------
# Mesa: o token do QR
# ---------------------------------------------------------------------------

def mesa_por_token(cur, token: str) -> dict | None:
    cur.execute(
        """SELECT m.id, m.id_unidade, m.nome, s.nome AS salao, m.id_salao
             FROM mesas m JOIN saloes s ON s.id = m.id_salao
            WHERE m.token = %s AND m.ativo""",
        (token,))
    linha = cur.fetchone()
    return dict(linha) if linha else None


def novo_token(cur, id_unidade: int, id_mesa: int) -> str:
    """Troca o segredo da mesa. ⚠️ O QR impresso antes deixa de abrir — é o objetivo."""
    token = secrets.token_hex(8)
    cur.execute("UPDATE mesas SET token = %s WHERE id = %s AND id_unidade = %s RETURNING id",
                (token, id_mesa, id_unidade))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Mesa não encontrada.")
    return token


def mesas_com_acesso(cur, id_unidade: int, web_url: str) -> list[dict]:
    cur.execute(
        """SELECT m.id, m.nome, m.token, m.ativo, s.id AS id_salao, s.nome AS salao
             FROM mesas m JOIN saloes s ON s.id = m.id_salao
            WHERE m.id_unidade = %s
            ORDER BY s.nome, length(m.nome), m.nome""",
        (id_unidade,))
    return [dict(r) | {"link": link_da_mesa(web_url, id_unidade, r["token"])}
            for r in cur.fetchall()]


def link_da_mesa(web_url: str, id_unidade: int, token: str) -> str:
    return f"{web_url.rstrip('/')}/c/{id_unidade}/{token}"


def link_da_loja(web_url: str, id_unidade: int, slug: str | None = None) -> str:
    """O link sem mesa: o principal em `/c/{loja}`, os outros com `?cardapio=`."""
    base = f"{web_url.rstrip('/')}/c/{id_unidade}"
    return f"{base}?cardapio={slug}" if slug else base


# ---------------------------------------------------------------------------
# O feed
# ---------------------------------------------------------------------------

def _secao_visivel(sec: dict, agora: datetime, dia_especial: bool) -> bool:
    """A seção aparece AGORA? Dia da semana, faixa de horário e dia especial.

    🔑 "Sábados e Feriados": dias = [6] com `horario_especial` — aparece no sábado e em
    todo dia que a casa marcou com horário especial nas Reservas.
    """
    dias = sec.get("dias")
    no_dia = (not dias) or (agora.isoweekday() in dias) or (dia_especial and sec.get("horario_especial"))
    return no_dia and _na_faixa(agora.time(), sec.get("hora_de"), sec.get("hora_ate"))


def _preco_sql(alias_produto: str) -> str:
    """A cascata do preço (loja → casa), a MESMA de `publico._montar_cardapio`."""
    return f"""(SELECT pr.preco_venda FROM produto_precos pr
                 WHERE pr.id_produto = {alias_produto}.id AND pr.vigente_ate IS NULL
                   AND (pr.id_unidade = %(u)s OR pr.id_unidade IS NULL)
                 ORDER BY pr.id_unidade NULLS LAST LIMIT 1)"""


def feed(cur, id_unidade: int, id_catalogo: int, idioma: str | None = None,
         agora: datetime | None = None, esconder_esgotado: bool = False,
         previa: bool = False, foto_forcada: set[int] | None = None) -> dict:
    """As seções e os itens do feed, na ordem do cardápio.

    🔑 **Mídia por item: vídeo → foto do item → foto da subcategoria → da categoria.**
    O servidor resolve e diz qual saiu (`midia.tipo`), porque é esse o tipo que o evento
    registra — a tela não precisa repetir a regra.
    ⚠️ `previa` (a pré-visualização do cadastro) mostra também as seções fora do dia e
    do horário, marcadas: quem monta o cardápio de sábado numa terça precisa vê-lo.
    """
    agora = agora or agora_da_casa().replace(tzinfo=None)
    cur.execute("SELECT 1 FROM reserva_dias_especiais WHERE id_unidade = %s AND data = %s",
                (id_unidade, agora.date()))
    especial = cur.fetchone() is not None

    cur.execute(
        f"""SELECT g.id AS id_categoria, g.nome AS categoria, g.nome_en AS categoria_en,
                   g.nome_de AS categoria_de, g.descricao AS categoria_descricao,
                   g.descricao_en AS categoria_descricao_en, g.descricao_de AS categoria_descricao_de,
                   g.foto_url AS categoria_foto, g.video_url AS categoria_video,
                   g.video_capa_url AS categoria_capa, g.abertura AS categoria_abertura,
                   g.dias AS g_dias, g.hora_de AS g_de,
                   g.hora_ate AS g_ate, g.horario_especial AS g_especial,
                   s.id AS id_subcategoria, s.nome AS subcategoria, s.nome_en AS subcategoria_en,
                   s.nome_de AS subcategoria_de, s.descricao AS subcategoria_descricao,
                   s.descricao_en AS subcategoria_descricao_en,
                   s.descricao_de AS subcategoria_descricao_de,
                   s.foto_url AS subcategoria_foto, s.video_url AS subcategoria_video,
                   s.video_capa_url AS subcategoria_capa, s.abertura AS subcategoria_abertura,
                   s.dias AS s_dias, s.hora_de AS s_de,
                   s.hora_ate AS s_ate, s.horario_especial AS s_especial,
                   -- 🔑 123: o esgotado com hora para voltar deixa de valer sozinho.
                   i.id AS id_item, i.destaque, (i.esgotado AND (i.esgotado_ate IS NULL OR i.esgotado_ate > now())) AS esgotado, i.midia_preferida, p.id AS id_produto,
                   -- 🔑 142: o item de ESCOLHA não tem produto — nome, descrição e foto são
                   -- dele; o preço e os adicionais vêm das opções, logo abaixo.
                   i.tipo,
                   coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome, i.nome) AS produto,
                   CASE WHEN i.tipo = 'ESCOLHA' THEN i.nome_en ELSE p.nome_catalogo_en END AS produto_en,
                   CASE WHEN i.tipo = 'ESCOLHA' THEN i.nome_de ELSE p.nome_catalogo_de END AS produto_de,
                   CASE WHEN i.tipo = 'ESCOLHA' THEN i.descricao ELSE p.informacao_adicional END
                       AS informacao_adicional,
                   CASE WHEN i.tipo = 'ESCOLHA' THEN i.descricao_en ELSE p.informacao_adicional_en END
                       AS informacao_en,
                   CASE WHEN i.tipo = 'ESCOLHA' THEN i.descricao_de ELSE p.informacao_adicional_de END
                       AS informacao_de,
                   coalesce(i.foto_url, p.foto_url) AS foto_url, p.video_url, p.video_capa_url,
                   coalesce(p.restricoes, '{{}}') AS restricoes,
                   {_preco_sql('p')} AS preco
              FROM catalogo_itens i
              JOIN catalogo_categorias g ON g.id = i.id_categoria
              LEFT JOIN catalogo_subcategorias s ON s.id = i.id_subcategoria
              LEFT JOIN produtos p ON p.id = i.id_produto
             WHERE g.id_catalogo = %(c)s AND (p.ativo OR i.tipo = 'ESCOLHA')
             ORDER BY g.ordem, lower(g.nome), s.ordem NULLS FIRST, lower(s.nome),
                      i.ordem, lower(coalesce(p.nome, i.nome))""",  # noqa: S608 - o SQL do preço é fixo
        {"c": id_catalogo, "u": id_unidade})
    linhas = [dict(r) for r in cur.fetchall()]

    def t(l: dict, campo: str, fonte: str | None = None) -> str | None:
        fonte = fonte or campo
        return traducao.escolher(l[campo], l.get(f"{fonte}_en"), l.get(f"{fonte}_de"), idioma)

    # 🔑 142: as opções de cada item de escolha — só as ATIVAS, com o preço vigente. Item de
    # escolha sem opção que se possa pedir não aparece (seria um cartão sem saída).
    escolhas = {k: [o for o in v if o["ativo"]] for k, v in catalogo_conteudo.opcoes_de_escolha(
        cur, id_unidade, [l["id_item"] for l in linhas if l["tipo"] == "ESCOLHA"]).items()}
    linhas = [l for l in linhas if l["tipo"] != "ESCOLHA" or escolhas.get(l["id_item"])]
    produtos = sorted({l["id_produto"] for l in linhas if l["id_produto"]}
                      | {o["id_produto"] for v in escolhas.values() for o in v})
    adicionais = _adicionais(cur, id_unidade, produtos)

    categorias: list[dict] = []
    por_cat: dict[int, dict] = {}
    vistas_sub: set[int] = set()
    itens: list[dict] = []
    for l in linhas:
        cat_vis = _secao_visivel({"dias": l["g_dias"], "hora_de": l["g_de"], "hora_ate": l["g_ate"],
                                  "horario_especial": l["g_especial"]}, agora, especial)
        sub_vis = l["id_subcategoria"] is None or _secao_visivel(
            {"dias": l["s_dias"], "hora_de": l["s_de"], "hora_ate": l["s_ate"],
             "horario_especial": l["s_especial"]}, agora, especial)
        fora = not (cat_vis and sub_vis)
        if fora and not previa:
            continue
        if l["esgotado"] and esconder_esgotado and not previa:
            continue

        cat = por_cat.get(l["id_categoria"])
        if cat is None:
            cat = {"id": l["id_categoria"], "nome": t(l, "categoria"),
                   "descricao": t(l, "categoria_descricao"), "foto": l["categoria_foto"],
                   # 🔑 120: a abertura automática da seção mostra o vídeo, se houver.
                   "video": l["categoria_video"], "capa": l["categoria_capa"],
                   "abertura": l["categoria_abertura"],
                   "fora_do_horario": not cat_vis, "subcategorias": []}
            por_cat[l["id_categoria"]] = cat
            categorias.append(cat)
        if l["id_subcategoria"] and l["id_subcategoria"] not in vistas_sub:
            vistas_sub.add(l["id_subcategoria"])
            cat["subcategorias"].append({
                "id": l["id_subcategoria"], "nome": t(l, "subcategoria"),
                "descricao": t(l, "subcategoria_descricao"), "foto": l["subcategoria_foto"],
                "video": l["subcategoria_video"], "capa": l["subcategoria_capa"],
                "abertura": l["subcategoria_abertura"],
                "fora_do_horario": not sub_vis})

        # 🔑 Fase 3 (116): a FOTO ganha do vídeo quando a casa aplicou esse vencedor
        # (`midia_preferida`) ou quando esta sessão caiu no braço "foto" de um teste A/B.
        usa_foto = l["midia_preferida"] == "FOTO" or l["id_produto"] in (foto_forcada or set())
        if l["video_url"] and not (usa_foto and l["foto_url"]):
            midia = {"tipo": "VIDEO", "video": l["video_url"],
                     "capa": l["video_capa_url"] or l["foto_url"]}
        else:
            foto = l["foto_url"] or l["subcategoria_foto"] or l["categoria_foto"]
            midia = {"tipo": "FOTO" if foto else "NENHUMA", "foto": foto,
                     # 🔑 Diz DE ONDE veio a foto: o aviso "sem foto e sem vídeo" do
                     # cadastro olha o próprio item, não a foto emprestada da seção.
                     "herdada": bool(foto) and not l["foto_url"]}
        opcoes = None
        preco = float(l["preco"]) if l["preco"] is not None else None
        if l["tipo"] == "ESCOLHA":
            opcoes = [{"id_produto": o["id_produto"],
                       "nome": traducao.escolher(o["rotulo"], o["rotulo_en"], o["rotulo_de"], idioma)
                       if o["rotulo"] else traducao.escolher(o["vitrine"], o["nome_catalogo_en"],
                                                             o["nome_catalogo_de"], idioma),
                       "preco": float(o["preco"]) if o["preco"] is not None else None,
                       "adicionais": adicionais.get(o["id_produto"], [])}
                      for o in escolhas[l["id_item"]]]
            # "A partir de": o menor preço das opções. Sem nenhum preço, sem preço.
            precos = [o["preco"] for o in opcoes if o["preco"] is not None]
            preco = min(precos) if precos else None
        itens.append({
            "id": l["id_item"], "id_categoria": l["id_categoria"],
            "id_subcategoria": l["id_subcategoria"],
            "nome": t(l, "produto"), "descricao": t(l, "informacao_adicional", "informacao"),
            # ⚠️ `float`: o JSON não fala decimal. Sem preço sai SEM preço, nunca zero.
            "preco": preco,
            "restricoes": list(l["restricoes"] or []),
            "destaque": l["destaque"], "esgotado": l["esgotado"],
            "fora_do_horario": fora, "midia": midia,
            "adicionais": adicionais.get(l["id_produto"], []) if l["id_produto"] else [],
            # 🔑 142: nulo = prato comum; lista = o cliente escolhe UMA antes de seguir.
            "escolhas": opcoes,
        })
    return {"categorias": categorias, "itens": itens,
            "restricoes": [{"chave": k, "nome": v} for k, v in RESTRICOES.items()]}


def _adicionais(cur, id_unidade: int, produtos: list[int]) -> dict[int, list[dict]]:
    """Os grupos de adicionais de cada produto, com o preço resolvido."""
    if not produtos:
        return {}
    cur.execute(
        f"""SELECT g.id_produto, g.id AS id_grupo, g.nome AS grupo, g.minimo, g.maximo,
                   g.permite_repetir, o.id, o.nome, o.id_produto_ref,
                   -- 🔑 142: "incluso" entra por R$ 0 mesmo apontando para um produto.
                   CASE WHEN o.incluso THEN 0
                        WHEN o.id_produto_ref IS NOT NULL THEN {_preco_sql('r')}
                        ELSE o.preco END AS preco
              FROM produto_adicionais_grupos g
              JOIN produto_adicionais_opcoes o ON o.id_grupo = g.id AND o.ativo
              LEFT JOIN produtos r ON r.id = o.id_produto_ref
             WHERE g.id_produto = ANY(%(p)s)
             ORDER BY g.ordem, g.id, o.ordem, o.id""",  # noqa: S608
        {"p": produtos, "u": id_unidade})
    saida: dict[int, list[dict]] = {}
    grupos: dict[int, dict] = {}
    for r in cur.fetchall():
        g = grupos.get(r["id_grupo"])
        if g is None:
            g = {"id": r["id_grupo"], "nome": r["grupo"], "minimo": r["minimo"],
                 "maximo": r["maximo"], "permite_repetir": r["permite_repetir"], "opcoes": []}
            grupos[r["id_grupo"]] = g
            saida.setdefault(r["id_produto"], []).append(g)
        g["opcoes"].append({"id": r["id"], "nome": r["nome"],
                            "preco": float(r["preco"]) if r["preco"] is not None else None})
    return saida


def cardapio_publico(cur, id_unidade: int, mesa: dict | None, idioma: str | None,
                     previa_catalogo: int | None = None, sessao: str | None = None,
                     slug: str | None = None, previa_anuncios: bool = False) -> dict:
    """Tudo que a tela do cliente precisa numa resposta: casa, marca, modo e feed.

    ⚠️ **404 quando a loja não ligou o Cardápio Vivo** (sem catálogo apontado): para o
    público, o cardápio da mesa simplesmente não existe ainda.
    """
    cur.execute("""SELECT id, coalesce(nullif(apelido, ''), nome) AS nome,
                          nullif(btrim(google_avaliacao_url), '') AS avaliacao,
                          nullif(btrim(wifi_rede), '') AS wifi_rede, wifi_senha
                     FROM unidades WHERE id = %s AND ativo""", (id_unidade,))
    loja = cur.fetchone()
    if not loja or not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
    cfg = config(cur, id_unidade)
    # 🔑 **Qual Cardápio Vivo** (117): a mesa abre o PRINCIPAL; o link sem mesa abre o do
    # `?cardapio=` (o catering), ou o principal. A prévia usa o do catálogo, se houver.
    if previa_catalogo:
        cv = vivo(cur, id_unidade, id_catalogo=previa_catalogo) or dict(_VIVO_PADRAO)
    else:
        cv = vivo(cur, id_unidade) if mesa else vivo(cur, id_unidade, slug=slug)
        if not cv:
            raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
    id_catalogo = previa_catalogo or cv["id_catalogo"]
    cur.execute("""SELECT nome, nome_en, nome_de, situacao FROM catalogos
                    WHERE id = %s AND origem = 'PRODUTOS'""", (id_catalogo,))
    capa = cur.fetchone()
    # ⚠️ O catálogo apontado precisa estar ATIVO — rascunho não vai à mesa. A prévia
    # do cadastro é a exceção: ela serve justamente para conferir antes de ativar.
    if not capa or (capa["situacao"] != "ATIVO" and not previa_catalogo):
        raise HTTPException(status_code=404, detail="Cardápio não encontrado.")

    cur.execute("SELECT nome_fantasia, razao_social, logo_url FROM empresa WHERE id = 1")
    empresa = cur.fetchone() or {}
    modo = modo_efetivo(cur, id_unidade, mesa["id"] if mesa else None, cv=cv)
    # 🔑 Os testes A/B (116): a variante sai do id anônimo da sessão, numa conta do banco.
    # ⚠️ A prévia do cadastro não entra em teste nenhum — mostra o cardápio da casa.
    from services import cardapio_testes
    var = (cardapio_testes.variantes(cur, id_unidade, id_catalogo, sessao)
           if sessao and not previa_catalogo else {"foto": set(), "ordem_b": None})
    conteudo = feed(cur, id_unidade, id_catalogo, idioma,
                    esconder_esgotado=cfg["esconder_esgotado"], previa=bool(previa_catalogo),
                    foto_forcada=var["foto"])
    if var["ordem_b"]:
        conteudo["itens"] = cardapio_testes.reordenar(conteudo["itens"], var["ordem_b"])
    return {
        "loja": {"id": id_unidade, "nome": loja["nome"],
                 "casa": empresa.get("nome_fantasia") or empresa.get("razao_social") or "Nossa casa"},
        "marca": {"cor_principal": cfg["cor_principal"], "cor_fundo": cfg["cor_fundo"],
                  "fonte": cfg["fonte"], "logo": cfg["logo_url"] or empresa.get("logo_url")},
        "mesa": {"nome": mesa["nome"], "salao": mesa["salao"]} if mesa else None,
        "cardapio": traducao.escolher(capa["nome"], capa["nome_en"], capa["nome_de"], idioma),
        "modo": modo["modo"], "aviso": modo["aviso"],
        # Fase 2 (115): os botões só aparecem com a opção ligada E numa mesa.
        "chamar_garcom": bool(cv["chamar_garcom"] and mesa),
        # 🔑 **Só consulta** (119, pedido do dono, 16/10/2026): na vitrine, a casa pode tirar a
        # "minha seleção" — o feed some com o botão de adicionar e a estrela do topo. No modo
        # PEDIDO a seleção é o carrinho, e vale sempre.
        "selecao": bool(modo["modo"] == "PEDIDO" or cv.get("selecao", True)),
        # 🔑 **Encomenda** (15/10/2026, o catering): sem mesa, o catálogo que aceita pedido
        # pelo site leva a seleção ao carrinho do site — o mesmo, já com retirada/entrega,
        # quando e pagamento. Na mesa, o pedido é o da mesa (`modo`).
        "encomenda": bool(not mesa and not previa_catalogo and _aceita_encomenda(cur, id_catalogo)),
        # Qual Cardápio Vivo é este — o feed devolve o catálogo nos eventos.
        "vivo": {"id_catalogo": id_catalogo, "slug": cv.get("slug"),
                 "principal": bool(cv.get("principal"))},
        # 🔑 **O Hub** (114): só o que a loja LIGOU e PREENCHEU. Nenhum dos dois → nulo, e a
        # tela pula direto para o feed.
        "hub": _hub(cfg, loja),
        "previa": bool(previa_catalogo),
        # 🔑 Os cartões de conteúdo (120): a abertura do cardápio e os cartões entre os pratos.
        # Só no feed — o site e o PDF continuam só com os pratos (decisão do dono).
        "cartoes": catalogo_cartoes.do_feed(cur, id_catalogo, idioma),
        # 🔑 121: quais seções abrem (deste Cardápio Vivo) e os anúncios que valem agora, com as
        # regras de exibição da casa. ⚠️ A prévia do cadastro não mostra anúncio — a não ser
        # que se peça (1.1.109): aí, os que valem AGORA, como na mesa se for o principal.
        "aberturas": cv.get("aberturas") or "AUTOMATICA",
        # ⚠️ 125: a prévia não entra no grupo de controle nem nas variações (sem sessão).
        **(catalogo_anuncios.do_feed(cur, id_unidade, id_catalogo,
                                     bool(mesa) or bool(previa_catalogo and cv.get("principal")), idioma,
                                     sessao=None if previa_catalogo else sessao)
           if not previa_catalogo or previa_anuncios
           else {"anuncios": [], "regras_anuncio": None, "grupo_anuncio": None}),
        **conteudo,
    }


def _aceita_encomenda(cur, id_catalogo: int) -> bool:
    from services import pedidos
    return bool(pedidos.config(cur, id_catalogo)["aceita"])


def _hub(cfg: dict, loja: dict) -> dict | None:
    avaliacao = loja["avaliacao"] if cfg["hub_avaliacao"] else None
    wifi = ({"rede": loja["wifi_rede"], "senha": loja["wifi_senha"] or ""}
            if cfg["hub_wifi"] and loja["wifi_rede"] else None)
    if not avaliacao and not wifi:
        return None
    return {"avaliacao": avaliacao, "wifi": wifi}


def sem_midia(cur, id_unidade: int, id_catalogo: int) -> list[dict]:
    """Os itens PUBLICADOS sem foto e sem vídeo próprios — o aviso do cadastro.

    ⚠️ A foto emprestada da seção não conta: no feed, dez pratos com a mesma foto da
    categoria parecem o mesmo prato.
    """
    cur.execute(
        """SELECT i.id, coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome) AS nome,
                  p.id AS id_produto, g.nome AS categoria
             FROM catalogo_itens i
             JOIN catalogo_categorias g ON g.id = i.id_categoria
             JOIN catalogos k ON k.id = g.id_catalogo
             JOIN produtos p ON p.id = i.id_produto
            WHERE g.id_catalogo = %s AND k.id_unidade = %s AND p.ativo
              AND p.foto_url IS NULL AND p.video_url IS NULL
            ORDER BY g.ordem, i.ordem""",
        (id_catalogo, id_unidade))
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Eventos: a atenção
# ---------------------------------------------------------------------------

# ⚠️ **É a única rota pública que grava sem identificação nenhuma**, e por isso tem
# freio em três lugares: tamanho do lote, eventos por sessão e lotes por origem.
LOTE_MAXIMO = 60
EVENTOS_POR_SESSAO = 3000
LOTES_POR_ORIGEM = 240          # em JANELA_ORIGEM segundos
JANELA_ORIGEM = 600
_lotes_por_origem: dict[str, deque] = {}


def _freio_da_origem(origem: str | None) -> None:
    """Conta lotes por endereço, em memória. ⚠️ Só CONTA — o endereço não é guardado."""
    if not origem:
        return
    agora = _tempo.monotonic()
    fila = _lotes_por_origem.setdefault(origem, deque())
    while fila and agora - fila[0] > JANELA_ORIGEM:
        fila.popleft()
    if len(fila) >= LOTES_POR_ORIGEM:
        raise HTTPException(status_code=429, detail="Muitos envios. Tente daqui a pouco.")
    fila.append(agora)
    if len(_lotes_por_origem) > 5000:  # não deixa o dicionário crescer sem fim
        for chave in [k for k, f in _lotes_por_origem.items() if not f][:2500]:
            _lotes_por_origem.pop(chave, None)


def registrar_eventos(cur, lote: dict, origem: str | None) -> dict:
    """Grava um lote de eventos de UMA sessão.

    🔑 **O produto é descoberto aqui, pelo item**, e só item do catálogo que a loja
    aponta entra: um id inventado vira evento sem produto, nunca o produto de outra casa.
    🔑 **A hora é a do SERVIDOR**, recuada pela idade que o navegador informa (no máximo
    15 min) — o relógio do celular do cliente não é confiável.
    """
    _freio_da_origem(origem)
    eventos = lote["eventos"][:LOTE_MAXIMO]
    id_unidade = lote["loja"]
    # 🔑 O lote diz de qual Cardápio Vivo veio (117); sem dizer, é o principal (o feed antigo).
    # ⚠️ E desde a 122 isso fica GRAVADO em cada evento: antes se usava só para conferir os
    # itens, e a medição da cafeteria e a do catering se somavam.
    cv = (vivo(cur, id_unidade, id_catalogo=lote["catalogo"]) if lote.get("catalogo")
          else vivo(cur, id_unidade))
    if not cv or not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Cardápio não encontrado.")
    id_mesa = None
    if lote.get("mesa"):
        mesa = mesa_por_token(cur, lote["mesa"])
        if not mesa or mesa["id_unidade"] != id_unidade:
            raise HTTPException(status_code=404, detail="Mesa não encontrada.")
        id_mesa = mesa["id"]

    cur.execute(
        """INSERT INTO cardapio_sessoes (id, id_unidade, id_mesa, modo, dispositivo, idioma)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET ultimo = now()
           RETURNING id_unidade, eventos""",
        (lote["sessao"], id_unidade, id_mesa, lote["modo"], lote["dispositivo"],
         lote.get("idioma")))
    sessao = cur.fetchone()
    if sessao["id_unidade"] != id_unidade:
        raise HTTPException(status_code=409, detail="Sessão de outra casa.")
    sobra = EVENTOS_POR_SESSAO - sessao["eventos"]
    if sobra <= 0:
        return {"gravados": 0}
    eventos = eventos[:sobra]

    itens = sorted({e["item"] for e in eventos if e.get("item")})
    produto_do_item: dict[int, int] = {}
    if itens:
        cur.execute(
            """SELECT i.id, i.id_produto FROM catalogo_itens i
                 JOIN catalogo_categorias g ON g.id = i.id_categoria
                WHERE i.id = ANY(%s) AND g.id_catalogo = %s""",
            (itens, cv["id_catalogo"]))
        produto_do_item = {r["id"]: r["id_produto"] for r in cur.fetchall()}

    # 🔑 O cartão (120), como o item: só o DESTE cardápio entra; id inventado vira nulo.
    cartoes = sorted({e["cartao"] for e in eventos if e.get("cartao")})
    do_catalogo: set[int] = set()
    if cartoes:
        cur.execute("SELECT id FROM catalogo_cartoes WHERE id = ANY(%s) AND id_catalogo = %s",
                    (cartoes, cv["id_catalogo"]))
        do_catalogo = {r["id"] for r in cur.fetchall()}

    anuncios = sorted({e["anuncio"] for e in eventos if e.get("anuncio")})
    da_loja: set[int] = set()
    if anuncios:
        cur.execute("SELECT id FROM cardapio_anuncios WHERE id = ANY(%s) AND id_unidade = %s",
                    (anuncios, id_unidade))
        da_loja = {r["id"] for r in cur.fetchall()}
    # 🔑 125: a variação só entra se é DAQUELE anúncio; id inventado vira nulo (a original).
    pares = {(e["anuncio"], e["variante"]) for e in eventos if e.get("anuncio") in da_loja and e.get("variante")}
    variante_ok: set[tuple] = set()
    if pares:
        cur.execute("SELECT id_anuncio, id FROM cardapio_anuncio_variantes WHERE id = ANY(%s)",
                    ([v for _a, v in pares],))
        variante_ok = {(r["id_anuncio"], r["id"]) for r in cur.fetchall()} & pares
    grupo = lote.get("grupo_anuncio")

    linhas = []
    for e in eventos:
        item = e.get("item") if e.get("item") in produto_do_item else None
        idade = min(max(int(e.get("idade_ms") or 0), 0), 15 * 60 * 1000)
        duracao = e.get("duracao_ms")
        if duracao is not None:
            duracao = min(max(int(duracao), 0), 30 * 60 * 1000)
        linhas.append((lote["sessao"], id_unidade, id_mesa, e["tipo"], item,
                       produto_do_item.get(item) if item else None, e.get("categoria"),
                       e.get("subcategoria"),
                       e.get("cartao") if e.get("cartao") in do_catalogo else None,
                       e.get("anuncio") if e.get("anuncio") in da_loja else None,
                       e.get("variante") if (e.get("anuncio"), e.get("variante")) in variante_ok else None,
                       grupo, cv["id_catalogo"], lote["modo"], e.get("midia"), duracao, idade))
    if linhas:
        cur.executemany(
            """INSERT INTO cardapio_eventos (id_sessao, id_unidade, id_mesa, tipo, id_item,
                                             id_produto, id_categoria, id_subcategoria, id_cartao,
                                             id_anuncio, id_variante, grupo_anuncio, id_catalogo,
                                             modo, midia, duracao_ms, quando)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       now() - make_interval(secs => %s / 1000.0))""",
            linhas)
        cur.execute("UPDATE cardapio_sessoes SET eventos = eventos + %s WHERE id = %s",
                    (len(linhas), lote["sessao"]))
    return {"gravados": len(linhas)}


def agregar_dia(cur, dia, id_unidade: int | None = None) -> int:
    """Resume um dia do bruto em `cardapio_agregados_dia`. Idempotente: refaz o dia.

    ⚠️ **Por loja quando a loja é dada**: a retenção de uma loja apaga o bruto dela, e
    refazer o dia inteiro depois disso zeraria o resumo que ela já tinha.
    """
    cur.execute("DELETE FROM cardapio_agregados_dia WHERE dia = %s "
                "AND (%s::int IS NULL OR id_unidade = %s)", (dia, id_unidade, id_unidade))
    cur.execute(
        """INSERT INTO cardapio_agregados_dia
               (dia, id_unidade, id_produto, id_mesa, hora, midia, visualizacoes,
                atencao_ms, detalhes, adicoes, remocoes, favoritos, deslizes_tras,
                personalizacoes)
           SELECT quando::date, id_unidade, id_produto, coalesce(id_mesa, 0),
                  extract(hour FROM quando)::smallint, coalesce(midia, 'NENHUMA'),
                  count(*) FILTER (WHERE tipo = 'viu_item'),
                  -- ⚠️ Com o TETO de 60 s por visualização: é a "atenção estimada".
                  coalesce(sum(least(duracao_ms, %s)) FILTER (WHERE tipo = 'viu_item'), 0),
                  count(*) FILTER (WHERE tipo = 'abriu_detalhe'),
                  count(*) FILTER (WHERE tipo = 'adicionou'),
                  count(*) FILTER (WHERE tipo = 'removeu'),
                  count(*) FILTER (WHERE tipo = 'favoritou'),
                  count(*) FILTER (WHERE tipo = 'deslizou_tras'),
                  count(*) FILTER (WHERE tipo = 'abriu_personalizacao')
             FROM cardapio_eventos
            WHERE quando >= %s::date AND quando < %s::date + 1 AND id_produto IS NOT NULL
              AND (%s::int IS NULL OR id_unidade = %s)
            GROUP BY 1, 2, 3, 4, 5, 6""",
        (ATENCAO_MAX_MS, dia, dia, id_unidade, id_unidade))
    linhas = cur.rowcount
    _resumir_dia(cur, dia, id_unidade)
    _resumir_conteudo(cur, dia, id_unidade)
    return linhas


def _resumir_conteudo(cur, dia, id_unidade: int | None = None) -> None:
    """Anúncios, cartões e aberturas de seção do dia em `cardapio_conteudo_dia` (124).

    🔑 O que o feed mostra ENTRE os pratos também sobrevive à retenção: o relatório do anúncio
    lê daqui os dias que o bruto já não tem. Idempotente: refaz o dia (da loja, se dada).
    """
    cur.execute("DELETE FROM cardapio_conteudo_dia WHERE dia = %s "
                "AND (%s::int IS NULL OR id_unidade = %s)", (dia, id_unidade, id_unidade))
    cur.execute(
        """INSERT INTO cardapio_conteudo_dia
               (dia, id_unidade, tipo, id_ref, id_sub, id_catalogo, canal, vistas, sessoes,
                soma_ms, pulados, cliques, sessoes_clicaram)
           SELECT quando::date, id_unidade, t_tipo, ref, sub, coalesce(id_catalogo, 0),
                  CASE WHEN id_mesa IS NULL THEN 'LINK' ELSE 'MESA' END,
                  count(*) FILTER (WHERE viu),
                  count(DISTINCT id_sessao) FILTER (WHERE viu),
                  coalesce(sum(duracao_ms) FILTER (WHERE viu), 0),
                  count(*) FILTER (WHERE viu AND duracao_ms < %s),
                  count(*) FILTER (WHERE NOT viu),
                  count(DISTINCT id_sessao) FILTER (WHERE NOT viu)
             FROM (SELECT e.*, e.tipo LIKE 'viu%%' AS viu,
                          CASE WHEN e.tipo IN ('viu_anuncio', 'clicou_anuncio') THEN 'ANUNCIO'
                               WHEN e.tipo IN ('viu_cartao', 'clicou_cartao') THEN 'CARTAO'
                               ELSE 'SECAO' END AS t_tipo,
                          CASE WHEN e.tipo IN ('viu_anuncio', 'clicou_anuncio') THEN e.id_anuncio
                               WHEN e.tipo IN ('viu_cartao', 'clicou_cartao') THEN e.id_cartao
                               ELSE e.id_categoria END AS ref,
                          CASE WHEN e.tipo = 'viu_secao' THEN coalesce(e.id_subcategoria, 0) ELSE 0 END AS sub
                     FROM cardapio_eventos e
                    WHERE e.tipo IN ('viu_anuncio', 'clicou_anuncio', 'viu_cartao', 'clicou_cartao', 'viu_secao')
                      AND e.quando >= %s::date AND e.quando < %s::date + 1
                      AND (%s::int IS NULL OR e.id_unidade = %s)) x
            WHERE ref IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5, 6, 7""",
        (catalogo_anuncios.PULOU_MS, dia, dia, id_unidade, id_unidade))


# 🔑 **"Sessão engajada"** = ao menos 3 itens DIFERENTES vistos, ou 1 interação (favorito,
# personalização ou adição). Os indicadores principais do painel usam só estas; o total de
# sessões abertas aparece à parte. A regra mora AQUI, em SQL, e só aqui.
SQL_SESSAO_ENGAJADA = """(count(DISTINCT id_item) FILTER (WHERE tipo = 'viu_item') >= 3
                          OR count(*) FILTER (WHERE tipo IN ('favoritou', 'abriu_personalizacao',
                                                             'adicionou')) > 0)"""


def _resumir_dia(cur, dia, id_unidade: int | None = None) -> None:
    """Sessões abertas e engajadas, e os cliques do Hub, por loja e dia."""
    cur.execute("DELETE FROM cardapio_resumo_dia WHERE dia = %s "
                "AND (%s::int IS NULL OR id_unidade = %s)", (dia, id_unidade, id_unidade))
    cur.execute(
        f"""INSERT INTO cardapio_resumo_dia (dia, id_unidade, sessoes, engajadas, hubs,
                                             cliques_avaliacao, cliques_wifi)
            SELECT %s::date, id_unidade, count(*), count(*) FILTER (WHERE engajada),
                   sum(hubs), sum(avaliacao), sum(wifi)
              FROM (SELECT id_sessao, id_unidade, {SQL_SESSAO_ENGAJADA} AS engajada,
                           count(*) FILTER (WHERE tipo = 'abriu_hub') AS hubs,
                           count(*) FILTER (WHERE tipo = 'clicou_avaliacao') AS avaliacao,
                           count(*) FILTER (WHERE tipo = 'clicou_wifi') AS wifi
                      FROM cardapio_eventos
                     WHERE quando >= %s::date AND quando < %s::date + 1
                       AND (%s::int IS NULL OR id_unidade = %s)
                     GROUP BY id_sessao, id_unidade) s
             GROUP BY id_unidade""",  # noqa: S608 - a regra é constante do módulo
        (dia, dia, dia, id_unidade, id_unidade))


# ---------------------------------------------------------------------------
# Apagar a medição de um período (20/10/2026)
# ---------------------------------------------------------------------------

_TABELAS_DO_DIA = ("cardapio_agregados_dia", "cardapio_resumo_dia", "cardapio_conteudo_dia")


def medicao_do_periodo(cur, id_unidade: int, de, ate) -> dict:
    """Quanto da medição do Cardápio Vivo existe no período, nesta loja — sem apagar.

    🔑 Pedido do dono (20/10/2026): *"realizar a limpeza de dados de determinado período"* — os
    dias de teste antes de abrir, ou um dia em que a medição saiu errada. Conta o bruto (eventos e
    sessões) e os três resumos por dia.
    """
    if de > ate:
        raise HTTPException(status_code=422, detail="O período termina antes de começar.")
    cur.execute("""SELECT count(*) AS eventos, count(DISTINCT id_sessao) AS sessoes
                     FROM cardapio_eventos
                    WHERE id_unidade = %s AND quando >= %s::date AND quando < %s::date + 1""",
                (id_unidade, de, ate))
    r = dict(cur.fetchone())
    for t in _TABELAS_DO_DIA:
        cur.execute(f"SELECT count(*) AS n FROM {t} WHERE id_unidade = %s AND dia BETWEEN %s AND %s",  # noqa: S608
                    (id_unidade, de, ate))
        r[t.removeprefix("cardapio_")] = cur.fetchone()["n"]
    return {"de": de, "ate": ate, **r, "vazio": not any(v for k, v in r.items())}


def apagar_medicao(cur, id_unidade: int, de, ate) -> dict:
    """Apaga a medição do período nesta loja: eventos, os resumos daqueles dias e as sessões que
    ficaram sem evento nenhum.

    ⚠️ **Não toca** nos anúncios, nos testes A/B, nos chamados de garçom nem nos pedidos — só na
    medição. Os números deles (que vêm da medição) voltam sem aqueles dias.
    ⚠️ A sessão que tem evento FORA do período fica: ela é de um dia que não se pediu para apagar.
    """
    antes = medicao_do_periodo(cur, id_unidade, de, ate)
    cur.execute("""DELETE FROM cardapio_eventos
                    WHERE id_unidade = %s AND quando >= %s::date AND quando < %s::date + 1
                RETURNING id_sessao""", (id_unidade, de, ate))
    sessoes = list({r["id_sessao"] for r in cur.fetchall()})
    for t in _TABELAS_DO_DIA:
        cur.execute(f"DELETE FROM {t} WHERE id_unidade = %s AND dia BETWEEN %s AND %s",  # noqa: S608
                    (id_unidade, de, ate))
    sem_evento = 0
    if sessoes:
        cur.execute("""DELETE FROM cardapio_sessoes s
                        WHERE s.id = ANY(%s::uuid[]) AND s.id_unidade = %s
                          AND NOT EXISTS (SELECT 1 FROM cardapio_eventos e WHERE e.id_sessao = s.id)""",
                    ([str(s) for s in sessoes], id_unidade))
        sem_evento = cur.rowcount
    return antes | {"sessoes_apagadas": sem_evento,
                    "message": f"Medição apagada: {antes['eventos']} evento(s) de {antes['sessoes']} visita(s)."}


def reter(cur, hoje=None) -> dict:
    """O job diário: agrega ontem e apaga o bruto além da retenção de cada loja.

    ⚠️ **Agrega ANTES de apagar** — todo dia que sai do bruto é resumido primeiro, senão
    a retenção apagaria a história que o painel promete guardar.
    """
    hoje = hoje or agora_da_casa().date()
    agregados = agregar_dia(cur, hoje - timedelta(days=1))
    # 🔑 123: o esgotado que já voltou sai da linha (a leitura já o ignorava).
    cur.execute("""UPDATE catalogo_itens SET esgotado = false, esgotado_ate = NULL
                    WHERE esgotado_ate IS NOT NULL AND esgotado_ate <= now()""")
    cur.execute(
        """SELECT u.id, coalesce(c.retencao_meses, 13) AS meses
             FROM unidades u LEFT JOIN cardapio_config c ON c.id_unidade = u.id""")
    apagados = 0
    for loja in cur.fetchall():
        limite = hoje - timedelta(days=int(loja["meses"]) * 30)
        cur.execute(
            """SELECT DISTINCT quando::date AS dia FROM cardapio_eventos
                WHERE id_unidade = %s AND quando < %s""",
            (loja["id"], limite))
        for d in [r["dia"] for r in cur.fetchall()]:
            cur.execute("SELECT 1 FROM cardapio_agregados_dia WHERE dia = %s "
                        "AND id_unidade = %s LIMIT 1", (d, loja["id"]))
            if not cur.fetchone():
                agregar_dia(cur, d, loja["id"])
        cur.execute("DELETE FROM cardapio_eventos WHERE id_unidade = %s AND quando < %s",
                    (loja["id"], limite))
        apagados += cur.rowcount
        cur.execute(
            """DELETE FROM cardapio_sessoes s WHERE s.id_unidade = %s AND s.ultimo < %s
                 AND NOT EXISTS (SELECT 1 FROM cardapio_eventos e WHERE e.id_sessao = s.id)""",
            (loja["id"], limite))
    return {"agregados": agregados, "apagados": apagados}


# ---------------------------------------------------------------------------
# O agendador da retenção
# ---------------------------------------------------------------------------

_ultimo_dia_retido = None


def _reter_com_cursor() -> dict | None:
    from database import get_cursor
    with get_cursor() as cur:
        # ⚠️ Dois contêineres convivem por um ou dois minutos no deploy: o lock faz só um
        # deles agregar, e o outro passa a vez em vez de esperar.
        cur.execute("SELECT pg_try_advisory_xact_lock(113113) AS ok")
        if not cur.fetchone()["ok"]:
            return None
        return reter(cur)


async def laco(parar) -> None:
    """Uma vez por dia, depois das 3h da casa: agrega ontem e aplica a retenção.

    ⚠️ Nada aqui pode levantar: um agendador que morre no primeiro erro some sem avisar.
    """
    import asyncio

    from services import erros
    global _ultimo_dia_retido
    while not parar.is_set():
        try:
            await asyncio.wait_for(parar.wait(), timeout=600)
            return
        except asyncio.TimeoutError:
            pass
        try:
            agora = agora_da_casa()
            if agora.hour >= 3 and _ultimo_dia_retido != agora.date():
                await asyncio.to_thread(_reter_com_cursor)
                _ultimo_dia_retido = agora.date()
        except Exception as e:  # noqa: BLE001
            await asyncio.to_thread(erros.registrar, "cardapio_vivo", e)
