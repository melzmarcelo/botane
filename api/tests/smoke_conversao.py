"""Teste de fumaça da conversão de unidades — a caixa que vale 12.

O cenário é o que o dono relatou, conferido na mão:

    Produto estocado em PCT, comprado em CX de 12.
    Nota: 1 CX a R$ 12,00  ->  razão: 12 PCT a R$ 1,00.
    Ficha que pede 1 CX    ->  custo R$ 12,00 e baixa de 12 PCT.

O que este teste existe para impedir: CX, FD, PCT e BDJ são todas grandeza
UNIDADE com fator 1, então a conversão genérica dizia que **1 CX = 1 PCT**. A
nota entrava certa (ela consulta a embalagem do produto) e a ficha entrava
errada — a mesma caixa valia 12 num lugar e 1 no outro. Dúzia continua
convertendo: doze é doze em qualquer produto.

    python tests/smoke_conversao.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, "tests")
from comum import garantir_local, garantir_fornecedor  # noqa: E402

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


def saldo_de(id_produto):
    """O saldo DESTE produto, perguntado ao servidor.

    ⚠️ **`/estoque/saldos` é PAGINADO.** Montar um dicionário com a primeira
    página e procurar o próprio produto nele funciona enquanto a base é pequena
    e passa a mentir quando ela cresce: o produto não está na página, e a
    checagem acusa o razão de não ter gravado o que gravou. Os dois `cenario_*`
    já tinham sido corrigidos disso; este arquivo ficou de fora e quebrou na
    primeira base grande.
    """
    _st, dados = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token)
    itens = dados["itens"] if isinstance(dados, dict) and "itens" in dados else dados
    return (itens or [None])[0]


def perto(a, b, casas=4):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
local = garantir_local(chamar, token)
forn = garantir_fornecedor(chamar, token, "Conversao fornecedor", "11444777000161")
suf = uuid.uuid4().hex[:6]

print("1. o produto que se estoca em pacote e se compra em caixa")
st, r = chamar("POST", "/produtos", {"nome": f"Conversao pacote {suf}", "tipo": "INSUMO",
                                     "um_estoque": "PCT"}, token=token)
prod = r["id"]
st, r = chamar("PUT", f"/produtos/{prod}/unidades",
               {"itens": [{"um": "PCT", "fator": 1, "padrao": False},
                          {"um": "CX", "fator": 12, "padrao": True}]}, token=token)
checar("grava as unidades de compra", st == 200, r)
st, p = chamar("GET", f"/produtos/{prod}", token=token)
checar("a unidade padrão vira o fator de compra do cadastro",
       p.get("um_compra") == "CX" and perto(p.get("fator_compra"), 12),
       (p.get("um_compra"), p.get("fator_compra")))

print("2. a nota de 1 CX a 12,00 entra como 12 PCT a 1,00")
st, r = chamar("POST", "/notas", {"id_fornecedor": forn, "numero": f"7{suf[:4]}", "serie": "1",
                                  "data_emissao": "2026-08-20",
                                  "itens": [{"descricao_fornecedor": "Caixa com 12 pacotes",
                                             "id_produto": prod, "quantidade": 1, "um": "CX",
                                             "valor_unitario": 12.00}]}, token=token)
nota = r["id"]
st, det = chamar("GET", f"/notas/{nota}", token=token)
item = det["itens"][0]
checar("a nota converte antes de lançar", perto(item.get("quantidade_convertida"), 12),
       item.get("quantidade_convertida"))
checar("e o custo sai por unidade de estoque",
       perto(item.get("custo_aquisicao_unitario"), 1), item.get("custo_aquisicao_unitario"))
st, r = chamar("POST", f"/notas/{nota}/lancar", {"id_local": local["id"]}, token=token)
checar("lança no estoque", st == 200, r)
saldo = saldo_de(prod)
checar("o razão guarda a quantidade JÁ convertida", saldo and perto(saldo["quantidade"], 12),
       saldo)
checar("e o custo médio é o do pacote, não o da caixa",
       saldo and perto(saldo["custo_medio"], 1), saldo)

print("3. a ficha que pede uma caixa custa a caixa inteira")
st, r = chamar("POST", "/produtos", {"nome": f"Conversao prato {suf}", "tipo": "PRODUZIDO",
                                     "producao_propria": True, "um_estoque": "UN"}, token=token)
prato = r["id"]
st, r = chamar("POST", "/fichas", {"id_produto": prato, "rendimento_qtd": 1,
                                   "rendimento_um": "UN", "porcoes": 1,
                                   "itens": [{"id_insumo": prod, "qtd_bruta": 1, "um": "CX"}]},
               token=token)
ficha_cx = r["id"]
st, f = chamar("GET", f"/fichas/{ficha_cx}", token=token)
it = f["itens"][0]
checar("1 CX na receita = 12 PCT no estoque", perto(it.get("qtd_estoque"), 12),
       it.get("qtd_estoque"))
checar("e custa 12,00, não 1,00", perto(it.get("custo_total"), 12), it.get("custo_total"))
checar("dizendo de onde veio a conversão", it.get("conversao") == "embalagem",
       it.get("conversao"))

print("4. a produção baixa 12, não 1")
st, r = chamar("POST", f"/fichas/{ficha_cx}/homologar", {}, token=token)
st, r = chamar("POST", "/estoque/producoes", {"id_produto": prato, "quantidade": 1,
                                             "id_local": local["id"]}, token=token)
checar("produz pela ficha em caixa", st == 201, r)
consumo = (r.get("consumos") or [{}])[0]
checar("consome 12 pacotes", perto(consumo.get("quantidade"), 12), consumo)
checar("ao custo dos 12 pacotes", perto(consumo.get("custo"), 12), consumo)
saldo = saldo_de(prod)
checar("e o saldo do insumo zera", not saldo or perto(saldo["quantidade"], 0), saldo)

print("5. embalagem que ninguém cadastrou não vira 1:1 calada")
st, r = chamar("POST", "/produtos", {"nome": f"Conversao sem caixa {suf}", "tipo": "INSUMO",
                                     "um_estoque": "PCT"}, token=token)
sem_caixa = r["id"]
st, r = chamar("POST", "/fichas", {"id_produto": prato, "rendimento_qtd": 1,
                                   "rendimento_um": "UN", "porcoes": 1,
                                   "itens": [{"id_insumo": sem_caixa, "qtd_bruta": 1,
                                              "um": "FD"}]}, token=token)
ficha_fd = r["id"]
st, f = chamar("GET", f"/fichas/{ficha_fd}", token=token)
it = f["itens"][0]
checar("a ficha avisa em vez de inventar", it.get("qtd_estoque") is None and it.get("aviso"),
       (it.get("qtd_estoque"), it.get("aviso")))
checar("e o aviso diz onde resolver", "unidade de compra" in (it.get("aviso") or ""),
       it.get("aviso"))
st, r = chamar("POST", f"/fichas/{ficha_fd}/homologar", {}, token=token)
st, r = chamar("POST", "/estoque/producoes", {"id_produto": prato, "quantidade": 1,
                                             "id_local": local["id"]}, token=token)
checar("e a produção recusa em vez de baixar 1", st == 400, (st, r))

print("6. dúzia continua sendo dúzia")
st, r = chamar("POST", "/produtos", {"nome": f"Conversao ovo {suf}", "tipo": "INSUMO",
                                     "um_estoque": "UN"}, token=token)
ovo = r["id"]
chamar("POST", "/estoque/entradas", {"id_produto": ovo, "quantidade": 60,
                                    "custo_unitario": 1, "id_local": local["id"]}, token=token)
st, r = chamar("POST", "/fichas", {"id_produto": prato, "rendimento_qtd": 1,
                                   "rendimento_um": "UN", "porcoes": 1,
                                   "itens": [{"id_insumo": ovo, "qtd_bruta": 1, "um": "DZ"}]},
               token=token)
st, f = chamar("GET", f"/fichas/{r['id']}", token=token)
it = f["itens"][0]
checar("1 DZ = 12 UN", perto(it.get("qtd_estoque"), 12), it.get("qtd_estoque"))
checar("pela grandeza, não pela embalagem", it.get("conversao") == "grandeza",
       it.get("conversao"))

print("7. o último preço de compra é por unidade de estoque")
st, p = chamar("GET", f"/produtos/{prod}", token=token)
vinculo = next((v for v in (p.get("fornecedores") or []) if v["id_fornecedor"] == forn), None)
checar("o lançamento grava o preço no fornecedor", vinculo and vinculo.get("ultimo_preco"),
       p.get("fornecedores"))
if vinculo:
    checar("e grava 1,00 (o pacote), não 12,00 (a caixa)",
           perto(vinculo["ultimo_preco"], 1), vinculo["ultimo_preco"])
    # Salvar o produto pela tela não pode levar junto o que a tela não manda.
    chamar("PUT", f"/produtos/{prod}", {"observacao": "salvo pela tela"}, token=token)
    st, p2 = chamar("GET", f"/produtos/{prod}", token=token)
    v2 = next((v for v in (p2.get("fornecedores") or []) if v["id_fornecedor"] == forn), None)
    checar("salvar o produto não apaga o preço de compra",
           v2 and perto(v2.get("ultimo_preco"), 1), p2.get("fornecedores"))

print("8. o local de estoque é do produto, não da nota")
# Uma nota traz congelado e seco na mesma folha. O local do CADASTRO manda; o
# da nota é a reserva de quem ainda não tem um.
locais = chamar("GET", "/locais", token=token)[1]
if len(locais) < 2:
    chamar("POST", "/locais", {"nome": f"Camara fria {suf}", "tipo": "REFRIGERADO"}, token=token)
    locais = chamar("GET", "/locais", token=token)[1]
reserva = next(l for l in locais if l["principal"])
camara = next(l for l in locais if l["id"] != reserva["id"])

st, r = chamar("POST", "/produtos", {"nome": f"Conversao congelado {suf}", "tipo": "INSUMO",
                                     "um_estoque": "KG", "id_local_padrao": camara["id"]},
               token=token)
congelado = r["id"]
st, p = chamar("GET", f"/produtos/{congelado}", token=token)
checar("o produto guarda o local dele", p.get("id_local_padrao") == camara["id"],
       p.get("id_local_padrao"))
checar("e devolve o nome para a tela", p.get("local_padrao") == camara["nome"],
       p.get("local_padrao"))

st, r = chamar("POST", "/produtos", {"nome": f"Conversao seco {suf}", "tipo": "INSUMO",
                                     "um_estoque": "KG"}, token=token)
seco = r["id"]
st, r = chamar("POST", "/notas", {"id_fornecedor": forn, "numero": f"8{suf[:4]}", "serie": "1",
                                  "data_emissao": "2026-08-20", "id_local": reserva["id"],
                                  "itens": [
                                      {"descricao_fornecedor": "Congelado", "id_produto": congelado,
                                       "quantidade": 2, "um": "KG", "valor_unitario": 10},
                                      {"descricao_fornecedor": "Seco", "id_produto": seco,
                                       "quantidade": 3, "um": "KG", "valor_unitario": 5}]},
               token=token)
nota2 = r["id"]
st, det = chamar("GET", f"/notas/{nota2}", token=token)
destinos = {i["id_produto"]: i.get("local_destino") for i in det["itens"]}
checar("a tela mostra o destino de cada item antes de lançar",
       destinos.get(congelado) == camara["nome"] and destinos.get(seco) is None, destinos)
st, r = chamar("POST", f"/notas/{nota2}/lancar", {}, token=token)
checar("lança a nota inteira de uma vez", st == 200, r)
onde = {alvo: (saldo_de(alvo) or {}).get("id_local") for alvo in (congelado, seco)}
checar("o congelado entra na câmara", onde.get(congelado) == camara["id"], onde)
checar("e o seco no local da nota", onde.get(seco) == reserva["id"], onde)

print("9. limpeza")
for caminho in (f"/produtos/{prod}", f"/produtos/{prato}", f"/produtos/{sem_caixa}",
                f"/produtos/{ovo}", f"/produtos/{congelado}", f"/produtos/{seco}"):
    chamar("DELETE", caminho, token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
