"""Cardápio Vivo, fase 3 (migração 116): testes A/B e sugestões de destaque.

🔑 **Decisões do dono (15/10/2026)**, seção 9 de `docs/cardapio-vivo-estudo.md`:
* A/B de **mídia** = vídeo × foto no MESMO prato (só prato que tem os dois);
* A/B de **ordem** = a ordem do catálogo × a ordem que o painel sugere;
* o **vencedor** sai da TAXA DE ADIÇÃO (quem viu e adicionou), que se atribui à sessão;
* **destaque**: o sistema sugere, o gerente aprova — nada muda sem um clique.

🔑 **A variante vem de uma conta no BANCO** (`SQL_VARIANTE`), a mesma no feed e na análise.
⚠️ Aplicar o vencedor é sempre um clique de quem edita o catálogo, auditado.
"""

import json
import math
from datetime import timedelta

from fastapi import HTTPException

from relogio import agora_da_casa
from services import cardapio_atencao
from services import cardapio_vivo as cv
from services import catalogo_conteudo

# A conta da variante: metade das sessões em cada braço, estável para a mesma sessão.
# ⚠️ `mod(…, 2)` e não `% 2`: o `%` solto conflita com os marcadores do psycopg2.
SQL_VARIANTE = ("CASE WHEN mod(abs(hashtext({sessao}::text || ':' || {teste}::text)), 2) = 0 "
                "THEN 'A' ELSE 'B' END")
# ⚠️ Antes disto por braço, o painel diz "amostra pequena" em vez de apontar vencedor: com
# vinte sessões, uma mesa animada decide o teste.
MIN_POR_BRACO = 100
SIGNIFICANCIA = 0.05
ROTULOS = {"MIDIA": {"A": "Vídeo", "B": "Foto"}, "ORDEM": {"A": "Ordem atual", "B": "Ordem sugerida"}}


# ---------------------------------------------------------------- o feed

def variantes(cur, id_unidade: int, id_catalogo: int, sessao: str) -> dict:
    """As variantes que esta sessão vê nos testes ABERTOS deste cardápio, NESTA loja.

    ⚠️ O teste é da LOJA, não do catálogo: um catálogo pode estar visível em duas lojas
    (`catalogo_lojas`) e ser o Cardápio Vivo das duas. Filtrar só pelo catálogo fazia o
    teste da matriz mudar o feed da filial — e o resultado, que conta só os eventos da
    loja do teste, nunca enxergava essa mudança."""
    cur.execute(
        f"""SELECT id, tipo, id_produto, ordem_b,
                   {SQL_VARIANTE.format(sessao='%s', teste='id')} AS variante
              FROM cardapio_testes
             WHERE id_unidade = %s AND id_catalogo = %s AND encerrado_em IS NULL""",  # noqa: S608
        (sessao, id_unidade, id_catalogo))
    saida = {"foto": set(), "ordem_b": None}
    for t in cur.fetchall():
        if t["variante"] != "B":
            continue
        if t["tipo"] == "MIDIA":
            saida["foto"].add(t["id_produto"])
        else:
            saida["ordem_b"] = list(t["ordem_b"] or [])
    return saida


def reordenar(itens: list[dict], ordem_b: list[int]) -> list[dict]:
    """Os itens do feed na ordem B; item novo (fora da foto da ordem) vai depois, como estava."""
    posicao = {id_item: n for n, id_item in enumerate(ordem_b)}
    fim = len(ordem_b)
    return sorted(itens, key=lambda i: (posicao.get(i["id"], fim), itens.index(i)))


# ---------------------------------------------------------------- a ordem sugerida

def ordem_sugerida(cur, id_unidade: int, id_catalogo: int) -> list[int]:
    """A ordem que o painel sugere, DENTRO de cada lista (seção ou subseção).

    🔑 Sobe o que está em destaque e o que o painel manda destacar ou proteger; desce o
    candidato a sair. Empate mantém a ordem da casa — a sugestão mexe só no que tem motivo.
    """
    hoje = agora_da_casa().date()
    painel = cardapio_atencao.painel(cur, id_unidade, hoje - timedelta(days=29), hoje)
    peso_sugestao = {"DESTACAR": 3, "PROTEGER": 2, "REVISAR": 0, None: 0, "SAIR": -2}
    por_produto = {l["id_produto"]: l for l in painel["itens"]}
    cur.execute(
        """SELECT i.id, i.id_produto, i.destaque, i.id_categoria, i.id_subcategoria
             FROM catalogo_itens i
             JOIN catalogo_categorias g ON g.id = i.id_categoria
             LEFT JOIN catalogo_subcategorias s ON s.id = i.id_subcategoria
             JOIN produtos p ON p.id = i.id_produto
            WHERE g.id_catalogo = %s AND p.ativo
            ORDER BY g.ordem, lower(g.nome), s.ordem NULLS FIRST, lower(s.nome), i.ordem, lower(p.nome)""",
        (id_catalogo,))
    linhas = [dict(r) for r in cur.fetchall()]
    listas: dict[tuple, list[dict]] = {}
    for n, l in enumerate(linhas):
        l["_n"] = n
        listas.setdefault((l["id_categoria"], l["id_subcategoria"]), []).append(l)

    def peso(l: dict) -> int:
        sug = por_produto.get(l["id_produto"], {}).get("sugestao")
        return (4 if l["destaque"] else 0) + peso_sugestao.get(sug, 0)

    ordem: list[int] = []
    for chave in dict.fromkeys((l["id_categoria"], l["id_subcategoria"]) for l in linhas):
        ordem += [l["id"] for l in sorted(listas[chave], key=lambda l: (-peso(l), l["_n"]))]
    return ordem


# ---------------------------------------------------------------- criar, encerrar, aplicar

def _catalogo_da_loja(cur, id_unidade: int) -> int:
    cfg = cv.config(cur, id_unidade)
    if not cfg["id_catalogo"]:
        raise HTTPException(status_code=409, detail="Aponte o cardápio da mesa antes de testar.")
    return cfg["id_catalogo"]


def criar(cur, id_unidade: int, dados: dict, id_usuario: int) -> dict:
    id_catalogo = _catalogo_da_loja(cur, id_unidade)
    if dados["tipo"] == "MIDIA":
        cur.execute(
            """SELECT p.id, coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome) AS nome,
                      p.video_url, p.foto_url
                 FROM catalogo_itens i JOIN catalogo_categorias g ON g.id = i.id_categoria
                 JOIN produtos p ON p.id = i.id_produto
                WHERE i.id = %s AND g.id_catalogo = %s""", (dados.get("id_item"), id_catalogo))
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Prato não encontrado no cardápio da mesa.")
        if not (p["video_url"] and p["foto_url"]):
            raise HTTPException(status_code=409,
                                detail=f"{p['nome']} precisa ter vídeo E foto para comparar os dois.")
        nome, id_produto, ordem_b = f"Vídeo × foto — {p['nome']}", p["id"], None
    else:
        ordem = ordem_sugerida(cur, id_unidade, id_catalogo)
        cur.execute(
            """SELECT i.id FROM catalogo_itens i JOIN catalogo_categorias g ON g.id = i.id_categoria
                 LEFT JOIN catalogo_subcategorias s ON s.id = i.id_subcategoria
                 JOIN produtos p ON p.id = i.id_produto
                WHERE g.id_catalogo = %s AND p.ativo
                ORDER BY g.ordem, lower(g.nome), s.ordem NULLS FIRST, lower(s.nome), i.ordem, lower(p.nome)""",
            (id_catalogo,))
        if [r["id"] for r in cur.fetchall()] == ordem:
            raise HTTPException(status_code=409,
                                detail="A ordem sugerida é igual à atual — não há o que comparar ainda.")
        nome, id_produto, ordem_b = "Ordem atual × ordem sugerida", None, json.dumps(ordem)
    cur.execute("SAVEPOINT teste_novo")
    try:
        cur.execute(
            """INSERT INTO cardapio_testes (id_unidade, id_catalogo, tipo, nome, id_produto, ordem_b,
                                            criado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (id_unidade, id_catalogo, dados["tipo"], nome, id_produto, ordem_b, id_usuario))
    except Exception as e:  # noqa: BLE001 - o índice único é quem garante; aqui se explica
        cur.execute("ROLLBACK TO SAVEPOINT teste_novo")
        if "ux_teste" in str(e):
            raise HTTPException(status_code=409, detail="Já existe um teste aberto para isto.")
        raise
    return obter(cur, id_unidade, cur.fetchone()["id"]) | {"message": f"Teste “{nome}” começou."}


def _teste(cur, id_unidade: int, id_teste: int, travar: bool = False) -> dict:
    cur.execute("SELECT * FROM cardapio_testes WHERE id = %s AND id_unidade = %s"
                + (" FOR UPDATE" if travar else ""), (id_teste, id_unidade))
    t = cur.fetchone()
    if not t:
        raise HTTPException(status_code=404, detail="Teste não encontrado.")
    return dict(t)


def encerrar(cur, id_unidade: int, id_teste: int, id_usuario: int) -> dict:
    """Fecha o teste e grava o vencedor — só se o resultado for conclusivo."""
    t = _teste(cur, id_unidade, id_teste, travar=True)
    if t["encerrado_em"]:
        raise HTTPException(status_code=409, detail="Este teste já foi encerrado.")
    r = resultado(cur, t)
    vencedor = {"A_VENCE": "A", "B_VENCE": "B"}.get(r["conclusao"])
    cur.execute("""UPDATE cardapio_testes SET encerrado_em = now(), encerrado_por = %s, vencedor = %s
                    WHERE id = %s""", (id_usuario, vencedor, id_teste))
    return obter(cur, id_unidade, id_teste) | {"message": "Teste encerrado."}


def aplicar(cur, id_unidade: int, id_teste: int, variante: str, id_usuario: int) -> dict:
    """Leva ao cardápio a variante escolhida (normalmente a vencedora) e encerra o teste.

    MÍDIA B = o prato passa a mostrar a FOTO no feed (`midia_preferida`); A = volta ao vídeo.
    ORDEM B = a ordem congelada vira a ordem do catálogo (passo 10, lista a lista); A = nada.
    """
    t = _teste(cur, id_unidade, id_teste, travar=True)
    if not t["encerrado_em"]:
        encerrar(cur, id_unidade, id_teste, id_usuario)
    if t["tipo"] == "MIDIA":
        cur.execute("""UPDATE catalogo_itens SET midia_preferida = %s
                        WHERE id_produto = %s AND id_categoria IN
                              (SELECT id FROM catalogo_categorias WHERE id_catalogo = %s)""",
                    ("FOTO" if variante == "B" else None, t["id_produto"], t["id_catalogo"]))
    elif variante == "B":
        cur.execute("""SELECT i.id, i.id_categoria, i.id_subcategoria FROM catalogo_itens i
                         JOIN catalogo_categorias g ON g.id = i.id_categoria
                        WHERE g.id_catalogo = %s""", (t["id_catalogo"],))
        lista_de = {r["id"]: (r["id_categoria"], r["id_subcategoria"]) for r in cur.fetchall()}
        contagem: dict[tuple, int] = {}
        for id_item in t["ordem_b"] or []:
            if id_item not in lista_de:  # saiu do cardápio durante o teste
                continue
            chave = lista_de[id_item]
            contagem[chave] = contagem.get(chave, 0) + 10
            cur.execute("UPDATE catalogo_itens SET ordem = %s WHERE id = %s",
                        (min(contagem[chave], 999), id_item))
    cur.execute("UPDATE cardapio_testes SET aplicado_em = now() WHERE id = %s", (id_teste,))
    rotulo = ROTULOS[t["tipo"]][variante]
    return obter(cur, id_unidade, id_teste) | {"message": f"Aplicado: {rotulo}."}


# ---------------------------------------------------------------- o resultado

def _proporcoes(n_a: int, s_a: int, n_b: int, s_b: int) -> dict:
    """Teste de duas proporções (bicaudal). Devolve as taxas, o p-valor e a conclusão."""
    ta = s_a / n_a if n_a else None
    tb = s_b / n_b if n_b else None
    if n_a < MIN_POR_BRACO or n_b < MIN_POR_BRACO:
        return {"taxa_a": ta, "taxa_b": tb, "p_valor": None, "conclusao": "AMOSTRA_PEQUENA"}
    p = (s_a + s_b) / (n_a + n_b)
    erro = math.sqrt(p * (1 - p) * (1 / n_a + 1 / n_b))
    if erro == 0:
        return {"taxa_a": ta, "taxa_b": tb, "p_valor": 1.0, "conclusao": "SEM_DIFERENCA"}
    z = (tb - ta) / erro
    p_valor = math.erfc(abs(z) / math.sqrt(2))
    if p_valor >= SIGNIFICANCIA:
        conclusao = "SEM_DIFERENCA"
    else:
        conclusao = "B_VENCE" if tb > ta else "A_VENCE"
    return {"taxa_a": ta, "taxa_b": tb, "p_valor": round(p_valor, 4), "conclusao": conclusao}


def resultado(cur, t: dict) -> dict:
    """Por braço: sessões EXPOSTAS e quantas adicionaram.

    🔑 **Exposta** = no teste de mídia, a sessão que VIU o prato; no de ordem, a que viu
    qualquer prato do cardápio. **Adicionou** = adicionou aquele prato (mídia) ou qualquer um
    (ordem). Só eventos dentro do período do teste e da loja dele.
    """
    variante = SQL_VARIANTE.format(sessao="e.id_sessao", teste="%(t)s")
    filtro_prod = "AND e.id_produto = %(p)s" if t["tipo"] == "MIDIA" else ""
    cur.execute(
        f"""WITH s AS (
                SELECT e.id_sessao, {variante} AS variante,
                       bool_or(e.tipo = 'viu_item' {filtro_prod}) AS viu,
                       bool_or(e.tipo = 'adicionou' {filtro_prod}) AS adicionou
                  FROM cardapio_eventos e
                 WHERE e.id_unidade = %(u)s AND e.quando >= %(de)s
                   AND (%(ate)s::timestamptz IS NULL OR e.quando <= %(ate)s)
                   -- 🔑 Só o cardápio do teste (122): ver o catering não expõe ninguém à ordem B
                   AND coalesce(e.id_catalogo, %(c)s) = %(c)s
                 GROUP BY e.id_sessao)
            SELECT variante, count(*) FILTER (WHERE viu) AS expostas,
                   count(*) FILTER (WHERE viu AND adicionou) AS adicionaram
              FROM s GROUP BY variante""",  # noqa: S608 - expressão constante do módulo
        {"t": t["id"], "p": t["id_produto"], "u": t["id_unidade"], "de": t["inicio"],
         "ate": t["encerrado_em"], "c": t["id_catalogo"]})
    braco = {r["variante"]: r for r in cur.fetchall()}
    a, b = braco.get("A", {}), braco.get("B", {})
    n_a, s_a = int(a.get("expostas") or 0), int(a.get("adicionaram") or 0)
    n_b, s_b = int(b.get("expostas") or 0), int(b.get("adicionaram") or 0)
    return {"A": {"rotulo": ROTULOS[t["tipo"]]["A"], "sessoes": n_a, "adicionaram": s_a},
            "B": {"rotulo": ROTULOS[t["tipo"]]["B"], "sessoes": n_b, "adicionaram": s_b},
            "minimo_por_braco": MIN_POR_BRACO, **_proporcoes(n_a, s_a, n_b, s_b)}


def _linha(cur, t: dict) -> dict:
    return {
        "id": t["id"], "tipo": t["tipo"], "nome": t["nome"], "id_produto": t["id_produto"],
        "inicio": t["inicio"], "encerrado_em": t["encerrado_em"], "vencedor": t["vencedor"],
        "aplicado_em": t["aplicado_em"], "aberto": t["encerrado_em"] is None,
        "resultado": resultado(cur, t),
    }


def obter(cur, id_unidade: int, id_teste: int) -> dict:
    return _linha(cur, _teste(cur, id_unidade, id_teste))


def listar(cur, id_unidade: int) -> list[dict]:
    cur.execute("""SELECT * FROM cardapio_testes WHERE id_unidade = %s
                    ORDER BY encerrado_em IS NOT NULL, inicio DESC LIMIT 50""", (id_unidade,))
    return [_linha(cur, dict(t)) for t in cur.fetchall()]


# ---------------------------------------------------------------- sugestões de destaque

def sugestoes_destaque(cur, id_unidade: int, de, ate) -> list[dict]:
    """Pôr e tirar destaque, com o motivo — para o gerente aprovar (decisão do dono).

    🔑 **Pôr**: o painel diz DESTACAR (margem alta ou lançamento/girar estoque com pouca
    atenção) e o prato não está em destaque. **Tirar**: está em destaque e mesmo assim é
    candidato a sair, ou tem margem BAIXA sem ser lançamento — destaque é vitrine cara.
    """
    p = cardapio_atencao.painel(cur, id_unidade, de, ate)
    saida = []
    for l in p["itens"]:
        if l["sugestao"] == "DESTACAR" and not l["destaque"]:
            motivo = ("lançamento com pouca atenção" if l["objetivo"] == "LANCAMENTO"
                      else "girar estoque com pouca atenção" if l["objetivo"] == "GIRAR_ESTOQUE"
                      else "margem alta e pouca atenção")
            saida.append({"id_item": l["id_item"], "nome": l["nome"], "acao": "POR",
                          "motivo": motivo, "prioridade": l["prioridade"]})
        elif l["destaque"] and (l["sugestao"] == "SAIR"
                                or (l["margem_nivel"] == "BAIXA" and l["objetivo"] != "LANCAMENTO")):
            motivo = ("em destaque e mesmo assim pouca atenção e pouca venda" if l["sugestao"] == "SAIR"
                      else "em destaque com margem baixa")
            saida.append({"id_item": l["id_item"], "nome": l["nome"], "acao": "TIRAR",
                          "motivo": motivo, "prioridade": l["prioridade"]})
    return sorted(saida, key=lambda s: (s["acao"] != "POR", -s["prioridade"], s["nome"]))


def aplicar_destaques(cur, id_unidade: int, escolhas: list[dict]) -> dict:
    """Aplica as sugestões aprovadas — pela MESMA porta da marca manual do catálogo."""
    feitos = []
    for e in escolhas:
        r = catalogo_conteudo.marcar_item(cur, id_unidade, e["id_item"], {"destaque": e["destaque"]})
        feitos.append({"id_item": e["id_item"], "antes": r["antes"]["destaque"], "depois": r["destaque"]})
    return {"feitos": feitos, "message": f"{len(feitos)} destaque(s) atualizado(s)."}
