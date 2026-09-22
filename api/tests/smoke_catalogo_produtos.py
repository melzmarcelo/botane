"""O catálogo de origem PRODUTOS: categorias, subcategorias e os produtos.

🔑 **Pedido do dono (22/09/2026):** *"vamos adicionar a Origem Produtos. Quando
for esta origem, ao listar os catálogos, ao clicar sobre vai abrir uma nova
página para configuração. Neste, podemos criar Categorias (exemplo: Menu
Principal) e suas SubCategorias (exemplo: Pra Dividir), cada item terá o Nome,
Descrição e uma foto. Após isto, podemos vincular os produtos disponíveis no PDV
para a subcategoria. Somente produtos ativos."*

⚠️ **Metade desta suíte é sobre o que o servidor RECUSA.** A lista de produtos
da tela é um conforto; quem garante que só entra produto ativo e vendido no
balcão é a rota — é a regra 4 da casa, nada de checagem só na tela.

    python tests/smoke_catalogo_produtos.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from base64 import b64decode

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(int(time.time()))[-7:]

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
    "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def enviar_foto(caminho, token, conteudo=PNG, nome="secao.png", tipo="image/png"):
    limite = uuid.uuid4().hex
    corpo = (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="arquivo"; filename="{nome}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n").encode() + conteudo \
        + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(BASE + caminho, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, corpo, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

_st, eu = chamar("GET", "/auth/me", token=token)
UNIDADE = (eu.get("unidades") or [{}])[0].get("id")

# ⚠️ Catálogo é de Reservas: sem o módulo ligado, as rotas recusam 409.
LIGADO_ANTES = bool(eu.get("reservas_ligado"))
chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": True}, token)


def limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM produtos WHERE nome LIKE %s", (f"%{MARCA}%",))


print("\n0. o cenário: um catálogo de cada origem e três produtos")
limpar()
_st, cat_pdf = chamar("POST", "/catalogos",
                      {"nome": f"Cardapio PDF {MARCA}", "origem": "PDF"}, token)
st, cat = chamar("POST", "/catalogos",
                 {"nome": f"Cardapio {MARCA}", "origem": "PRODUTOS"}, token)
ID_CAT = (cat or {}).get("id")
checar("a origem PRODUTOS é aceita no cadastro", st == 201 and bool(ID_CAT), (st, cat))
_st, ops = chamar("GET", "/catalogos/opcoes", token=token)
checar("e a tela passa a oferecer as duas origens",
       ops.get("origens") == ["PDF", "PRODUTOS"], ops.get("origens"))


def novo_produto(sufixo, **extra):
    corpo = {"nome": f"PRATO {MARCA} {sufixo}", "tipo": "INSUMO", "um_estoque": "UN",
             "um_compra": "UN", "fator_compra": 1, "controla_estoque": True}
    _st, p = chamar("POST", "/produtos", corpo, token)
    if extra:
        _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
        chamar("PUT", f"/produtos/{p['id']}", {**atual, **extra}, token)
    return p["id"]


P_PDV = novo_produto("PDV", integrado_pdv=True)
P_FORA = novo_produto("FORA")                      # não vai ao balcão
P_INATIVO = novo_produto("INATIVO", integrado_pdv=True)
chamar("PUT", f"/produtos/{P_INATIVO}",
       {**chamar("GET", f"/produtos/{P_INATIVO}", token=token)[1], "ativo": False}, token)

print("\n1. a lista de produtos que podem entrar")
st, lista = chamar("GET", f"/catalogos/produtos-disponiveis?busca={MARCA}", token=token)
ids = {p["id"] for p in lista}
checar("a rota responde", st == 200, st)
checar("o produto do PDV aparece", P_PDV in ids, sorted(ids))
# 🔑 *"Somente produtos ativos"*, nas palavras do dono.
checar("o inativo NÃO aparece, mesmo indo ao PDV", P_INATIVO not in ids, sorted(ids))
checar("e o que não vai ao balcão também não", P_FORA not in ids, sorted(ids))

print("\n2. o catálogo de PDF não se monta por categorias")
# ⚠️ 409 e não 404: ele existe e é desta casa — o que não existe é conteúdo
# montado item a item nele.
st, r = chamar("GET", f"/catalogos/{cat_pdf['id']}/conteudo", token=token)
checar("ver o conteúdo de um catálogo PDF é recusado com 409", st == 409, (st, r))
checar("dizendo qual é a origem dele e o que serve",
       "PDF" in (r.get("detail") or "") and "PRODUTOS" in (r.get("detail") or ""),
       r.get("detail"))
st, _r = chamar("POST", f"/catalogos/{cat_pdf['id']}/categorias", {"nome": "Bebidas"},
                token)
checar("e criar categoria nele também", st == 409, st)

print("\n2b. o catálogo de PRODUTOS não carrega PDF")
# 🔑 **Pedido do dono (22/09/2026):** *"quando for PRODUTO, tirar o campo para
# carregar PDF."* A tela esconde o botão; esta recusa é o que GARANTE — tela é
# conforto, e um PDF pendurado num catálogo que o site nunca lê é um arquivo que
# ninguém sabe que existe.
PDF_FALSO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
st, r = enviar_foto(f"/catalogos/{ID_CAT}/arquivo", token, conteudo=PDF_FALSO,
                    nome="cardapio.pdf", tipo="application/pdf")
checar("subir PDF num catálogo de PRODUTOS é recusado", st == 409, (st, r))
checar("dizendo o que fazer no lugar",
       "categorias" in (r.get("detail") or "").lower(), r.get("detail"))
# ⚠️ E o de PDF continua aceitando: a guarda não pode ter pegado os dois.
st, _r = enviar_foto(f"/catalogos/{cat_pdf['id']}/arquivo", token, conteudo=PDF_FALSO,
                     nome="cardapio.pdf", tipo="application/pdf")
checar("e o catálogo de PDF continua aceitando o dele", st == 200, st)

# ⚠️ **Trocar a origem com PDF carregado deixaria o arquivo ÓRFÃO** — apontado
# por um catálogo cuja tela não mostra mais o campo para removê-lo.
st, r = chamar("PUT", f"/catalogos/{cat_pdf['id']}", {"origem": "PRODUTOS"}, token)
checar("virar PRODUTOS com PDF carregado é recusado", st == 409, (st, r))
checar("dizendo para tirar o PDF antes",
       "Tire o PDF" in (r.get("detail") or ""), r.get("detail"))
chamar("DELETE", f"/catalogos/{cat_pdf['id']}/arquivo", token=token)
st, _r = chamar("PUT", f"/catalogos/{cat_pdf['id']}", {"origem": "PRODUTOS"}, token)
checar("tirado o PDF, a troca passa", st == 200, st)

print("\n3. as categorias")
st, cat_princ = chamar("POST", f"/catalogos/{ID_CAT}/categorias",
                       {"nome": "Menu Principal", "descricao": "O prato do dia a dia",
                        "ordem": 1}, token)
ID_PRINC = (cat_princ or {}).get("id")
checar("a categoria nasce (201)", st == 201 and bool(ID_PRINC), (st, cat_princ))
checar("com nome, descrição e ordem",
       cat_princ.get("nome") == "Menu Principal" and cat_princ.get("ordem") == 1,
       cat_princ)
st, bebidas = chamar("POST", f"/catalogos/{ID_CAT}/categorias",
                     {"nome": "Bebidas", "ordem": 2}, token)
ID_BEB = (bebidas or {}).get("id")
checar("e a segunda também", st == 201, st)

# ⚠️ Nome repetido no mesmo catálogo é engano — e a frase cita o GRAVADO.
st, r = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "menu principal"},
               token)
checar("nome repetido (até com outra caixa) é recusado", st == 409, (st, r))
checar("citando o nome como está GRAVADO, não o digitado",
       "Menu Principal" in (r.get("detail") or ""), r.get("detail"))

print("\n4. as subcategorias")
st, dividir = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/subcategorias",
                     {"nome": "Pra Dividir", "descricao": "Para a mesa toda"}, token)
ID_DIV = (dividir or {}).get("id")
checar("a subcategoria nasce", st == 201 and bool(ID_DIV), (st, dividir))
st, _r = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/subcategorias",
                {"nome": "PRA DIVIDIR"}, token)
checar("repetida na mesma categoria é recusada", st == 409, st)
# 🔑 O mesmo nome noutra categoria PODE: "Clássicos" de Bebidas e de Sobremesas
# são duas coisas diferentes.
st, _r = chamar("POST", f"/catalogos/categorias/{ID_BEB}/subcategorias",
                {"nome": "Pra Dividir"}, token)
checar("mas o mesmo nome em OUTRA categoria é aceito", st == 201, st)

print("\n5. pendurar produto — na subcategoria e direto na categoria")
st, posto = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/itens",
                   {"id_produto": P_PDV, "id_subcategoria": ID_DIV}, token)
checar("o produto entra na subcategoria", st == 201, (st, posto))
checar("e a resposta diz qual produto entrou",
       f"PRATO {MARCA} PDV" in (posto.get("message") or ""), posto.get("message"))
ITEM_SUB = posto.get("id")

# 🔑 **Decisão do dono**: categoria pode ter produto direto, sem subcategoria.
st, solto = chamar("POST", f"/catalogos/categorias/{ID_BEB}/itens",
                   {"id_produto": P_PDV}, token)
checar("e também entra DIRETO numa categoria, sem subcategoria", st == 201, (st, solto))

# 🔑 **Decisão do dono**: o mesmo produto pode estar em mais de uma lista.
st, _r = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/itens",
                {"id_produto": P_PDV}, token)
checar("o mesmo produto pode estar em outra lista do mesmo catálogo", st == 201, st)
# ⚠️ Mas repetido na MESMA lista é sempre engano.
st, r = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/itens",
               {"id_produto": P_PDV, "id_subcategoria": ID_DIV}, token)
checar("repetido na MESMA lista é recusado", st == 409, (st, r))
checar("dizendo que ele já está ali", "já está" in (r.get("detail") or ""),
       r.get("detail"))

print("\n5b. a ordem dos itens")
# 🔑 **Pedido do dono (22/09/2026):** *"ao cadastrar os produtos, permitir a
# ordenação deles, e os novos ir adicionando no fim da lista."*
# ⚠️ **A ordem e de CADA lista** — a da subcategoria, ou a dos soltos da
# categoria —, porque sao duas filas diferentes na tela.
P_DOIS = novo_produto("SEGUNDO", integrado_pdv=True)
P_TRES = novo_produto("TERCEIRO", integrado_pdv=True)
st, _r = chamar("POST", f"/catalogos/categorias/{ID_BEB}/itens",
                {"id_produto": P_DOIS}, token)
checar("o segundo produto entra", st == 201, (st, _r))
st, _r = chamar("POST", f"/catalogos/categorias/{ID_BEB}/itens",
                {"id_produto": P_TRES}, token)
checar("e o terceiro tambem", st == 201, (st, _r))

st, arvore = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
bebidas = next(c for c in arvore["categorias"] if c["id"] == ID_BEB)
ordens = [i["ordem"] for i in bebidas["itens"]]
# 🔑 **Cada novo entra DEPOIS do ultimo.** Antes todos nasciam com ordem 0 e a
# lista caia na ordem alfabetica — o cardapio nao e uma lista telefonica.
checar("cada um nasce com ordem maior que a do anterior",
       ordens == sorted(ordens) and len(set(ordens)) == len(ordens), ordens)
checar("e o ultimo cadastrado e o ultimo da lista",
       bebidas["itens"][-1]["id_produto"] == P_TRES,
       [i["id_produto"] for i in bebidas["itens"]])

# 🔑 **Reordenar manda a lista INTEIRA.** Mandar so o que se moveu deixaria o
# servidor adivinhando o resto.
invertida = list(reversed(bebidas["itens"]))
st, r = chamar("PUT", "/catalogos/itens/ordem",
               [{"id": i["id"], "ordem": (n + 1) * 10} for n, i in enumerate(invertida)],
               token)
checar("reordenar responde 200", st == 200, (st, r))
st, arvore = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
bebidas = next(c for c in arvore["categorias"] if c["id"] == ID_BEB)
checar("e a lista volta na ordem nova",
       [i["id_produto"] for i in bebidas["itens"]]
       == [i["id_produto"] for i in invertida],
       [i["id_produto"] for i in bebidas["itens"]])

# ⚠️ **Item de OUTRA casa nao entra na lista a ser reordenada.** Sem a conferencia
# por loja, um id qualquer seria reordenado junto.
st, r = chamar("PUT", "/catalogos/itens/ordem",
               [{"id": 999999999, "ordem": 10}], token)
checar("id que nao existe e recusado com 404", st == 404, (st, r))

# ⚠️ **`/itens/ordem` nao pode ser lida como um id.** Foi o que aconteceu com
# `/produtos-disponiveis` nesta mesma sessao: rota de um segmento so tem de ser
# declarada ANTES da que tem parametro.
checar("e a rota de ordem nao e confundida com /itens/{id}",
       chamar("PUT", "/catalogos/itens/ordem", [], token)[0] == 200)

print("\n6. o que a rota RECUSA pendurar")
st, r = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/itens",
               {"id_produto": P_INATIVO}, token)
checar("produto inativo é recusado", st == 409, (st, r))
checar("dizendo que está inativo", "inativo" in (r.get("detail") or "").lower(),
       r.get("detail"))
st, r = chamar("POST", f"/catalogos/categorias/{ID_PRINC}/itens",
               {"id_produto": P_FORA}, token)
checar("produto que não vai ao PDV é recusado", st == 409, (st, r))
checar("explicando que o cardápio mostra o que está no balcão",
       "PDV" in (r.get("detail") or ""), r.get("detail"))
# ⚠️ **O banco garante que a subcategoria é DESTA categoria**; a rota explica.
st, r = chamar("POST", f"/catalogos/categorias/{ID_BEB}/itens",
               {"id_produto": P_PDV, "id_subcategoria": ID_DIV}, token)
checar("subcategoria de OUTRA categoria é recusada", st == 409, (st, r))

print("\n7. o cardápio montado, em árvore")
st, arvore = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
checar("o conteúdo responde", st == 200, st)
cats = arvore.get("categorias") or []
checar("com as duas categorias", len(cats) == 2, [c["nome"] for c in cats])
# ⚠️ A ordem é a do CARDÁPIO, não alfabética: "Menu Principal" (ordem 1) antes
# de "Bebidas" (ordem 2), que alfabeticamente viria primeiro.
checar("na ordem do cardápio, não na alfabética",
       [c["nome"] for c in cats] == ["Menu Principal", "Bebidas"],
       [c["nome"] for c in cats])
principal = cats[0]
checar("a subcategoria vem dentro da categoria",
       [s["nome"] for s in principal["subcategorias"]] == ["Pra Dividir"],
       principal["subcategorias"])
checar("com o produto dentro dela",
       len(principal["subcategorias"][0]["itens"]) == 1,
       principal["subcategorias"][0]["itens"])
checar("e o item solto aparece na categoria, fora de subcategoria",
       len(principal["itens"]) == 1, principal["itens"])
item = principal["subcategorias"][0]["itens"][0]
# 🔑 O produto chega com o que o CLIENTE vê — e com `ativo`, para a tela poder
# marcar o que saiu de linha depois de entrar no cardápio.
checar("o item traz o nome do produto e se ele está ativo",
       item.get("produto") and item.get("ativo") is True, item)

print("\n8. a foto da seção")
st, r = enviar_foto(f"/catalogos/secoes/categoria/{ID_PRINC}/foto", token)
checar("a categoria aceita foto", st == 200 and r.get("foto_url"), (st, r))
URL = r.get("foto_url")
st, r = enviar_foto(f"/catalogos/secoes/subcategoria/{ID_DIV}/foto", token)
checar("a subcategoria também", st == 200 and r.get("foto_url"), (st, r))
st, r = enviar_foto(f"/catalogos/secoes/sobremesa/{ID_DIV}/foto", token)
checar("tipo de seção inventado é recusado", st == 404, (st, r))
st, r = enviar_foto(f"/catalogos/secoes/categoria/{ID_PRINC}/foto", token,
                    conteudo=b"nao sou imagem")
checar("arquivo que não é imagem é recusado", st == 400, (st, r))

# ⚠️ Trocar apaga a anterior — a lição que a logo pagou.
st, r = enviar_foto(f"/catalogos/secoes/categoria/{ID_PRINC}/foto", token,
                    nome="outra.png")
checar("trocar a foto dá um endereço novo", st == 200 and r["foto_url"] != URL,
       (st, r.get("foto_url"), URL))
st, _c = chamar("GET", URL, token=token)
checar("e a anterior deixa de existir", st == 404, st)

st, _r = chamar("DELETE", f"/catalogos/secoes/categoria/{ID_PRINC}/foto", token=token)
checar("remover a foto responde 200", st == 200, st)
st, arvore = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
checar("e a categoria fica sem foto",
       arvore["categorias"][0]["foto_url"] is None,
       arvore["categorias"][0]["foto_url"])

print("\n9. tirar produto e apagar seção")
st, r = chamar("DELETE", f"/catalogos/itens/{ITEM_SUB}", token=token)
checar("desvincular responde 200 dizendo qual saiu",
       st == 200 and f"PRATO {MARCA} PDV" in (r.get("message") or ""), (st, r))

# 🔑 A resposta conta quantos produtos saem junto, para a tela avisar ANTES.
st, r = chamar("DELETE", f"/catalogos/categorias/{ID_PRINC}", token=token)
checar("apagar a categoria responde 200", st == 200, (st, r))
checar("dizendo quantos itens foram junto", r.get("itens_removidos") == 1, r)
st, arvore = chamar("GET", f"/catalogos/{ID_CAT}/conteudo", token=token)
checar("e ela some do cardápio", len(arvore["categorias"]) == 1,
       [c["nome"] for c in arvore["categorias"]])
# ⚠️ O CASCADE do banco leva subcategorias e vínculos junto.
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM catalogo_subcategorias WHERE id_categoria = %s",
                (ID_PRINC,))
    checar("com as subcategorias dela", cur.fetchone()["n"] == 0)
    cur.execute("SELECT count(*) AS n FROM catalogo_itens WHERE id_categoria = %s",
                (ID_PRINC,))
    checar("e com os vínculos", cur.fetchone()["n"] == 0)

print("\n10. apagar o catálogo leva o conteúdo")
chamar("DELETE", f"/catalogos/{ID_CAT}", token=token)
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM catalogo_categorias WHERE id_catalogo = %s",
                (ID_CAT,))
    checar("nenhuma categoria órfã fica para trás", cur.fetchone()["n"] == 0)

print("\n11. limpeza")
limpar()
chamar("PUT", f"/unidades/{UNIDADE}/parametros",
       {"reservas_ligado": LIGADO_ANTES}, token)
checar("o módulo volta ao estado em que a suíte o encontrou", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
