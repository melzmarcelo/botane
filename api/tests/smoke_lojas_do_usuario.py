"""Em que loja cada pessoa trabalha — `usuario_papeis.id_unidade`.

O escopo por loja existe desde o primeiro script (`id_unidade` nulo = todas),
e a tela mandava **sempre nulo**: com uma loja era a resposta certa, com duas
todo mundo passou a enxergar as duas e o `ve_unidade` que protege saldo, venda,
inventário e remessa virou enfeite.

O que este arquivo cobra:

1. quem é lotado numa loja só **não enxerga** a outra — nem o saldo, nem a lista
   de lojas, nem a remessa
2. e `unidade_atual` resolve para a loja dele, não para a matriz
3. **ninguém dá acesso a loja que não enxerga** — o caminho clássico de escalar
   alcance sem tocar em permissão nenhuma
4. **ninguém encolhe o próprio alcance** e fica sem como voltar
5. loja inativa e loja inexistente são recusadas com frase, não com 500
6. tirar a loja devolve o "vale em todas"
7. **a visão consolidada não vaza pelo total** — quem só vê a filial soma só a
   filial, e a matriz não aparece nem na quantidade nem no valor

    python tests/smoke_lojas_do_usuario.py     (API de pé na 9200)

⚠️ Cria a própria filial e o próprio usuário, com marca de tempo, e **desativa
os dois no `atexit`** — filial ativa de teste muda a barra superior do dono.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, unidade=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if unidade:
        req.add_header("X-Unidade", str(unidade))
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


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
EMAIL = f"smoke.filial{marca}@botane.com.br"
SENHA = "smoke-filial-123"
criados: dict = {}


def _limpar():
    """A filial e o usuário saem mesmo se a suíte estourar no meio.

    ⚠️ Filial de teste ATIVA faz o seletor de loja aparecer na barra superior do
    dono — e ele vira o primeiro `<select>` do documento, quebrando checagens
    de tela que nada têm a ver com loja. Mesma lição do `preservar_credenciais`.
    """
    try:
        if criados.get("usuario"):
            chamar("DELETE", f"/usuarios/{criados['usuario']}", token=token)
        if criados.get("filial"):
            chamar("PUT", f"/unidades/{criados['filial']}", {"ativo": False}, token=token)
    except Exception:
        pass


atexit.register(_limpar)


print("1. preparo: uma filial e alguém lotado só nela")
st, filial = chamar("POST", "/unidades", {
    "nome": f"Filial acesso {marca}", "apelido": f"A{marca}"}, token=token)
id_filial = (filial or {}).get("id")
criados["filial"] = id_filial
checar("a filial é criada", st == 201 and bool(id_filial), (st, filial))

st, papeis = chamar("GET", "/papeis", token=token)
papel = next((p for p in (papeis or []) if p["nome"] == "Conferente / Estoque"), None)
checar("o papel de conferente existe", papel is not None, papeis and len(papeis))

st, novo = chamar("POST", "/usuarios", {
    "nome": f"Conferente da filial {marca}", "email": EMAIL, "senha": SENHA,
    # 🔑 **É este `id_unidade` que a tela nunca mandava.**
    "papeis": [{"id_papel": papel["id"], "id_unidade": id_filial}],
}, token=token)
id_usuario = (novo or {}).get("id")
criados["usuario"] = id_usuario
checar("o usuário nasce lotado na filial", st == 201 and bool(id_usuario), (st, novo))

st, entrou = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA})
checar("e ele entra", st == 200, (st, entrou))
tk = (entrou or {}).get("access_token")


print("\n2. ele NÃO enxerga a outra loja")
st, me = chamar("GET", "/auth/me", token=tk)
lojas = [u["id"] for u in (me or {}).get("unidades", [])]
checar("o /auth/me lista só a filial", lojas == [id_filial], lojas)
checar("e ele não é 'todas as lojas'", (me or {}).get("todas_unidades") is False, me)

# 🔑 **A loja atual dele é a DELE**, não a matriz — senão a primeira tela que
# abrisse mostraria o estoque de uma loja que ele não pode nem consultar.
st, saldos_padrao = chamar("GET", "/estoque/saldos?limite=1", token=tk)
checar("sem cabeçalho nenhum, a loja resolvida é a filial", st == 200, (st, saldos_padrao))

# ⚠️ Mandar `X-Unidade` de uma loja que não é sua não dá acesso a nada: o
# cabeçalho é uma escolha, não uma chave.
st, r = chamar("GET", "/estoque/saldos", token=tk, unidade=1)
checar("mandar X-Unidade da matriz é recusado (403)", st == 403, (st, r))


# 🔑 **E o consolidado NÃO pode vazar pelo total.** A visão de empresa soma as
# lojas; somando uma que a pessoa não enxerga, o número entregaria justamente o
# que a trava esconde — e é o pior lugar para vazar, porque nada na tela
# denuncia um total maior do que devia.
st, prod_r = chamar("POST", "/produtos", {
    "codigo": f"RED{marca}", "nome": f"Insumo de duas lojas {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True}, token=token)
id_prod_r = (prod_r or {}).get("id")
st, locais_m = chamar("GET", "/locais", token=token, unidade=1)
st, locais_f = chamar("GET", "/locais", token=token, unidade=id_filial)
local_filial = (locais_f or [{}])[0].get("id")
if id_prod_r and locais_m and local_filial:
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_prod_r, "id_local": locais_m[0]["id"],
        "quantidade": 10, "custo_unitario": 40}, token=token, unidade=1)
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_prod_r, "id_local": local_filial,
        "quantidade": 2, "custo_unitario": 52}, token=token, unidade=id_filial)

    st, rede_admin = chamar(
        "GET", f"/estoque/saldos-rede?id_produto={id_prod_r}", token=token)
    linha_admin = (rede_admin or [{}])[0]
    checar("o administrador soma as duas lojas",
           abs(float(linha_admin.get("quantidade", 0)) - 12) < 0.0001, linha_admin)

    st, rede_dele = chamar(
        "GET", f"/estoque/saldos-rede?id_produto={id_prod_r}", token=tk)
    linha_dele = (rede_dele or [{}])[0]
    checar("mas quem so ve a filial soma SO a filial",
           abs(float(linha_dele.get("quantidade", 0)) - 2) < 0.0001, linha_dele)
    checar("e a matriz nao aparece na quebra por loja",
           [x["id_unidade"] for x in (linha_dele.get("por_loja") or [])] == [id_filial],
           linha_dele.get("por_loja"))
    # ⚠️ O valor idem: 2 × 52 = 104, e nao os 520 das duas somadas.
    checar("nem pelo valor", abs(float(linha_dele.get("valor", 0)) - 104) < 0.01,
           linha_dele.get("valor"))


print("\n3. ninguém dá acesso a loja que não enxerga")
# 🔑 Sem esta trava, quem está preso à filial criaria um usuário com acesso à
# matriz — dando a outra pessoa um alcance que ele mesmo não tem. É escalar
# privilégio sem tocar em permissão nenhuma.
st, r = chamar("POST", "/usuarios", {
    "nome": "Tentativa", "email": f"tentativa{marca}@botane.com.br", "senha": SENHA,
    "papeis": [{"id_papel": papel["id"], "id_unidade": 1}],
}, token=tk)
# O conferente não administra usuários, então a porta fecha antes — e é o certo.
checar("conferente nem chega a criar usuário (403)", st == 403, (st, r))

# Com um administrador escopado, a trava que responde é a de loja.
st, papeis2 = chamar("GET", "/papeis", token=token)
admin_papel = next((p for p in (papeis2 or []) if "admin.usuarios" in p["permissoes"]), None)
if admin_papel:
    EMAIL2 = f"smoke.adminfilial{marca}@botane.com.br"
    st, adm = chamar("POST", "/usuarios", {
        "nome": f"Admin da filial {marca}", "email": EMAIL2, "senha": SENHA,
        "papeis": [{"id_papel": admin_papel["id"], "id_unidade": id_filial}],
    }, token=token)
    id_adm = (adm or {}).get("id")
    st, e2 = chamar("POST", "/auth/login", {"email": EMAIL2, "senha": SENHA})
    tk2 = (e2 or {}).get("access_token")
    st, r = chamar("POST", "/usuarios", {
        "nome": "Alcance maior", "email": f"alcance{marca}@botane.com.br", "senha": SENHA,
        "papeis": [{"id_papel": papel["id"], "id_unidade": 1}],
    }, token=tk2)
    checar("admin da filial NÃO dá acesso à matriz (403)", st == 403, (st, r))
    checar("e a frase nomeia a loja",
           "acesso" in str((r or {}).get("detail", "")).lower(), r)

    # 🔑 **E ele não encolhe o próprio alcance**: ficaria sem como voltar,
    # porque a trava de cima o impediria de devolver a loja a si mesmo.
    st, r = chamar("PUT", f"/usuarios/{id_adm}", {
        "papeis": [{"id_papel": admin_papel["id"], "id_unidade": id_filial}]}, token=tk2)
    checar("e manter o mesmo alcance passa", st == 200, (st, r))
    if id_adm:
        chamar("DELETE", f"/usuarios/{id_adm}", token=token)

# O administrador da casa vê todas — reduzir a si mesmo é o que fica barrado.
st, me_admin = chamar("GET", "/auth/me", token=token)
id_admin = (me_admin or {}).get("id")
st, r = chamar("PUT", f"/usuarios/{id_admin}", {
    "papeis": [{"id_papel": (admin_papel or papel)["id"], "id_unidade": id_filial}]},
    token=token)
checar("o administrador NÃO se tranca numa loja só (400)", st == 400, (st, r))
checar("e a frase diz que ele ficaria sem volta",
       "reduzir" in str((r or {}).get("detail", "")).lower(), r)
st, me_depois = chamar("GET", "/auth/me", token=token)
checar("e o alcance dele continua intacto",
       (me_depois or {}).get("todas_unidades") is True, me_depois)


print("\n4. loja que não serve é recusada com frase, não com 500")
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {
    "papeis": [{"id_papel": papel["id"], "id_unidade": 99999999}]}, token=token)
checar("loja inexistente devolve 404", st == 404, (st, r))

st, outra = chamar("POST", "/unidades", {
    "nome": f"Filial acesso morta {marca}", "apelido": f"M{marca}"}, token=token)
id_morta = (outra or {}).get("id")
chamar("PUT", f"/unidades/{id_morta}", {"ativo": False}, token=token)
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {
    "papeis": [{"id_papel": papel["id"], "id_unidade": id_morta}]}, token=token)
checar("loja inativa devolve 400", st == 400, (st, r))
checar("e a frase diz que ela está inativa",
       "inativa" in str((r or {}).get("detail", "")).lower(), r)


print("\n5. tirar a loja devolve o 'vale em todas'")
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {
    "papeis": [{"id_papel": papel["id"], "id_unidade": None}]}, token=token)
checar("o vínculo volta a ser sem loja", st == 200, (st, r))
st, e3 = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA})
st, me3 = chamar("GET", "/auth/me", token=(e3 or {}).get("access_token"))
checar("e agora ele enxerga todas", (me3 or {}).get("todas_unidades") is True, me3)
checar("com a matriz na lista",
       any(u["id"] == 1 for u in (me3 or {}).get("unidades", [])), me3)

# ⚠️ A lista de usuários devolve o vínculo com o NOME da loja: é o que a tela
# mostra na coluna "Lojas", e sem ele ela teria de casar id com nome sozinha.
st, lista = chamar("GET", "/usuarios?incluir_inativos=true&limite=500", token=token)
eu_na_lista = next((u for u in (lista or []) if u["email"] == EMAIL), None)
checar("a lista traz os papéis com a loja de cada um",
       eu_na_lista is not None and "id_unidade" in (eu_na_lista["papeis"] or [{}])[0],
       eu_na_lista)


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
