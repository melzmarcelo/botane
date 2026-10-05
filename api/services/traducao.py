"""O cardápio do site em inglês e alemão, traduzido pelo Claude Haiku.

🔑 **Pedido do dono (24/09/2026, decidido em 29/09/2026):** *"gerar o texto do catálogo em
inglês e alemão de forma automática, e a escolha do idioma no site"* — Claude Haiku,
categorias também, e o site nos três idiomas.

Quatro regras:

* **Traduz o que o cliente LÊ**: o nome de vitrine do produto (ou o nome, sem vitrine) e o
  texto dele; nome e descrição de categoria e subcategoria; o nome do catálogo.
* **Tradução corrigida à mão nunca é sobrescrita** (`traducao_editada`). "Gerar de novo" é
  que devolve o campo à tradução automática.
* **Só retraduz quando o português MUDA** (`traducao_origem`, a impressão digital do
  português traduzido). Salvar sem mexer no texto não gasta chamada.
* **Falhar não trava nada.** Sem a chave, ou com a API fora, o salvar continua; os campos
  ficam como estavam e o site mostra o português.

🔑 **A chave é da CASA, cadastrada no sistema** (pedido do dono, 29/09/2026: *"o cliente pode
configurar a sua chave"*) — em Integrações ▸ Tradução, cifrada em `integracoes` (serviço
`ANTHROPIC`, da casa toda), como a senha do e-mail. ⚠️ Não mora mais no ambiente do servidor:
quem paga a conta da Anthropic é quem a configura, sem precisar de acesso ao painel.
"""

import hashlib
import json
import logging

import httpx

from services import segredos

log = logging.getLogger("botane.traducao")
IDIOMAS = ("en", "de")
LOTE = 25
SERVICO = "ANTHROPIC"
MODELO_PADRAO = "claude-haiku-4-5-20251001"

# tipo → a tabela, e de onde sai cada campo em português → para onde vai cada tradução.
ENTIDADES: dict[str, dict] = {
    "produto": {
        "tabela": "produtos",
        "campos": {
            "nome": ("coalesce(nullif(btrim(nome_catalogo), ''), nome)",
                     {"en": "nome_catalogo_en", "de": "nome_catalogo_de"}),
            "descricao": ("informacao_adicional",
                          {"en": "informacao_adicional_en", "de": "informacao_adicional_de"}),
        },
    },
    "categoria": {
        "tabela": "catalogo_categorias",
        "campos": {
            "nome": ("nome", {"en": "nome_en", "de": "nome_de"}),
            "descricao": ("descricao", {"en": "descricao_en", "de": "descricao_de"}),
        },
    },
    "subcategoria": {
        "tabela": "catalogo_subcategorias",
        "campos": {
            "nome": ("nome", {"en": "nome_en", "de": "nome_de"}),
            "descricao": ("descricao", {"en": "descricao_en", "de": "descricao_de"}),
        },
    },
    "catalogo": {
        "tabela": "catalogos",
        "campos": {"nome": ("nome", {"en": "nome_en", "de": "nome_de"})},
    },
}

_SISTEMA = """Você traduz o cardápio de um café e restaurante brasileiro{casa} \
para turistas: para inglês ("en") e alemão ("de").

Regras:
- Tradução natural de cardápio, não literal. Capitalização normal (o original pode estar em \
MAIÚSCULAS; a tradução não).
- Pratos e produtos tipicamente brasileiros mantêm o nome original (ex.: "Pão de queijo", \
"Coxinha", "Brigadeiro", "Escondidinho"); no nome, pode acrescentar uma explicação curta \
entre parênteses só se ajudar muito. Na descrição, explique em poucas palavras.
- Nomes próprios, marcas e medidas (ml, g, kg) ficam como estão.
- Não invente ingredientes nem informações que não estão no texto.
- Campo vazio ou ausente no original: devolva vazio.

Responda SÓ com JSON, sem comentário, no formato:
{"itens": [{"chave": "...", "en": {"nome": "...", "descricao": "..."}, "de": {"nome": "...", "descricao": "..."}}]}"""


def _casa(cur) -> str:
    """" (Nome da casa, em Cidade)", ou vazio — o parêntese do prompt."""
    cur.execute("SELECT nome_fantasia, razao_social, cidade FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    nome = e.get("nome_fantasia") or e.get("razao_social")
    partes = [p for p in (nome, e.get("cidade") and f"em {e['cidade']}") if p]
    return f" ({', '.join(partes)})" if partes else ""


def _config(cur) -> dict:
    """A chave e o modelo guardados. `chave` vazia = desligada."""
    cur.execute("""SELECT ativa, credenciais, config FROM integracoes
                    WHERE servico = %s AND id_unidade IS NULL""", (SERVICO,))
    l = cur.fetchone()
    if not l:
        return {"ativa": False, "chave": "", "modelo": MODELO_PADRAO, "ilegivel": False}
    cred = segredos.decifrar(l["credenciais"])
    return {"casa": _casa(cur), "ativa": bool(l["ativa"]), "chave": (cred.get("chave") or "").strip(),
            "modelo": (l["config"] or {}).get("modelo") or MODELO_PADRAO,
            "ilegivel": segredos.ilegivel(l["credenciais"])}


def ligada(cur) -> bool:
    c = _config(cur)
    return bool(c["ativa"] and c["chave"])


def estado(cur) -> dict:
    c = _config(cur)
    return {"ligada": bool(c["ativa"] and c["chave"]), "modelo": c["modelo"]}


def _impressao(textos: dict) -> str:
    return hashlib.sha256(json.dumps(textos, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _chamar(itens: list[dict], cfg: dict) -> list[dict]:
    """UMA chamada ao Claude para um lote. ⚠️ Separada para os testes a trocarem."""
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": cfg["chave"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": cfg["modelo"], "max_tokens": 4096,
              # A casa e a cidade vêm do cadastro da empresa — é contexto para o
              # tradutor (cardápio de Blumenau não se traduz como o de Salvador).
              "system": _SISTEMA.replace("{casa}", cfg.get("casa") or ""),
              "messages": [{"role": "user",
                            "content": json.dumps({"itens": itens}, ensure_ascii=False)}]},
        timeout=40,
    )
    r.raise_for_status()
    texto = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    return _ler_json(texto)


def _ler_json(texto: str) -> list[dict]:
    """O JSON da resposta — tolerando a cerca de código que o modelo às vezes põe."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    ini, fim = t.find("{"), t.rfind("}")
    dados = json.loads(t[ini:fim + 1])
    return dados.get("itens", [])


def _linhas(cur, tipo: str, ids: list[int]) -> list[dict]:
    e = ENTIDADES[tipo]
    fontes = ", ".join(f"{expr} AS pt_{campo}" for campo, (expr, _d) in e["campos"].items())
    destinos = ", ".join(col for _c, (_e, d) in e["campos"].items() for col in d.values())
    cur.execute(
        f"""SELECT id, {fontes}, {destinos}, traducao_editada, traducao_origem, traducao_em
              FROM {e['tabela']} WHERE id = ANY(%s)""", (ids,))
    return [dict(r) for r in cur.fetchall()]


def _origem(tipo: str, linha: dict) -> dict:
    return {c: (linha.get(f"pt_{c}") or "").strip() for c in ENTIDADES[tipo]["campos"]}


def traduzir(cur, tipo: str, ids: list[int], forcar: bool = False) -> dict:
    """Traduz o que está sem tradução ou com o português mudado. Devolve o que fez.

    `forcar`: traduz de novo mesmo sem mudança — e é o "gerar de novo", que também devolve
    os campos corrigidos à mão para a tradução automática.
    """
    if not ids:
        return {"traduzidos": 0, "erro": None}
    cfg = _config(cur)
    if not (cfg["ativa"] and cfg["chave"]):
        return {"traduzidos": 0, "erro": "A tradução automática está desligada: falta cadastrar a "
                "chave da Anthropic em Integrações ▸ Tradução."}
    e = ENTIDADES[tipo]
    pendentes = []
    for l in _linhas(cur, tipo, ids):
        origem = _origem(tipo, l)
        if not any(origem.values()):
            continue
        if forcar or l["traducao_origem"] != _impressao(origem):
            pendentes.append((l, origem))
    feitos = 0
    erro = None
    for i in range(0, len(pendentes), LOTE):
        lote = pendentes[i:i + LOTE]
        try:
            respostas = {str(r.get("chave")): r for r in _chamar(
                [{"chave": str(l["id"]), **{c: v for c, v in o.items() if v}} for l, o in lote], cfg)}
        except Exception as ex:  # noqa: BLE001 - a API fora não pode travar o salvar
            log.warning("tradução falhou (%s): %s", tipo, ex)
            erro = "Não foi possível traduzir agora — tente de novo em instantes."
            continue
        for l, origem in lote:
            r = respostas.get(str(l["id"]))
            if not r:
                continue
            editada = [] if forcar else list(l["traducao_editada"] or [])
            sets, valores = [], []
            for campo, (_expr, destino) in e["campos"].items():
                for idioma in IDIOMAS:
                    col = destino[idioma]
                    if col in editada:
                        continue  # 🔑 corrigida à mão: fica
                    valor = ((r.get(idioma) or {}).get(campo) or "").strip() if origem[campo] else ""
                    sets.append(f"{col} = %s")
                    valores.append(valor or None)
            cur.execute(
                f"""UPDATE {e['tabela']} SET {', '.join(sets + ['traducao_origem = %s',
                    'traducao_em = now()', 'traducao_editada = %s'])} WHERE id = %s""",
                (*valores, _impressao(origem), editada, l["id"]))
            feitos += 1
    return {"traduzidos": feitos, "erro": erro}


def tentar(cur, tipo: str, id_: int) -> None:
    """Depois de salvar: traduz se der. ⚠️ Nunca levanta — salvar não depende disto."""
    try:
        cur.execute("SAVEPOINT traducao")
        if not ligada(cur):
            cur.execute("RELEASE SAVEPOINT traducao")
            return
        traduzir(cur, tipo, [id_])
        cur.execute("RELEASE SAVEPOINT traducao")
    except Exception as ex:  # noqa: BLE001
        cur.execute("ROLLBACK TO SAVEPOINT traducao")
        log.warning("tradução automática falhou (%s %s): %s", tipo, id_, ex)


def obter(cur, tipo: str, id_: int) -> dict:
    linhas = _linhas(cur, tipo, [id_])
    if not linhas:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Não encontrado")
    l = linhas[0]
    e = ENTIDADES[tipo]
    origem = _origem(tipo, l)
    return {
        "tipo": tipo, "id": id_, "origem": origem,
        **{idioma: {c: l[d[idioma]] for c, (_x, d) in e["campos"].items()} for idioma in IDIOMAS},
        "editada": list(l["traducao_editada"] or []),
        "traduzida_em": l["traducao_em"],
        "desatualizada": bool(any(origem.values()) and l["traducao_origem"] != _impressao(origem)
                              and l["traducao_origem"] is not None),
        "campos": list(e["campos"]),
        "colunas": {c: d for c, (_x, d) in e["campos"].items()},
    }


def gravar_manual(cur, tipo: str, id_: int, dados: dict) -> dict:
    """A casa corrige a tradução. O campo que MUDOU vira "editado à mão"."""
    atual = obter(cur, tipo, id_)
    e = ENTIDADES[tipo]
    editada = set(atual["editada"])
    sets, valores = [], []
    for idioma in IDIOMAS:
        for campo, (_x, destino) in e["campos"].items():
            if campo not in (dados.get(idioma) or {}):
                continue
            novo = ((dados[idioma] or {}).get(campo) or "").strip() or None
            if novo != (atual[idioma].get(campo) or None):
                sets.append(f"{destino[idioma]} = %s")
                valores.append(novo)
                editada.add(destino[idioma])
    if sets:
        cur.execute(f"UPDATE {e['tabela']} SET {', '.join(sets)}, traducao_editada = %s WHERE id = %s",
                    (*valores, sorted(editada), id_))
    return obter(cur, tipo, id_)


def do_catalogo(cur, id_catalogo: int, forcar: bool = False) -> dict:
    """Tudo o que o site mostra deste catálogo: o nome, as seções e os produtos."""
    cur.execute("SELECT id FROM catalogo_categorias WHERE id_catalogo = %s", (id_catalogo,))
    cats = [r["id"] for r in cur.fetchall()]
    cur.execute("SELECT s.id FROM catalogo_subcategorias s JOIN catalogo_categorias c "
                "ON c.id = s.id_categoria WHERE c.id_catalogo = %s", (id_catalogo,))
    subs = [r["id"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT i.id_produto FROM catalogo_itens i JOIN catalogo_categorias c "
                "ON c.id = i.id_categoria WHERE c.id_catalogo = %s", (id_catalogo,))
    prods = [r["id_produto"] for r in cur.fetchall()]
    total, erro = 0, None
    for tipo, ids in (("catalogo", [id_catalogo]), ("categoria", cats), ("subcategoria", subs),
                      ("produto", prods)):
        r = traduzir(cur, tipo, ids, forcar)
        total += r["traduzidos"]
        erro = erro or r["erro"]
    return {"traduzidos": total, "erro": erro}


def pendentes_do_catalogo(cur, id_catalogo: int) -> int:
    """Quantas coisas do catálogo estão sem tradução, ou com o português mudado."""
    n = 0
    cur.execute("SELECT id FROM catalogo_categorias WHERE id_catalogo = %s", (id_catalogo,))
    cats = [r["id"] for r in cur.fetchall()]
    cur.execute("SELECT s.id FROM catalogo_subcategorias s JOIN catalogo_categorias c "
                "ON c.id = s.id_categoria WHERE c.id_catalogo = %s", (id_catalogo,))
    subs = [r["id"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT i.id_produto FROM catalogo_itens i JOIN catalogo_categorias c "
                "ON c.id = i.id_categoria WHERE c.id_catalogo = %s", (id_catalogo,))
    prods = [r["id_produto"] for r in cur.fetchall()]
    for tipo, ids in (("catalogo", [id_catalogo]), ("categoria", cats), ("subcategoria", subs),
                      ("produto", prods)):
        if not ids:
            continue
        for l in _linhas(cur, tipo, ids):
            o = _origem(tipo, l)
            if any(o.values()) and l["traducao_origem"] != _impressao(o):
                n += 1
    return n


def escolher(pt: str | None, en: str | None, de: str | None, idioma: str | None) -> str | None:
    """🔑 Faltou tradução → o português, nunca vazio."""
    if idioma == "en" and en:
        return en
    if idioma == "de" and de:
        return de
    return pt


def testar(chave: str, modelo: str) -> tuple[bool, str]:
    """Uma chamada mínima, para a tela dizer se a chave funciona antes de o cardápio depender dela."""
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": modelo, "max_tokens": 16,
                  "messages": [{"role": "user", "content": "Traduza para inglês: pão de queijo"}]},
            timeout=20)
    except httpx.HTTPError as ex:
        return False, f"Não foi possível falar com a Anthropic: {ex.__class__.__name__}."
    if r.status_code == 200:
        return True, "A chave funciona."
    # ⚠️ As causas comuns, na língua de quem cadastrou — o corpo da Anthropic vem em inglês.
    motivo = {401: "a chave não foi aceita (confira se copiou inteira)",
              403: "a chave não tem permissão para este uso",
              404: "o modelo informado não existe",
              429: "limite de uso atingido — tente em instantes",
              400: "a conta recusou o pedido (sem crédito? confira em Billing)"}.get(r.status_code)
    return False, f"A Anthropic recusou: {motivo or f'erro {r.status_code}'}."
