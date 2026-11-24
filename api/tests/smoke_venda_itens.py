"""Editar a quantidade e excluir itens de documento lançado à mão e em aberto (24/11/2026).

O que este arquivo cobra:

1. o detalhe diz se as linhas podem mudar (`pode_mudar_itens`) e por que não
2. mudar a quantidade ajusta a linha, o total da venda e **refaz a baixa de estoque** pelo
   total novo — por estorno, nunca por cima (regra 1)
3. no produto feito NA HORA, a produção que a venda disparou é refeita junto: o insumo
   volta na proporção certa
4. excluir tira a linha, o valor e devolve o estoque; a última linha não sai (409)
5. documento da planilha, do PDV ou cancelado: 409 com a frase do porquê
6. item de outra venda: 404

    python tests/smoke_venda_itens.py      (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
from comum import garantir_locais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def igual(a, b):
    return a is not None and abs(float(a) - float(b)) < 0.0001


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today().isoformat()

print("0. preparo: revenda com saldo, e um prato feito na hora com ficha")
garantir_locais(chamar, token)
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])


def produto(sufixo, **extra):
    s, p = chamar("POST", "/produtos", {"codigo": f"VI-{sufixo}-{marca}",
                                        "nome": f"Item editar {sufixo} {marca}",
                                        "um_estoque": "UN", "controla_estoque": True,
                                        "status": "ATIVO", **extra}, token=token)
    checar(f"produto {sufixo} nasce", s == 201, (s, p))
    return p["id"]


refri = produto("REF", tipo="REVENDA")
insumo = produto("INS", tipo="INSUMO", um_estoque="KG")
prato = produto("PRT", tipo="PRODUZIDO", producao_propria=True, modo_producao="NA_HORA")
for pid, q in ((refri, 10), (insumo, 10)):
    s, _ = chamar("POST", "/estoque/entradas", {"id_produto": pid, "quantidade": q,
                                               "custo_unitario": 2, "id_local": principal["id"],
                                               "documento": f"VI-{marca}"}, token=token)
s, f = chamar("POST", "/fichas", {"id_produto": prato, "rendimento_qtd": 1, "rendimento_um": "UN",
                                  "porcoes": 1,
                                  "itens": [{"id_insumo": insumo, "qtd_bruta": 0.5, "um": "KG"}]},
              token=token)
chamar("POST", f"/fichas/{f['id']}/homologar", token=token)


def saldo(pid):
    _s, d = chamar("GET", f"/estoque/saldos?busca=VI-&limite=200", token=token)
    return sum(float(x["quantidade"]) for x in (d or []) if x.get("id_produto") == pid)


def lancar(documento, origem="MANUAL", itens=None):
    s, r = chamar("POST", "/vendas/importar", {"vendas": [{
        "data": hoje, "hora": "15:00:00", "documento": documento, "origem": origem,
        "itens": itens or [{"id_produto": refri, "quantidade": 3, "valor_unitario": 5},
                           {"id_produto": prato, "quantidade": 2, "valor_unitario": 20}]}]},
        token=token)
    _s, l = chamar("GET", f"/vendas?busca={documento}&limite=5", token=token)
    lista = l["itens"] if isinstance(l, dict) and "itens" in l else (l or [])
    return next((v["id"] for v in lista if v.get("documento") == documento), None)


refri0, insumo0 = saldo(refri), saldo(insumo)
id_venda = lancar(f"VI-{marca}")
_s, det = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("o documento à mão em aberto pode mudar os itens", det.get("pode_mudar_itens") is True, det)
linha_refri = next(i for i in det["itens"] if i["id_produto"] == refri)
linha_prato = next(i for i in det["itens"] if i["id_produto"] == prato)
checar("vender tirou 3 refrigerantes e 1 kg de insumo (2 pratos × 0,5)",
       igual(saldo(refri), refri0 - 3) and igual(saldo(insumo), insumo0 - 1),
       (saldo(refri), saldo(insumo)))

print("1. mudar a quantidade")
s, r = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_refri['id']}", {"quantidade": 1}, token=token)
checar("3 → 1 aceito", s == 200, (s, r))
_s, det = chamar("GET", f"/vendas/{id_venda}", token=token)
l = next(i for i in det["itens"] if i["id"] == linha_refri["id"])
checar("a linha vale 1 × 5", igual(l["quantidade"], 1) and igual(l["valor_total"], 5), l)
checar("o total da venda caiu 10 (55 → 45)", igual(det["valor_total"], 45), det["valor_total"])
checar("e 2 refrigerantes voltaram ao estoque", igual(saldo(refri), refri0 - 1), saldo(refri))
estornos = [m for m in det["movimentos"] if m["id_estorno_de"]]
checar("pela forma do razão: houve estorno, não UPDATE", len(estornos) >= 1, det["movimentos"])

s, r = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_prato['id']}", {"quantidade": 1}, token=token)
checar("prato 2 → 1 aceito", s == 200, (s, r))
checar("o insumo da produção na hora voltou meio quilo", igual(saldo(insumo), insumo0 - 0.5),
       saldo(insumo))
s, r = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_prato['id']}", {"quantidade": 4}, token=token)
checar("e subir para 4 consome 2 kg", s == 200 and igual(saldo(insumo), insumo0 - 2), saldo(insumo))
s, _ = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_prato['id']}", {"quantidade": 0}, token=token)
checar("quantidade zero: 422 (para tirar, exclua)", s == 422, s)

print("2. excluir")
s, r = chamar("DELETE", f"/vendas/{id_venda}/itens/{linha_prato['id']}", token=token)
checar("excluir o prato", s == 200, (s, r))
_s, det = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("sai da venda, e o total fica só o refrigerante (5)",
       len(det["itens"]) == 1 and igual(det["valor_total"], 5), det["itens"])
checar("o insumo voltou inteiro", igual(saldo(insumo), insumo0), saldo(insumo))
s, r = chamar("DELETE", f"/vendas/{id_venda}/itens/{linha_refri['id']}", token=token)
checar("a última linha não sai: 409 mandando cancelar", s == 409 and "cancele" in r["detail"], (s, r))
s, _ = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_prato['id']}", {"quantidade": 1}, token=token)
checar("item que já não está na venda: 404", s == 404, s)

print("3. o que não muda")
id_planilha = lancar(f"VIP-{marca}", origem="PLANILHA")
_s, det = chamar("GET", f"/vendas/{id_planilha}", token=token)
checar("documento da planilha não muda os itens, e o detalhe diz por quê",
       det.get("pode_mudar_itens") is False and "planilha" in (det.get("por_que_nao_muda_itens") or ""),
       det.get("por_que_nao_muda_itens"))
s, r = chamar("PUT", f"/vendas/{id_planilha}/itens/{det['itens'][0]['id']}", {"quantidade": 1}, token=token)
checar("e a rota recusa: 409", s == 409, (s, r))
chamar("DELETE", f"/vendas/{id_planilha}", token=token)

chamar("DELETE", f"/vendas/{id_venda}", token=token)
_s, det = chamar("GET", f"/vendas/{id_venda}", token=token)
checar("cancelada, não muda mais", det.get("pode_mudar_itens") is False, det.get("por_que_nao_muda_itens"))
s, _ = chamar("PUT", f"/vendas/{id_venda}/itens/{linha_refri['id']}", {"quantidade": 2}, token=token)
checar("e a rota recusa: 409", s == 409, s)
checar("o cancelamento devolveu o último refrigerante", igual(saldo(refri), refri0), saldo(refri))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
