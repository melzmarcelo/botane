"""Códigos do produto: o vazio, o EAN preso num arquivado e o rótulo do vínculo.

🔑 **Três achados de 23/10/2026, todos do ar:**
1. Salvar um produto com código de barras VAZIO dava 500 (`ux_produto_barras`): o
   primeiro "" gravado passava, o segundo colidia. O conector manda "".
2. "Criar produto" num item de nota cujo EAN é de um cadastro ARQUIVADO dava 500: a
   busca por EAN não olha arquivado, mas o índice único olha.
3. O PÃO BOTANE aparecia em Vinculados como "COSTELA PONTA DESOSSADA KG" — o rótulo
   que o Omie mandou na nota em que se vinculou, sem como corrigir.

    python tests/smoke_codigos_do_produto.py      (API de pé; BOTANE_API muda a porta)
"""

import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402
from comum import garantir_cozinha  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
CODIGO = f"K{marca}"
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


def ean13() -> str:
    """Um EAN-13 válido (dígito verificador certo) que ninguém usa."""
    corpo = "29" + "".join(random.choice("0123456789") for _ in range(10))
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(corpo))
    return corpo + str((10 - soma % 10) % 10)


def novo_produto(nome, **extra):
    st, r = chamar("POST", "/produtos", {
        "nome": f"{nome} {marca}", "tipo": "INSUMO", "um_estoque": "UN",
        "status": "ATIVO", "controla_estoque": True, **extra,
    }, token)
    if r and r.get("id"):
        produtos.append(r["id"])
    return st, (r or {}).get("id")


def nota_com(id_fornecedor, descricao, data, ean=None):
    """Nota digitada de um item, com o código do fornecedor (e, se vier, o EAN)."""
    _st, r = chamar("POST", "/notas", {
        "id_fornecedor": id_fornecedor, "numero": uuid.uuid4().hex[:8].upper(),
        "serie": "1", "data_emissao": data,
        "itens": [{"descricao": descricao, "codigo_fornecedor": CODIGO,
                   "quantidade": 2, "valor_unitario": 5, "um": "UN"}],
    }, token)
    id_nota = (r or {}).get("id")
    if id_nota:
        notas.append(id_nota)
    _st, n = chamar("GET", f"/notas/{id_nota}", token=token)
    item = (n.get("itens") or [{}])[0]
    if ean and item.get("id"):
        # ⚠️ A nota digitada não tem campo de EAN; a do Omie traz. Planta-se direto.
        with get_cursor() as cur:
            cur.execute("UPDATE nota_itens SET codigo_barras = %s WHERE id = %s",
                        (ean, item["id"]))
    return item


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, f = chamar("POST", "/fornecedores", {"nome": f"Panificadora {marca}", "fornecedor": True},
                token)
forn = (f or {}).get("id")
if forn:
    pessoas.append(forn)

print("\n1. código único em branco vira nulo, não colisão")
_st, a = novo_produto("Vazio A", codigo_barras="", codigo_pdv="  ")
st, b = novo_produto("Vazio B", codigo_barras="", codigo_pdv="")
checar("dois produtos CRIADOS com códigos em branco", bool(a) and st == 201 and bool(b), st)
st, r = chamar("PUT", f"/produtos/{a}", {"codigo_barras": "", "codigo_omie": ""}, token)
checar("salvar um com o código de barras vazio passa", st == 200, (st, r))
st, r = chamar("PUT", f"/produtos/{b}", {"codigo_barras": "   "}, token)
checar("e o segundo também — antes era 500 (ux_produto_barras)", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("""SELECT count(*) AS n FROM produtos WHERE id = ANY(%s)
                     AND (codigo_barras = '' OR codigo_pdv = '' OR codigo_omie = '')""",
                ([a, b],))
    checar("nenhum dos dois guardou texto vazio", cur.fetchone()["n"] == 0)
ean_ok = ean13()
st, r = chamar("PUT", f"/produtos/{a}", {"codigo_barras": f"  {ean_ok} "}, token)
_st, pa = chamar("GET", f"/produtos/{a}", token=token)
checar("código de verdade continua gravando (sem os espaços)",
       st == 200 and pa.get("codigo_barras") == ean_ok, (st, pa.get("codigo_barras")))
st, r = chamar("PUT", f"/produtos/{b}", {"codigo_barras": ean_ok}, token)
checar("e o repetido ainda é recusado com frase (409)", st == 409, (st, r))

print("\n2. criar produto do item com EAN de cadastro ARQUIVADO")
ean_arq = ean13()
_st, arquivado = novo_produto("Oleo Arquivado", codigo_barras=ean_arq)
with get_cursor() as cur:
    cur.execute("UPDATE produtos SET ativo = false, status = 'ARQUIVADO' WHERE id = %s",
                (arquivado,))
it = nota_com(forn, f"OLEO SOJA 900ML {marca}", "2026-10-20", ean=ean_arq)
st, r = chamar("POST", f"/notas/itens/{it['id']}/criar-produto", {}, token)
checar("responde 409, não 500", st == 409, (st, r))
checar("e nomeia o cadastro arquivado", f"Oleo Arquivado {marca}".upper()
       in (r.get("detail") or "").upper(), r.get("detail"))
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM produtos WHERE codigo_barras = %s", (ean_arq,))
    checar("e nenhum segundo cadastro nasce", cur.fetchone()["n"] == 1)
# Reativado, o mesmo botão vincula a ele — o caminho que a frase ensina.
with get_cursor() as cur:
    cur.execute("UPDATE produtos SET ativo = true, status = 'ATIVO' WHERE id = %s",
                (arquivado,))
st, r = chamar("POST", f"/notas/itens/{it['id']}/criar-produto", {}, token)
checar("reativado, o item se vincula a ele", st == 200 and r.get("id_produto") == arquivado,
       (st, r))

ean_fus = ean13()
_st, principal = novo_produto("Oleo Principal")
_st, absorvido = novo_produto("Oleo Absorvido", codigo_barras=ean_fus)
with get_cursor() as cur:
    cur.execute("""UPDATE produtos SET ativo = false, status = 'ARQUIVADO', fundido_em = %s
                    WHERE id = %s""", (principal, absorvido))
it2 = nota_com(forn, f"OLEO SOJA FUSAO {marca}", "2026-10-20", ean=ean_fus)
st, r = chamar("POST", f"/notas/itens/{it2['id']}/criar-produto", {"substituir": True}, token)
checar("absorvido de fusão leva ao PRINCIPAL", st == 200 and r.get("id_produto") == principal,
       (st, r))

print("\n3. o rótulo do vínculo: a nota mais nova e a correção à mão")
it3 = nota_com(forn, f"COSTELA PONTA DESOSSADA KG {marca}", "2026-10-13")
_st, pao = novo_produto("Pao Teste")
st, r = chamar("POST", f"/notas/itens/{it3['id']}/vincular",
               {"id_produto": pao, "aprender": True}, token)
checar("o item de rótulo errado é vinculado ao pão", st == 200, (st, r))
nota_com(forn, f"Pao Teste {marca}", "2026-10-20")


def linha_do_codigo():
    _st, p = chamar("GET", f"/produtos/{pao}", token=token)
    return next((c for c in p.get("codigos_externos") or [] if c["codigo"] == CODIGO), {})


c = linha_do_codigo()
checar("Vinculados mostra o rótulo gravado no vínculo",
       (c.get("descricao_externa") or "").startswith("COSTELA"), c)
checar("e ao lado o que a nota mais nova diz",
       (c.get("descricao_recente") or "").upper().startswith("PAO TESTE")
       and str(c.get("descricao_recente_em")) == "2026-10-20", c)
corpo = {"sistema": "OMIE", "codigo": CODIGO, "id_fornecedor": forn,
         "descricao": "  Pao Botane  "}
st, r = chamar("PUT", f"/produtos/{pao}/codigos/descricao", corpo, token)
checar("corrigir a descrição é aceito", st == 200, (st, r))
c = linha_do_codigo()
checar("e o rótulo passa a ser o corrigido (sem espaços)",
       c.get("descricao_externa") == "Pao Botane", c)
checar("sem mexer no produto do código nem no fator",
       float(c.get("fator") or 0) == 1.0 and not c.get("fator_confirmado"), c)
st, r = chamar("PUT", f"/produtos/{principal}/codigos/descricao", corpo, token)
checar("pelo cadastro errado devolve 404", st == 404, (st, r))
st, r = chamar("PUT", f"/produtos/{pao}/codigos/descricao", {**corpo, "descricao": " "}, token)
checar("descrição em branco é recusada (422)", st == 422, st)
with get_cursor() as cur:
    cur.execute("""SELECT 1 FROM auditoria WHERE entidade = 'produto'
                     AND id_entidade::text = %s AND acao = 'descricao_codigo'""", (str(pao),))
    checar("a correção fica na auditoria", cur.fetchone() is not None)
_cozinha = garantir_cozinha(chamar, token)
st, r = chamar("PUT", f"/produtos/{pao}/codigos/descricao", corpo, _cozinha)
checar("a cozinha não corrige (403)", st == 403, st)

print("\n4. limpeza")
for nid in reversed(notas):
    chamar("POST", f"/notas/{nid}/estornar", {}, token)
    chamar("DELETE", f"/notas/{nid}", token=token)
with get_cursor() as cur:
    cur.execute("DELETE FROM codigos_externos WHERE codigo = %s", (CODIGO,))
    # ⚠️ O EAN plantado sai do cadastro: o índice é único e o desativar não o solta.
    cur.execute("UPDATE produtos SET codigo_barras = NULL WHERE id = ANY(%s)", (produtos,))
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)
for sid in pessoas:
    chamar("DELETE", f"/fornecedores/{sid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
