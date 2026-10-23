"""Os quatro relatórios de 23/10/2026: compras, perdas e ajustes, margem dos pratos e
recebimentos do consumo.

🔑 Pedido do dono: *"Gostaria de mais relatorios e planilhas"* — escolhidos 1, 2, 3 e 6
da lista proposta. Cada um é cobrado pelo que AFIRMA: a soma que fecha, a linha que
aparece, o filtro que corta e a permissão que barra.

    python tests/smoke_relatorios_gestao.py      (API de pé na 9200)
"""

import atexit
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, cru=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=180) as r:
            bruto = r.read()
            return r.status, bruto if cru else json.loads(bruto or b"null")
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


def numero(texto: str) -> float:
    """"1234,5" (o CSV da casa) → 1234.5; vazio → 0."""
    texto = (texto or "").strip()
    return float(texto.replace(",", ".")) if texto else 0.0


def csv(caminho: str) -> tuple[int, list[list[str]]]:
    """O CSV em linhas de células; o título, o resumo e o cabeçalho vêm junto."""
    st, bruto = chamar("GET", caminho, token=token, cru=True)
    if st != 200 or not isinstance(bruto, bytes):
        return st, []
    texto = bruto.decode("utf-8-sig")
    return st, [l.split(";") for l in texto.splitlines()]


def linha_com(linhas, trecho: str) -> list[str] | None:
    return next((l for l in linhas if any(trecho in c for c in l)), None)


def coluna(linhas, cabecalho: str, linha: list[str]) -> str:
    """A célula de `linha` na coluna cujo cabeçalho é `cabecalho`."""
    for l in linhas:
        if cabecalho in l and len(l) == len(linha):
            return linha[l.index(cabecalho)]
    return ""


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today().isoformat()
criados: dict = {"produtos": [], "vendas": [], "lotes": [], "pessoas": [], "movimentos": []}


def _limpar():
    for lid in criados["lotes"]:
        chamar("POST", f"/receber/lotes/{lid}/estornar-baixa", None, token=token)
        chamar("POST", f"/receber/lotes/{lid}/cancelar", None, token=token)
    for v in criados["vendas"]:
        if v:
            chamar("DELETE", f"/vendas/{v}", token=token)
    for m in criados["movimentos"]:
        chamar("POST", f"/estoque/movimentos/{m}/estornar", {"motivo": "limpeza da suite"},
               token=token)
    for p in criados["produtos"]:
        if p:
            chamar("DELETE", f"/produtos/{p}", token=token)
    for f in criados["pessoas"]:
        chamar("DELETE", f"/fornecedores/{f}", token=token)
    for k in criados:
        criados[k].clear()


atexit.register(_limpar)


print("1. os quatro entram no catalogo de quem pode")
st, cat = chamar("GET", "/exportar/catalogo", token=token)
chaves = {c["chave"] for c in cat or []}
checar("compras, perdas, margem e recebimentos aparecem para o admin",
       {"compras", "perdas", "margem", "recebimentos"} <= chaves, sorted(chaves))
filtros = {c["chave"]: {x["nome"] for x in c["filtros"]} for c in cat or []}
checar("com os filtros declarados",
       {"detalhe_compras", "situacao_nota", "busca_fornecedor"} <= filtros.get("compras", set())
       and {"detalhe_perdas", "motivos"} <= filtros.get("perdas", set())
       and {"formas", "pessoas"} <= filtros.get("recebimentos", set()), filtros)


print("\n2. o cenario: um insumo com entrada, perda e uma venda; uma pessoa com lote")
local = garantir_local(chamar, token)
st, prod = chamar("POST", "/produtos", {
    "codigo": f"REL-{marca}", "nome": f"INSUMO RELATORIO {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", "preco_venda": 25,
}, token=token)
PROD = (prod or {}).get("id")
criados["produtos"].append(PROD)
st, ent = chamar("POST", "/estoque/entradas", {
    "id_produto": PROD, "quantidade": 10, "custo_unitario": 10, "id_local": local["id"],
    "documento": f"REL {marca}"}, token=token)
if (ent or {}).get("id"):
    criados["movimentos"].append(ent["id"])
_st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
MOTIVO = (motivos or [{}])[0]
st, perda = chamar("POST", "/estoque/saidas", {
    "id_produto": PROD, "quantidade": 3, "tipo": "SAIDA_PERDA", "id_local": local["id"],
    "id_motivo_perda": MOTIVO.get("id"), "observacao": f"perda {marca}"}, token=token)
PERDA = (perda or {}).get("id")
checar("a entrada e a perda entram", ent.get("id") and PERDA, (ent, perda))

st, v = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"REL{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": PROD, "quantidade": 2, "valor_unitario": 25}]}]}, token=token)
st, lista = chamar("GET", f"/vendas?busca=REL{marca}", token=token)
criados["vendas"].append((lista or [{}])[0].get("id"))

st, pessoa = chamar("POST", "/fornecedores", {"nome": f"REL PESSOA {marca}",
                                              "fornecedor": False}, token=token)
PESSOA = (pessoa or {}).get("id")
criados["pessoas"].append(PESSOA)
st, v = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"RELP{marca}", "origem": "MANUAL", "id_pessoa": PESSOA,
    "itens": [{"id_produto": PROD, "quantidade": 1, "valor_unitario": 30}]}]}, token=token)
st, lista = chamar("GET", f"/vendas?busca=RELP{marca}", token=token)
criados["vendas"].append((lista or [{}])[0].get("id"))
st, g = chamar("POST", "/receber/lotes", {"ate": hoje, "ids_pessoa": [PESSOA]}, token=token)
LOTE = ((g or {}).get("lotes") or [{}])[0].get("id")
criados["lotes"].append(LOTE)
st, b = chamar("POST", f"/receber/lotes/{LOTE}/receber",
               {"recebido_em": hoje, "forma_pagamento": "PERMUTA"}, token=token)
checar("a venda, o lote e a baixa por permuta entram", st == 200 and LOTE, (st, b))


print("\n3. perdas e ajustes: a perda aparece com o motivo, e o estorno a zera")
q = f"inicio={hoje}&fim={hoje}"
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=movimento")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("movimento a movimento: a perda de 3 a 10,00 vale 30",
       st == 200 and minha and abs(numero(coluna(linhas, "Valor", minha)) - 30) < 0.01,
       (st, minha))
checar("com o motivo do cadastro", minha and coluna(linhas, "Motivo", minha) == MOTIVO.get("nome"),
       (minha, MOTIVO))
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=motivo&motivos=m{MOTIVO.get('id')}")
checar("por motivo, filtrado pelo motivo: so ele sai",
       st == 200 and linha_com(linhas, MOTIVO.get("nome", "?"))
       and not linha_com(linhas, "Diferença de inventário"), linhas[:8])
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=produto&motivos=inventario")
checar("o filtro por origem corta: em 'inventario' o insumo nao aparece",
       st == 200 and not linha_com(linhas, f"INSUMO RELATORIO {marca}"), linhas[:6])
chamar("POST", f"/estoque/movimentos/{PERDA}/estornar", {"motivo": "teste"}, token=token)
st, linhas = csv(f"/exportar/perdas.csv?{q}&detalhe_perdas=produto")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("estornada, a perda liquida do produto vai a zero",
       minha and abs(numero(coluna(linhas, "Valor perdido", minha))) < 0.01, minha)
st, pdf = chamar("GET", f"/exportar/perdas.pdf?{q}", token=token, cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n4. compras: as visoes somam o mesmo, e o filtro de situacao corta")
q = "inicio=2026-01-01&fim=2026-12-31"
totais = {}
for det, cab, rotulo in (("nota", "Total das notas", "Total das notas"),
                         ("fornecedor", "Total das notas", "Total das notas"),
                         ("produto", "Custo total dos itens", "Custo total dos itens"),
                         ("item", "Custo total dos itens", "Custo total dos itens")):
    st, linhas = csv(f"/exportar/compras.csv?{q}&detalhe_compras={det}")
    resumo = linha_com(linhas, rotulo)
    totais[det] = numero(resumo[1]) if resumo and len(resumo) > 1 else None
    checar(f"a visao '{det}' sai", st == 200 and totais[det] is not None, (st, linhas[:6]))
checar("por nota e por fornecedor fecham no mesmo total",
       totais["nota"] is not None and abs(totais["nota"] - (totais["fornecedor"] or -1)) < 0.01,
       totais)
checar("por produto e item a item fecham no mesmo custo",
       totais["produto"] is not None and abs(totais["produto"] - (totais["item"] or -1)) < 0.01,
       totais)
st, linhas = csv(f"/exportar/compras.csv?{q}&detalhe_compras=nota&situacao_nota=cancelada")
situacoes = {l[4] for l in linhas if len(l) == 11 and l[4] in
             ("lançada", "importada", "conciliada", "cancelada")}
checar("so canceladas: nenhuma lancada no arquivo", st == 200 and situacoes <= {"cancelada"},
       situacoes)
st, pdf = chamar("GET", f"/exportar/compras.pdf?{q}&detalhe_compras=fornecedor", token=token,
                 cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n5. margem dos pratos: o vendido no periodo, com o custo e o CMV %")
st, linhas = csv(f"/exportar/margem.csv?inicio={hoje}&fim={hoje}")
minha = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("o produto vendido hoje aparece", st == 200 and minha, (st, linhas[:6]))
checar("com o preco de 25 e as 3 unidades vendidas (2 + 1 da pessoa)",
       minha and abs(numero(coluna(linhas, "Preço", minha)) - 25) < 0.01
       and abs(numero(coluna(linhas, "Vendido", minha)) - 3) < 0.01, minha)
cmv_pct = numero(coluna(linhas, "CMV %", minha)) if minha else 0
checar("e o CMV % de pelo menos 40 (custo 10 sobre 25, mais o que a loja somar por unidade)",
       cmv_pct >= 39.99, cmv_pct)
st, linhas = csv("/exportar/margem.csv?inicio=2001-01-01&fim=2001-01-31")
checar("periodo sem venda: o produto nao aparece",
       st == 200 and not linha_com(linhas, f"INSUMO RELATORIO {marca}"), st)


print("\n6. recebimentos: o lote baixado no periodo, e o quadro por forma")
st, linhas = csv(f"/exportar/recebimentos.csv?inicio={hoje}&fim={hoje}")
minha = linha_com(linhas, f"REL PESSOA {marca}")
checar("o lote recebido hoje aparece com a forma",
       st == 200 and minha and coluna(linhas, "Forma", minha) == "Permuta", minha)
checar("e o quadro por forma de pagamento vem junto",
       linha_com(linhas, "Por forma de pagamento") is not None, linhas[-6:])
st, linhas = csv(f"/exportar/recebimentos.csv?inicio={hoje}&fim={hoje}&formas=DINHEIRO")
checar("filtrado por dinheiro, o lote da permuta some",
       st == 200 and not linha_com(linhas, f"REL PESSOA {marca}"), st)
st, pdf = chamar("GET", f"/exportar/recebimentos.pdf?inicio={hoje}&fim={hoje}", token=token,
                 cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n8. vendas documento a documento: a fita do periodo, cancelada marcada e fora da conta")
q = f"inicio={hoje}&fim={hoje}"
st, linhas = csv(f"/exportar/vendas-documentos.csv?{q}")
minha = linha_com(linhas, f"REL{marca}")
checar("o cupom lancado hoje aparece com o total de 50",
       st == 200 and minha and abs(numero(coluna(linhas, "Total", minha)) - 50) < 0.01, minha)
total_antes = linha_com(linhas, "Total vendido")
checar("e o quadro por origem e canal vem junto",
       linha_com(linhas, "Por origem e canal") is not None, linhas[-5:])
VREL = criados["vendas"][0]
chamar("DELETE", f"/vendas/{VREL}", token=token)
st, linhas = csv(f"/exportar/vendas-documentos.csv?{q}")
minha = linha_com(linhas, f"REL{marca}")
total_depois = linha_com(linhas, "Total vendido")
checar("cancelado, o cupom CONTINUA na fita, marcado",
       minha and coluna(linhas, "Situação", minha) == "cancelada", minha)
checar("e o total do dia cai os 50",
       total_antes and total_depois
       and abs(numero(total_antes[1]) - numero(total_depois[1]) - 50) < 0.01,
       (total_antes, total_depois))
st, linhas = csv(f"/exportar/vendas-documentos.csv?{q}&origem_venda=PDV_LEGAL")
checar("filtrado pelo PDV, a venda lancada a mao some",
       st == 200 and not linha_com(linhas, f"REL{marca}"), st)


print("\n9. producao e a agenda do dia")
st, linhas = csv("/exportar/producao.csv?inicio=2026-01-01&fim=2026-12-31")
resumo = linha_com(linhas, "Custo produzido")
st2, linhas2 = csv("/exportar/producao.csv?inicio=2026-01-01&fim=2026-12-31"
                   "&detalhe_producao=produto")
resumo2 = linha_com(linhas2, "Custo produzido")
checar("producao a producao e por produto fecham no mesmo custo",
       st == 200 and st2 == 200 and resumo and resumo2 and resumo[1] == resumo2[1],
       (resumo, resumo2))
# A agenda so aceita produto com ficha HOMOLOGADA: um prato de 1 insumo por unidade.
st, prato = chamar("POST", "/produtos", {
    "codigo": f"RELP-{marca}", "nome": f"PRATO RELATORIO {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "producao_propria": True, "controla_estoque": True,
    "status": "ATIVO"}, token=token)
PRATO = (prato or {}).get("id")
criados["produtos"].append(PRATO)
st, fi = chamar("POST", "/fichas", {
    "id_produto": PRATO, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": PROD, "qtd_bruta": 1, "um": "UN"}]}, token=token)
chamar("POST", f"/fichas/{(fi or {}).get('id')}/homologar", {}, token=token)
st, ag = chamar("POST", "/producao-agenda", {
    "id_produto": PRATO, "data_prevista": hoje, "quantidade": 4,
    "observacao": f"agenda {marca}"}, token=token)
AG = (ag or {}).get("id")
checar("o prato com ficha entra na agenda de hoje", st in (200, 201) and AG, (st, ag))
st, linhas = csv(f"/exportar/agenda-producao.csv?data={hoje}")
minha = linha_com(linhas, f"agenda {marca}")
checar("a agenda do dia traz a linha planejada para hoje",
       st == 200 and minha and abs(numero(coluna(linhas, "Quantidade", minha)) - 4) < 0.01,
       (st, minha))
insumo = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("e o 'O que separar' pede 4 do insumo (1 por prato)",
       insumo and abs(numero(coluna(linhas, "Separar", insumo)) - 4) < 0.01, insumo)
st, linhas = csv("/exportar/agenda-producao.csv?data=2001-01-01")
checar("outro dia: a linha de hoje nao aparece",
       st == 200 and not linha_com(linhas, f"agenda {marca}"), st)
st, pdf = chamar("GET", f"/exportar/agenda-producao.pdf?data={hoje}", token=token, cru=True)
checar("e o PDF da agenda sai", st == 200 and pdf[:5] == b"%PDF-", st)
if AG:
    chamar("DELETE", f"/producao-agenda/{AG}", token=token)


print("\n10. o livro de fichas: uma ficha por pagina")
st, livro = chamar("GET", "/exportar/livro-de-fichas.pdf", token=token, cru=True)
paginas = len(re.findall(rb"/Type /Page[^s]", livro)) if isinstance(livro, bytes) else 0
checar("o livro sai em PDF", st == 200 and isinstance(livro, bytes) and livro[:5] == b"%PDF-",
       st)
checar("com ao menos uma pagina por ficha", paginas >= 1, paginas)
st, nada = chamar("GET", "/exportar/livro-de-fichas.pdf?categorias=999999999", token=token)
checar("recorte sem ficha: 404", st == 404, (st, nada))


print("\n12. reservas do dia: a folha da recepcao")
# 🔑 Direto no banco: o que se cobra aqui é o RELATÓRIO, e a criação da reserva já tem
# a suíte dela (com horário, disponibilidade e alocação de mesa no meio).
from database import get_cursor, init_pool  # noqa: E402

init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = ((eu or {}).get("unidades") or [{}])[0].get("id") or 1
with get_cursor() as cur:
    cur.execute("INSERT INTO saloes (id_unidade, nome) VALUES (%s, %s) RETURNING id",
                (U, f"SALAO REL {marca}"))
    SALAO = cur.fetchone()["id"]
    mesas = []
    for nome in ("R1", "R2"):
        cur.execute("""INSERT INTO mesas (id_unidade, id_salao, nome, lugares, capacidade_max)
                       VALUES (%s, %s, %s, 4, 4) RETURNING id""", (U, SALAO, f"{nome}{marca[-3:]}"))
        mesas.append(cur.fetchone()["id"])
    reservas = {}
    for nome, hora, pessoas, status in (("GRUPO", "20:00", 8, "CONFIRMADA"),
                                        ("CASAL", "19:30", 2, "PENDENTE"),
                                        ("DESISTIU", "21:00", 3, "CANCELADA")):
        cur.execute(
            """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, nome, telefone,
                                     observacao_interna)
               VALUES (%s, %s, %s, %s, %s, %s, '47999990000', %s) RETURNING id""",
            (U, hoje, hora, pessoas, status, f"REL {nome} {marca}",
             "trazer o bolo" if nome == "GRUPO" else None))
        reservas[nome] = cur.fetchone()["id"]
    for m in mesas:
        cur.execute("INSERT INTO reserva_mesas (id_reserva, id_mesa) VALUES (%s, %s)",
                    (reservas["GRUPO"], m))


def _limpar_reservas():
    with get_cursor() as cur:
        cur.execute("DELETE FROM reservas WHERE id = ANY(%s)", (list(reservas.values()),))
        cur.execute("DELETE FROM mesas WHERE id = ANY(%s)", (mesas,))
        cur.execute("DELETE FROM saloes WHERE id = %s", (SALAO,))


atexit.register(_limpar_reservas)
st, linhas = csv(f"/exportar/reservas-dia.csv?data={hoje}")
grupo = linha_com(linhas, f"REL GRUPO {marca}")
checar("o grupo aparece com as duas mesas JUNTAS numa linha so",
       st == 200 and grupo and coluna(linhas, "Mesa", grupo) == f"R1{marca[-3:]} + R2{marca[-3:]}"
       and len([l for l in linhas if any(f"REL GRUPO {marca}" in c for c in l)]) == 1,
       (st, grupo))
checar("com a observacao interna e o salao",
       grupo and "trazer o bolo" in coluna(linhas, "Observação", grupo)
       and coluna(linhas, "Salão", grupo) == f"SALAO REL {marca}", grupo)
casal = linha_com(linhas, f"REL CASAL {marca}")
checar("a pendente aparece, antes do grupo (ordem da hora)",
       casal and coluna(linhas, "Situação", casal) == "aguardando confirmação"
       and linhas.index(casal) < linhas.index(grupo), casal)
checar("a cancelada fica de fora sem escolha",
       not linha_com(linhas, f"REL DESISTIU {marca}"), linhas[:12])
st, linhas = csv(f"/exportar/reservas-dia.csv?data={hoje}&situacao_reserva=CANCELADA")
checar("pedindo as canceladas, so ela sai",
       st == 200 and linha_com(linhas, f"REL DESISTIU {marca}")
       and not linha_com(linhas, f"REL GRUPO {marca}"), linhas[:12])
st, linhas = csv("/exportar/reservas-dia.csv?data=2001-01-01")
checar("outro dia: nada destas", st == 200 and not linha_com(linhas, f"REL GRUPO {marca}"), st)
st, pdf = chamar("GET", f"/exportar/reservas-dia.pdf?data={hoje}", token=token, cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n13. pedidos do cardapio: pedido a pedido e por produto, recusado fora da conta")
with get_cursor() as cur:
    cur.execute("SELECT coalesce(max(numero), 0) AS n FROM pedidos WHERE id_unidade = %s", (U,))
    n0 = cur.fetchone()["n"]
    pedidos_rel = []
    for i, (situacao, qtd_) in enumerate((("CONFIRMADO", 2), ("ENTREGUE", 1), ("RECUSADO", 5))):
        total_ = 25 * qtd_
        cur.execute(
            """INSERT INTO pedidos (id_unidade, numero, nome, telefone, modo, para_quando,
                                    forma_pagamento, subtotal, total, situacao, chave)
               VALUES (%s, %s, %s, '47999990000', 'RETIRADA', (%s::date + time '12:00'),
                       'RETIRADA', %s, %s, %s, %s) RETURNING id""",
            (U, n0 + 1 + i, f"REL PEDIDO {situacao} {marca}", hoje, total_, total_, situacao,
             f"rel-{marca}-{i}"))
        pid = cur.fetchone()["id"]
        pedidos_rel.append(pid)
        cur.execute("""INSERT INTO pedido_itens (id_pedido, id_produto, nome, quantidade,
                                                 preco_unitario, total)
                       VALUES (%s, %s, %s, %s, 25, %s)""",
                    (pid, PROD, f"INSUMO RELATORIO {marca}", qtd_, total_))


def _limpar_pedidos():
    with get_cursor() as cur:
        cur.execute("DELETE FROM pedidos WHERE id = ANY(%s)", (pedidos_rel,))


atexit.register(_limpar_pedidos)
q = f"inicio={hoje}&fim={hoje}"
st, linhas = csv(f"/exportar/pedidos.csv?{q}")
conf = linha_com(linhas, f"REL PEDIDO CONFIRMADO {marca}")
recu = linha_com(linhas, f"REL PEDIDO RECUSADO {marca}")
checar("o confirmado aparece com o total de 50",
       st == 200 and conf and abs(numero(coluna(linhas, "Total", conf)) - 50) < 0.01, conf)
checar("o recusado APARECE, marcado", recu and coluna(linhas, "Situação", recu) == "recusado",
       recu)
checar("e os quadros por situacao e por origem e modo vem junto",
       linha_com(linhas, "Por situação") and linha_com(linhas, "Por origem e modo"), linhas[-8:])
st, linhas = csv(f"/exportar/pedidos.csv?{q}&detalhe_pedidos=produto")
item = linha_com(linhas, f"INSUMO RELATORIO {marca}")
checar("por produto: 3 unidades (2 + 1), sem as 5 do recusado, em 2 pedidos",
       st == 200 and item and abs(numero(coluna(linhas, "Quantidade", item)) - 3) < 0.01
       and coluna(linhas, "Em quantos pedidos", item) == "2", item)
checar("valendo 75", item and abs(numero(coluna(linhas, "Total", item)) - 75) < 0.01, item)
st, linhas = csv(f"/exportar/pedidos.csv?{q}&situacao_pedido=ENTREGUE")
checar("filtrado por entregue, so ele sai",
       st == 200 and linha_com(linhas, f"REL PEDIDO ENTREGUE {marca}")
       and not linha_com(linhas, f"REL PEDIDO CONFIRMADO {marca}"), linhas[:10])
st, linhas = csv("/exportar/pedidos.csv?inicio=2001-01-01&fim=2001-01-31")
checar("outro periodo: nada destes",
       st == 200 and not linha_com(linhas, f"REL PEDIDO CONFIRMADO {marca}"), st)
st, pdf = chamar("GET", f"/exportar/pedidos.pdf?{q}&detalhe_pedidos=produto", token=token, cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)


print("\n11. quem nao tem a chave nao baixa")
tk = garantir_cozinha(chamar, token)
st_c, cat_c = chamar("GET", "/exportar/catalogo", token=tk)
chaves_c = {c["chave"] for c in cat_c or []}
for chave in ("compras", "margem", "recebimentos", "producao", "vendas-documentos",
              "reservas-dia", "pedidos"):
    if chave not in chaves_c:
        st, r = chamar("GET", f"/exportar/{chave}.csv", token=tk)
        checar(f"{chave} sem a chave: 403", st == 403, (st, r))
checar("e o catalogo da cozinha so oferece o que ela pode baixar",
       all(chamar("GET", f"/exportar/{c}.csv?inicio={hoje}&fim={hoje}", token=tk,
                  cru=True)[0] == 200
           for c in chaves_c & {"compras", "perdas", "margem", "recebimentos"}), chaves_c)


# ⚠️ Pedidos antes do resto: o item do pedido aponta para o produto da suíte.
_limpar_pedidos()
_limpar_reservas()
_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
