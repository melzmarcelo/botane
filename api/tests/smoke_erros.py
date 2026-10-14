"""O erro que estoura sem tratamento fica guardado e pode ser lido (migração 112).

🔑 **Nasceu do incidente de 09 a 11/10/2026**: a busca das vendas do PDV falhou
três dias e o diagnóstico dependeu de o dono colar a mensagem da tela de
Integrações. Esta suíte cobra o caminho inteiro:

1. um erro não tratado numa rota vira 500 COM o número do registro, e não um
   traceback nem um 500 mudo — pelo `exception_handler` de verdade do `main.py`
2. o registro tem a rota, o tipo, a mensagem e o traceback
3. `GET /erros` o devolve a quem tem `admin.auditoria`, e só a quem tem
4. o registro nunca levanta, nem com o banco recusando a gravação

⚠️ **O item 1 roda a aplicação DENTRO deste processo** (`TestClient`, sem
`lifespan`), com uma rota que só existe aqui. Não há — nem deve haver — rota no
sistema que quebre de propósito; e testar uma cópia do tratamento provaria a
cópia, não o que vai ao ar.

    python tests/smoke_erros.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except json.JSONDecodeError:
            return e.code, None


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


marca = str(time.time_ns() // 100)[-6:]
st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

print("1. erro não tratado vira 500 com o número do registro")
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402

database.init_pool()


def _quebra():
    raise ZeroDivisionError(f"divisão de teste {marca}")


rota_teste = f"/_teste_erro_{marca}"
main.app.add_api_route(rota_teste, _quebra, methods=["GET"])
cliente = TestClient(main.app, raise_server_exceptions=False)
resposta = cliente.get(rota_teste)
checar("responde 500", resposta.status_code == 500, resposta.status_code)
corpo = resposta.json() if resposta.headers.get("content-type", "").startswith(
    "application/json") else {}
detalhe = corpo.get("detail") or ""
checar("com frase, e não traceback", "Erro interno" in detalhe and "Traceback" not in detalhe,
       detalhe)
checar("e o número do registro", "registro " in detalhe, detalhe)

print("2. o registro guarda o que é preciso para investigar")
st, lista = chamar("GET", "/erros?limite=20", token=token)
checar("GET /erros responde", st == 200 and isinstance(lista, list), (st, lista))
meu = next((e for e in (lista or []) if f"teste {marca}" in (e.get("mensagem") or "")), None)
checar("o erro da rota está lá", meu is not None, [e.get("mensagem") for e in (lista or [])][:5])
meu = meu or {}
checar("com a rota e o método", meu.get("rota") == rota_teste and meu.get("metodo") == "GET", meu)
checar("com o tipo", meu.get("tipo") == "ZeroDivisionError", meu.get("tipo"))
checar("com o traceback, terminando no erro",
       "ZeroDivisionError" in (meu.get("detalhe") or "")[-300:], (meu.get("detalhe") or "")[-300:])
checar("e a origem é a API", meu.get("origem") == "api", meu.get("origem"))
checar("o número da resposta é o do registro", f"registro {meu.get('id')} " in detalhe,
       (detalhe, meu.get("id")))
st, so_api = chamar("GET", "/erros?origem=agenda_pdv&limite=50", token=token)
checar("o filtro por origem filtra",
       st == 200 and all(e["origem"] == "agenda_pdv" for e in so_api or []), so_api)

print("3. só quem vê a auditoria vê os erros")
st, r = chamar("GET", "/erros", token=garantir_cozinha(chamar, token))
checar("a cozinha leva 403", st == 403, st)

print("4. o registro nunca levanta")
from services import erros  # noqa: E402

# Origem nula viola o NOT NULL: o INSERT falha, e o registro tem de engolir.
try:
    numero = erros.registrar(None, RuntimeError("teste"))  # type: ignore[arg-type]
    checar("com o banco recusando, devolve None em vez de levantar", numero is None, numero)
except Exception as e:  # noqa: BLE001
    checar("com o banco recusando, devolve None em vez de levantar", False, repr(e))

# Limpeza: o registro de teste não fica na tela de quem investiga de verdade.
from database import get_cursor  # noqa: E402

with get_cursor() as cur:
    cur.execute("DELETE FROM erros_sistema WHERE rota = %s", (rota_teste,))
database.close_pool()

print(f"\n{ok} passaram, {len(falhas)} falharam")
sys.exit(1 if falhas else 0)
