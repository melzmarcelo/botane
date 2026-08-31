"""Remessa entre lojas: sai daqui, alguém confere lá, e só então o razão anda.

O que este arquivo cobra:

1. dentro da MESMA loja a transferência continua imediata — nada de remessa
2. entre lojas nasce EM_TRANSITO e **o razão não se mexe**
3. a quantidade continua contando na origem, e o saldo dela diz quanto está na
   estrada
4. o recebimento lança os dois movimentos, pelo MESMO custo, cada um na sua loja
5. **o que não chegou vira PERDA na origem** — não sobra de saldo
6. receber duas vezes é recusado; cancelar não estorna nada
7. quem recebe é o DESTINO; quem cancela é a ORIGEM
8. a identidade `inicial + entradas − saídas = final` fecha nas duas lojas

    python tests/smoke_transferencias.py       (API de pé na 9200)

⚠️ Cria a própria filial e os próprios produtos, com marca de tempo, e
**desativa a filial no `atexit`** — uma rodada que estoure no meio deixaria
duas lojas ativas na base do dono, e aí o seletor de loja aparece na barra
superior e vira o primeiro `<select>` do documento.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, unidade=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if unidade:
        req.add_header("X-Unidade", str(unidade))
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


def perto(a, b, tol=0.01):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]


def _desativar_filiais_de_teste():
    """A filial sai mesmo se a suíte estourar no meio — mesma lição do
    `preservar_credenciais`. Duas lojas ativas mudam a barra superior."""
    try:
        _st, lista = chamar("GET", "/unidades?incluir_inativas=true", token=token)
        for u in (lista or []):
            if u.get("ativo") and str(u.get("nome", "")).startswith("Filial remessa"):
                chamar("PUT", f"/unidades/{u['id']}", {"ativo": False}, token=token)
    except Exception:
        pass


atexit.register(_desativar_filiais_de_teste)


print("1. preparo: matriz, filial e um insumo com saldo")
matriz = garantir_local(chamar, token)
st, filial = chamar("POST", "/unidades", {
    "nome": f"Filial remessa {marca}", "apelido": f"R{marca}"}, token=token)
id_filial = (filial or {}).get("id")
checar("a filial é criada", st == 201 and bool(id_filial), (st, filial))

st, locais_f = chamar("GET", "/locais", token=token, unidade=id_filial)
local_filial = (locais_f or [{}])[0].get("id")
checar("e nasce com local de estoque", bool(local_filial), locais_f)

st, prod = chamar("POST", "/produtos", {
    "codigo": f"REM{marca}", "nome": f"Insumo de remessa {marca}",
    "tipo": "INSUMO", "um_estoque": "KG", "controla_estoque": True}, token=token)
id_produto = (prod or {}).get("id")
checar("o produto é criado", st == 201 and bool(id_produto), (st, prod))

# 20 KG a R$ 5,00 na matriz.
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": id_produto, "id_local": matriz["id"],
    "quantidade": 20, "custo_unitario": 5.00}, token=token)
checar("com 20 KG a 5,00 na matriz", st == 201, (st, r))


def saldo(unidade, id_local=None):
    alvo = f"&id_local={id_local}" if id_local else ""
    _st, s = chamar("GET", f"/estoque/saldos?id_produto={id_produto}{alvo}",
                    token=token, unidade=unidade)
    return sum(float(x["quantidade"]) for x in (s or []))


def em_transito(unidade):
    _st, s = chamar("GET", f"/estoque/saldos?id_produto={id_produto}",
                    token=token, unidade=unidade)
    return sum(float(x.get("em_transito") or 0) for x in (s or []))


print("\n2. dentro da MESMA loja continua imediata")
# ⚠️ Prateleira para prateleira da mesma casa alguém carrega a caixa — exigir
# recebimento ali seria burocracia inventada.
st, locais_matriz = chamar("GET", "/locais", token=token)
segundo = next((l["id"] for l in (locais_matriz or []) if l["id"] != matriz["id"]), None)
if segundo:
    st, r = chamar("POST", "/estoque/transferencias", {
        "id_produto": id_produto, "quantidade": 1,
        "id_local_origem": matriz["id"], "id_local_destino": segundo}, token=token)
    checar("aceita a transferência dentro da loja", st == 201, (st, r))
    checar("e NÃO cria remessa nenhuma",
           (r or {}).get("em_transito") is False and "remessa" not in (r or {}), r)
    # devolve para não bagunçar a conta do resto
    chamar("POST", "/estoque/transferencias", {
        "id_produto": id_produto, "quantidade": 1,
        "id_local_origem": segundo, "id_local_destino": matriz["id"]}, token=token)


print("\n3. entre lojas nasce em trânsito — e o razão não se mexe")
antes_matriz, antes_filial = saldo(1), saldo(id_filial)
st, envio = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": local_filial,
    "itens": [{"id_produto": id_produto, "quantidade": 6}],
    "observacao": f"remessa {marca}"}, token=token)
id_remessa = (envio or {}).get("id")
checar("a remessa é criada", st == 201 and bool(id_remessa), (st, envio))
checar("nasce EM_TRANSITO", (envio or {}).get("status") == "EM_TRANSITO", envio)
checar("a origem NÃO perdeu nada", perto(saldo(1), antes_matriz), (saldo(1), antes_matriz))
checar("e o destino não ganhou nada", perto(saldo(id_filial), antes_filial),
       (saldo(id_filial), antes_filial))
# 🔑 A quantidade continua contando na origem — é o que impede o valor de ficar
# sem dono no caminho. Mas o saldo precisa DIZER quanto dele já está na estrada.
checar("e o saldo da origem avisa 6 em trânsito", perto(em_transito(1), 6), em_transito(1))
checar("a filial não vê nada em trânsito saindo dela", perto(em_transito(id_filial), 0),
       em_transito(id_filial))

st, lista = chamar("GET", "/transferencias?status=EM_TRANSITO", token=token)
checar("e ela aparece na lista de em trânsito",
       any(x["id"] == id_remessa for x in (lista or [])), lista)
# ⚠️ A loja atual vê os DOIS lados: filtrar só pela origem esconderia da filial
# justamente a remessa que ela precisa receber.
st, lista_f = chamar("GET", "/transferencias?status=EM_TRANSITO", token=token,
                     unidade=id_filial)
checar("e a filial também a enxerga, porque é ela quem recebe",
       any(x["id"] == id_remessa for x in (lista_f or [])), lista_f)


print("\n4. quem recebe é o DESTINO")
# A matriz é quem mandou: dar entrada dela mesma anularia a conferência.
st, r = chamar("POST", f"/transferencias/{id_remessa}/receber", {}, token=token, unidade=1)
checar("a origem NÃO recebe a própria remessa (403)", st == 403, (st, r))

st, recebida = chamar("POST", f"/transferencias/{id_remessa}/receber", {
    "observacao": "conferido na chegada"}, token=token, unidade=id_filial)
checar("o destino recebe", st == 201, (st, recebida))
checar("a origem perde as 6", perto(saldo(1), antes_matriz - 6), (saldo(1), antes_matriz))
checar("e o destino ganha as MESMAS 6", perto(saldo(id_filial), antes_filial + 6),
       (saldo(id_filial), antes_filial))
checar("e nada fica mais em trânsito", perto(em_transito(1), 0), em_transito(1))

st, detalhe = chamar("GET", f"/transferencias/{id_remessa}", token=token)
item = (detalhe or {}).get("itens", [{}])[0]
checar("a remessa fica RECEBIDA", (detalhe or {}).get("status") == "RECEBIDA", detalhe)
checar("com saída e entrada apontadas no razão",
       bool(item.get("id_movimento_saida")) and bool(item.get("id_movimento_entrada")), item)
checar("e sem perda nenhuma", item.get("id_movimento_perda") is None, item)

st, r = chamar("POST", f"/transferencias/{id_remessa}/receber", {}, token=token,
               unidade=id_filial)
checar("receber de novo é recusado (409)", st == 409, (st, r))


print("\n5. o custo atravessa a fronteira")
# 🔑 A entrada usa o médio que a saída apurou. É isso que faz a origem perder
# exatamente o valor que o destino ganha — entre lojas a transferência também
# não pode criar dinheiro.
st, movs = chamar(
    "GET", f"/estoque/movimentos?id_produto={id_produto}&limite=20", token=token)
saidas = [m for m in (movs or []) if m["tipo"] == "TRANSFERENCIA_SAIDA"]
st, movs_f = chamar(
    "GET", f"/estoque/movimentos?id_produto={id_produto}&limite=20",
    token=token, unidade=id_filial)
entradas = [m for m in (movs_f or []) if m["tipo"] == "TRANSFERENCIA_ENTRADA"]
checar("há saída na origem e entrada no destino", bool(saidas) and bool(entradas),
       (len(saidas), len(entradas)))
if saidas and entradas:
    checar("pelo MESMO custo unitário",
           perto(saidas[0]["custo_unitario"], entradas[0]["custo_unitario"], 0.000001),
           (saidas[0]["custo_unitario"], entradas[0]["custo_unitario"]))
    checar("e o custo é o médio da ORIGEM (5,00)", perto(saidas[0]["custo_unitario"], 5.00),
           saidas[0]["custo_unitario"])


print("\n6. o que não chegou vira PERDA na origem")
# 🔑 A mercadoria saiu da prateleira do mesmo jeito. Transferir só o que chegou
# deixaria a origem com um saldo que ela não tem — e a próxima contagem cobriria
# o buraco como ajuste de inventário, que é onde a diferença some sem nome.
antes_matriz, antes_filial = saldo(1), saldo(id_filial)
st, envio2 = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": local_filial,
    "itens": [{"id_produto": id_produto, "quantidade": 5}]}, token=token)
id_remessa2 = (envio2 or {}).get("id")
st, detalhe2 = chamar("GET", f"/transferencias/{id_remessa2}", token=token)
id_item2 = (detalhe2 or {}).get("itens", [{}])[0].get("id")

st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
id_motivo = (motivos or [{}])[0].get("id")

st, rec2 = chamar("POST", f"/transferencias/{id_remessa2}/receber", {
    "itens": [{"id_item": id_item2, "qtd_recebida": 3, "id_motivo_perda": id_motivo}],
    "observacao": "chegaram 3 de 5"}, token=token, unidade=id_filial)
checar("o recebimento parcial é aceito", st == 201, (st, rec2))
checar("e a frase NOMEIA o que não chegou",
       "perda" in str((rec2 or {}).get("message", "")).lower(), rec2)
checar("o destino ganha só o que chegou (3)", perto(saldo(id_filial), antes_filial + 3),
       (saldo(id_filial), antes_filial))
# 🔑 A origem perde os CINCO: três transferidos e dois perdidos.
checar("mas a origem perde os 5 que despachou", perto(saldo(1), antes_matriz - 5),
       (saldo(1), antes_matriz))

st, detalhe2 = chamar("GET", f"/transferencias/{id_remessa2}", token=token)
item2 = (detalhe2 or {}).get("itens", [{}])[0]
checar("e o item guarda o movimento de PERDA", bool(item2.get("id_movimento_perda")), item2)
st, movs2 = chamar("GET", f"/estoque/movimentos?id_produto={id_produto}&tipo=SAIDA_PERDA",
                   token=token)
# ⚠️ `REMESSA`, não `TRANSFERENCIA`: naquele vocabulário o `origem_id` é o
# movimento do outro lado, e aqui não há outro lado — a mercadoria não chegou.
perdas = [m for m in (movs2 or []) if m.get("origem_tipo") == "REMESSA"]
checar("a perda fica na loja da ORIGEM, com 2 KG", bool(perdas) and perto(
    abs(float(perdas[0]["quantidade"])), 2), perdas[:1])


print("\n7. cancelar não estorna nada — porque nada foi lançado")
antes_matriz = saldo(1)
st, envio3 = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": local_filial,
    "itens": [{"id_produto": id_produto, "quantidade": 2}]}, token=token)
id_remessa3 = (envio3 or {}).get("id")
checar("a terceira remessa sai", st == 201, (st, envio3))

# ⚠️ Quem cancela é a ORIGEM: quem recebe não desfaz o despacho de outra loja.
st, r = chamar("POST", f"/transferencias/{id_remessa3}/cancelar", {}, token=token,
               unidade=id_filial)
checar("o destino NÃO cancela a remessa (403)", st == 403, (st, r))

st, cancelada = chamar("POST", f"/transferencias/{id_remessa3}/cancelar", {}, token=token)
checar("a origem cancela", st == 201, (st, cancelada))
checar("e a frase diz que nada foi lançado",
       "nada foi lançado" in str((cancelada or {}).get("message", "")).lower(), cancelada)
checar("o saldo da origem não mudou", perto(saldo(1), antes_matriz), (saldo(1), antes_matriz))
checar("e nada ficou em trânsito", perto(em_transito(1), 0), em_transito(1))
st, r = chamar("POST", f"/transferencias/{id_remessa3}/receber", {}, token=token,
               unidade=id_filial)
checar("remessa cancelada não se recebe (409)", st == 409, (st, r))


print("\n8. o que a remessa recusa")
st, r = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": matriz["id"],
    "itens": [{"id_produto": id_produto, "quantidade": 1}]}, token=token)
checar("remessa dentro da mesma loja é recusada (400)", st == 400, (st, r))
st, r = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": local_filial,
    "itens": []}, token=token)
checar("remessa sem item é recusada (400)", st == 400, (st, r))
st, r = chamar("POST", "/transferencias", {
    "id_local_origem": matriz["id"], "id_local_destino": local_filial,
    "itens": [{"id_produto": id_produto, "quantidade": 1},
              {"id_produto": id_produto, "quantidade": 2}]}, token=token)
checar("o mesmo produto duas vezes é recusado (400)", st == 400, (st, r))
checar("e a frase manda somar as quantidades",
       "some" in str((r or {}).get("detail", "")).lower(), r)


print("\n9. a identidade fecha nas DUAS lojas")
# 🔑 O destino recebe mercadoria que não comprou e a origem perde mercadoria que
# não vendeu: sem a remessa entrar na apuração como compra de um lado e compra
# negativa do outro, o CMV da filial ficaria negativo.
for nome, unidade in (("matriz", 1), ("filial", id_filial)):
    st, ap = chamar("GET", "/cmv/apuracao", token=token, unidade=unidade)
    checar(f"a apuração da {nome} responde", st == 200, (st, ap))
    if st == 200:
        conta = (float(ap.get("estoque_inicial", 0)) + float(ap.get("compras", 0))
                 - float(ap.get("estoque_final", 0)))
        checar(f"e inicial + compras − final = CMV na {nome}",
               perto(conta, ap.get("cmv_real"), 0.05), (conta, ap.get("cmv_real")))


_desativar_filiais_de_teste()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
