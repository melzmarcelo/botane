"""O filtro "vende no PDV" do cadastro de produtos (pedido do dono, 10/11/2026).

🔑 A regra é a da aba PDV da ficha: vende no PDV quem está MARCADO para o PDV
(`integrado_pdv`) OU tem o código de lá (`codigo_pdv`) — o produto que veio do PDV e
a casa não quer que o Botané mexa continua sendo vendido no balcão. Confere:

    1. a lista (`GET /produtos?no_pdv=`): marcado e com código entram em "sim"; o
       sem nenhum dos dois, em "não"; sem o filtro, os três;
    2. o relatório "Cadastro de produtos" com o mesmo recorte (`pdv_produto`).

    python tests/smoke_produtos_pdv.py      (API de pé na 9200)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from database import get_cursor, init_pool  # noqa: E402

BASE = os.environ.get("API_URL", "http://127.0.0.1:9200")
ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def main():
    init_pool()
    st, r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
    token = r["access_token"]
    nomes = {"marcado": f"PDVTESTE MARCADO {marca}", "codigo": f"PDVTESTE CODIGO {marca}",
             "nenhum": f"PDVTESTE NENHUM {marca}"}
    ids = []
    with get_cursor() as cur:
        for chave, nome in nomes.items():
            cur.execute(
                """INSERT INTO produtos (codigo, nome, tipo, um_estoque, status,
                                         integrado_pdv, codigo_pdv)
                   VALUES (%s, %s, 'REVENDA', 'UN', 'ATIVO', %s, %s) RETURNING id""",
                (f"PDVT{marca}{chave[0]}", nome, chave == "marcado",
                 f"PDVT{marca}" if chave == "codigo" else None))
            ids.append(cur.fetchone()["id"])
    try:
        print("1. a lista")
        def nomes_de(filtro):
            st, lst = chamar("GET", f"/produtos?busca=PDVTESTE&limite=50{filtro}", token=token)
            return {p["nome"] for p in lst if marca in p["nome"]}
        checar("sem filtro: os três", nomes_de("") == set(nomes.values()), nomes_de(""))
        checar("vende no PDV: o marcado e o que só tem o código",
               nomes_de("&no_pdv=true") == {nomes["marcado"], nomes["codigo"]}, nomes_de("&no_pdv=true"))
        checar("não vende no PDV: só o sem nenhum dos dois",
               nomes_de("&no_pdv=false") == {nomes["nenhum"]}, nomes_de("&no_pdv=false"))

        print("\n2. o relatório")
        def no_relatorio(filtro):
            req = urllib.request.Request(f"{BASE}/exportar/produtos/dados?{filtro}")
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            i = [c["chave"] for c in d["colunas"]].index("produto")
            return d, {l[i] for l in d["linhas"] if marca in str(l[i])}
        d_sim, _ = no_relatorio("pdv_produto=sim")
        d_nao, _ = no_relatorio("pdv_produto=nao")
        d_todos, _ = no_relatorio("")
        checar("o relatório recorta: sim + não = todos",
               d_sim["total"] + d_nao["total"] == d_todos["total"] and d_sim["total"] > 0,
               (d_sim["total"], d_nao["total"], d_todos["total"]))
    finally:
        with get_cursor() as cur:
            cur.execute("DELETE FROM produtos WHERE id = ANY(%s)", (ids,))

    print(f"\n{ok} passaram, {len(falhas)} falharam")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
