"""Painel do estoque, aba "Entradas por nota" (pedido do dono, 26/11/2026).

O que este arquivo cobra, numa janela de 2033 só dele:

1. os itens das notas do período, com nota, fornecedor, situação e quem recebeu
2. os totais por situação: a conciliar, conciliada, recebida, lançada
3. fora: nota cancelada, nota não encontrada no Omie, item fora do estoque, nota fora do período
4. a quantidade é a de estoque (convertida) quando há produto; senão, a da nota
5. o custo é valor − desconto + frete e outros rateados
6. filtro de situação e busca (produto, nota, quem recebeu)
7. o relatório "entradas-por-nota" responde e está no catálogo

    python tests/smoke_painel_entradas.py      (API de pé na 9200)
"""

import atexit
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from database import get_cursor  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ADMIN = ("admin@botane.com.br", "botane123")
UNIDADE = 1
DE, ATE = "2033-04-01", "2033-04-30"
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("X-Unidade", str(UNIDADE))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = None
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
        dados = json.dumps(corpo, default=str).encode()
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 1000)[-6:]
notas: list[int] = []


def _limpar():
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM notas_entrada WHERE id = ANY(%s)", (notas,))
    except Exception as e:  # noqa: BLE001
        print("limpeza falhou:", e)


atexit.register(_limpar)

print("0. preparo")
with get_cursor() as cur:
    # Sobras de uma rodada interrompida na mesma janela.
    cur.execute("""DELETE FROM notas_entrada WHERE id_unidade = %s AND numero LIKE 'PE%%'
                     AND data_entrada BETWEEN %s AND %s""", (UNIDADE, DE, ATE))
    cur.execute("""SELECT id, codigo, nome, um_estoque FROM produtos
                    WHERE ativo AND controla_estoque AND um_estoque IS NOT NULL
                    ORDER BY id LIMIT 2""")
    p1, p2 = [dict(x) for x in cur.fetchall()]

    def nota(sufixo, status, dia, recebido=None):
        cur.execute(
            """INSERT INTO notas_entrada (id_unidade, numero, nome_emitente, data_emissao,
                                          data_entrada, status, origem, recebido_por, recebido_em)
               VALUES (%s, %s, %s, %s, %s, %s, 'OMIE', %s,
                       CASE WHEN %s::text IS NULL THEN NULL ELSE now() END) RETURNING id""",
            (UNIDADE, f"PE{sufixo}{marca}", f"Fornecedor PE {marca}", dia, dia, status,
             recebido, recebido))
        i = cur.fetchone()["id"]
        notas.append(i)
        return i

    def item(id_nota, seq, produto, qtd, conv, valor, desc=0, frete=0, ignorado=False,
             descricao="ITEM PE"):
        cur.execute(
            """INSERT INTO nota_itens (id_nota, seq, descricao_fornecedor, quantidade, um_nota,
                                       valor_unitario, valor_total, valor_desconto,
                                       valor_frete_rateado, id_produto, quantidade_convertida,
                                       ignorado)
               VALUES (%s, %s, %s, %s, 'CX', %s, %s, %s, %s, %s, %s, %s)""",
            (id_nota, seq, descricao, qtd, valor / qtd, valor, desc, frete,
             produto["id"] if produto else None, conv, ignorado))

    lanc = nota("L", "LANCADA", "2033-04-05")
    item(lanc, 1, p1, 2, 24, 100, desc=10, frete=5)            # custo 95, 24 un. de estoque
    item(lanc, 2, p2, 1, 6, 30, ignorado=True)                 # fora do estoque: não entra
    rec = nota("R", "RECEBIDA", "2033-04-10", recebido="Joana Recebe")
    item(rec, 1, p1, 1, 12, 50)
    conc = nota("C", "CONCILIADA", "2033-04-12")
    item(conc, 1, p2, 3, 3, 60)
    imp = nota("I", "IMPORTADA", "2033-04-15")
    item(imp, 1, None, 4, None, 40, descricao=f"COISA NOVA {marca}")
    canc = nota("X", "CANCELADA", "2033-04-16")
    item(canc, 1, p1, 1, 12, 999)
    nenc = nota("N", "NAO_ENCONTRADA", "2033-04-17")
    item(nenc, 1, p1, 1, 12, 999)
    fora = nota("F", "LANCADA", "2033-05-02")
    item(fora, 1, p1, 1, 12, 999)
checar("há dois produtos para o teste", bool(p1 and p2))


def painel(extra=""):
    return chamar("GET", f"/estoque/painel/entradas?inicio={DE}&fim={ATE}&busca=PE%20{marca}{extra}",
                  token=token)


print("1. os itens")
s, d = painel()
checar("responde", s == 200, (s, str(d)[:200]))
itens = d.get("itens", []) if s == 200 else []
checar("quatro itens: o ignorado, a cancelada, a não encontrada e a de maio ficam fora",
       len(itens) == 4, [(i["nota"], i["situacao"]) for i in itens])
por_nota = {i["id_nota"]: i for i in itens}
checar("cada item traz a nota, o fornecedor e a situação",
       por_nota.get(lanc, {}).get("nota") == f"PEL{marca}"
       and por_nota[lanc]["fornecedor"] == f"Fornecedor PE {marca}"
       and por_nota[lanc]["situacao"] == "LANCADA", por_nota.get(lanc))
checar("a recebida traz quem recebeu", por_nota.get(rec, {}).get("recebido_por") == "Joana Recebe",
       por_nota.get(rec))
checar("quantidade na unidade de estoque quando há produto (24 e não 2 CX)",
       por_nota[lanc]["quantidade"] == 24 and por_nota[lanc]["um"] == p1["um_estoque"], por_nota[lanc])
checar("sem produto, a quantidade e a unidade da nota",
       por_nota.get(imp, {}).get("quantidade") == 4 and por_nota[imp]["um"] == "CX"
       and por_nota[imp]["produto"] is None, por_nota.get(imp))
checar("custo = valor − desconto + frete (100 − 10 + 5 = 95)", por_nota[lanc]["custo"] == 95,
       por_nota[lanc]["custo"])

print("2. os totais por situação")
sit = {x["situacao"]: x for x in d.get("por_situacao", [])}
checar("as quatro situações, na ordem", list(sit) == ["IMPORTADA", "CONCILIADA", "RECEBIDA", "LANCADA"],
       list(sit))
checar("um item em cada", all(sit[k]["itens"] == 1 for k in sit), sit)
checar("o valor da lançada é o custo dela", sit["LANCADA"]["valor"] == 95, sit["LANCADA"])
checar("totais: 4 itens, 4 notas, 2 produtos, R$ 245",
       d["totais"] == {"itens": 4, "notas": 4, "produtos": 2, "valor": 245.0}, d["totais"])

print("3. filtro e busca")
s, d2 = painel("&situacao=RECEBIDA")
checar("só as recebidas", s == 200 and [i["id_nota"] for i in d2["itens"]] == [rec], d2.get("itens"))
checar("os totais por situação continuam os do período", s == 200
       and sum(x["itens"] for x in d2["por_situacao"]) == 4, d2.get("por_situacao"))
s, d3 = painel("&situacao=CONCILIADA&situacao=LANCADA")
checar("duas situações juntas", s == 200 and {i["id_nota"] for i in d3["itens"]} == {conc, lanc},
       d3.get("itens"))
s, d4 = chamar("GET", f"/estoque/painel/entradas?inicio={DE}&fim={ATE}&busca=Joana%20Recebe",
               token=token)
checar("busca por quem recebeu", s == 200 and any(i["id_nota"] == rec for i in d4["itens"]), s)
s, d5 = chamar("GET", f"/estoque/painel/entradas?inicio={DE}&fim={ATE}&busca=PEC{marca}",
               token=token)
checar("busca pelo número da nota", s == 200 and [i["id_nota"] for i in d5["itens"]] == [conc], s)
s, _ = chamar("GET", "/estoque/painel/entradas?inicio=2033-04-30&fim=2033-04-01", token=token)
checar("fim antes do início: 400", s == 400, s)

print("4. o relatório")
s, dd = chamar("GET", f"/exportar/entradas-por-nota/dados?inicio={DE}&fim={ATE}"
                      f"&busca_entrada=PE%20{marca}", token=token)
texto = json.dumps(dd, ensure_ascii=False, default=str)
checar("responde com as notas, a situação e quem recebeu",
       s == 200 and f"PEL{marca}" in texto and "Joana Recebe" in texto and "recebida" in texto
       and f"PEX{marca}" not in texto, (s, texto[:300]))
s, cat = chamar("GET", "/exportar/catalogo", token=token)
checar("está no catálogo", "entradas-por-nota" in json.dumps(cat, ensure_ascii=False), str(cat)[:200])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
