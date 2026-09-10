"""Os produtos que uma pessoa fornece, na ficha dela.

🔑 **Pedido do dono (09/09/2026):** *"no cadastro de pessoas, criar um grupo dos
produtos que a pessoa/fornecedor está vinculado"*.

A ficha já dizia **quantos** (`12 produto(s)`), e o número sozinho não responde a
pergunta que se faz olhando para ela: *o que a gente compra deste aqui?* — para
descobrir, era preciso ir à lista de produtos e filtrar um por um.

⚠️ **O vínculo NASCE do lançamento da nota**, não de um cadastro à mão. Por isso
esta suíte lança uma nota de verdade: testar contra uma linha inserida por SQL
provaria que a consulta lê a tabela, não que a tela mostra o que o sistema
produz.

    python tests/smoke_produtos_da_pessoa.py        (API de pé na 9200)
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


def perto(a, b, casas=2):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


def vinculos(id_pessoa):
    _st, r = chamar("GET", f"/fornecedores/{id_pessoa}/produtos", token=token)
    return r if isinstance(r, list) else []


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
init_pool()
local = garantir_local(chamar, token)
pessoa = garantir_fornecedor(chamar, token, f"DISTRIBUIDORA {marca}", "44555666000177")


print("\n1. a pessoa nova nao fornece nada, e a resposta DIZ isso")
st, r = chamar("GET", f"/fornecedores/{pessoa}/produtos", token=token)
checar("a rota responde", st == 200, (st, r))
checar("com uma lista vazia, nao um erro", r == [], r)


print("\n2. o vinculo NASCE do lancamento da nota")
_st, p = chamar("POST", "/produtos", {
    "codigo": f"PDP-{marca}", "nome": f"CAFE DA PESSOA {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "status": "ATIVO", "id_local_padrao": local["id"]}, token=token)
produto = p.get("id")
if produto:
    criados.append(produto)
checar("o produto nasce", bool(produto), (_st, p))

st, nota = chamar("POST", "/notas", {
    "id_fornecedor": pessoa, "numero": f"PD{marca}", "serie": "1",
    "data_emissao": "2026-09-09", "id_local": local["id"],
    "itens": [{"id_produto": produto, "quantidade": 4, "um": "KG",
               "valor_unitario": 12.50, "codigo_fornecedor": f"F-{marca}"}],
}, token=token)
id_nota = nota.get("id")
if id_nota:
    notas.append(id_nota)
checar("a nota entra", st == 200 and id_nota, (st, nota))

st, r = chamar("POST", f"/notas/{id_nota}/lancar", {"id_local": local["id"]}, token=token)
checar("e lanca no estoque", st == 200, (st, r))

lista = vinculos(pessoa)
checar("agora a pessoa tem UM produto", len(lista) == 1, lista)
linha = (lista or [{}])[0]
checar("e e o produto certo", linha.get("id") == produto, linha)
checar("com o nome dele", f"CAFE DA PESSOA {marca}" in (linha.get("nome") or "").upper(), linha)


print("\n3. o que a linha precisa dizer para ser util")
# 🔑 **O preco e POR UNIDADE DE ESTOQUE**, nunca por embalagem -- e o mesmo
# numero que a cascata de custo le como segundo degrau. 4 KG a 12,50 = 50,00, e
# o preco por KG e 12,50.
checar("o ultimo preco vem, por unidade de estoque",
       perto(linha.get("ultimo_preco"), 12.50), linha.get("ultimo_preco"))
checar("com a unidade ao lado, para a conta fechar",
       (linha.get("um_estoque") or "").upper() == "KG", linha.get("um_estoque"))
# ⚠️ Sem a DATA, "R$ 12,50" nao diz se e de ontem ou de 2024 -- e preco de
# insumo de dois anos atras nao serve para decidir nada.
checar("e a data da ultima compra", bool(linha.get("ultima_compra")), linha)
# ⚠️ **O lancamento da nota NAO grava `codigo_no_fornecedor`** -- ele so escreve
# preco e data. O codigo se registra na aba de fornecedores do produto (ou
# quando o produto NASCE de um item de nota, em `criar_produto_do_item`). Esta
# suite afirma o que o sistema faz, nao o que seria bom que fizesse: ela grava
# pelo caminho de quem usa e confere que a coluna aparece.
checar("recem-lancada, a linha ainda nao tem o codigo do fornecedor",
       not linha.get("codigo_no_fornecedor"), linha.get("codigo_no_fornecedor"))

st, r = chamar("PUT", f"/produtos/{produto}", {"fornecedores": [
    {"id_fornecedor": pessoa, "codigo_no_fornecedor": f"F-{marca}",
     "embalagem": "SC", "fator": 1, "preferencial": True}]}, token=token)
checar("a aba de fornecedores do produto grava o codigo", st == 200, (st, r))

linha = (vinculos(pessoa) or [{}])[0]
# 🔑 O codigo do fornecedor e o nivel 4 da cascata de conciliacao: e ele que
# liga a PROXIMA nota dele a este produto, sem EAN e sem ninguem escolher.
checar("e ele passa a aparecer na ficha da pessoa",
       (linha.get("codigo_no_fornecedor") or "") == f"F-{marca}",
       linha.get("codigo_no_fornecedor"))
# ⚠️ **A gravacao do codigo NAO pode apagar o preco.** As duas informacoes vem
# de caminhos diferentes -- o preco do lancamento, o codigo da tela -- e a linha
# so e util com as duas juntas.
checar("sem perder o preco que veio do lancamento",
       perto(linha.get("ultimo_preco"), 12.50), linha.get("ultimo_preco"))
checar("nem a data da ultima compra", bool(linha.get("ultima_compra")), linha)


print("\n4. o produto INATIVO sai da lista")
# 🔑 **Decisao do dono (09/09/2026): "lista somente os ativos".** A primeira
# versao trazia o arquivado marcado, com o argumento de que ele explica a nota
# antiga; na base real isso encheu o cartao de cadastro morto e afogou o que a
# pessoa fornece HOJE, que e a pergunta da ficha. O vinculo continua existindo e
# aparece na ficha do PRODUTO.
chamar("PUT", f"/produtos/{produto}", {"ativo": False}, token=token)
lista = vinculos(pessoa)
checar("desativar o produto o tira da ficha da pessoa", lista == [], lista)
chamar("PUT", f"/produtos/{produto}", {"ativo": True}, token=token)
checar("e reativar o traz de volta", len(vinculos(pessoa)) == 1, vinculos(pessoa))


print("\n5. o que o servidor recusa")
st, r = chamar("GET", "/fornecedores/99999999/produtos", token=token)
checar("pessoa inexistente e 404", st == 404, (st, r))
checar("com a frase dizendo o que nao achou",
       "encontrada" in str(r.get("detail", "")).lower(), r)

st, r = chamar("GET", f"/fornecedores/{pessoa}/produtos")
checar("sem autenticacao e barrado", st in (401, 403), st)


print("\n6. limpando o que a suite criou")
for nid in notas:
    chamar("POST", f"/notas/{nid}/estornar", {}, token=token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM produto_fornecedor WHERE id_fornecedor = %s", (pessoa,))
for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)
# ⚠️ **Nada de DELETE cru no produto.** Ele tem movimentos no razao -- a entrada
# da nota e o estorno dela --, e `estoque_movimentos` tem chave estrangeira para
# `produtos`: o apagar direto estourava a limpeza com ForeignKeyViolation e
# deixava a pessoa de teste para tras. O razao e append-only por decisao do
# projeto; o cadastro fica inativo, que e o que o proprio sistema faz.
with get_cursor() as cur:
    cur.execute("DELETE FROM produto_fornecedor WHERE id_fornecedor = %s", (pessoa,))
    cur.execute("UPDATE produtos SET ativo = false, status = 'ARQUIVADO' WHERE id = ANY(%s)",
                (criados,))
    cur.execute("UPDATE fornecedores SET ativo = false WHERE id = %s", (pessoa,))
checar("a limpeza roda sem violar o razao", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
