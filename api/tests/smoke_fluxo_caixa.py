"""Fluxo de caixa (módulo Financeiro, etapa 4 — sem migração).

O que este arquivo cobra:

1. entradas: vendas por forma, com o dinheiro líquido do troco; venda sem forma vira "não
   informado"; venda cancelada, com pessoa, consumo interno e paga em vale NÃO entram
2. contas a receber: o lote recebido entra na data da baixa; permuta não; o lote em cobrança fica
   "sem data", fora dos dias
3. saídas: pago pela data do pagamento e pelo valor pago; em aberto pelo vencimento; agendada pela
   data agendada; a conta fixa que ainda não nasceu entra no vencimento; o atrasado cai em hoje
4. taxas de cartão estimadas pela taxa da loja; saldo do dia, acumulado e saldo inicial
5. previsão de vendas: média do mesmo dia da semana nas quatro semanas antes de hoje
6. validação, permissão (a cozinha não vê) e o relatório

🔑 Tudo é medido como DIFERENÇA contra o fluxo antes do teste, numa janela de 2032: a base pode
ter contas fixas de verdade que projetam meses lá na frente.

    python tests/smoke_fluxo_caixa.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ORIGEM = "SMOKE_FLUXO"
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = None
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
        dados = json.dumps(corpo, default=str).encode()
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def igual(a, b):
    return a is not None and abs(float(a) - float(b)) < 0.005


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 1000)[-7:]
hoje = date.today()
contas: list[int] = []
fixas: list[int] = []
lotes: list[int] = []
pessoas: list[int] = []
taxas_antes: list[dict] = []
email = f"fluxo{marca}@teste.botane"

from database import get_cursor  # noqa: E402
from services import fluxo_caixa as fc  # noqa: E402


def _limpar():
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM vendas WHERE origem = %s", (ORIGEM,))
            if lotes:
                cur.execute("DELETE FROM consumo_lotes WHERE id = ANY(%s)", (lotes,))
            if fixas:
                cur.execute("DELETE FROM contas_pagar WHERE id_conta_fixa = ANY(%s)", (fixas,))
            if contas:
                cur.execute("DELETE FROM contas_pagar WHERE id = ANY(%s)", (contas,))
            if fixas:
                cur.execute("DELETE FROM contas_fixas WHERE id = ANY(%s)", (fixas,))
            cur.execute("DELETE FROM forma_pagamento_taxas WHERE id_unidade = 1")
            for t in taxas_antes:
                cur.execute("""INSERT INTO forma_pagamento_taxas (id_unidade, grupo, taxa_pct)
                               VALUES (1, %s, %s)""", (t["grupo"], t["taxa_pct"]))
            for p in pessoas:
                cur.execute("UPDATE fornecedores SET ativo = false WHERE id = %s", (p,))
    except Exception as e:  # noqa: BLE001
        print("limpeza falhou:", e)


atexit.register(_limpar)

DE, ATE = "2032-03-01", "2032-03-31"


def fluxo(de=DE, ate=ATE, previsao=False, saldo=None, tk=None):
    q = f"/contas-pagar/fluxo?de={de}&ate={ate}&previsao={str(previsao).lower()}"
    if saldo is not None:
        q += f"&saldo_inicial={saldo}"
    return chamar("GET", q, token=tk or token)


def dia(f, d):
    return next(x for x in f["dias"] if x["data"] == d)


def venda(data, valor, pagamentos=(), **extra):
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO vendas (id_unidade, data, origem, documento, valor_total, cancelada,
                                   consumo_interno, id_pessoa)
               VALUES (1, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (data, ORIGEM, f"F{marca}{time.time_ns() % 10**6}", valor, extra.get("cancelada", False),
             extra.get("consumo_interno", False), extra.get("id_pessoa")))
        vid = cur.fetchone()["id"]
        for g, v in pagamentos:
            cur.execute("""INSERT INTO venda_pagamentos (id_venda, id_unidade, grupo, valor)
                           VALUES (%s, 1, %s, %s)""", (vid, g, v))
    return vid


def lote(status, total, recebido_em=None, forma=None):
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO consumo_lotes (id_unidade, id_pessoa, ate, status, total, recebido_em,
                                          forma_pagamento)
               VALUES (1, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (pessoa, recebido_em or DE, status, total, recebido_em, forma))
        lotes.append(cur.fetchone()["id"])


print("0. preparo e o fluxo de antes")
with get_cursor() as cur:
    cur.execute("DELETE FROM vendas WHERE origem = %s", (ORIGEM,))  # sobra de rodada interrompida
    cur.execute("SELECT grupo, taxa_pct FROM forma_pagamento_taxas WHERE id_unidade = 1")
    taxas_antes = [dict(x) for x in cur.fetchall()]
    # Sem taxa nenhuma durante o teste: a diferença de taxa é só a do crédito de 3% abaixo.
    cur.execute("DELETE FROM forma_pagamento_taxas WHERE id_unidade = 1")
s, p = chamar("POST", "/fornecedores", {"nome": f"Fluxo {marca}", "fornecedor": True}, token=token)
checar("a pessoa nasce", s == 201, (s, p))
pessoas.append(p["id"])
pessoa = p["id"]
s, antes = fluxo()
checar("o fluxo responde", s == 200 and len(antes["dias"]) == 31, (s, str(antes)[:200]))
s, antes_hoje = fluxo(str(hoje), str(hoje + timedelta(days=3)))
with get_cursor() as cur:
    base_prev = fc.fluxo(cur, 1, date(2032, 4, 1), date(2032, 4, 7), True, hoje=date(2032, 3, 31))

print("1. entradas: vendas por forma")
venda("2032-03-05", 200, [("CREDITO", 100), ("DINHEIRO", 120), ("TROCO", 20)])
venda("2032-03-05", 50)                                            # sem forma
venda("2032-03-05", 30, [("VALE", 30)])                            # vale-presente
venda("2032-03-05", 999, [("PIX", 999)], cancelada=True)
venda("2032-03-05", 999, [("PIX", 999)], consumo_interno=True)
venda("2032-03-05", 999, id_pessoa=pessoa)                         # consumo a receber
lote("RECEBIDO", 300, "2032-03-10", "PIX")
lote("RECEBIDO", 400, "2032-03-10", "PERMUTA")
lote("ABERTO", 70)

print("2. saídas")
s, c1 = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": f"Paga {marca}",
               "competencia": "2032-03-01", "vencimento": "2032-03-28", "valor": 160}, token=token)
contas.append(c1["id"])
s, r = chamar("POST", "/contas-pagar/pagar", {"ids": [c1["id"]], "pago_em": "2032-03-12",
              "forma": "PIX", "valor_pago": 150}, token=token)
checar("paga com desconto em 12/03", s == 200, (s, r))
s, c2 = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": f"Aberta {marca}",
               "competencia": "2032-03-01", "vencimento": "2032-03-20", "valor": 80}, token=token)
contas.append(c2["id"])
s, c3 = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": f"Agendada {marca}",
               "competencia": "2032-03-01", "vencimento": "2032-03-25", "valor": 60}, token=token)
contas.append(c3["id"])
s, r = chamar("POST", "/contas-pagar/agendar", {"ids": [c3["id"]], "data": "2032-03-22",
              "forma": "BOLETO"}, token=token)
checar("agenda para 22/03", s == 200, (s, r))
s, cx = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": f"Cancelada {marca}",
               "competencia": "2032-03-01", "vencimento": "2032-03-20", "valor": 999}, token=token)
contas.append(cx["id"])
chamar("POST", "/contas-pagar/cancelar", {"ids": [cx["id"]]}, token=token)
s, fx = chamar("POST", "/contas-pagar/fixas", {
    "id_pessoa": pessoa, "descricao": f"Aluguel {marca}", "valor": 500, "dia_vencimento": 15,
    "inicio": "2032-03-01", "fim": "2032-03-01", "antecedencia_dias": 10}, token=token)
checar("a conta fixa de março/2032 nasce como molde (sem conta ainda)",
       s == 201 and fx.get("geradas") == [], (s, fx))
fixas.append(fx["id"])
ontem = hoje - timedelta(days=1)
s, ca = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": f"Atrasada {marca}",
               "competencia": str(ontem), "vencimento": str(ontem), "valor": 45}, token=token)
contas.append(ca["id"])
with get_cursor() as cur:
    cur.execute("""INSERT INTO forma_pagamento_taxas (id_unidade, grupo, taxa_pct)
                   VALUES (1, 'CREDITO', 3)""")

s, depois = fluxo()
checar("o fluxo responde de novo", s == 200, s)
d5a, d5 = dia(antes, "2032-03-05"), dia(depois, "2032-03-05")
checar("vendas do dia: 100 crédito + 100 dinheiro líquido + 50 não informado = 250",
       igual(d5["vendas"] - d5a["vendas"], 250), (d5a["vendas"], d5["vendas"]))
checar("o dinheiro entra líquido do troco (120 − 20)",
       igual(d5["formas"].get("DINHEIRO", 0) - d5a["formas"].get("DINHEIRO", 0), 100), d5["formas"])
checar("a venda sem forma entra como não informado",
       igual(d5["formas"].get("NAO_INFORMADO", 0) - d5a["formas"].get("NAO_INFORMADO", 0), 50), d5["formas"])
checar("vale, cancelada, consumo interno e venda com pessoa não entram",
       "VALE" not in d5["formas"] and igual(d5["formas"].get("PIX", 0), d5a["formas"].get("PIX", 0)), d5["formas"])
checar("o quadro por forma soma o crédito",
       any(f["forma"] == "CREDITO" and f["rotulo"] == "Crédito" for f in depois["por_forma"]), depois["por_forma"])
checar("a venda sem forma é contada no aviso",
       depois["sem_forma"]["cupons"] - antes["sem_forma"]["cupons"] == 1, depois["sem_forma"])
checar("taxa de 3% sobre os 100 do crédito = 3,00",
       igual(d5["taxas"] - d5a["taxas"], 3), (d5a["taxas"], d5["taxas"]))
checar("as taxas estão configuradas", depois["taxas_configuradas"] is True)
d10a, d10 = dia(antes, "2032-03-10"), dia(depois, "2032-03-10")
checar("o lote recebido em Pix entra na data da baixa; a permuta não",
       igual(d10["receber"] - d10a["receber"], 300), (d10a["receber"], d10["receber"]))
checar("o lote em cobrança fica a receber sem data",
       igual(depois["a_receber_sem_data"]["em_cobranca"] - antes["a_receber_sem_data"]["em_cobranca"], 70),
       depois["a_receber_sem_data"])
d12a, d12 = dia(antes, "2032-03-12"), dia(depois, "2032-03-12")
checar("pago pela data do pagamento e pelo valor pago (150, não 160)",
       igual(d12["pago"] - d12a["pago"], 150) and d12["n_pago"] - d12a["n_pago"] == 1, d12)
checar("e não aparece no vencimento dela (28/03)",
       igual(dia(depois, "2032-03-28")["a_pagar"], dia(antes, "2032-03-28")["a_pagar"]))
checar("em aberto pelo vencimento (80 em 20/03); a cancelada não entra",
       igual(dia(depois, "2032-03-20")["a_pagar"] - dia(antes, "2032-03-20")["a_pagar"], 80))
checar("a agendada entra na data agendada (22/03), não no vencimento",
       igual(dia(depois, "2032-03-22")["a_pagar"] - dia(antes, "2032-03-22")["a_pagar"], 60)
       and igual(dia(depois, "2032-03-25")["a_pagar"], dia(antes, "2032-03-25")["a_pagar"]))
d15 = dia(depois, "2032-03-15")
checar("a conta fixa que não nasceu entra no vencimento (500 em 15/03)",
       igual(d15["fixas"] - dia(antes, "2032-03-15")["fixas"], 500)
       and any(x["descricao"] == f"Aluguel {marca}" for x in d15["fixas_previstas"]), d15)
checar("e só em março (o último mês é março)",
       not any(x["descricao"] == f"Aluguel {marca}" for d in depois["dias"] for x in d["fixas_previstas"]
               if d["data"] != "2032-03-15"))
ta, td = antes["totais"], depois["totais"]
checar("entradas do período: +250 vendas +300 recebido",
       igual(td["entradas"] - ta["entradas"], 550), (ta["entradas"], td["entradas"]))
checar("saídas do período: 150 + 80 + 60 + 500 + 3 de taxa",
       igual(td["saidas"] - ta["saidas"], 793), (ta["saidas"], td["saidas"]))
checar("saldo = entradas − saídas", igual(td["saldo"], td["entradas"] - td["saidas"]), td)
checar("a soma dos dias é o saldo do período", igual(sum(x["saldo"] for x in depois["dias"]), td["saldo"]))
checar("o acumulado do último dia é o saldo final, e o do 1º é o saldo do 1º",
       igual(depois["dias"][-1]["acumulado"], td["saldo_final"])
       and igual(depois["dias"][0]["acumulado"], depois["dias"][0]["saldo"]))
s, com_saldo = fluxo(saldo=1000)
checar("com saldo inicial de 1.000, o final sobe 1.000 e o saldo do período não muda",
       s == 200 and igual(com_saldo["totais"]["saldo_final"] - td["saldo_final"], 1000)
       and igual(com_saldo["totais"]["saldo"], td["saldo"]), (s, com_saldo.get("totais")))
checar("2032 é tudo previsto", not any(x["passado"] or x["hoje"] for x in depois["dias"]))

print("3. o atrasado cai em hoje")
s, agora = fluxo(str(hoje), str(hoje + timedelta(days=3)))
h, ha = dia(agora, str(hoje)), dia(antes_hoje, str(hoje))
checar("a conta vencida ontem entra como saída de hoje",
       igual(h["a_pagar"] - ha["a_pagar"], 45) and igual(h["atrasado"] - ha["atrasado"], 45), (ha, h))
checar("e no aviso de atrasadas", agora["atrasado"]["contas"] - antes_hoje["atrasado"]["contas"] == 1
       and h["hoje"], agora["atrasado"])
s, ontem_f = fluxo(str(ontem), str(ontem))
checar("período só com ontem: a atrasada não fica em ontem (vai para hoje)",
       s == 200 and igual(ontem_f["dias"][0]["a_pagar"], 0), ontem_f.get("dias"))

print("4. previsão de vendas")
with get_cursor() as cur:
    prev = fc.fluxo(cur, 1, date(2032, 4, 1), date(2032, 4, 7), True, hoje=date(2032, 3, 31))
pa, pd = dia(base_prev, date(2032, 4, 2)), dia(prev, date(2032, 4, 2))
# Nas 4 semanas antes de 31/03 caem as vendas de 05/03 (sexta) que são do caixa: 200 + 50 + 30.
checar("a sexta 02/04 prevê a média das 4 sextas: (200 + 50 + 30) / 4 = 70",
       igual(pd["vendas_previstas"] - pa["vendas_previstas"], 70), (pa["vendas_previstas"], pd["vendas_previstas"]))
checar("a previsão entra nas entradas e não em vendas",
       igual(pd["entradas"] - pa["entradas"], pd["vendas_previstas"] - pa["vendas_previstas"]
             + pd["receber"] - pa["receber"]) and igual(pd["vendas"], pa["vendas"]))
s, sem = fluxo("2032-04-01", "2032-04-07", previsao=False)
checar("sem a previsão, nada de vendas previstas", s == 200 and all(x["vendas_previstas"] == 0 for x in sem["dias"]))
with get_cursor() as cur:
    passado = fc.fluxo(cur, 1, date(2032, 3, 1), date(2032, 3, 31), True, hoje=date(2032, 4, 30))
checar("dia que já passou não tem previsão", all(x["vendas_previstas"] == 0 for x in passado["dias"]))

print("5. validação, permissão e relatório")
s, _ = fluxo("2032-03-10", "2032-03-01")
checar("fim antes do início: 422", s == 422, s)
s, _ = fluxo("2030-01-01", "2032-01-01")
checar("mais de 400 dias: 422", s == 422, s)
s, padrao = chamar("GET", "/contas-pagar/fluxo", token=token)
checar("sem período: do dia 1º do mês até 30 dias à frente",
       s == 200 and padrao["de"] == str(hoje.replace(day=1)) and padrao["ate"] == str(hoje + timedelta(days=30)),
       (s, padrao.get("de"), padrao.get("ate")))
_s, papeis = chamar("GET", "/papeis", token=token)
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
_s, unidades = chamar("GET", "/unidades", token=token)
matriz = next(u["id"] for u in unidades if u.get("matriz"))
chamar("POST", "/usuarios", {"nome": f"Sem financeiro {marca}", "email": email, "senha": "Teste#12345",
                             "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz}]}, token=token)
_s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
s, _ = fluxo(tk=(lg or {}).get("access_token"))
checar("a cozinha não vê o fluxo de caixa: 403", s == 403, s)
s, d = chamar("GET", f"/exportar/fluxo-caixa/dados?inicio={DE}&fim={ATE}", token=token)
texto = json.dumps(d, ensure_ascii=False, default=str)
checar("o relatório responde, com o dia 05/03 e o aluguel previsto",
       s == 200 and "05/03/2032" in texto and "15/03/2032" in texto, (s, texto[:300]))
s, cat = chamar("GET", "/exportar/catalogo", token=token)
checar("o relatório está no catálogo, no Financeiro",
       "fluxo-caixa" in json.dumps(cat, ensure_ascii=False), str(cat)[:200])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
