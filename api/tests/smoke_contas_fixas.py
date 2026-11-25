"""Contas fixas e parcelas (migração 167, módulo Financeiro, etapa 3).

O que este arquivo cobra:

1. parcelar: 100 em 3 = 33,34 + 33,33 + 33,33 (a soma é o total), um mês entre as parcelas,
   31 em fevereiro vira o último dia, "parcela 2/3", mesmo lote; mais de 60 parcelas é recusado
2. a conta fixa gera o mês SÓ na antecedência do vencimento, uma vez por mês (o banco garante),
   não regenera o mês cancelado, gera os meses atrasados de uma vez e nunca volta para trás
3. mudar a conta fixa vale para os meses seguintes; encerrar para de gerar (e cancela as em
   aberto, se pedido); reativar volta a gerar do mês seguinte ao último
4. débito automático nasce AGENDADO; valor variável avisa que é previsão
5. validação, permissão (a cozinha não vê) e os relatórios

⚠️ As datas futuras são simuladas chamando `contas_fixas.gerar(hoje=..., so_ids=[...])` direto:
só as contas fixas do teste, para não gerar meses futuros das contas fixas de verdade.

    python tests/smoke_contas_fixas.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
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
criadas: list[int] = []
fixas: list[int] = []
pessoas: list[int] = []

from database import get_cursor  # noqa: E402
from services import contas_fixas as cf  # noqa: E402


def _limpar():
    try:
        with get_cursor() as cur:
            if fixas:
                cur.execute("DELETE FROM contas_pagar WHERE id_conta_fixa = ANY(%s)", (fixas,))
            if criadas:
                cur.execute("DELETE FROM contas_pagar WHERE id = ANY(%s)", (criadas,))
            if fixas:
                cur.execute("DELETE FROM contas_fixas WHERE id = ANY(%s)", (fixas,))
            for p in pessoas:
                cur.execute("UPDATE fornecedores SET ativo = false WHERE id = %s", (p,))
    except Exception as e:  # noqa: BLE001
        print("limpeza falhou:", e)


atexit.register(_limpar)


def contas_da_fixa(id_fixa):
    with get_cursor() as cur:
        cur.execute("""SELECT id, competencia, vencimento, valor, status, descricao, observacao,
                              agendado_para, forma, baixa_automatica
                         FROM contas_pagar WHERE id_conta_fixa = %s ORDER BY competencia""", (id_fixa,))
        return [dict(x) for x in cur.fetchall()]


def gerar(dia, *ids):
    with get_cursor() as cur:
        return cf.gerar(cur, dia, list(ids))


print("0. preparo")
s, p = chamar("POST", "/fornecedores", {"nome": f"Imobiliária {marca}", "fornecedor": True}, token=token)
checar("a pessoa nasce", s == 201, (s, p))
pessoas.append(p["id"])
pessoa = p["id"]
s, cats = chamar("GET", "/contas-pagar/categorias", token=token)
aluguel = next((c["id"] for c in cats if c["nome"] == "Aluguel"), None)

print("1. parcelar")
s, pc = chamar("POST", "/contas-pagar", {
    "id_pessoa": pessoa, "id_categoria": aluguel, "descricao": f"Freezer {marca}",
    "competencia": "2030-01-15", "vencimento": "2030-01-31", "valor": 100, "parcelas": 3}, token=token)
checar("lança em 3 parcelas", s == 201 and len(pc.get("ids", [])) == 3, (s, pc))
criadas += pc.get("ids", [])
with get_cursor() as cur:
    cur.execute("""SELECT valor, vencimento, competencia, parcela, parcelas, lote FROM contas_pagar
                    WHERE id = ANY(%s) ORDER BY parcela""", (pc["ids"],))
    ps = [dict(x) for x in cur.fetchall()]
checar("100 em 3: 33,34 + 33,33 + 33,33", [float(x["valor"]) for x in ps] == [33.34, 33.33, 33.33], ps)
checar("a soma das parcelas é o total", igual(sum(float(x["valor"]) for x in ps), 100))
checar("um mês entre elas, e 31 em fevereiro vira o último dia",
       [str(x["vencimento"]) for x in ps] == ["2030-01-31", "2030-02-28", "2030-03-31"], ps)
checar("parcela 1/3, 2/3, 3/3 no mesmo lote",
       [(x["parcela"], x["parcelas"]) for x in ps] == [(1, 3), (2, 3), (3, 3)]
       and len({x["lote"] for x in ps}) == 1 and ps[0]["lote"].startswith("PC"), ps)
checar("a competência é a da compra em todas", all(str(x["competencia"]) == "2030-01-15" for x in ps))
checar("a mensagem diz as parcelas", "3x" in pc.get("message", ""), pc)
s, _ = chamar("POST", "/contas-pagar", {
    "id_pessoa": pessoa, "descricao": "x", "competencia": "2030-01-15", "vencimento": "2030-01-31",
    "valor": 100, "parcelas": 61}, token=token)
checar("mais de 60 parcelas: 422", s == 422, s)
s, um = chamar("POST", "/contas-pagar", {
    "id_pessoa": pessoa, "descricao": f"Avulsa {marca}", "competencia": "2030-01-15",
    "vencimento": "2030-01-31", "valor": 80}, token=token)
criadas.append(um["id"])
with get_cursor() as cur:
    cur.execute("SELECT parcela, parcelas FROM contas_pagar WHERE id = %s", (um["id"],))
    x = cur.fetchone()
checar("sem parcelar, a conta não tem parcela", x["parcela"] is None and x["parcelas"] is None, x)
s, l = chamar("GET", f"/contas-pagar?status=A_PAGAR&busca=Freezer {marca}&limite=50".replace(" ", "%20"), token=token)
checar("a lista traz parcela e parcelas", s == 200 and any(c.get("parcelas") == 3 for c in l["itens"]), l)
s, d = chamar("GET", "/exportar/contas-pagar/dados?inicio=2030-01-01&fim=2030-04-30&situacao_pagar=A_PAGAR",
              token=token)
checar("o relatório mostra a parcela", "parcela 2/3" in json.dumps(d, ensure_ascii=False, default=str),
       str(d)[:300])

print("2. a conta fixa gera o mês na antecedência")
fixa = {"id_pessoa": pessoa, "id_categoria": aluguel, "descricao": f"Aluguel {marca}", "valor": 1500,
        "dia_vencimento": 31, "inicio": "2031-01-20", "antecedencia_dias": 10}
s, fx = chamar("POST", "/contas-pagar/fixas", fixa, token=token)
checar("cria a conta fixa", s == 201 and fx.get("id"), (s, fx))
fixas.append(fx["id"])
checar("com início no futuro, nada nasce agora", fx.get("geradas") == [], fx)
with get_cursor() as cur:
    cur.execute("SELECT inicio FROM contas_fixas WHERE id = %s", (fx["id"],))
    checar("o início vira o dia 1º do mês", str(cur.fetchone()["inicio"]) == "2031-01-01")
checar("antes da antecedência, não gera", gerar(date(2031, 1, 20), fx["id"]) == [])
g = gerar(date(2031, 1, 21), fx["id"])
checar("10 dias antes do dia 31, gera janeiro", len(g) == 1, g)
cs = contas_da_fixa(fx["id"])
checar("a conta de janeiro: vence 31/01, competência 01/01, a pagar, 1.500",
       len(cs) == 1 and str(cs[0]["vencimento"]) == "2031-01-31" and str(cs[0]["competencia"]) == "2031-01-01"
       and cs[0]["status"] == "A_PAGAR" and igual(cs[0]["valor"], 1500), cs)
checar("a descrição leva o mês", cs[0]["descricao"] == f"Aluguel {marca} — jan/2031", cs[0]["descricao"])
checar("rodar de novo no mesmo dia não duplica", gerar(date(2031, 1, 21), fx["id"]) == []
       and len(contas_da_fixa(fx["id"])) == 1)
g = gerar(date(2031, 2, 18), fx["id"])
cs = contas_da_fixa(fx["id"])
checar("fevereiro vence no dia 28 (não há 31)", len(g) == 1 and str(cs[1]["vencimento"]) == "2031-02-28", cs)
s, r = chamar("POST", "/contas-pagar/cancelar", {"ids": [cs[1]["id"]]}, token=token)
checar("cancela a de fevereiro", s == 200, (s, r))
checar("e ela não nasce de novo", gerar(date(2031, 2, 20), fx["id"]) == [])
g = gerar(date(2031, 5, 1), fx["id"])
checar("um salto no tempo gera os meses que faltam de uma vez (março e abril, maio ainda não)",
       [str(x["mes"]) for x in g] == ["2031-03-01", "2031-04-01"], g)
s, lf = chamar("GET", "/contas-pagar/fixas", token=token)
meu = next((x for x in (lf or []) if x["id"] == fx["id"]), None)
checar("a lista diz o próximo: maio, vencendo 31/05",
       meu and meu["proxima"] and meu["proxima"]["mes"] == "2031-05-01"
       and meu["proxima"]["vencimento"] == "2031-05-31", meu)
checar("e conta as que estão em aberto (jan, mar, abr)", meu and meu["em_aberto"] == 3, meu)

print("3. mudar, encerrar, reativar")
s, r = chamar("PUT", f"/contas-pagar/fixas/{fx['id']}", {**fixa, "valor": 1650}, token=token)
checar("muda o valor", s == 200, (s, r))
checar("a já gerada não muda", igual(contas_da_fixa(fx["id"])[0]["valor"], 1500))
gerar(date(2031, 5, 21), fx["id"])
checar("a de maio nasce com o valor novo", igual(contas_da_fixa(fx["id"])[-1]["valor"], 1650),
       contas_da_fixa(fx["id"])[-1])
s, r = chamar("POST", f"/contas-pagar/fixas/{fx['id']}/encerrar", {"cancelar_abertas": True}, token=token)
checar("encerra cancelando as em aberto (jan, mar, abr, mai)", s == 200 and len(r["canceladas"]) == 4, (s, r))
checar("encerrada, não gera mais", gerar(date(2031, 9, 1), fx["id"]) == [])
s, r = chamar("PUT", f"/contas-pagar/fixas/{fx['id']}", fixa, token=token)
checar("encerrada não se altera: 409", s == 409, s)
s, r = chamar("POST", f"/contas-pagar/fixas/{fx['id']}/encerrar", {}, token=token)
checar("encerrar de novo: 409", s == 409, s)
s, lf = chamar("GET", "/contas-pagar/fixas", token=token)
checar("a encerrada sai da lista padrão", not any(x["id"] == fx["id"] for x in lf))
s, lf = chamar("GET", "/contas-pagar/fixas?encerradas=true", token=token)
checar("e aparece pedindo as encerradas", any(x["id"] == fx["id"] and not x["ativo"] for x in lf))
s, r = chamar("POST", f"/contas-pagar/fixas/{fx['id']}/reativar", {}, token=token)
checar("reativa", s == 200, (s, r))
g = gerar(date(2031, 6, 25), fx["id"])
checar("reativada, continua do mês seguinte ao último (junho), sem voltar atrás",
       [str(x["mes"]) for x in g] == ["2031-06-01"], g)

print("4. débito automático e valor variável")
s, fx2 = chamar("POST", "/contas-pagar/fixas", {
    "id_pessoa": pessoa, "descricao": f"Luz {marca}", "valor": 420, "valor_variavel": True,
    "dia_vencimento": 5, "inicio": "2031-01-01", "antecedencia_dias": 0, "agendar": True,
    "forma": "BOLETO"}, token=token)
checar("cria a conta de débito automático", s == 201, (s, fx2))
fixas.append(fx2["id"])
gerar(date(2031, 1, 5), fx2["id"])
c2 = contas_da_fixa(fx2["id"])
checar("nasce AGENDADA para o vencimento, por boleto, com baixa automática",
       len(c2) == 1 and c2[0]["status"] == "AGENDADO" and str(c2[0]["agendado_para"]) == "2031-01-05"
       and c2[0]["forma"] == "BOLETO" and c2[0]["baixa_automatica"], c2)
checar("e avisa que o valor é previsão", "valor previsto" in (c2[0]["observacao"] or ""), c2)

print("5. validação, geração na hora, permissão e relatórios")
s, _ = chamar("POST", "/contas-pagar/fixas", {**fixa, "agendar": True}, token=token)
checar("agendar sem forma: 400", s == 400, s)
s, _ = chamar("POST", "/contas-pagar/fixas", {**fixa, "fim": "2030-01-01"}, token=token)
checar("último mês antes do primeiro: 400", s == 400, s)
s, _ = chamar("POST", "/contas-pagar/fixas", {**fixa, "dia_vencimento": 32}, token=token)
checar("dia 32: 422", s == 422, s)
s, fx3 = chamar("POST", "/contas-pagar/fixas", {
    "id_pessoa": pessoa, "descricao": f"Internet {marca}", "valor": 99.9,
    "dia_vencimento": hoje.day, "inicio": str(hoje.replace(day=1)), "antecedencia_dias": 0}, token=token)
fixas.append(fx3["id"])
checar("vencendo hoje, a conta deste mês nasce na hora", s == 201 and len(fx3.get("geradas", [])) == 1, (s, fx3))
_s, papeis = chamar("GET", "/papeis", token=token)
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
_s, unidades = chamar("GET", "/unidades", token=token)
matriz = next(u["id"] for u in unidades if u.get("matriz"))
email = f"fixas{marca}@teste.botane"
chamar("POST", "/usuarios", {"nome": f"Sem financeiro {marca}", "email": email, "senha": "Teste#12345",
                             "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz}]}, token=token)
_s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
tk = (lg or {}).get("access_token")
s, _ = chamar("GET", "/contas-pagar/fixas", token=tk)
checar("a cozinha não vê as contas fixas: 403", s == 403, s)
s, _ = chamar("POST", "/contas-pagar/fixas", fixa, token=tk)
checar("nem cria: 403", s == 403, s)
s, d = chamar("GET", "/exportar/contas-fixas/dados", token=token)
texto = json.dumps(d, ensure_ascii=False, default=str)
checar("o relatório das contas fixas responde, com as do teste",
       s == 200 and f"Internet {marca}" in texto and "Total por mês" in texto, (s, texto[:300]))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
