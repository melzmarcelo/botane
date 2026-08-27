"""Teste de fumaça do vínculo entre cadastros: o botão Vincular e a fusão.

O sistema recebe produto por três portas — o catálogo do **Omie** (o que a casa
compra), o cardápio do **PDV Legal** (o que a casa vende) e a mão de quem
cadastra. Nenhuma chave impede o mesmo produto de existir duas vezes.

⚠️ **Nada aqui adivinha, e o par que motivou isso está no teste.** Existiu um
detector que cruzava os nomes por semelhança, e ele errava nos dois sentidos:
não achava "BEB CERV HEINEKEN 350ML" contra "CERVEJA HEINEKEN PILSEN" — o mesmo
produto, **63,8%** de semelhança — e juntava "CAKE BOARD N19" com "CAKE BOARD
N21", que são tamanhos diferentes. Nenhum piso separa os dois casos, porque a
diferença não está no texto.

O que este arquivo cobra:

1. `codigo_pdv` é campo do produto, espelho do `codigo_omie`, e **único**
2. a prévia mostra o resultado ANTES — fusão não tem desfazer
3. **a descrição vem do lado do Omie e a curta do lado do PDV**
4. os campos em branco se completam; os preenchidos NÃO são sobrescritos
5. os códigos das duas integrações migram para o mesmo cadastro
6. **dois códigos do PDV viram principal + apelido**, porque o caso é real
7. quem tem história não é absorvido, e a recusa nomeia o que trava
8. os itens de venda mudam de dono e o que estava sem custo ganha custo
9. o absorvido vira **inativo**, nunca apagado

    python tests/smoke_vinculo.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_locais  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns())[-6:]
hoje = date.today().isoformat()
garantir_locais(chamar, token)

print("1. o mesmo produto entrando por duas portas")
# ⚠️ Os nomes REAIS do caso do cliente. Nenhum detector honesto os junta.
st, r = chamar("POST", "/produtos", {
    "codigo": f"OM-{marca}", "nome": f"BEB CERV HEINEKEN 350ML {marca}",
    "tipo": "REVENDA", "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
    "codigo_omie": f"77{marca}", "ncm": "22030000",
}, token=token)
do_omie = r.get("id")
checar("o cadastro do lado do Omie", st == 201, (st, r))

st, r = chamar("POST", "/produtos", {
    "codigo": f"PDV-{marca}", "nome": f"CERVEJA HEINEKEN PILSEN {marca}",
    "tipo": "PRODUZIDO", "producao_propria": True, "controla_estoque": False,
    "status": "RASCUNHO", "codigo_pdv": f"99{marca}", "marca": "Heineken",
    "cest": "0300100",
}, token=token)
do_pdv = r.get("id")
checar("o cadastro do lado do cardápio", st == 201, (st, r))

st, p = chamar("GET", f"/produtos/{do_pdv}", token=token)
checar("`codigo_pdv` é campo do produto, como o `codigo_omie`",
       p.get("codigo_pdv") == f"99{marca}", p.get("codigo_pdv"))

# ⚠️ Único, como `ux_produto_omie`: dois cadastros com o mesmo código do PDV
# fariam a venda escolher um deles ao acaso.
st, r = chamar("POST", "/produtos", {
    "codigo": f"XX-{marca}", "nome": f"Colidente {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "status": "ATIVO", "codigo_pdv": f"99{marca}",
}, token=token)
checar("e é ÚNICO — o mesmo código não entra duas vezes", st >= 400, (st, r))

print("\n2. uma venda pelo cadastro do cardápio, sem custo")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"VINC-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": do_pdv, "quantidade": 4, "valor_unitario": 12}],
}]}, token=token)
checar("venda gravada", st == 201 and r.get("importadas") == 1, (st, r))
checar("e o item entrou SEM custo", r.get("itens_sem_custo") == 1, r)
# ⚠️ O cadastro do cardápio não controla estoque: é assim que o saldo do outro
# nunca desce, e a sobra vira "ajuste de inventário" na contagem.
checar("e sem baixar estoque", (r.get("itens_baixados") or 0) == 0, r)

print("\n3. a prévia — fusão não tem desfazer")
st, prev = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai={do_pdv}", token=token)
checar("a prévia responde", st == 200, (st, prev))
checar("e diz que pode", prev.get("pode") is True, prev.get("impedimentos"))
res = prev.get("resultado") or {}
# ⚠️ A afirmação central: os dois nomes têm funções diferentes. O do Omie é o
# fiscal, o que aparece na nota; o do PDV é o que sai no cupom.
checar("a descrição vem do lado do OMIE",
       res.get("nome") == f"BEB CERV HEINEKEN 350ML {marca}", res.get("nome"))
checar("e a descrição curta do lado do PDV",
       res.get("nome_curto") == f"CERVEJA HEINEKEN PILSEN {marca}", res.get("nome_curto"))
checar("a prévia diz de onde veio cada uma",
       (res.get("de_onde") or {}).get("nome") == "omie"
       and (res.get("de_onde") or {}).get("nome_curto") == "pdv", res.get("de_onde"))
checar("os dois códigos ficam no mesmo cadastro",
       res.get("codigo_omie") == f"77{marca}" and res.get("codigo_pdv") == f"99{marca}", res)
checar("e lista os campos que vão ser completados",
       set(prev.get("completa") or []) >= {"marca", "cest"}, prev.get("completa"))
checar("dizendo quantos itens de venda mudam de dono",
       prev.get("itens_de_venda") == 1, prev.get("itens_de_venda"))

st, r = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai={do_omie}", token=token)
checar("conferir consigo mesmo é recusado", st == 400, st)
st, r = chamar("GET", f"/produtos/{do_omie}/vincular/previa?id_sai=99999999", token=token)
checar("cadastro inexistente é 404", st == 404, st)

print("\n4. a recusa: história não muda de cadastro")
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": do_omie, "quantidade": 6, "custo_unitario": 5,
    "id_local": principal["id"], "documento": f"VINC-{marca}",
}, token=token)
checar("o lado do Omie ganha movimento no razão", st == 201, (st, r))

st, r = chamar("POST", f"/produtos/{do_pdv}/vincular", {"id_sai": do_omie}, token=token)
checar("absorver quem tem movimento é recusado", st == 409, (st, r))
checar("e a recusa NOMEIA o que trava", "append-only" in str(r.get("detail", "")), r)
checar("mandando fazer ao contrário", "ao contrário" in str(r.get("detail", "")), r)

print("\n5. a fusão, na direção certa")
st, r = chamar("POST", f"/produtos/{do_omie}/vincular", {"id_sai": do_pdv}, token=token)
checar("vincular responde", st == 200, (st, r))
checar("moveu o item de venda", r.get("itens_de_venda") == 1, r)
checar("e ele ganhou custo (o do Omie tem custo médio)",
       r.get("itens_que_ganharam_custo") == 1, r)
checar("completou marca e cest", set(r.get("completados") or []) >= {"marca", "cest"}, r)

st, fica = chamar("GET", f"/produtos/{do_omie}", token=token)
checar("a descrição ficou a do Omie",
       fica.get("nome") == f"BEB CERV HEINEKEN 350ML {marca}", fica.get("nome"))
checar("a curta ficou a do PDV",
       fica.get("nome_curto") == f"CERVEJA HEINEKEN PILSEN {marca}", fica.get("nome_curto"))
checar("o código do PDV migrou", fica.get("codigo_pdv") == f"99{marca}", fica.get("codigo_pdv"))
checar("o do Omie continua", fica.get("codigo_omie") == f"77{marca}", fica.get("codigo_omie"))
# ⚠️ Não sobrescreve: o NCM era do cadastro que fica e continua sendo dele.
checar("o que já estava preenchido NÃO foi sobrescrito",
       fica.get("ncm") == "22030000", fica.get("ncm"))
checar("marca veio do que saiu", fica.get("marca") == "Heineken", fica.get("marca"))

st, saiu = chamar("GET", f"/produtos/{do_pdv}", token=token)
checar("o absorvido virou inativo, não sumiu",
       saiu.get("ativo") is False and saiu.get("status") == "ARQUIVADO",
       (saiu.get("ativo"), saiu.get("status")))
checar("e a observação diz para onde ele foi",
       "Fundido em" in (saiu.get("observacao") or ""), saiu.get("observacao"))
checar("e ele perdeu o código do PDV, que agora é do outro",
       saiu.get("codigo_pdv") is None, saiu.get("codigo_pdv"))

print("\n6. dois códigos do PDV: principal e apelido")
# ⚠️ **O caso é REAL**: "ENTREGA" tem QUATRO códigos de cardápio distintos na
# conta do cliente. Uma coluna sozinha guardaria um, e os outros voltariam a
# virar rascunho na importação seguinte — o duplicado renascendo sozinho.
st, r = chamar("POST", "/produtos", {
    "codigo": f"PDV2-{marca}", "nome": f"HEINEKEN LONG NECK {marca}",
    "tipo": "PRODUZIDO", "producao_propria": True, "controla_estoque": False,
    "status": "RASCUNHO", "codigo_pdv": f"88{marca}",
}, token=token)
outro_pdv = r.get("id")
checar("um segundo cadastro do cardápio", st == 201, (st, r))

st, r = chamar("POST", f"/produtos/{do_omie}/vincular", {"id_sai": outro_pdv}, token=token)
checar("a fusão aceita, mesmo com os dois tendo código do PDV", st == 200, (st, r))
checar("e o segundo código virou APELIDO", r.get("apelido_pdv") == f"88{marca}", r)

st, fica = chamar("GET", f"/produtos/{do_omie}", token=token)
checar("o principal continua sendo o primeiro",
       fica.get("codigo_pdv") == f"99{marca}", fica.get("codigo_pdv"))
checar("e o apelido aparece na tela do produto",
       f"88{marca}" in (fica.get("apelidos_pdv") or []), fica.get("apelidos_pdv"))

# ⚠️ O que importa de verdade: a venda que chegar com o APELIDO acha o produto.
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"VINC2-{marca}", "origem": "PDV_LEGAL",
    "itens": [{"codigo": f"88{marca}", "descricao": "Long neck",
               "quantidade": 2, "valor_unitario": 14}],
}]}, token=token)
# O importador de vendas resolve por `codigo` da casa e por nome; o de-para do
# PDV é aplicado pelo importador do PDV. Aqui a checagem é a da fila:
st, fila = chamar("GET", "/vendas/sem-vinculo", token=token)
st, rec = chamar("POST", "/pdv/reconciliar", token=token)
checar("a reconciliação acha o produto pelo apelido",
       (rec.get("vinculados") or 0) >= 1, rec)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
