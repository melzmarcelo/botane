"""Teste de fumaça: lançar de uma vez as notas conciliadas, com prévia.

O cenário, cinco notas desta rodada:

    A, B  digitadas e prontas             -> a prévia diz "pronta"; o lote lança
    C     aponta para produto ARQUIVADO   -> "travada", com a frase do lançamento
    D     XML que declara CX = 24 UN,     -> "conferir": o lote NÃO lança
          e o cadastro usaria outro fator
    E     pronta, mas fora dos `ids`      -> fica como estava

Prova o que sustenta a ideia: a prévia NÃO grava nada (o ensaio é desfeito), o
lote lança só as prontas, uma recusada não desfaz as outras, e quem não tem
`compras.lancar` não passa.

⚠️ **Sempre com `ids`.** A base local pode ter outras notas conciliadas (as do
Omie de verdade), e um lote sem `ids` lançaria todas elas.

    python tests/smoke_notas_lote.py       (API de pé na 9200)
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
HOJE = datetime.date.today().isoformat()


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def enviar_xml(nome, conteudo, token):
    limite = f"----lote{uuid.uuid4().hex}"
    corpo = (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="arquivos"; filename="{nome}"\r\n'
        "Content-Type: text/xml\r\n\r\n"
    ).encode() + conteudo.encode("utf-8") + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(BASE + "/notas/importar-xml", method="POST", data=corpo)
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
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


def xml_caixa(chave, numero, ean):
    """Uma NF-e de 1 CX que o emitente declara valer 24 UN (`qTrib/qCom`)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><cUF>42</cUF><nNF>{numero}</nNF><serie>1</serie><mod>55</mod>
         <dhEmi>{HOJE}T09:30:00-03:00</dhEmi></ide>
    <emit><CNPJ>12345678000177</CNPJ><xNome>Distribuidora Lote {marca} LTDA</xNome>
          <enderEmit><xMun>Blumenau</xMun><UF>SC</UF></enderEmit></emit>
    <dest><CNPJ>11222333000181</CNPJ><xNome>Casa de Teste</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>LT{marca}</cProd><cEAN>{ean}</cEAN><xProd>REFRIGERANTE LOTE {marca}</xProd>
          <NCM>22021000</NCM><CFOP>5102</CFOP><uCom>CX</uCom>
          <qCom>1.0000</qCom><vUnCom>48.0000</vUnCom>
          <vProd>48.00</vProd><vFrete>0.00</vFrete>
          <cEANTrib>{ean}</cEANTrib><uTrib>UN</uTrib><qTrib>24.0000</qTrib>
          <vUnTrib>2.0000</vUnTrib><indTot>1</indTot>
        </prod>
        <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vICMS>0.00</vICMS></ICMS00></ICMS></imposto>
      </det>
    <total><ICMSTot><vProd>48.00</vProd><vFrete>0.00</vFrete>
      <vDesc>0.00</vDesc><vIPI>0.00</vIPI><vST>0.00</vST><vOutro>0.00</vOutro>
      <vNF>48.00</vNF></ICMSTot></total>
  </infNFe></NFe>
</nfeProc>"""


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
local = garantir_local(chamar, token)
st, fornecedores = chamar("GET", "/fornecedores?limite=1", token=token)
fornecedor = fornecedores[0]

produtos, notas = [], []


def produto(nome, **extra):
    st, p = chamar("POST", "/produtos", {
        "codigo": f"LT{len(produtos)}-{marca}", "nome": f"{nome} {marca}", "tipo": "INSUMO",
        "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", **extra}, token=token)
    produtos.append(p["id"])
    return p["id"]


def nota_digitada(letra, id_produto, quantidade=10, unitario=5):
    st, n = chamar("POST", "/notas", {
        "id_fornecedor": fornecedor["id"], "numero": f"L{letra}{marca}", "serie": "1",
        "data_emissao": HOJE, "id_local": local["id"],
        "itens": [{"id_produto": id_produto, "quantidade": quantidade,
                   "valor_unitario": unitario}]}, token=token)
    assert st == 200, (st, n)
    notas.append(n["id"])
    return n["id"]


def saldo(id_produto):
    st, linhas = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    return sum(float(x.get("quantidade") or 0) for x in (linhas or [])
               if x.get("id_produto") == id_produto)


print("1. o cenário")
p_a, p_b, p_c, p_e = produto("Lote A"), produto("Lote B"), produto("Lote C"), produto("Lote E")
ean = f"789{marca}0019"[:13].ljust(13, "0")
p_d = produto("Refrigerante Lote", codigo_barras=ean)
id_a, id_b = nota_digitada("A", p_a), nota_digitada("B", p_b, quantidade=4, unitario=2.5)
id_c, id_e = nota_digitada("C", p_c), nota_digitada("E", p_e)
# C: o produto é arquivado DEPOIS de a nota apontar para ele — o caso da fusão.
chamar("DELETE", f"/produtos/{p_c}", token=token)

chave = f"42{marca}12345678000177550010000{marca}1{marca}"[:44].ljust(44, "0")
st, r = enviar_xml(f"lote{marca}.xml", xml_caixa(chave, marca[-5:], ean), token)
res = ((r or {}).get("resultados") or [{}])[0]
id_d = res.get("id_nota") or res.get("id")
checar("o XML entra e casa pelo EAN", st == 200 and bool(id_d) and not res.get("pendentes"),
       (st, r))
if id_d:
    notas.append(id_d)
minhas = [id_a, id_b, id_c, id_d, id_e]

print("\n2. a prévia classifica, e NÃO grava")
st, previa = chamar("GET", "/notas/lote/previa", token=token)
checar("a prévia responde", st == 200, (st, previa))
por_id = {n["id"]: n for n in (previa or {}).get("notas", [])}
checar("A e B estão prontas",
       por_id.get(id_a, {}).get("situacao") == "pronta"
       and por_id.get(id_b, {}).get("situacao") == "pronta",
       (por_id.get(id_a), por_id.get(id_b)))
checar("e a pronta diz quanto entra no estoque: 10 x 5,00 = 50,00",
       abs((por_id.get(id_a, {}).get("valor_estoque") or 0) - 50) < 0.01, por_id.get(id_a))
checar("C está travada, com a frase do lançamento",
       por_id.get(id_c, {}).get("situacao") == "travada" and bool(por_id[id_c].get("motivo")),
       por_id.get(id_c))
checar("D pede conferência: a nota declara outra conversão",
       por_id.get(id_d, {}).get("situacao") == "conferir", por_id.get(id_d))
resumo = (previa or {}).get("resumo", {})
checar("o resumo soma por situação",
       resumo.get("pronta", {}).get("notas", 0) >= 3
       and resumo.get("travada", {}).get("notas", 0) >= 1
       and resumo.get("conferir", {}).get("notas", 0) >= 1, resumo)

st, nota_a = chamar("GET", f"/notas/{id_a}", token=token)
checar("depois da prévia a nota A continua aberta", nota_a.get("status") != "LANCADA",
       nota_a.get("status"))
checar("e nada entrou no estoque", saldo(p_a) == 0, saldo(p_a))
st, de_novo = chamar("GET", "/notas/lote/previa", token=token)
checar("pedir a prévia duas vezes dá a mesma resposta",
       {n["id"]: n["situacao"] for n in de_novo["notas"] if n["id"] in minhas}
       == {i: por_id[i]["situacao"] for i in minhas if i in por_id})

print("\n3. o lote lança só as prontas que foram pedidas")
st, r = chamar("POST", "/notas/lote/lancar", {"ids": [id_a, id_b, id_c, id_d]}, token=token)
checar("o lote responde", st == 200, (st, r))
lancadas = {n["id"] for n in (r or {}).get("lancadas", [])}
fora = {n["id"]: n for n in (r or {}).get("fora", [])}
checar("lançou A e B, e só elas", lancadas == {id_a, id_b}, lancadas)
checar("soma os itens e o valor: 50,00 + 10,00 = 60,00",
       r.get("notas") == 2 and r.get("itens") == 2 and abs(r.get("valor", 0) - 60) < 0.01, r)
checar("C ficou de fora com o motivo", fora.get(id_c, {}).get("situacao") == "travada", fora)
checar("D ficou de fora: conferência é de gente, nem a pedido o lote lança",
       fora.get(id_d, {}).get("situacao") == "conferir", fora)
checar("a recusa de C não desfez A: o saldo entrou", saldo(p_a) == 10 and saldo(p_b) == 4,
       (saldo(p_a), saldo(p_b)))
st, nota_a = chamar("GET", f"/notas/{id_a}", token=token)
checar("A virou LANCADA", nota_a.get("status") == "LANCADA", nota_a.get("status"))
st, nota_e = chamar("GET", f"/notas/{id_e}", token=token)
checar("E, que não foi pedida, continua aberta e fora do estoque",
       nota_e.get("status") != "LANCADA" and saldo(p_e) == 0, nota_e.get("status"))
st, nota_d = chamar("GET", f"/notas/{id_d}", token=token)
checar("D continua aberta", nota_d.get("status") != "LANCADA", nota_d.get("status"))

print("\n4. repetir não lança em dobro")
st, r2 = chamar("POST", "/notas/lote/lancar", {"ids": [id_a, id_b]}, token=token)
checar("o segundo pedido não lança nada", st == 200 and r2.get("notas") == 0, (st, r2))
checar("e o saldo é o mesmo", saldo(p_a) == 10, saldo(p_a))
st, previa3 = chamar("GET", "/notas/lote/previa", token=token)
checar("A e B saíram da prévia",
       not ({id_a, id_b} & {n["id"] for n in previa3["notas"]}))

print("\n5. a auditoria registra cada nota do lote")
st, hist = chamar("GET", f"/auditoria?entidade=nota&id_entidade={id_a}", token=token)
linhas = hist if isinstance(hist, list) else (hist or {}).get("linhas", [])
checar("a nota A tem a linha de lançamento",
       any(x.get("acao") == "lancar" for x in linhas), (st, str(hist)[:200]))

print("\n6. quem não lança nota não lança lote")
cozinha = garantir_cozinha(chamar, token)
st, _ = chamar("GET", "/notas/lote/previa", token=cozinha)
checar("a cozinha não vê a prévia", st == 403, st)
st, _ = chamar("POST", "/notas/lote/lancar", {"ids": [id_e]}, token=cozinha)
checar("nem lança", st == 403, st)
checar("e a nota E segue fora do estoque", saldo(p_e) == 0, saldo(p_e))

print("\n7. limpeza")
for id_nota in (id_a, id_b):
    chamar("POST", f"/notas/{id_nota}/estornar", {}, token=token)
for id_nota in notas:
    chamar("DELETE", f"/notas/{id_nota}", token=token)
for id_produto in produtos:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
checar("o estorno devolveu o saldo de A", saldo(p_a) == 0, saldo(p_a))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
