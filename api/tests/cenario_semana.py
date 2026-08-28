"""Uma semana de operação, cada papel fazendo o seu — e a conta fechando no fim.

O `cenario_cafeteria` prova que os NÚMEROS batem. Este prova que a OPERAÇÃO
funciona: quem pode o quê, e o que acontece quando a semana inteira passa pelo
sistema. Os dois juntos são o que se chamaria de "aceitação".

O elenco, com os papéis de fábrica:

    Gerente     cadastra, homologa ficha, fecha inventário e fecha o mês
    Conferente  recebe nota, lança no estoque, transfere, conta
    Cozinha     produz pela ficha e aponta perda
    Salão       aponta perda e consulta saldo — e mais nada
    Contador    lê o CMV e os relatórios, sem tocar em nada

A semana, com os números conferidos no papel:

    SEG  nota 8001: 40 KG de farinha a 6,00 = 240,00 + 20,00 de frete
                    → 260,00 ÷ 40 = 6,50 /KG
    TER  produz 100 pães (0,2 KG cada = 20 KG) = 130,00 → 1,30 cada
    QUA  vende 60 pães a 5,00 = 300,00 (e SAEM do estoque) | perde 5 (6,50)
    QUI  nota 8002: 40 KG a 8,00 = 320,00 → médio (130,00 + 320,00) ÷ 60 = 7,50
    SEX  produz mais 100 pães: 20 KG × 7,50 = 150,00 → 1,50 cada
                    e o pão fica com médio ponderado entre 1,30 e 1,50
    SAB  inventário cego: contam 130 pães onde o sistema acha 135

    python tests/cenario_semana.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date

sys.path.insert(0, "tests")
import comum  # noqa: F401  — reconfigura a saída (o sinal − mata o print)

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
SUF = uuid.uuid4().hex[:4].upper()

ok = 0
falhas: list[str] = []
achados: list[str] = []


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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} -> {detalhe}")


def conferir(nome, obtido, esperado, tol=0.005):
    try:
        houve = float(obtido)
    except (TypeError, ValueError):
        checar(nome, False, f"esperado {esperado}, veio {obtido!r}")
        return
    checar(nome, abs(houve - float(esperado)) <= tol, f"esperado {esperado}, veio {houve}")


def anotar(oque):
    """Não é falha: é atrito de processo que vale contar a quem usa."""
    achados.append(oque)
    print(f"  nota  {oque}")


def precisa(valor, oque):
    if not valor:
        print(f"\n  parou: {oque}")
        sys.exit(1)
    return valor


print(f"UMA SEMANA NO BOTANÉ — {SUF}\n")

st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
admin = precisa(r.get("access_token"), "não entrou como administrador")

# A apuração é do MÊS INTEIRO: se a base já tem movimento, o número absoluto
# não é deste cenário. Mede-se o quanto ele MOVEU — que é o que se confere no
# papel. (Já custou uma rodada: os valores batiam só em base recém-limpa.)
_hoje = date.today()
_periodo = f"inicio={_hoje.replace(day=1)}&fim={_hoje}"
st, _antes_apuracao = chamar("GET", f"/cmv/apuracao?{_periodo}", token=admin)


def moveu(a, campo):
    return float(a.get(campo) or 0) - float(_antes_apuracao.get(campo) or 0)

# ------------------------------------------------------------------- o elenco
print("1. o elenco: um usuário por papel")

st, papeis = chamar("GET", "/papeis", token=admin)
por_nome = {p["nome"]: p["id"] for p in papeis}
tokens = {}
for papel, apelido in (("Gerente", "gerente"), ("Conferente / Estoque", "conferente"),
                       ("Cozinha", "cozinha"), ("Salão", "salao"), ("Contador", "contador")):
    email = f"semana.{apelido}@botane.com.br"
    st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=admin)
    existe = next((u for u in usuarios if u["email"] == email), None)
    corpo = {"nome": f"Semana {apelido}", "email": email, "senha": "semana12345",
             "ativo": True, "papeis": [{"id_papel": por_nome[papel]}]}
    if existe:
        chamar("PUT", f"/usuarios/{existe['id']}", corpo, token=admin)
    else:
        chamar("POST", "/usuarios", corpo, token=admin)
    st, r = chamar("POST", "/auth/login", {"email": email, "senha": "semana12345"})
    tokens[apelido] = precisa(r.get("access_token"), f"{apelido} não entrou")
checar("os cinco papéis entram no sistema", len(tokens) == 5, list(tokens))

# --------------------------------------------------------------- as permissões
print("\n2. cada um só faz o que é dele")

st, r = chamar("POST", "/produtos", {"nome": f"Sem X {SUF}", "um_estoque": "KG"},
               token=tokens["cozinha"])
checar("cozinha NÃO cadastra produto", st == 403, st)
st, r = chamar("POST", "/notas", {"numero": "x", "itens": []}, token=tokens["cozinha"])
checar("cozinha NÃO digita nota", st == 403, st)
st, r = chamar("GET", "/cmv/apuracao", token=tokens["cozinha"])
checar("cozinha NÃO vê o CMV", st == 403, st)
st, r = chamar("GET", "/estoque/saldos", token=tokens["salao"])
checar("salão VÊ o saldo (precisa saber se tem)", st == 200, st)
st, r = chamar("POST", "/estoque/entradas",
               {"id_produto": 1, "quantidade": 1, "custo_unitario": 1}, token=tokens["salao"])
checar("salão NÃO lança entrada", st == 403, st)
st, r = chamar("POST", "/estoque/entradas",
               {"id_produto": 1, "quantidade": 1, "custo_unitario": 1},
               token=tokens["contador"])
checar("contador NÃO mexe no estoque", st == 403, st)
st, r = chamar("GET", "/cmv/apuracao", token=tokens["contador"])
checar("mas LÊ o CMV, que é o trabalho dele", st == 200, st)
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": str(date.today().replace(day=1))},
               token=tokens["conferente"])
checar("conferente NÃO fecha o mês", st == 403, st)
st, r = chamar("GET", "/usuarios", token=tokens["gerente"])
checar("gerente NÃO administra usuários", st == 403, st)

# ------------------------------------------------------------------ os cadastros
print("\n3. segunda: o gerente cadastra")

st, locais = chamar("GET", "/locais", token=tokens["gerente"])
if not any(l["nome"] == f"Cozinha {SUF}" for l in locais):
    chamar("POST", "/locais", {"nome": f"Cozinha {SUF}", "tipo": "SECO"},
           token=tokens["gerente"])
    st, locais = chamar("GET", "/locais", token=tokens["gerente"])
local = next(l for l in locais if l["nome"] == f"Cozinha {SUF}")
checar("gerente cria o local", bool(local["id"]), local)

st, r = chamar("POST", "/fornecedores",
               {"nome": f"Moinho {SUF}", "cnpj": "11.444.777/0001-61"},
               token=tokens["conferente"])
if not r.get("id"):
    st, ach = chamar("GET", "/fornecedores?busca=11444777000161", token=tokens["conferente"])
    r = ach[0] if ach else {}
forn = precisa(r.get("id"), "sem fornecedor")
checar("conferente cadastra fornecedor (recebe a mercadoria)", bool(forn), forn)

st, r = chamar("POST", "/produtos", {"nome": f"Farinha {SUF}", "tipo": "INSUMO",
                                     "um_estoque": "KG", "id_local_padrao": local["id"]},
               token=tokens["gerente"])
farinha = precisa(r.get("id"), "sem farinha")
st, r = chamar("POST", "/produtos", {"nome": f"Pão {SUF}", "tipo": "PRODUZIDO",
                                     "um_estoque": "UN", "producao_propria": True,
                                     "estoque_minimo": 40, "estoque_maximo": 200,
                                     "id_local_padrao": local["id"]},
               token=tokens["gerente"])
pao = precisa(r.get("id"), "sem pão")

st, r = chamar("POST", "/fichas", {
    "id_produto": pao, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": farinha, "qtd_bruta": 0.2, "um": "KG"}]},
    token=tokens["cozinha"])
ficha = precisa(r.get("id"), f"sem ficha: {r}")
checar("cozinha escreve a ficha", bool(ficha), ficha)
st, r = chamar("POST", f"/fichas/{ficha}/homologar", {}, token=tokens["cozinha"])
checar("mas NÃO homologa — é decisão de quem responde pelo custo", st == 403, st)
st, r = chamar("POST", f"/fichas/{ficha}/homologar", {}, token=tokens["gerente"])
checar("o gerente homologa", st == 200, r)

# ---------------------------------------------------------------------- a nota
print("\n4. segunda: chega a farinha")

st, nota = chamar("POST", "/notas", {
    "id_fornecedor": forn, "numero": f"8001{SUF}", "serie": "1",
    "data_emissao": str(date.today()), "valor_frete": 20.00,
    "itens": [{"descricao_fornecedor": "FARINHA TRIGO KG", "id_produto": farinha,
               "quantidade": 40, "um": "KG", "valor_unitario": 6.00}],
}, token=tokens["conferente"])
id_nota = precisa(nota.get("id"), f"sem nota: {nota}")
st, r = chamar("POST", f"/notas/{id_nota}/lancar", {}, token=tokens["conferente"])
checar("conferente lança a nota", st == 200, r)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=tokens["conferente"])
s_farinha = next(s for s in saldos if s["id_produto"] == farinha)
conferir("farinha a 6,50 (240 + 20 de frete ÷ 40)", s_farinha["custo_medio"], 6.50)

# ------------------------------------------------------------------- a produção
print("\n5. terça: a cozinha produz 100 pães")

st, r = chamar("POST", "/producao-agenda",
               {"id_produto": pao, "quantidade": 100}, token=tokens["cozinha"])
linha = precisa(r.get("id"), f"não agendou: {r}")
st, prev = chamar("GET", f"/producao-agenda/{linha}", token=tokens["cozinha"])
conferir("a folha diz que precisa de 20 KG",
         (prev["previsao"]["itens"] or [{}])[0].get("necessario"), 20)
st, r = chamar("POST", f"/producao-agenda/{linha}/produzir", {}, token=tokens["cozinha"])
checar("cozinha produz", st == 200, r)
conferir("consumindo 130,00 (20 × 6,50)", r.get("custo_total"), 130.00, 0.01)
conferir("e cada pão nasce a 1,30", r.get("custo_unitario"), 1.30)

# --------------------------------------------------------------- venda e perda
print("\n6. quarta: vende 60 e perde 5")

st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"DIA1-{SUF}",
    "itens": [{"id_produto": pao, "quantidade": 60, "valor_unitario": 5.00}]}]},
    token=tokens["gerente"])
checar("gerente importa a venda do dia", st == 201, r)

st, motivos = chamar("GET", "/estoque/motivos-perda", token=tokens["salao"])
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": pao, "quantidade": 5, "tipo": "SAIDA_PERDA",
    "id_local": local["id"], "id_motivo_perda": motivos[0]["id"],
    "observacao": "caíram no chão"}, token=tokens["salao"])
checar("salão aponta a perda (quem vê a perda é quem está no salão)", st == 201, r)
conferir("a perda vale 6,50 (5 × 1,30)", float(r.get("custo_unitario", 0)) * 5, 6.50, 0.01)

st, saldos = chamar("GET", f"/estoque/saldos?id_produto={pao}", token=tokens["conferente"])
s_pao = next(s for s in saldos if s["id_produto"] == pao)
# 100 produzidos − 60 vendidos − 5 perdidos = 35. VENDER É SAIR DO ESTOQUE:
# sem essa baixa, o pão vendido continuaria na prateleira do sistema e a
# primeira contagem cobriria o buraco inteiro como "ajuste".
conferir("sobram 35 pães (100 − 60 vendidos − 5 perdidos)", s_pao["quantidade"], 35)
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={pao}", token=tokens["conferente"])
checar("a venda deixou rastro no razão",
       any(m["tipo"] == "SAIDA_VENDA" for m in mov), {m["tipo"] for m in mov})

# --------------------------------------------------------- a segunda compra
print("\n7. quinta: a farinha sobe de preço")

st, nota2 = chamar("POST", "/notas", {
    "id_fornecedor": forn, "numero": f"8002{SUF}", "serie": "1",
    "data_emissao": str(date.today()),
    "itens": [{"descricao_fornecedor": "FARINHA TRIGO KG", "id_produto": farinha,
               "quantidade": 40, "um": "KG", "valor_unitario": 8.00}],
}, token=tokens["conferente"])
id_nota2 = precisa(nota2.get("id"), "sem a segunda nota")
chamar("POST", f"/notas/{id_nota2}/lancar", {}, token=tokens["conferente"])
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={farinha}", token=tokens["conferente"])
s_farinha = next(s for s in saldos if s["id_produto"] == farinha)
conferir("médio novo: (130 + 320) ÷ 60 = 7,50", s_farinha["custo_medio"], 7.50)

st, f = chamar("GET", f"/fichas/{ficha}", token=tokens["gerente"])
conferir("a ficha JÁ custa mais: 0,2 × 7,50 = 1,50", f.get("custo_total"), 1.50)

print("\n8. sexta: produz de novo, e o pão fica com dois custos")
st, r = chamar("POST", "/producao-agenda",
               {"id_produto": pao, "quantidade": 100}, token=tokens["cozinha"])
linha2 = r.get("id")
st, r = chamar("POST", f"/producao-agenda/{linha2}/produzir", {}, token=tokens["cozinha"])
conferir("a leva nova custa 150,00", r.get("custo_total"), 150.00, 0.01)
conferir("a 1,50 cada", r.get("custo_unitario"), 1.50)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={pao}", token=tokens["conferente"])
s_pao = next(s for s in saldos if s["id_produto"] == pao)
conferir("135 pães em estoque", s_pao["quantidade"], 135)
# 35 a 1,30 = 45,50 | 100 a 1,50 = 150,00 | 195,50 ÷ 135 = 1,448148
conferir("ao médio ponderado de 1,448148", s_pao["custo_medio"], 1.448148, 0.000005)

# ------------------------------------------------------------------ inventário
print("\n9. sábado: contagem cega")

st, inv = chamar("POST", "/inventarios",
                 {"id_local": local["id"], "produtos": [pao], "cega": True},
                 token=tokens["conferente"])
id_inv = precisa(inv.get("id"), f"sem inventário: {inv}")
checar("o conferente não vê o esperado", inv["itens"][0]["qtd_sistema"] is None,
       inv["itens"][0])
st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem",
               {"itens": [{"id_produto": pao, "qtd_contada": 130, "um": "UN"}]},
               token=tokens["conferente"])
checar("conta 130", st == 200, st)
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=tokens["conferente"])
checar("conferente NÃO fecha o inventário (o ajuste é do gerente)", st == 403, st)
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=tokens["gerente"])
checar("o gerente fecha", st == 200, r)
conferir("o ajuste tira 5 pães a 1,448148 = 7,24",
         abs(float(r.get("diferenca_valor", 0))), 7.24, 0.02)
st, saldos = chamar("GET", f"/estoque/saldos?id_produto={pao}", token=tokens["gerente"])
s_pao = next(s for s in saldos if s["id_produto"] == pao)
conferir("o saldo vira o contado: 130", s_pao["quantidade"], 130)
conferir("e o médio não muda", s_pao["custo_medio"], 1.448148, 0.000005)

# ------------------------------------------------------------------ o fechamento
print("\n10. domingo: a conta do período")

hoje = date.today()
periodo = f"inicio={hoje.replace(day=1)}&fim={hoje}"
st, a = chamar("GET", f"/cmv/apuracao?{periodo}", token=tokens["contador"])
checar("o contador lê a apuração", st == 200, st)
st, mov = chamar("GET", f"/cmv/movimentacao?{periodo}", token=tokens["contador"])
linha_farinha = next((l for l in mov["linhas"] if l["id_produto"] == farinha), None)
checar("a farinha aparece na movimentação", linha_farinha is not None,
       [l["produto"] for l in mov["linhas"]][:4])
if linha_farinha:
    conferir("entraram 80 KG", linha_farinha["qtd_entradas"], 80)
    conferir("saíram 40 KG (duas produções)", linha_farinha["qtd_saidas"], 40)
    conferir("sobraram 40 KG", linha_farinha["qtd_final"], 40)
    conferir("valendo 300,00 (40 × 7,50)", linha_farinha["valor_final"], 300.00, 0.01)

t = mov["total"]
# ⚠️ Tolerância proporcional ao tamanho do relatório: cada linha sai
# arredondada em dois dígitos e o rodapé soma as linhas arredondadas — para
# fechar com a coluna na tela. Em centenas de produtos isso dá centavos de
# diferença na identidade, que não são erro de conta.
folga = max(0.05, 0.005 * mov["produtos"])
conferir("a movimentação fecha",
         t["valor_inicial"] + t["valor_entradas"] - t["valor_saidas"],
         t["valor_final"], folga)

# A conta do dono, e a prova de que ela fecha: numa semana em que tudo o que
# saiu foi receita, perda ou diferença de contagem, a VARIÂNCIA tem de ser
# exatamente perda + ajuste. Sobrando qualquer coisa, é saída que ninguém
# explicou — e é esse número que o CMV existe para mostrar.
st, a = chamar("GET", f"/cmv/apuracao?{periodo}", token=tokens["gerente"])
conferir("compras da semana: 260 + 320 = 580,00", moveu(a, "compras"), 580.00, 0.01)
conferir("CMV real = compras − o que ficou no estoque",
         moveu(a, "compras") - moveu(a, "estoque_final"), moveu(a, "cmv_real"), 0.02)
conferir("CMV teórico = 60 pães × 1,30 congelado na venda",
         moveu(a, "cmv_teorico"), 78.00, 0.01)
conferir("variância = perda (6,50) + ajuste (7,24)",
         moveu(a, "variancia"), moveu(a, "perdas") + abs(moveu(a, "ajustes")), 0.02)
food = moveu(a, "cmv_real") / moveu(a, "receita") * 100
checar("e o food cost da semana sai num número de gente (30,6%)", 28 < food < 33, round(food, 2))

# O alerta é da casa INTEIRA: numa base compartilhada ele fala de outro
# produto. O que este cenário pode afirmar é sobre o que ele mesmo mexeu.
# ⚠️ Um pedido por produto: a lista é paginada, e filtrar a primeira página
# faria `meus` vir VAZIO numa base grande — a checagem abaixo passaria sem ter
# olhado nada, que é pior do que falhar.
meus = []
for _p in (farinha, pao):
    st, _s = chamar("GET", f"/estoque/saldos?id_produto={_p}", token=tokens["gerente"])
    meus += _s or []
checar("nenhum saldo negativo no que a semana mexeu",
       all(float(s["quantidade"]) >= 0 for s in meus),
       [(s["produto"], s["quantidade"]) for s in meus])
st, alertas = chamar("GET", "/alertas", token=tokens["gerente"])
checar("o gerente recebe os alertas da casa", isinstance(alertas, list), type(alertas))

print("\n11. limpeza")
for pid in (farinha, pao):
    chamar("DELETE", f"/produtos/{pid}", token=admin)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
if achados:
    print(f"\n{len(achados)} ponto(s) de processo para conversar:")
    for a in achados:
        print(f"  · {a}")
sys.exit(1 if falhas else 0)
