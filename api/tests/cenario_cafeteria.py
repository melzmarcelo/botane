"""Cenário completo de uma cafeteria — do cadastro ao CMV, conferindo o dinheiro.

Não é uma suíte de unidade: é a casa inteira funcionando uma vez, com números
escolhidos para caberem na cabeça e serem conferidos à mão. Se algum valor
divergir, é aqui que aparece — e a mensagem diz qual conta deu diferente.

O cenário, calculado no papel antes de virar código:

    NOTA 4001, frete R$ 30,00 rateado por valor (total de produtos R$ 800,00)

      20 PCT de café a 25,00 = 500,00 | frete 500/800 × 30 = 18,75
         líquido 518,75 ÷ (20 × 0,5 KG = 10 KG)          = 51,875 /KG
       5 CX de leite a 48,00 = 240,00 | frete 240/800 × 30 =  9,00
         líquido 249,00 ÷ (5 × 12 L = 60 L)              =  4,15 /L
      10 KG de açúcar a 6,00 =  60,00 | frete  60/800 × 30 =  2,25
         líquido  62,25 ÷ 10 KG                          =  6,225 /KG

      A nota vale 830,00 e o estoque passa a valer 830,00. É a mesma conta.

    ENTRADA MANUAL: 10 KG de café a 60,00 → 600,00

      Médio novo = (518,75 + 600,00) ÷ 20 KG = 55,9375 /KG
      (é o médio PONDERADO: não é a média de 51,875 com 60,00)

    FICHAS

      Espresso (1 UN)         8 G de café  → 0,008 KG × 55,9375 = 0,4475
      Café com leite (1 UN)   1 Espresso   →                      0,4475
                              0,12 L leite → 0,12 × 4,15        = 0,4980
                                                        total     0,9455

    PRODUÇÃO

      20 Espresso        consomem 0,16 KG de café = 8,9500
      10 Café com leite  consomem 10 Espresso (4,4750) + 1,2 L (4,9800)
                                                        total     9,4550

    O resto — perda, transferência, inventário e venda — entra para o CMV e a
    movimentação fecharem com o razão.

    python tests/cenario_cafeteria.py            (API de pé na 9200)
"""

import json
import sys

sys.path.insert(0, "tests")
import comum  # noqa: F401,E402  — reconfigura a saída: o sinal − mata o print
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
SUF = uuid.uuid4().hex[:4].upper()


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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} -> {detalhe}")


def conferir(nome, obtido, esperado, tol=0.0001):
    """Checagem de DINHEIRO: mostra os dois números quando erra."""
    try:
        houve = float(obtido)
    except (TypeError, ValueError):
        checar(nome, False, f"esperado {esperado}, veio {obtido!r}")
        return
    checar(nome, abs(houve - float(esperado)) <= tol,
           f"esperado {esperado}, veio {houve}")


def precisa(valor, oque):
    if not valor:
        print(f"\n  parou: {oque}")
        print(f"\n{ok} passaram, {len(falhas) + 1} falharam")
        sys.exit(1)
    return valor


print(f"CENÁRIO CAFETERIA {SUF} — do cadastro ao CMV\n")

st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = precisa(r.get("access_token"), "não entrou como administrador")

# A apuração é do MÊS: se a base já tem movimento, o número absoluto não é do
# cenário. Mede-se o quanto ele MOVEU — que é o que se pode conferir na mão.
_hoje = date.today()
_periodo = f"inicio={_hoje.replace(day=1)}&fim={_hoje}"
st, _antes = chamar("GET", f"/cmv/apuracao?{_periodo}", token=token)


def delta(campo):
    st, agora = chamar("GET", f"/cmv/apuracao?{_periodo}", token=token)
    return float(agora.get(campo) or 0) - float(_antes.get(campo) or 0)


# ---------------------------------------------------------------- 1. cadastros
print("1. cadastros da casa")

st, locais = chamar("GET", "/locais", token=token)
seco = next((l for l in locais if l["nome"] == f"Estoque seco {SUF}"), None)
if not seco:
    st, r = chamar("POST", "/locais", {"nome": f"Estoque seco {SUF}", "tipo": "SECO"},
                   token=token)
    checar("cria o estoque seco", st == 201, r)
    st, locais = chamar("GET", "/locais", token=token)
    seco = next(l for l in locais if l["nome"] == f"Estoque seco {SUF}")
checar("o primeiro local nasce principal (ninguém marcou nada)",
       any(l["principal"] for l in locais), [(l["nome"], l["principal"]) for l in locais])

st, r = chamar("POST", "/locais", {"nome": f"Câmara fria {SUF}", "tipo": "RESFRIADO"},
               token=token)
checar("cria a câmara fria", st == 201, r)
st, locais = chamar("GET", "/locais", token=token)
camara = precisa(next((l for l in locais if l["nome"] == f"Câmara fria {SUF}"), None),
                 f"não criou a câmara fria: {r}")

st, r = chamar("POST", "/setores", {"nome": f"Cozinha {SUF}"}, token=token)
id_setor = r.get("id")
st, r = chamar("POST", "/categorias", {"nome": f"Mercearia {SUF}", "tipo": "INSUMO"},
               token=token)
id_categoria = r.get("id")

st, r = chamar("POST", "/fornecedores",
               {"nome": f"Distribuidora Café {SUF}", "cnpj": "11.444.777/0001-61"},
               token=token)
if not r.get("id"):
    st, achados = chamar("GET", "/fornecedores?busca=11444777000161", token=token)
    r = achados[0] if achados else {}
forn = precisa(r.get("id"), "não criou o fornecedor")
checar("cadastra o fornecedor", bool(forn), forn)

# ---------------------------------------------------------------- 2. produtos
print("\n2. produtos, com as embalagens em que se compra")


def novo_produto(nome, um, tipo="INSUMO", **extra):
    corpo = {"nome": nome, "tipo": tipo, "um_estoque": um,
             "id_categoria": id_categoria, "id_setor": id_setor, **extra}
    st, r = chamar("POST", "/produtos", corpo, token=token)
    return precisa(r.get("id"), f"não criou o produto {nome}")


cafe = novo_produto(f"Café em grão {SUF}", "KG")
leite = novo_produto(f"Leite integral {SUF}", "L", id_local_padrao=camara["id"])
acucar = novo_produto(f"Açúcar refinado {SUF}", "KG")
copo = novo_produto(f"Copo 300ml {SUF}", "UN")

# O pacote de café tem MEIO quilo: fator fracionário é o que mais erra na mão.
st, r = chamar("PUT", f"/produtos/{cafe}/unidades",
               {"itens": [{"um": "KG", "fator": 1, "padrao": False},
                          {"um": "PCT", "fator": 0.5, "padrao": True}]}, token=token)
checar("café: pacote de 0,5 KG", st == 200, r)
st, r = chamar("PUT", f"/produtos/{leite}/unidades",
               {"itens": [{"um": "L", "fator": 1, "padrao": False},
                          {"um": "CX", "fator": 12, "padrao": True}]}, token=token)
checar("leite: caixa de 12 L", st == 200, r)
st, r = chamar("PUT", f"/produtos/{copo}/unidades",
               {"itens": [{"um": "UN", "fator": 1, "padrao": False},
                          {"um": "PCT", "fator": 100, "padrao": True}]}, token=token)
checar("copo: pacote de 100 UN", st == 200, r)

st, p = chamar("GET", f"/produtos/{leite}", token=token)
checar("o leite entra na câmara fria, não no local da nota",
       p.get("id_local_padrao") == camara["id"], p.get("local_padrao"))

espresso = novo_produto(f"Espresso {SUF}", "UN", tipo="PRODUZIDO", producao_propria=True)
com_leite = novo_produto(f"Café com leite {SUF}", "UN", tipo="PRODUZIDO",
                         producao_propria=True)

# ---------------------------------------------------------------- 3. a nota
print("\n3. nota de entrada: frete rateado e embalagem convertida")

st, nota = chamar("POST", "/notas", {
    "id_fornecedor": forn, "numero": f"4001{SUF}", "serie": "1",
    "data_emissao": str(date.today()), "id_local": seco["id"], "valor_frete": 30.00,
    "itens": [
        {"descricao_fornecedor": "CAFE GRAO PCT 500G", "id_produto": cafe,
         "quantidade": 20, "um": "PCT", "valor_unitario": 25.00},
        {"descricao_fornecedor": "LEITE INT CX 12L", "id_produto": leite,
         "quantidade": 5, "um": "CX", "valor_unitario": 48.00},
        {"descricao_fornecedor": "ACUCAR REFINADO KG", "id_produto": acucar,
         "quantidade": 10, "um": "KG", "valor_unitario": 6.00},
    ],
}, token=token)
id_nota = precisa(nota.get("id"), f"não gravou a nota: {nota}")
conferir("a nota vale 830,00 (800 de produto + 30 de frete)", nota.get("valor_total"), 830.00,
         0.01)

st, det = chamar("GET", f"/notas/{id_nota}", token=token)
por_produto = {i["id_produto"]: i for i in det["itens"]}
conferir("café: 20 PCT viram 10 KG", por_produto[cafe]["quantidade_convertida"], 10)
conferir("café: custo 51,875/KG (com 18,75 de frete)",
         por_produto[cafe]["custo_aquisicao_unitario"], 51.875)
conferir("leite: 5 CX viram 60 L", por_produto[leite]["quantidade_convertida"], 60)
conferir("leite: custo 4,15/L", por_produto[leite]["custo_aquisicao_unitario"], 4.15)
conferir("açúcar: custo 6,225/KG", por_produto[acucar]["custo_aquisicao_unitario"], 6.225)

st, r = chamar("POST", f"/notas/{id_nota}/lancar", {}, token=token)
checar("lança a nota no estoque", st == 200, r)

def saldos_de(*produtos):
    """O saldo por (produto, local) — pedindo o de CADA produto.

    ⚠️ `/estoque/saldos` é PAGINADO. Buscar a lista inteira e montar o
    dicionário funcionava enquanto a base era pequena; com alguns milhares de
    produtos, os do cenário caem fora da primeira página e o `saldo[(x, y)]`
    estoura com KeyError num ponto que não tem nada a ver com o que se testa.
    Vale a regra da casa: **cada suíte procura os registros DELA**.
    """
    linhas = []
    for p in produtos:
        _, s = chamar("GET", f"/estoque/saldos?id_produto={p}", token=token)
        linhas += s or []
    return {(x["id_produto"], x["id_local"]): x for x in linhas}


saldo = saldos_de(cafe, leite, acucar)
conferir("café: 10 KG no estoque seco", saldo[(cafe, seco["id"])]["quantidade"], 10)
conferir("leite: 60 L NA CÂMARA (o local é do produto)",
         saldo[(leite, camara["id"])]["quantidade"], 60)
conferir("açúcar: 10 KG", saldo[(acucar, seco["id"])]["quantidade"], 10)
# Só os produtos DESTE cenário: a base pode ter outra coisa, e somar tudo
# transformaria a checagem numa conta sobre o que não é do teste.
# ⚠️ Pede o saldo de cada um: a lista é paginada, e o `copo` nem estava no
# dicionário acima. Somar a primeira página daria o valor de outros produtos.
valor_estoque = sum(float(x["valor"])
                    for x in saldos_de(cafe, leite, acucar, copo).values())
conferir("o estoque passa a valer o total da nota", valor_estoque, 830.00, 0.01)

# ---------------------------------------------------------- 4. o custo médio
print("\n4. segunda compra: o custo médio é ponderado")

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": cafe, "quantidade": 10, "custo_unitario": 60.00, "id_local": seco["id"],
    "documento": "compra avulsa",
}, token=token)
checar("entra mais 10 KG de café a 60,00", st == 201, r)
conferir("médio novo = (518,75 + 600) ÷ 20 = 55,9375", r.get("custo_medio"), 55.9375)

saldo = saldos_de(cafe)
conferir("e o café passa a valer 1.118,75", saldo[(cafe, seco["id"])]["valor"], 1118.75, 0.01)

# ---------------------------------------------------------------- 5. fichas
print("\n5. fichas: o custo desce da receita")

st, r = chamar("POST", "/fichas", {
    "id_produto": espresso, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": cafe, "qtd_bruta": 8, "um": "G"}],
}, token=token)
ficha_espresso = precisa(r.get("id"), f"não criou a ficha do espresso: {r}")
st, f = chamar("GET", f"/fichas/{ficha_espresso}", token=token)
conferir("8 G de café = 0,008 KG", f["itens"][0]["qtd_estoque"], 0.008)
conferir("espresso custa 0,4475 (0,008 × 55,9375)", f["custo_total"], 0.4475)
st, r = chamar("POST", f"/fichas/{ficha_espresso}/homologar", {}, token=token)
checar("homologa a ficha do espresso", st == 200, r)

st, r = chamar("POST", "/fichas", {
    "id_produto": com_leite, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_subficha": ficha_espresso, "qtd_bruta": 1, "um": "UN"},
              {"id_insumo": leite, "qtd_bruta": 0.12, "um": "L"}],
}, token=token)
ficha_com_leite = precisa(r.get("id"), f"não criou a ficha do café com leite: {r}")
st, f = chamar("GET", f"/fichas/{ficha_com_leite}", token=token)
conferir("café com leite = 0,4475 + 0,4980 = 0,9455", f["custo_total"], 0.9455)
st, r = chamar("POST", f"/fichas/{ficha_com_leite}/homologar", {}, token=token)
checar("homologa a ficha do café com leite", st == 200, r)

# ------------------------------------------------------------- 6. produção
print("\n6. produção: o que sai do estoque é o que a receita pede")

st, r = chamar("POST", "/estoque/producoes",
               {"id_produto": espresso, "quantidade": 20, "id_local": seco["id"]},
               token=token)
checar("produz 20 espressos", st == 201, r)
conferir("consome 0,16 KG de café", (r.get("consumos") or [{}])[0].get("quantidade"), 0.16)
conferir("ao custo de 8,95", r.get("custo_total"), 8.95, 0.01)
conferir("cada espresso entra a 0,4475", r.get("custo_unitario"), 0.4475)

st, r = chamar("POST", "/estoque/producoes",
               {"id_produto": com_leite, "quantidade": 10, "id_local": seco["id"]},
               token=token)
checar("produz 10 cafés com leite", st == 201, r)
conferir("consumindo 9,4550 (4,4750 de espresso + 4,9800 de leite)",
         r.get("custo_total"), 9.455, 0.01)
conferir("cada um a 0,9455", r.get("custo_unitario"), 0.9455)

saldo = saldos_de(espresso, cafe)
conferir("sobram 10 espressos", saldo[(espresso, seco["id"])]["quantidade"], 10)
conferir("café baixou para 19,84 KG", saldo[(cafe, seco["id"])]["quantidade"], 19.84)

# --------------------------------------------------- 7. perda e transferência
print("\n7. perda e transferência")

st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
id_motivo = motivos[0]["id"] if motivos else None
st, r = chamar("POST", "/estoque/saidas", {
    "id_produto": leite, "quantidade": 2, "tipo": "SAIDA_PERDA",
    "id_local": camara["id"], "id_motivo_perda": id_motivo, "observacao": "caixa furada",
}, token=token)
checar("aponta perda de 2 L de leite", st == 201, r)
conferir("a perda vale 8,30 (2 × 4,15)", float(r.get("custo_unitario", 0)) * 2, 8.30, 0.01)

st, r = chamar("POST", "/estoque/transferencias", {
    "id_produto": leite, "quantidade": 5, "id_local_origem": camara["id"],
    "id_local_destino": seco["id"],
}, token=token)
checar("transfere 5 L para o seco", st == 201, r)
saldo = saldos_de(leite)
conferir("câmara fica com 51,8 L", saldo[(leite, camara["id"])]["quantidade"], 51.8)
conferir("e o seco recebe 5 L pelo mesmo médio",
         saldo[(leite, seco["id"])]["custo_medio"], 4.15)

# ------------------------------------------------------------- 8. inventário
print("\n8. inventário: a contagem acerta o razão")

# ⚠️ `cega: False` de propósito: a contagem passou a nascer CEGA, e o cenário
# confere o saldo congelado e a diferença número a número. Contagem cega
# esconde os dois até fechar — o que é o certo para quem conta, e inútil para
# quem está provando a conta.
st, inv = chamar("POST", "/inventarios",
                 {"id_local": seco["id"], "produtos": [cafe], "cega": False}, token=token)
id_inv = precisa(inv.get("id"), f"não abriu o inventário: {inv}")
conferir("o sistema acha 19,84 KG de café", inv["itens"][0]["qtd_sistema"], 19.84)
st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem",
               {"itens": [{"id_produto": cafe, "qtd_contada": 19.5, "um": "KG"}]},
               token=token)
conferir("contaram 19,5 — faltam 0,34", r["itens"][0]["diferenca"], -0.34)
st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token)
checar("fecha o inventário", st == 200, r)
saldo = saldos_de(cafe)
conferir("o saldo passa a ser o contado", saldo[(cafe, seco["id"])]["quantidade"], 19.5)
conferir("o médio NÃO muda com o ajuste", saldo[(cafe, seco["id"])]["custo_medio"], 55.9375)

# ---------------------------------------------------------------- 9. venda
print("\n9. venda: CMV teórico pela ficha")

st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(date.today()), "documento": f"CUPOM-{SUF}", "canal": "salão",
    "itens": [{"id_produto": com_leite, "quantidade": 5, "valor_unitario": 8.00}],
}]}, token=token)
checar("importa a venda de 5 cafés com leite", st == 201, r)

hoje, periodo = _hoje, _periodo
st, a = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
conferir("receita de 40,00", delta("receita"), 40.00, 0.01)
conferir("CMV teórico = 5 × 0,9455 = 4,7275", delta("cmv_teorico"), 4.7275, 0.01)

# ------------------------------------------------------- 10. a conta fecha
print("\n10. a conta do mês fecha com o razão")

conferir("compras do mês = 830 + 600 = 1.430,00", delta("compras"), 1430.00, 0.01)
cmv_real = (float(a["estoque_inicial"]) + float(a["compras"]) - float(a["estoque_final"]))
conferir("CMV real = inicial + compras − final", a.get("cmv_real"), cmv_real, 0.01)

st, mov = chamar("GET", f"/cmv/movimentacao?{periodo}", token=token)
t = mov["total"]
# ⚠️ A tolerância acompanha o TAMANHO do relatório. Cada linha sai arredondada
# em dois dígitos e o rodapé soma as linhas arredondadas — de propósito, para o
# rodapé fechar com a coluna na tela. Num relatório de uma conta real, com
# centenas de produtos, isso dá alguns centavos de diferença na identidade. Meio
# centavo por linha é folga suficiente e continua acusando erro de verdade.
folga = max(0.05, 0.005 * mov["produtos"])
conferir("movimentação: inicial + entradas − saídas = final",
         t["valor_inicial"] + t["valor_entradas"] - t["valor_saidas"], t["valor_final"], folga)
# ⚠️ A movimentação mostra TODO o estoque; a apuração desconta os tipos que a
# casa pôs fora do CMV (`considerar_no_cmv = false`). Enquanto não havia nenhum
# grupo assim na base, os dois números coincidiam e a checagem parecia uma
# identidade — não é. Ver a armadilha no CLAUDE.md.
_fora = a.get("tipos_fora_do_cmv") or []
_ids_fora: set[int] = set()
for _t in _fora:
    _, _lista = chamar("GET", f"/produtos?tipo={_t}&por_pagina=500", token=token)
    _ids_fora |= {p["id"] for p in (_lista or [])}
_valor_fora = sum(float(l["valor_final"]) for l in mov["linhas"]
                  if l["id_produto"] in _ids_fora)
conferir("e as compras da movimentação batem com o estoque de agora",
         t["valor_final"] - _valor_fora, float(a["estoque_final"]), folga)

linha_cafe = next((l for l in mov["linhas"] if l["id_produto"] == cafe), None)
checar("o café aparece na movimentação", linha_cafe is not None,
       [l["produto"] for l in mov["linhas"]])
if linha_cafe:
    conferir("café: entraram 20 KG", linha_cafe["qtd_entradas"], 20)
    conferir("café: saíram 0,5 KG (0,16 de produção + 0,34 de ajuste)",
             linha_cafe["qtd_saidas"], 0.5)
    conferir("café: sobraram 19,5 KG", linha_cafe["qtd_final"], 19.5)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
