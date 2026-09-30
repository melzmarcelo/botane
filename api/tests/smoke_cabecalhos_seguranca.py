"""Cabeçalhos de segurança da API, e a documentação só em casa (validação de 29/09/2026).

🔴 No ar não saía cabeçalho nenhum, e `/api/docs` entregava o mapa inteiro das rotas.
Esta suíte segura as duas correções:
1. toda resposta sai com nosniff, moldura SAMEORIGIN, política de referência e HSTS;
2. ⚠️ o middleware usa `setdefault` — a tela do OAuth, que pede senha, continua com os
   cabeçalhos MAIS rígidos dela (moldura DENY, referência no-referrer);
3. com `DEBUG` desligado, `/docs`, `/redoc` e `/openapi.json` não existem.

    python tests/smoke_cabecalhos_seguranca.py        (API de pé na 9200)
"""

import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9200"
ok = 0
falhas: list[str] = []


def cabecalhos(caminho):
    try:
        with urllib.request.urlopen(BASE + caminho, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


print("1. toda resposta sai com os cabeçalhos")
st, h = cabecalhos("/saude")
checar("nosniff", h.get("x-content-type-options") == "nosniff", h)
checar("moldura só do próprio site", h.get("x-frame-options") == "SAMEORIGIN", h)
checar("política de referência", h.get("referrer-policy") == "strict-origin-when-cross-origin", h)
checar("HSTS", "max-age=" in (h.get("strict-transport-security") or ""), h)
st, h = cabecalhos("/rota-que-nao-existe")
checar("inclusive no erro (404)", st == 404 and h.get("x-content-type-options") == "nosniff", (st, h))

print("\n2. o middleware não afrouxa quem já é mais rígido")
st, h = cabecalhos("/oauth/autorizar")
checar("a tela do OAuth continua recusando QUALQUER moldura (DENY)",
       h.get("x-frame-options") == "DENY", (st, h.get("x-frame-options")))
checar("e sem referência nenhuma", h.get("referrer-policy") == "no-referrer",
       h.get("referrer-policy"))

print("\n3. a documentação só existe com DEBUG ligado")
# ⚠️ Num processo à parte: o `DEBUG` é lido na importação do `config`.
saida = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, '.'); import main; "
     "print(main.app.docs_url, main.app.redoc_url, main.app.openapi_url)"],
    capture_output=True, text=True, env={**os.environ, "DEBUG": "false"}, cwd=".")
ultima = (saida.stdout.strip().splitlines() or [""])[-1]
checar("com DEBUG=false não há /docs, /redoc nem /openapi.json", ultima == "None None None",
       (ultima, saida.stderr[-300:]))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
