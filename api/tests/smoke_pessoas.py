"""Pessoas: o fornecedor virou gente, e a pessoa tem política de cupom.

🔑 **Pedido do dono (04/09/2026):** "hoje temos somente o cadastro de
fornecedores, podemos tratar ele como pessoa — visualmente no menu e no
cadastro; na base podemos manter a mesma estrutura. E gostaria de poder criar um
vínculo entre o usuário e a pessoa. No cadastro da pessoa, criar uma
configuração para o Cupom: se vai utilizar o preço de venda ou o custo, se vai
possuir um percentual de desconto."

E a regra, dita depois: **a venda lançada à mão sempre puxa o preço de venda**;
informando uma pessoa, olha a configuração — se for pelo custo, o custo entra no
lugar do preço; se houver desconto, aplica sobre o preço. Assim se tem o
desconto de funcionário e o consumo do proprietário com a mesma mecânica.

O que este arquivo cobra:

1. a pessoa que **não é fornecedor** some dos seletores de compra e continua na
   lista de Pessoas
2. o vínculo **usuário ↔ pessoa**, pelas duas portas — vincular uma existente ou
   criar na hora — e a recusa de mandar as duas juntas
3. uma pessoa, **um** usuário
4. as quatro políticas de cupom, com o valor gravado conferido
5. e a **frase**, porque um cupom que sai por outro valor sem explicar por quê é
   indistinguível de erro de digitação

    python tests/smoke_pessoas.py     (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&+")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
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


def perto(a, b, tol=0.01):
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
criados: dict = {"pessoas": [], "usuarios": [], "produtos": []}


def _limpar():
    try:
        for u in criados["usuarios"]:
            chamar("DELETE", f"/usuarios/{u}", token=token)
        for p in criados["produtos"]:
            chamar("DELETE", f"/produtos/{p}", token=token)
        for f in criados["pessoas"]:
            chamar("DELETE", f"/fornecedores/{f}", token=token)
    except Exception:
        pass


atexit.register(_limpar)


def nova_pessoa(nome, fornecedor=True, base="VENDA", desconto=0):
    st, r = chamar("POST", "/fornecedores", {
        "nome": nome, "fornecedor": fornecedor,
        "cupom_base": base, "cupom_desconto_pct": desconto}, token=token)
    idp = (r or {}).get("id")
    criados["pessoas"].append(idp)
    return idp


print("1. a pessoa que NAO vende para a casa")
so_gente = nova_pessoa(f"FUNCIONARIO {marca}", fornecedor=False)
fornece = nova_pessoa(f"FORNECEDOR {marca}", fornecedor=True)
checar("as duas nascem", bool(so_gente and fornece), (so_gente, fornece))

st, lista = chamar("GET", f"/fornecedores?busca={marca}", token=token)
checar("a lista de PESSOAS traz as duas", len(lista or []) == 2, lista and len(lista))
# 🔑 **O recorte que protege o seletor da nota.** Sem ele, quem lanca uma nota
# escolheria o fornecedor numa lista cheia de funcionarios.
st, so_forn = chamar("GET", f"/fornecedores?busca={marca}&so_fornecedores=true", token=token)
nomes = [x["nome"] for x in (so_forn or [])]
checar("mas o seletor de fornecedor so traz quem vende",
       nomes == [f"FORNECEDOR {marca}"], nomes)
# ⚠️ O padrao e VERDADEIRO: cadastro antigo continua aparecendo onde sempre
# apareceu, e e isso que faz esta mudanca nao mexer em nada de quem ja usa.
st, antigo = chamar("GET", f"/fornecedores/{fornece}", token=token)
checar("e quem nao disse nada e fornecedor", antigo.get("fornecedor") is True, antigo)


print("\n2. o vinculo entre o usuario e a pessoa")
st, papeis = chamar("GET", "/papeis", token=token)
papel = next(p["id"] for p in papeis if p["nome"] == "Cozinha")

# porta 1: criar a pessoa a partir do usuario
st, u1 = chamar("POST", "/usuarios", {
    "nome": f"Cria pessoa {marca}", "email": f"cria{marca}@botane.com.br",
    "senha": "pessoa-teste-123", "papeis": [{"id_papel": papel}],
    "pessoa_nova": {"nome": f"NASCIDA DO USUARIO {marca}",
                    "email": f"cria{marca}@botane.com.br"}}, token=token)
id_u1 = (u1 or {}).get("id")
criados["usuarios"].append(id_u1)
st, v1 = chamar("GET", f"/usuarios/{id_u1}", token=token)
checar("criar a pessoa a partir do usuario vincula as duas",
       bool(v1.get("id_pessoa")) and v1.get("pessoa") == f"NASCIDA DO USUARIO {marca}", v1)
criados["pessoas"].append(v1.get("id_pessoa"))
# 🔑 **Ela NAO nasce fornecedor**: quem cadastra um usuario esta cadastrando
# gente da casa, nao quem vende para ela.
st, nascida = chamar("GET", f"/fornecedores/{v1['id_pessoa']}", token=token)
checar("e a pessoa nascida assim NAO e fornecedor",
       nascida.get("fornecedor") is False, nascida.get("fornecedor"))

# porta 2: vincular uma que ja existe
st, u2 = chamar("POST", "/usuarios", {
    "nome": f"Vincula {marca}", "email": f"vinc{marca}@botane.com.br",
    "senha": "pessoa-teste-123", "papeis": [{"id_papel": papel}],
    "id_pessoa": so_gente}, token=token)
id_u2 = (u2 or {}).get("id")
criados["usuarios"].append(id_u2)
st, v2 = chamar("GET", f"/usuarios/{id_u2}", token=token)
checar("vincular uma pessoa existente funciona", v2.get("id_pessoa") == so_gente, v2)
# A pessoa passa a dizer quem entra como ela — e o contrario tambem.
st, pes = chamar("GET", f"/fornecedores/{so_gente}", token=token)
checar("e a pessoa passa a dizer quem entra como ela",
       pes.get("usuario") == f"Vincula {marca}", pes.get("usuario"))

# ⚠️ As duas portas juntas sao ambiguas — qual vale? A resposta honesta e
# recusar, nao escolher por quem pediu.
st, r = chamar("PUT", f"/usuarios/{id_u2}", {
    "id_pessoa": fornece, "pessoa_nova": {"nome": "OUTRA"}}, token=token)
checar("mandar as duas portas juntas e recusado", st == 400, (st, r))

# 🔑 Uma pessoa, UM usuario: dois logins na mesma pessoa fariam a politica de
# cupom dela responder por duas credenciais.
st, r = chamar("PUT", f"/usuarios/{id_u1}", {"id_pessoa": so_gente}, token=token)
checar("a mesma pessoa em dois usuarios e recusada", st == 409, (st, r))

# ⚠️ Zero DESVINCULA — nulo ja quer dizer "nao mexi" no PUT.
st, r = chamar("PUT", f"/usuarios/{id_u2}", {"id_pessoa": 0}, token=token)
st, v3 = chamar("GET", f"/usuarios/{id_u2}", token=token)
checar("e id_pessoa zero desvincula", v3.get("id_pessoa") is None, v3.get("id_pessoa"))


print("\n3. a politica de cupom na venda lancada a mao")
st, r = chamar("POST", "/produtos", {
    "codigo": f"PES-{marca}", "nome": f"PRATO PESSOA {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
    "preco_venda": 100}, token=token)
prod = (r or {}).get("id")
criados["produtos"].append(prod)
st, locais = chamar("GET", "/locais", token=token)
local = next((x for x in locais if x.get("principal")), locais[0])
chamar("POST", "/estoque/entradas", {
    "id_produto": prod, "quantidade": 20, "custo_unitario": 40,
    "id_local": local["id"]}, token=token)
checar("o produto vale 100 e custa 40", bool(prod), prod)

casos = [
    ("sem pessoa", None, 100.0, None),
    ("pelo custo", nova_pessoa(f"P CUSTO {marca}", False, "CUSTO", 0), 40.0, "CUSTO"),
    ("desconto 20", nova_pessoa(f"P DESC {marca}", False, "VENDA", 20), 80.0, "desconto"),
    ("custo -10", nova_pessoa(f"P AMBOS {marca}", False, "CUSTO", 10), 36.0, "CUSTO"),
]
for rotulo, id_pessoa, esperado, na_frase in casos:
    corpo = {"data": "2026-09-04", "documento": f"PES-{rotulo.replace(' ', '')}-{marca}",
             "origem": "MANUAL",
             "itens": [{"id_produto": prod, "quantidade": 1, "valor_unitario": 100}]}
    if id_pessoa:
        corpo["id_pessoa"] = id_pessoa
    st, r = chamar("POST", "/vendas/importar", {"vendas": [corpo]}, token=token)
    st, lista_v = chamar("GET", f"/vendas?busca={corpo['documento']}", token=token)
    valor = (lista_v or [{}])[0].get("valor_total")
    checar(f"{rotulo}: o cupom vale {esperado:g}", perto(valor, esperado), valor)
    if na_frase:
        # 🔑 **A frase, porque um cupom que sai por outro valor sem explicar por
        # que e indistinguivel de erro de digitacao.**
        checar(f"{rotulo}: e a resposta DIZ o que aplicou",
               na_frase.lower() in str((r or {}).get("message", "")).lower(),
               (r or {}).get("message"))

# ⚠️ Pessoa sem politica (VENDA, zero) nao anuncia ajuste nenhum: politica que
# nao muda nada devolvendo frase faria toda venda anunciar algo que nao houve.
neutra = nova_pessoa(f"P NEUTRA {marca}", False, "VENDA", 0)
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": "2026-09-04", "documento": f"PES-NEUTRA-{marca}", "origem": "MANUAL",
    "id_pessoa": neutra,
    "itens": [{"id_produto": prod, "quantidade": 1, "valor_unitario": 100}]}]}, token=token)
checar("pessoa sem politica nao anuncia ajuste", not (r or {}).get("politicas"),
       (r or {}).get("politicas"))

# ⚠️ Pessoa inexistente ou inativa e recusada — melhor a recusa que uma venda
# gravada pelo preco cheio quando quem lancou pediu o custo.
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": "2026-09-04", "documento": f"PES-X-{marca}", "origem": "MANUAL",
    "id_pessoa": 99999999,
    "itens": [{"id_produto": prod, "quantidade": 1, "valor_unitario": 100}]}]}, token=token)
checar("pessoa inexistente e recusada", st == 404, (st, r))


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
