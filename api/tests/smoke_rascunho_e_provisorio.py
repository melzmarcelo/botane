"""Rascunho se exclui, e o custo que a ficha prevê aparece antes de produzir.

🔑 **Dois pedidos do dono (13/09/2026):** *"caso a ficha esteja como rascunho,
permitir que ela seja excluida"* e *"caso a ficha nao tenha sido produzida, a
ficha esta sem custo, levar este custo provisorio para a tela do cadastro de
produto"*.

⚠️ **Arquivar existe para nao quebrar o passado** — ficha publicada apurou custo e
o historico aponta para ela. Rascunho nao tem passado: nunca homologou, nunca
produziu, nunca entrou em CMV. O que trava a exclusao e o dado, nao a vontade de
quem clica: sub-ficha em uso, producao registrada.

⚠️ **O provisorio e o que a FICHA preve com os precos de hoje**, nao o que a
producao vai apurar. Vem marcado, e nao entra na cascata de `custo_do_insumo`: la
ele alimentaria ficha de terceiros, CMV e margem de uma vez.

    python tests/smoke_rascunho_e_provisorio.py        (API de pe na 9200)
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
produtos: list[int] = []
fichas: list[int] = []


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


def perto(a, b, tol=0.01):
    return abs(float(a or 0) - float(b)) < tol


def novo(nome, tipo, um, **extra):
    _st, r = chamar("POST", "/produtos", {
        "nome": f"{nome} {marca}", "tipo": tipo, "um_estoque": um,
        "status": "ATIVO", "controla_estoque": True, **extra,
    }, token)
    if r.get("id"):
        produtos.append(r["id"])
    return r.get("id")


def ficha_de(id_produto, itens, rendimento=10):
    _st, f = chamar("POST", "/fichas", {
        "id_produto": id_produto, "rendimento_qtd": rendimento, "rendimento_um": "KG",
        "porcoes": 1, "itens": itens,
    }, token)
    if f.get("id"):
        fichas.append(f["id"])
    return f.get("id")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

print("\n1. o rascunho se exclui de verdade")
bolo = novo("Rasc bolo", "PRODUZIDO", "KG", producao_propria=True)
farinha = novo("Rasc farinha", "INSUMO", "KG")
chamar("POST", "/estoque/entradas",
       {"id_produto": farinha, "quantidade": 50, "custo_unitario": 4}, token)
f1 = ficha_de(bolo, [{"id_insumo": farinha, "qtd_bruta": 6, "um": "KG"}])
checar("a ficha nasce em rascunho", bool(f1))
st, r = chamar("DELETE", f"/fichas/{f1}", token=token)
checar("excluir rascunho responde 200", st == 200, (st, r))
checar("e a mensagem diz que EXCLUIU, nao que arquivou",
       "exclu" in (r.get("message") or "").lower(), r.get("message"))
st, _ = chamar("GET", f"/fichas/{f1}", token=token)
checar("a ficha nao existe mais", st == 404, st)
# ⚠️ Os itens somem por CASCADE — sao partes da receita, nao registros proprios.
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM ficha_itens WHERE id_ficha = %s", (f1,))
    checar("e os itens dela foram junto", cur.fetchone()["n"] == 0)

print("\n2. homologada continua sendo ARQUIVADA")
f2 = ficha_de(bolo, [{"id_insumo": farinha, "qtd_bruta": 6, "um": "KG"}])
chamar("POST", f"/fichas/{f2}/homologar", None, token)
st, r = chamar("DELETE", f"/fichas/{f2}", token=token)
checar("excluir homologada arquiva", st == 200
       and "arquiv" in (r.get("message") or "").lower(), (st, r))
st, d = chamar("GET", f"/fichas/{f2}", token=token)
checar("e ela continua consultavel, arquivada",
       st == 200 and d.get("status") == "ARQUIVADA", (st, d.get("status")))

print("\n3. o que TRAVA a exclusao do rascunho")
# Sub-ficha em uso: a FK e RESTRICT e o custo da outra quebraria.
base = novo("Rasc base", "PRODUZIDO", "KG", producao_propria=True)
f_base = ficha_de(base, [{"id_insumo": farinha, "qtd_bruta": 2, "um": "KG"}])
usa = novo("Rasc usa", "PRODUZIDO", "KG", producao_propria=True)
f_usa = ficha_de(usa, [{"id_subficha": f_base, "qtd_bruta": 1, "um": "KG"}])
st, r = chamar("DELETE", f"/fichas/{f_base}", token=token)
checar("rascunho usado como sub-ficha nao se exclui", st == 409, (st, r))
checar("dizendo onde esta o vinculo",
       "sub-ficha" in (r.get("detail") or "").lower(), r.get("detail"))
st, _ = chamar("GET", f"/fichas/{f_base}", token=token)
checar("e ele continua la", st == 200, st)

print("\n4. o custo que a ficha PREVE, antes de produzir")
# ⚠️ **Produto NOVO, com ficha propria.** A primeira versao deste bloco reusava o
# `bolo`, cuja unica ficha viva havia sido arquivada na secao 2 — e a checagem
# falhou acusando o recurso, quando "ficha arquivada nao responde por custo" e
# exatamente o comportamento certo.
pao = novo("Rasc pao", "PRODUZIDO", "KG", producao_propria=True)
ficha_de(pao, [{"id_insumo": farinha, "qtd_bruta": 6, "um": "KG"}])
# 6 KG de farinha a 4,00 = 24,00 para 10 KG de pao: 2,40 por KG.
st, c = chamar("GET", f"/produtos/{pao}/custo", token=token)
checar("a tela do produto responde", st == 200, st)
# ⚠️ O bolo nunca foi produzido: a cascata inteira nao sabe o custo.
checar("o custo apurado e NULO — nada foi produzido", c.get("atual") is None, c.get("atual"))
prov = c.get("provisorio") or {}
checar("mas vem o provisorio da ficha", bool(prov), c)
checar("com 2,40 por KG (24,00 de ingredientes para 10 KG)",
       perto(prov.get("custo"), 2.4, 0.001), prov)
checar("dizendo de qual ficha e versao veio",
       prov.get("id_ficha") is not None and prov.get("versao") is not None, prov)
checar("e que a receita esta completa", prov.get("completo") is True
       and prov.get("itens_sem_custo") == 0, prov)

print("\n5. ficha incompleta vem MARCADA, nao escondida")
# Item sem preco nenhum: o provisorio soma so parte da receita.
sem_preco = novo("Rasc sem preco", "INSUMO", "KG")
torta = novo("Rasc torta", "PRODUZIDO", "KG", producao_propria=True)
ficha_de(torta, [
    {"id_insumo": farinha, "qtd_bruta": 5, "um": "KG"},
    {"id_insumo": sem_preco, "qtd_bruta": 1, "um": "KG"},
])
st, c2 = chamar("GET", f"/produtos/{torta}/custo", token=token)
prov2 = c2.get("provisorio") or {}
checar("o provisorio existe mesmo incompleto", bool(prov2), c2)
checar("e se declara incompleto, com quantos itens faltam",
       prov2.get("completo") is False and prov2.get("itens_sem_custo") == 1, prov2)

print("\n6. com custo apurado, o provisorio NAO aparece")
# Dois numeros para a mesma pergunta e pior que um numero so.
st, r = chamar("POST", "/estoque/entradas",
               {"id_produto": pao, "quantidade": 3, "custo_unitario": 9}, token)
checar("o pao ganha uma entrada no razao", st == 201, (st, r))
st, c3 = chamar("GET", f"/produtos/{pao}/custo", token=token)
checar("agora o custo apurado responde", perto(c3.get("atual"), 9), c3.get("atual"))
checar("e o provisorio sai de cena", c3.get("provisorio") is None, c3.get("provisorio"))

print("\n7. produto SEM ficha nao inventa provisorio")
insumo = novo("Rasc insumo puro", "INSUMO", "KG")
st, c4 = chamar("GET", f"/produtos/{insumo}/custo", token=token)
checar("sem ficha, sem provisorio", c4.get("provisorio") is None, c4.get("provisorio"))

print("\n8. limpeza")
for fid in reversed([x for x in fichas if x]):
    chamar("DELETE", f"/fichas/{fid}", token=token)
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
