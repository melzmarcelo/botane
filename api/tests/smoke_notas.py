"""Teste de fumaça das notas sem integração: XML da NF-e e digitação.

O cenário, conferido na mão:

    NF 9001 (XML) — 10 UN de farinha a 10,00, com 30,00 de frete NO ITEM
                    10 UN de açúcar  a 10,00, com  0,00 de frete
                    frete total 30,00

    O rateio por valor daria 15,00 para cada, porque os dois valem 100,00.
    Mas o emitente já rateou: 30,00 no primeiro, nada no segundo. Então o
    custo tem de sair 13,00 e 10,00 — se sair 11,50 nos dois, o sistema
    ignorou o que a nota dizia e inventou o próprio rateio.

    NF 9002 (digitada) — 5 KG a 8,00 (40,00) + 5 KG a 8,00 (40,00),
                    frete 20,00 sem rateio informado → 10,00 para cada,
                    custo (40 + 10) ÷ 5 = 10,00 por KG.

Prova também: a chave da NF-e impede o XML duplicado, o número + fornecedor
impede a nota digitada duplicada, arquivo errado é recusado com uma frase que
dá para mostrar na tela, e quem não tem `compras.notas` não entra por nenhuma
das duas portas.

    python tests/smoke_notas.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402
import uuid

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

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


def enviar_xmls(arquivos, token):
    """POST multipart — o `urllib` não monta sozinho, então monta-se na mão."""
    limite = f"----botane{uuid.uuid4().hex}"
    corpo = b""
    for nome, conteudo in arquivos:
        corpo += (
            f"--{limite}\r\n"
            f'Content-Disposition: form-data; name="arquivos"; filename="{nome}"\r\n'
            "Content-Type: text/xml\r\n\r\n"
        ).encode()
        corpo += (conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo)
        corpo += b"\r\n"
    corpo += f"--{limite}--\r\n".encode()

    req = urllib.request.Request(BASE + "/notas/importar-xml", method="POST", data=corpo)
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
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


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]

# A chave da NF-e tem 44 dígitos e é única — a marca da rodada entra nela para
# que a segunda execução importe de verdade em vez de bater no de-duplicador.
CHAVE = f"4226081234567800019555001000000900110000{marca[-4:]}"


def xml_nfe(chave, numero, itens, frete_total):
    dets = ""
    for i, (descricao, codigo, ean, qtd, unitario, frete_item, lote) in enumerate(itens, 1):
        rastro = (f"<rastro><nLote>{lote}</nLote><qLote>{qtd}</qLote>"
                  f"<dFab>2026-08-01</dFab><dVal>2027-08-01</dVal></rastro>" if lote else "")
        dets += f"""
      <det nItem="{i}">
        <prod>
          <cProd>{codigo}</cProd><cEAN>{ean}</cEAN><xProd>{descricao}</xProd>
          <NCM>19012000</NCM><CFOP>5102</CFOP><uCom>UN</uCom>
          <qCom>{qtd:.4f}</qCom><vUnCom>{unitario:.4f}</vUnCom>
          <vProd>{qtd * unitario:.2f}</vProd><vFrete>{frete_item:.2f}</vFrete>
          <cEANTrib>{ean}</cEANTrib><uTrib>UN</uTrib><qTrib>{qtd:.4f}</qTrib>
          <vUnTrib>{unitario:.4f}</vUnTrib><indTot>1</indTot>{rastro}
        </prod>
        <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vICMS>0.00</vICMS></ICMS00></ICMS></imposto>
      </det>"""
    produtos = sum(q * v for _d, _c, _e, q, v, _f, _l in itens)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><cUF>42</cUF><nNF>{numero}</nNF><serie>1</serie><mod>55</mod>
         <dhEmi>2026-08-16T09:30:00-03:00</dhEmi><dhSaiEnt>2026-08-16T14:00:00-03:00</dhSaiEnt>
    </ide>
    <emit><CNPJ>12345678000199</CNPJ><xNome>Distribuidora Teste {marca} LTDA</xNome>
          <enderEmit><xMun>Blumenau</xMun><UF>SC</UF></enderEmit></emit>
    <dest><CNPJ>11222333000181</CNPJ><xNome>Botane Deli e Cafe</xNome></dest>{dets}
    <total><ICMSTot><vProd>{produtos:.2f}</vProd><vFrete>{frete_total:.2f}</vFrete>
      <vDesc>0.00</vDesc><vIPI>0.00</vIPI><vST>0.00</vST><vOutro>0.00</vOutro>
      <vNF>{produtos + frete_total:.2f}</vNF></ICMSTot></total>
  </infNFe></NFe>
</nfeProc>"""


print("1. o XML da NF-e entra sem integração nenhuma")
ITENS = [
    (f"FARINHA TRIGO TIPO 1 {marca}", f"FAR-{marca}", "7890000000017", 10.0, 10.0, 30.0,
     f"LT{marca}"),
    (f"ACUCAR REFINADO {marca}", f"ACU-{marca}", "7890000000024", 10.0, 10.0, 0.0, None),
]
st, r = enviar_xmls([("nota9001.xml", xml_nfe(CHAVE, 9001, ITENS, 30.0))], token)
checar("importa o XML", st == 200 and r.get("novas") == 1, r)
resultado = (r.get("resultados") or [{}])[0]
id_nota = resultado.get("id")
checar("reconhece o fornecedor pelo emitente",
       (resultado.get("fornecedor") or "").startswith("Distribuidora Teste"), resultado)
checar("leu os dois itens", resultado.get("itens") == 2, resultado)
checar("os dois caem na fila de conciliação", resultado.get("pendentes") == 2, resultado)
checar("guardou a chave da NF-e", resultado.get("chave_nfe") == CHAVE, resultado.get("chave_nfe"))
checar("marcou a origem como XML", resultado.get("origem") == "XML", resultado)

st, nota = chamar("GET", f"/notas/{id_nota}", token=token)
checar("guardou o XML original para auditoria", nota.get("tem_xml") is True, nota.get("tem_xml"))
checar("mas não devolve o XML inteiro no JSON da tela", "xml_bruto" not in nota)
item1 = nota["itens"][0]
checar("leu o código de barras", item1["codigo_barras"] == "7890000000017", item1)
checar("leu o lote e a validade",
       item1["lote_nf"] == f"LT{marca}" and str(item1["validade_nf"]).startswith("2027-08-01"),
       (item1["lote_nf"], item1["validade_nf"]))
checar("leu o frete que o emitente pôs no item", perto(item1["frete_informado"], 30), item1)

print("2. o mesmo XML não entra duas vezes")
st, r = enviar_xmls([("nota9001-de-novo.xml", xml_nfe(CHAVE, 9001, ITENS, 30.0))], token)
checar("reconhece a nota repetida", r.get("novas") == 0 and r.get("repetidas") == 1, r)

print("3. arquivo errado é recusado com uma frase que dá para mostrar")
st, r = enviar_xmls([("recibo.xml", "<retEnviNFe><infRec><nRec>42</nRec></infRec></retEnviNFe>"),
                     ("danfe.pdf", "%PDF-1.4 nao sou xml"),
                     ("vazio.xml", "<nfeProc><NFe><infNFe Id='NFe1'></infNFe></NFe></nfeProc>")],
                    token)
erros = [x for x in r["resultados"] if x["status"] == "erro"]
checar("os três arquivos ruins são recusados", len(erros) == 3, r["resultados"])
checar("o recibo é identificado como recibo",
       "recibo" in (erros[0].get("erro") or "").lower(), erros[0])
checar("o PDF é identificado como não-XML",
       "XML válido" in (erros[1].get("erro") or ""), erros[1])
checar("a nota sem itens é recusada", "itens" in (erros[2].get("erro") or "").lower(), erros[2])
checar("um arquivo ruim não derruba o lote", st == 200, st)

print("4. conciliar e lançar — o frete do emitente vence o rateio")
st, farinha = chamar("POST", "/produtos", {
    "nome": f"Farinha XML {marca}", "tipo": "INSUMO", "um_estoque": "UN"}, token=token)
st, acucar = chamar("POST", "/produtos", {
    "nome": f"Acucar XML {marca}", "tipo": "INSUMO", "um_estoque": "UN"}, token=token)
st, nota = chamar("GET", f"/notas/{id_nota}", token=token)
for item, produto in zip(nota["itens"], (farinha["id"], acucar["id"])):
    st, r = chamar("POST", f"/notas/itens/{item['id']}/vincular",
                   {"id_produto": produto, "aprender": True}, token=token)
    checar(f"vincula o item {item['seq']}", st == 200, r)

st, nota = chamar("GET", f"/notas/{id_nota}", token=token)
custos = {i["seq"]: i["custo_aquisicao_unitario"] for i in nota["itens"]}
checar("item com frete informado custa 13,00 (não 11,50 do rateio por valor)",
       perto(custos[1], 13), custos)
checar("item sem frete custa os 10,00 da nota", perto(custos[2], 10), custos)
checar("a nota ficou conciliada", nota["status"] == "CONCILIADA", nota["status"])

local = garantir_local(chamar, token)
st, r = chamar("POST", f"/notas/{id_nota}/lancar", {"id_local": local["id"]}, token=token)
checar("lança os dois itens no estoque", st == 200 and r.get("itens_lancados") == 2, r)
checar("o valor lançado é 230,00 (200 de produto + 30 de frete)", perto(r.get("valor"), 230), r)

st, saldos = chamar("GET", f"/estoque/saldos?busca=Farinha XML {marca}", token=token)
saldo = (saldos or [{}])[0]
checar("o saldo entrou", perto(saldo.get("quantidade"), 10), saldo)
checar("o custo médio saiu com o frete dentro", perto(saldo.get("custo_medio"), 13), saldo)

print("5. o vínculo aprendido faz a próxima nota entrar sozinha")
CHAVE2 = CHAVE[:-4] + "9002"
st, r = enviar_xmls([("nota9002.xml", xml_nfe(CHAVE2, 9002, ITENS, 30.0))], token)
segunda = (r.get("resultados") or [{}])[0]
checar("a segunda nota do mesmo fornecedor entra sem pendência",
       segunda.get("pendentes") == 0, segunda)
chamar("DELETE", f"/notas/{segunda.get('id')}", token=token)

print("6. a nota digitada na mão")
st, fornecedores = chamar("GET", "/fornecedores", token=token)
fornecedor = fornecedores[0]
manual = {
    "id_fornecedor": fornecedor["id"],
    "numero": f"M{marca}",
    "serie": "1",
    "data_emissao": "2026-08-17",
    "valor_frete": 20,
    "id_local": local["id"],
    "itens": [
        {"id_produto": farinha["id"], "quantidade": 5, "valor_unitario": 8},
        {"id_produto": acucar["id"], "quantidade": 5, "valor_unitario": 8},
    ],
}
st, r = chamar("POST", "/notas", manual, token=token)
checar("digita a nota", st == 200, r)
id_manual = r.get("id")
checar("item digitado já nasce vinculado (ninguém precisa conciliar)",
       r.get("pendentes") == 0, r)
checar("marcou a origem como MANUAL", r.get("origem") == "MANUAL", r)
checar("somou o total com o frete: 80 + 20 = 100", perto(r.get("valor_total"), 100), r)

st, nota = chamar("GET", f"/notas/{id_manual}", token=token)
custos = {i["seq"]: i["custo_aquisicao_unitario"] for i in nota["itens"]}
checar("sem frete por item, rateia por valor: (40 + 10) ÷ 5 = 10,00",
       perto(custos[1], 10) and perto(custos[2], 10), custos)

print("6a. a unidade da nota pode ser diferente da do estoque")
# A farinha é KG no estoque; a nota veio em CX. O que se guarda é a unidade DA
# NOTA — é ela que a conversão do lançamento usa.
st, r = chamar("POST", "/notas", {
    "id_fornecedor": fornecedor["id"], "numero": f"U{marca}",
    "id_local": local["id"],
    "itens": [{"id_produto": farinha["id"], "quantidade": 3, "um": "CX",
               "valor_unitario": 90}],
}, token=token)
checar("aceita unidade diferente da do produto", st == 200, r)
st, nota_um = chamar("GET", f"/notas/{r['id']}", token=token)
checar("guarda a unidade da nota, não a do estoque",
       nota_um["itens"][0]["um_nota"] == "CX", nota_um["itens"][0])
checar("e a do produto continua sendo a do estoque",
       nota_um["itens"][0]["um_estoque"] == "UN", nota_um["itens"][0])
chamar("DELETE", f"/notas/{r['id']}", token=token)

print("6a2. várias unidades de compra por produto")
# A mesma água vem em caixa de 12, fardo de 6 e palete de 480. Antes só cabia
# um fator por produto, e quem comprava no palete corrigia a conta à mão.
st, agua = chamar("POST", "/produtos", {
    "nome": f"Água FEFO {marca}", "tipo": "REVENDA", "um_estoque": "UN"}, token=token)
st, r = chamar("PUT", f"/produtos/{agua['id']}/unidades", {"itens": [
    {"um": "UN", "fator": 1},
    {"um": "CX", "fator": 12, "padrao": True},
    {"um": "FD", "fator": 6},
]}, token=token)
checar("grava três unidades de compra", st == 200 and r.get("itens") == 3, r)
st, us = chamar("GET", f"/produtos/{agua['id']}/unidades", token=token)
checar("a padrão vem primeiro", us and us[0]["um"] == "CX" and us[0]["padrao"], us)

for um, qtd, preco, esperado in (("CX", 5, 21, 60), ("FD", 2, 11, 12), ("UN", 10, 2, 10)):
    st, n = chamar("POST", "/notas", {
        "numero": f"UM{um}{marca}", "id_local": local["id"],
        "itens": [{"id_produto": agua["id"], "quantidade": qtd, "um": um,
                   "valor_unitario": preco}],
    }, token=token)
    st, nota_um2 = chamar("GET", f"/notas/{n['id']}", token=token)
    item_um = nota_um2["itens"][0]
    checar(f"{qtd} {um} viram {esperado} UN",
           perto(item_um["quantidade_convertida"], esperado, 0.01), item_um)
    chamar("DELETE", f"/notas/{n['id']}", token=token)

checar("unidade repetida é recusada",
       chamar("PUT", f"/produtos/{agua['id']}/unidades", {"itens": [
           {"um": "CX", "fator": 12}, {"um": "cx", "fator": 6}]}, token=token)[0] == 400)
checar("fator diferente de 1 na unidade de estoque é recusado",
       chamar("PUT", f"/produtos/{agua['id']}/unidades", {"itens": [
           {"um": "UN", "fator": 5}]}, token=token)[0] == 400)
checar("unidade que não existe no cadastro é recusada",
       chamar("PUT", f"/produtos/{agua['id']}/unidades", {"itens": [
           {"um": "XYZ", "fator": 2}]}, token=token)[0] == 400)

print("6a3. desconto e acréscimo no item")
st, n = chamar("POST", "/notas", {
    "numero": f"AJ{marca}", "id_local": local["id"],
    "itens": [{"id_produto": agua["id"], "quantidade": 1, "um": "CX", "valor_unitario": 100,
               "valor_desconto": 10, "valor_acrescimo": 22}],
}, token=token)
st, nota_aj = chamar("GET", f"/notas/{n['id']}", token=token)
item_aj = nota_aj["itens"][0]
# 100 - 10 + 22 = 112, em 12 unidades de estoque
checar("o acréscimo entra no custo como o frete entra",
       perto(item_aj["custo_aquisicao_unitario"], 112 / 12, 0.001), item_aj)
checar("e o desconto do item continua abatendo",
       float(item_aj["valor_desconto"]) == 10 and float(item_aj["valor_acrescimo"]) == 22,
       item_aj)
chamar("DELETE", f"/notas/{n['id']}", token=token)
chamar("DELETE", f"/produtos/{agua['id']}", token=token)

print("6a4. o vínculo com o fornecedor não encobre o fator do produto")
# ⚠️ Lançar uma nota CRIA a linha de `produto_fornecedor` só para guardar o
# último preço — e ela nasce com `fator` 1, o padrão da coluna. Aceitar esse 1
# como informação fazia o vínculo recém-criado passar na frente do
# `fator_compra` do produto: o galão de azeite de 5 L entrou certo na primeira
# nota e virou 1 L na segunda, sem ninguém mexer no cadastro. Fator 1 não é
# resposta, é a falta dela.
st, galao = chamar("POST", "/produtos", {
    "nome": f"Nota galao {marca}", "tipo": "INSUMO", "um_estoque": "L",
    "fator_compra": 5,
}, token=token)
st, forn = chamar("GET", "/fornecedores?limite=1", token=token)
id_forn = forn[0]["id"] if forn else None

def custo_do_galao(sufixo):
    st, n = chamar("POST", "/notas", {
        "numero": f"GL{sufixo}{marca}", "id_local": local["id"], "id_fornecedor": id_forn,
        "itens": [{"id_produto": galao["id"], "quantidade": 1, "um": "GL",
                   "valor_unitario": 200}],
    }, token=token)
    st, nota = chamar("GET", f"/notas/{n['id']}", token=token)
    return n["id"], nota["itens"][0]

id_n1, item1 = custo_do_galao("A")
checar("1 galão vira 5 L pelo fator do produto",
       perto(item1["quantidade_convertida"], 5, 0.001), item1)
st, r = chamar("POST", f"/notas/{id_n1}/lancar", {}, token=token)
checar("a nota lança (e cria o vínculo com o fornecedor)", st == 200, r)

id_n2, item2 = custo_do_galao("B")
checar("a SEGUNDA nota continua virando 5 L",
       perto(item2["quantidade_convertida"], 5, 0.001), item2)
checar("e o custo continua sendo 200 ÷ 5 = 40,00",
       perto(item2["custo_aquisicao_unitario"], 40, 0.001), item2)
chamar("DELETE", f"/notas/{id_n2}", token=token)
chamar("POST", f"/notas/{id_n1}/estornar", {}, token=token)
chamar("DELETE", f"/notas/{id_n1}", token=token)
chamar("DELETE", f"/produtos/{galao['id']}", token=token)

print("6b. a nota digitada se corrige enquanto não virou estoque")
st, r = chamar("PUT", f"/notas/{id_manual}", {
    "id_fornecedor": fornecedor["id"], "numero": f"M{marca}", "serie": "1",
    "data_emissao": "2026-08-17", "valor_frete": 20, "id_local": local["id"],
    "itens": [
        # o segundo item some, o primeiro muda de quantidade e preço
        {"id_produto": farinha["id"], "quantidade": 10, "valor_unitario": 9},
    ],
}, token=token)
checar("a correção passa", st == 200, r)
checar("agora tem um item só", r.get("itens") == 1, r)
checar("e o total refez a conta: 90 + 20 = 110", perto(r.get("valor_total"), 110), r)
st, nota = chamar("GET", f"/notas/{id_manual}", token=token)
checar("o custo unitário foi recalculado: (90 + 20) ÷ 10 = 11,00",
       perto(nota["itens"][0]["custo_aquisicao_unitario"], 11), nota["itens"])

# Nota que veio do XML é o documento do fornecedor: não se edita.
st, r = chamar("PUT", f"/notas/{id_nota}", {
    "numero": "outro", "itens": [{"id_produto": farinha["id"], "quantidade": 1,
                                  "valor_unitario": 1}]}, token=token)
checar("nota de XML recusa correção", st == 400, st)
checar("dizendo que ela é o documento", "documento" in (r.get("detail") or "").lower(), r)

print("7. a mesma nota digitada duas vezes é barrada")
st, r = chamar("POST", "/notas", manual, token=token)
checar("segunda digitação é recusada (409)", st == 409, st)
checar("e a mensagem manda abrir a que existe", "já existe" in (r.get("detail") or "").lower(), r)

print("8. item sem produto na nota digitada vira pendência")
st, r = chamar("POST", "/notas", {
    "id_fornecedor": fornecedor["id"], "numero": f"P{marca}",
    "itens": [{"descricao": f"Item sem cadastro {marca}", "quantidade": 1,
               "valor_unitario": 5}],
}, token=token)
checar("aceita o item só com descrição", st == 200, r)
checar("e ele vai para a fila de conciliação", r.get("pendentes") == 1, r)
id_pendente = r.get("id")
st, fila = chamar("GET", "/notas/pendencias", token=token)
checar("aparece na fila de pendências",
       any(i["id_nota"] == id_pendente for i in fila), len(fila))
st, r = chamar("POST", f"/notas/{id_pendente}/lancar", {}, token=token)
checar("e a nota não se lança com pendência", st == 400, st)
checar("dizendo quantos itens faltam", "1 item" in (r.get("detail") or ""), r)

print("9. item sem produto nem descrição é recusado")
st, r = chamar("POST", "/notas", {
    "numero": f"X{marca}", "itens": [{"quantidade": 1, "valor_unitario": 5}]}, token=token)
checar("recusa o item vazio", st == 400, st)
st, r = chamar("POST", "/notas", {"numero": f"X{marca}", "itens": []}, token=token)
checar("recusa a nota sem itens", st == 422, st)
st, r = chamar("POST", "/notas", {
    "numero": f"X{marca}",
    "itens": [{"id_produto": farinha["id"], "quantidade": 0, "valor_unitario": 5}]}, token=token)
checar("recusa quantidade zero", st == 422, st)

print("10. as duas portas exigem permissão")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]}, token=token)
else:
    chamar("POST", "/usuarios", {"nome": "Smoke Cozinha", "email": COZINHA[0],
                                 "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
st, r = enviar_xmls([("nota.xml", xml_nfe(CHAVE[:-1] + "7", 9007, ITENS, 0.0))], tk)
checar("cozinha não importa XML (403)", st == 403, st)
st, r = chamar("POST", "/notas", manual, token=tk)
checar("cozinha não digita nota (403)", st == 403, st)
st, r = chamar("GET", "/notas", token=tk)
checar("cozinha nem lista as notas (403)", st == 403, st)

print("11. limpeza")
st, r = chamar("POST", f"/notas/{id_nota}/estornar", token=token)
checar("estorna o lançamento do XML", st == 200, r)
for n in (id_nota, id_manual, id_pendente):
    chamar("DELETE", f"/notas/{n}", token=token)
for codigo in (f"FAR-{marca}", f"ACU-{marca}"):
    chamar("DELETE", f"/notas/vinculos/{codigo}", token=token)
for p in (farinha.get("id"), acucar.get("id")):
    chamar("DELETE", f"/produtos/{p}", token=token)
st, notas = chamar("GET", f"/notas?limite=200", token=token)
checar("as notas do teste saíram", not any(n["id"] == id_nota for n in notas))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
