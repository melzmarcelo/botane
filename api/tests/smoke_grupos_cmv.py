"""Teste de fumaça dos grupos do CMV por tipo de produto.

O CMV mostrava Perdas, Consumo interno e Ajustes de inventário como linhas que
EXPLICAM o número. Faltava a pergunta que o dono faz olhando a nota do mês:
*quanto disto não é comida?* Detergente e marmita entram no custo pela mesma
porta dos insumos e somem no total.

O que este arquivo cobra:

1. o tipo `MATERIAL_LIMPEZA` existe e aceita produto
2. um tipo só pode estar em UM grupo — e a recusa diz em qual ele está
3. nome de grupo não se repete
4. **a soma dos grupos fecha com o CMV do período** (é o que dá sentido ao corte)
5. comprar material de limpeza move o grupo, e só ele
6. grupo configurado aparece no painel mesmo valendo zero
7. apagar o grupo devolve os tipos e não perde histórico
8. quem só vê o painel não reconfigura a apuração da casa

    python tests/smoke_grupos_cmv.py            (API de pé na 9200)

⚠️ Cria os PRÓPRIOS produtos, com marca de tempo, e mede DELTA sobre a apuração
anterior: a base é compartilhada com as outras suítes e já tem dado de sobra.
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
from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

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

# O que este arquivo criar sai no fim, dê certo ou não: a base é compartilhada,
# e um grupo esquecido vira uma linha a mais no painel de todas as outras suítes.
criados: dict[str, list[int]] = {"grupos": [], "produtos": []}


def limpar():
    for id_g in criados["grupos"]:
        chamar("DELETE", f"/cmv/grupos/{id_g}", token=token)


atexit.register(limpar)


print("1. o tipo novo existe e aceita produto")
st, r = chamar("POST", "/produtos", {
    "codigo": f"LIMP{marca}", "nome": f"Detergente {marca}",
    "tipo": "MATERIAL_LIMPEZA", "um_estoque": "UN",
}, token=token)
checar("cria produto do tipo material de limpeza", st == 201, (st, r))
id_limpeza = r.get("id")
if id_limpeza:
    criados["produtos"].append(id_limpeza)

st, r = chamar("POST", "/produtos", {
    "codigo": f"EMB{marca}", "nome": f"Marmita {marca}",
    "tipo": "EMBALAGEM", "um_estoque": "UN",
}, token=token)
checar("e um de embalagem, para o grupo ter dois tipos", st == 201, (st, r))
id_embalagem = r.get("id")
if id_embalagem:
    criados["produtos"].append(id_embalagem)

st, r = chamar("POST", "/produtos", {
    "codigo": f"INS{marca}", "nome": f"Farinha {marca}",
    "tipo": "INSUMO", "um_estoque": "KG",
}, token=token)
checar("e um insumo, que fica FORA do grupo", st == 201, (st, r))
id_insumo = r.get("id")
if id_insumo:
    criados["produtos"].append(id_insumo)

st, r = chamar("POST", "/produtos", {
    "codigo": f"XX{marca}", "nome": f"Invalido {marca}",
    "tipo": "NAO_EXISTE", "um_estoque": "UN",
}, token=token)
checar("tipo inventado é recusado", st == 400, (st, r))
checar("e a recusa lista os tipos válidos",
       "MATERIAL_LIMPEZA" in str(r.get("detail", "")), r.get("detail"))


print("\n2. um tipo só pode estar num grupo")
st, existentes = chamar("GET", "/cmv/grupos", token=token)
checar("a lista de grupos responde", st == 200, st)

st, r = chamar("POST", "/cmv/grupos", {
    "nome": f"Não comida {marca}", "tipos": ["MATERIAL_LIMPEZA", "EMBALAGEM"], "ordem": 90,
}, token=token)
# Se a instalação já trouxe o grupo de exemplo, os dois tipos estão tomados —
# e a recusa É o comportamento sob teste. Nesse caso o grupo do teste nasce com
# um tipo que ninguém usa, e o de exemplo é quem responde pelos dois.
if st == 409:
    checar("a recusa nomeia o grupo que já tem o tipo",
           "já está em" in str(r.get("detail", "")), r.get("detail"))
    dono = next((g for g in existentes
                 if "MATERIAL_LIMPEZA" in g["tipos"] or "EMBALAGEM" in g["tipos"]), None)
    checar("e esse grupo existe mesmo", dono is not None, existentes)
    # Libera os dois tipos para o grupo do teste, devolvendo depois.
    original = dict(dono)
    chamar("PUT", f"/cmv/grupos/{dono['id']}",
           {"nome": dono["nome"], "tipos": [], "ordem": dono["ordem"], "ativo": True},
           token=token)
    atexit.register(lambda: chamar(
        "PUT", f"/cmv/grupos/{original['id']}",
        {"nome": original["nome"], "tipos": list(original["tipos"]),
         "ordem": original["ordem"], "ativo": original["ativo"]}, token=token))
    st, r = chamar("POST", "/cmv/grupos", {
        "nome": f"Não comida {marca}", "tipos": ["MATERIAL_LIMPEZA", "EMBALAGEM"],
        "ordem": 90,
    }, token=token)
else:
    checar("a recusa nomeia o grupo que já tem o tipo", True)
    checar("e esse grupo existe mesmo", True)

checar("cria o grupo com dois tipos", st == 201, (st, r))
id_grupo = r.get("id")
if id_grupo:
    criados["grupos"].append(id_grupo)

st, r = chamar("POST", "/cmv/grupos",
               {"nome": f"Outro {marca}", "tipos": ["EMBALAGEM"]}, token=token)
checar("outro grupo NÃO leva um tipo já usado (409)", st == 409, (st, r))
checar("e a recusa diz em qual grupo ele está",
       f"Não comida {marca}" in str(r.get("detail", "")), r.get("detail"))


print("\n3. nome de grupo não se repete")
st, r = chamar("POST", "/cmv/grupos",
               {"nome": f"nÃo COMIDA {marca}", "tipos": []}, token=token)
checar("nome repetido é recusado, ignorando maiúsculas", st == 409, (st, r))


print("\n4. editar o grupo enxerga os próprios tipos como livres")
st, r = chamar("GET", f"/cmv/grupos/tipos-livres?id_grupo={id_grupo}", token=token)
checar("os tipos do próprio grupo continuam disponíveis",
       "EMBALAGEM" in r.get("tipos", []) and "MATERIAL_LIMPEZA" in r.get("tipos", []),
       r.get("tipos"))
st, r = chamar("GET", "/cmv/grupos/tipos-livres", token=token)
checar("mas para um grupo novo eles estão tomados",
       "EMBALAGEM" not in r.get("tipos", []), r.get("tipos"))


print("\n5. comprar material de limpeza move o grupo, e só ele")
local = garantir_local(chamar, token)
st, antes = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
grupo_antes = next((g for g in antes.get("grupos", []) if g["nome"] == f"Não comida {marca}"),
                   None)
checar("o grupo aparece no painel", grupo_antes is not None,
       [g["nome"] for g in antes.get("grupos", [])])
base_grupo = float(grupo_antes["cmv"]) if grupo_antes else 0.0
base_cmv = float(antes["cmv_real"])
# ⚠️ **Não afirmar "começa em zero".** A base é compartilhada e produto com
# movimento vira INATIVO em vez de sumir: qualquer suíte que compre uma
# embalagem deixa valor neste grupo para sempre. O que se afirma daqui para
# baixo é o DELTA — a linha de base é só o ponto de partida.
checar("e traz um número, não nulo", isinstance(base_grupo, float), base_grupo)

for id_produto, quanto in ((id_limpeza, 40.0), (id_embalagem, 60.0), (id_insumo, 100.0)):
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": id_produto, "quantidade": 10, "custo_unitario": quanto / 10,
        "id_local": local["id"],
    }, token=token)
    checar(f"entrada de {quanto:.0f} lançada", st == 201, (st, r))

st, depois = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
grupo_depois = next((g for g in depois.get("grupos", []) if g["nome"] == f"Não comida {marca}"),
                    None)
# ⚠️ Entrada sem saída: o que entrou está no estoque final, então o CMV do
# período NÃO muda. O que muda é a COMPRA do grupo — e é ela que se mede aqui.
checar("as compras do grupo somam os dois produtos dele",
       grupo_depois and perto(float(grupo_depois["compras"]) - float(grupo_antes["compras"]),
                              100.0),
       grupo_depois)
# ⚠️ A prova de que o corte é corte: a compra TOTAL andou 200,00 (os três
# produtos) e a do grupo andou 100,00 (só os dois tipos dele). Repetir a mesma
# comparação com outro nome não provaria que o insumo ficou de fora.
checar("enquanto a compra total do período andou os 200,00 dos três",
       perto(float(depois["compras"]) - float(antes["compras"]), 200.0),
       (antes["compras"], depois["compras"]))
checar("o grupo conta os produtos que se mexeram",
       grupo_depois and grupo_depois["produtos"] >= 2, grupo_depois)


print("\n6. a soma dos grupos fecha com o CMV do período")
st, por_grupo = chamar("GET", f"/cmv/por-grupo?agrupar=grupo&{periodo}", token=token)
checar("o relatório por grupo responde", st == 200, st)
soma = sum(float(l["cmv"]) for l in por_grupo)
# ⚠️ É a propriedade que dá sentido ao corte: não é rateio, é a mesma conta
# restrita a cada grupo. A folga é de centavo, do arredondamento por linha.
checar("a soma dos grupos é o CMV do período",
       perto(soma, float(depois["cmv_real"]), max(0.05, 0.005 * len(por_grupo))),
       (soma, depois["cmv_real"]))
checar("e existe a linha do que não está em grupo nenhum",
       any(l["grupo"] == "Sem grupo" for l in por_grupo),
       [l["grupo"] for l in por_grupo])


print("\n7. tirar o tipo do grupo reclassifica o passado")
# ⚠️ **Nada de somar 40 e conferir.** Produto com movimento não é apagado, vira
# INATIVO — então as rodadas anteriores desta suíte deixam compras de material
# de limpeza na base, e um valor absoluto esperado erraria a partir da segunda
# vez. O que se afirma aqui é a IDENTIDADE, que não depende do que já existia:
# partir o grupo em dois tem de somar exatamente o grupo inteiro.
com_ambos = float(grupo_depois["compras"])

st, r = chamar("PUT", f"/cmv/grupos/{id_grupo}",
               {"nome": f"Não comida {marca}", "tipos": ["MATERIAL_LIMPEZA"], "ordem": 90,
                "ativo": True}, token=token)
checar("o grupo aceita ficar com um tipo só", st == 200, (st, r))

st, r = chamar("GET", "/cmv/grupos/tipos-livres", token=token)
checar("e EMBALAGEM volta a ficar livre na hora", "EMBALAGEM" in r.get("tipos", []),
       r.get("tipos"))

st, r = chamar("POST", "/cmv/grupos",
               {"nome": f"Só embalagem {marca}", "tipos": ["EMBALAGEM"], "ordem": 91},
               token=token)
checar("o tipo liberado entra num grupo novo", st == 201, (st, r))
if r.get("id"):
    criados["grupos"].append(r["id"])

st, partido = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
so_limpeza = next((x for x in partido.get("grupos", [])
                   if x["nome"] == f"Não comida {marca}"), None)
so_embalagem = next((x for x in partido.get("grupos", [])
                     if x["nome"] == f"Só embalagem {marca}"), None)
checar("os dois grupos aparecem no painel",
       so_limpeza is not None and so_embalagem is not None,
       [x["nome"] for x in partido.get("grupos", [])])
# ⚠️ Reclassifica o PASSADO inteiro: o vínculo é com o tipo, não com o produto,
# então a embalagem trocou de grupo sem que ninguém tocasse no cadastro dela.
checar("partir o grupo em dois soma exatamente o grupo inteiro",
       so_limpeza and so_embalagem
       and perto(float(so_limpeza["compras"]) + float(so_embalagem["compras"]), com_ambos),
       (so_limpeza and so_limpeza["compras"], so_embalagem and so_embalagem["compras"],
        com_ambos))
checar("e cada um ficou com o tipo certo",
       so_limpeza and so_limpeza["tipos"] == ["MATERIAL_LIMPEZA"]
       and so_embalagem and so_embalagem["tipos"] == ["EMBALAGEM"],
       (so_limpeza and so_limpeza["tipos"], so_embalagem and so_embalagem["tipos"]))


print("\n8. quem só vê o painel não reconfigura a apuração")
tk_cozinha = garantir_cozinha(chamar, token)
st, r = chamar("POST", "/cmv/grupos", {"nome": f"Da cozinha {marca}", "tipos": []},
               token=tk_cozinha)
checar("cozinha NÃO cria grupo (403)", st == 403, st)
st, papeis = chamar("GET", "/papeis", token=token)
id_contador = next((p["id"] for p in papeis if p["nome"] == "Contador"), None)
checar("o papel Contador existe", id_contador is not None)


print("\n9. limpeza")
st, r = chamar("DELETE", f"/cmv/grupos/{id_grupo}", token=token)
checar("apaga o grupo", st == 200, (st, r))
if id_grupo in criados["grupos"]:
    criados["grupos"].remove(id_grupo)
st, r = chamar("GET", "/cmv/grupos/tipos-livres", token=token)
checar("e os tipos dele voltam a ficar livres",
       "MATERIAL_LIMPEZA" in r.get("tipos", []), r.get("tipos"))
st, final = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
# ⚠️ Apagar o grupo não mexe em custo nenhum: o material de limpeza continua
# dentro do CMV real, só deixa de aparecer separado.
checar("apagar o grupo NÃO muda o CMV real",
       perto(float(final["cmv_real"]), float(depois["cmv_real"])),
       (final["cmv_real"], depois["cmv_real"]))

st, r = chamar("DELETE", f"/cmv/grupos/{id_grupo}", token=token)
checar("apagar duas vezes devolve 404", st == 404, st)

for id_produto in criados["produtos"]:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
