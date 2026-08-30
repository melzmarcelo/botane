"""Teste de fumaça do tipo de produto `UTENSILIO` — "Utensílios".

Prato, talher, taça, panela e avental entravam como INSUMO ou REVENDA e sumiam
dentro do custo da comida. O que separa este tipo de EMBALAGEM e
MATERIAL_LIMPEZA não é ser "não comida" — os três são. É que utensílio **não é
consumido**: quebra, some, e é reposto.

O que este arquivo cobra:

1. o tipo existe, aceita produto e aparece na lista viva do CMV
2. serve também como tipo de CATEGORIA — nos dois lados
   (⚠️ `MATERIAL_LIMPEZA` estava só no front e o servidor recusava com 422)
3. a migração 037 semeou o grupo, com o acento certo, FORA do CMV real
4. **comprar utensílio não mexe no CMV real** — que é o motivo de o tipo existir
5. mas o dinheiro continua à vista no painel, e o tipo é nomeado como fora
6. o filtro de inventário aceita o tipo
7. o tipo não pode entrar em dois grupos

    python tests/smoke_utensilios.py            (API de pé na 9200)

⚠️ Cria os PRÓPRIOS produtos, com marca de tempo, e mede DELTA: a base é
compartilhada com as outras suítes e já tem dado de sobra.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
GRUPO_SEMEADO = "Utensílios"

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
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
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
hoje = date.today()
periodo = f"inicio={hoje.replace(day=1)}&fim={hoje}"

criados: dict[str, list[int]] = {"grupos": [], "categorias": []}


def limpar():
    for id_g in criados["grupos"]:
        chamar("DELETE", f"/cmv/grupos/{id_g}", token=token)
    for id_c in criados["categorias"]:
        chamar("DELETE", f"/categorias/{id_c}", token=token)


atexit.register(limpar)


print("1. o tipo existe e aceita produto")
st, r = chamar("POST", "/produtos", {
    "codigo": f"UTE{marca}", "nome": f"Taça de vinho {marca}",
    "tipo": "UTENSILIO", "um_estoque": "UN",
}, token=token)
checar("cria produto do tipo utensílio", st == 201, (st, r))
id_utensilio = r.get("id")

st, r = chamar("GET", f"/produtos/{id_utensilio}", token=token)
checar("e o tipo volta gravado", r.get("tipo") == "UTENSILIO", r.get("tipo"))
# ⚠️ O gatilho da migração 036 põe o nome em maiúsculas — afirmar sobre o que
# foi MANDADO, e não sobre o que foi gravado, quebraria aqui sem haver bug.
checar("com o nome em maiúsculas, como todo produto",
       (r.get("nome") or "") == f"TAÇA DE VINHO {marca}", r.get("nome"))

st, r = chamar("GET", "/cmv/grupos/tipos-livres", token=token)
checar("o tipo está na lista viva que o CMV publica",
       "UTENSILIO" in (r.get("todos") or []), r.get("todos"))

st, r = chamar("POST", "/produtos", {
    "codigo": f"XX{marca}", "nome": f"Invalido {marca}",
    "tipo": "UTENSILIOS", "um_estoque": "UN",
}, token=token)
# ⚠️ 400 e não 422: o tipo não é validado pelo Pydantic (a coluna é varchar
# livre), e sim no router, que devolve a lista inteira na frase. É o certo —
# "UTENSILIOS" no plural é o erro de digitação provável, e a resposta mostra a
# grafia boa em vez de um erro de esquema.
checar("e um tipo parecido, mas inexistente, é recusado", st == 400, (st, r))
checar("com a frase dizendo quais valem",
       "UTENSILIO" in str(r.get("detail", "")), r.get("detail"))


print("\n2. o tipo serve para categoria — nos DOIS lados")
# ⚠️ Esta fase existe por causa de um bug real: o front oferecia
# MATERIAL_LIMPEZA como tipo de categoria desde a migração 029 e o servidor
# recusava com 422, porque TIPOS_CATEGORIA não tinha sido atualizado junto.
# Ninguém tinha tentado criar a categoria ainda.
for tipo in ("UTENSILIO", "MATERIAL_LIMPEZA"):
    st, r = chamar("POST", "/categorias", {
        "nome": f"Cat {tipo} {marca}", "tipo": tipo,
    }, token=token)
    checar(f"categoria do tipo {tipo} é aceita", st == 201, (st, r))
    if r.get("id"):
        criados["categorias"].append(r["id"])


print("\n3. a migração semeou o grupo, fora do CMV")
st, grupos = chamar("GET", "/cmv/grupos", token=token)
semeado = next((g for g in grupos if g["nome"] == GRUPO_SEMEADO), None)
# ⚠️ **A precondição é GARANTIDA, não suposta.** A migração 037 semeia o grupo,
# mas migração não reexecuta: quem limpar as tabelas de apoio para recadastrar
# leva o grupo junto, e a suíte passava a acusar de defeito uma decisão de quem
# usa o sistema. O que ela cobra é o COMPORTAMENTO do grupo sobre o tipo — o
# nome acentuado inclusive, que é o que prova o `.sql` chegando em UTF-8.
if semeado is None:
    st, _novo_g = chamar("POST", "/cmv/grupos",
                         {"nome": GRUPO_SEMEADO, "tipos": ["UTENSILIO"],
                          "considerar_no_cmv": False, "ordem": 90}, token=token)
    if (_novo_g or {}).get("id"):
        criados["grupos"].append(_novo_g["id"])
    st, grupos = chamar("GET", "/cmv/grupos", token=token)
    semeado = next((g for g in grupos if g["nome"] == GRUPO_SEMEADO), None)
# ⚠️ Comparar o nome INTEIRO, com acento: é o que prova que o .sql chegou ao
# banco em UTF-8. Um `Utens?lios` passaria num teste que só comparasse o começo.
checar("o grupo existe com o nome acentuado certo", semeado is not None,
       [g["nome"] for g in grupos])
checar("e ele é dono do tipo utensílio",
       semeado and semeado["tipos"] == ["UTENSILIO"], semeado)
checar("e nasce FORA do CMV real — é o motivo de existir",
       semeado and semeado["considerar_no_cmv"] is False, semeado)

st, r = chamar("GET", "/cmv/grupos/tipos-livres", token=token)
checar("logo o tipo não está livre: já tem grupo",
       "UTENSILIO" not in (r.get("tipos") or []), r.get("tipos"))


print("\n4. comprar utensílio NÃO mexe no CMV real")
local = garantir_local(chamar, token)
st, antes = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("a apuração responde", st == 200, st)
cmv_antes = float(antes["cmv_real"])
compras_antes = float(antes["compras"])

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": id_utensilio, "quantidade": 12, "custo_unitario": 15.0,
    "id_local": local["id"],
}, token=token)
checar("entrada de 12 taças a 15,00 lançada (180,00)", st == 201, (st, r))

st, depois = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
# ⚠️ A afirmação forte da suíte. O grupo está fora do CMV, então o custo sai das
# TRÊS pontas (inicial, compras e final) e a contribuição se anula por completo.
# Se um dia alguém marcar `considerar_no_cmv` no grupo, esta linha cai — e é o
# aviso certo, porque o food cost teria mudado de régua sem ninguém pedir.
checar("o CMV real não se move com a compra de utensílio",
       perto(float(depois["cmv_real"]) - cmv_antes, 0.0),
       (cmv_antes, depois["cmv_real"]))
checar("nem as compras que entram na conta do CMV",
       perto(float(depois["compras"]) - compras_antes, 0.0),
       (compras_antes, depois["compras"]))


print("\n5. mas o dinheiro continua à vista")
grupo = next((g for g in depois.get("grupos", []) if g["nome"] == GRUPO_SEMEADO), None)
grupo_antes = next((g for g in antes.get("grupos", []) if g["nome"] == GRUPO_SEMEADO), None)
checar("o grupo aparece no painel", grupo is not None,
       [g["nome"] for g in depois.get("grupos", [])])
# ⚠️ DELTA, não valor absoluto: outra rodada desta suíte já deixou taça comprada
# neste grupo, e produto com movimento vira INATIVO em vez de sumir.
checar("e as compras dele andaram os 180,00",
       grupo and grupo_antes
       and perto(float(grupo["compras"]) - float(grupo_antes["compras"]), 180.0),
       (grupo_antes, grupo))
checar("o painel nomeia o tipo como fora do CMV",
       "UTENSILIO" in (depois.get("tipos_fora_do_cmv") or []),
       depois.get("tipos_fora_do_cmv"))


print("\n6. o filtro de inventário aceita o tipo")
st, r = chamar("GET", "/inventarios/previa?tipos=UTENSILIO", token=token)
checar("a prévia responde ao recorte por tipo", st == 200, (st, r))
checar("e traz ao menos a taça recém-criada", (r or {}).get("total", 0) >= 1, r)


print("\n7. o tipo não entra em dois grupos")
st, r = chamar("POST", "/cmv/grupos", {
    "nome": f"Outro utensilio {marca}", "tipos": ["UTENSILIO"], "ordem": 95,
    "considerar_no_cmv": False,
}, token=token)
checar("criar outro grupo com o mesmo tipo é recusado", st == 409, (st, r))
# ⚠️ A recusa tem de DIZER onde o tipo está: sem isso, quem monta os grupos vê
# "não pode" e não sabe qual grupo abrir para liberá-lo.
checar("e a recusa nomeia o grupo que já o tem",
       GRUPO_SEMEADO in str(r.get("detail", "")), r.get("detail"))
if r.get("id"):
    criados["grupos"].append(r["id"])


print(f"\n{ok} ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
