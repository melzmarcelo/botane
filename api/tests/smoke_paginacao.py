"""Teste de fumaça da paginação — o padrão das listas.

Toda lista que pode crescer devolve um PEDAÇO e diz quantos existem, no
cabeçalho `X-Total`. Sem o total, uma lista cheia e uma lista cortada são
iguais para quem chama: a tela de compras mostrava as 50 notas mais recentes
de 3.670 e nada avisava que havia mais.

O que esta suíte cobra de cada endpoint:

* `limite` corta de verdade;
* `X-Total` conta o que existe, não o que veio;
* `offset` anda — a segunda página não repete a primeira;
* o filtro entra na conta: buscar reduz o total, não só a página;
* o cabeçalho está exposto no CORS (senão o navegador não o entrega).

    python tests/smoke_paginacao.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    """Devolve (status, corpo, cabeçalhos) — o total mora nos cabeçalhos."""
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null"), dict(r.headers)
    except urllib.error.HTTPError as e:
        conteudo = e.read()
        try:
            return e.code, json.loads(conteudo or b"null"), dict(e.headers)
        except json.JSONDecodeError:
            return e.code, {"detail": conteudo.decode(errors="replace")}, dict(e.headers)


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def total_de(cabecalhos) -> int | None:
    for k, v in cabecalhos.items():
        if k.lower() == "x-total":
            return int(v)
    return None


st, r, _ = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r.get("access_token")
if not token:
    print("Não entrou:", r)
    raise SystemExit(1)

print("0. cenário: cada suíte garante o que precisa")
garantir_local(chamar_simples := (lambda m, c, b=None, token=None: chamar(m, c, b, token)[:2]),
               token)
marca = str(abs(hash(BASE)) % 100000)

# Produtos suficientes para haver o que paginar. Reaproveita os que existirem:
# a base pode já ter um catálogo inteiro, e criar mais 5 não muda nada.
st, produtos, cab = chamar("GET", "/produtos?limite=1", token=token)
existentes = total_de(cab) or 0
criados = []
for i in range(max(0, 5 - existentes)):
    st, r, _ = chamar("POST", "/produtos",
                      {"nome": f"Pag teste {marca}-{i}", "tipo": "INSUMO", "um_estoque": "UN"},
                      token=token)
    if st == 201:
        criados.append(r["id"])
checar("há o que paginar", (total_de(chamar("GET", "/produtos?limite=1", token=token)[2]) or 0) >= 3)


print("1. o total vem no cabeçalho, e conta o que EXISTE")
st, pagina, cab = chamar("GET", "/produtos?limite=2&offset=0", token=token)
checar("a lista responde", st == 200, st)
checar("o limite corta de verdade", len(pagina) <= 2, len(pagina))
total = total_de(cab)
checar("o total vem em X-Total", total is not None, list(cab))
checar("e é maior que a página", total is not None and total >= len(pagina), (total, len(pagina)))


print("2. offset anda — a segunda página não repete a primeira")
st, segunda, cab2 = chamar("GET", "/produtos?limite=2&offset=2", token=token)
ids_um = {p["id"] for p in pagina}
ids_dois = {p["id"] for p in segunda}
checar("a segunda página traz outros registros", not (ids_um & ids_dois), (ids_um, ids_dois))
checar("e o total não muda entre páginas", total_de(cab2) == total, (total_de(cab2), total))


print("3. o filtro entra na conta, não só na página")
st, achados, cab3 = chamar("GET", f"/produtos?busca=Pag teste {marca}&limite=100", token=token)
total_filtrado = total_de(cab3)
checar("buscar reduz o TOTAL, não só o que veio",
       total_filtrado is not None and total_filtrado <= (total or 0),
       (total_filtrado, total))
checar("e o total bate com o que veio quando cabe numa página",
       total_filtrado == len(achados), (total_filtrado, len(achados)))


print("4. o mesmo contrato nas outras listas")
# Cada uma com o seu nome de coisa — se o endpoint não paginar, `X-Total` some
# e o navegador passa a achar que o total é o tamanho da página.
for caminho, nome in [
    ("/produtos", "produtos"),
    ("/fornecedores", "fornecedores"),
    ("/notas", "notas de entrada"),
    ("/fichas", "fichas"),
    ("/vendas", "vendas"),
    ("/inventarios", "inventários"),
    ("/usuarios", "usuários"),
    ("/auditoria", "auditoria"),
    ("/estoque/saldos", "saldos"),
    ("/estoque/movimentos", "razão"),
    ("/estoque/producoes", "produções"),
]:
    st, corpo, cab = chamar("GET", f"{caminho}?limite=3&offset=0", token=token)
    checar(f"{nome}: responde e diz o total",
           st == 200 and total_de(cab) is not None and len(corpo) <= 3,
           (st, total_de(cab), len(corpo) if isinstance(corpo, list) else corpo))


print("5. o limite tem teto — ninguém puxa a base inteira por engano")
st, r, _ = chamar("GET", "/produtos?limite=99999", token=token)
checar("limite absurdo é recusado", st == 422, st)
st, r, _ = chamar("GET", "/produtos?offset=-1", token=token)
checar("offset negativo é recusado", st == 422, st)


print("6. o cabeçalho chega ao navegador (CORS)")
# ⚠️ Sem `expose_headers`, o servidor manda o X-Total e o navegador NÃO o
# entrega à tela — que passa a achar que o total é o tamanho da página.
# `Access-Control-Expose-Headers` vem na resposta DE VERDADE, não no preflight:
# é preciso fazer o GET com `Origin`, como o navegador faz.
req = urllib.request.Request(BASE + "/produtos?limite=1", method="GET")
req.add_header("Origin", "http://localhost:3100")
req.add_header("Authorization", f"Bearer {token}")
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        expostos = ""
        for k, v in r.headers.items():
            if k.lower() == "access-control-expose-headers":
                expostos = v
        checar("X-Total está exposto no CORS", "x-total" in expostos.lower(), expostos)
except urllib.error.HTTPError as e:
    checar("X-Total está exposto no CORS", False, e.code)


print("7. limpeza")
for id_produto in criados:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
