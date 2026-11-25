"""Contas a pagar (migração 163, módulo Financeiro).

O que este arquivo cobra:

1. lançar: pessoa do cadastro, categoria, valor; a validação recusa pessoa que não existe,
   valor zero e categoria inventada
2. a equipe do dia: uma conta por pessoa, no mesmo lote; a mesma pessoa duas vezes é recusada;
   o último valor da pessoa volta para preencher a próxima
3. agendar e a BAIXA AUTOMÁTICA: o agendado com a data chegada vira PAGO na data agendada,
   marcado como automático; sem a marca, continua agendado
4. pagar à mão (com valor diferente só numa conta), estornar (volta ao que era), cancelar
5. as transições erradas são recusadas (pagar o pago, cancelar o pago, estornar o aberto)
6. o comprovante: anexar em várias contas, sair só por rota autenticada, trocar
7. o resumo (atrasado, hoje) e os totais do recorte
8. permissões: quem não tem `financeiro.pagar_*` recebe 403
9. a chave Pix no cadastro de Pessoas
10. os relatórios respondem

    python tests/smoke_contas_pagar.py      (API de pé na 9200)
"""

import atexit
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
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
            c = r.read()
            return r.status, (c if bruto else json.loads(c or b"null"))
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def anexar(ids, conteudo, tipo, token):
    fr = uuid.uuid4().hex
    corpo = (f'--{fr}\r\nContent-Disposition: form-data; name="ids"\r\n\r\n{",".join(map(str, ids))}\r\n'
             f'--{fr}\r\nContent-Disposition: form-data; name="arquivo"; filename="c.png"\r\n'
             f"Content-Type: {tipo}\r\n\r\n").encode() + conteudo + f"\r\n--{fr}--\r\n".encode()
    req = urllib.request.Request(BASE + "/contas-pagar/comprovante", data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={fr}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Unidade", "1")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


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
ontem = hoje - timedelta(days=1)
criadas: list[int] = []
pessoas: list[int] = []


def _limpar():
    try:
        from database import get_cursor
        with get_cursor() as cur:
            if criadas:
                cur.execute("DELETE FROM contas_pagar WHERE id = ANY(%s)", (criadas,))
            for p in pessoas:
                cur.execute("UPDATE fornecedores SET ativo = false WHERE id = %s", (p,))
    except Exception:
        pass


atexit.register(_limpar)


def conta(i):
    from database import get_cursor
    with get_cursor() as cur:
        cur.execute("SELECT * FROM contas_pagar WHERE id = %s", (i,))
        return dict(cur.fetchone() or {})


print("0. preparo: três freelancers com chave Pix")
for n in range(3):
    s, p = chamar("POST", "/fornecedores", {"nome": f"Freela {marca} {n}", "fornecedor": False,
                                            "cnpj": f"{marca}{n:04d}"[:11], "chave_pix": f"freela{n}@{marca}.pix"},
                  token=token)
    checar(f"freelancer {n} nasce com chave Pix", s == 201, (s, p))
    pessoas.append(p["id"])
s, f0 = chamar("GET", f"/fornecedores/{pessoas[0]}", token=token)
checar("a chave Pix volta no cadastro", f0.get("chave_pix") == f"freela0@{marca}.pix", f0)
s, cats = chamar("GET", "/contas-pagar/categorias", token=token)
freela = next((c["id"] for c in cats if c["nome"] == "Freelancer"), None)
checar("as categorias iniciais existem, com Freelancer", freela is not None, cats)

print("1. lançar")
base = {"id_pessoa": pessoas[0], "id_categoria": freela, "descricao": f"Diária {marca}",
        "funcao": "garçom", "competencia": str(ontem), "vencimento": str(ontem), "valor": 150}
s, a = chamar("POST", "/contas-pagar", base, token=token)
checar("lança", s == 201 and a.get("id"), (s, a))
criadas.append(a["id"])
checar("nasce A_PAGAR", conta(a["id"])["status"] == "A_PAGAR")
s, _ = chamar("POST", "/contas-pagar", {**base, "id_pessoa": 999999999}, token=token)
checar("pessoa que não existe: 400", s == 400, s)
s, _ = chamar("POST", "/contas-pagar", {**base, "valor": 0}, token=token)
checar("valor zero: 422", s == 422, s)
s, _ = chamar("POST", "/contas-pagar", {**base, "id_categoria": 999999}, token=token)
checar("categoria inventada: 400", s == 400, s)

print("2. a equipe do dia")
s, eq = chamar("POST", "/contas-pagar/equipe", {
    "data": str(hoje), "vencimento": str(hoje + timedelta(days=2)), "id_categoria": freela,
    "descricao": f"Diária {marca}",
    "itens": [{"id_pessoa": pessoas[1], "valor": 120, "funcao": "cozinha"},
              {"id_pessoa": pessoas[2], "valor": 100.5}]}, token=token)
checar("lança duas contas no mesmo lote", s == 201 and len(eq["ids"]) == 2, (s, eq))
criadas.extend(eq.get("ids", []))
checar("as duas com o mesmo lote", len({conta(i)["lote"] for i in eq["ids"]}) == 1)
s, _ = chamar("POST", "/contas-pagar/equipe", {
    "data": str(hoje), "vencimento": str(hoje), "itens": [{"id_pessoa": pessoas[1], "valor": 1},
                                                           {"id_pessoa": pessoas[1], "valor": 2}]}, token=token)
checar("a mesma pessoa duas vezes: 400", s == 400, s)
s, u = chamar("GET", f"/contas-pagar/pessoa/{pessoas[1]}/ultimo", token=token)
checar("o último valor e a função voltam para a próxima", igual(u.get("valor"), 120) and u.get("funcao") == "cozinha", u)

print("3. agendar e a baixa automática")
b_id, c_id = eq["ids"]
s, r = chamar("POST", "/contas-pagar/agendar", {"ids": [a["id"]], "data": str(ontem), "forma": "PIX"}, token=token)
checar("agenda para ontem, com baixa automática", s == 200, (s, r))
s, r = chamar("POST", "/contas-pagar/agendar", {"ids": [b_id], "data": str(ontem), "forma": "PIX",
                                                "baixa_automatica": False}, token=token)
s, lst = chamar("GET", f"/contas-pagar?status=PAGO&busca={marca}", token=token)
ca = conta(a["id"])
checar("a leitura da tela já baixou a de ontem: PAGO, na data agendada, automática",
       ca["status"] == "PAGO" and ca["pago_em"] == ontem and ca["baixado_automaticamente"]
       and igual(ca["valor_pago"], 150), ca)
checar("sem a marca, a outra continua AGENDADO", conta(b_id)["status"] == "AGENDADO")
s, res = chamar("GET", "/contas-pagar/resumo", token=token)
checar("o resumo responde", s == 200 and "atrasado" in res, res)

print("4. pagar, estornar, cancelar")
s, r = chamar("POST", "/contas-pagar/estornar", {"ids": [a["id"]]}, token=token)
ca = conta(a["id"])
checar("estornar a automática volta a AGENDADO, sem baixa automática de novo",
       s == 200 and ca["status"] == "AGENDADO" and ca["pago_em"] is None and not ca["baixa_automatica"], ca)
s, r = chamar("POST", "/contas-pagar/pagar", {"ids": [a["id"]], "pago_em": str(hoje), "forma": "DINHEIRO",
                                              "valor_pago": 140}, token=token)
ca = conta(a["id"])
checar("pagar à mão com valor diferente (desconto)", s == 200 and ca["status"] == "PAGO"
       and igual(ca["valor_pago"], 140) and not ca["baixado_automaticamente"] and ca["pago_por"], ca)
s, _ = chamar("POST", "/contas-pagar/pagar", {"ids": [b_id, c_id], "pago_em": str(hoje), "forma": "PIX",
                                              "valor_pago": 10}, token=token)
checar("valor diferente em várias contas: 400", s == 400, s)
s, _ = chamar("POST", "/contas-pagar/pagar", {"ids": [a["id"]], "pago_em": str(hoje), "forma": "PIX"}, token=token)
checar("pagar o que já foi pago: 409", s == 409, s)
s, _ = chamar("POST", "/contas-pagar/cancelar", {"ids": [a["id"]]}, token=token)
checar("cancelar o pago: 409", s == 409, s)
s, _ = chamar("POST", "/contas-pagar/estornar", {"ids": [c_id]}, token=token)
checar("estornar o que está em aberto: 409", s == 409, s)
s, r = chamar("POST", "/contas-pagar/pagar", {"ids": [b_id, c_id], "pago_em": str(hoje), "forma": "PIX"}, token=token)
checar("pagar as duas da equipe de uma vez, cada uma pelo seu valor",
       s == 200 and igual(conta(b_id)["valor_pago"], 120) and igual(conta(c_id)["valor_pago"], 100.5), r)

print("5. o comprovante")
s, r = anexar([b_id, c_id], PNG, "image/png", token)
checar("anexa um comprovante nas duas", s == 200, (s, r))
s, img = chamar("GET", f"/contas-pagar/{b_id}/comprovante", token=token, bruto=True)
checar("sai pela rota autenticada", s == 200 and img[:4] == PNG[:4], s)
s, _ = chamar("GET", f"/contas-pagar/{b_id}/comprovante", bruto=True)
checar("sem login: 401", s == 401, s)
s, r = anexar([b_id], b"%PDF-1.4 teste", "application/pdf", token)
checar("PDF também vale, e troca o de uma só", s == 200 and conta(b_id)["comprovante"] != conta(c_id)["comprovante"], (s, r))
s, _ = anexar([c_id], b"nao e imagem", "image/png", token)
checar("arquivo que não é imagem: 400", s == 400, s)

print("6. a lista, os totais e o cancelamento")
s, d = chamar("POST", "/contas-pagar", {**base, "competencia": str(hoje), "vencimento": str(ontem - timedelta(days=3)),
                                        "descricao": f"Atrasada {marca}"}, token=token)
criadas.append(d["id"])
s, l = chamar("GET", f"/contas-pagar?status=A_PAGAR&busca={marca}", token=token)
checar("a lista traz a atrasada marcada, e os totais do recorte",
       any(x["id"] == d["id"] and x["atrasada"] for x in l["itens"]) and l["totais"]["atrasadas"] >= 1, l.get("totais"))
s, l = chamar("GET", f"/contas-pagar?status=PAGO&busca={marca}", token=token)
checar("os pagos somam pelo valor pago (140 + 120 + 100,50)", igual(l["totais"]["valor"], 360.5), l["totais"])
s, r = chamar("POST", "/contas-pagar/cancelar", {"ids": [d["id"]]}, token=token)
checar("cancelar a aberta", s == 200 and conta(d["id"])["status"] == "CANCELADO", (s, r))

print("7. permissões")
_s, papeis = chamar("GET", "/papeis", token=token)
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
_s, unidades = chamar("GET", "/unidades", token=token)
matriz = next(u["id"] for u in unidades if u.get("matriz"))
email = f"pagar{marca}@teste.botane"
chamar("POST", "/usuarios", {"nome": f"Sem financeiro {marca}", "email": email, "senha": "Teste#12345",
                             "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz}]}, token=token)
_s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
tk = (lg or {}).get("access_token")
s, _ = chamar("GET", "/contas-pagar", token=tk)
checar("a cozinha não vê as contas a pagar: 403", s == 403, s)
s, _ = chamar("POST", "/contas-pagar", base, token=tk)
checar("nem lança: 403", s == 403, s)

print("8. relatórios")
for rel in ("contas-pagar", "pagamentos-pessoa"):
    s, dados = chamar("GET", f"/exportar/{rel}/dados?inicio={ontem - timedelta(days=5)}&fim={hoje + timedelta(days=5)}",
                      token=token)
    checar(f"o relatório {rel} responde com as contas do teste",
           s == 200 and marca in json.dumps(dados, ensure_ascii=False, default=str), (s, str(dados)[:200]))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
