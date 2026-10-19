"""Cardápio Vivo, fase 2 (migração 115): o pedido da mesa, os chamados, a identificação e o
painel Atenção × Vendas.

🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`.

⚠️ **O pedido do site não pode mudar**: a CHECK nova exige telefone e pagamento fora do
modo MESA, e esta suíte prova isso direto no banco.

    python tests/smoke_cardapio_pedido.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, time as hora, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1

# 🔑 Suíte devolve o que encontrou: reserva e pedidos da loja, e o Cardápio Vivo dela.
preservar_reserva(U)
# 🔑 Desde a 117, o Cardápio Vivo da loja são DUAS tabelas — a suíte devolve as duas.
from comum import gravar_cardapio, preservar_cardapio_vivo  # noqa: E402
preservar_cardapio_vivo(U)
with get_cursor() as cur:
    cur.execute("SELECT * FROM cardapio_config WHERE id_unidade = %s", (U,))
    _CFG_ANTES = cur.fetchone()
    _CFG_ANTES = dict(_CFG_ANTES) if _CFG_ANTES else None
    cur.execute("SELECT fidelidade_ligada FROM reserva_config WHERE id_unidade = %s", (U,))
    _FID = cur.fetchone()


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM cardapio_config WHERE id_unidade = %s", (U,))
        if _CFG_ANTES:
            cols = list(_CFG_ANTES)
            cur.execute(f"INSERT INTO cardapio_config ({', '.join(cols)}) "
                        f"VALUES ({', '.join(['%s'] * len(cols))})", [_CFG_ANTES[c] for c in cols])
        cur.execute("DELETE FROM cardapio_chamados WHERE id_mesa IN "
                    "(SELECT m.id FROM mesas m JOIN saloes s ON s.id = m.id_salao WHERE s.nome LIKE %s)",
                    (f"%{MARCA}%",))
        cur.execute("DELETE FROM vendas WHERE origem = 'SMOKE_CARDAPIO'")
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM reserva_clientes WHERE nome LIKE %s", (f"%{MARCA}%",))


atexit.register(_devolver)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def produto(nome, preco):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True, "preco_venda": preco}, token)
    return p["id"]


print("0. cenário: cardápio, três pratos (um com adicionais), salão com duas mesas")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Mesa {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Pratos"}, token)
A, B, C = produto("MESA RISOTO", 58), produto("MESA SUCO", 12), produto("MESA TORTA", 20)
itens = {}
for n, pid in (("A", A), ("B", B), ("C", C)):
    _st, it = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": pid}, token)
    itens[n] = it["id"]
_st, ad = chamar("PUT", f"/produtos/{A}/adicionais", [
    {"nome": "Ponto", "minimo": 1, "maximo": 1, "opcoes": [{"nome": "Al dente"}, {"nome": "Macio"}]},
    {"nome": "Extras", "minimo": 0, "maximo": 2, "opcoes": [{"nome": "Parmesão", "preco": 6},
                                                            {"nome": "Trufa", "preco": 15}]}], token)
OP = {o["nome"]: o["id"] for gr in ad["adicionais"] for o in gr["opcoes"]}
_st, salao = chamar("POST", "/reservas/saloes", {"nome": f"Varanda {MARCA}"}, token)
_st, m1 = chamar("POST", "/reservas/mesas", {"id_salao": salao["id"], "nome": "M1", "lugares": 4}, token)
_st, m2 = chamar("POST", "/reservas/mesas", {"id_salao": salao["id"], "nome": "M2", "lugares": 4}, token)
_st, ac = chamar("GET", "/cardapio-vivo/mesas", token=token)
TOK = {m["id"]: m["link"].rsplit("/", 1)[1] for m in ac["mesas"]}
T1, T2 = TOK[m1["id"]], TOK[m2["id"]]
CFG = {"id_catalogo": ID_CAT, "modo": "PEDIDO", "exige_confirmacao": True, "chamar_garcom": False,
       "fonte": "NEWSREADER", "retencao_meses": 13}
st, r = gravar_cardapio(chamar, token, CFG)
checar("a loja liga o modo PEDIDO", st == 200 and r["vivos"][0]["modo"] == "PEDIDO", (st, r))

print("\n1. o feed diz o modo")
_st, f = chamar("GET", f"/publico/cardapio/mesa/{T1}")
checar("na mesa, PEDIDO", f.get("modo") == "PEDIDO", f.get("modo"))
_st, f2 = chamar("GET", f"/publico/cardapio/loja/{U}")
checar("sem mesa (balcão), sempre VITRINE — não há para onde levar", f2.get("modo") == "VITRINE", f2.get("modo"))
checar("chamar garçom desligado na loja: sem botão", f.get("chamar_garcom") is False)

print("\n2. o pedido da mesa")
S = str(uuid.uuid4())


def pedir(tok, itens_, chave=None, telefone=None, sessao=None):
    corpo = {"sessao": sessao or S, "chave": chave or uuid.uuid4().hex, "itens": itens_}
    if telefone:
        corpo["telefone"] = telefone
    return chamar("POST", f"/publico/cardapio/mesa/{tok}/pedido", corpo)


st, r = pedir(T1, [{"item": itens["A"], "quantidade": 1}])
checar("o grupo obrigatório sem escolha é recusado (422), dizendo qual", st == 422 and "Ponto" in r["detail"], (st, r))
st, r = pedir(T1, [{"item": itens["A"], "quantidade": 1,
                    "adicionais": [OP["Al dente"], OP["Macio"]]}])
checar("duas escolhas num grupo de UMA é recusado", st == 422, (st, r))
st, r = pedir(T1, [{"item": itens["A"], "quantidade": 1, "adicionais": [999999]}])
checar("opção que não é do prato é recusada", st == 409, (st, r))
CHAVE = uuid.uuid4().hex
st, p1 = pedir(T1, [{"item": itens["A"], "quantidade": 2, "adicionais": [OP["Al dente"], OP["Trufa"]],
                     "observacao": "sem cebola"},
                    {"item": itens["B"], "quantidade": 1, "preco": 0.01}], chave=CHAVE)
checar("o pedido nasce (201) NOVO", st == 201 and p1.get("situacao") == "NOVO", (st, p1))
checar("o preço é do SERVIDOR, com os adicionais: 2 × (58 + 15) + 12 = 158",
       p1.get("total") == 158.0, p1.get("total"))
checar("mostra a mesa e não tem forma de pagamento", p1.get("mesa") == "M1" and p1.get("forma_pagamento") is None, p1)
checar("os adicionais ficam congelados no item",
       [a["nome"] for a in (p1["itens"][0].get("adicionais") or [])] == ["Al dente", "Trufa"], p1["itens"][0])
st, rep = pedir(T1, [{"item": itens["A"], "quantidade": 9, "adicionais": [OP["Al dente"]]}], chave=CHAVE)
checar("a mesma chave devolve o MESMO pedido (toque duplo, rede ruim)",
       rep.get("numero") == p1.get("numero") and rep.get("repetido") is True, rep)
_st, lista = chamar("GET", f"/publico/cardapio/mesa/{T1}/pedidos?sessao={S}")
checar("a sessão acompanha os próprios pedidos", [x["numero"] for x in lista] == [p1["numero"]], lista)
_st, outra = chamar("GET", f"/publico/cardapio/mesa/{T2}/pedidos?sessao={S}")
checar("e a outra mesa não vê os dela", outra == [], outra)

print("\n3. o painel: coluna Mesas")
_st, pn = chamar("GET", "/pedidos/painel", token=token)
meu = next((x for x in pn.get("mesas", []) if x["numero"] == p1["numero"]), None)
checar("o pedido aparece na coluna Mesas", meu is not None, pn.get("mesas"))
checar("com o rótulo da mesa", meu and meu["modo_rotulo"] == "Mesa M1", meu)
checar("e NÃO na coluna dos novos do site", p1["numero"] not in [x["numero"] for x in pn["novos"]])
ID1 = meu["id"]
st, conf = chamar("POST", f"/pedidos/{ID1}/confirmar", {"itens": [
    {"id_produto": A, "quantidade": 3}, {"id_produto": B, "quantidade": 1}]}, token)
item_a = next(i for i in conf.get("itens", []) if i["id_produto"] == A)
checar("confirmar com troca de quantidade mantém os adicionais do item",
       st == 200 and [a["nome"] for a in item_a.get("adicionais") or []] == ["Al dente", "Trufa"], (st, item_a))
_st, pn = chamar("GET", "/pedidos/painel", token=token)
checar("confirmado, ele espera o lançamento no PDV como os do site",
       ID1 in [x["id"] for x in pn["sem_pdv"]], pn["sem_pdv"])

print("\n4. sem confirmação da equipe, nasce confirmado")
gravar_cardapio(chamar, token, {**CFG, "exige_confirmacao": False})
st, p2 = pedir(T1, [{"item": itens["C"], "quantidade": 1}])
checar("nasce CONFIRMADO", st == 201 and p2.get("situacao") == "CONFIRMADO", (st, p2))
gravar_cardapio(chamar, token, CFG)

print("\n5. o que o feed não oferece, a mesa não pede")
chamar("PUT", f"/catalogos/itens/{itens['C']}/marcas", {"esgotado": True}, token)
st, r = pedir(T1, [{"item": itens["C"], "quantidade": 1}])
checar("esgotado é recusado", st == 409 and "esgotou" in r["detail"], (st, r))
chamar("PUT", f"/catalogos/itens/{itens['C']}/marcas", {"esgotado": False}, token)
st, r = pedir(T1, [{"item": 999999, "quantidade": 1}])
checar("item de fora do cardápio é recusado", st == 409, (st, r))
st, r = chamar("PUT", "/cardapio-vivo/excecoes", {"id_mesa": m2["id"], "modo": "VITRINE"}, token)
st, r = pedir(T2, [{"item": itens["B"], "quantidade": 1}])
checar("mesa com exceção em VITRINE recusa o pedido", st == 409, (st, r))
with get_cursor() as cur:
    cur.execute("DELETE FROM cardapio_excecoes WHERE id_mesa = %s", (m2["id"],))
from relogio import agora_da_casa  # noqa: E402
agora = agora_da_casa().replace(tzinfo=None)
fora_de = (agora + timedelta(hours=2)).time().replace(second=0, microsecond=0)
fora_ate = (agora + timedelta(hours=3)).time().replace(second=0, microsecond=0)
gravar_cardapio(chamar, token, {**CFG, "pedido_hora_de": str(fora_de), "pedido_hora_ate": str(fora_ate)})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{T1}")
checar("fora do horário, o feed cai para VITRINE com 'pedidos com o garçom'",
       f.get("modo") == "VITRINE" and f.get("aviso") == "Pedidos com o garçom.", (f.get("modo"), f.get("aviso")))
st, r = pedir(T1, [{"item": itens["B"], "quantidade": 1}])
checar("e o pedido é recusado com a mesma frase", st == 409 and "garçom" in r["detail"], (st, r))
gravar_cardapio(chamar, token, CFG)

print("\n6. o pedido do site continua exigindo tudo (a CHECK nova)")
with get_cursor() as cur:
    cur.execute("SAVEPOINT s")
    try:
        cur.execute("""INSERT INTO pedidos (id_unidade, numero, nome, modo, para_quando, chave)
                       VALUES (%s, 999999, 'x', 'RETIRADA', now(), %s)""", (U, uuid.uuid4().hex))
        checar("pedido de RETIRADA sem telefone e pagamento é recusado pelo banco", False)
    except Exception:  # noqa: BLE001
        cur.execute("ROLLBACK TO SAVEPOINT s")
        checar("pedido de RETIRADA sem telefone e pagamento é recusado pelo banco", True)

print("\n7. chamar garçom e pedir a conta")
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/chamado", {"tipo": "GARCOM", "sessao": S})
checar("com a opção desligada, 409", st == 409, (st, r))
gravar_cardapio(chamar, token, {**CFG, "chamar_garcom": True})
_st, f = chamar("GET", f"/publico/cardapio/mesa/{T1}")
checar("ligada, o feed mostra os botões", f.get("chamar_garcom") is True)
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/chamado", {"tipo": "GARCOM", "sessao": S})
checar("o chamado abre", st == 200 and r.get("novo") is True, (st, r))
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/chamado", {"tipo": "GARCOM", "sessao": S})
checar("apertar de novo não abre outro (um por mesa e tipo)", st == 200 and r.get("novo") is False, (st, r))
chamar("POST", f"/publico/cardapio/mesa/{T1}/chamado", {"tipo": "CONTA", "sessao": S})
_st, pn = chamar("GET", "/pedidos/painel", token=token)
meus = [c for c in pn.get("chamados", []) if c["mesa"] == "M1" and c["salao"] == f"Varanda {MARCA}"]
checar("o painel mostra os dois chamados da mesa", sorted(c["tipo"] for c in meus) == ["CONTA", "GARCOM"], meus)
st, r = chamar("POST", f"/cardapio-vivo/chamados/{meus[0]['id']}/atender", token=token)
checar("atender fecha o chamado", st == 200, (st, r))
st, r = chamar("POST", f"/cardapio-vivo/chamados/{meus[0]['id']}/atender", token=token)
checar("atender de novo: 404", st == 404, st)

print("\n8. identificação na mesa (fidelidade opcional)")
FONE = f"4799{str(time.time_ns())[-7:]}"
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/identificar", {"telefone": FONE})
checar("telefone sem cadastro e sem nome: pede o nome (422)", st == 422, (st, r))
st, r = chamar("POST", f"/publico/cardapio/mesa/{T1}/identificar",
               {"telefone": FONE, "nome": f"Ana {MARCA}", "aceite_termo": True,
                "genero": "FEMININO", "cidade": "Blumenau", "nascimento": "1990-05-01"})
checar("com nome e aceite, cadastra ali mesmo", st == 200 and r.get("novo") is True and r.get("nome") == "Ana", (st, r))
checar("e diz o que aconteceu na fidelidade (ou nulo se a casa não tem)", "fidelidade" in r, r)
st, p3 = pedir(T1, [{"item": itens["B"], "quantidade": 1}], telefone=FONE)
checar("o pedido de quem se identificou leva o nome da pessoa", st == 201, (st, p3))
with get_cursor() as cur:
    cur.execute("SELECT nome, id_cliente FROM pedidos WHERE id_unidade = %s AND numero = %s",
                (U, p3["numero"]))
    pp = cur.fetchone()
checar("e fica ligado ao cadastro", pp and pp["id_cliente"] and pp["nome"].startswith("Ana"), pp)

print("\n9. objetivo e margem do item")
st, r = chamar("PUT", f"/catalogos/itens/{itens['C']}/marcas", {"objetivo": "LANCAMENTO", "margem_nivel": "ALTA"}, token)
checar("objetivo e margem manual gravam", r.get("objetivo") == "LANCAMENTO" and r.get("margem_nivel") == "ALTA", r)
st, r = chamar("PUT", f"/catalogos/itens/{itens['C']}/marcas", {"objetivo": "VENDER_TUDO"}, token)
checar("objetivo fora da lista é recusado", st == 422, st)
st, r = chamar("PUT", f"/catalogos/itens/{itens['B']}/marcas", {"margem_nivel": ""}, token)
checar("margem manual vazia volta ao calculado", st == 200 and r.get("margem_nivel") is None, r)

print("\n10. o painel Atenção × Vendas")
SE, SN = str(uuid.uuid4()), str(uuid.uuid4())
lote = {"sessao": SE, "loja": U, "mesa": T1, "modo": "PEDIDO", "dispositivo": "CELULAR", "eventos": [
    {"tipo": "viu_item", "item": itens["A"], "midia": "FOTO", "duracao_ms": 90000},
    {"tipo": "viu_item", "item": itens["B"], "midia": "FOTO", "duracao_ms": 4000},
    {"tipo": "deslizou_tras", "item": itens["A"]}, {"tipo": "favoritou", "item": itens["A"]},
    {"tipo": "adicionou", "item": itens["A"]}, {"tipo": "removeu", "item": itens["A"]},
    {"tipo": "abriu_hub"}, {"tipo": "clicou_wifi"}]}
lote2 = {"sessao": SN, "loja": U, "mesa": T1, "modo": "PEDIDO", "dispositivo": "CELULAR",
         "eventos": [{"tipo": "viu_item", "item": itens["B"], "midia": "FOTO", "duracao_ms": 1000}]}
for l in (lote, lote2):
    req = urllib.request.Request(BASE + "/publico/cardapio/eventos", data=json.dumps(l).encode(),
                                 method="POST", headers={"Content-Type": "text/plain"})
    urllib.request.urlopen(req).read()
with get_cursor() as cur:
    cur.execute("""INSERT INTO vendas (id_unidade, data, hora, origem, valor_total)
                   VALUES (%s, current_date, '12:00', 'SMOKE_CARDAPIO', 120) RETURNING id""", (U,))
    vid = cur.fetchone()["id"]
    cur.execute("""INSERT INTO venda_itens (id_venda, id_produto, quantidade, valor_unitario, valor_total)
                   VALUES (%s, %s, 10, 12, 120)""", (vid, B))
hoje = date.today()
st, pa = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}", token=token)
checar("o painel responde", st == 200, (st, pa))
checar("e traz as definições para a tela mostrar", {"sessao_engajada", "atencao_estimada", "deslize_tras"}
       <= set((pa.get("definicoes") or {})), pa.get("definicoes"))
por = {l["id_produto"]: l for l in pa.get("itens", [])}
la, lb = por.get(A, {}), por.get(B, {})
checar("só a sessão ENGAJADA conta nos itens (a outra viu um prato só)", lb.get("visualizacoes") == 1, lb)
checar("atenção estimada com teto: 90 s viram 60 s", la.get("atencao_ms") == 60000, la)
checar("favoritos, deslizes para trás e 'quase pediu' por item",
       la.get("favoritos") == 1 and la.get("deslizes_tras") == 1 and la.get("quase_pediu", 0) >= 1, la)
checar("a venda do PDV entra no item", lb.get("vendas_qtd") == 10.0, lb)
checar("o topo separa sessões abertas de engajadas e conta o Wi-Fi",
       pa["topo"]["sessoes"] >= 2 and pa["topo"]["engajadas"] >= 1
       and pa["topo"]["engajadas"] < pa["topo"]["sessoes"] and pa["topo"]["cliques_wifi"] >= 1, pa.get("topo"))
checar("o funil vai de abriu a enviou", set(pa["funil"]) == {"sessoes", "viram", "adicionaram", "enviaram"})
checar("os chamados trazem o tempo de atendimento", "GARCOM" in pa.get("chamados", {}), pa.get("chamados"))
checar("muita atenção e pouca venda → revisar", la.get("sugestao") == "REVISAR", la)
lc = por.get(C, {})
checar("lançamento com pouca atenção sobe para destaque, no topo da lista",
       lc.get("sugestao") == "DESTACAR" and pa["itens"][0]["id_produto"] == C, (lc, pa["itens"][0]))
outro = (hoje.isoweekday() % 7) + 1
st, pa2 = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}&dias={outro}", token=token)
checar("filtrar outro dia da semana zera a atenção de hoje",
       all(l["visualizacoes"] == 0 for l in pa2.get("itens", [])), pa2.get("itens"))
st, r = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}&hora_de=10:00", token=token)
checar("só uma ponta do horário é recusada", st == 422, st)
# 🔑 (122) O painel olha o cardápio PRINCIPAL: o mesmo prato visto noutro Cardápio Vivo da loja
# (o catering) não soma aqui. Sessão engajada (favoritou) de outro catálogo, gravada direto.
with get_cursor() as cur:
    s_outro = str(uuid.uuid4())
    cur.execute("INSERT INTO cardapio_sessoes (id, id_unidade, modo) VALUES (%s, %s, 'VITRINE')", (s_outro, U))
    for tipo in ("viu_item", "favoritou"):
        cur.execute("""INSERT INTO cardapio_eventos (id_sessao, id_unidade, tipo, id_produto, id_catalogo,
                                                     modo, duracao_ms)
                       VALUES (%s, %s, %s, %s, -1, 'VITRINE', 5000)""", (s_outro, U, tipo, A))
st, pa3 = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}", token=token)
la3 = {l["id_produto"]: l for l in pa3.get("itens", [])}.get(A, {})
checar("o prato visto noutro Cardápio Vivo da loja não soma no painel do principal",
       la3.get("visualizacoes") == la.get("visualizacoes") and pa3["topo"]["sessoes"] == pa["topo"]["sessoes"],
       (la3.get("visualizacoes"), la.get("visualizacoes")))
# 🔑 (1.1.109) E o painel mede também os OUTROS Cardápios Vivos da loja, um de cada vez.
_st, cat2 = chamar("POST", "/catalogos", {"nome": f"Catering {MARCA}", "origem": "PRODUTOS",
                                          "situacao": "ATIVO"}, token)
ID_CAT2 = cat2["id"]
_st, g2 = chamar("POST", f"/catalogos/{ID_CAT2}/categorias", {"nome": "Pratos"}, token)
_st, it2 = chamar("POST", f"/catalogos/categorias/{g2['id']}/itens", {"id_produto": A}, token)
st, r = chamar("PUT", f"/cardapio-vivo/vivos/{ID_CAT2}", {"modo": "VITRINE", "principal": False}, token)
checar("um segundo Cardápio Vivo na loja, sem ser o principal", st == 200, (st, r))
lote3 = {"sessao": str(uuid.uuid4()), "loja": U, "catalogo": ID_CAT2, "modo": "VITRINE",
         "dispositivo": "CELULAR", "eventos": [
             {"tipo": "viu_item", "item": it2["id"], "midia": "FOTO", "duracao_ms": 7000},
             {"tipo": "favoritou", "item": it2["id"]}]}
req = urllib.request.Request(BASE + "/publico/cardapio/eventos", data=json.dumps(lote3).encode(),
                             method="POST", headers={"Content-Type": "text/plain"})
urllib.request.urlopen(req).read()
st, pc = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}&id_catalogo={ID_CAT2}", token=token)
lc2 = {l["id_produto"]: l for l in pc.get("itens", [])}.get(A, {})
checar("o painel do outro cardápio diz qual é e lista os da loja para escolher",
       st == 200 and pc["cardapio"]["id_catalogo"] == ID_CAT2 and not pc["cardapio"]["principal"]
       and {ID_CAT, ID_CAT2} <= {c["id_catalogo"] for c in pc["cardapios"]}, (st, pc.get("cardapio")))
checar("e conta só o que veio dele: uma sessão, uma visualização de 7 s",
       pc["topo"]["sessoes"] == 1 and lc2.get("visualizacoes") == 1 and lc2.get("atencao_ms") == 7000,
       (pc.get("topo"), lc2))
checar("os pratos são os do cardápio escolhido", [l["id_produto"] for l in pc["itens"]] == [A], pc.get("itens"))
_st, pa4 = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}", token=token)
checar("sem escolher, segue o principal — e ele não ganhou a sessão do outro",
       pa4["cardapio"]["id_catalogo"] == ID_CAT and pa4["topo"]["sessoes"] == pa["topo"]["sessoes"],
       (pa4.get("cardapio"), pa4.get("topo")))
st, r = chamar("GET", f"/cardapio-vivo/atencao?de={hoje}&ate={hoje}&id_catalogo=999999", token=token)
checar("catálogo que não é Cardápio Vivo da loja: 404", st == 404, (st, r))
st, r = chamar("GET", f"/cardapio-vivo/destaques/sugestoes?de={hoje}&ate={hoje}&id_catalogo={ID_CAT2}", token=token)
checar("as sugestões de destaque também por cardápio", st == 200 and isinstance(r, list), (st, r))
st, r = chamar("POST", "/cardapio-vivo/testes", {"tipo": "MIDIA", "id_item": itens["A"], "id_catalogo": ID_CAT2}, token)
checar("o teste A/B procura o prato no cardápio ESCOLHIDO (o item do principal não serve)",
       st == 404 and "neste Cardápio Vivo" in r.get("detail", ""), (st, r))
chamar("DELETE", f"/cardapio-vivo/vivos/{ID_CAT2}", token=token)
from services import cardapio_atencao as ca  # noqa: E402
from decimal import Decimal  # noqa: E402
checar("nível de margem pela margem-alvo (meta 30%): 35 alta, 25 média, 15 baixa, sem meta nulo",
       [ca._nivel_de_margem(Decimal(x), Decimal(30)) for x in (35, 25, 15)] == ["ALTA", "MEDIA", "BAIXA"]
       and ca._nivel_de_margem(Decimal(35), Decimal(0)) is None)
checar("MANTER não vira candidato a sair", ca._sugestao(False, False, None, "MANTER")[0] is None)

print("\n11. apagar a mesa não esbarra no pedido antigo dela")
st, r = chamar("DELETE", f"/reservas/mesas/{m2['id']}", token=token)
checar("a mesa sem pedido sai", st == 200, (st, r))
with get_cursor() as cur:
    cur.execute("DELETE FROM mesas WHERE id = %s", (m1["id"],))
    cur.execute("SELECT mesa_nome, id_mesa FROM pedidos WHERE id = %s", (ID1,))
    pm = dict(cur.fetchone())
checar("apagada a mesa com pedidos, o pedido guarda o nome dela", pm == {"mesa_nome": "M1", "id_mesa": None}, pm)
chamar("DELETE", f"/reservas/saloes/{salao['id']}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
