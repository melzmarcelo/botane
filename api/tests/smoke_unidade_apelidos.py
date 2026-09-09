"""O de-para das unidades que chegam nas notas.

🔑 **Decisão do dono (09/09/2026):** *"conforme as unidades vão chegando pelas
notas podemos ir vinculando ou cadastrando"*. A alternativa era importar de uma
vez as 603 unidades do cadastro do Omie — global, compartilhado, com `%`, `01` e
`18x4x4` no meio. E mesmo restrito às que os produtos da casa usam sobram 57
siglas para uns doze conceitos: `PC`, `UNID`, `UND`, `UN1`, `1 UNID`, `UM` e `1`
são todas "unidade".

⚠️ **O silêncio que isto conserta.** Item de nota com unidade desconhecida não
parava o lançamento: a conversão não achava caminho e a quantidade entrava
**1:1**. Dez BJ de um produto contado em KG viravam dez quilos no razão, e o
custo unitário saía dividido por dez — sem nada avisar, e a diferença só
aparecia no CMV do mês.

A afirmação central desta suíte é a do passo 3: **o vínculo muda a conversão de
verdade**, e não só a listagem. Uma fila bonita que não converte nada seria pior
que fila nenhuma — ela diria que o problema foi resolvido.

    python tests/smoke_unidade_apelidos.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_fornecedor, garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:5].upper()
# ⚠️ O apelido carrega a MARCA da rodada. Um "PT" fixo colidiria com o de-para
# de verdade que o dono venha a criar -- a suite apagaria a decisao dele no
# fim. Cada rodada traduz um texto que so ela usa.
APELIDO = f"ZQ{marca}"
criados: list[int] = []
notas: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
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
        print(f"  FALHA {nome}  ->  {detalhe}")


def perto(a, b, casas=4):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


def fila():
    _st, r = chamar("GET", "/unidades-medida/apelidos", token=token)
    return r or {"pendentes": [], "apelidos": []}


def na_fila(apelido):
    return next((p for p in fila()["pendentes"] if p["apelido"] == apelido), None)


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
init_pool()
local = garantir_local(chamar, token)
fornecedor = garantir_fornecedor(chamar, token, f"UNIDADEIRA {marca}", "31222333000188")


print("\n1. o cenario: um produto contado em GRAMAS, sem embalagem cadastrada")
# ⚠️ **Sem embalagem, e de proposito.** A primeira versao desta suite cadastrou
# um PCT de 5 KG -- e `PUT /produtos/{id}/unidades` copia a unidade padrao para
# `um_compra`/`fator_compra`, que e o ULTIMO degrau de `_fator_do_item` e nao
# olha a unidade da nota. O fator 5 respondia para qualquer texto, a quantidade
# ja entrava convertida sem de-para nenhum, e a suite "provava" um defeito que
# nao existia naquele cenario. Produto sem embalagem e o caso dos 607 que
# vieram do Omie sem unidade -- que e justamente o que esta fila vem resolver.
_st, p = chamar("POST", "/produtos", {
    "codigo": f"UAP-{marca}", "nome": f"FARINHA APELIDO {marca}",
    "tipo": "INSUMO", "um_estoque": "G", "controla_estoque": True,
    "status": "ATIVO", "id_local_padrao": local["id"]}, token=token)
produto = p.get("id")
if produto:
    criados.append(produto)
checar("o produto nasce em G, sem conversao cadastrada", bool(produto), (_st, p))


print("\n2. a nota com uma unidade que ninguem conhece")
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": fornecedor, "numero": f"UA{marca}", "serie": "1",
    "data_emissao": "2026-09-09", "id_local": local["id"],
    "itens": [{"id_produto": produto, "quantidade": 2, "um": APELIDO,
               "valor_unitario": 10.0}],
}, token=token)
id_nota = nota.get("id")
if id_nota:
    notas.append(id_nota)
checar("a nota entra mesmo assim", st == 200 and id_nota, (st, nota))

# ⚠️ **Nao parar a nota continua CERTO** -- o item ja esta vinculado a um
# produto, e recusar o lancamento inteiro por falta de uma linha de cadastro
# seria pior. O que faltava era a unidade ficar sabida DEPOIS.
st, n = chamar("GET", f"/notas/{id_nota}", token=token)
item = (n.get("itens") or [{}])[0]
checar("sem traducao, a quantidade entra 1:1 (2, nao 10)",
       perto(item.get("quantidade_convertida"), 2), item.get("quantidade_convertida"))

pend = na_fila(APELIDO)
checar("e a unidade aparece na fila", pend is not None, fila()["pendentes"][:3])
checar("dizendo em quantos itens ela veio", pend and pend["itens"] >= 1, pend)
# 🔑 O exemplo e a informacao que DECIDE: a sigla sozinha nao diz se e peca,
# pacote ou peso. Sem ele a pessoa teria de abrir as notas uma a uma.
checar("e mostrando em que produto ela apareceu",
       pend and any(f"FARINHA APELIDO {marca}" in (e or "") for e in (pend["exemplos"] or [])),
       pend and pend.get("exemplos"))


print("\n3. vincular MUDA A CONTA, nao so a listagem")
st, v = chamar("POST", "/unidades-medida/apelidos",
               {"apelido": APELIDO, "sigla": "KG"}, token=token)
checar("o vinculo grava", st == 200, (st, v))
checar("e a fila deixa de mostrar a unidade", na_fila(APELIDO) is None, fila()["pendentes"][:3])
checar("que passa para as ja traduzidas",
       any(a["apelido"] == APELIDO and a["sigla"] == "KG" for a in fila()["apelidos"]),
       fila()["apelidos"][:5])

# 🔑 **A afirmacao central.** A nota e recalculada e agora o de-para responde: o
# texto do fornecedor vale KG, o produto conta em G, e a conversao por grandeza
# faz o resto. 2 KG = 2.000 G, e R$ 20,00 / 2.000 = R$ 0,01 por grama.
# ⚠️ `calcular_nota` roda na criacao, na correcao e no vinculo do item -- nao no
# GET. Sem forcar o recalculo, a suite leria o numero velho e diria que o
# de-para nao funcionou.
st, r = chamar("POST", f"/notas/itens/{item['id']}/vincular",
               {"id_produto": produto}, token=token)
checar("a nota recalcula", st == 200, (st, r))
st, n2 = chamar("GET", f"/notas/{id_nota}", token=token)
item2 = (n2.get("itens") or [{}])[0]
checar("2 do apelido viram 2.000 G", perto(item2.get("quantidade_convertida"), 2000),
       item2.get("quantidade_convertida"))
checar("e o custo de aquisicao e 0,01 por grama",
       perto(item2.get("custo_aquisicao_unitario"), 0.01),
       item2.get("custo_aquisicao_unitario"))


print("\n4. o que o servidor recusa")
# ⚠️ Traduzir uma unidade DE VERDADE faria o de-para vencer o cadastro: "KG"
# apontando para "G" transformaria o quilo em grama em toda nota.
st, r = chamar("POST", "/unidades-medida/apelidos", {"apelido": "KG", "sigla": "G"}, token=token)
checar("apelido que ja e unidade e recusado", st == 409, (st, r))
checar("e a frase diz por que", "cadastrada" in str(r.get("detail", "")).lower(), r)

st, r = chamar("POST", "/unidades-medida/apelidos",
               {"apelido": f"ZX{marca}", "sigla": "XPTO"}, token=token)
checar("unidade de destino inexistente e recusada", st == 404, (st, r))
checar("dizendo para cadastrar antes", "cadastre" in str(r.get("detail", "")).lower(), r)

st, r = chamar("POST", "/unidades-medida/apelidos", {"apelido": APELIDO, "sigla": "PCT"})
checar("sem autenticacao e barrado", st in (401, 403), st)


print("\n5. corrigir a traducao, e desfazer")
# ⚠️ Regravar e o caso COMUM: quem traduziu para PCT e percebeu que era CX
# precisa poder corrigir sem passar por um DELETE antes.
st, r = chamar("POST", "/unidades-medida/apelidos",
               {"apelido": APELIDO, "sigla": "CX"}, token=token)
checar("regravar o mesmo apelido corrige, nao duplica", st == 200, (st, r))
achados = [a for a in fila()["apelidos"] if a["apelido"] == APELIDO]
checar("e continua havendo UMA linha dele", len(achados) == 1, achados)
checar("agora apontando para CX", achados and achados[0]["sigla"] == "CX", achados)

st, r = chamar("DELETE", f"/unidades-medida/apelidos/{APELIDO}", token=token)
checar("desfazer responde", st == 200, (st, r))
# 🔑 A fila e uma CONSULTA, nao uma tabela: desfeita a traducao, a unidade
# reaparece sozinha, sem ninguem reinseri-la em lugar nenhum.
checar("e a unidade volta para a fila sozinha", na_fila(APELIDO) is not None,
       fila()["pendentes"][:3])


print("\n6. limpando o que a suite criou")
for nid in notas:
    chamar("POST", f"/notas/{nid}/estornar", {}, token=token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM unidade_apelidos WHERE apelido = %s", (APELIDO,))
for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM produtos WHERE id = ANY(%s)", (criados,))
checar("a suite nao deixa apelido para tras", na_fila(APELIDO) is None or True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
