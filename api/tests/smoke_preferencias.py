"""As preferências de tela por usuário e a ordem do grid de produtos (layout novo, fase 2 — 05/11/2026).

🔑 **Pedido do dono:** *"grids configuráveis"*. Cada pessoa guarda colunas, densidade e visões no
servidor (`preferencias_usuario`, migração 148), e o cabeçalho do grid ordena NO SERVIDOR
(`/produtos?ordem=&direcao=`), porque a lista é paginada.

⚠️ Confere o que importa para a segurança: cada um só enxerga a PRÓPRIA preferência, a chave é
validada e o tamanho tem teto. Usa a chave `teste:smoke-preferencias`, apagada no fim.

    python tests/smoke_preferencias.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
CHAVE = "teste:smoke-preferencias"
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, None


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


init_pool()
_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))


def limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM preferencias_usuario WHERE chave = %s", (CHAVE,))


limpar()
try:
    print("1. ler, gravar e apagar")
    st, r = chamar("GET", f"/preferencias/{CHAVE}", token=token)
    checar("sem preferência, devolve valor nulo", st == 200 and r == {"valor": None}, (st, r))
    valor = {"ordem": ["codigo", "nome"], "ocultas": ["setor"], "compacta": True,
             "visoes": [{"nome": "Rascunhos", "busca": "situacao=RASCUNHO", "ordem": [], "ocultas": [], "compacta": False}]}
    st, _ = chamar("PUT", f"/preferencias/{CHAVE}", {"valor": valor}, token)
    st2, r = chamar("GET", f"/preferencias/{CHAVE}", token=token)
    checar("grava e lê de volta o mesmo JSON", st == 200 and st2 == 200 and r["valor"] == valor, r)
    st, _ = chamar("PUT", f"/preferencias/{CHAVE}", {"valor": {"compacta": False}}, token)
    _st, r = chamar("GET", f"/preferencias/{CHAVE}", token=token)
    checar("gravar de novo SUBSTITUI (não mescla)", r["valor"] == {"compacta": False}, r)
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM preferencias_usuario WHERE chave = %s", (CHAVE,))
        n = cur.fetchone()["n"]
    checar("uma linha só por usuário e chave", n == 1, n)
    chamar("DELETE", f"/preferencias/{CHAVE}", token=token)
    _st, r = chamar("GET", f"/preferencias/{CHAVE}", token=token)
    checar("apagar volta ao nulo", r == {"valor": None}, r)

    print("\n2. cada um vê só a sua")
    with get_cursor() as cur:
        cur.execute("SELECT id FROM usuarios WHERE email <> %s ORDER BY id LIMIT 1", (ADMIN[0],))
        outro = cur.fetchone()
        if outro:
            cur.execute("INSERT INTO preferencias_usuario (id_usuario, chave, valor) VALUES (%s, %s, %s)",
                        (outro["id"], CHAVE, json.dumps({"de": "outro"})))
    _st, r = chamar("GET", f"/preferencias/{CHAVE}", token=token)
    checar("a preferência de outro usuário com a mesma chave não aparece", not outro or r == {"valor": None}, r)

    print("\n3. validação")
    st, _ = chamar("GET", "/preferencias/Chave%20Ruim", token=token)
    checar("chave fora do padrão: 422", st == 422, st)
    st, _ = chamar("PUT", f"/preferencias/{CHAVE}", {"valor": [1, 2]}, token)
    checar("valor que não é objeto: 422", st == 422, st)
    st, _ = chamar("PUT", f"/preferencias/{CHAVE}", {"valor": {"x": "a" * 40000}}, token)
    checar("valor grande demais: 413", st == 413, st)
    st, _ = chamar("GET", f"/preferencias/{CHAVE}")
    checar("sem login: 401", st == 401, st)

    print("\n4. a ordem do grid de produtos")
    st, asc = chamar("GET", "/produtos?ordem=codigo&direcao=asc&limite=30&incluir_inativos=true", token=token)
    _st, desc = chamar("GET", "/produtos?ordem=codigo&direcao=desc&limite=30&incluir_inativos=true", token=token)
    # A ordem é "ativos primeiro" e depois a coluna: confere dentro dos ativos.
    cods = [x["codigo"].lower() for x in asc if x["ativo"]]
    checar("por código, crescente", st == 200 and cods == sorted(cods), cods[:5])
    cods_d = [x["codigo"].lower() for x in desc if x["ativo"]]
    checar("por código, decrescente", cods_d == sorted(cods_d, reverse=True), cods_d[:5])
    _st, preco = chamar("GET", "/produtos?ordem=preco&direcao=desc&limite=30", token=token)
    precos = [x["preco_venda"] for x in preco if x["preco_venda"] is not None]
    checar("por preço, do maior para o menor (sem preço no fim)",
           precos == sorted(precos, reverse=True)
           and all(x["preco_venda"] is not None for x in preco[:len(precos)]), precos[:5])
    st, _ = chamar("GET", "/produtos?ordem=p.id;DROP&limite=5", token=token)
    st2, _ = chamar("GET", "/produtos?ordem=nome&direcao=lado&limite=5", token=token)
    checar("chave de ordem desconhecida cai na ordem de sempre; direção inválida é 422",
           st == 200 and st2 == 422, (st, st2))
finally:
    limpar()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
