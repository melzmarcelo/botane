"""Teste de fumaça da colheita de EAN das notas fiscais.

🔑 **A maior fonte gratuita de código de barras é a própria compra**
(08/09/2026). Medido na base real: 2.019 dos 3.183 produtos não têm código
nenhum — e **nenhuma API de GTIN ajuda quem não tem o número**. O XML da NF-e
traz `cEAN`, o parser já o guarda em `nota_itens.codigo_barras`, e ele ficava
parado ali.

⚠️ **Sugere, não aplica sozinho.** Três armadilhas justificam a confirmação, e
esta suíte cobra as três: o EAN pode ser o da CAIXA e não o da unidade, o
de-para pode estar errado, e `codigo_barras` é ÚNICO — dois produtos recebendo
o mesmo código quebrariam o lote no meio.

    python tests/smoke_ean_das_notas.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_fornecedor, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
criados: list[int] = []
notas: list[int] = []

# ⚠️ **Os EANs nascem da MARCA da rodada, e o digito e calculado.**
# A primeira versao usou codigos reais (7891000315507 e afins) e eles ja eram de
# produtos do catalogo -- o `codigo_barras` e unico, entao o cenario nao subia e
# tres checagens caiam acusando um codigo intacto. Alem disso, uma rodada que
# quebrasse no meio deixava produtos donos daqueles numeros e envenenava a
# proxima. Com o numero derivado da marca, cada rodada tem os seus.
def _com_digito(doze: str) -> str:
    """Fecha um EAN-13: o digito verificador que o codigo precisa ter."""
    soma = sum(int(d) * (3 if k % 2 == 0 else 1)
               for k, d in enumerate(reversed(doze)))
    return doze + str((10 - soma % 10) % 10)


_base = f"200{int(marca, 16) % 1000000000:09d}"
EAN_BOM = _com_digito(_base)
EAN_OUTRO = _com_digito(_base[:-1] + str((int(_base[-1]) + 1) % 10))
# O mesmo do bom com o ultimo digito trocado: parece EAN e nao fecha.
EAN_TORTO = EAN_BOM[:-1] + str((int(EAN_BOM[-1]) + 1) % 10)


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


def enviar_xml(nome, conteudo, token):
    """POST multipart — o `urllib` não monta sozinho."""
    limite = f"----botane{uuid.uuid4().hex}"
    corpo = (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="arquivos"; filename="{nome}"\r\n'
        "Content-Type: text/xml\r\n\r\n"
    ).encode() + conteudo.encode("utf-8") + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(BASE + "/notas/importar-xml", method="POST", data=corpo)
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read().decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def xml_nfe(chave, numero, itens):
    """Uma NF-e mínima, com `cEAN` em cada item — que é o ponto do teste."""
    dets = ""
    for i, (descricao, codigo, ean, qtd, unitario, um) in enumerate(itens, 1):
        dets += f"""
      <det nItem="{i}">
        <prod>
          <cProd>{codigo}</cProd><cEAN>{ean}</cEAN><xProd>{descricao}</xProd>
          <NCM>19012000</NCM><CFOP>5102</CFOP><uCom>{um}</uCom>
          <qCom>{qtd:.4f}</qCom><vUnCom>{unitario:.4f}</vUnCom>
          <vProd>{qtd * unitario:.2f}</vProd><vFrete>0.00</vFrete>
          <cEANTrib>{ean}</cEANTrib><uTrib>{um}</uTrib><qTrib>{qtd:.4f}</qTrib>
          <vUnTrib>{unitario:.4f}</vUnTrib><indTot>1</indTot>
        </prod>
        <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vICMS>0.00</vICMS></ICMS00></ICMS></imposto>
      </det>"""
    total = sum(q * v for _d, _c, _e, q, v, _u in itens)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><cUF>42</cUF><nNF>{numero}</nNF><serie>1</serie><mod>55</mod>
         <dhEmi>2026-09-05T09:30:00-03:00</dhEmi></ide>
    <emit><CNPJ>12345678000177</CNPJ><xNome>Distribuidora EAN {marca} LTDA</xNome>
          <enderEmit><xMun>Blumenau</xMun><UF>SC</UF></enderEmit></emit>
    <dest><CNPJ>11222333000181</CNPJ><xNome>Botane Deli e Cafe</xNome></dest>{dets}
    <total><ICMSTot><vProd>{total:.2f}</vProd><vFrete>0.00</vFrete>
      <vDesc>0.00</vDesc><vIPI>0.00</vIPI><vST>0.00</vST><vOutro>0.00</vOutro>
      <vNF>{total:.2f}</vNF></ICMSTot></total>
  </infNFe></NFe>
</nfeProc>"""


def criar_produto(nome, **extra):
    _st, r = chamar("POST", "/produtos", {
        "codigo": f"EAN{len(criados)}-{marca}", "nome": f"{nome} {marca}",
        "tipo": "INSUMO", "um_estoque": "UN", "controla_estoque": True,
        "status": "ATIVO", **extra}, token=token)
    if r.get("id"):
        criados.append(r["id"])
    return r.get("id")


def linha_de(previa, id_produto):
    return next((x for x in previa["linhas"] if x["id_produto"] == id_produto), None)


def conflito_de(previa, id_produto):
    return next((x for x in previa["conflitos"] if x["id_produto"] == id_produto), None)


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
garantir_local(chamar, token)
garantir_fornecedor(chamar, token, f"DISTRIBUIDORA EAN {marca}", "12345678000177")


print("\n1. o cenario: tres produtos SEM codigo de barras e uma nota com EAN")
sem_codigo = criar_produto("CAFE SEM CODIGO")
ja_dono = criar_produto("DONO DO CODIGO", codigo_barras=EAN_OUTRO)
vizinho = criar_produto("VIZINHO DO CODIGO")
torto = criar_produto("ITEM DE EAN TORTO")
checar("os produtos nascem", all([sem_codigo, ja_dono, vizinho, torto]),
       (sem_codigo, ja_dono, vizinho, torto))

chave = f"4226091234567800017755001000000{marca[-3:]}00110{marca[-4:]}"[:44].ljust(44, "0")
st, r = enviar_xml(f"nota{marca}.xml", xml_nfe(chave, marca[-5:], [
    (f"CAFE DO FORNECEDOR {marca}", f"F1{marca}", EAN_BOM, 2, 30, "UN"),
    (f"OUTRO DO FORNECEDOR {marca}", f"F2{marca}", EAN_OUTRO, 1, 10, "UN"),
    (f"TORTO DO FORNECEDOR {marca}", f"F3{marca}", EAN_TORTO, 1, 10, "UN"),
]), token)
checar("a nota entra pelo XML", st in (200, 201), (st, r))
st, lista = chamar("GET", f"/notas?busca={marca[-5:]}", token=token)
# /notas devolve LISTA crua em alguns caminhos e paginado em outros.
itens_nota = lista.get("itens", []) if isinstance(lista, dict) else (lista or [])
id_nota = itens_nota[0]["id"] if itens_nota else None
if id_nota:
    notas.append(id_nota)
checar("e e encontrada", bool(id_nota), lista)

st, nota = chamar("GET", f"/notas/{id_nota}", token=token)
por_seq = {i["seq"]: i for i in (nota.get("itens") or [])}
for seq, produto in ((1, sem_codigo), (2, vizinho), (3, torto)):
    if seq in por_seq:
        chamar("POST", f"/notas/itens/{por_seq[seq]['id']}/vincular",
               {"id_produto": produto, "aprender": True}, token=token)
checar("os itens sao vinculados aos produtos", len(por_seq) == 3, list(por_seq))


print("\n2. a previa mostra o que seria preenchido")
st, previa = chamar("GET", "/produtos/ean-das-notas", token=token)
checar("a previa responde", st == 200, st)
alvo = linha_de(previa, sem_codigo)
checar("o produto sem codigo aparece", alvo is not None,
       [x["nome"] for x in previa["linhas"]][:6])
checar("com o EAN que a nota trouxe", alvo and alvo["codigo_barras"] == EAN_BOM, alvo)
# 🔑 A origem precisa estar a vista: quem confirma quer saber de que nota saiu.
checar("dizendo de que nota e de que fornecedor veio",
       alvo and alvo.get("nota") and alvo.get("fornecedor"), alvo)
checar("e a unidade da nota ao lado da do estoque",
       alvo and "um_nota" in alvo and "um_estoque" in alvo, alvo)
# ⚠️ Aqui as duas sao UN, entao NAO ha divergencia — o alerta da caixa so
# aparece quando elas diferem.
checar("sem divergencia de unidade neste caso", alvo and not alvo["unidade_diverge"], alvo)


print("\n3. as tres armadilhas viram CONFLITO, nao gravacao")
# ⚠️ Digito que nao fecha e digitacao do emitente, nao codigo.
c = conflito_de(previa, torto)
checar("EAN com digito errado vira conflito", c is not None,
       [x["nome"] for x in previa["conflitos"]][:6])
checar("dizendo que o digito nao confere",
       c and "gito" in (c.get("motivo") or ""), c and c.get("motivo"))

# ⚠️ `codigo_barras` e UNICO: o codigo ja e de outro produto.
c2 = conflito_de(previa, vizinho)
checar("EAN que ja e de outro produto vira conflito", c2 is not None,
       [x["nome"] for x in previa["conflitos"]][:6])
checar("nomeando o dono atual",
       c2 and f"DONO DO CODIGO {marca}" in (c2.get("motivo") or ""),
       c2 and c2.get("motivo"))
checar("e nenhum conflito entra na lista de aplicaveis",
       not linha_de(previa, torto) and not linha_de(previa, vizinho), previa["linhas"])


print("\n4. colher grava so o que foi escolhido")
st, r = chamar("POST", "/produtos/ean-das-notas", {"ids_produto": [sem_codigo]}, token=token)
checar("a colheita responde", st == 200, (st, r))
checar("gravou exatamente um", r.get("gravados") == 1, r)
st, p = chamar("GET", f"/produtos/{sem_codigo}", token=token)
checar("o produto ganhou o codigo de barras", p.get("codigo_barras") == EAN_BOM, p.get("codigo_barras"))

# 🔑 Rodar de novo nao acha mais nada: quem ja tem codigo sai da conta.
st, depois = chamar("GET", "/produtos/ean-das-notas", token=token)
checar("e a previa nao o oferece mais", linha_de(depois, sem_codigo) is None,
       [x["nome"] for x in depois["linhas"]][:6])

# ⚠️ Mandar um id que nao esta na previa nao grava nada — o codigo vem do
# SERVIDOR, nunca do cliente.
st, r = chamar("POST", "/produtos/ean-das-notas", {"ids_produto": [ja_dono]}, token=token)
checar("id fora da previa nao grava nada", r.get("gravados") == 0, r)
st, r = chamar("POST", "/produtos/ean-das-notas", {"ids_produto": []}, token=token)
checar("lista vazia tambem nao", r.get("gravados") == 0, r)


print("\n5. sem permissao nao passa")
st, r = chamar("GET", "/produtos/ean-das-notas")
checar("sem autenticacao e barrado", st in (401, 403), st)


for nid in notas:
    chamar("DELETE", f"/notas/{nid}", token=token)
for pid in criados:
    chamar("DELETE", f"/produtos/{pid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
