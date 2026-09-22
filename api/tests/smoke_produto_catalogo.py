"""A aba Catálogo do produto: a foto e a informação adicional.

🔑 **Pedido do dono (22/09/2026):** *"no cadastro de produtos, quando utilizando
Reservas, criar uma nova aba chamada Catálogo. Nesta aba teremos Foto e um campo
para Informação Adicional."*

⚠️ **São dois caminhos diferentes de propósito.** A informação adicional viaja no
formulário, que é JSON; a foto sobe por rota própria, multipart. Um campo de
arquivo dentro do formulário faria quem só arruma o preço carregar megabytes a
cada salvar.

    python tests/smoke_produto_catalogo.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from base64 import b64decode

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(int(time.time()))[-7:]

# Um PNG 8x8 de verdade: o servidor ABRE a imagem para conferir, e bytes
# inventados levariam 400 por um motivo que não é o que se quer medir.
PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
    "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"),
                                 method=metodo)
    if not bruto:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            conteudo = r.read()
            if bruto:
                return r.status, conteudo, r.headers
            return r.status, json.loads(conteudo or b"null")
    except urllib.error.HTTPError as e:
        conteudo = e.read()
        if bruto:
            return e.code, conteudo, e.headers
        try:
            return e.code, json.loads(conteudo or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": conteudo.decode(errors="replace")}


def enviar_foto(id_produto, token, conteudo=PNG, nome="prato.png", tipo="image/png"):
    """Um POST multipart escrito à mão — o `chamar` acima só fala JSON."""
    limite = uuid.uuid4().hex
    corpo = (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="arquivo"; filename="{nome}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n").encode() + conteudo + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/produtos/{id_produto}/foto", method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, corpo, timeout=60) as r:
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


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

print("\n0. um produto para vestir")
st, novo = chamar("POST", "/produtos", {
    "nome": f"PRATO CATALOGO {MARCA}", "tipo": "INSUMO", "um_estoque": "UN",
    "um_compra": "UN", "fator_compra": 1, "controla_estoque": True,
}, token)
ID = (novo or {}).get("id")
checar("o produto nasce", st == 201 and bool(ID), (st, novo))

print("\n1. a informação adicional viaja no formulário")
st, atual = chamar("GET", f"/produtos/{ID}", token=token)
# ⚠️ Nasce NULA, não vazia: campo que nunca foi preenchido e campo apagado são
# a mesma coisa para quem lê, e string vazia no banco esconde a diferença.
checar("ela nasce nula", st == 200 and atual.get("informacao_adicional") is None,
       (st, atual.get("informacao_adicional")))

TEXTO = "Massa de fermentação natural, 48 horas de descanso."
st, _r = chamar("PUT", f"/produtos/{ID}", {**atual, "informacao_adicional": TEXTO}, token)
checar("salvar aceita o texto", st == 200, (st, _r))
st, atual = chamar("GET", f"/produtos/{ID}", token=token)
checar("e ele volta como foi escrito, com acento",
       atual.get("informacao_adicional") == TEXTO, atual.get("informacao_adicional"))

# 🔑 **Não é a `observacao`, e a diferença é quem lê.** Observação é recado
# interno; esta é para o cliente. A suíte cobra que sejam DUAS colunas, porque
# misturá-las publicaria recado de equipe na vitrine.
st, _r = chamar("PUT", f"/produtos/{ID}",
                {**atual, "observacao": "conferir com o fornecedor"}, token)
st, atual = chamar("GET", f"/produtos/{ID}", token=token)
checar("e a observação interna continua sendo outra coisa",
       atual.get("observacao") == "conferir com o fornecedor"
       and atual.get("informacao_adicional") == TEXTO,
       (atual.get("observacao"), atual.get("informacao_adicional")))

# ⚠️ Teto de 500: o campo é lido numa tela, e texto livre sem limite é convite
# para alguém colar uma receita inteira e descobrir no site que não cabe.
st, _r = chamar("PUT", f"/produtos/{ID}", {**atual, "informacao_adicional": "x" * 501},
                token)
checar("acima de 500 caracteres é recusado", st == 422, st)

print("\n2. a foto sobe por rota própria")
st, r = enviar_foto(ID, token)
checar("o envio responde 200", st == 200, (st, r))
URL = (r or {}).get("foto_url")
checar("devolvendo o endereço do arquivo", bool(URL) and "/arquivos/" in (URL or ""), r)
checar("e o nome do arquivo original", r.get("foto_nome") == "prato.png", r)

st, atual = chamar("GET", f"/produtos/{ID}", token=token)
checar("o produto passa a apontar para ela", atual.get("foto_url") == URL,
       atual.get("foto_url"))
checar("com o tamanho gravado", atual.get("foto_bytes") == len(PNG),
       (atual.get("foto_bytes"), len(PNG)))

# 🔑 **A rota do arquivo é PÚBLICA**, como a da logo: a `<img>` do navegador não
# manda cabeçalho de autenticação. O que protege é o sufixo aleatório no nome.
st, conteudo, cabecalhos = chamar("GET", URL, bruto=True)
checar("e a imagem abre sem token", st == 200 and conteudo == PNG, st)
checar("servida como imagem", cabecalhos.get("Content-Type", "").startswith("image/"),
       cabecalhos.get("Content-Type"))
# ⚠️ `nosniff` sempre: sem ele o navegador pode adivinhar o tipo e tratar como
# outra coisa o que a casa subiu.
checar("com nosniff", cabecalhos.get("X-Content-Type-Options") == "nosniff",
       cabecalhos.get("X-Content-Type-Options"))

print("\n3. trocar a foto apaga a anterior")
st, r2 = enviar_foto(ID, token, nome="outro.png")
NOVA = (r2 or {}).get("foto_url")
checar("a troca responde 200 com endereço NOVO", st == 200 and NOVA and NOVA != URL,
       (st, NOVA, URL))
# 🔑 **Gravar o novo, apontar e apagar o velho são UMA coisa só** — é a lição
# que a logo pagou. Sobrar o antigo encheria o banco de imagens órfãs.
st, _c, _h = chamar("GET", URL, bruto=True)
checar("e a imagem antiga deixa de existir", st == 404, st)

print("\n4. o que a rota RECUSA")
st, r = enviar_foto(ID, token, conteudo=b"isto nao e imagem nenhuma", nome="falso.png")
checar("arquivo que não é imagem é recusado", st == 400, (st, r))
checar("dizendo o porquê em português",
       "imagem" in (r.get("detail") or "").lower(), r.get("detail"))
# ⚠️ O `content-type` é só o que o navegador DIZ; quem decide é o conteúdo.
st, r = enviar_foto(ID, token, conteudo=PNG, nome="x.exe", tipo="application/x-msdownload")
checar("formato fora da lista é recusado", st == 400, (st, r))
checar("e a recusa diz quais valem",
       "PNG" in (r.get("detail") or ""), r.get("detail"))
st, r = enviar_foto(999999999, token)
checar("produto que não existe responde 404", st == 404, (st, r))

print("\n5. remover a foto")
st, r = chamar("DELETE", f"/produtos/{ID}/foto", token=token)
checar("a remoção responde 200", st == 200, (st, r))
st, atual = chamar("GET", f"/produtos/{ID}", token=token)
checar("o produto fica sem foto",
       atual.get("foto_url") is None and atual.get("foto_bytes") is None, atual.get("foto_url"))
st, _c, _h = chamar("GET", NOVA, bruto=True)
checar("e o arquivo sai do banco junto", st == 404, st)
# ⚠️ **Remover foto não apaga o produto nem o texto.** São coisas separadas, e
# quem tira a imagem não está desistindo do cadastro.
checar("mas a informação adicional continua lá",
       atual.get("informacao_adicional") == TEXTO, atual.get("informacao_adicional"))

print("\n6. limpeza")
with get_cursor() as cur:
    cur.execute("DELETE FROM produtos WHERE id = %s", (ID,))
    cur.execute("SELECT count(*) AS n FROM produtos WHERE id = %s", (ID,))
    checar("o produto de teste sai da base", cur.fetchone()["n"] == 0)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
