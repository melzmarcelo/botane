"""Como cada venda foi paga — as finalizadoras do PDV (migração 160).

O que este arquivo cobra:

1. a importação grava os pagamentos, e o detalhe da venda os mostra, com o troco à parte
2. **reimportar o mesmo documento troca os pagamentos, não duplica** (é o que completa o
   histórico sem criar venda)
3. o painel de vendas soma por forma, com o DINHEIRO LÍQUIDO (recebido − troco), conta o que
   não tem forma em "não informado" e deixa a venda cancelada de fora
4. com recorte de produto não há quadro de pagamento (o pagamento é do cupom inteiro)
5. a validação recusa grupo inventado e valor negativo
6. o mapeador lê o `formaPgtos` real: troco pela forma -1, PIX WEB no grupo PIX, classificação
   desconhecida em OUTRO
7. `completar` relê um dia e preenche a venda do PDV que já existia, sem criar venda
8. o relatório "Vendas por forma de pagamento" fecha com a receita do dia

⚠️ **A suíte mede DIFERENÇAS.** Hoje tem venda real e de outras suítes; ela compara o painel
antes e depois das vendas dela, e cancela as suas no fim.

    python tests/smoke_venda_pagamentos.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Unidade", "1")
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
            return e.code, {"detail": bruto.decode(errors="replace")}


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
marca = str(time.time_ns() // 1000)[-8:]
hoje = date.today().isoformat()
criadas: list[int] = []


def _limpar():
    for i in criadas:
        try:
            chamar("DELETE", f"/vendas/{i}", token=token)
        except Exception:
            pass


atexit.register(_limpar)


def importar(documento, total, pagamentos, origem="TESTE_PAGAMENTO", cancelada=False):
    return chamar("POST", "/vendas/importar", {"vendas": [{
        "data": hoje, "hora": "12:00:00", "documento": documento, "origem": origem,
        "cancelada": cancelada, "pagamentos": pagamentos,
        "itens": [{"descricao": f"Item pagamento {marca}", "quantidade": 1,
                   "valor_unitario": total}]}]}, token=token)


def id_da_venda(documento):
    _s, l = chamar("GET", f"/vendas?busca={documento}&limite=10", token=token)
    itens = l["itens"] if isinstance(l, dict) and "itens" in l else (l or [])
    return next((v["id"] for v in itens if v.get("documento") == documento), None)


def quadro():
    _s, p = chamar("GET", f"/vendas/painel?inicio={hoje}&fim={hoje}", token=token)
    q = (p or {}).get("por_pagamento") or {}
    por = {l["grupo"]: l["valor"] for l in q.get("linhas", [])}
    return por, q


print("1. importar com pagamentos")
antes, q_antes = quadro()
doc_cartao = f"PG{marca}A"
st, r = importar(doc_cartao, 40, [{"grupo": "CREDITO", "nome_pdv": "CREDITO", "valor": 30},
                                  {"grupo": "PIX", "nome_pdv": "PIX WEB", "valor": 10}])
checar("a venda entra", st in (200, 201) and r.get("importadas") == 1, (st, r))
id_cartao = id_da_venda(doc_cartao)
criadas.append(id_cartao)
_s, det = chamar("GET", f"/vendas/{id_cartao}", token=token)
formas = {p["grupo"]: p["valor"] for p in det.get("pagamentos", [])}
checar("o detalhe mostra crédito 30 e Pix 10",
       igual(formas.get("CREDITO"), 30) and igual(formas.get("PIX"), 10), det.get("pagamentos"))
checar("com o rótulo da casa e o nome do PDV",
       any(p["rotulo"] == "Pix" and p["nome_pdv"] == "PIX WEB" for p in det["pagamentos"]),
       det["pagamentos"])

doc_dinheiro = f"PG{marca}B"
st, r = importar(doc_dinheiro, 40, [{"grupo": "DINHEIRO", "valor": 50},
                                    {"grupo": "TROCO", "nome_pdv": "TROCO", "valor": 10}])
id_dinheiro = id_da_venda(doc_dinheiro)
criadas.append(id_dinheiro)
_s, det = chamar("GET", f"/vendas/{id_dinheiro}", token=token)
checar("o troco vem à parte, fora da lista de formas",
       igual(det.get("troco"), 10) and [p["grupo"] for p in det["pagamentos"]] == ["DINHEIRO"],
       det.get("pagamentos"))

print("2. reimportar troca, não duplica")
st, r = importar(doc_cartao, 40, [{"grupo": "DEBITO", "valor": 40}])
checar("o documento repetido não vira venda nova", r.get("repetidas") == 1 and r.get("importadas") == 0, r)
_s, det = chamar("GET", f"/vendas/{id_cartao}", token=token)
checar("e os pagamentos dele foram trocados (débito 40)",
       [(p["grupo"], float(p["valor"])) for p in det["pagamentos"]] == [("DEBITO", 40.0)],
       det["pagamentos"])
importar(doc_cartao, 40, [{"grupo": "DEBITO", "valor": 40}])
_s, det = chamar("GET", f"/vendas/{id_cartao}", token=token)
checar("reimportar de novo não dobra", len(det["pagamentos"]) == 1, det["pagamentos"])

print("3. o painel por forma")
doc_sem = f"PG{marca}C"
importar(doc_sem, 25, [])
criadas.append(id_da_venda(doc_sem))
doc_canc = f"PG{marca}D"
importar(doc_canc, 99, [{"grupo": "CREDITO", "valor": 99}], cancelada=True)
criadas.append(id_da_venda(doc_canc))
depois, q = quadro()


def delta(g):
    return float(depois.get(g, 0)) - float(antes.get(g, 0))


checar("débito andou 40", igual(delta("DEBITO"), 40), (antes, depois))
checar("dinheiro andou 40 (50 recebidos − 10 de troco)", igual(delta("DINHEIRO"), 40), (antes, depois))
checar("a venda cancelada não somou no crédito", igual(delta("CREDITO"), 0), (antes, depois))
checar("o troco do dia andou 10", igual(q["troco"] - q_antes.get("troco", 0), 10), q)
checar("a venda sem forma conta em não informado",
       q["sem_pagamento"]["cupons"] - q_antes.get("sem_pagamento", {}).get("cupons", 0) == 1
       and igual(q["sem_pagamento"]["valor"] - q_antes.get("sem_pagamento", {}).get("valor", 0), 25), q)
# ⚠️ Pela DIFERENÇA: o dia de hoje tem cupom real do PDV com acréscimo (taxa de entrega ou de
# serviço) pago nas formas e fora da receita dos itens — o dia inteiro não fecha no centavo, e não
# é deste teste. As vendas daqui não podem mexer na diferença.
checar("as formas + não informado fecham com a receita (as vendas do teste não mexem na diferença)",
       abs(q["diferenca"] - q_antes.get("diferenca", 0)) < 0.05, (q_antes.get("diferenca"), q["diferenca"]))
_s, p = chamar("GET", f"/vendas/painel?inicio={hoje}&fim={hoje}&produtos=1", token=token)
checar("com recorte de produto não há quadro de pagamento", p.get("por_pagamento") is None,
       p.get("por_pagamento"))

print("4. validação")
st, _ = importar(f"PG{marca}E", 10, [{"grupo": "CHEQUE", "valor": 10}])
checar("grupo que não existe: 422", st == 422, st)
st, _ = importar(f"PG{marca}F", 10, [{"grupo": "PIX", "valor": -1}])
checar("valor negativo: 422", st == 422, st)

print("5. o mapeador e o completar")
from services.pdv import mapeadores  # noqa: E402
from services import venda_pagamentos  # noqa: E402
from database import get_cursor  # noqa: E402

cupom_real = {
    "venda_id": f"PG{marca}G", "dtmovimento": f"{hoje}T00:00:00", "valortotal": 163.5,
    "itens": [], "formaPgtos": [
        {"nome": "TROCO", "codformarecebimentopdv": -1, "codClassificacao": 1, "valortotal": 36.5},
        {"nome": "DINHEIRO", "codformarecebimentopdv": 1, "codClassificacao": 1, "valortotal": 200},
        {"nome": "PIX WEB", "codformarecebimentopdv": 108159, "codClassificacao": 22, "valortotal": 5},
        {"nome": "IFOOD", "codClassificacao": 99, "valortotal": 3},
        {"nome": "ZERADO", "codClassificacao": 3, "valortotal": 0}]}
pg = mapeadores.cupom(cupom_real)["pagamentos"]
checar("troco pela forma -1, mesmo com a classificação do dinheiro", pg[0]["grupo"] == "TROCO", pg)
checar("PIX WEB cai no grupo PIX, com o nome preservado",
       pg[2]["grupo"] == "PIX" and pg[2]["nome_pdv"] == "PIX WEB", pg)
checar("classificação desconhecida vira OUTRO", pg[3]["grupo"] == "OUTRO", pg)
checar("linha de valor zero não entra", len(pg) == 4, pg)

doc_pdv = f"PG{marca}G"
st, r = importar(doc_pdv, 163.5, [], origem="PDV_LEGAL")
id_pdv = id_da_venda(doc_pdv)
criadas.append(id_pdv)


class PdvDeMentira:
    def get(self, caminho):
        return [cupom_real]


with get_cursor() as cur:
    rc = venda_pagamentos.completar(cur, PdvDeMentira(), mapeadores, 1, "1",
                                    date.today(), date.today())
checar("completar acha a venda pelo documento e preenche", rc["completadas"] == 1, rc)
_s, det = chamar("GET", f"/vendas/{id_pdv}", token=token)
checar("a venda do PDV agora tem dinheiro, Pix e outro, e o troco",
       sorted(p["grupo"] for p in det["pagamentos"]) == ["DINHEIRO", "OUTRO", "PIX"]
       and igual(det["troco"], 36.5), det["pagamentos"])
_s, lista = chamar("GET", f"/vendas?busca={doc_pdv}&limite=10", token=token)
itens = lista["itens"] if isinstance(lista, dict) and "itens" in lista else (lista or [])
checar("e nenhuma venda nova foi criada", sum(1 for v in itens if v.get("documento") == doc_pdv) == 1,
       itens)

print("6. o relatório")
st, rel = chamar("GET", f"/exportar/vendas-pagamentos/dados?inicio={hoje}&fim={hoje}", token=token)
checar("o relatório responde", st == 200, (st, rel))
texto = json.dumps(rel, ensure_ascii=False, default=str)
checar("com as colunas das formas e o troco",
       all(c in texto for c in ("Crédito", "Débito", "Dinheiro (líquido)", "Troco", "Não informado")),
       texto[:300])

# ⚠️ Os anexos saem no PDF e na planilha; a rota `/dados` (prévia da tela) traz só o quadro da
# frente. Por isso a montagem do relatório é chamada direto.
from services import exportacao_catalogo as ex  # noqa: E402

with get_cursor() as cur:
    s1 = ex._vendas(cur, 1, {"inicio": date.today(), "fim": date.today()})
    s2 = ex._vendas(cur, 1, {"inicio": date.today(), "fim": date.today(), "produtos": [1]})
    s3 = ex._vendas(cur, 1, {"inicio": date.fromordinal(date.today().toordinal() - 6),
                             "fim": date.today()})
titulos = [a[2] for a in s1.anexos]
formas = next((a[0] for a in s1.anexos if a[2] == "Por forma de pagamento"), [])
checar("o relatório do painel (Estudo de vendas) traz o quadro Por forma de pagamento",
       "Por forma de pagamento" in titulos and any(f["forma"] == "Débito" for f in formas), titulos)
checar("com o troco dito à parte", any(str(f["forma"]).startswith("Troco") for f in formas), formas)
checar("com recorte de produto, não traz (o pagamento é do cupom inteiro)",
       "Por forma de pagamento" not in [a[2] for a in s2.anexos])
checar("em mais de um dia, vem também o dia a dia das formas",
       "Formas de pagamento dia a dia" in [a[2] for a in s3.anexos], [a[2] for a in s3.anexos])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
