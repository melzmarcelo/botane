"""Ajustes em lote: de estoque (quantidade) e de custo (valor).

Dois processos separados de propósito. Mexer na quantidade é dizer que a
prateleira tem outra coisa; mexer no custo é dizer que o dinheiro é outro — e
o segundo altera o CMV do período **sem que nada tenha entrado ou saído**.

O que este arquivo cobra:

1. um lote de estoque lança vários produtos de uma vez, amarrados a uma origem
2. a linha que falha derruba o lote INTEIRO, e a mensagem diz qual linha
3. a prévia do custo mostra a diferença em reais antes de qualquer coisa
4. o ajuste de custo muda o valor sem mexer na quantidade
5. **e o CMV do período anda exatamente o que ele valeu**, com sinal invertido
6. saldo zero e custo repetido são recusados, com frase
7. o ajuste de custo tem permissão PRÓPRIA — quem só ajusta estoque não passa
8. tudo fica na auditoria, com o custo de antes e o de depois

    python tests/smoke_ajustes.py            (API de pé na 9200)

⚠️ Cria os próprios produtos, com marca de tempo, e mede DELTA sobre a
apuração anterior: a base é compartilhada.
"""

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
local = garantir_local(chamar, token)


def criar(sufixo, um="KG"):
    st, r = chamar("POST", "/produtos", {
        "codigo": f"AJ{sufixo}{marca}", "nome": f"Ajuste {sufixo} {marca}",
        "tipo": "INSUMO", "um_estoque": um,
    }, token=token)
    assert st == 201, (st, r)
    return r["id"]


print("1. o lote de estoque lança vários de uma vez")
a, b, c = criar("A"), criar("B"), criar("C")
# Entradas prévias, para haver saldo e custo médio conhecidos.
for pid, qtd, custo in ((a, 10, 5.00), (b, 20, 3.00), (c, 40, 2.50)):
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": pid, "quantidade": qtd, "custo_unitario": custo,
        "id_local": local["id"]}, token=token)
    assert st == 201, (st, r)

st, r = chamar("POST", "/ajustes/estoque", {
    "observacao": f"Conferência da despensa {marca}",
    "linhas": [
        {"id_produto": a, "tipo": "ENTRADA_MANUAL", "quantidade": 2, "custo_unitario": 5.00,
         "id_local": local["id"]},
        {"id_produto": b, "tipo": "SAIDA_CONSUMO_INTERNO", "quantidade": 3,
         "id_local": local["id"]},
        {"id_produto": c, "tipo": "SAIDA_CONSUMO_INTERNO", "quantidade": 5,
         "id_local": local["id"]},
    ],
}, token=token)
checar("três linhas num lançamento só", st == 201 and r.get("lancados") == 3, (st, r))
id_lote = r.get("id_lote")

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
checar("o primeiro produto subiu para 12", saldos and perto(saldos[0]["quantidade"], 12),
       saldos)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={c}", token=token)
checar("e o terceiro caiu para 35", saldos and perto(saldos[0]["quantidade"], 35), saldos)

st, lotes = chamar("GET", "/ajustes/lotes?natureza=ESTOQUE", token=token)
meu = next((x for x in lotes if x["id"] == id_lote), None)
checar("o lote aparece no histórico, com autor e contagem",
       meu and meu["linhas"] == 3 and meu["usuario"], meu)
checar("e guarda a observação que explica o conjunto",
       meu and marca in (meu.get("observacao") or ""), meu)

# ⚠️ É o que amarra os movimentos ao lote: sem isso, três ajustes da mesma
# conferência ficam indistinguíveis de três avulsos.
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={a}", token=token)
checar("o movimento aponta para o lote como origem",
       any(m.get("origem_tipo") == "AJUSTE_LOTE" for m in (movs or [])),
       (movs or [{}])[0])


print("\n2. a linha que falha derruba o lote inteiro")
st, antes = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
qtd_antes = float(antes[0]["quantidade"])
st, r = chamar("POST", "/ajustes/estoque", {
    "linhas": [
        {"id_produto": a, "tipo": "ENTRADA_MANUAL", "quantidade": 1, "custo_unitario": 5.00,
         "id_local": local["id"]},
        {"id_produto": 999999999, "tipo": "ENTRADA_MANUAL", "quantidade": 1,
         "custo_unitario": 1.00, "id_local": local["id"]},
    ],
}, token=token)
checar("o lote com produto inexistente é recusado", st == 404, (st, r))
# ⚠️ Num lote de vinte, "produto não encontrado" sem número manda procurar em
# vinte. A frase diz a linha.
checar("e a mensagem diz QUAL linha", "Linha 2" in str(r.get("detail", "")), r.get("detail"))
st, depois = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
checar("a linha boa NÃO entrou (tudo ou nada)",
       perto(depois[0]["quantidade"], qtd_antes), (qtd_antes, depois[0]["quantidade"]))


print("\n3. a prévia do custo mostra a diferença antes")
# O produto A tem 12 unidades a 5,00 = 60,00. A 6,00 passa a valer 72,00.
st, r = chamar("POST", "/ajustes/custo/previa", {
    "linhas": [{"id_produto": a, "custo_novo": 6.00, "id_local": local["id"]}],
}, token=token)
checar("a prévia responde", st == 200, (st, r))
linha = (r.get("linhas") or [{}])[0]
checar("com o saldo e o custo de agora",
       perto(linha.get("saldo"), 12) and perto(linha.get("custo_atual"), 5.00), linha)
checar("o valor de antes e o de depois", perto(linha.get("valor_atual"), 60.00)
       and perto(linha.get("valor_novo"), 72.00), linha)
checar("e a diferença em reais (12,00)", perto(linha.get("diferenca"), 12.00), linha)
# 🔑 O sinal invertido é o ponto que confunde: estoque mais caro, CMV MENOR.
checar("o efeito no CMV vem com o sinal invertido (−12,00)",
       perto(linha.get("efeito_no_cmv"), -12.00), linha)
checar("a prévia NÃO lançou nada",
       (chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)[1][0]["custo_medio"]) == 5.0,
       "custo mudou sem lançar")


print("\n4. o ajuste de custo muda o valor, não a quantidade")
st, ap_antes = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
cmv_antes = float(ap_antes["cmv_real"])
custo_antes = float(ap_antes.get("ajuste_custo") or 0)

st, r = chamar("POST", "/ajustes/custo", {
    "observacao": f"Correção do custo provisório {marca}",
    "linhas": [
        {"id_produto": a, "custo_novo": 6.00, "id_local": local["id"]},
        {"id_produto": b, "custo_novo": 4.00, "id_local": local["id"]},
    ],
}, token=token)
checar("dois custos corrigidos num lote", st == 201 and r.get("lancados") == 2, (st, r))
# A: 12 × (6,00 − 5,00) = +12,00 | B: 17 × (4,00 − 3,00) = +17,00 → 29,00
checar("a diferença total é 29,00", perto(r.get("diferenca_total"), 29.00), r)

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
checar("o custo médio passou a 6,00", perto(saldos[0]["custo_medio"], 6.00), saldos)
checar("e a QUANTIDADE não mudou", perto(saldos[0]["quantidade"], 12), saldos)

st, movs = chamar("GET", f"/estoque/movimentos?id_produto={a}", token=token)
mov = next((m for m in (movs or []) if m.get("tipo") == "AJUSTE_CUSTO"), None)
checar("o razão registra o movimento de valor", mov is not None,
       [m.get("tipo") for m in (movs or [])][:5])
checar("com quantidade zero e valor 12,00",
       mov and perto(mov.get("quantidade"), 0) and perto(mov.get("custo_total"), 12.00), mov)


print("\n5. e o CMV anda exatamente o que o ajuste valeu")
st, ap_depois = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
# 🔑 A afirmação central. Estoque reavaliado +29,00 → estoque final maior →
# CMV menor em 29,00. Se um dia isso deixar de valer, a identidade do CMV
# quebrou e o número na tela do dono está errado.
checar("o CMV real caiu 29,00 (estoque mais caro, CMV menor)",
       perto(float(ap_depois["cmv_real"]) - cmv_antes, -29.00),
       (cmv_antes, ap_depois["cmv_real"]))
checar("e a linha do painel nomeia o efeito (−29,00)",
       perto(float(ap_depois.get("ajuste_custo") or 0) - custo_antes, -29.00),
       (custo_antes, ap_depois.get("ajuste_custo")))


# 🔑 **A regressão que este arquivo existe para impedir.** O ajuste de custo
# muda o estoque FINAL (que sai da fotografia do razão) sem aparecer em
# entradas nem saídas — a CTE da movimentação ramificava só em `quantidade > 0`
# e `< 0`, e o movimento de quantidade ZERO caía em nenhum dos dois. A
# identidade parava de fechar, e a diferença era exatamente o que fora
# reavaliado. Três suítes caíram de uma vez quando isso entrou.
st, mov = chamar("GET", f"/cmv/movimentacao?{periodo}", token=token)
t = mov["total"]
folga = max(0.05, 0.005 * mov["produtos"])
checar("a movimentação continua fechando depois da reavaliação",
       perto(t["valor_inicial"] + t["valor_entradas"] - t["valor_saidas"],
             t["valor_final"], folga),
       t)
linha_a = next((x for x in mov["linhas"] if x["id_produto"] == a), None)
# Entraram 12 KG (10 da carga inicial + 2 do lote), todos a 5,00 = 60,00 de
# mercadoria. A reavaliação somou 12,00 de VALOR sem somar quantidade nenhuma —
# então o valor das entradas passa a mercadoria em exatamente 12,00.
checar("a linha do produto soma valor sem somar quantidade",
       linha_a and perto(linha_a["qtd_entradas"], 12)
       and perto(float(linha_a["valor_entradas"]) - 60.00, 12.00),
       linha_a)


print("\n6. o que é recusado, e com frase")
zerado = criar("Z", "UN")
st, r = chamar("POST", "/ajustes/custo", {
    "linhas": [{"id_produto": zerado, "custo_novo": 9.00, "id_local": local["id"]}],
}, token=token)
checar("produto sem saldo neste local é recusado", st in (400, 404), (st, r))

st, r = chamar("POST", "/ajustes/custo", {
    "linhas": [{"id_produto": a, "custo_novo": 6.00, "id_local": local["id"]}],
}, token=token)
checar("repetir o mesmo custo é recusado", st == 400, (st, r))
checar("e a frase diz que já está assim",
       "já está" in str(r.get("detail", "")).lower(), r.get("detail"))

st, r = chamar("POST", "/ajustes/custo", {
    "linhas": [{"id_produto": a, "custo_novo": -1, "id_local": local["id"]}],
}, token=token)
checar("custo negativo é recusado", st == 422, st)


print("\n7. ajuste de custo tem permissão própria")
# ⚠️ O Conferente ajusta estoque e NÃO ajusta custo: contar prateleira e
# decidir valor são poderes diferentes. Se um dia a chave for para o papel
# errado, esta checagem cai.
st, papeis = chamar("GET", "/papeis", token=token)
conferente = next((p for p in (papeis or []) if "onferente" in p["nome"]), None)
checar("o papel Conferente existe", conferente is not None,
       [p["nome"] for p in (papeis or [])])
if conferente:
    chaves = set(conferente.get("permissoes") or conferente.get("chaves") or [])
    # ⚠️ A afirmação é sobre a CAPACIDADE, não sobre uma chave específica. O
    # lote de estoque aceita qualquer uma das quatro (ajuste, entradas, saídas,
    # perdas) porque um lote pode misturar os três tipos — e quem só tem a de
    # perda precisa conseguir lançar a perda dele. Cobrar `estoque.ajuste`
    # nominalmente falhava sem haver problema: essa chave é a do ESTORNO.
    porta = {"estoque.ajuste", "estoque.entradas", "estoque.saidas", "estoque.perdas"}
    checar("ele passa pela porta do lote de estoque", bool(chaves & porta), sorted(chaves))
    checar("e NÃO ajusta custo — contar prateleira não é decidir valor",
           "estoque.custo" not in chaves, sorted(chaves))


print("\n8. tudo na auditoria")
st, aud = chamar("GET", "/auditoria?entidade=ajuste_lote&limite=20", token=token)
eventos = [e for e in (aud or []) if e.get("acao") in ("ajuste_estoque", "ajuste_custo")]
checar("os dois lotes estão registrados", len(eventos) >= 2,
       [e.get("acao") for e in (aud or [])][:6])
custo_ev = next((e for e in eventos if e["acao"] == "ajuste_custo"), None)
# ⚠️ É dinheiro mudando sem mercadoria se mover: sem o antes E o depois, o
# registro diria que houve um ajuste e não quanto ele valeu.
checar("o de custo guarda o valor de ANTES e o de DEPOIS",
       custo_ev and custo_ev.get("antes") and custo_ev.get("depois"), custo_ev)


print(f"\n{ok} ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
