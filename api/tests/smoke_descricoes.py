"""Descrições de tipo, categoria e setor (migração 133).

🔑 Pedido do dono (25/10/2026): no cadastro do produto, passar o mouse no Tipo, na
Categoria e no Setor mostra o uso operacional, os exemplos/abrangência e o uso previsto;
o texto é editado em Tabelas de apoio ▸ Descrições.

O que esta suíte afirma:
1. tipos: `GET /tipos-produto` devolve os nove tipos do sistema, na ordem do modelo, com a
   descrição carregada do documento; `PUT` grava, audita, em branco vira nulo; tipo que
   não existe é 400; a cozinha não altera (403) mas lê (é o cadastro do produto que lê)
2. categorias e setores: nascem com descrição, a corrigem pelo PUT, em branco vira nulo,
   e a descrição volta na listagem que o cadastro do produto usa

    python tests/smoke_descricoes.py      (API de pé; BOTANE_API muda a porta)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402
from comum import garantir_cozinha  # noqa: E402
from models.produtos import TIPOS  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&[]"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(f"{nome}: {detalhe}")
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
token = (r or {}).get("access_token")
init_pool()

# A descrição do INSUMO é da casa: guardada para devolver no fim, a base é compartilhada.
with get_cursor() as cur:
    cur.execute("SELECT descricao FROM tipos_produto_descricao WHERE tipo = 'INSUMO'")
    _linha = cur.fetchone()
    INSUMO_ANTES = _linha["descricao"] if _linha else None

print("\n1. tipos")
st, tipos = chamar("GET", "/tipos-produto", token=token)
checar("a lista traz os nove tipos do sistema, na ordem do modelo",
       st == 200 and [t["tipo"] for t in tipos] == list(TIPOS), (st, tipos))
checar("com a descrição do documento já carregada (migração 133)",
       all(t["descricao"] for t in tipos), tipos)
checar("o serviço diz que não movimenta estoque",
       "estoque" in next(t for t in tipos if t["tipo"] == "SERVICO")["descricao"], tipos)

texto = f"Ingrediente da casa {marca}"
st, r = chamar("PUT", "/tipos-produto/INSUMO", {"descricao": f"  {texto}  "}, token)
st2, tipos = chamar("GET", "/tipos-produto", token=token)
checar("PUT grava a descrição do tipo, sem os espaços das pontas",
       st == 200 and next(t for t in tipos if t["tipo"] == "INSUMO")["descricao"] == texto,
       (st, r, tipos))
with get_cursor() as cur:
    cur.execute("""SELECT 1 FROM auditoria WHERE entidade = 'tipo_produto'
                    AND id_entidade = 'INSUMO' AND depois->>'descricao' = %s""", (texto,))
    checar("e audita", cur.fetchone() is not None)
st, r = chamar("PUT", "/tipos-produto/INSUMO", {"descricao": "   "}, token)
st2, tipos = chamar("GET", "/tipos-produto", token=token)
checar("em branco vira nulo (a tela cai na ajuda do código)",
       st == 200 and next(t for t in tipos if t["tipo"] == "INSUMO")["descricao"] is None,
       tipos)
st, r = chamar("PUT", "/tipos-produto/MATERIAL_LIMPEZA", {"descricao": "x"}, token)
checar("tipo que não existe é 400", st == 400, (st, r))

cozinha = garantir_cozinha(chamar, token)
st, r = chamar("PUT", "/tipos-produto/INSUMO", {"descricao": "da cozinha"}, cozinha)
checar("a cozinha não altera a descrição do tipo (403)", st == 403, (st, r))
st, r = chamar("GET", "/tipos-produto", token=cozinha)
checar("mas lê: é o cadastro do produto que mostra a dica", st == 200, (st, r))

print("\n2. categorias e setores")
st, r = chamar("POST", "/categorias",
               {"nome": f"CAT DESC {marca}", "descricao": "Exemplos: a, b e c."}, token)
id_cat = (r or {}).get("id")
st, cats = chamar("GET", "/categorias", token=token)
cat = next((c for c in cats or [] if c["id"] == id_cat), {})
checar("categoria nasce com a descrição, e ela volta na listagem",
       cat.get("descricao") == "Exemplos: a, b e c.", cat)
chamar("PUT", f"/categorias/{id_cat}", {"descricao": "Outros exemplos."}, token)
st, cats = chamar("GET", "/categorias", token=token)
cat = next((c for c in cats or [] if c["id"] == id_cat), {})
checar("e a corrige pelo PUT", cat.get("descricao") == "Outros exemplos.", cat)
chamar("PUT", f"/categorias/{id_cat}", {"descricao": ""}, token)
st, cats = chamar("GET", "/categorias", token=token)
cat = next((c for c in cats or [] if c["id"] == id_cat), {})
checar("categoria com descrição em branco fica nula", cat.get("descricao") is None, cat)

st, r = chamar("POST", "/setores", {"nome": f"SETOR DESC {marca}", "descricao": "Uso X."},
               token)
id_set = (r or {}).get("id")
st, sets = chamar("GET", "/setores", token=token)
sto = next((s for s in sets or [] if s["id"] == id_set), {})
checar("setor nasce com a descrição, e ela volta na listagem",
       sto.get("descricao") == "Uso X.", sto)
chamar("PUT", f"/setores/{id_set}", {"descricao": "Uso Y."}, token)
st, sets = chamar("GET", "/setores", token=token)
sto = next((s for s in sets or [] if s["id"] == id_set), {})
checar("e o corrige pelo PUT", sto.get("descricao") == "Uso Y.", sto)
st, r = chamar("PUT", f"/setores/{id_set}", {"descricao": "x" * 501}, token)
checar("mais de 500 caracteres é recusado (422)", st == 422, st)

print("\n3. limpeza")
chamar("DELETE", f"/categorias/{id_cat}", token=token)
chamar("DELETE", f"/setores/{id_set}", token=token)
with get_cursor() as cur:
    cur.execute("UPDATE tipos_produto_descricao SET descricao = %s WHERE tipo = 'INSUMO'",
                (INSUMO_ANTES,))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
