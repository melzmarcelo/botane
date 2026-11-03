"""O documento com motivo Prêmio liga (ou entrega) o prêmio da fidelidade (migração 147).

🔑 **Pedido do dono (03/11/2026):** *"vincular o documento com o resgate de prêmios"* —
código obrigatório. O almoço do prêmio vai num documento do PDV que não é importado e é
lançado à mão depois: quase sempre o balcão já entregou, e o documento só liga.
Estudo: docs/fidelidade-resgate-estudo.md.

O que esta suíte afirma:
1. motivo Prêmio sem código é recusado (422); código que não existe, 404
2. prêmio JÁ entregue no balcão: o documento só liga (não entrega de novo); ele sai da
   lista "entregue sem documento", e o grid de Prêmios mostra o documento e o custo
3. o mesmo prêmio num segundo documento é recusado (409), dizendo qual
4. prêmio ainda disponível: o documento ENTREGA, na data dele, e tira o check-in do dia
5. documento retroativo confere as regras NA DATA DELE (dia de consumo, vencimento)
6. cancelar o documento que entregou devolve o prêmio; o do balcão continua entregue e
   volta para "sem documento" — e pode ir para um documento novo
7. o painel conta o que falta lançar e o custo do mês; o detalhe da venda mostra o prêmio
8. o banco garante: id_premio só com motivo PREMIO, e um documento vivo por prêmio

    python tests/smoke_premio_no_documento.py        (API de pé na 9200)
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
ontem = hoje - timedelta(days=1)
local = garantir_local(chamar, token)
documentos: list[str] = []
FONE = f"4799{marca}9"
LETRAS = "ABCDEFGHJKMNPQRSTUVWXYZ"
# Códigos de teste: 6 letras, sem colidir com os de verdade (que não usam Z no começo + marca).
codigos = ["Z" + "".join(LETRAS[int(c)] for c in marca[:4]) + s for s in "ABCDE"]
TODOS_OS_DIAS = [1, 2, 3, 4, 5, 6, 7]


def lancar(doc, dia=None, **cabecalho):
    documentos.append(doc)
    corpo = {"data": str(dia or hoje), "documento": doc, "origem": "MANUAL",
             "itens": [{"id_produto": produto, "quantidade": 1, "valor_unitario": 30}],
             **cabecalho}
    return chamar("POST", "/vendas/importar", {"vendas": [corpo]}, token=token)


def premio(codigo):
    with get_cursor() as cur:
        cur.execute("""SELECT id, usado_em, usado_por, id_unidade_uso, entregue_pelo_documento,
                              (usado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia_uso
                         FROM fidelidade_premios WHERE codigo = %s""", (codigo,))
        return dict(cur.fetchone() or {})


def id_venda(doc):
    with get_cursor() as cur:
        cur.execute("SELECT id, id_premio FROM vendas WHERE documento = %s", (doc,))
        return dict(cur.fetchone() or {})


def no_grid(codigo, status=None):
    q = f"/fidelidade/premios?busca={codigo}&limite=100" + (f"&status={status}" if status else "")
    _st, lista = chamar("GET", q, token=token)
    return next((x for x in lista or [] if x.get("codigo") == codigo), None)


print("0. o cenário: um prato a R$ 12,00 de custo, um cliente e cinco prêmios")
st, prod = chamar("POST", "/produtos", {
    "nome": f"ALMOCO PREMIO {marca}", "tipo": "REVENDA", "um_estoque": "UN",
    "preco_venda": 30, "status": "ATIVO"}, token=token)
produto = (prod or {}).get("id")
chamar("PUT", f"/produtos/{produto}", {"id_local_padrao": local["id"]}, token=token)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 10, "custo_unitario": 12, "id_local": local["id"],
    "documento": f"NF-PR-{marca}"}, token=token)
checar("10 pratos a R$ 12,00 em estoque", st == 201, r)
_st, resumo_antes = chamar("GET", "/fidelidade/painel/resumo", token=token)
with get_cursor() as cur:
    cur.execute("SELECT id FROM unidades ORDER BY id LIMIT 1")
    loja = cur.fetchone()["id"]
    cur.execute("INSERT INTO reserva_clientes (nome, telefone) VALUES (%s, %s) RETURNING id",
                (f"CLIENTE PREMIO {marca}", FONE))
    cliente = cur.fetchone()["id"]
    for i, cod in enumerate(codigos):
        # C (índice 2) só vale de domingo: serve à recusa por dia de consumo.
        dias = [7] if i == 2 else TODOS_OS_DIAS
        cur.execute(
            """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                               dias_consumo, vence_em, vale_de, emitido_em)
               VALUES (%s, %s, %s, 'Almoço cortesia', 10, %s, %s, %s, now() - interval '5 days')""",
            (cliente, loja, cod, dias, hoje + timedelta(days=20), hoje - timedelta(days=4)))
    # O check-in de hoje, aberto: a visita do prêmio não conta carimbo.
    cur.execute("""INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data)
                   VALUES (%s, %s, %s)""", (cliente, loja, hoje))
A, B, C, D, E = codigos

print("\n1. as recusas")
st, r = lancar(f"PR0-{marca}", motivo="PREMIO")
checar("motivo Prêmio sem código é recusado (422)",
       st == 422 and "código do prêmio" in str((r or {}).get("detail", "")), (st, r))
st, r = lancar(f"PR1-{marca}", motivo="PREMIO", codigo_premio="ZZZZZQ")
checar("código que não existe: 404, dizendo o código",
       st == 404 and "ZZZZZQ" in str((r or {}).get("detail", "")), (st, r))
st, r = lancar(f"PR2-{marca}", motivo="BRINDE", codigo_premio=A)
checar("o código num motivo que não é Prêmio é ignorado (o brinde entra sem prêmio)",
       st == 201 and id_venda(f"PR2-{marca}").get("id_premio") is None
       and not premio(A).get("usado_em"), (st, r))

print("\n2. prêmio já entregue no balcão: o documento só liga")
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": A}, token=token)
checar("o balcão entrega A, e a resposta lembra de lançar o documento",
       st == 200 and A in (r or {}).get("message", "") and "motivo Prêmio" in r["message"],
       (st, r))
checar("A aparece em 'entregue sem documento'", no_grid(A, "SEM_DOCUMENTO") is not None)
usado_antes = premio(A)["usado_em"]
st, r = lancar(f"PRA-{marca}", motivo="PREMIO", codigo_premio=A.lower())
checar("o documento entra (código em minúsculas também) e diz que ligou",
       st == 201 and r.get("importadas") == 1 and "ligado ao documento" in r["message"],
       (st, r))
p = premio(A)
checar("a entrega do balcão não muda (não entrega de novo, não vira 'do documento')",
       p["usado_em"] == usado_antes and p["entregue_pelo_documento"] is False, p)
checar("o documento guarda o prêmio", id_venda(f"PRA-{marca}").get("id_premio") == p["id"])
checar("e A sai de 'entregue sem documento'", no_grid(A, "SEM_DOCUMENTO") is None)
g = no_grid(A)
checar("o grid de Prêmios mostra o documento e o custo (R$ 12,00)",
       g and g.get("documento") == f"PRA-{marca}" and perto(g.get("custo_documento"), 12)
       and g.get("sem_documento") is False, g)

print("\n3. um prêmio, um documento")
st, r = lancar(f"PRA2-{marca}", motivo="PREMIO", codigo_premio=A)
checar("o mesmo prêmio num segundo documento é recusado (409), dizendo qual",
       st == 409 and f"PRA-{marca}" in str((r or {}).get("detail", "")), (st, r))

print("\n4. prêmio ainda disponível: o documento entrega")
# A entrega de A no balcão já tirou o check-in de hoje; o cliente leu o QR de novo.
with get_cursor() as cur:
    cur.execute("""INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data)
                   VALUES (%s, %s, %s)""", (cliente, loja, hoje))
st, r = lancar(f"PRB-{marca}", motivo="PREMIO", codigo_premio=B)
p = premio(B)
checar("o documento entrega B hoje, nesta loja, e diz isso",
       st == 201 and p.get("usado_em") and p["dia_uso"] == hoje
       and p["entregue_pelo_documento"] is True and p["id_unidade_uso"]
       and "entregue por este documento" in r["message"], (st, r, p))
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM fidelidade_checkins WHERE id_cliente = %s AND data = %s",
                (cliente, hoje))
    checins_hoje = cur.fetchone()["n"]
checar("e tira o check-in aberto de hoje (a visita do prêmio não conta carimbo)",
       checins_hoje == 0 and "check-in" in r["message"], (checins_hoje, r))

print("\n5. documento retroativo: as regras na data DELE")
st, r = lancar(f"PRC-{marca}", motivo="PREMIO", codigo_premio=C,
               dia=hoje if hoje.isoweekday() != 7 else ontem)
checar("C só vale de domingo: o documento de outro dia é recusado (409) e C não muda",
       st == 409 and "Dom" in str((r or {}).get("detail", ""))
       and not premio(C).get("usado_em"), (st, r))
st, r = lancar(f"PRD-{marca}", motivo="PREMIO", codigo_premio=D, dia=ontem)
p = premio(D)
checar("D lançado com a data de ontem: entregue ONTEM",
       st == 201 and p.get("dia_uso") == ontem and p["entregue_pelo_documento"] is True,
       (st, r, p))
with get_cursor() as cur:
    cur.execute("UPDATE fidelidade_premios SET vence_em = %s WHERE codigo = %s",
                (ontem - timedelta(days=1), E))
st, r = lancar(f"PRE-{marca}", motivo="PREMIO", codigo_premio=E, dia=ontem)
checar("E, vencido antes de ontem, é recusado num documento de ontem (409)",
       st == 409 and "venceu" in str((r or {}).get("detail", "")), (st, r))
with get_cursor() as cur:
    cur.execute("UPDATE fidelidade_premios SET vence_em = %s WHERE codigo = %s",
                (hoje + timedelta(days=20), E))
v = id_venda(f"PRD-{marca}")
st, r = chamar("PUT", f"/vendas/{v.get('id')}", {"data": str(hoje)}, token=token)
checar("trocar a data do documento leva a entrega junto",
       st == 200 and premio(D).get("dia_uso") == hoje, (st, r, premio(D)))

print("\n6. cancelar")
v = id_venda(f"PRB-{marca}")
st, r = chamar("DELETE", f"/vendas/{v.get('id')}", token=token)
p = premio(B)
checar("cancelar o documento que ENTREGOU devolve o prêmio ao cliente",
       st == 200 and r.get("premio_devolvido") is True and p.get("usado_em") is None
       and p["entregue_pelo_documento"] is False and "voltou" in r["message"], (st, r, p))
v = id_venda(f"PRA-{marca}")
st, r = chamar("DELETE", f"/vendas/{v.get('id')}", token=token)
p = premio(A)
checar("cancelar o documento de um prêmio do BALCÃO: continua entregue, sem documento",
       st == 200 and r.get("premio_devolvido") is False and p.get("usado_em")
       and no_grid(A, "SEM_DOCUMENTO") is not None, (st, r, p))
st, r = lancar(f"PRA3-{marca}", motivo="PREMIO", codigo_premio=A)
checar("e A pode ir para um documento novo (o cancelado não prende)",
       st == 201 and r.get("importadas") == 1, (st, r))

print("\n7. painel e detalhe")
_st, resumo = chamar("GET", "/fidelidade/painel/resumo", token=token)
checar("o painel traz o que falta lançar e o custo do mês",
       all(k in (resumo or {}) for k in ("entregues_sem_documento", "custo_no_mes",
                                         "documentos_no_mes")), resumo)
# Vivos agora: PRA3 (A) e PRD (D, hoje) — 2 documentos, 2 × 12,00.
checar("o custo do mês cresce 2 × 12,00 (os documentos vivos de prêmio)",
       perto(resumo["custo_no_mes"] - float(resumo_antes.get("custo_no_mes") or 0), 24)
       and resumo["documentos_no_mes"] - int(resumo_antes.get("documentos_no_mes") or 0) == 2,
       (resumo, resumo_antes))
v = id_venda(f"PRA3-{marca}")
_st, det = chamar("GET", f"/vendas/{v.get('id')}", token=token)
checar("o detalhe da venda mostra o código e o cliente do prêmio",
       det.get("premio_codigo") == A and det.get("premio_cliente") == f"CLIENTE PREMIO {marca}",
       det)

print("\n8. o banco garante")
with get_cursor() as cur:
    cur.execute("SAVEPOINT s")
    try:
        cur.execute("UPDATE vendas SET id_premio = %s WHERE documento = %s",
                    (premio(B)["id"], f"PR2-{marca}"))
        recusou = False
    except Exception:  # noqa: BLE001
        recusou = True
    cur.execute("ROLLBACK TO SAVEPOINT s")
    checar("id_premio num documento que não é Prêmio: o CHECK recusa", recusou)
    cur.execute("SAVEPOINT s2")
    try:
        cur.execute("""UPDATE vendas SET id_premio = %s, motivo = 'PREMIO', consumo_interno = true
                        WHERE documento = %s""", (premio(A)["id"], f"PR2-{marca}"))
        recusou = False
    except Exception:  # noqa: BLE001
        recusou = True
    cur.execute("ROLLBACK TO SAVEPOINT s2")
    checar("dois documentos vivos com o mesmo prêmio: o índice único recusa", recusou)

print("\n9. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM venda_itens WHERE id_venda IN "
                "(SELECT id FROM vendas WHERE documento = ANY(%s))", (documentos,))
    cur.execute("DELETE FROM vendas WHERE documento = ANY(%s)", (documentos,))
    cur.execute("DELETE FROM fidelidade_checkins WHERE id_cliente = %s", (cliente,))
    cur.execute("DELETE FROM fidelidade_premios WHERE id_cliente = %s", (cliente,))
    cur.execute("DELETE FROM reserva_clientes WHERE id = %s", (cliente,))
chamar("DELETE", f"/produtos/{produto}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
