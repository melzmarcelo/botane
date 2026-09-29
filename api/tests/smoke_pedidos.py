"""Pedidos pelo catálogo do site: configuração, carrinho, confirmação com troca, PDV e entrega.

🔑 **Pedido do dono (28/09/2026):** *"o cliente poder realizar pedidos diretamente na tela de
catálogo … um carrinho … uma tela com pedidos, um painel e aviso na tela inicial."* Decisões em
`docs/pedidos-estudo.md` (seção 0). Migração 101, `services/pedidos.py`.

    python tests/smoke_pedidos.py        (API de pé na 9200)
"""

import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha, preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
_pool_pronto = False


def chamar(metodo, caminho, corpo=None, token=None):
    # ⚠️ O site tem limite de tentativas por origem, e a suíte bate nele dezenas de vezes
    # seguidas: zera antes de cada chamada pública, como `smoke_publico` e `smoke_fidelidade`.
    if caminho.startswith("/publico") and _pool_pronto:
        with get_cursor() as cur:
            cur.execute("DELETE FROM reserva_tentativas")
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"), method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            bruto = r.read()
            return r.status, (json.loads(bruto or b"null") if not bruto.startswith(b"%PDF")
                              else bruto)
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


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
cozinha = garantir_cozinha(chamar, token)
init_pool()
_pool_pronto = True
MARCA = str(time.time_ns() // 100)[-6:]
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1

# 🔑 A suíte mexe no horário e nos clientes da loja: devolve tudo como encontrou (e os
# pedidos da loja junto — ver `preservar_reserva`).
preservar_reserva(U)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)
with get_cursor() as cur:
    # A casa aberta o dia todo, todo dia, sem bloqueio: o que a suíte testa é o pedido, não o
    # relógio do dia em que ela roda.
    cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (U,))
    cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (U,))
    for d in range(1, 8):
        cur.execute(
            """INSERT INTO reserva_horarios (id_unidade, dia_semana, aberto, abre, fecha, ultima_reserva)
               VALUES (%s, %s, true, '00:00', '23:59', '23:00')
               ON CONFLICT (id_unidade, dia_semana) DO UPDATE
                  SET aberto = true, abre = '00:00', fecha = '23:59', ultima_reserva = '23:00'""",
            (U, d))


def produto(nome, preco=None):
    _st, p = chamar("POST", "/produtos", {"nome": f"{nome} {MARCA}", "tipo": "INSUMO",
                                          "um_estoque": "UN", "controla_estoque": False}, token)
    # "Vai ao PDV" é o que deixa o produto entrar no catálogo; o sem preço também vai.
    _st, atual = chamar("GET", f"/produtos/{p['id']}", token=token)
    chamar("PUT", f"/produtos/{p['id']}", {**atual, "integrado_pdv": True,
                                            **({"preco_venda": preco} if preco is not None else {})},
           token)
    return p["id"]


print("0. cenário: um cardápio de produtos no ar, e um PDF")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Delivery {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat.get("id")
_st, pdf = chamar("POST", "/catalogos", {"nome": f"Menu PDF {MARCA}", "origem": "PDF"}, token)
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias", {"nome": "Lanches"}, token)
A, B, C, D = (produto("PED SANDUICHE", 10), produto("PED SUCO", 7.5), produto("PED SEM PRECO"),
              produto("PED TORTA", 12))
itens = {}
for nome, pid in (("A", A), ("B", B), ("C", C), ("D", D)):
    _st, it = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": pid}, token)
    itens[nome] = it.get("id")
checar("o catálogo e os quatro itens existem", ID_CAT and all(itens.values()), itens)

print("\n1. a configuração é do catálogo, e só do tipo Produtos")
st, cfg = chamar("GET", f"/pedidos/config/{ID_CAT}", token=token)
checar("nasce desligada", st == 200 and cfg.get("aceita") is False, (st, cfg))
st, r = chamar("GET", f"/publico/{U}/catalogos/{ID_CAT}")
checar("e o cardápio público não traz carrinho", st == 200 and r.get("pedidos") is None, (st, r))
checar("mas cada item já tem o id, para o carrinho",
       all(i.get("id") for c in r.get("categorias", []) for i in c["itens"]), r)
st, r = chamar("PUT", f"/pedidos/config/{pdf['id']}", {"aceita": True}, token)
checar("catálogo PDF não aceita pedido", st == 400, (st, r))
CFG = {"aceita": True, "retirada": True, "entrega": True, "taxa_entrega": 5,
       "pedido_minimo": 15, "antecedencia_min": 30, "antecedencia_max_dias": 7,
       "pagamentos": ["RETIRADA", "ENTREGA", "WHATSAPP"],
       "texto_pagamento": "O pagamento é na retirada ou na entrega."}
st, r = chamar("PUT", f"/pedidos/config/{ID_CAT}", {**CFG, "retirada": False, "entrega": False},
               token)
checar("ligado sem retirada nem entrega é recusado", st == 422, st)
st, r = chamar("PUT", f"/pedidos/config/{ID_CAT}", CFG, token)
checar("liga os pedidos", st == 200 and r.get("aceita") is True, (st, r))
st, r = chamar("PUT", f"/pedidos/config/{ID_CAT}", CFG, cozinha)
checar("a cozinha não configura (403)", st == 403, st)
st, r = chamar("GET", f"/publico/{U}/catalogos/{ID_CAT}")
pc = (r or {}).get("pedidos") or {}
checar("agora o cardápio traz a configuração do carrinho",
       len(pc.get("modos", [])) == 2 and pc.get("pedido_minimo") == 15
       and pc.get("texto_pagamento") and len(pc.get("dias", [])) >= 7, pc)

print("\n2. o envio pelo site")
FONE = f"4799{random.randint(1000000, 9999999)}"
corpo = {"telefone": FONE, "chave": f"carrinho-{MARCA}-1", "modo": "RETIRADA",
         "forma_pagamento": "RETIRADA", "itens": [{"id_item": itens["A"], "quantidade": 2},
                                                  {"id_item": itens["B"], "quantidade": 1,
                                                   "observacao": "sem gelo"}]}
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", corpo)
checar("sem cadastro, 403 dizendo o que fazer", st == 403 and "cadastro" in str(r), (st, r))
st, r = chamar("POST", f"/publico/{U}/cliente", {
    "telefone": FONE, "nome": "Paula Pedido", "genero": "FEMININO", "cidade": "Blumenau",
    "nascimento": "1990-05-10", "aceite_termo": True})
checar("a cliente se cadastra", st == 200, (st, r))
st, p1 = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", corpo)
checar("o pedido entra NOVO, com número", st == 201 and p1.get("situacao") == "NOVO"
       and p1.get("numero"), (st, p1))
checar("o preço é do SERVIDOR: 2 × 10 + 7,50 = 27,50",
       p1.get("subtotal") == 27.5 and p1.get("total") == 27.5, p1)
checar("e a observação do item vem junto",
       any(i["observacao"] == "sem gelo" for i in p1.get("itens", [])), p1.get("itens"))
st, rep = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", corpo)
checar("enviar de novo (toque duplo) devolve o MESMO pedido",
       st == 201 and rep.get("numero") == p1.get("numero") and rep.get("repetido") is True,
       (st, rep))
novo = lambda n, **x: {**corpo, "chave": f"carrinho-{MARCA}-{n}", **x}  # noqa: E731
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
               novo(2, itens=[{"id_item": itens["A"], "quantidade": 1}]))
checar("abaixo do pedido mínimo é recusado", st == 400 and "mínimo" in str(r), (st, r))
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
               novo(3, itens=[{"id_item": itens["C"], "quantidade": 3}]))
checar("item sem preço não entra", st == 409, (st, r))
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
               novo(4, itens=[{"id_item": 999999999, "quantidade": 3}]))
checar("item que não é do cardápio não entra", st == 409, (st, r))
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", novo(5, modo="ENTREGA"))
checar("entrega sem endereço é recusada", st == 400 and "endereço" in str(r), (st, r))
st, p2 = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
                novo(6, modo="ENTREGA", endereco="Rua das Flores, 10", forma_pagamento="ENTREGA"))
checar("com endereço, a taxa entra no total (27,50 + 5)",
       st == 201 and p2.get("taxa_entrega") == 5 and p2.get("total") == 32.5, (st, p2))
agora = datetime.now()
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
               novo(7, para_quando=(agora + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")))
checar("encomenda antes da antecedência mínima é recusada", st == 400, (st, r))
st, r = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
               novo(8, para_quando=(agora + timedelta(days=10)).strftime("%Y-%m-%dT12:00")))
checar("encomenda além da antecedência máxima é recusada", st == 400, (st, r))
amanha = (agora + timedelta(days=1)).strftime("%Y-%m-%dT15:00")
st, p3 = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido",
                novo(9, para_quando=amanha, forma_pagamento="WHATSAPP"))
checar("encomenda para amanhã às 15h entra, com a hora da casa",
       st == 201 and p3.get("para_quando", "").startswith(amanha[:16]), (st, p3))

print("\n3. meus pedidos, e o cancelar do cliente")
st, m = chamar("POST", f"/publico/{U}/pedidos/meus", {"telefone": FONE})
checar("a cliente vê os três pedidos", st == 200 and len(m.get("pedidos", [])) == 3, (st, m))
st, r = chamar("POST", f"/publico/{U}/pedidos/{p2['numero']}/cancelar", {"telefone": FONE})
checar("cancela o pedido ainda NOVO", st == 200 and r.get("situacao") == "CANCELADO", (st, r))
st, m = chamar("POST", f"/publico/{U}/pedidos/meus", {"telefone": "4799" + "0" * 7})
checar("telefone sem cadastro: lista vazia, não 404", st == 200 and m == {"pedidos": []}, (st, m))

print("\n4. a casa: lista, painel e Início")
with get_cursor() as cur:
    cur.execute("SELECT id FROM pedidos WHERE id_unidade = %s AND numero = %s", (U, p1["numero"]))
    ID1 = cur.fetchone()["id"]
    cur.execute("SELECT id FROM pedidos WHERE id_unidade = %s AND numero = %s", (U, p3["numero"]))
    ID3 = cur.fetchone()["id"]
st, lista = chamar("GET", "/pedidos?situacao=novos&limite=200", token=token)
checar("a lista de novos traz os pedidos", st == 200 and {ID1, ID3} <= {x["id"] for x in lista},
       (st, lista[:1] if isinstance(lista, list) else lista))
st, r = chamar("GET", "/pedidos?situacao=novos", token=cozinha)
checar("a cozinha não vê pedidos (403)", st == 403, st)
st, pn = chamar("GET", "/pedidos/painel", token=token)
checar("o painel tem os novos na primeira coluna",
       st == 200 and ID1 in [x["id"] for x in pn.get("novos", [])], (st, pn))
st, ini = chamar("GET", "/inicio", token=token)
checar("o Início traz o bloco de pedidos", (ini.get("pedidos") or {}).get("novos", 0) >= 2,
       ini.get("pedidos"))

print("\n5. confirmar com troca de produtos")
st, r = chamar("POST", f"/pedidos/{ID3}/lancado-pdv", {"cupom": "X"}, token)
checar("pedido NOVO não se lança no PDV", st == 409, (st, r))
st, troca = chamar("GET", f"/pedidos/{ID1}/catalogo", token=token)
checar("o catálogo para troca traz só itens com preço",
       st == 200 and {x["id_produto"] for x in troca} >= {A, B, D}
       and C not in {x["id_produto"] for x in troca}, troca)
st, c1 = chamar("POST", f"/pedidos/{ID1}/confirmar", {"itens": [
    {"id_produto": A, "quantidade": 1},
    {"id_item_catalogo": itens["D"], "quantidade": 1}]}, token)
checar("confirma trocando o suco pela torta, e a frase diz",
       st == 200 and c1.get("situacao") == "CONFIRMADO" and c1.get("alterado") is True
       and "trocados" in c1.get("message", ""), (st, c1))
checar("o total recalcula no servidor: 10 + 12 = 22", c1.get("total") == 22, c1.get("total"))
hist = [h for h in c1.get("historico", []) if h["acao"] == "CONFIRMADO"]
checar("o histórico guarda o que a cliente pediu",
       hist and len((hist[0].get("detalhe") or {}).get("pedido_pelo_cliente", [])) == 2, hist)
st, r = chamar("POST", f"/pedidos/{ID1}/confirmar", {}, token)
checar("confirmar de novo é recusado", st == 409, st)
st, m = chamar("POST", f"/publico/{U}/pedidos/meus", {"telefone": FONE})
visto = next((x for x in m.get("pedidos", []) if x["numero"] == p1["numero"]), {})
checar("a cliente vê o pedido como ficou", visto.get("total") == 22 and visto.get("alterado"),
       visto)
st, r = chamar("POST", f"/publico/{U}/pedidos/{p1['numero']}/cancelar", {"telefone": FONE})
checar("e já não cancela sozinha depois de confirmado", st == 409, (st, r))

print("\n6. lançado no PDV, a venda ligada pelo cupom, pago e entregue")
CUPOM = f"C{MARCA}"
st, r = chamar("POST", f"/pedidos/{ID1}/lancado-pdv", {"cupom": CUPOM}, token)
checar("marca lançado no PDV com o cupom",
       st == 200 and r.get("lancado_pdv_em") and r.get("cupom_pdv") == CUPOM, (st, r))
st, pn = chamar("GET", "/pedidos/painel", token=token)
checar("e sai da coluna 'falta lançar no PDV'",
       ID1 not in [x["id"] for x in pn.get("sem_pdv", [])], pn.get("sem_pdv"))
with get_cursor() as cur:
    cur.execute("""INSERT INTO vendas (id_unidade, data, origem, documento, valor_total)
                   VALUES (%s, current_date, 'SMOKE_PEDIDO', %s, 22) RETURNING id""", (U, CUPOM))
    ID_VENDA = cur.fetchone()["id"]
st, r = chamar("GET", f"/pedidos/{ID1}", token=token)
checar("quando a venda chega com aquele cupom, o pedido a acha (sem criar venda)",
       r.get("id_venda") == ID_VENDA, r.get("id_venda"))
st, r = chamar("POST", f"/pedidos/{ID1}/pago", {"como": "PIX"}, token)
checar("registra o pagamento", st == 200 and r.get("pago_como") == "PIX", (st, r))
st, r = chamar("POST", f"/pedidos/{ID1}/entregar", token=token)
checar("entrega", st == 200 and r.get("situacao") == "ENTREGUE", (st, r))
st, r = chamar("POST", f"/pedidos/{ID3}/recusar", {"motivo": "sem torta amanhã"}, token)
checar("recusa o outro, com motivo", st == 200 and r.get("situacao") == "RECUSADO", (st, r))
st, m = chamar("POST", f"/publico/{U}/pedidos/meus", {"telefone": FONE})
visto = next((x for x in m.get("pedidos", []) if x["numero"] == p3["numero"]), {})
checar("e a cliente vê o motivo", visto.get("motivo") == "sem torta amanhã", visto)
st, conteudo = chamar("GET", f"/pedidos/{ID1}/pdf", token=token)
checar("o pedido sai em PDF", st == 200 and isinstance(conteudo, bytes)
       and conteudo[:4] == b"%PDF", st)

print("\n7. os alertas")
st, p4 = chamar("POST", f"/publico/{U}/catalogos/{ID_CAT}/pedido", novo(10))
with get_cursor() as cur:
    cur.execute("UPDATE pedidos SET criado_em = now() - interval '20 minutes' "
                "WHERE id_unidade = %s AND numero = %s", (U, p4["numero"]))
st, al = chamar("GET", "/alertas", token=token)
lista_al = al if isinstance(al, list) else (al or {}).get("alertas", [])
checar("pedido novo parado há 15 min vira alerta crítico",
       any(a.get("chave") == "pedidos.parados" for a in lista_al), str(al)[:300])

with get_cursor() as cur:
    cur.execute("DELETE FROM vendas WHERE id = %s", (ID_VENDA,))
    cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
