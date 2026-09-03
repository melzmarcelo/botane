"""De que SETOR cada pessoa cuida — `usuario_setores`, e o painel que sai dela.

A tabela existe desde o script **004**, com o comentário "Restrição por setor
(o ajudante conta só a área dele). Sem linha = sem limite." — e ficou VAZIA
desde então: nenhuma tela oferecia o campo, nenhum endpoint a lia. É a mesma
história de `usuario_papeis.id_unidade`, que esperou a tela aparecer para valer
alguma coisa. Aqui ela passa a valer (pedido do dono, 03/09/2026).

O que este arquivo cobra:

1. o cadastro de usuário **grava e devolve** os setores da pessoa
2. `/auth/me` diz `todos_setores` — e com ele ligado oferece a lista INTEIRA,
   que é o que o formulário precisa para deixar marcar
3. o painel traz a agenda de produção **recortada pelo setor** de quem olha
4. **sem setor marcado, vem a casa inteira** — a convenção que faz o deploy não
   tirar nada de ninguém
5. **produto SEM setor aparece para todos**: ele não é de ninguém, e escondê-lo
   sumiria com a linha do painel da casa toda
6. lista vazia é "todos", não "nenhum" — e o PUT sem o campo NÃO apaga a escolha
7. setor inexistente e setor inativo são recusados com frase, não com 500
8. **ninguém encolhe o próprio alcance** e fica sem como voltar
9. **dinheiro continua obedecendo a `cmv.painel`**: quem não a tem recebe a
   agenda de produção e nenhum valor

    python tests/smoke_setor_do_usuario.py     (API de pé na 9200)

⚠️ Cria os próprios setores, produtos, fichas e usuário, com marca de tempo, e
desativa tudo no `atexit` — setor de teste ATIVO entra no seletor de todo
cadastro de produto.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

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
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
EMAIL = f"smoke.setor{marca}@botane.com.br"
SENHA = "smoke-setor-12345"
criados: dict = {"setores": [], "produtos": []}


def _limpar():
    """Tudo o que a suite criou sai — mesmo se ela estourar no meio.

    ⚠️ **Setor de teste ATIVO entra no seletor de todo cadastro de produto**, e
    a base ja carrega dezenas deles de rodadas antigas. E a mesma licao da
    filial que aparecia na barra superior do dono.
    """
    try:
        if criados.get("usuario"):
            chamar("DELETE", f"/usuarios/{criados['usuario']}", token=token)
        for p in criados["produtos"]:
            chamar("DELETE", f"/produtos/{p}", token=token)
        for s in criados["setores"]:
            chamar("DELETE", f"/setores/{s}", token=token)
    except Exception:
        pass


atexit.register(_limpar)


print("1. preparo: dois setores, um produto em cada e um sem setor nenhum")
setores = {}
for chave in ("MEU", "OUTRO"):
    st, s = chamar("POST", "/setores", {"nome": f"{chave} SETOR {marca}"}, token=token)
    setores[chave] = (s or {}).get("id")
    criados["setores"].append(setores[chave])
checar("os dois setores sao criados", all(setores.values()), setores)

st, locais = chamar("GET", "/locais", token=token)
local = next((x for x in (locais or []) if x.get("principal")), (locais or [{}])[0])

amanha = date.today() + timedelta(days=1)
produtos = {}
# ⚠️ O produto tem de ser de PRODUCAO PROPRIA e ter ficha homologada, senao o
# agendamento e recusado — e a agenda ficaria vazia por um motivo que nao tem
# nada a ver com setor. E a armadilha que a suite de producao ja pagou.
for chave, id_setor in (("MEU", setores["MEU"]), ("OUTRO", setores["OUTRO"]), ("SEM", None)):
    corpo = {
        "codigo": f"SET{chave}-{marca}", "nome": f"PREPARO {chave} {marca}",
        "tipo": "PRODUZIDO", "um_estoque": "KG", "controla_estoque": True,
        "status": "ATIVO",
    }
    if id_setor:
        corpo["id_setor"] = id_setor
    st, p = chamar("POST", "/produtos", corpo, token=token)
    produtos[chave] = (p or {}).get("id")
    criados["produtos"].append(produtos[chave])
checar("os tres produtos sao criados", all(produtos.values()), produtos)

st, insumo = chamar("POST", "/produtos", {
    "codigo": f"SETINS-{marca}", "nome": f"INSUMO SETOR {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO"}, token=token)
id_insumo = (insumo or {}).get("id")
criados["produtos"].append(id_insumo)

agendadas = {}
for chave, id_produto in produtos.items():
    # ⚠️ Os campos sao `rendimento_qtd`/`rendimento_um` e o item pede
    # `qtd_bruta` — nomes proprios da ficha. Adivinha-los fazia o POST voltar
    # 422 e a agenda ficar vazia, e a falha aparecia tres checagens adiante
    # dizendo que o painel nao recorta por setor.
    st, f = chamar("POST", "/fichas", {
        "id_produto": id_produto, "rendimento_qtd": 10, "rendimento_um": "KG",
        "porcoes": 1,
        "itens": [{"id_insumo": id_insumo, "qtd_bruta": 1, "um": "KG"}]}, token=token)
    id_ficha = (f or {}).get("id")
    chamar("POST", f"/fichas/{id_ficha}/homologar", token=token)
    st, a = chamar("POST", "/producao-agenda", {
        "id_produto": id_produto, "data_prevista": amanha, "quantidade": 3,
        "id_local": local.get("id")}, token=token)
    agendadas[chave] = (st, a)
checar("as tres linhas entram na agenda",
       all(v[0] == 201 for v in agendadas.values()), agendadas)


print("\n2. o cadastro do usuario GRAVA o setor")
st, papeis = chamar("GET", "/papeis", token=token)
papel = next((p for p in (papeis or []) if p["nome"] == "Cozinha"), None)
checar("o papel de cozinha existe", papel is not None, papeis and len(papeis))

st, novo = chamar("POST", "/usuarios", {
    "nome": f"Cozinha do setor {marca}", "email": EMAIL, "senha": SENHA,
    "papeis": [{"id_papel": papel["id"]}],
    # 🔑 **O campo que a tabela esperava desde o script 004.**
    "setores": [setores["MEU"]],
}, token=token)
id_usuario = (novo or {}).get("id")
criados["usuario"] = id_usuario
checar("o usuario nasce com o setor", st == 201 and bool(id_usuario), (st, novo))

st, lista = chamar("GET", "/usuarios?incluir_inativos=true&limite=500", token=token)
na_lista = next((u for u in (lista or []) if u["email"] == EMAIL), None)
checar("e a lista devolve o setor dele",
       [s["id"] for s in (na_lista or {}).get("setores") or []] == [setores["MEU"]],
       na_lista and na_lista.get("setores"))


print("\n3. /auth/me diz de que setor a pessoa cuida")
st, entrou = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA})
tk = (entrou or {}).get("access_token")
checar("ele entra", st == 200, (st, entrou))

st, me = chamar("GET", "/auth/me", token=tk)
checar("e NAO e 'todos os setores'", me.get("todos_setores") is False, me.get("todos_setores"))
checar("com o setor dele nomeado",
       [s["nome"] for s in me.get("setores") or []] == [f"MEU SETOR {marca}"], me.get("setores"))

# ⚠️ Com `todos_setores`, a lista vem CHEIA — e ela que o formulario oferece
# para marcar, e um administrador com lista vazia nao teria o que oferecer.
st, meu_admin = chamar("GET", "/auth/me", token=token)
checar("o administrador ve 'todos' e recebe a lista inteira para oferecer",
       meu_admin.get("todos_setores") is True and len(meu_admin.get("setores") or []) > 1,
       (meu_admin.get("todos_setores"), len(meu_admin.get("setores") or [])))


print("\n4. o painel traz a producao RECORTADA pelo setor")
st, painel = chamar("GET", "/inicio", token=tk)
prod = (painel or {}).get("producao")
checar("o painel da cozinha traz o bloco de producao", prod is not None, painel and list(painel))
nomes = [l["produto"] for l in (prod or {}).get("linhas") or []]
checar("com o preparo do setor dele", f"PREPARO MEU {marca}" in nomes, nomes)
# 🔑 **O recorte e o ponto do pedido**: sem ele, quem e da Confeitaria percorre
# a agenda do Bar inteira para achar as duas linhas que sao dela.
checar("e SEM o preparo do outro setor", f"PREPARO OUTRO {marca}" not in nomes, nomes)
# ⚠️ Produto sem setor nao e de ninguem: escode-lo sumiria com a linha do
# painel da casa toda, sem nada dizendo por que.
checar("o produto SEM setor aparece para ele", f"PREPARO SEM {marca}" in nomes, nomes)
checar("e a tela sabe que esta vendo um recorte",
       (prod or {}).get("todos_setores") is False, prod)

st, painel_admin = chamar("GET", "/inicio", token=token)
checar("quem nao tem setor marcado ve a casa inteira",
       (painel_admin.get("producao") or {}).get("todos_setores") is True,
       painel_admin.get("producao"))


print("\n5. dinheiro continua obedecendo a permissao")
# 🔑 A cozinha ganhou um painel util, e isso NAO pode ter aberto valor nenhum.
checar("a cozinha nao recebe dinheiro", painel.get("dinheiro") is None, painel.get("dinheiro"))
checar("nem o movimento do dia", painel.get("dia") is None, painel.get("dia"))
checar("nem o peso por setor", painel.get("pesos") == [], painel.get("pesos"))
# ⚠️ E nenhuma linha da agenda carrega custo — o bloco vale para quem nao ve valor.
checar("e nenhuma linha da agenda carrega valor",
       all(not any("custo" in k or "valor" in k for k in l)
           for l in (prod or {}).get("linhas") or []),
       (prod or {}).get("linhas"))
st, negado = chamar("GET", "/inicio/dia", token=tk)
checar("o endpoint do dia recusa quem nao ve dinheiro", st == 403, (st, negado))


print("\n6. lista vazia e TODOS; ausente e 'nao mexi'")
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {"setores": []}, token=token)
checar("gravar lista vazia responde", st == 200, (st, r))
st, me2 = chamar("GET", "/auth/me", token=tk)
checar("e devolve a pessoa para 'todos os setores'",
       me2.get("todos_setores") is True, me2.get("todos_setores"))

chamar("PUT", f"/usuarios/{id_usuario}", {"setores": [setores["MEU"]]}, token=token)
# ⚠️ **O PUT sem o campo NAO pode apagar a escolha** — e o que uma tela antiga
# manda, e apagar em silencio desfaria o que alguem acabou de configurar.
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {"telefone": "11999999999"}, token=token)
st, me3 = chamar("GET", "/auth/me", token=tk)
checar("PUT sem o campo preserva o setor",
       me3.get("todos_setores") is False
       and [s["id"] for s in me3.get("setores") or []] == [setores["MEU"]],
       me3.get("setores"))


print("\n7. setor inexistente e inativo sao recusados com frase")
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {"setores": [99999999]}, token=token)
checar("setor inexistente devolve 404, nao 500", st == 404, (st, r))

st, s_inativo = chamar("POST", "/setores", {"nome": f"INATIVO SETOR {marca}"}, token=token)
id_inativo = (s_inativo or {}).get("id")
criados["setores"].append(id_inativo)
# ⚠️ **`DELETE /setores` APAGA o setor que nunca foi usado** e so desativa o que
# tem produto — "nunca apaga o que ja foi usado: o historico ficaria sem nome".
# Sem este produto, o setor sumia da tabela e a recusa vinha como 404 "nao
# encontrado", que e outra afirmacao: o teste mediria o caso errado.
chamar("PUT", f"/produtos/{produtos['SEM']}", {"id_setor": id_inativo}, token=token)
chamar("DELETE", f"/setores/{id_inativo}", token=token)
st, r = chamar("PUT", f"/usuarios/{id_usuario}", {"setores": [id_inativo]}, token=token)
checar("setor inativo devolve 400 com a frase", st == 400, (st, r))
checar("dizendo que esta inativo", "inativo" in str((r or {}).get("detail", "")).lower(), r)


print("\n8. ninguem encolhe o PROPRIO alcance")
# 🔑 Quem se restringisse perderia os outros de vista — e a trava de cima o
# impediria de devolve-los a si mesmo. Mesmo erro que a loja ja paga.
st, eu_admin = chamar("GET", "/auth/me", token=token)
st, r = chamar("PUT", f"/usuarios/{eu_admin['id']}", {"setores": [setores["MEU"]]}, token=token)
checar("o administrador nao se tranca num setor", st == 400, (st, r))
checar("com a frase dizendo por que",
       "voltar" in str((r or {}).get("detail", "")), r)


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
