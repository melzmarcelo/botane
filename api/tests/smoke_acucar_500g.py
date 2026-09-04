"""O AÇÚCAR DE CONFEITEIRO, de ponta a ponta.

O cenário real, descrito pelo dono em 04/09/2026:

    O fornecedor manda o açúcar de confeiteiro em pacote de 1 kg e às vezes em
    pacote de 500 g — e para ELE são produtos diferentes, com códigos
    diferentes. Aqui os dois são o mesmo produto. Vinculei os dois, deixei o
    cadastro do principal bonito e NÃO cadastrei nada no de 500 g. Informei no
    vínculo que ele vale 0,5 kg. Quando a nota chegar em unidade, ele vai se
    achar e atualizar certo?

Este arquivo é a resposta, exercitada:

1. o item da nota **encontra o principal** pelo apelido que a fusão criou —
   o cadastro do absorvido está arquivado e ninguém o lê
2. e **converte pelos 0,5**: 4 UN viram 2 KG no razão
3. o cadastro do absorvido continuar vazio **não atrapalha nada** — o que vale é
   o `um_estoque` do principal e a conversão dita na tela dele
4. ⚠️ **nota que chega na PRÓPRIA unidade de estoque passa direto**: dizer
   "4 KG" já é dizer quilos, e aplicar o 0,5 ali transformaria 4 kg em 2 kg
5. e a conversão **não vale sem a marca** — o fator 1 automático que a fusão
   deixa continua sendo ignorado, senão toda fusão encobriria o fator de compra
   do produto

    python tests/smoke_acucar_500g.py     (API de pé na 9200)

⚠️ Cria os próprios produtos, fornecedor e notas, com marca de tempo, e desativa
tudo no `atexit`.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")

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
        with urllib.request.urlopen(req, dados, timeout=60) as r:
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


def perto(a, b, tol=0.001):
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
criados: dict = {"produtos": []}


def _limpar():
    try:
        for p in criados["produtos"]:
            if p:
                chamar("DELETE", f"/produtos/{p}", token=token)
    except Exception:
        pass


atexit.register(_limpar)

st, locais = chamar("GET", "/locais", token=token)
local = next((x for x in (locais or []) if x.get("principal")), (locais or [{}])[0])
st, forns = chamar("GET", "/fornecedores?limite=1", token=token)
fornecedor = (forns or [{}])[0]


print("1. os dois cadastros, como o fornecedor os manda")
# O principal: cadastro completo, unidade de estoque em KG — a MEDIDA, nunca a
# embalagem. Com o estoque contado em pacotes, o de 500 g nao teria como ser
# representado e a ficha, que consome em gramas, nao fecharia.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ACU1-{marca}", "nome": f"ACUCAR CONFEITEIRO 1KG {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "status": "ATIVO", "codigo_omie": f"AC1{marca}",
}, token=token)
principal = (r or {}).get("id")
criados["produtos"].append(principal)

# ⚠️ **O de 500 g fica CRU de proposito** — sem unidade de compra, sem fator,
# sem nada. E a pergunta do dono: "nao cadastrei a unidade de compra nele".
st, r = chamar("POST", "/produtos", {
    "codigo": f"ACU5-{marca}", "nome": f"ACUCAR CONFEITEIRO 500G {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True,
    "status": "ATIVO", "codigo_omie": f"AC5{marca}",
}, token=token)
meio = (r or {}).get("id")
criados["produtos"].append(meio)
checar("os dois cadastros nascem", bool(principal and meio), (principal, meio))


print("\n2. o vinculo, e a conversao dita na tela do principal")
st, r = chamar("POST", f"/produtos/{principal}/vincular", {"id_sai": meio}, token=token)
checar("a fusao acontece", st == 200, (st, r))
# 🔑 O codigo do absorvido vira APELIDO do principal — e sem isso a nota dele nao
# acharia dono, cairia na fila de pendencias e quem clicasse em "criar produto"
# recriaria o duplicado.
checar("e o codigo do de 500 g vira apelido do principal",
       (r or {}).get("apelido_omie") == f"AC5{marca}", r)

st, p = chamar("GET", f"/produtos/{principal}", token=token)
apelido = next((c for c in (p.get("codigos_externos") or [])
                if c["codigo"] == f"AC5{marca}"), None)
checar("o apelido aparece na tela do principal", apelido is not None,
       p.get("codigos_externos"))
checar("com a conversao ainda NAO informada",
       apelido and apelido.get("fator_confirmado") is False, apelido)

st, r = chamar("PUT", f"/produtos/{principal}/codigos/conversao",
               {"sistema": "OMIE_PRODUTO", "codigo": f"AC5{marca}", "fator": 0.5},
               token=token)
checar("informar que 1 unidade dele vale 0,5 KG responde", st == 200, (st, r))


def _nota_com_codigo_omie(numero, codigo_omie, quantidade, um, valor=10):
    """Uma nota cujo item chega SEM produto e com o identificador do Omie.

    ⚠️ O item digitado a mao nao tem `codigo_omie` — quem o preenche e a
    importacao do Omie. Aqui ele e posto direto na coluna, que existe para isso,
    e TODO o resto passa pelo caminho de verdade: reconciliar, calcular e
    lancar. Simular a importacao inteira exigiria fixture propria e mediria a
    importacao, nao a conversao.
    """
    st, r = chamar("POST", "/notas", {
        "id_fornecedor": (fornecedor or {}).get("id"),
        "numero": numero, "id_local": local.get("id"),
        "itens": [{"descricao": f"ACUCAR CONF PCT {marca}",
                   "codigo_fornecedor": f"F{numero}",
                   "quantidade": quantidade, "um": um, "valor_unitario": valor}],
    }, token=token)
    id_nota = (r or {}).get("id")
    from database import get_cursor  # noqa: E402

    with get_cursor() as cur:
        cur.execute("UPDATE nota_itens SET codigo_omie = %s WHERE id_nota = %s",
                    (codigo_omie, id_nota))
    chamar("POST", "/notas/reconciliar", {"id_nota": id_nota}, token=token)
    return id_nota


from database import init_pool  # noqa: E402

init_pool()

print("\n3. a nota chega em UNIDADE — o caso do dono")
nota_un = _nota_com_codigo_omie(f"AC{marca}", f"AC5{marca}", 4, "UN")
st, n = chamar("GET", f"/notas/{nota_un}", token=token)
item = (n.get("itens") or [{}])[0]
# 🔑 **Ele se acha**: o apelido da fusao e o que leva o item ao principal, mesmo
# com o cadastro do absorvido arquivado.
checar("o item encontra o PRINCIPAL sozinho", item.get("id_produto") == principal,
       (item.get("id_produto"), principal))
# 🔑 **E converte**: 4 UN x 0,5 = 2 KG.
checar("e 4 UN viram 2 KG pela conversao dita",
       perto(item.get("quantidade_convertida"), 2), item.get("quantidade_convertida"))

st, r = chamar("POST", f"/notas/{nota_un}/lancar", {}, token=token)
checar("a nota lanca", st == 200, (st, r))
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={principal}", token=token)
entrada = next((m for m in (movs or []) if m["tipo"] == "ENTRADA_NF"), None)
# A prova final: o que entrou no RAZAO, que e a unica memoria do estoque.
checar("e o razao recebe 2 KG, nao 4", entrada and perto(entrada["quantidade"], 2),
       entrada and entrada.get("quantidade"))


print("\n4. a nota chega em KG — a unidade da propria casa")
# ⚠️ **Aqui o fator NAO se aplica, e e deliberado.** Dizer "4 KG" ja e dizer
# quilos; aplicar o 0,5 transformaria 4 kg em 2 kg. A checagem da unidade igual
# vem ANTES do fator, de proposito.
nota_kg = _nota_com_codigo_omie(f"AK{marca}", f"AC5{marca}", 4, "KG")
st, n2 = chamar("GET", f"/notas/{nota_kg}", token=token)
item2 = (n2.get("itens") or [{}])[0]
checar("o item tambem encontra o principal", item2.get("id_produto") == principal,
       item2.get("id_produto"))
checar("mas 4 KG continuam 4 KG — o fator nao se aplica",
       perto(item2.get("quantidade_convertida"), 4), item2.get("quantidade_convertida"))


print("\n5. sem a marca, a conversao nao vale")
# 🔑 O fator 1 que a fusao deixa em cada apelido e a AUSENCIA de resposta, nao
# uma resposta. Aceita-lo faria toda fusao encobrir o fator de compra do
# produto — foi assim que o azeite de 5 L virou 1 L na segunda nota.
from database import get_cursor  # noqa: E402

with get_cursor() as cur:
    cur.execute("""UPDATE codigos_externos SET fator_confirmado = false
                    WHERE sistema = 'OMIE_PRODUTO' AND codigo = %s""", (f"AC5{marca}",))
nota_sem = _nota_com_codigo_omie(f"AS{marca}", f"AC5{marca}", 4, "UN")
st, n3 = chamar("GET", f"/notas/{nota_sem}", token=token)
item3 = (n3.get("itens") or [{}])[0]
checar("sem a marca, 4 UN NAO viram 2 KG",
       not perto(item3.get("quantidade_convertida"), 2),
       item3.get("quantidade_convertida"))


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
