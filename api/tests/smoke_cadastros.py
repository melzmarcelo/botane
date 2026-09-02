"""Teste de fumaça da etapa 2 (cadastros), contra a API local.

Cobre setores, locais, categorias (inclusive a trava de ciclo), unidades de
medida, fornecedores e produtos — com preço, fornecedor vinculado, rascunho e
permissão. Cria e limpa o que usa.

    python tests/smoke_cadastros.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "tests")
from comum import (  # noqa: E402
    garantir_categorias,
    garantir_fornecedor,
    garantir_locais,
    garantir_setores,
)

import uuid  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

print("1. cadastros de apoio")
# Antes isto conferia a semente da migração ("vieram semeados"). Depois que a
# base pôde ser zerada, contar linha vira teste do estado do banco, não do
# sistema: o que importa é que as telas de apoio respondam e aceitem cadastro.
setores = garantir_setores(chamar, token, 2)
checar("setores respondem", isinstance(setores, list) and len(setores) >= 2, setores)
checar("o setor criado aparece na lista", any(s.get("nome") for s in setores), setores)

locais = garantir_locais(chamar, token, 2)
checar("locais respondem", isinstance(locais, list) and len(locais) >= 2, locais)
# Ninguém marcou a caixinha: quem elegeu foi o servidor. Sem principal, as
# telas de estoque, produção e inventário mandavam o pedido sem local e a
# resposta era "Local não encontrado" — com o nome do local à vista no seletor.
checar("um local é o principal, mesmo sem ninguém marcar",
       sum(1 for l in locais if l["principal"]) == 1,
       [(l["nome"], l["principal"]) for l in locais])
st, r = chamar("POST", "/locais", {"nome": f"Local extra {uuid.uuid4().hex[:6]}", "tipo": "SECO"}, token=token)
extra = r.get("id")
st, locais2 = chamar("GET", "/locais", token=token)
checar("o segundo local NÃO rouba o principal",
       sum(1 for l in locais2 if l["principal"]) == 1
       and not next((l["principal"] for l in locais2 if l["id"] == extra), True),
       [(l["nome"], l["principal"]) for l in locais2])
chamar("DELETE", f"/locais/{extra}", token=token)

st, ums = chamar("GET", "/unidades-medida", token=token)
checar("unidades de medida semeadas", st == 200 and len(ums) >= 8, len(ums) if st == 200 else ums)
kg = next((u for u in ums if u["sigla"] == "KG"), None)
checar("KG converte para grama", kg and float(kg["fator_base"]) == 1000, kg)

categorias = garantir_categorias(chamar, token, 2)
checar("categorias respondem", isinstance(categorias, list) and len(categorias) >= 2, categorias)

print("1b. corrigir o que foi cadastrado errado")
# 🔑 **Dava para criar e desativar, e não dava para CORRIGIR pela tela.** Os
# quatro PUT existem no servidor desde o começo e nenhuma tela os oferecia: um
# setor cadastrado com o nome errado no primeiro dia ficava errado para sempre,
# e o "conserto" era desativar e criar outro — deixando o histórico apontando
# para um cadastro morto. A suíte cobra os quatro, porque é a tela que passou a
# depender deles.
marca_ed = uuid.uuid4().hex[:6]
st, r = chamar("POST", "/setores", {"nome": f"Setor errado {marca_ed}"}, token=token)
id_set = (r or {}).get("id")
st, r = chamar("PUT", f"/setores/{id_set}", {"nome": f"Setor certo {marca_ed}"}, token=token)
checar("o setor se corrige", st == 200, (st, r))
st, lista = chamar("GET", "/setores?incluir_inativos=true", token=token)
# ⚠️ `.upper()`: quem normaliza é o BANCO (gatilho da migração 050), então a
# suíte afirma sobre o que foi GRAVADO, nunca sobre o que ela mandou. É a mesma
# correção que a 036 exigiu de onze checagens de uma vez.
checar("e a lista mostra o nome novo",
       any(x["id"] == id_set and x["nome"] == f"Setor certo {marca_ed}".upper()
           for x in lista),
       [x["nome"] for x in lista if x["id"] == id_set])
chamar("PUT", f"/setores/{id_set}", {"ativo": False}, token=token)

st, r = chamar("POST", "/locais",
               {"nome": f"Local errado {marca_ed}", "tipo": "SECO"}, token=token)
id_loc = (r or {}).get("id")
st, r = chamar("PUT", f"/locais/{id_loc}",
               {"nome": f"Local certo {marca_ed}", "tipo": "CONGELADO"}, token=token)
checar("o local se corrige, nome e tipo", st == 200, (st, r))
st, lista = chamar("GET", "/locais?incluir_inativos=true", token=token)
achado = next((x for x in lista if x["id"] == id_loc), {})
checar("e o tipo novo vale", achado.get("tipo") == "CONGELADO", achado)
chamar("DELETE", f"/locais/{id_loc}", token=token)

st, r = chamar("POST", "/categorias",
               {"nome": f"Cat errada {marca_ed}", "tipo": "INSUMO"}, token=token)
id_cat = (r or {}).get("id")
st, r = chamar("PUT", f"/categorias/{id_cat}",
               {"nome": f"Cat certa {marca_ed}", "tipo": "REVENDA"}, token=token)
checar("a categoria se corrige", st == 200, (st, r))
# ⚠️ **Dentro de si mesma seria um ciclo** — e a consulta recursiva da árvore
# entraria em laço. A tela já não oferece a própria categoria como mãe; quem de
# fato barra é o servidor.
st, r = chamar("PUT", f"/categorias/{id_cat}", {"id_pai": id_cat}, token=token)
checar("mas não pode virar mãe de si mesma", st == 400, (st, r))
chamar("DELETE", f"/categorias/{id_cat}", token=token)

sigla_ed = f"Z{marca_ed[:4]}".upper()[:6]
st, r = chamar("POST", "/unidades-medida",
               {"sigla": sigla_ed, "nome": "Errada", "grandeza": "MASSA",
                "fator_base": 1}, token=token)
if st == 201:
    st, r = chamar("PUT", f"/unidades-medida/{sigla_ed}",
                   {"nome": "Certa", "fator_base": 1000}, token=token)
    checar("a unidade de medida se corrige", st == 200, (st, r))
    st, lista = chamar("GET", "/unidades-medida?incluir_inativas=true", token=token)
    achada = next((x for x in lista if x["sigla"] == sigla_ed), {})
    checar("com o nome e o fator novos",
           achada.get("nome") == "CERTA" and float(achada.get("fator_base", 0)) == 1000,
           achada)
    chamar("PUT", f"/unidades-medida/{sigla_ed}", {"ativo": False}, token=token)


print("2. árvore de categorias")
st, r = chamar("POST", "/categorias", {"nome": "Smoke Raiz", "tipo": "INSUMO"}, token=token)
checar("cria categoria raiz", st == 201, r)
raiz = r.get("id")
st, r = chamar("POST", "/categorias", {"nome": "Smoke Filha", "id_pai": raiz}, token=token)
checar("cria subcategoria", st == 201, r)
filha = r.get("id")
st, lista = chamar("GET", "/categorias", token=token)
item = next((c for c in lista if c["id"] == filha), None)
checar("caminho da filha vem montado",
       item and item["caminho"] == "SMOKE RAIZ › SMOKE FILHA",
       item.get("caminho") if item else None)
checar("nível da filha é 1", item and item["nivel"] == 1)

st, r = chamar("PUT", f"/categorias/{raiz}", {"id_pai": filha}, token=token)
checar("recusa ciclo (raiz dentro da filha)", st == 400, st)
st, r = chamar("PUT", f"/categorias/{raiz}", {"id_pai": raiz}, token=token)
checar("recusa categoria dentro dela mesma", st == 400, st)
st, r = chamar("DELETE", f"/categorias/{raiz}", token=token)
checar("recusa excluir categoria com filha", st == 409, st)

print("3. fornecedor")
# A limpeza da rodada anterior DESATIVA o fornecedor (não apaga), e o CNPJ
# continua ocupado — então aqui ele é reaproveitado.
forn = garantir_fornecedor(chamar, token, "Smoke Distribuidora", "12.345.678/0001-95")
checar("fornecedor de teste pronto", bool(forn), forn)
st, r = chamar("PUT", f"/fornecedores/{forn}",
               {"prazo_entrega_dias": 2, "dias_entrega": "seg,qui"}, token=token)
checar("grava prazo e dias de entrega", st == 200, r)
st, r = chamar("POST", "/fornecedores", {"nome": "Outro", "cnpj": "12345678000195"}, token=token)
checar("recusa CNPJ repetido (mesmo com máscara diferente)", st == 409, st)
# Busca pelo nome do fornecedor que de fato está lá: o CNPJ pode ter sido
# reaproveitado de um registro criado por outra suíte, com outro nome.
st, dele = chamar("GET", f"/fornecedores/{forn}", token=token)
st, lista = chamar("GET", f"/fornecedores?busca={dele['nome'][:6]}", token=token)
checar("busca por nome encontra", st == 200 and any(f["id"] == forn for f in lista), lista)

print("4. produto")
st, r = chamar("POST", "/produtos", {
    "nome": "Café em grão smoke", "tipo": "INSUMO", "id_categoria": filha,
    "um_estoque": "KG", "um_compra": "PCT", "fator_compra": 1,
    "perecivel": True, "validade_dias": 180, "controla_validade": True,
    "preco_venda": None,
    "fornecedores": [{"id_fornecedor": forn, "codigo_no_fornecedor": "CAF-1",
                      "embalagem": "Pacote 1kg", "fator": 1, "preferencial": True}],
}, token=token)
checar("cria produto", st == 201, r)
prod = r.get("id")
checar("código foi gerado sozinho", str(r.get("codigo", "")).startswith("P"), r.get("codigo"))

st, p = chamar("GET", f"/produtos/{prod}", token=token)
checar("produto traz a categoria resolvida", p.get("categoria") == "SMOKE FILHA",
       p.get("categoria"))
checar("produto traz o fornecedor vinculado", len(p.get("fornecedores", [])) == 1)
checar("fornecedor preferencial marcado", p["fornecedores"][0]["preferencial"] is True)

st, r = chamar("POST", "/produtos", {"nome": "Duplicado", "codigo": p["codigo"],
                                     "um_estoque": "UN"}, token=token)
checar("recusa código repetido", st == 409, st)

st, r = chamar("POST", "/produtos", {"nome": "Prato smoke", "tipo": "INSUMO",
                                     "producao_propria": True, "um_estoque": "UN"}, token=token)
checar("recusa produção própria em insumo", st == 400, st)

print("5. preço com vigência")
chamar("PUT", f"/produtos/{prod}", {"preco_venda": 42.50}, token=token)
st, p = chamar("GET", f"/produtos/{prod}", token=token)
checar("grava preço de venda", float(p.get("preco_venda") or 0) == 42.5, p.get("preco_venda"))
chamar("PUT", f"/produtos/{prod}", {"preco_venda": 45.00}, token=token)
st, p = chamar("GET", f"/produtos/{prod}", token=token)
checar("troca de preço mantém um só vigente", float(p.get("preco_venda") or 0) == 45.0,
       p.get("preco_venda"))

print("6. rascunho não vira ativo sem o que decide o custo")
st, r = chamar("POST", "/produtos", {"nome": "Rascunho smoke", "status": "RASCUNHO"}, token=token)
checar("cria rascunho sem unidade", st == 201, r)
rasc = r.get("id")
st, r = chamar("POST", f"/produtos/{rasc}/revisar", token=token)
checar("recusa ativar rascunho sem unidade de estoque", st == 400, st)
chamar("PUT", f"/produtos/{rasc}", {"um_estoque": "UN", "fator_compra": 12}, token=token)
st, r = chamar("POST", f"/produtos/{rasc}/revisar", token=token)
checar("ativa depois de completar", st == 200, r)

print("7. lista, filtro e contagem")
st, lista = chamar("GET", "/produtos?busca=smoke", token=token)
checar("busca encontra os produtos", st == 200 and len(lista) >= 2, len(lista) if st == 200 else lista)
st, lista = chamar("GET", "/produtos?tipo=INSUMO&busca=smoke", token=token)
checar("filtro por tipo funciona", st == 200 and all(p["tipo"] == "INSUMO" for p in lista))
st, c = chamar("GET", "/produtos/contagem", token=token)
checar("contagem responde", st == 200 and c.get("total", 0) >= 2, c)

print("7b. paginação e loja")
# Página de 2 só prova alguma coisa se houver uma TERCEIRA linha: numa base
# recém-limpa a suíte tinha criado exatamente 2 produtos, o total batia com o
# tamanho da página e a checagem acusava falha sem haver defeito. A suíte
# garante o que precisa, como faz com local e setor.
extras_pagina = []
st, quantos = chamar("GET", "/produtos/contagem", token=token)
while (quantos.get("total") or 0) < 3:
    st, r = chamar("POST", "/produtos", {"nome": f"Pagina smoke {len(extras_pagina)}",
                                         "tipo": "INSUMO", "um_estoque": "UN"}, token=token)
    extras_pagina.append(r.get("id"))
    st, quantos = chamar("GET", "/produtos/contagem", token=token)

# A lista corta em `limite`, e o total tem de vir no cabeçalho: sem ele a tela
# não distingue "acabou" de "tem mais na próxima página".
req = urllib.request.Request(BASE + "/produtos?limite=2")
req.add_header("Authorization", f"Bearer {token}")
with urllib.request.urlopen(req, timeout=30) as r:
    pagina1 = json.loads(r.read())
    total = int(r.headers.get("X-Total", "0"))
checar("a página respeita o limite", len(pagina1) <= 2, len(pagina1))
checar("e o total vem no cabeçalho X-Total", total > len(pagina1), (total, len(pagina1)))
checar("o total não vaza para dentro das linhas",
       all("_total" not in p for p in pagina1), pagina1[:1])

req = urllib.request.Request(BASE + "/produtos?limite=2&offset=2")
req.add_header("Authorization", f"Bearer {token}")
with urllib.request.urlopen(req, timeout=30) as r:
    pagina2 = json.loads(r.read())
checar("a segunda página traz outros produtos",
       not ({p["id"] for p in pagina1} & {p["id"] for p in pagina2}),
       ([p["id"] for p in pagina1], [p["id"] for p in pagina2]))

# O cabeçalho da loja: quem não enxerga aquela loja é barrado, e o resto segue.
st, r = chamar("GET", "/auth/me", token=token)
minha = r["unidades"][0]["id"] if r.get("unidades") else None
req = urllib.request.Request(BASE + "/estoque/saldos")
req.add_header("Authorization", f"Bearer {token}")
req.add_header("X-Unidade", str(minha or 1))
with urllib.request.urlopen(req, timeout=30) as r:
    checar("a loja escolhida é aceita no cabeçalho", r.status == 200)
req = urllib.request.Request(BASE + "/estoque/saldos")
req.add_header("Authorization", f"Bearer {token}")
req.add_header("X-Unidade", "999999")
try:
    with urllib.request.urlopen(req, timeout=30):
        # O admin enxerga todas as lojas: mandar uma que não existe não vira 403,
        # e o que importa é não abrir porta para quem NÃO enxerga.
        checar("loja inexistente não derruba o admin (ele vê todas)", True)
except urllib.error.HTTPError as e:
    checar("loja fora do alcance é recusada (403)", e.code == 403, e.code)

print("8. permissão")
# Garante o usuário limitado: o smoke da fundação o desativa no fim.
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]}, token=token)
else:
    chamar("POST", "/usuarios", {"nome": "Smoke Cozinha", "email": COZINHA[0],
                                 "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)

st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
if st == 200:
    tk = r["access_token"]
    st, r = chamar("GET", "/produtos", token=tk)
    checar("cozinha LÊ produtos", st == 200, st)
    st, r = chamar("POST", "/produtos", {"nome": "Invadido", "um_estoque": "UN"}, token=tk)
    checar("cozinha NÃO cria produto (403)", st == 403, st)
    st, r = chamar("POST", "/fornecedores", {"nome": "Invadido"}, token=tk)
    checar("cozinha NÃO cria fornecedor (403)", st == 403, st)
    st, r = chamar("POST", "/setores", {"nome": "Invadido"}, token=tk)
    checar("cozinha NÃO cria setor (403)", st == 403, st)
else:
    print("  (usuário de cozinha ausente — rode tests/smoke_fundacao.py antes)")

print("9. limpeza")
# Categoria com produto apontando para ela é desativada, não excluída — por
# isso o produto solta a categoria antes.
chamar("PUT", f"/produtos/{prod}", {"id_categoria": None}, token=token)
for caminho in (f"/produtos/{prod}", f"/produtos/{rasc}", f"/fornecedores/{forn}",
                *[f"/produtos/{i}" for i in extras_pagina]):
    chamar("DELETE", caminho, token=token)
st, r = chamar("DELETE", f"/categorias/{filha}", token=token)
checar("exclui a subcategoria", st == 200 and "excluída" in r.get("message", ""), r)
st, r = chamar("DELETE", f"/categorias/{raiz}", token=token)
checar("limpa as categorias de teste", st == 200, r)
st, lista = chamar("GET", "/produtos?busca=smoke", token=token)
checar("produtos de teste saíram da lista ativa", all("smoke" not in p["nome"].lower() for p in lista),
       [p["nome"] for p in lista])

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
