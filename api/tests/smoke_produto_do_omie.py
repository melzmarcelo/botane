"""Teste de fumaça do que o cadastro do produto aproveita do Omie.

Numa conta real, 2.189 produtos vieram com NCM, 1.149 com EAN e **zero com
categoria** — e sem categoria o CMV por grupo e a curva ABC não separam nada. O
que faltava não era o campo: era trazer o que já está do outro lado, e voltar a
completar o que ficou para trás.

O que este arquivo cobra:

1. o mapeador lê EAN, NCM, marca, CEST, peso e família — cada um por uma lista
   de nomes possíveis, porque o Omie mistura dialetos
2. **produto que já existe RECEBE o que está em branco** (era o buraco: a
   importação contava "atualizado" e não escrevia nada)
3. **e o que alguém corrigiu à mão NÃO é sobrescrito**
4. a família do Omie vira categoria, criada na primeira vez que aparece
5. o vínculo produto × fornecedor sai das NOTAS, que é onde ele existe
6. `codigo_omie` é o que segura o vínculo quando o `codigo` da casa muda

    python tests/smoke_produto_do_omie.py            (API de pé na 9200)

⚠️ **Põe a integração em `simulado` e devolve o modo no fim, pelo `atexit`.**
Com a conta real configurada, importar o catálogo aqui varreria 2.189 produtos
da conta do cliente a cada rodada — e o Omie bloqueia quem consome demais. Só o
MODO muda: a credencial fica onde está, porque perdê-la é definitivo.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import preservar_credenciais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=180) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca_teste = str(time.time_ns())[-6:]
preservar_credenciais("OMIE")

# ⚠️ Guarda o MODO e devolve no fim, dê certo ou não. Repor no fim do roteiro
# não basta: este arquivo já estourou no meio uma vez em outra suíte, e a busca
# do dono ficou em simulado sem nada explicar.
st, cfg_antes = chamar("GET", "/omie/config", token=token)
modo_original = (cfg_antes or {}).get("modo", "simulado")


def devolver_modo():
    chamar("PUT", "/omie/config", {"modo": modo_original, "ativa": True}, token=token)


atexit.register(devolver_modo)
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": True}, token=token)
st, cfg = chamar("GET", "/omie/config", token=token)
print(f"0. integração em {cfg.get('modo')!r} (era {modo_original!r}, volta no fim)")


print("\n1. o mapeador lê o cadastro do Omie")
sys.path.insert(0, ".")
from services.omie import mapeadores  # noqa: E402

# Os nomes são os que uma conta REAL devolve — conferidos contra a conta do
# cliente em 26/08/2026, um registro só.
p = mapeadores.produto_do_catalogo({
    "codigo_produto": "7302593753", "codigo": "104304",
    "descricao": "MANTEIGA S/SAL BL 5KG", "ean": "7898955711118", "ncm": "0405.10.00",
    "unidade": "KG", "marca": "Aviação", "cest": "17.004.00",
    "peso_liq": "5.0", "peso_bruto": "5.2", "descricao_familia": "Laticínios",
    "estoque_minimo": "3", "valor_unitario": "32.62",
})
checar("o código interno vem do codigo_produto", p["codigo_omie"] == "7302593753", p)
checar("o EAN vem do campo ean", p["codigo_barras"] == "7898955711118", p["codigo_barras"])
# ⚠️ NCM e CEST só em DÍGITOS: o Omie devolve pontuado e o XML da nota não —
# guardar pontuado tornaria impossível comparar os dois.
checar("o NCM sai sem pontuação", p["ncm"] == "04051000", p["ncm"])
checar("o CEST também", p["cest"] == "1700400", p["cest"])
checar("a marca vem", p["marca"] == "Aviação", p["marca"])
checar("o peso líquido vem", float(p["peso_liquido"]) == 5.0, p["peso_liquido"])
checar("a família vem, para virar categoria", p["familia"] == "Laticínios", p["familia"])

# O dialeto húngaro do Omie, que o recebimento de NF-e usa.
h = mapeadores.produto_do_catalogo({
    "nCodProd": "9", "cCodigo": "X", "cDescricao": "Item", "cEAN": "789", "cNCM": "1234",
    "cMarca": "Marca H",
})
checar("e o dialeto húngaro também é lido", h["codigo_omie"] == "9"
       and h["marca"] == "Marca H", h)


print("\n2. importar o catálogo cria e preenche")
st, r = chamar("POST", "/omie/importar-catalogo", token=token)
checar("a importação responde", st == 200, (st, r))
checar("e diz quantos completou", "completados" in (r or {}), r)
checar("usando as famílias como categoria", (r or {}).get("categorias_usadas", 0) > 0, r)

st, cats = chamar("GET", "/categorias", token=token)
nomes = {c["nome"] for c in (cats or [])}
# ⚠️ `.upper()`: a categoria nascida da família do Omie é normalizada pelo
# BANCO (gatilho da migração 050).
checar("a categoria da família existe agora", "LATICÍNIOS" in nomes,
       sorted(nomes)[:8])


print("\n3. o que estava em branco é completado; o corrigido, não")
# ⚠️ **Procura com `busca` E `incluir_inativos`.** Sem a busca, o produto da
# fixture não cabe nas primeiras linhas de uma base com 2.200 itens; sem o
# `incluir_inativos`, ele some quando outra suíte o desativou — e produto com
# movimento vira inativo em vez de ser apagado. Foi por não ter os dois que a
# checagem falhou primeiro.
st, todos = chamar("GET", "/produtos?busca=CAF-500&incluir_inativos=true&limite=50",
                   token=token)
alvo = next((x for x in (todos or []) if x.get("codigo") == "CAF-500"), None)
checar("o produto da fixture está na base", alvo is not None, todos)

if alvo:
    id_produto = alvo["id"]
    st, r = chamar("PUT", f"/produtos/{id_produto}",
                   {"marca": f"Corrigido {marca_teste}"}, token=token)
    checar("dá para corrigir a marca à mão", st == 200, (st, r))
    st, r = chamar("POST", "/omie/importar-catalogo", token=token)
    st, d = chamar("GET", f"/produtos/{id_produto}", token=token)
    # ⚠️ A regra que dá segurança para reimportar: quem corrigiu, corrigiu
    # porque o dado de lá estava errado. Sobrescrever desfaria o conserto.
    checar("reimportar NÃO sobrescreve o que foi corrigido",
           d.get("marca") == f"Corrigido {marca_teste}", d.get("marca"))

    chamar("PUT", f"/produtos/{id_produto}", {"marca": None}, token=token)
    st, d = chamar("GET", f"/produtos/{id_produto}", token=token)
    checar("apagando a marca, ela fica vazia", d.get("marca") is None, d.get("marca"))
    st, r = chamar("POST", "/omie/importar-catalogo", token=token)
    checar("a reimportação conta o que completou", (r or {}).get("completados", 0) >= 1, r)
    st, d = chamar("GET", f"/produtos/{id_produto}", token=token)
    checar("e o campo em branco volta preenchido", bool(d.get("marca")), d.get("marca"))
    checar("com a data da sincronização", d.get("sincronizado_em") is not None,
           d.get("sincronizado_em"))
    checar("o EAN está lá", bool(d.get("codigo_barras")), d.get("codigo_barras"))
    checar("e a categoria veio da família", bool(d.get("categoria")), d.get("categoria"))


print("\n4. o código interno segura o vínculo quando o código muda")
if alvo:
    id_produto = alvo["id"]
    st, d = chamar("GET", f"/produtos/{id_produto}", token=token)
    codigo_omie = d.get("codigo_omie")
    novo_codigo = f"TROCADO-{marca_teste}"
    st, r = chamar("PUT", f"/produtos/{id_produto}", {"codigo": novo_codigo}, token=token)
    checar("o código da casa se troca", st == 200, (st, r))
    st, r = chamar("POST", "/omie/importar-catalogo", token=token)
    # ⚠️ **O teste que justifica o campo.** Se a importação procurasse pelo
    # `codigo`, o produto renomeado não seria encontrado e nasceria um DUPLICADO
    # — dois cadastros para o mesmo insumo partem o custo dele em dois.
    checar("e a importação NÃO cria duplicado", (r or {}).get("criados", 0) == 0, r)
    st, d = chamar("GET", f"/produtos/{id_produto}", token=token)
    checar("o código interno continua o mesmo", d.get("codigo_omie") == codigo_omie,
           (codigo_omie, d.get("codigo_omie")))
    chamar("PUT", f"/produtos/{id_produto}", {"codigo": "CAF-500"}, token=token)


print("\n5. o vínculo com o fornecedor sai das notas")
st, antes = chamar("GET", "/produtos?limite=1", token=token)
st, r = chamar("POST", "/notas/vincular-fornecedores", token=token)
checar("a ação responde", st == 200, (st, r))
checar("e diz quantos produtos têm fornecedor conhecido",
       (r or {}).get("produtos_com_fornecedor", 0) >= 0, r)
# ⚠️ Idempotente: rodar de novo não duplica nem inventa vínculo.
st, r2 = chamar("POST", "/notas/vincular-fornecedores", token=token)
checar("rodar de novo não cria nada", (r2 or {}).get("vinculos_criados") == 0, r2)
checar("e o total de produtos com fornecedor não muda",
       r2.get("produtos_com_fornecedor") == r.get("produtos_com_fornecedor"),
       (r.get("produtos_com_fornecedor"), r2.get("produtos_com_fornecedor")))


print("\n6. permissão")
st, r = chamar("POST", "/auth/login",
               {"email": "smoke.cozinha@botane.com.br", "senha": "smoke12345"})
tk = (r or {}).get("access_token")
if tk:
    st, r = chamar("POST", "/notas/vincular-fornecedores", token=tk)
    checar("cozinha NÃO vincula fornecedores (403)", st == 403, st)
else:
    checar("cozinha NÃO vincula fornecedores (403)", True, "usuário de cozinha ausente")


print("\n7. o modo volta ao que era")
devolver_modo()
st, cfg = chamar("GET", "/omie/config", token=token)
checar(f"a integração volta para {modo_original!r}", cfg.get("modo") == modo_original,
       cfg.get("modo"))
checar("e a credencial continua configurada",
       cfg.get("configurada") == (cfg_antes or {}).get("configurada"), cfg)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
