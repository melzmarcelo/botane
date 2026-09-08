"""Teste de fumaça do Open Food Facts — a caixa que virava muffin.

🔑 **O que este teste existe para impedir**, e não é hipótese: na base real, o
produto `CAIXA 30X30X14 1KG BR`, de código `0000000027083`, casa no Open Food
Facts com "Made Without Wheat Blueberry Muffins", da Marks & Spencer. O código
não é EAN — é código interno preenchido com zeros que, por acaso, ocupa um
número de verdade lá. Uma versão deste recurso que aplicasse sozinho renomearia
uma caixa de papelão para muffin de mirtilo, calada.

⚠️ **NÃO depende da internet.** Todas as checagens abaixo param ANTES da
chamada externa: ou são a validação pura do código, ou são códigos que o
servidor recusa sem perguntar a ninguém. Suíte que precisa de um serviço de fora
falha quando aquele serviço cai, e ensina a ignorar o vermelho.

    python tests/smoke_openfoodfacts.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from services import openfoodfacts as off  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=40) as r:
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


print("1. o digito verificador separa EAN de sequencia qualquer")
checar("um EAN-13 real confere", off.digito_verificador_ok("7898080640611"))
checar("mexer no ultimo digito derruba", not off.digito_verificador_ok("7898080640612"))
# ⚠️ Digito calculado, nao inventado: a primeira versao deste teste usou
# "78908125" supondo que servisse, e o proprio teste reprovou -- que e o
# comportamento certo da funcao, e a prova de que ela nao aceita qualquer coisa.
checar("EAN-8 tambem confere", off.digito_verificador_ok("78908123"))
checar("11 digitos nao e comprimento de GTIN",
       not off.digito_verificador_ok("78980806406"))
checar("com letra nao passa", not off.digito_verificador_ok("789808064061X"))


print("\n2. o codigo interno e recusado ANTES de perguntar ao OFF")
# 🔑 A caixa de papelao. Este e o caso que deu origem ao recurso ter confirmacao.
pode, motivo = off.codigo_utilizavel("0000000027083")
checar("zeros a esquerda: recusado", not pode, motivo)
checar("e a frase explica que o codigo e interno, nao que 'nao achamos'",
       "interno" in motivo.lower(), motivo)

# ⚠️ Faixa 2 e reservada a uso interno de loja (peso variavel): o que o OFF
# devolver para ela e outro produto qualquer que ocupou o mesmo numero.
pode, motivo = off.codigo_utilizavel("2345678901234")
checar("faixa 2 (uso interno da loja): recusado", not pode, motivo)
checar("dizendo que e peso variavel", "interno" in motivo.lower(), motivo)

pode, motivo = off.codigo_utilizavel("7898080640612")
checar("digito verificador errado: recusado", not pode, motivo)

pode, motivo = off.codigo_utilizavel("")
checar("sem codigo de barras: recusado", not pode, motivo)
checar("e a frase fala do CADASTRO daqui, nao do OFF",
       "cadastrado" in motivo.lower(), motivo)

pode, _ = off.codigo_utilizavel("7898080640611")
checar("um EAN de verdade passa da porteira", pode)


print("\n3. o endpoint devolve a recusa, sem chamar ninguem de fora")
st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))

marca = uuid.uuid4().hex[:6].upper()
criados = []

# Um produto com codigo INTERNO: e o caso da caixa de papelao, reproduzido.
# ⚠️ **O codigo NAO pode ser o `0000000027083` de verdade.** A primeira versao
# usou o codigo real e tomou 409: `codigo_barras` e unico, e o produto legitimo
# da casa ja o ocupa. O sistema estava certo e o teste, errado -- ele carimba o
# proprio marcador, como todas as suites da casa.
codigo_interno = "0000" + str(int(marca, 16))[:9].zfill(9)
st, p = chamar("POST", "/produtos", {
    "codigo": f"OFF-{marca}", "nome": f"CAIXA DE PAPELAO {marca}",
    "tipo": "INSUMO", "um_estoque": "UN", "controla_estoque": False,
    "status": "ATIVO", "codigo_barras": codigo_interno,
}, token=token)
interno = (p or {}).get("id")
if interno:
    criados.append(interno)
checar("o produto de teste nasce", bool(interno), (st, p))

if interno:
    st, r = chamar("GET", f"/produtos/{interno}/openfoodfacts", token=token)
    checar("o endpoint responde", st == 200, (st, r))
    checar("nao achou nada", r.get("achou") is False, r)
    checar("e diz por que: o codigo e interno",
           "interno" in (r.get("erro") or "").lower(), r.get("erro"))
    # 🔑 O ponto do teste inteiro: nenhuma sugestao chega para ser aplicada.
    checar("NENHUMA sugestao veio para este codigo", not r.get("sugestoes"), r)

# Produto sem codigo de barras nenhum.
st, p2 = chamar("POST", "/produtos", {
    "codigo": f"OFF2-{marca}", "nome": f"SEM CODIGO {marca}",
    "tipo": "INSUMO", "um_estoque": "UN", "controla_estoque": False,
    "status": "ATIVO",
}, token=token)
sem_codigo = (p2 or {}).get("id")
if sem_codigo:
    criados.append(sem_codigo)
if sem_codigo:
    st, r = chamar("GET", f"/produtos/{sem_codigo}/openfoodfacts", token=token)
    checar("sem codigo de barras, tambem responde 200 (nao e erro)", st == 200, (st, r))
    checar("dizendo que falta o codigo no cadastro",
           "codigo de barras" in (r.get("erro") or "").lower()
           or "código de barras" in (r.get("erro") or "").lower(), r.get("erro"))

st, r = chamar("GET", "/produtos/99999999/openfoodfacts", token=token)
checar("produto inexistente e 404", st == 404, (st, r))

# ⚠️ Sem token nao passa: o recurso le o cadastro de produto.
st, r = chamar("GET", f"/produtos/{interno or 1}/openfoodfacts")
checar("sem autenticacao e barrado", st in (401, 403), st)


for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
