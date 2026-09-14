"""O mesmo codigo em dois fornecedores sao dois produtos — e trocar o errado.

🔑 **Caso real relatado pelo dono (14/09/2026):** *"No omie, temos produto
ABACATE com o codigo 1, ai vem uma nota de outro fornecedor, com o produto
MORANGO, com o codigo 1 tambem. Por ter o mesmo codigo, este produto acaba
vinculando com o ABACATE, e caso a nota seja consiliada sem este ajuste, acaba
vindo para o botane com esta diferenca."*

⚠️ **A causa era nossa, nao do Omie.** `codigos_externos` tinha
`PRIMARY KEY (sistema, codigo)` e o degrau 1 da cascata perguntava so pelo
codigo — embora a coluna `id_fornecedor` ja existisse na tabela e ja fosse
gravada. A migracao 067 poe o fornecedor na chave e na pergunta.

⚠️ **E a correcao manual PIORAVA**: o `ON CONFLICT (sistema, codigo)` fazia
corrigir o MORANGO sobrescrever o vinculo do ABACATE do outro fornecedor. Este
arquivo prova que isso acabou — e o vai-e-vem com ele.

    python tests/smoke_codigo_por_fornecedor.py        (API de pe na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
CODIGO = f"C{marca}"          # o "1" do caso: o MESMO codigo nos dois fornecedores
produtos: list[int] = []
notas: list[int] = []
pessoas: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def novo_produto(nome, um="KG"):
    _st, r = chamar("POST", "/produtos", {
        "nome": f"{nome} {marca}", "tipo": "INSUMO", "um_estoque": um,
        "status": "ATIVO", "controla_estoque": True,
    }, token)
    if r.get("id"):
        produtos.append(r["id"])
    return r.get("id")


def nova_pessoa(nome):
    _st, r = chamar("POST", "/fornecedores", {
        "nome": f"{nome} {marca}", "fornecedor": True,
    }, token)
    if r.get("id"):
        pessoas.append(r["id"])
    return r.get("id")


def nota_com(id_fornecedor, descricao, id_produto=None, numero=None):
    """Uma nota digitada de um item, com o codigo do fornecedor na linha."""
    _st, r = chamar("POST", "/notas", {
        "id_fornecedor": id_fornecedor,
        "numero": numero or uuid.uuid4().hex[:8].upper(),
        "serie": "1",
        "data_emissao": "2026-09-14",
        "itens": [{
            "id_produto": id_produto,
            "descricao": descricao,
            "codigo_fornecedor": CODIGO,
            "quantidade": 10, "valor_unitario": 5, "um": "KG",
        }],
    }, token)
    if r.get("id"):
        notas.append(r["id"])
    return r.get("id")


def item_da(id_nota):
    _st, n = chamar("GET", f"/notas/{id_nota}", token=token)
    return (n.get("itens") or [{}])[0], n


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

print("\n0. a migracao 067 afrouxou a chave certa")
with get_cursor() as cur:
    cur.execute("""SELECT indexdef FROM pg_indexes
                    WHERE tablename = 'codigos_externos'
                      AND indexname = 'ux_codigos_externos_por_fornecedor'""")
    linha = cur.fetchone()
    checar("o indice unico inclui o fornecedor",
           bool(linha) and "id_fornecedor" in linha["indexdef"], linha)
    cur.execute("""SELECT conname FROM pg_constraint
                    WHERE conrelid = 'codigos_externos'::regclass AND contype = 'p'""")
    checar("e a chave primaria global saiu de cena", cur.fetchone() is None)

print("\n1. o fornecedor A ensina que o codigo 1 e o ABACATE")
forn_a = nova_pessoa("Hortifruti A")
forn_b = nova_pessoa("Distribuidora B")
abacate = novo_produto("Abacate")
morango = novo_produto("Morango")
checar("os dois fornecedores e os dois produtos existem",
       all([forn_a, forn_b, abacate, morango]))

n1 = nota_com(forn_a, "ABACATE MANTEIGA CX")
it1, _ = item_da(n1)
checar("o item nasce pendente — ninguem ensinou nada ainda", not it1.get("id_produto"), it1)
st, r = chamar("POST", f"/notas/itens/{it1['id']}/vincular",
               {"id_produto": abacate, "aprender": True}, token)
checar("vincular ao abacate responde 200", st == 200, (st, r))

# A proxima nota DO MESMO fornecedor entra sozinha: e para isso que serve.
n2 = nota_com(forn_a, "ABACATE MANTEIGA CX")
it2, _ = item_da(n2)
checar("a nota seguinte do MESMO fornecedor casa sozinha",
       it2.get("id_produto") == abacate, it2.get("produto"))

print("\n2. a nota do fornecedor B com o MESMO codigo nao casa no abacate")
# 🔑 Este e o defeito relatado. Antes da 067, o item abaixo vinha casado no
# ABACATE — e conciliar assim levava a mercadoria errada para o razao.
n3 = nota_com(forn_b, "MORANGO BANDEJA 250G")
it3, _ = item_da(n3)
checar("o item do fornecedor B NAO virou abacate",
       it3.get("id_produto") != abacate, (it3.get("id_produto"), it3.get("produto")))
# ⚠️ Cair em pendente e a troca certa: pendente aparece na conferencia,
# casamento errado nao aparece em lugar nenhum ate o CMV do mes.
checar("ele cai em pendente, para alguem resolver", not it3.get("id_produto"), it3)

print("\n3. e ensinar o morango NAO desfaz o abacate")
st, r = chamar("POST", f"/notas/itens/{it3['id']}/vincular",
               {"id_produto": morango, "aprender": True}, token)
checar("vincular ao morango responde 200", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("""SELECT id_fornecedor, id_produto FROM codigos_externos
                    WHERE sistema = 'OMIE' AND codigo = %s ORDER BY id_fornecedor""",
                (CODIGO,))
    linhas = cur.fetchall()
checar("o mesmo codigo convive em DUAS linhas, uma por fornecedor",
       len(linhas) == 2, linhas)
checar("e cada uma aponta para o produto do seu fornecedor",
       {(x["id_fornecedor"], x["id_produto"]) for x in linhas}
       == {(forn_a, abacate), (forn_b, morango)}, linhas)

# A prova do vai-e-vem: a nota nova de A tem de continuar caindo no abacate.
n4 = nota_com(forn_a, "ABACATE MANTEIGA CX")
it4, _ = item_da(n4)
checar("a nota nova do fornecedor A continua casando no ABACATE",
       it4.get("id_produto") == abacate, it4.get("produto"))
n5 = nota_com(forn_b, "MORANGO BANDEJA 250G")
it5, _ = item_da(n5)
checar("e a do fornecedor B, no MORANGO", it5.get("id_produto") == morango,
       it5.get("produto"))

print("\n4. trocar o produto de um item JA vinculado")
# 🔑 O pedido do dono: *"uma opcao para alterar o produto na nota na hora do
# recebimento"*. Ate aqui so item PENDENTE aceitava escolha.
pera = novo_produto("Pera")
st, r = chamar("POST", f"/notas/itens/{it5['id']}/vincular",
               {"id_produto": pera, "aprender": False}, token)
checar("trocar item ja vinculado responde 200", st == 200, (st, r))
checar("e a mensagem diz de onde para onde", "trocado" in (r.get("message") or "").lower(),
       r.get("message"))
it5b, _ = item_da(n5)
checar("a linha aponta para o produto novo", it5b.get("id_produto") == pera, it5b.get("produto"))
# ⚠️ Sem "aprender", o de-para NAO muda: a troca vale so para esta nota. E o
# caso do item que veio errado uma vez, sem o codigo do fornecedor ter mudado.
with get_cursor() as cur:
    cur.execute("""SELECT id_produto FROM codigos_externos
                    WHERE sistema = 'OMIE' AND codigo = %s AND id_fornecedor = %s""",
                (CODIGO, forn_b))
    checar("sem aprender, o de-para do fornecedor continua no morango",
           cur.fetchone()["id_produto"] == morango)

# Com "aprender", a troca CORRIGE o de-para em vez de duplica-lo.
st, r = chamar("POST", f"/notas/itens/{it5['id']}/vincular",
               {"id_produto": morango, "aprender": True}, token)
checar("voltar ao morango com aprender responde 200", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("""SELECT count(*) AS n FROM codigos_externos
                    WHERE sistema = 'OMIE' AND codigo = %s""", (CODIGO,))
    checar("e o de-para continua com duas linhas, nao quatro",
           cur.fetchone()["n"] == 2)

print("\n5. nota LANCADA nao se reponta")
# ⚠️ O razao e append-only: repontar so a linha da nota faria o documento
# discordar do lancamento, que nao teria como acompanhar.
st, r = chamar("POST", f"/notas/{n5}/lancar", {}, token)
checar("a nota lanca", st in (200, 201), (st, r))
st, r = chamar("POST", f"/notas/itens/{it5['id']}/vincular",
               {"id_produto": pera, "aprender": False}, token)
checar("trocar produto em nota lancada responde 409", st == 409, (st, r))
checar("dizendo que o caminho e estornar",
       "estorne" in (r.get("detail") or "").lower(), r.get("detail"))

print("\n6. pre-cadastro a partir da nota")
# 🔑 *"caso o produto nao seja encontrado, podemos realizar um pre-cadastro
# nesta nota e apontamos que este precisa ser completado."*
n6 = nota_com(forn_b, f"AGRIAO ORGANICO MACO {marca}", numero=f"N{marca}")
it6, _ = item_da(n6)
# Este item casou no morango (o de-para do fornecedor B aprendeu o codigo).
checar("o item chegou casado pelo de-para do fornecedor",
       it6.get("id_produto") == morango, it6.get("produto"))
# ⚠️ Sem dizer que e de proposito, criar sobre item vinculado e recusado: um
# clique distraido partiria o custo medio de um insumo em dois cadastros.
st, r = chamar("POST", f"/notas/itens/{it6['id']}/criar-produto", {}, token)
checar("criar produto sobre item vinculado pede confirmacao (409)", st == 409, (st, r))
checar("e diz em que produto ele esta hoje",
       (it6.get("produto") or "").split()[0].lower() in (r.get("detail") or "").lower(),
       r.get("detail"))
st, r = chamar("POST", f"/notas/itens/{it6['id']}/criar-produto",
               {"substituir": True}, token)
checar("com a confirmacao, cria e substitui", st == 200, (st, r))
novo = r.get("id_produto")
if novo:
    produtos.append(novo)
checar("a mensagem diz no lugar de quem entrou",
       "no lugar de" in (r.get("message") or "").lower(), r.get("message"))
st, p = chamar("GET", f"/produtos/{novo}", token=token)
checar("o produto novo nasce RASCUNHO", p.get("status") == "RASCUNHO", p.get("status"))
checar("com a origem dizendo que veio da nota", p.get("origem") == "NOTA", p.get("origem"))
it6b, _ = item_da(n6)
checar("a linha da nota aponta para ele", it6b.get("id_produto") == novo, it6b.get("id_produto"))
# 🔑 E a LINHA diz que falta completar — o alerta do inicio avisa a casa, nao
# esta nota, e quem sabe a unidade e o fator e quem esta conferindo.
checar("e a linha da nota carrega o status do cadastro",
       it6b.get("produto_status") == "RASCUNHO", it6b.get("produto_status"))

print("\n7. limpeza")
for nid in reversed(notas):
    chamar("POST", f"/notas/{nid}/estornar", {}, token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM codigos_externos WHERE codigo = %s", (CODIGO,))
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)
for sid in pessoas:
    chamar("DELETE", f"/fornecedores/{sid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
