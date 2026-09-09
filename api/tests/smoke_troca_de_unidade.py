"""Teste de fumaça da troca de unidade de estoque — o custo que estava em CX.

🔑 **O caso do dono (08/09/2026):** "o custo está em CX, mas alteramos para o
estoque em UN e a unidade de compra CX — deve fazer a alteração. E caso haja
alteração e não for possível fazer a conversão, apresentar uma mensagem de
validação."

⚠️ **A unidade de estoque é o denominador de tudo**: custo de referência,
mínimo, máximo e os fatores de embalagem são todos *por unidade de estoque*.
Trocar CX por UN sem convertê-los divide ou multiplica por doze, calado, o custo
de tudo que usa o insumo — e o erro só apareceria no CMV do mês, longe da causa.

⚠️ **O custo DIVIDE e as quantidades MULTIPLICAM**, e trocar os dois sentidos é
o engano natural: a caixa de 12 que custava 60 dá unidade a 5, não a 720.

    python tests/smoke_troca_de_unidade.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
criados: list[int] = []


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
        print(f"  FALHA {nome} {detalhe}")


def perto(a, b, casas=4):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


def criar(nome, um, **extra):
    corpo = {"codigo": f"TU{len(criados)}-{marca}", "nome": f"{nome} {marca}",
             "tipo": "INSUMO", "um_estoque": um, "controla_estoque": True,
             "status": "ATIVO", **extra}
    _st, r = chamar("POST", "/produtos", corpo, token=token)
    if r.get("id"):
        criados.append(r["id"])
    return r.get("id")


def campos_de(id_produto, colunas):
    with get_cursor() as cur:
        cur.execute(f"SELECT {', '.join(colunas)} FROM produtos WHERE id = %s", (id_produto,))
        return dict(cur.fetchone() or {})


def escrever_custo(id_produto, valor):
    """O custo de referência não tem endpoint de escrita — vai direto."""
    with get_cursor() as cur:
        cur.execute("UPDATE produtos SET custo_referencia = %s WHERE id = %s",
                    (valor, id_produto))


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
init_pool()
local = garantir_local(chamar, token)


print("\n1. o caso do dono: custo em CX, estoque passa a UN comprando CX de 12")
caixa = criar("AGUA EM CAIXA", "CX", estoque_minimo=2, estoque_maximo=10)
escrever_custo(caixa, 60)
checar("o produto nasce em CX", bool(caixa), caixa)

st, r = chamar("PUT", f"/produtos/{caixa}",
               {"um_estoque": "UN", "um_compra": "CX", "fator_compra": 12}, token=token)
checar("a troca é aceita", st == 200, (st, r))
d = campos_de(caixa, ["um_estoque", "custo_referencia", "estoque_minimo", "estoque_maximo"])
checar("a unidade de estoque virou UN", d["um_estoque"] == "UN", d)
# 🔑 O número do pedido: a caixa de 12 que custava 60 dá unidade a 5.
checar("o custo DIVIDIU: 60,00/CX -> 5,00/UN", perto(d["custo_referencia"], 5), d)
# ⚠️ E as quantidades vão no sentido CONTRÁRIO — 2 caixas são 24 unidades.
checar("o mínimo MULTIPLICOU: 2 CX -> 24 UN", perto(d["estoque_minimo"], 24), d)
checar("e o máximo também: 10 CX -> 120 UN", perto(d["estoque_maximo"], 120), d)


print("\n2. a embalagem cadastrada acompanha")
# ⚠️ `produto_unidades.fator` é "quantas unidades de ESTOQUE cabem nesta
# embalagem". Com o estoque em CX a caixa valia 1; com o estoque em UN ela passa
# a valer 12. Deixá-la como estava faria a nota de uma caixa baixar UMA unidade.
cx2 = criar("OLEO EM CAIXA", "CX")
# ⚠️ **O campo do corpo e `itens`.** A primeira versao deste teste mandou
# `unidades`, e o Pydantic aceitou com a lista VAZIA -- o endpoint substitui a
# tabela inteira, entao a chamada APAGOU em vez de gravar, e a checagem seguinte
# acusou a conversao de nao ter acontecido. O teste estava errado, nao o codigo.
#
# Um FARDO de 2 caixas: com o estoque em CX ele vale 2; com o estoque em UN e a
# caixa de 6, ele passa a valer 12 unidades.
st, r = chamar("PUT", f"/produtos/{cx2}/unidades",
               {"itens": [{"um": "FD", "fator": 2, "padrao": True}]}, token=token)
checar("a embalagem FD (2 caixas) e cadastrada", st in (200, 201), (st, r))
st, r = chamar("PUT", f"/produtos/{cx2}",
               {"um_estoque": "UN", "um_compra": "CX", "fator_compra": 6}, token=token)
checar("a troca e aceita com embalagem cadastrada", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT um, fator FROM produto_unidades WHERE id_produto = %s", (cx2,))
    emb = [dict(x) for x in cur.fetchall()]
checar("o fardo passou de 2 CX para 12 UN",
       any(e["um"] == "FD" and perto(e["fator"], 12) for e in emb), emb)


print("\n3. sem saber o fator, RECUSA com a frase que diz o que fazer")
# ⚠️ CX, PCT, FD e BDJ são todas grandeza UNIDADE com fator 1: a conta genérica
# diria 1 CX = 1 PCT e engoliria a caixa de 12 sem avisar. É por isso que a
# recusa existe, e não um palpite.
solto = criar("ITEM SOLTO", "CX")
escrever_custo(solto, 90)
st, r = chamar("PUT", f"/produtos/{solto}", {"um_estoque": "PCT"}, token=token)
checar("CX -> PCT sem fator é recusado", st == 400, (st, r))
checar("e a mensagem diz o que fazer",
       "unidade de compra" in (r.get("detail") or "").lower(), r.get("detail"))
d = campos_de(solto, ["um_estoque", "custo_referencia"])
# 🔑 Recusa é recusa: nada pode ter sido gravado pela metade.
checar("a unidade NÃO mudou", d["um_estoque"] == "CX", d)
checar("e o custo continua 90,00", perto(d["custo_referencia"], 90), d)


print("\n4. converte por grandeza quando ela responde: KG -> G")
farinha = criar("FARINHA", "KG")
escrever_custo(farinha, 8)
# 🔑 **Dividir o custo por cem ou mais PERGUNTA antes** (09/09/2026, relato do
# dono). Aconteceu com uma caixa de 1.000 unidades a R$ 33,99: um fator
# invertido dividiu por mil, o custo virou R$ 0,03 e nada avisou — e corrigir o
# fator de volta nao desfaz, porque a conversao so roda quando a unidade muda.
# ⚠️ KG -> G divide por mil e cai na mesma guarda, mesmo sendo legitimo. E o
# preco certo: o Sim custa um clique, o Nao custa o custo do produto.
st, r = chamar("PUT", f"/produtos/{farinha}", {"um_estoque": "G"}, token=token)
checar("KG -> G pede confirmacao, porque o custo despenca", st == 409, (st, r))
checar("e a recusa mostra os DOIS numeros",
       "8" in str(r.get("detail", "")) and "0.01" in str(r.get("detail", "")),
       r.get("detail"))
d = campos_de(farinha, ["um_estoque", "custo_referencia"])
# ⚠️ Recusa e recusa: nada pode ter sido gravado pela metade.
checar("a unidade NAO mudou sem o sim", d["um_estoque"] == "KG", d)
checar("e o custo continua 8,00", perto(d["custo_referencia"], 8), d)

st, r = chamar("PUT", f"/produtos/{farinha}",
               {"um_estoque": "G", "confirmar_troca_de_unidade": True}, token=token)
checar("com o sim explicito, a troca acontece", st == 200, (st, r))
d = campos_de(farinha, ["um_estoque", "custo_referencia"])
checar("o custo virou 0,008 por grama", perto(d["custo_referencia"], 0.008, 6), d)

# 🔑 **O custo antigo fica AUDITADO.** Antes ele sumia sem deixar de onde
# recuperar: o `PUT` audita nome, tipo e unidades, e o custo nao estava na lista.
with get_cursor() as cur:
    cur.execute("""SELECT antes FROM auditoria
                    WHERE acao = 'troca_de_unidade' AND id_entidade = %s
                    ORDER BY id DESC LIMIT 1""", (str(farinha),))
    aud = cur.fetchone()
checar("e o custo de antes ficou gravado na auditoria",
       aud and perto((aud["antes"] or {}).get("custo_referencia"), 8), aud and aud["antes"])


print("\n5. produto COM razão não troca de unidade — e o motivo é dito")
# ⚠️ **`estoque_movimentos` é append-only.** As quantidades históricas estão
# gravadas na unidade antiga e não há como reescrevê-las: converter só o cadastro
# deixaria o saldo dizendo "10" numa unidade e o histórico "10" noutra.
com_razao = criar("ITEM COM MOVIMENTO", "CX")
st, r = chamar("POST", "/ajustes/estoque", {
    "id_produto": com_razao, "quantidade_certa": 5, "id_local": local["id"],
    "observacao": f"cenario {marca}"}, token=token)
checar("o produto ganha um movimento no razão", st == 201, (st, r))

st, r = chamar("PUT", f"/produtos/{com_razao}",
               {"um_estoque": "UN", "um_compra": "CX", "fator_compra": 12}, token=token)
checar("a troca é RECUSADA", st == 400, (st, r))
checar("dizendo que há movimento gravado na unidade antiga",
       "movimento" in (r.get("detail") or "").lower(), r.get("detail"))
d = campos_de(com_razao, ["um_estoque"])
checar("e a unidade continua CX", d["um_estoque"] == "CX", d)


print("\n6. PUT que não mexe na unidade continua passando")
# ⚠️ A avaliação roda em TODO PUT. Se ela cobrasse fator de quem não trocou
# nada, salvar o nome de um produto viraria 400 — o tipo de regressão que fecha
# a tela inteira.
st, r = chamar("PUT", f"/produtos/{farinha}", {"nome": f"FARINHA RENOMEADA {marca}"},
               token=token)
checar("salvar só o nome não pede fator nenhum", st == 200, (st, r))


for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
