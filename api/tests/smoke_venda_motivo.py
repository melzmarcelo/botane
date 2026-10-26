"""O MOTIVO de um documento lançado à mão que não é venda (migração 134).

🔑 **Pedido do dono (26/10/2026):** *"ao lançar um documento à mão, gostaria de ter um
campo Motivo, e quando selecionado algum, ter um campo Observação. Motivos: Perda, Prêmio,
Brinde/Aniversário, Outros … basicamente seria um consumo interno, saindo pelo custo."*
E a caixa "Considerar consumo interno" (095) virou o motivo CONSUMO_INTERNO.

O que esta suíte afirma:
1. as recusas: perda sem o motivo da perda, outros sem observação, consumo interno sem
   pessoa (422), e motivo de perda que não existe
2. PERDA: sai como `SAIDA_PERDA` com o motivo; receita e teórico não mudam; o custo entra
   em PERDAS e no CMV real; lista e detalhe dizem o motivo; não vira "vendido e não baixado"
3. BRINDE sem pessoa e OUTROS com observação: consumo interno, e a apuração separa o
   consumo interno por motivo
4. quem manda só `consumo_interno=true` (tela antiga, conector) ganha o motivo CONSUMO_INTERNO
5. a perda segue perda no "acrescentar itens" e na troca de data (que relança o razão)
6. cancelar devolve e tira da linha de perdas

Mede pelo DELTA da apuração do dia (a base tem dado de outras suítes).

    python tests/smoke_venda_motivo.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def perto(a, b, tol=0.005):
    return a is not None and abs(float(a) - float(b)) <= tol


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today()
local = garantir_local(chamar, token)
documentos: list[str] = []


def apuracao():
    _st, a = chamar("GET", f"/cmv/apuracao?inicio={hoje}&fim={hoje}", token=token)
    return a or {}


def lancar(doc, **cabecalho):
    documentos.append(doc)
    corpo = {"data": str(hoje), "documento": doc, "origem": "MANUAL",
             "itens": [{"id_produto": produto, "quantidade": cabecalho.pop("qtd", 1),
                        "valor_unitario": 10}], **cabecalho}
    return chamar("POST", "/vendas/importar", {"vendas": [corpo]}, token=token)


def venda_e_movimentos(doc):
    with get_cursor() as cur:
        cur.execute("""SELECT id, consumo_interno, motivo, motivo_observacao, id_motivo_perda
                         FROM vendas WHERE documento = %s""", (doc,))
        v = dict(cur.fetchone() or {})
        cur.execute("""SELECT tipo, quantidade, custo_total, id_motivo_perda, observacao
                         FROM estoque_movimentos
                        WHERE origem_tipo = 'VENDA' AND origem_id = %s ORDER BY id""",
                    (v.get("id"),))
        return v, [dict(x) for x in cur.fetchall()]


def parte(a, motivo):
    return float(next((p["valor"] for p in a.get("consumo_por_motivo") or []
                       if p["motivo"] == motivo), 0))


print("0. o cenário: um produto a R$ 4,00 de custo e R$ 10,00 de venda, e uma pessoa")
st, prod = chamar("POST", "/produtos", {
    "nome": f"MOTIVO VENDA {marca}", "tipo": "REVENDA", "um_estoque": "UN",
    "preco_venda": 10, "status": "ATIVO"}, token=token)
produto = (prod or {}).get("id")
chamar("PUT", f"/produtos/{produto}", {"id_local_padrao": local["id"]}, token=token)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 20, "custo_unitario": 4, "id_local": local["id"],
    "documento": f"NF-MV-{marca}"}, token=token)
checar("20 unidades a R$ 4,00 em estoque", st == 201, r)
st, pes = chamar("POST", "/fornecedores", {"nome": f"CLIENTE MOTIVO {marca}",
                                            "fornecedor": False}, token=token)
pessoa = (pes or {}).get("id")
_st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
quebra = next((m for m in motivos or [] if m["nome"] == "Quebra"), (motivos or [{}])[0])
checar("há motivo de perda para escolher", bool(quebra.get("id")), motivos)
antes = apuracao()

print("\n1. as recusas")
st, r = lancar(f"P0-{marca}", motivo="PERDA")
checar("perda sem o motivo da perda é recusada (422)",
       st == 422 and "motivo da perda" in str(r.get("detail", "")), (st, r))
st, r = lancar(f"PX-{marca}", motivo="PERDA", id_motivo_perda=999999)
checar("e com um motivo de perda que não existe também", st == 422, (st, r))
st, r = lancar(f"O0-{marca}", motivo="OUTROS", motivo_observacao="   ")
checar("outros sem observação é recusado (422)",
       st == 422 and "observação" in str(r.get("detail", "")), (st, r))
st, r = lancar(f"C0-{marca}", motivo="CONSUMO_INTERNO")
checar("consumo interno sem pessoa continua recusado (422)",
       st == 422 and "pessoa" in str(r.get("detail", "")), (st, r))

print("\n2. PERDA")
doc_perda = f"PERDA-{marca}"
st, r = lancar(doc_perda, motivo="PERDA", id_motivo_perda=quebra.get("id"),
               motivo_observacao="caiu no chão", qtd=2)
checar("entra", st == 201 and r.get("importadas") == 1, (st, r))
v, movs = venda_e_movimentos(doc_perda)
checar("gravada fora da receita, com o motivo e o motivo da perda",
       v.get("consumo_interno") is True and v.get("motivo") == "PERDA"
       and v.get("id_motivo_perda") == quebra.get("id")
       and v.get("motivo_observacao") == "caiu no chão", v)
checar("o estoque sai como PERDA, com o motivo da perda",
       len(movs) == 1 and movs[0]["tipo"] == "SAIDA_PERDA"
       and movs[0]["id_motivo_perda"] == quebra.get("id")
       and perto(abs(movs[0]["quantidade"]), 2), movs)
depois = apuracao()
d = {k: float(depois.get(k) or 0) - float(antes.get(k) or 0)
     for k in ("receita", "cmv_teorico", "perdas", "consumo_interno", "cmv_real")}
checar("receita e CMV teórico não mudam", perto(d["receita"], 0) and perto(d["cmv_teorico"], 0), d)
checar("o custo (2 × 4,00) entra em PERDAS e no CMV real, não no consumo interno",
       perto(d["perdas"], 8) and perto(d["cmv_real"], 8) and perto(d["consumo_interno"], 0), d)
st, lista = chamar("GET", f"/vendas?busca={doc_perda}", token=token)
checar("a lista diz o motivo", st == 200 and lista and lista[0].get("motivo") == "PERDA", lista)
st, det = chamar("GET", f"/vendas/{v.get('id')}", token=token)
checar("e o detalhe traz o motivo, o da perda e a observação",
       det.get("motivo") == "PERDA" and det.get("motivo_perda") == quebra.get("nome")
       and det.get("motivo_observacao") == "caiu no chão", det)
st, sb = chamar("GET", "/vendas/sem-baixa/previa", token=token)
pendente = [x for x in (sb or {}).get("itens", []) if x.get("id_produto") == produto]
checar("não aparece como 'vendido e não baixado' (a baixa foi a perda)",
       st == 200 and not pendente, pendente)

print("\n3. BRINDE sem pessoa e OUTROS com observação: consumo interno, por motivo")
antes3 = apuracao()
st, r = lancar(f"BRINDE-{marca}", motivo="BRINDE", motivo_observacao="aniversário da Ana")
checar("brinde entra SEM pessoa", st == 201 and r.get("importadas") == 1, (st, r))
v, movs = venda_e_movimentos(f"BRINDE-{marca}")
checar("e sai como consumo interno, com o motivo na observação do movimento",
       len(movs) == 1 and movs[0]["tipo"] == "SAIDA_CONSUMO_INTERNO"
       and "Brinde" in (movs[0]["observacao"] or "")
       and "aniversário da Ana" in (movs[0]["observacao"] or ""), movs)
st, r = lancar(f"OUTROS-{marca}", motivo="OUTROS", motivo_observacao="foto do cardápio",
               qtd=3)
checar("outros com observação entra", st == 201 and r.get("importadas") == 1, (st, r))
depois3 = apuracao()
checar("o consumo interno cresce 4 × 4,00",
       perto(float(depois3["consumo_interno"]) - float(antes3["consumo_interno"]), 16),
       (depois3.get("consumo_interno"), antes3.get("consumo_interno")))
checar("e a apuração separa: brinde 4,00 e outros 12,00",
       perto(parte(depois3, "BRINDE") - parte(antes3, "BRINDE"), 4)
       and perto(parte(depois3, "OUTROS") - parte(antes3, "OUTROS"), 12),
       depois3.get("consumo_por_motivo"))
checar("as partes fecham com a linha do consumo interno",
       perto(sum(float(p["valor"]) for p in depois3.get("consumo_por_motivo") or []),
             depois3["consumo_interno"], 0.02),
       (depois3.get("consumo_por_motivo"), depois3.get("consumo_interno")))

print("\n4. a caixa antiga continua valendo")
st, r = lancar(f"CI-{marca}", id_pessoa=pessoa, consumo_interno=True)
v, movs = venda_e_movimentos(f"CI-{marca}")
checar("consumo_interno=true sem motivo vira o motivo CONSUMO_INTERNO",
       st == 201 and v.get("motivo") == "CONSUMO_INTERNO"
       and movs and movs[0]["tipo"] == "SAIDA_CONSUMO_INTERNO", (st, r, v, movs))

print("\n5. a perda segue perda depois de lançada")
v, _ = venda_e_movimentos(doc_perda)
st, r = chamar("POST", f"/vendas/{v.get('id')}/itens", {"itens": [
    {"id_produto": produto, "quantidade": 1, "valor_unitario": 10}]}, token=token)
_v, movs = venda_e_movimentos(doc_perda)
checar("o item acrescentado sai como perda, com o motivo",
       st == 201 and len(movs) == 2 and all(m["tipo"] == "SAIDA_PERDA"
                                            and m["id_motivo_perda"] == quebra.get("id")
                                            for m in movs), (st, r, movs))
ontem = hoje - timedelta(days=1)
st, r = chamar("PUT", f"/vendas/{v.get('id')}", {"data": str(ontem)}, token=token)
_v, movs = venda_e_movimentos(doc_perda)
vivos = [m for m in movs if m["tipo"] == "SAIDA_PERDA"]
checar("trocar a data relança a perda com o motivo (não é recusada)",
       st == 200 and len(vivos) == 4 and all(m["id_motivo_perda"] == quebra.get("id")
                                             for m in vivos), (st, r, movs))

print("\n6. cancelar devolve e tira da linha de perdas")
antes6 = apuracao()
st, r = chamar("DELETE", f"/vendas/{v.get('id')}", token=token)
checar("o cancelamento estorna", st == 200 and (r or {}).get("estornados", 0) >= 1, (st, r))
st, sb = chamar("GET", "/vendas/sem-baixa/previa", token=token)
pendente = [x for x in (sb or {}).get("itens", []) if x.get("id_produto") == produto]
checar("e nada fica pendente de baixa", st == 200 and not pendente, pendente)
_st, saldo = chamar("GET", f"/estoque/saldos?id_produto={produto}", token=token)
qtd = sum(float(s.get("quantidade") or 0) for s in (saldo or [])
          if s.get("id_produto") == produto) if isinstance(saldo, list) else None
checar("o saldo volta: 20 − 1 brinde − 3 outros − 1 consumo interno = 15",
       qtd is not None and perto(qtd, 15), saldo)

print("\n7. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM venda_itens WHERE id_venda IN "
                "(SELECT id FROM vendas WHERE documento = ANY(%s))", (documentos,))
    cur.execute("DELETE FROM vendas WHERE documento = ANY(%s)", (documentos,))
chamar("DELETE", f"/produtos/{produto}", token=token)
if pessoa:
    chamar("DELETE", f"/fornecedores/{pessoa}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
