"""A nota RECEBIDA (migração 168): a mercadoria chegou, falta o recebimento no Omie.

Pedido do dono (26/11/2026): com "Somente recebidas" desligado no Omie, a nota chega
conciliada; quem recebe marca como RECEBIDA com o nome de quem recebeu (obrigatório); outra
pessoa confere as recebidas, dá o recebimento no Omie, e a nota volta LANÇADA.

O que este arquivo cobra:

1. `pode_receber` no detalhe: só a conciliada do Omie, só com "Somente recebidas" desligado
2. as recusas: sem nome, importada, XML, "Somente recebidas" ligado, já recebida
3. marcar: status, nome (espaços normalizados), data e quem marcou ficam na nota
4. a lista: filtro RECEBIDA e o nome de quem recebeu; o "a lançar" a inclui
5. o recálculo NÃO a devolve a conciliada; com item pendente vira importada e volta recebida
6. entra no lote "lançar as conciliadas"; lançada, guarda quem recebeu; estornada, volta RECEBIDA
7. desfazer o recebimento: volta a conciliada e apaga o nome
8. o relatório de compras: a coluna "Recebido por" e a situação "recebida"

    python tests/smoke_nota_recebida.py      (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, ".")

from database import get_cursor  # noqa: E402
from services.omie import importador  # noqa: E402

import os  # noqa: E402
BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ADMIN = ("admin@botane.com.br", "botane123")
UNIDADE = 1
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
marca = str(time.time_ns() // 1000)[-7:]
hoje = date.today()
notas: list[int] = []
estado_omie: dict = {}


def _so_recebidas(valor: bool):
    with get_cursor() as cur:
        cur.execute("""UPDATE integracoes SET so_recebidas = %s
                        WHERE id_unidade = %s AND servico = 'OMIE'""", (valor, UNIDADE))


def _limpar():
    try:
        with get_cursor() as cur:
            if estado_omie.get("existia"):
                cur.execute("""UPDATE integracoes SET so_recebidas = %s
                                WHERE id_unidade = %s AND servico = 'OMIE'""",
                            (estado_omie["so_recebidas"], UNIDADE))
            elif estado_omie:
                cur.execute("DELETE FROM integracoes WHERE id_unidade = %s AND servico = 'OMIE'",
                            (UNIDADE,))
            for n in notas:
                cur.execute("""DELETE FROM notas_entrada n WHERE id = %s AND NOT EXISTS (
                                 SELECT 1 FROM estoque_movimentos m
                                  WHERE m.origem_tipo = 'NOTA' AND m.origem_id = n.id)""", (n,))
                # ⚠️ A lançada e estornada tem movimentos no razão (append-only) e fica —
                # CANCELADA, fora das filas: recebida, ela entrava no "a lançar" e o
                # roteiro do navegador contava uma nota a mais por rodada.
                cur.execute("""UPDATE notas_entrada SET status = 'CANCELADA'
                                WHERE id = %s AND status <> 'LANCADA'""", (n,))
            # Sobras de rodadas antigas (antes desta limpeza).
            cur.execute("""UPDATE notas_entrada SET status = 'CANCELADA'
                            WHERE numero LIKE 'RC_%%' AND nome_emitente LIKE 'Fornecedor recebida %%'
                              AND status IN ('IMPORTADA', 'CONCILIADA', 'RECEBIDA')""")
    except Exception as e:  # noqa: BLE001
        print("limpeza falhou:", e)


atexit.register(_limpar)

print("0. preparo")
with get_cursor() as cur:
    cur.execute("SELECT so_recebidas FROM integracoes WHERE id_unidade = %s AND servico = 'OMIE'",
                (UNIDADE,))
    linha = cur.fetchone()
    if linha:
        estado_omie.update(existia=True, so_recebidas=linha["so_recebidas"])
    else:
        estado_omie.update(existia=False)
        cur.execute("""INSERT INTO integracoes (id_unidade, servico, modo, so_recebidas)
                       VALUES (%s, 'OMIE', 'SIMULADO', false)""", (UNIDADE,))
    cur.execute("""UPDATE integracoes SET so_recebidas = false
                    WHERE id_unidade = %s AND servico = 'OMIE'""", (UNIDADE,))
    cur.execute("""SELECT id, um_estoque FROM produtos
                    WHERE ativo AND controla_estoque AND status = 'ATIVO'
                      AND um_estoque IS NOT NULL AND fundido_em IS NULL
                    ORDER BY id LIMIT 1""")
    produto = cur.fetchone()

    def nota(numero, origem, ligado=True):
        cur.execute(
            """INSERT INTO notas_entrada (id_unidade, numero, nome_emitente, data_emissao,
                                          data_entrada, status, origem, valor_total, valor_produtos)
               VALUES (%s, %s, %s, %s, %s, 'IMPORTADA', %s, 10, 10) RETURNING id""",
            (UNIDADE, numero, f"Fornecedor recebida {marca}", hoje, hoje, origem))
        i = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO nota_itens (id_nota, seq, descricao_fornecedor, quantidade, um_nota,
                                       valor_unitario, valor_total, id_produto)
               VALUES (%s, 1, 'ITEM DA RECEBIDA', 1, %s, 10, 10, %s)""",
            (i, produto["um_estoque"], produto["id"] if ligado else None))
        importador.calcular_nota(cur, i)
        notas.append(i)
        return i

    omie = nota(f"RC1{marca}", "OMIE")
    xml = nota(f"RC2{marca}", "XML")
    pendente = nota(f"RC3{marca}", "OMIE", ligado=False)
checar("há produto para o teste", bool(produto))


def detalhe(i):
    return chamar("GET", f"/notas/{i}", token=token)[1]


print("1. pode_receber")
d = detalhe(omie)
checar("a conciliada do Omie pode", d["status"] == "CONCILIADA" and d["pode_receber"] is True, d.get("status"))
checar("a do XML não pode", detalhe(xml)["pode_receber"] is False)
checar("a importada (item sem produto) não pode", detalhe(pendente)["pode_receber"] is False)
_so_recebidas(True)
checar("com Somente recebidas ligado, não pode", detalhe(omie)["pode_receber"] is False)

print("2. as recusas")
s, r = chamar("POST", f"/notas/{omie}/receber", {"recebido_por": "Maria"}, token)
checar("Somente recebidas ligado: 409", s == 409 and "Somente recebidas" in r["detail"], (s, r))
_so_recebidas(False)
s, _ = chamar("POST", f"/notas/{omie}/receber", {}, token)
checar("sem nome: 422", s == 422, s)
s, _ = chamar("POST", f"/notas/{omie}/receber", {"recebido_por": "   "}, token)
checar("nome só de espaços: 422", s == 422, s)
s, r = chamar("POST", f"/notas/{pendente}/receber", {"recebido_por": "Maria"}, token)
checar("importada: 409, e diz do item sem produto", s == 409 and "sem produto" in r["detail"], (s, r))
s, r = chamar("POST", f"/notas/{xml}/receber", {"recebido_por": "Maria"}, token)
checar("XML: 409", s == 409 and "Omie" in r["detail"], (s, r))

print("3. marcar como recebida")
s, r = chamar("POST", f"/notas/{omie}/receber", {"recebido_por": "  Maria   da Silva "}, token)
checar("200", s == 200, (s, r))
d = detalhe(omie)
checar("status RECEBIDA", d["status"] == "RECEBIDA", d["status"])
checar("o nome fica na nota, com os espaços arrumados", d["recebido_por"] == "Maria da Silva", d["recebido_por"])
checar("com a data e quem marcou", bool(d["recebido_em"]) and bool(d["recebido_marcado_por"]), d)
checar("e não oferece marcar de novo", d["pode_receber"] is False)
s, r = chamar("POST", f"/notas/{omie}/receber", {"recebido_por": "Outro"}, token)
checar("de novo: 409", s == 409 and "já está" in r["detail"], (s, r))

print("4. a lista")
s, l = chamar("GET", f"/notas?status=RECEBIDA&busca=RC1{marca}", token=token)
checar("o filtro RECEBIDA traz a nota, com quem recebeu",
       s == 200 and len(l) == 1 and l[0]["recebido_por"] == "Maria da Silva", (s, l))
s, l = chamar("GET", f"/notas?status=IMPORTADA&status=CONCILIADA&status=RECEBIDA&busca={marca}",
              token=token)
checar("o 'a lançar' a inclui", any(n["id"] == omie for n in l), l)

print("5. o recálculo")
with get_cursor() as cur:
    importador.calcular_nota(cur, omie)
checar("recalculada, continua RECEBIDA", detalhe(omie)["status"] == "RECEBIDA")
with get_cursor() as cur:
    cur.execute("UPDATE nota_itens SET id_produto = NULL WHERE id_nota = %s", (omie,))
    importador.calcular_nota(cur, omie)
checar("com item pendente, vira IMPORTADA (o nome fica)",
       detalhe(omie)["status"] == "IMPORTADA" and detalhe(omie)["recebido_por"] == "Maria da Silva")
with get_cursor() as cur:
    cur.execute("UPDATE nota_itens SET id_produto = %s WHERE id_nota = %s", (produto["id"], omie))
    importador.calcular_nota(cur, omie)
checar("resolvido o item, volta RECEBIDA (não conciliada)", detalhe(omie)["status"] == "RECEBIDA")

print("6. lote, lançamento e estorno")
s, pv = chamar("GET", "/notas/lote/previa", token=token)
checar("entra na prévia do lote", s == 200 and any(n["id"] == omie for n in pv.get("notas", [])),
       (s, str(pv)[:200]))
s, r = chamar("POST", f"/notas/{omie}/lancar", {"aceitar_inativos": True}, token)
checar("lança", s == 200, (s, r))
d = detalhe(omie)
checar("lançada, guarda quem recebeu", d["status"] == "LANCADA" and d["recebido_por"] == "Maria da Silva", d["status"])
s, r = chamar("POST", f"/notas/{omie}/estornar", {}, token)
checar("estornada, volta a RECEBIDA (a mercadoria chegou)", s == 200 and detalhe(omie)["status"] == "RECEBIDA",
       (s, r, detalhe(omie)["status"]))

print("7. desfazer o recebimento")
s, r = chamar("DELETE", f"/notas/{omie}/receber", token=token)
d = detalhe(omie)
checar("volta a conciliada e apaga o nome",
       s == 200 and d["status"] == "CONCILIADA" and d["recebido_por"] is None, (s, r, d["status"]))
s, _ = chamar("DELETE", f"/notas/{omie}/receber", token=token)
checar("de novo: 409", s == 409, s)

print("8. o relatório de compras")
chamar("POST", f"/notas/{omie}/receber", {"recebido_por": "João"}, token)
br = hoje.strftime("%d/%m/%Y")
s, dd = chamar("GET", f"/exportar/compras/dados?inicio={hoje}&fim={hoje}&situacao_nota=recebida"
                      f"&busca_fornecedor=recebida%20{marca}", token=token)
texto = json.dumps(dd, ensure_ascii=False, default=str)
checar("filtra as recebidas, com a coluna 'Recebido por' e o nome",
       s == 200 and "Recebido por" in texto and "João" in texto and f"RC1{marca}" in texto
       and f"RC2{marca}" not in texto, (s, texto[:400]))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
