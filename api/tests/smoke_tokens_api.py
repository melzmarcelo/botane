"""Chave de acesso de máquina — a porta do conector MCP.

O que este arquivo cobra:

1. a chave nasce só de leitura, aparece em claro UMA vez e começa com `btn_`
2. ela age COMO o usuário dono: mesmo `/auth/me`, mesmas permissões, e 403
   onde ele levaria 403
3. **só leitura pelo método**: POST/PUT/DELETE com chave dão 403, em qualquer rota
4. chave não gere chave — nem para listar
5. a lista não devolve nem o valor nem o hash; o último uso é gravado
6. revogada, vencida e de usuário inativo deixam de abrir
7. a auditoria registra a criação sem o valor
8. ninguém gera chave que abre loja que ele mesmo não enxerga
9. o login de sempre (JWT) continua funcionando

    python tests/smoke_tokens_api.py            (API de pé na 9200)

⚠️ Cria chaves e as revoga no fim. Usa o usuário de Cozinha das suítes.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = "smoke.cozinha@botane.com.br"

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, sessao = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
admin = sessao["access_token"]
id_admin = sessao["usuario"]["id"]
tok_cozinha_sessao = garantir_cozinha(chamar, admin)
_, usuarios = chamar("GET", "/usuarios?incluir_inativos=true&limite=500", token=admin)
id_cozinha = next(u["id"] for u in usuarios if u["email"] == COZINHA)
criadas: list[tuple[int, int]] = []


print("1. a chave nasce só de leitura e aparece em claro uma vez")
st, c = chamar("POST", f"/usuarios/{id_cozinha}/tokens",
               {"nome": "Claude da cozinha", "dias": 30}, token=admin)
checar("criar devolve 201", st == 201, (st, c))
chave = c.get("token", "")
criadas.append((id_cozinha, c.get("id")))
checar("o valor começa com btn_", chave.startswith("btn_"), chave[:8])
checar("o prefixo mostrável é o começo do valor",
       c.get("prefixo") and chave.startswith(c["prefixo"]), c.get("prefixo"))
checar("nasce somente leitura", c.get("somente_leitura") is True, c)
st, r = chamar("POST", f"/usuarios/{id_cozinha}/tokens", {"nome": "x", "dias": 400}, token=admin)
checar("validade acima de um ano é recusada (422)", st == 422, st)


print("\n2. a chave age como o usuário dono")
st, me = chamar("GET", "/auth/me", token=chave)
checar("GET /auth/me com a chave responde", st == 200, (st, me))
checar("e é a Cozinha, não quem gerou", me.get("email") == COZINHA, me.get("email"))
_, me_sessao = chamar("GET", "/auth/me", token=tok_cozinha_sessao)
checar("com as mesmas permissões do login dela",
       sorted(me.get("permissoes", [])) == sorted(me_sessao.get("permissoes", [])))
st, _ = chamar("GET", "/usuarios", token=chave)
checar("onde a Cozinha leva 403, a chave também", st == 403, st)


print("\n3. só leitura, decidido pelo método")
st, r = chamar("PUT", "/auth/me", {"nome": "Invadido"}, token=chave)
checar("PUT /auth/me com a chave dá 403", st == 403, (st, r))
checar("e a frase diz que a chave é só de leitura", "leitura" in str(r.get("detail")), r)
st, _ = chamar("POST", "/auth/trocar-senha",
               {"senha_atual": "smoke12345", "senha_nova": "outra12345"}, token=chave)
checar("trocar a senha do dono com a chave dá 403", st == 403, st)


print("\n4. chave não gere chave")
st, ca = chamar("POST", f"/usuarios/{id_admin}/tokens", {"nome": "chave do admin"}, token=admin)
chave_admin = ca.get("token", "")
criadas.append((id_admin, ca.get("id")))
st, r = chamar("GET", f"/usuarios/{id_cozinha}/tokens", token=chave_admin)
checar("nem LISTAR chaves com uma chave de administrador", st == 403, (st, r))
st, _ = chamar("POST", f"/usuarios/{id_cozinha}/tokens", {"nome": "filha"}, token=chave_admin)
checar("nem criar", st == 403, st)


print("\n5. a lista não devolve segredo, e o último uso é gravado")
st, lista = chamar("GET", f"/usuarios/{id_cozinha}/tokens", token=admin)
minha = next((t for t in lista if t["id"] == c["id"]), {})
checar("a chave aparece na lista do usuário", bool(minha), lista)
checar("sem o valor e sem o hash", "token" not in minha and "token_hash" not in minha, minha)
checar("com o último uso preenchido", minha.get("ultimo_uso_em") is not None, minha)
checar("e com quem a criou", minha.get("criado_por"), minha)


print("\n6. revogada, vencida e de usuário inativo deixam de abrir")
st, r = chamar("DELETE", f"/usuarios/{id_cozinha}/tokens/{c['id']}", token=admin)
checar("revogar responde 200", st == 200, (st, r))
st, r = chamar("GET", "/auth/me", token=chave)
checar("a chave revogada leva 401 na hora", st == 401, st)
st, _ = chamar("DELETE", f"/usuarios/{id_cozinha}/tokens/{c['id']}", token=admin)
checar("revogar de novo é 404", st == 404, st)

st, v = chamar("POST", f"/usuarios/{id_cozinha}/tokens", {"nome": "vencida"}, token=admin)
criadas.append((id_cozinha, v["id"]))
with get_cursor() as cur:
    cur.execute("UPDATE tokens_api SET expira_em = now() - interval '1 minute' WHERE id = %s",
                (v["id"],))
st, r2 = chamar("GET", "/auth/me", token=v["token"])
checar("a chave vencida leva 401", st == 401, st)
checar("com a MESMA frase da revogada", r2.get("detail") == r.get("detail"), (r, r2))

st, i = chamar("POST", f"/usuarios/{id_cozinha}/tokens", {"nome": "inativa"}, token=admin)
criadas.append((id_cozinha, i["id"]))
chamar("DELETE", f"/usuarios/{id_cozinha}", token=admin)
st, _ = chamar("GET", "/auth/me", token=i["token"])
checar("usuário desativado: a chave dele para de abrir", st in (401, 403), st)
st, _ = chamar("POST", f"/usuarios/{id_cozinha}/tokens", {"nome": "x"}, token=admin)
checar("e inativo não recebe chave nova (400)", st == 400, st)
st, _ = chamar("GET", f"/usuarios/{id_cozinha}/tokens", token=admin)
checar("mas a lista dele continua visível", st == 200, st)
garantir_cozinha(chamar, admin)
st, fantasma = chamar("GET", "/auth/me", token="btn_naoexiste")
checar("chave inventada leva 401", st == 401, st)


print("\n7. a auditoria registra sem o valor")
with get_cursor() as cur:
    cur.execute("""SELECT count(*) AS n FROM auditoria
                    WHERE entidade = 'token_api' AND id_entidade = %s AND acao = 'criar'""",
                (str(c["id"]),))
    registrada = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM auditoria WHERE depois::text LIKE %s",
                (f"%{chave}%",))
    vazada = cur.fetchone()["n"]
checar("a criação está na auditoria", registrada == 1, registrada)
checar("e o valor da chave não", vazada == 0, vazada)


print("\n8. ninguém gera chave que abre loja que não enxerga")
# ⚠️ A suíte cria a PRÓPRIA filial e a desativa no `atexit`: filial de teste
# ativa faz o seletor de loja aparecer na barra do dono (mesmo padrão de
# `smoke_lojas_do_usuario`).
marca = str(int(time.time()))[-6:]
EMAIL_G = f"smoke.chave{marca}@botane.com.br"
st, filial = chamar("POST", "/unidades", {"nome": f"Filial chave {marca}",
                                          "apelido": f"K{marca}"}, token=admin)
id_filial = (filial or {}).get("id")
_, papeis = chamar("GET", "/papeis", token=admin)
id_adm = next(p["id"] for p in papeis if p["nome"].lower().startswith("admin"))
st, g = chamar("POST", "/usuarios", {
    "nome": f"Gerente da filial {marca}", "email": EMAIL_G, "senha": "smoke12345",
    "papeis": [{"id_papel": id_adm, "id_unidade": id_filial}],
}, token=admin)
id_gerente = (g or {}).get("id")


def _limpar():
    try:
        if id_gerente:
            chamar("DELETE", f"/usuarios/{id_gerente}", token=admin)
        if id_filial:
            chamar("PUT", f"/unidades/{id_filial}", {"ativo": False}, token=admin)
    except Exception:
        pass


atexit.register(_limpar)
checar("preparo: filial e gerente lotado só nela", bool(id_filial and id_gerente), (filial, g))
_, entrou = chamar("POST", "/auth/login", {"email": EMAIL_G, "senha": "smoke12345"})
gerente = (entrou or {}).get("access_token")
st, r = chamar("POST", f"/usuarios/{id_admin}/tokens", {"nome": "roubo"}, token=gerente)
checar("o gerente da filial NÃO gera a chave do dono (403)", st == 403, (st, r))
st, _ = chamar("GET", f"/usuarios/{id_admin}/tokens", token=gerente)
checar("nem lista as chaves do dono", st == 403, st)
st, r = chamar("POST", f"/usuarios/{id_gerente}/tokens", {"nome": "a minha"}, token=gerente)
checar("mas gera a de quem está na loja dele", st == 201, (st, r))
if st == 201:
    criadas.append((id_gerente, r["id"]))


print("\n9. o login de sempre continua valendo")
st, me = chamar("GET", "/auth/me", token=admin)
checar("JWT de sessão responde /auth/me", st == 200 and me.get("id") == id_admin, st)


for dono, id_token in criadas:
    if id_token:
        chamar("DELETE", f"/usuarios/{dono}/tokens/{id_token}", token=admin)

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for f in falhas:
        print("  -", f)
    sys.exit(1)
