"""Teste de fumaça: o relatório "Fichas técnicas" — a lista das fichas, uma por linha.

🔑 Pedido do dono (26/10/2026): *"um relatório para listar todas as fichas técnicas,
em linhas, contendo a situação"*. Confere:

    1. Cenário: um insumo com custo, um prato com ficha homologada e uma v2 em
       rascunho, um rascunho com insumo sem custo e um produzido sem ficha.
    2. Uma linha por produto, a versão que VALE; a homologada avisa da v2.
    3. O rascunho diz que falta homologar e que há ingrediente sem custo.
    4. O produzido sem ficha é linha, "criar a ficha".
    5. Todas as versões: a v2 aparece; o filtro de situação recorta.
    6. Custo só para quem tem `fichas.custos` — a cozinha não vê a coluna.
    7. PDF sai.

⚠️ Isolado pela MARCA na busca: a base local tem centenas de fichas de verdade.

    python tests/smoke_relatorio_fichas.py      (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]


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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def csv(caminho: str, tk=None) -> tuple[int, list[list[str]]]:
    st, bruto = chamar("GET", caminho, token=tk or token, cru=True)
    if st != 200 or not isinstance(bruto, bytes):
        return st, []
    return st, [l.split(";") for l in bruto.decode("utf-8-sig").splitlines()]


def cabecalho(linhas):
    return next((l for l in linhas if "Produto" in l and "Situação" in l), [])


def linhas_de(linhas, trecho):
    return [l for l in linhas if any(trecho in c for c in l) and "Situação" not in l]


def campo(linhas, linha, nome):
    cab = cabecalho(linhas)
    return linha[cab.index(nome)] if nome in cab and len(linha) == len(cab) else None


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
local = garantir_local(chamar, token)
produtos = []

print("1. cenário")


def produto(nome, tipo, **extra):
    st, p = chamar("POST", "/produtos", {"nome": f"{nome} RF{marca}", "tipo": tipo,
                                         "um_estoque": "UN", "status": "ATIVO", **extra},
                   token=token)
    produtos.append((p or {}).get("id"))
    return (p or {}).get("id")


insumo = produto("INSUMO", "INSUMO")
st, r = chamar("POST", "/estoque/entradas", {"id_produto": insumo, "quantidade": 10,
                                             "custo_unitario": 3, "id_local": local["id"],
                                             "documento": f"NF-RF-{marca}"}, token=token)
checar("o insumo entra a R$ 3", st in (200, 201), (st, r))
sem_custo = produto("INSUMO SEM CUSTO", "INSUMO")
prato = produto("PRATO", "PRODUZIDO", producao_propria=True, controla_estoque=False)
rascunho = produto("RASCUNHO", "PRODUZIDO", producao_propria=True, controla_estoque=False)
sem_ficha = produto("SEM FICHA", "PRODUZIDO", producao_propria=True, controla_estoque=False)
checar("os produtos nascem", all(produtos), produtos)

st, f = chamar("POST", "/fichas", {"id_produto": prato, "rendimento_qtd": 1,
                                   "rendimento_um": "UN", "porcoes": 2,
                                   "itens": [{"id_insumo": insumo, "qtd_bruta": 2, "um": "UN"}]},
               token=token)
ficha_prato = (f or {}).get("id")
st, _ = chamar("POST", f"/fichas/{ficha_prato}/homologar", {}, token=token)
checar("a ficha do prato é homologada", st == 200, st)
st, v2 = chamar("POST", f"/fichas/{ficha_prato}/nova-versao", token=token)
checar("e ganha uma v2 em rascunho", st == 201, (st, v2))
st, f = chamar("POST", "/fichas", {"id_produto": rascunho, "rendimento_qtd": 1,
                                   "rendimento_um": "UN", "porcoes": 1,
                                   "itens": [{"id_insumo": sem_custo, "qtd_bruta": 1,
                                              "um": "UN"}]}, token=token)
checar("o rascunho nasce", st == 201, (st, f))

print("\n2-4. uma linha por produto, a versão que vale")
st, ls = csv(f"/exportar/fichas.csv?busca=RF{marca}")
checar("o CSV sai", st == 200, st)
lp = linhas_de(ls, f"PRATO RF{marca}")
checar("o prato é UMA linha", len(lp) == 1, lp)
if lp:
    checar("é a v1 de 2, homologada", campo(ls, lp[0], "Versão") == "v1 de 2"
           and campo(ls, lp[0], "Situação") == "homologada", lp[0])
    checar("e avisa da v2 em rascunho", "v2 em rascunho" in (campo(ls, lp[0], "O que falta") or ""),
           lp[0])
    checar("custo 2 × R$ 3 = R$ 6, R$ 3 por porção",
           campo(ls, lp[0], "Custo total") == "6,00"
           and campo(ls, lp[0], "Custo/porção") == "3,00", lp[0])
lr = linhas_de(ls, f"RASCUNHO RF{marca}")
falta = (campo(ls, lr[0], "O que falta") or "") if lr else ""
checar("o rascunho pede homologar e acusa o ingrediente sem custo",
       "homologar" in falta and "sem custo" in falta, lr)
ls_ = linhas_de(ls, f"SEM FICHA RF{marca}")
checar("o produzido sem ficha é linha: 'criar a ficha'",
       len(ls_) == 1 and campo(ls, ls_[0], "Situação") == "sem ficha"
       and campo(ls, ls_[0], "O que falta") == "criar a ficha", ls_)
checar("o insumo não entra (não é produzido)", not linhas_de(ls, f"INSUMO RF{marca}"))

print("\n5. todas as versões e o filtro de situação")
st, ls = csv(f"/exportar/fichas.csv?busca=RF{marca}&versoes_ficha=todas")
lp = linhas_de(ls, f"PRATO RF{marca}")
checar("todas as versões: o prato vira duas linhas",
       sorted(campo(ls, l, "Situação") or "" for l in lp) == ["homologada", "rascunho"], lp)
st, ls = csv(f"/exportar/fichas.csv?busca=RF{marca}&situacao_ficha=SEM_FICHA")
checar("só sem ficha: uma linha", len(linhas_de(ls, f"RF{marca}")) == 1,
       linhas_de(ls, f"RF{marca}"))
st, pv = chamar("GET", f"/exportar/fichas/previa?busca=RF{marca}", token=token)
checar("a prévia conta as linhas", st == 200 and pv.get("linhas", 0) >= 3, (st, pv))

print("\n6. custo só para quem tem fichas.custos")
tk_coz = garantir_cozinha(chamar, token)
st, ls = csv(f"/exportar/fichas.csv?busca=RF{marca}", tk=tk_coz)
checar("a cozinha baixa a lista", st == 200 and linhas_de(ls, f"PRATO RF{marca}"), st)
checar("sem a coluna de custo", "Custo total" not in cabecalho(ls) and cabecalho(ls), cabecalho(ls))

print("\n7. PDF")
st, pdf = chamar("GET", f"/exportar/fichas.pdf?busca=RF{marca}", token=token, cru=True)
checar("o PDF sai", st == 200 and isinstance(pdf, bytes) and pdf[:4] == b"%PDF", st)

for idp in produtos:
    if idp:
        chamar("DELETE", f"/produtos/{idp}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
