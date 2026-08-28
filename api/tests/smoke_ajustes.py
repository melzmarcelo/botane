"""Ajuste de CUSTO: corrigir o custo médio sem mexer na quantidade.

Mexer na quantidade é dizer que a prateleira tem outra coisa; mexer no custo é
dizer que o dinheiro é outro — e este altera o CMV do período **sem que nada
tenha entrado ou saído**. Por isso é tipo próprio no razão, tem permissão
própria e mora como mais um item na tela de Ajustes, um produto por vez.

O que este arquivo cobra:

1. a prévia mostra a diferença em reais antes de qualquer coisa
2. o ajuste muda o valor sem mexer na quantidade
3. **e o CMV do período anda exatamente o que ele valeu**, com sinal invertido
4. **a movimentação continua fechando** — foi aqui que o desenho falhou
5. saldo zero e custo repetido são recusados, com frase
6. permissão PRÓPRIA: quem só ajusta estoque não passa
7. tudo fica na auditoria, com o custo de antes e o de depois

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


print("1. preparo: três produtos com saldo e custo conhecidos")
a, b, c = criar("A"), criar("B"), criar("C")
for pid, quantia, custo in ((a, 12, 5.00), (b, 17, 3.00), (c, 35, 2.50)):
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": pid, "quantidade": quantia, "custo_unitario": custo,
        "id_local": local["id"]}, token=token)
    checar(f"entrada de {quantia} lançada", st == 201, (st, r))


print("\n2. ajuste de SALDO: a prateleira tem outra coisa")
# O produto A tem 12. A conferência achou 9 — faltam 3.
st, r = chamar("POST", "/ajustes/estoque/previa", {
    "id_produto": a, "quantidade_certa": 9, "id_local": local["id"]}, token=token)
checar("a prévia responde", st == 200, (st, r))
checar("com o saldo de agora e o novo",
       perto(r.get("saldo_atual"), 12) and perto(r.get("saldo_novo"), 9), r)
checar("e diz que é FALTA de 3", r.get("movimento") == "falta"
       and perto(r.get("diferenca"), -3), r)
# 3 × 5,00 = 15,00
checar("valendo 15,00 pelo custo médio", perto(r.get("valor"), -15.00), r)
# 🔑 **O sinal aqui NÃO se inverte, ao contrário do ajuste de custo.** Falta
# baixa o estoque final, e o CMV é `inicial + compras − final`: menos estoque,
# CMV MAIOR. Falta encarece o mês; sobra barateia. Trocar os dois sinais é o
# erro mais fácil de cometer nesta tela.
checar("e que isso AUMENTA o CMV em 15,00", perto(r.get("efeito_no_cmv"), 15.00), r)

st, ap_antes = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
cmv_antes = float(ap_antes["cmv_real"])
ajustes_antes = float(ap_antes.get("ajustes") or 0)

st, r = chamar("POST", "/ajustes/estoque", {
    "id_produto": a, "quantidade_certa": 9, "id_local": local["id"],
    "observacao": f"conferência {marca}"}, token=token)
checar("o acerto é lançado", st == 201, (st, r))
checar("como falta", r.get("movimento") == "falta", r)

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
checar("o saldo passou a 9", perto(saldos[0]["quantidade"], 9), saldos)
# ⚠️ Sobra entra pelo MÉDIO que já existe, e falta sai por ele: o acerto de
# QUANTIDADE não pode mexer no custo médio — quem faz isso é o outro tipo.
checar("e o custo médio NÃO mudou", perto(saldos[0]["custo_medio"], 5.00), saldos)

st, ap_depois = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("o CMV subiu 15,00 (menos estoque, CMV maior)",
       perto(float(ap_depois["cmv_real"]) - cmv_antes, 15.00),
       (cmv_antes, ap_depois["cmv_real"]))
# Cai na linha que já existe, não numa nova: é a mesma natureza de correção.
checar("e caiu na linha de ajustes de inventário do painel",
       perto(float(ap_depois.get("ajustes") or 0) - ajustes_antes, -15.00),
       (ajustes_antes, ap_depois.get("ajustes")))

st, r = chamar("POST", "/ajustes/estoque", {
    "id_produto": a, "quantidade_certa": 9, "id_local": local["id"]}, token=token)
checar("repetir a mesma quantidade é recusado", st == 400, (st, r))
checar("com a frase dizendo que já está assim",
       "já está" in str(r.get("detail", "")).lower(), r.get("detail"))


print("\n3. a prévia do custo mostra a diferença antes")
# O produto A tem 9 unidades a 5,00 = 45,00 (perdeu 3 no acerto de saldo
# acima). A 6,00 passa a valer 54,00.
st, r = chamar("POST", "/ajustes/custo/previa", {
    "linhas": [{"id_produto": a, "custo_novo": 6.00, "id_local": local["id"]}],
}, token=token)
checar("a prévia responde", st == 200, (st, r))
linha = (r.get("linhas") or [{}])[0]
checar("com o saldo e o custo de agora",
       perto(linha.get("saldo"), 9) and perto(linha.get("custo_atual"), 5.00), linha)
checar("o valor de antes e o de depois", perto(linha.get("valor_atual"), 45.00)
       and perto(linha.get("valor_novo"), 54.00), linha)
checar("e a diferença em reais (9,00)", perto(linha.get("diferenca"), 9.00), linha)
# 🔑 O sinal invertido é o ponto que confunde: estoque mais caro, CMV MENOR.
checar("o efeito no CMV vem com o sinal invertido (−9,00)",
       perto(linha.get("efeito_no_cmv"), -9.00), linha)
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
# A: 9 × (6,00 − 5,00) = +9,00 | B: 17 × (4,00 − 3,00) = +17,00 → 26,00
checar("a diferença total é 26,00", perto(r.get("diferenca_total"), 26.00), r)

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={a}", token=token)
checar("o custo médio passou a 6,00", perto(saldos[0]["custo_medio"], 6.00), saldos)
checar("e a QUANTIDADE não mudou", perto(saldos[0]["quantidade"], 9), saldos)

st, movs = chamar("GET", f"/estoque/movimentos?id_produto={a}", token=token)
mov = next((m for m in (movs or []) if m.get("tipo") == "AJUSTE_CUSTO"), None)
checar("o razão registra o movimento de valor", mov is not None,
       [m.get("tipo") for m in (movs or [])][:5])
checar("com quantidade zero e valor 9,00",
       mov and perto(mov.get("quantidade"), 0) and perto(mov.get("custo_total"), 9.00), mov)


print("\n5. e o CMV anda exatamente o que o ajuste valeu")
st, ap_depois = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
# 🔑 A afirmação central. Estoque reavaliado +29,00 → estoque final maior →
# CMV menor em 29,00. Se um dia isso deixar de valer, a identidade do CMV
# quebrou e o número na tela do dono está errado.
checar("o CMV real caiu 26,00 (estoque mais caro, CMV menor)",
       perto(float(ap_depois["cmv_real"]) - cmv_antes, -26.00),
       (cmv_antes, ap_depois["cmv_real"]))
checar("e a linha do painel nomeia o efeito (−26,00)",
       perto(float(ap_depois.get("ajuste_custo") or 0) - custo_antes, -26.00),
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
       and perto(float(linha_a["valor_entradas"]) - 60.00, 9.00),
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
    checar("ele lança ajuste de quantidade", bool(chaves & porta), sorted(chaves))
    checar("e NÃO ajusta custo — contar prateleira não é decidir valor",
           "estoque.custo" not in chaves, sorted(chaves))


print("\n8. tudo na auditoria")
st, aud = chamar("GET", "/auditoria?entidade=ajuste_lote&limite=20", token=token)
eventos = [e for e in (aud or []) if e.get("acao") in ("ajuste_estoque", "ajuste_custo")]
checar("o ajuste está registrado", len(eventos) >= 1,
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
