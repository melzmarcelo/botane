"""A trava de tentativas do login — que nunca travou até 19/09/2026.

O `UPDATE tentativas_login` e o `raise` moravam no mesmo `with get_cursor()`, e
`get_conn` desfaz tudo quando uma exceção atravessa o bloco: o contador voltava
a zero a cada erro, e o bloqueio nunca acontecia. Qualquer um podia tentar
senhas sem limite, na tela e — agora — na página de autorização do Claude.

1. cada senha errada fica gravada
2. na N-ésima, o usuário fica bloqueado (429), mesmo com a senha CERTA
3. a página de autorização do Claude conta na MESMA trava
4. o administrador desbloqueia, e acertar zera o contador

    python tests/smoke_bloqueio_login.py            (API de pé na 9200)

⚠️ Cria o próprio usuário e o desativa no `atexit`: travar o usuário de Cozinha
das outras suítes derrubaria o login delas por quinze minutos.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from config import MAX_TENTATIVAS_LOGIN  # noqa: E402
from database import get_cursor  # noqa: E402

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
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def tentativas(email):
    with get_cursor() as cur:
        cur.execute("SELECT tentativas_login, bloqueado_ate FROM usuarios WHERE email = %s",
                    (email,))
        return cur.fetchone()


_, s = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
admin = s["access_token"]
marca = str(int(time.time()))[-6:]
EMAIL, SENHA = f"smoke.bloqueio{marca}@botane.com.br", "smoke12345"
_, papeis = chamar("GET", "/papeis", token=admin)
id_papel = next(p["id"] for p in papeis if p["nome"].lower().startswith("admin"))
st, novo = chamar("POST", "/usuarios", {"nome": f"Bloqueio {marca}", "email": EMAIL,
                                        "senha": SENHA, "papeis": [{"id_papel": id_papel}]},
                  token=admin)
id_usuario = novo["id"]
atexit.register(lambda: chamar("DELETE", f"/usuarios/{id_usuario}", token=admin))

print("1. cada senha errada fica gravada")
st, _ = chamar("POST", "/auth/login", {"email": EMAIL, "senha": "errada"})
checar("senha errada é 401", st == 401, st)
checar("e o contador vai a 1 (antes voltava a zero)", tentativas(EMAIL)["tentativas_login"] == 1,
       tentativas(EMAIL))

print("\n2. o bloqueio acontece")
for _ in range(MAX_TENTATIVAS_LOGIN - 2):
    chamar("POST", "/auth/login", {"email": EMAIL, "senha": "errada"})

print("\n3. a página do Claude conta na mesma trava")
# A última tentativa antes do bloqueio vem pela página de autorização: se ela
# não contasse, seria a porta lateral para adivinhar a senha.
st, cli = chamar("POST", "/oauth/registrar", {"client_name": "suite bloqueio",
                                               "redirect_uris": ["http://localhost:1/cb"]})
form = {"response_type": "code", "client_id": cli["client_id"],
        "redirect_uri": "http://localhost:1/cb", "code_challenge": "x" * 43,
        "code_challenge_method": "S256", "email": EMAIL, "senha": "errada",
        "decisao": "permitir"}
urllib.request.urlopen(urllib.request.Request(
    BASE + "/oauth/autorizar", urllib.parse.urlencode(form).encode(), method="POST")).read()
t = tentativas(EMAIL)
checar(f"na {MAX_TENTATIVAS_LOGIN}ª tentativa (a da página do Claude) fica bloqueado",
       t["bloqueado_ate"] is not None, t)
st, r = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA})
checar("bloqueado, nem a senha CERTA entra (429)", st == 429, (st, r))

print("\n4. desbloquear e acertar")
st, _ = chamar("POST", f"/usuarios/{id_usuario}/desbloquear", token=admin)
checar("o administrador desbloqueia", st == 200, st)
st, _ = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA})
checar("e a pessoa entra", st == 200, st)
checar("com o contador zerado", tentativas(EMAIL)["tentativas_login"] == 0, tentativas(EMAIL))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
