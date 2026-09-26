"""Teste de fumaça do reprocessamento do estoque — o razão relido por data.

🔑 **Pedido do dono (15/09/2026):** *"em saldos e movimentos, criar uma opção de
reprocessar, caso tenha alterações, disponibilizar a opção de reprocessar o
estoque, filtrando por produto"*.

O caso que ele existe para consertar é o **lançamento retroativo**: a nota do dia
5/8 entra depois de a venda do dia 8/8 já ter saído. A venda saiu com custo
estimado (não havia saldo) e o saldo ficou negativo — e nada disso se acerta
sozinho, porque o custo médio é calculado no instante do lançamento.

O que este arquivo cobra:

1. a PRÉVIA não grava nada — é o padrão da casa para operação que reescreve
   número que alguém já leu
2. o custo da SAÍDA passa a ser a média do momento, e o saldo entra na ordem
3. o custo da ENTRADA **não se toca**: é o que a casa pagou
4. rodar de novo não muda nada — é idempotente
5. produto em ordem responde "nada mudaria", e produto sem movimento também
6. quem não tem `estoque.custo` recebe 403

    python tests/smoke_reprocessar.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_locais  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns() // 100)[-6:]
garantir_locais(chamar, token)
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])["id"]


def movimentos_de(id_produto):
    st, m = chamar("GET", f"/estoque/movimentos?id_produto={id_produto}&por_pagina=100",
                   token=token)
    return sorted(m or [], key=lambda x: (x["data_movimento"], x["id"]))


print("1. a venda que saiu ANTES de a nota entrar")
st, p = chamar("POST", "/produtos", {
    "codigo": f"REPRO-{marca}", "nome": f"VINHO REPRO {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
}, token=token)
produto = (p or {}).get("id")
checar("o produto de teste nasce", st == 201 and produto, (st, p))

# ⚠️ **A ORDEM importa, e as DATAS também.** A saída primeiro, sem saldo nenhum
# — é ela que sai por custo estimado e deixa o saldo negativo. E as duas ficam
# num mês (agosto) em que a bateria não fecha período nenhum: com elas no mês corrente, o
# reprocessamento mudava números que as fases de fechamento já tinham
# fotografado em `cmv_movimentacao`, e as suítes de grupos e de relatórios
# quebravam com a diferença exata desta entrada — três telas adiante da causa.
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": produto, "quantidade": 2, "tipo": "SAIDA_VENDA", "id_local": principal,
    "data_movimento": "2026-08-08", "documento": f"REPRO-V-{marca}",
}, token=token)
checar("a saída do dia 8/8 é lançada, sem saldo", st == 201, (st, r))
checar("e deixa o saldo negativo", float((r or {}).get("saldo", 0)) == -2, r)

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 6, "custo_unitario": 64, "id_local": principal,
    "data_movimento": "2026-08-05", "documento": f"REPRO-N-{marca}",
}, token=token)
checar("a nota do dia 5/8 entra depois, com data anterior", st == 201, (st, r))

antes = movimentos_de(produto)
saida_antes = next((m for m in antes if m["tipo"] == "SAIDA_VENDA"), None)
# 🔑 O defeito, medido: a venda ficou com custo ZERO e saldo negativo, e a
# entrada posterior não a corrigiu — nem tinha como.
checar("a venda ficou sem custo, porque não havia saldo na hora",
       float((saida_antes or {}).get("custo_unitario") or 0) == 0, saida_antes)
checar("e com saldo negativo depois dela",
       float((saida_antes or {}).get("saldo_apos") or 0) == -2, saida_antes)

print("\n2. a prévia diz o que mudaria — e NÃO grava")
st, previa = chamar("POST", "/estoque/reprocessar", {"id_produto": produto}, token=token)
checar("a prévia responde", st == 200, (st, previa))
checar("e aponta os movimentos que mudam", (previa or {}).get("mudam", 0) >= 2, previa)
checar("sem ter aplicado nada", (previa or {}).get("aplicado") is False, previa)
depois_da_previa = movimentos_de(produto)
checar("o razão continua exatamente como estava",
       [(m["id"], float(m["custo_unitario"] or 0), float(m["saldo_apos"])) for m in antes]
       == [(m["id"], float(m["custo_unitario"] or 0), float(m["saldo_apos"]))
           for m in depois_da_previa],
       depois_da_previa)

print("\n3. reprocessando de verdade")
st, r = chamar("POST", "/estoque/reprocessar", {"id_produto": produto, "aplicar": True},
               token=token)
checar("o reprocessamento responde", st == 200, (st, r))
checar("e diz que aplicou", (r or {}).get("aplicado") is True, r)

feito = movimentos_de(produto)
entrada = next((m for m in feito if m["tipo"] == "ENTRADA_MANUAL"), None)
saida = next((m for m in feito if m["tipo"] == "SAIDA_VENDA"), None)
# 🔑 A afirmação central: a saída passou a custar a média do momento.
checar("a saída passou a custar o que a prateleira valia",
       float((saida or {}).get("custo_unitario") or 0) == 64, saida)
checar("e o saldo dela deixou de ser negativo",
       float((saida or {}).get("saldo_apos") or 0) == 4, saida)
# ⚠️ E o custo da ENTRADA não se toca: é o que a casa pagou.
checar("o custo da entrada continua o da nota",
       float((entrada or {}).get("custo_unitario") or 0) == 64, entrada)
checar("com o saldo dela na ordem certa",
       float((entrada or {}).get("saldo_apos") or 0) == 6, entrada)

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={produto}", token=token)
linha = (saldos or [{}])[0]
checar("a prateleira fica com o saldo certo", float(linha.get("quantidade") or 0) == 4, linha)
checar("e com o custo médio certo", float(linha.get("custo_medio") or 0) == 64, linha)

print("\n4. rodar de novo não muda nada")
st, denovo = chamar("POST", "/estoque/reprocessar", {"id_produto": produto}, token=token)
checar("a segunda prévia não acha nada a mudar", (denovo or {}).get("mudam") == 0, denovo)
checar("e diz isso com todas as letras",
       "em ordem" in (denovo or {}).get("message", ""), denovo)

print("\n4b. o estorno de uma saída acompanha o custo dela")
# 🔑 **O par que devolve tem de devolver o que tirou.** Reprocessar reescreve o
# custo da SAÍDA (que nunca foi fato, é a média do momento) e deixava o espelho
# dela -- o ESTORNO_ENTRADA -- no valor antigo. O par parava de fechar em zero e a
# diferença ficava pendurada no estoque para sempre, quebrando a identidade
# `inicial + entradas - saídas = final`. Medido numa base real: uma saída de
# 2,712 KG repreçada de R$ 63,00 para R$ 315,00 com o estorno parado em
# R$ 63,00 abriu um buraco de R$ 683,42 num produto só.
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": produto, "quantidade": 2, "tipo": "SAIDA_VENDA", "id_local": principal,
    "data_movimento": "2026-08-20", "documento": f"REPRO-E-{marca}",
}, token=token)
checar("uma saída nova, já com a prateleira valendo 64", st == 201, (st, r))
id_saida = (r or {}).get("id")
st, r = chamar("POST", f"/estoque/movimentos/{id_saida}/estornar",
               {"motivo": "para provar o espelho"}, token=token)
checar("e o estorno dela é lançado", st == 201, (st, r))

# A nota atrasada que muda a média ANTES da saída: 4 a 100 no dia 15 põem a
# prateleira em (4x64 + 4x100) / 8 = 82,00.
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 4, "custo_unitario": 100, "id_local": principal,
    "data_movimento": "2026-08-15", "documento": f"REPRO-N2-{marca}",
}, token=token)
checar("a nota do dia 15 entra por último, com data anterior", st == 201, (st, r))

st, r = chamar("POST", "/estoque/reprocessar", {"id_produto": produto, "aplicar": True},
               token=token)
checar("o reprocessamento aplica", st == 200 and (r or {}).get("aplicado") is True, (st, r))

feito = movimentos_de(produto)
saida20 = next((m for m in feito if m["id"] == id_saida), None)
espelho = next((m for m in feito if m.get("id_estorno_de") == id_saida), None)
checar("a saída passou a custar a média do dia 20 (82,00)",
       float((saida20 or {}).get("custo_unitario") or 0) == 82, saida20)
# ⚠️ A afirmação central desta fase.
checar("e o estorno dela custa o MESMO",
       float((espelho or {}).get("custo_unitario") or 0) == 82, espelho)
checar("o par volta a valer exatamente zero",
       float((saida20 or {}).get("custo_total") or 0)
       == float((espelho or {}).get("custo_total") or 0), (saida20, espelho))

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={produto}", token=token)
linha = (saldos or [{}])[0]
checar("a prateleira fecha com 8 ao custo de 82,00",
       float(linha.get("quantidade") or 0) == 8 and float(linha.get("custo_medio") or 0) == 82,
       linha)


print("\n5. produto sem movimento, e quem não pode")
st, p2 = chamar("POST", "/produtos", {
    "codigo": f"REPRO-VAZIO-{marca}", "nome": f"SEM MOVIMENTO {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
}, token=token)
vazio = (p2 or {}).get("id")
st, r = chamar("POST", "/estoque/reprocessar", {"id_produto": vazio}, token=token)
checar("produto sem movimento responde sem erro", st == 200, (st, r))
checar("dizendo que não há o que reprocessar",
       "não tem movimento" in (r or {}).get("message", ""), r)

st, r = chamar("POST", "/estoque/reprocessar", {"id_produto": 99999999}, token=token)
checar("produto inexistente é 404", st == 404, (st, r))

# ⚠️ **A permissão é a do CUSTO**: o que isto reescreve é custo médio e custo de
# saída, a mesma autoridade do Ajuste de custo. Sem ela, 403.
st, papel = chamar("POST", "/papeis", {
    "nome": f"So saldos {marca}", "permissoes": ["estoque.saldos"],
}, token=token)
st, u = chamar("POST", "/usuarios", {
    "nome": f"Sem custo {marca}", "email": f"smoke.semcusto{marca}@botane.com.br",
    "senha": "semcusto12345", "id_papel": (papel or {}).get("id"),
}, token=token)
if (u or {}).get("id"):
    st, entrou = chamar("POST", "/auth/login",
                        {"email": f"smoke.semcusto{marca}@botane.com.br", "senha": "semcusto12345"})
    if st == 200:
        st, r = chamar("POST", "/estoque/reprocessar", {"id_produto": produto},
                       token=entrou["access_token"])
        checar("quem não pode mexer em custo recebe 403", st == 403, (st, r))
    else:
        # Senha definida por outra pessoa obriga a troca no primeiro acesso —
        # e isso já é uma recusa legítima para o que se queria provar.
        checar("quem não pode mexer em custo nem chega a entrar", st in (401, 403), (st, entrou))
    chamar("DELETE", f"/usuarios/{u['id']}", token=token)
chamar("DELETE", f"/papeis/{(papel or {}).get('id')}", token=token)

# ⚠️ **Esta suíte apaga o próprio rastro do RAZÃO, por SQL — e isso é exceção
# deliberada, não descuido.** O razão é append-only para o SISTEMA; aqui a
# questão é outra: reprocessar REESCREVE custo histórico, e as suítes de CMV,
# de grupos e de relatórios conferem a identidade `inicial + entradas − saídas
# = final` sobre a base INTEIRA. Qualquer produto cujo custo foi reescrito
# depois de outra fase ter fotografado o período abre essa conta — e a falha
# aparece em três suítes que não têm nada a ver com o assunto, com a diferença
# exata desta entrada.
# ⚠️ Tentei antes: apagar o produto pela API (a diferença ficou), estornar os
# movimentos (piorou: estorno de saída é mais uma entrada) e mudar as datas
# para um mês sem fechamento (o estoque inicial do mês seguinte passou a
# discordar). O que fecha a conta é não deixar rastro nenhum.
# ⚠️ Por SQL direto porque NÃO EXISTE rota para isso, e não deve existir: o
# sistema não apaga movimento. `smoke_pdv_legal` já abre o banco pelo mesmo
# motivo — preparar (ou desfazer) um estado que a API, com razão, não oferece.
try:
    import psycopg2

    sys.path.insert(0, ".")
    from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

    conexao = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                               password=DB_PASSWORD, dbname=DB_NAME, sslmode=DB_SSLMODE)
    with conexao, conexao.cursor() as c:
        c.execute("DELETE FROM movimento_lotes WHERE id_movimento IN ("
                  "SELECT id FROM estoque_movimentos WHERE id_produto = %s)", (produto,))
        c.execute("DELETE FROM estoque_movimentos WHERE id_produto = %s", (produto,))
        c.execute("DELETE FROM estoque_saldos WHERE id_produto = %s", (produto,))
        c.execute("DELETE FROM estoque_lotes WHERE id_produto = %s", (produto,))
    conexao.close()
    st, sobrou = chamar("GET", f"/estoque/movimentos?id_produto={produto}", token=token)
    checar("a suíte não deixa rastro no razão", not (sobrou or []), sobrou)
except Exception as e:  # noqa: BLE001
    checar("a suíte não deixa rastro no razão", False, repr(e)[:160])

for _p in (produto, vazio):
    chamar("DELETE", f"/produtos/{_p}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
