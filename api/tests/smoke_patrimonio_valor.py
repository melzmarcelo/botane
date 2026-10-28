"""Teste de fumaça do VALOR do patrimônio (migração 141, etapa 4).

🔑 Pedido do dono (28/10/2026): *"pode seguir com a etapa 4 do patrimônio"* — valor
patrimonial por setor e depreciação (valor de compra e vida útil, dando o valor atual), só
como relatório. Confere:

    1. A conta (linear, por mês inteiro): a cota, o mês que vira no "aniversário" da compra,
       o fim da vida útil (valor zero), a vida útil padrão, sem data e sem valor, e a baixa
       que para a conta.
    2. A data da baixa é do banco (gatilho): baixado sem data → hoje; reativado → some; a
       data no futuro é recusada; vida útil fora de 1 a 50 é recusada.
    3. `/patrimonio/valor` numa data: o "A confirmar" não conta, o comprado depois não
       conta, o baixado conta até a baixa; as somas por setor e no total.
    4. A ficha traz o valor de hoje.
    5. Os relatórios: o do valor (PDF e planilha) e o dos bens com a vida útil e o valor
       atual. A planilha da importação lê a vida útil.
    6. Cozinha (patrimonio.ver) vê o valor.

    python tests/smoke_patrimonio_valor.py      (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402
from services import patrimonio_planilha  # noqa: E402
from services.patrimonio_valor import calcular  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&.,")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def baixar(caminho, token):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&.,"))
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


print("1. a conta")
compra = date(2024, 1, 15)
b = {"valor_compra": 12000, "data_compra": compra, "vida_util_anos": None, "data_baixa": None}
r = calcular(b, date(2026, 1, 14))
checar("vida útil vazia = 10 anos (padrão)", r["vida_util"] == 10 and r["vida_padrao"], r)
checar("cota mensal = 12.000 / 120 = 100", r["quota_mensal"] == 100.0, r)
checar("um dia antes do aniversário: 23 meses (2.300)",
       r["meses"] == 23 and r["depreciacao"] == 2300.0, r)
r = calcular(b, date(2026, 1, 15))
checar("no aniversário: 24 meses, vale 9.600 (20%)",
       r["meses"] == 24 and r["valor_atual"] == 9600.0 and r["depreciado_pct"] == 20.0, r)
r = calcular(b, compra)
checar("no dia da compra vale o que custou", r["valor_atual"] == 12000.0 and r["meses"] == 0, r)
r = calcular(b, date(2040, 1, 1))
checar("depois da vida útil: zero, e totalmente depreciado",
       r["valor_atual"] == 0.0 and r["depreciado_total"] and r["meses"] == 120, r)
r = calcular(b | {"vida_util_anos": 5}, date(2026, 1, 15))
checar("vida útil de 5 anos: 24/60 (4.800)", r["depreciacao"] == 4800.0 and not r["vida_padrao"], r)
r = calcular(b | {"data_baixa": date(2025, 1, 20)}, date(2026, 1, 15))
checar("o baixado para na data da baixa (12 meses)", r["meses"] == 12, r)
r = calcular(b | {"data_compra": None}, date(2026, 1, 15))
checar("sem data de compra: vale o valor de compra, sem depreciar",
       r["sem_data"] and r["valor_atual"] == 12000.0 and r["depreciacao"] == 0.0, r)
r = calcular(b | {"valor_compra": None}, date(2026, 1, 15))
checar("sem valor de compra: sem valor atual", r["sem_valor"] and r["valor_atual"] is None, r)
r = calcular({"valor_compra": 100, "data_compra": compra, "data_baixa": None,
              "vida_util_anos": 3}, date(2024, 2, 15))
checar("os centavos arredondam (100 / 36 = 2,78)",
       r["quota_mensal"] == 2.78 and r["depreciacao"] == 2.78, r)

st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
init_pool()
setores: list[int] = []


def bem(**campos) -> dict:
    st, x = chamar("POST", "/patrimonio", {"descricao": f"Bem valor {marca}", **campos},
                   token=token)
    assert st == 201, (st, x)
    return x


try:
    print("2. a data da baixa")
    st, s = chamar("POST", "/setores", {"nome": f"SALAO VALOR {marca}"}, token=token)
    setores.append(s["id"])
    setor = s["id"]
    hoje = date.today()
    x = bem(descricao=f"Vitrine valor {marca}", id_setor=setor, valor_compra=1000,
            data_compra="2024-01-15")
    st, r = chamar("PUT", f"/patrimonio/{x['id']}",
                   {"situacao": "BAIXADO", "motivo_baixa": "vendida"}, token=token)
    checar("baixado sem data: o banco põe hoje",
           st == 200 and r["data_baixa"] == str(hoje), (st, r))
    _, x2 = chamar("GET", f"/patrimonio/{x['id']}", token=token)
    checar("e a ficha mostra a data da baixa", x2["data_baixa"] == str(hoje), x2.get("data_baixa"))
    st, r = chamar("PUT", f"/patrimonio/{x['id']}", {"data_baixa": "2025-06-01"}, token=token)
    _, x2 = chamar("GET", f"/patrimonio/{x['id']}", token=token)
    checar("a data da baixa se corrige", st == 200 and x2["data_baixa"] == "2025-06-01",
           (st, x2.get("data_baixa")))
    checar("e o valor da ficha para nela (16 meses)", x2["valor"]["meses"] == 16, x2.get("valor"))
    st, r = chamar("PUT", f"/patrimonio/{x['id']}", {"situacao": "EM_USO"}, token=token)
    _, x2 = chamar("GET", f"/patrimonio/{x['id']}", token=token)
    checar("reativado, a data da baixa some", st == 200 and x2["data_baixa"] is None,
           (st, x2.get("data_baixa")))
    st, r = chamar("PUT", f"/patrimonio/{x['id']}",
                   {"situacao": "BAIXADO", "motivo_baixa": "x", "data_baixa": "2099-01-01"},
                   token=token)
    checar("data da baixa no futuro é 400", st == 400, (st, r))
    st, r = chamar("PUT", f"/patrimonio/{x['id']}", {"vida_util_anos": 0}, token=token)
    checar("vida útil 0 é recusada (422)", st == 422, st)
    st, r = chamar("PUT", f"/patrimonio/{x['id']}", {"vida_util_anos": 51}, token=token)
    checar("e 51 também", st == 422, st)
    with get_cursor() as cur:
        cur.execute("DELETE FROM bens WHERE id = %s", (x["id"],))

    print("3. o valor numa data")
    a = bem(descricao=f"Forno valor {marca}", id_setor=setor, valor_compra=12000,
            data_compra="2024-01-15")
    b5 = bem(descricao=f"Computador valor {marca}", id_setor=setor, valor_compra=6000,
             data_compra="2024-01-15", vida_util_anos=5)
    bem(descricao=f"Sugestao valor {marca}", id_setor=setor, valor_compra=1000,
        data_compra="2024-01-15", situacao="A_CONFIRMAR")
    sem_valor = bem(descricao=f"Banco valor {marca}", id_setor=setor, data_compra="2024-01-15")
    sem_data = bem(descricao=f"Mesa valor {marca}", id_setor=setor, valor_compra=500)
    baixado = bem(descricao=f"Chapa valor {marca}", id_setor=setor, valor_compra=1200,
                  data_compra="2024-01-15", situacao="BAIXADO", motivo_baixa="quebrou",
                  data_baixa="2025-06-01")
    bem(descricao=f"Novo valor {marca}", id_setor=setor, valor_compra=3000,
        data_compra="2026-03-01")

    st, v = chamar("GET", f"/patrimonio/valor?data=2026-01-15&setores={setor}", token=token)
    codigos = {x["codigo"] for x in v["bens"]}
    checar("responde, na data pedida", st == 200 and v["data"] == "2026-01-15", (st, v.get("data")))
    checar("contam 4: o A confirmar, o comprado depois e o baixado antes ficam de fora",
           codigos == {a["codigo"], b5["codigo"], sem_valor["codigo"], sem_data["codigo"]},
           codigos)
    t = v["total"]
    checar("valor de compra 18.500 (12.000 + 6.000 + 500)", t["valor_compra"] == 18500.0, t)
    checar("depreciação 4.800 (2.400 + 2.400)", t["depreciacao"] == 4800.0, t)
    checar("valor atual 13.700", t["valor_atual"] == 13700.0, t)
    checar("1 sem valor e 1 sem data", t["sem_valor"] == 1 and t["sem_data"] == 1, t)
    checar("o setor soma igual", len(v["setores"]) == 1
           and v["setores"][0]["valor_atual"] == 13700.0 and v["setores"][0]["bens"] == 4,
           v["setores"])

    st, v = chamar("GET", f"/patrimonio/valor?data=2025-01-15&setores={setor}", token=token)
    linha = next((x for x in v["bens"] if x["codigo"] == baixado["codigo"]), None)
    checar("em 15/01/2025 o baixado em 06/2025 ainda conta",
           linha is not None and linha["depreciacao"] == 120.0
           and linha["situacao_txt"].startswith("Baixado depois"), linha)
    checar("e o total daquele dia é outro (1.200 + 1.200 + 120 de depreciação)",
           v["total"]["depreciacao"] == 2520.0 and v["total"]["valor_compra"] == 19700.0,
           v["total"])

    print("4. a ficha")
    _, fa = chamar("GET", f"/patrimonio/{a['id']}", token=token)
    esperado = calcular({"valor_compra": 12000, "data_compra": date(2024, 1, 15),
                         "vida_util_anos": None, "data_baixa": None}, date.today())
    checar("a ficha traz o valor de hoje, pela mesma conta",
           fa["valor"]["valor_atual"] == esperado["valor_atual"] and fa["valor"]["vida_padrao"],
           fa.get("valor"))

    print("5. os relatórios")
    st, tipo, pdf = baixar(f"/exportar/patrimonio-valor.pdf?data=2026-01-15&setores={setor}", token)
    checar("o relatório do valor sai em PDF", st == 200 and pdf[:4] == b"%PDF", (st, tipo))
    st, tipo, csv = baixar(f"/exportar/patrimonio-valor.csv?data=2026-01-15&setores={setor}", token)
    texto = csv.decode("utf-8-sig")
    checar("e em planilha, com o valor atual de cada bem",
           "Valor atual" in texto and a["codigo"] in texto and "10 (padrão)" in texto
           and "sem data de compra" in texto, texto[:500])
    st, tipo, rel = baixar("/exportar/patrimonio.csv?busca_bem="
                           + urllib.parse.quote(f"valor {marca}"), token)
    texto = rel.decode("utf-8-sig")
    checar("o relatório dos bens traz a vida útil e o valor atual",
           "Vida útil (anos)" in texto and "Valor atual" in texto and "Data da baixa" in texto,
           texto[:300])
    d, recusa = patrimonio_planilha._converter({"vida_util_anos": "5"}, {}, {}, ({}, {}))
    checar("a importação lê a vida útil", recusa is None and d.get("vida_util_anos") == 5,
           (d, recusa))
    d, recusa = patrimonio_planilha._converter({"vida_util_anos": "70"}, {}, {}, ({}, {}))
    checar("e recusa a fora de 1 a 50", bool(recusa), (d, recusa))
    checar("o cabeçalho da planilha exportada é reconhecido",
           patrimonio_planilha.COLUNAS.get(patrimonio_planilha._chave("Vida útil (anos)"))
           == "vida_util_anos")

    print("6. permissões")
    tk = garantir_cozinha(chamar, token)
    st, _ = chamar("GET", "/patrimonio/valor", token=tk)
    checar("cozinha (patrimonio.ver) vê o valor", st == 200, st)
finally:
    with get_cursor() as cur:
        cur.execute("DELETE FROM bens WHERE descricao LIKE %s", (f"%valor {marca}",))
    for i in setores:
        chamar("DELETE", f"/setores/{i}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
