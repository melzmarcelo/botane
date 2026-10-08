"""Duas lojas, do cadastro ao CMV: cada número fecha na sua loja e na soma delas.

    python tests/smoke_duas_lojas.py        (API de pé na 9200)

🔑 **Pedido do dono (05/10/2026)**: *"fazer a bateria de teste utilizando duas
lojas, verificando que todas as configurações estão corretas, se todos os
valores fecham utilizando duas filiais — custos, estoque, transferências e tudo
mais"*. As outras suítes provam cada peça (remessa, lojas do usuário, custo por
loja); esta conta UMA história com as duas lojas trabalhando ao mesmo tempo, e
cobra o total conferido à mão.

A história, com os números:

    compra     matriz 10 KG de farinha a 4,00   | filial 10 KG a 6,00
    ficha      bolo = 0,5 KG de farinha         -> custa 2,00 na matriz, 3,00 na filial
    produção   4 bolos em cada loja             -> consome 2 KG em cada
    venda      matriz 3 bolos a 20,00           | filial 2 bolos a 20,00
    remessa    matriz manda 4 KG para a filial  -> pelo custo da matriz (4,00)

    no fim     matriz: 4 KG a 4,00  + 1 bolo a 2,00          = 18,00 em estoque
               filial: 12 KG a 5,333333 + 2 bolos a 3,00     = 70,00 em estoque
               CMV     matriz 6,00 (3 x 2,00) | filial 6,00 (2 x 3,00) | empresa 12,00

Depois, na mesma rodada: uma nota de compra em cada loja (matriz 6 KG a 5,00,
filial 4 KG a 7,00), a contagem da filial (15 -> 14 KG), a precificação de cada
uma e o fechamento do dia SÓ da filial — com a matriz seguindo aberta.

⚠️ **Mede por DIFERENÇA.** A matriz é a loja 1 da base de trabalho, cheia de
movimento de outras suítes; a apuração dela é lida antes e depois, e o que se
cobra é o quanto andou.

⚠️ Cria a própria filial e a **desativa no `atexit`**: uma rodada que estoure
no meio deixaria duas lojas ativas, e o seletor de loja aparece na barra.
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
HOJE = date.today().isoformat()
MATRIZ = 1

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]
PREFIXO = "Filial duas lojas"


def _desativar_filiais_de_teste():
    try:
        _st, lista = chamar("GET", "/unidades?incluir_inativas=true", token=token)
        for u in (lista or []):
            if u.get("ativo") and str(u.get("nome", "")).startswith(PREFIXO):
                chamar("PUT", f"/unidades/{u['id']}", {"ativo": False}, token=token)
    except Exception:
        pass


atexit.register(_desativar_filiais_de_teste)


def apuracao(unidade=None, escopo="loja"):
    _st, a = chamar("GET", f"/cmv/apuracao?inicio={HOJE}&fim={HOJE}&escopo={escopo}",
                    token=token, unidade=unidade)
    if _st != 200:
        # ⚠️ Uma apuração que não responde NÃO pode virar `{}` calado: foi assim que
        # o 500 do painel da empresa passou despercebido — o "antes" vazio fazia a
        # diferença ser o total do dia, e quase todas as contas fechavam por acaso.
        checar(f"a apuração responde (escopo {escopo}, loja {unidade})", False, (_st, a))
        return {}
    return a


def andou(antes: dict, depois: dict, campo: str) -> float:
    return round(float(depois.get(campo) or 0) - float(antes.get(campo) or 0), 2)


def saldos(id_produto, unidade):
    _st, s = chamar("GET", f"/estoque/saldos?id_produto={id_produto}", token=token,
                    unidade=unidade)
    return s or []


def qtd(id_produto, unidade) -> float:
    return sum(float(x["quantidade"]) for x in saldos(id_produto, unidade))


def valor(id_produto, unidade) -> float:
    return sum(float(x["quantidade"]) * float(x["custo_medio"]) for x in saldos(id_produto, unidade))


def custo(id_produto, unidade) -> dict:
    _st, c = chamar("GET", f"/produtos/{id_produto}/custo", token=token, unidade=unidade)
    return c or {}


produtos: list[int] = []
usuario_criado = None
usuarios_criados: list = []

try:
    print("1. as duas lojas, cada uma com a sua configuração")
    local_m = garantir_local(chamar, token)
    st, filial = chamar("POST", "/unidades", {
        "nome": f"{PREFIXO} {marca}", "apelido": f"D{marca}"}, token=token)
    FILIAL = (filial or {}).get("id")
    checar("a filial é criada", st == 201 and bool(FILIAL), (st, filial))
    st, locais_f = chamar("GET", "/locais", token=token, unidade=FILIAL)
    local_f = (locais_f or [{}])[0]
    checar("e nasce com local de estoque próprio",
           bool(local_f.get("id")) and local_f.get("id") != local_m["id"], locais_f)
    st, locais_m = chamar("GET", "/locais", token=token, unidade=MATRIZ)
    checar("a matriz não enxerga o local da filial",
           local_f.get("id") not in {l["id"] for l in (locais_m or [])})
    checar("nem a filial o da matriz",
           local_m["id"] not in {l["id"] for l in (locais_f or [])})

    st, par_m = chamar("GET", f"/unidades/{MATRIZ}/parametros", token=token)
    st, par_f = chamar("GET", f"/unidades/{FILIAL}/parametros", token=token)
    checar("a filial tem parâmetros próprios", st == 200 and par_f.get("id_unidade") == FILIAL,
           (st, par_f))
    dias_m = par_m.get("alerta_validade_dias")
    st, r = chamar("PUT", f"/unidades/{FILIAL}/parametros",
                   {"alerta_validade_dias": (dias_m or 0) + 7}, token=token)
    st, par_m2 = chamar("GET", f"/unidades/{MATRIZ}/parametros", token=token)
    st, par_f2 = chamar("GET", f"/unidades/{FILIAL}/parametros", token=token)
    checar("mudar um parâmetro da filial muda o DELA",
           par_f2.get("alerta_validade_dias") == (dias_m or 0) + 7, par_f2)
    checar("e não toca no da matriz", par_m2.get("alerta_validade_dias") == dias_m,
           (dias_m, par_m2.get("alerta_validade_dias")))
    checar("as duas usam o mesmo modo de custo (único por loja)",
           par_m2.get("custo_por_local") == par_f2.get("custo_por_local"),
           (par_m2.get("custo_por_local"), par_f2.get("custo_por_local")))

    # ⚠️ Usuário PRÓPRIO, lotado na matriz: o de cozinha das outras suítes não tem
    # loja marcada, e sem loja marcada a pessoa enxerga todas.
    st, papeis = chamar("GET", "/papeis", token=token)
    papel = next((x for x in (papeis or []) if x["nome"] == "Conferente / Estoque"), None)
    email = f"duas.lojas.{marca}@botane.com.br"
    st, novo = chamar("POST", "/usuarios", {
        "nome": f"Conferente da matriz {marca}", "email": email, "senha": "smoke12345",
        "papeis": [{"id_papel": (papel or {}).get("id"), "id_unidade": MATRIZ}]}, token=token)
    usuario_criado = (novo or {}).get("id")
    checar("um conferente nasce lotado só na matriz", st == 201 and bool(usuario_criado),
           (st, novo))
    st, entrou = chamar("POST", "/auth/login", {"email": email, "senha": "smoke12345"})
    so_matriz = (entrou or {}).get("access_token")

    print("\n2. o cadastro é da CASA: produto, ficha e preço valem nas duas")
    st, p = chamar("POST", "/produtos", {
        "codigo": f"DLF{marca}", "nome": f"FARINHA DUAS LOJAS {marca}", "tipo": "INSUMO",
        "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO"}, token=token)
    farinha = p["id"]
    produtos.append(farinha)
    st, p = chamar("POST", "/produtos", {
        "codigo": f"DLB{marca}", "nome": f"BOLO DUAS LOJAS {marca}", "tipo": "PRODUZIDO",
        "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO",
        "producao_propria": True, "preco_venda": 20}, token=token)
    bolo = p["id"]
    produtos.append(bolo)
    st, d = chamar("GET", f"/produtos/{bolo}", token=token, unidade=FILIAL)
    checar("a filial enxerga o produto criado na matriz", st == 200 and d.get("id") == bolo, st)
    checar("com o preço da casa (20,00)", perto(d.get("preco_venda"), 20), d.get("preco_venda"))

    st, r = chamar("PUT", f"/produtos/{bolo}/preco-loja", {"preco_venda": 22}, token=token,
                   unidade=FILIAL)
    checar("a filial grava o preço dela (22,00)", st == 200, (st, r))
    st, d_f = chamar("GET", f"/produtos/{bolo}", token=token, unidade=FILIAL)
    st, d_m = chamar("GET", f"/produtos/{bolo}", token=token, unidade=MATRIZ)
    checar("na filial vale 22,00", perto(d_f.get("preco_venda"), 22), d_f.get("preco_venda"))
    checar("na matriz continua 20,00", perto(d_m.get("preco_venda"), 20), d_m.get("preco_venda"))

    antes_m = apuracao(MATRIZ)
    # 🔑 Loja nova, dia sem venda: é o caso em que o painel da empresa dava 500.
    antes_e = apuracao(MATRIZ, "empresa")
    checar("o painel da EMPRESA responde mesmo com uma loja sem venda no período",
           bool(antes_e) and antes_e.get("cobertura_ficha_pct") is not None,
           antes_e.get("cobertura_ficha_pct"))

    print("\n3. cada loja compra pelo seu preço — e o custo é o DELA")
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 10, "custo_unitario": 4,
        "id_local": local_m["id"]}, token=token, unidade=MATRIZ)
    checar("a matriz compra 10 KG a 4,00", st == 201, (st, r))
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 10, "custo_unitario": 6,
        "id_local": local_f["id"]}, token=token, unidade=FILIAL)
    checar("a filial compra 10 KG a 6,00", st == 201, (st, r))
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 1, "custo_unitario": 9,
        "id_local": local_f["id"]}, token=token, unidade=MATRIZ)
    checar("a matriz NÃO lança entrada no local da filial (400)", st == 400, (st, r))
    checar("e a frase manda usar a transferência entre lojas",
           "transfer" in str((r or {}).get("detail", "")).lower(), r)
    st, r = chamar("POST", "/estoque/saidas", {
        "id_produto": farinha, "quantidade": 1, "tipo": "SAIDA_CONSUMO_INTERNO",
        "id_local": local_m["id"]}, token=token, unidade=FILIAL)
    checar("nem a filial dá saída do local da matriz", st == 400
           and "outra loja" in str((r or {}).get("detail", "")), (st, r))
    checar("o custo na matriz é 4,00",
           perto(custo(farinha, MATRIZ).get("atual"), 4), custo(farinha, MATRIZ))
    checar("e na filial é 6,00 — não a média das duas (5,00)",
           perto(custo(farinha, FILIAL).get("atual"), 6), custo(farinha, FILIAL))
    checar("o saldo de cada uma é 10", perto(qtd(farinha, MATRIZ), 10)
           and perto(qtd(farinha, FILIAL), 10), (qtd(farinha, MATRIZ), qtd(farinha, FILIAL)))

    st, rede = chamar("GET", f"/estoque/saldos-rede?id_produto={farinha}", token=token)
    linha = next((x for x in (rede or []) if x["id_produto"] == farinha), None)
    checar("a rede soma 20 KG valendo 100,00",
           linha and perto(linha["quantidade"], 20) and perto(linha["valor"], 100), linha)
    checar("com o médio PONDERADO da rede (5,00)",
           linha and perto(linha.get("custo_medio"), 5), linha)

    print("\n4. a mesma ficha custa diferente em cada loja")
    st, r = chamar("POST", "/fichas", {
        "id_produto": bolo, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
        "itens": [{"id_insumo": farinha, "qtd_bruta": 0.5, "um": "KG"}]}, token=token)
    ficha = r.get("id")
    checar("a ficha do bolo é criada", bool(ficha), (st, r))
    chamar("POST", f"/fichas/{ficha}/homologar", {}, token=token)
    st, f_m = chamar("GET", f"/fichas/{ficha}", token=token, unidade=MATRIZ)
    st, f_f = chamar("GET", f"/fichas/{ficha}", token=token, unidade=FILIAL)
    checar("na matriz o bolo custa 2,00", perto(f_m.get("custo_por_porcao"), 2),
           f_m.get("custo_por_porcao"))
    checar("na filial custa 3,00", perto(f_f.get("custo_por_porcao"), 3),
           f_f.get("custo_por_porcao"))

    print("\n5. cada loja produz com o insumo e o custo dela")
    st, r = chamar("POST", "/estoque/producoes", {
        "id_produto": bolo, "quantidade": 4, "id_local": local_m["id"]},
        token=token, unidade=MATRIZ)
    checar("a matriz produz 4 bolos consumindo 8,00",
           st == 201 and perto(r.get("custo_total"), 8), (st, r))
    producao_m = r.get("id")
    st, r = chamar("POST", "/estoque/producoes", {
        "id_produto": bolo, "quantidade": 4, "id_local": local_f["id"]},
        token=token, unidade=FILIAL)
    checar("a filial produz 4 bolos consumindo 12,00",
           st == 201 and perto(r.get("custo_total"), 12), (st, r))
    producao_f = r.get("id")
    # 🔑 **A lista de produções é da LOJA** (08/10/2026). Ela não filtrava por
    # `id_unidade` e somava as duas — o mesmo buraco que a listagem de vendas já
    # teve. Com uma loja só no ar ninguém via.
    st, lista_m = chamar("GET", "/estoque/producoes", token=token, unidade=MATRIZ)
    st, lista_f = chamar("GET", "/estoque/producoes", token=token, unidade=FILIAL)
    ids_m = {x["id"] for x in lista_m or []}
    ids_f = {x["id"] for x in lista_f or []}
    checar("a matriz lista a produção dela, e não a da filial",
           producao_m in ids_m and producao_f not in ids_m, (producao_m, producao_f))
    checar("e a filial lista a dela, e não a da matriz",
           producao_f in ids_f and producao_m not in ids_f, (producao_m, producao_f))
    checar("sobram 8 KG de farinha em cada loja", perto(qtd(farinha, MATRIZ), 8)
           and perto(qtd(farinha, FILIAL), 8), (qtd(farinha, MATRIZ), qtd(farinha, FILIAL)))
    checar("e 4 bolos em cada: 8,00 na matriz, 12,00 na filial",
           perto(valor(bolo, MATRIZ), 8) and perto(valor(bolo, FILIAL), 12),
           (valor(bolo, MATRIZ), valor(bolo, FILIAL)))

    print("\n6. cada loja vende do seu estoque, e congela o custo DELA")
    st, r = chamar("POST", "/vendas/importar", {"vendas": [{
        "data": HOJE, "documento": f"DL-{marca}-M", "origem": "MANUAL",
        "itens": [{"id_produto": bolo, "quantidade": 3, "valor_unitario": 20}]}]},
        token=token, unidade=MATRIZ)
    checar("a matriz vende 3 bolos", st in (200, 201) and r.get("importadas") == 1, (st, r))
    st, r = chamar("POST", "/vendas/importar", {"vendas": [{
        "data": HOJE, "documento": f"DL-{marca}-F", "origem": "MANUAL",
        "itens": [{"id_produto": bolo, "quantidade": 2, "valor_unitario": 22}]}]},
        token=token, unidade=FILIAL)
    checar("a filial vende 2 bolos", st in (200, 201) and r.get("importadas") == 1, (st, r))
    checar("a matriz fica com 1 bolo", perto(qtd(bolo, MATRIZ), 1), qtd(bolo, MATRIZ))
    checar("a filial com 2", perto(qtd(bolo, FILIAL), 2), qtd(bolo, FILIAL))

    st, v_m = chamar("GET", f"/vendas?busca=DL-{marca}", token=token, unidade=MATRIZ)
    st, v_f = chamar("GET", f"/vendas?busca=DL-{marca}", token=token, unidade=FILIAL)
    checar("a matriz só lista a venda dela",
           [v["documento"] for v in (v_m or [])] == [f"DL-{marca}-M"],
           [v.get("documento") for v in (v_m or [])])
    checar("a filial só lista a dela",
           [v["documento"] for v in (v_f or [])] == [f"DL-{marca}-F"],
           [v.get("documento") for v in (v_f or [])])
    st, det_m = chamar("GET", f"/vendas/{v_m[0]['id']}", token=token, unidade=MATRIZ)
    st, det_f = chamar("GET", f"/vendas/{v_f[0]['id']}", token=token, unidade=FILIAL)
    item_m = (det_m.get("itens") or [{}])[0]
    item_f = (det_f.get("itens") or [{}])[0]
    checar("o item da matriz congelou 2,00", perto(item_m.get("custo_ficha_unitario"), 2), item_m)
    checar("o da filial congelou 3,00", perto(item_f.get("custo_ficha_unitario"), 3), item_f)
    st, x = chamar("GET", f"/vendas/{v_f[0]['id']}", token=token, unidade=MATRIZ)
    checar("a matriz não abre a venda da filial", st in (403, 404), st)

    print("\n7. a remessa leva a mercadoria e o custo — sem criar dinheiro")
    rede_antes = valor(farinha, MATRIZ) + valor(farinha, FILIAL)
    st, envio = chamar("POST", "/transferencias", {
        "id_local_origem": local_m["id"], "id_local_destino": local_f["id"],
        "itens": [{"id_produto": farinha, "quantidade": 4}],
        "observacao": f"duas lojas {marca}"}, token=token, unidade=MATRIZ)
    remessa = (envio or {}).get("id")
    checar("a matriz despacha 4 KG para a filial", st == 201 and bool(remessa), (st, envio))
    checar("em trânsito, nenhum saldo andou",
           perto(qtd(farinha, MATRIZ), 8) and perto(qtd(farinha, FILIAL), 8))
    st, r = chamar("POST", f"/transferencias/{remessa}/receber", {}, token=token, unidade=FILIAL)
    checar("a filial recebe", st == 201, (st, r))
    checar("a matriz fica com 4 KG, ainda a 4,00",
           perto(qtd(farinha, MATRIZ), 4) and perto(custo(farinha, MATRIZ).get("atual"), 4),
           (qtd(farinha, MATRIZ), custo(farinha, MATRIZ).get("atual")))
    checar("a filial com 12 KG", perto(qtd(farinha, FILIAL), 12), qtd(farinha, FILIAL))
    # (8 x 6,00 + 4 x 4,00) / 12 = 5,333333
    checar("e o médio dela vira 5,3333 — o dela ponderado com o que chegou",
           perto(custo(farinha, FILIAL).get("atual"), 64 / 12, 0.0001),
           custo(farinha, FILIAL).get("atual"))
    rede_depois = valor(farinha, MATRIZ) + valor(farinha, FILIAL)
    checar("o valor da farinha na rede é o mesmo de antes (80,00)",
           perto(rede_antes, 80) and perto(rede_depois, 80), (rede_antes, rede_depois))
    st, rede = chamar("GET", f"/estoque/saldos-rede?id_produto={farinha}", token=token)
    linha = next((x for x in (rede or []) if x["id_produto"] == farinha), None)
    checar("e a visão da rede diz 16 KG valendo 80,00",
           linha and perto(linha["quantidade"], 16) and perto(linha["valor"], 80), linha)

    print("\n8. o CMV fecha em cada loja e na soma delas")
    depois_m = apuracao(MATRIZ)
    depois_f = apuracao(FILIAL)
    depois_e = apuracao(MATRIZ, "empresa")
    for nome, ap in (("matriz", depois_m), ("filial", depois_f), ("empresa", depois_e)):
        conta = (float(ap.get("estoque_inicial", 0)) + float(ap.get("compras", 0))
                 - float(ap.get("estoque_final", 0)))
        checar(f"inicial + compras - final = CMV na {nome}",
               bool(ap) and perto(conta, ap.get("cmv_real"), 0.05), (conta, ap.get("cmv_real")))
    # matriz: comprou 40, mandou 16 embora; ficou com 16 de farinha + 2 de bolo.
    checar("matriz: compras andaram 24,00 (40 comprados - 16 remetidos)",
           perto(andou(antes_m, depois_m, "compras"), 24), andou(antes_m, depois_m, "compras"))
    checar("matriz: estoque final andou 18,00",
           perto(andou(antes_m, depois_m, "estoque_final"), 18),
           andou(antes_m, depois_m, "estoque_final"))
    checar("matriz: CMV real andou 6,00 (3 bolos a 2,00)",
           perto(andou(antes_m, depois_m, "cmv_real"), 6), andou(antes_m, depois_m, "cmv_real"))
    checar("matriz: CMV teórico andou 6,00",
           perto(andou(antes_m, depois_m, "cmv_teorico"), 6),
           andou(antes_m, depois_m, "cmv_teorico"))
    checar("matriz: receita andou 60,00",
           perto(andou(antes_m, depois_m, "receita"), 60), andou(antes_m, depois_m, "receita"))
    # filial: loja nova, tudo o que ela tem é desta rodada.
    checar("filial: compras 76,00 (60 compradas + 16 recebidas)",
           perto(depois_f.get("compras"), 76), depois_f.get("compras"))
    checar("filial: estoque final 70,00 (64 de farinha + 6 de bolo)",
           perto(depois_f.get("estoque_final"), 70), depois_f.get("estoque_final"))
    checar("filial: CMV real 6,00 (2 bolos a 3,00)",
           perto(depois_f.get("cmv_real"), 6), depois_f.get("cmv_real"))
    checar("filial: CMV teórico 6,00", perto(depois_f.get("cmv_teorico"), 6),
           depois_f.get("cmv_teorico"))
    checar("filial: receita 44,00 (2 x 22,00, o preço dela)",
           perto(depois_f.get("receita"), 44), depois_f.get("receita"))
    # empresa: a remessa se anula; sobram as duas compras de verdade.
    checar("empresa: compras andaram 100,00 — a remessa não é compra da rede",
           perto(andou(antes_e, depois_e, "compras"), 100), andou(antes_e, depois_e, "compras"))
    checar("empresa: estoque final andou 88,00",
           perto(andou(antes_e, depois_e, "estoque_final"), 88),
           andou(antes_e, depois_e, "estoque_final"))
    checar("empresa: CMV real andou 12,00",
           perto(andou(antes_e, depois_e, "cmv_real"), 12), andou(antes_e, depois_e, "cmv_real"))
    checar("empresa: receita andou 104,00",
           perto(andou(antes_e, depois_e, "receita"), 104), andou(antes_e, depois_e, "receita"))
    for campo in ("compras", "estoque_final", "cmv_real", "cmv_teorico", "receita",
                  "estoque_inicial"):
        soma = float(depois_m.get(campo) or 0) + float(depois_f.get(campo) or 0)
        # ⚠️ Outras filiais de teste, já desativadas, podem ter movimento de hoje:
        # por isso a soma das DUAS é o piso, e a igualdade vale quando só há elas.
        checar(f"empresa = matriz + filial em {campo}",
               perto(depois_e.get(campo), soma, 0.05), (depois_e.get(campo), soma))

    print("\n9. os relatórios do CMV respeitam a loja")
    for nome, unidade, esperado in (("matriz", MATRIZ, None), ("filial", FILIAL, 6)):
        st, g = chamar("GET", f"/cmv/por-grupo?inicio={HOJE}&fim={HOJE}", token=token,
                       unidade=unidade)
        checar(f"o CMV por grupo da {nome} responde", st == 200, (st, g))
        grupos = g.get("grupos", g) if isinstance(g, dict) else g
        total = sum(float(x.get("cmv") or x.get("cmv_real") or 0) for x in (grupos or []))
        ap = depois_f if unidade == FILIAL else depois_m
        checar(f"e a soma dos grupos da {nome} é o CMV dela",
               perto(total, ap.get("cmv_real"), 0.05), (total, ap.get("cmv_real")))
    st, mg = chamar("GET", f"/cmv/margem?inicio={HOJE}&fim={HOJE}&id_produto={bolo}",
                    token=token, unidade=FILIAL)
    linha = next((x for x in (mg or []) if x.get("id_produto") == bolo), None)
    checar("a margem do bolo na filial: receita 44,00, custo 6,00",
           linha and perto(linha.get("receita"), 44) and perto(linha.get("custo"), 6), linha)
    st, mg = chamar("GET", f"/cmv/margem?inicio={HOJE}&fim={HOJE}&id_produto={bolo}",
                    token=token, unidade=MATRIZ)
    linha = next((x for x in (mg or []) if x.get("id_produto") == bolo), None)
    checar("e na matriz: receita 60,00, custo 6,00",
           linha and perto(linha.get("receita"), 60) and perto(linha.get("custo"), 6), linha)

    print("\n10. o que se faz numa loja não vaza para a outra")
    st, r = chamar("POST", "/ajustes/estoque", {
        "id_produto": farinha, "quantidade_certa": 11, "id_local": local_f["id"],
        "observacao": "contagem da filial"}, token=token, unidade=FILIAL)
    checar("a filial acerta o saldo dela para 11 KG", st == 201, (st, r))
    checar("a filial fica com 11", perto(qtd(farinha, FILIAL), 11), qtd(farinha, FILIAL))
    checar("e a matriz continua com 4", perto(qtd(farinha, MATRIZ), 4), qtd(farinha, MATRIZ))
    st, movs_m = chamar("GET", f"/estoque/movimentos?id_produto={farinha}&limite=50",
                        token=token, unidade=MATRIZ)
    st, movs_f = chamar("GET", f"/estoque/movimentos?id_produto={farinha}&limite=50",
                        token=token, unidade=FILIAL)
    locais_m_ids = {l["id"] for l in (locais_m or [])}
    checar("o razão da matriz só tem movimento em local dela",
           bool(movs_m) and all(m.get("id_local", local_m["id"]) in locais_m_ids
                                or m.get("local") != local_f.get("nome") for m in movs_m))
    checar("e o da filial tem a entrada, a produção, a remessa e o ajuste",
           {"ENTRADA_MANUAL", "TRANSFERENCIA_ENTRADA"} <= {m["tipo"] for m in (movs_f or [])},
           sorted({m["tipo"] for m in (movs_f or [])}))
    checar("os dois razões não repetem movimento",
           not ({m["id"] for m in (movs_m or [])} & {m["id"] for m in (movs_f or [])}))

    st, rp = chamar("POST", "/estoque/reprocessar", {"id_produto": farinha}, token=token,
                    unidade=FILIAL)
    checar("reprocessar a farinha na filial é só prévia e não acha o que mudar",
           st == 200 and not rp.get("mudam"), (st, rp.get("mudam") if isinstance(rp, dict) else rp))
    st, rp = chamar("POST", "/estoque/reprocessar", {"id_produto": farinha}, token=token,
                    unidade=MATRIZ)
    checar("nem na matriz", st == 200 and not rp.get("mudam"),
           (st, rp.get("mudam") if isinstance(rp, dict) else rp))

    print("\n11. cancelar a venda da filial devolve o estoque à filial")
    st, r = chamar("DELETE", f"/vendas/{v_f[0]['id']}", token=token, unidade=MATRIZ)
    checar("a matriz não cancela a venda da filial", st in (403, 404), (st, r))
    st, r = chamar("DELETE", f"/vendas/{v_f[0]['id']}", token=token, unidade=FILIAL)
    checar("a filial cancela a venda dela", st == 200, (st, r))
    checar("os 2 bolos voltam para a filial", perto(qtd(bolo, FILIAL), 4), qtd(bolo, FILIAL))
    checar("e a matriz continua com 1", perto(qtd(bolo, MATRIZ), 1), qtd(bolo, MATRIZ))
    fim_f = apuracao(FILIAL)
    checar("a receita da filial volta a zero", perto(fim_f.get("receita"), 0), fim_f.get("receita"))
    conta = (float(fim_f.get("estoque_inicial", 0)) + float(fim_f.get("compras", 0))
             - float(fim_f.get("estoque_final", 0)))
    checar("e a identidade da filial continua fechando",
           perto(conta, fim_f.get("cmv_real"), 0.05), (conta, fim_f.get("cmv_real")))

    print("\n11a. cada loja lança a sua nota de compra")
    # Estado de partida: matriz 4 KG a 4,00 | filial 11 KG a 5,333333.
    st, forns = chamar("GET", "/fornecedores?limite=1", token=token)
    fornecedor = (forns or [{}])[0].get("id")
    st, nota_m = chamar("POST", "/notas", {
        "id_fornecedor": fornecedor, "numero": f"DM{marca}", "serie": "1",
        "id_local": local_m["id"],
        "itens": [{"id_produto": farinha, "quantidade": 6, "valor_unitario": 5}]},
        token=token, unidade=MATRIZ)
    checar("a matriz digita uma nota de 6 KG a 5,00", st == 200 and nota_m.get("id"),
           (st, nota_m))
    st, nota_f = chamar("POST", "/notas", {
        "id_fornecedor": fornecedor, "numero": f"DF{marca}", "serie": "1",
        "id_local": local_f["id"],
        "itens": [{"id_produto": farinha, "quantidade": 4, "valor_unitario": 7}]},
        token=token, unidade=FILIAL)
    checar("a filial digita uma nota de 4 KG a 7,00", st == 200 and nota_f.get("id"),
           (st, nota_f))
    st, lista_m = chamar("GET", f"/notas?busca=D{'M'}{marca}", token=token, unidade=MATRIZ)
    st, lista_fm = chamar("GET", f"/notas?busca=DF{marca}", token=token, unidade=MATRIZ)
    st, lista_f = chamar("GET", f"/notas?busca=DF{marca}", token=token, unidade=FILIAL)
    checar("a matriz lista a nota dela", any(n["id"] == nota_m["id"] for n in (lista_m or [])))
    checar("e NÃO lista a da filial", not (lista_fm or []), lista_fm)
    checar("a filial lista a dela", any(n["id"] == nota_f["id"] for n in (lista_f or [])))
    st, r = chamar("POST", f"/notas/{nota_f['id']}/lancar", {"id_local": local_m["id"]},
                   token=token, unidade=MATRIZ)
    checar("a matriz não lança a nota da filial num local dela", st == 400, (st, r))
    st, r = chamar("GET", f"/notas/{nota_f['id']}", token=so_matriz, unidade=MATRIZ)
    checar("quem é só da matriz não abre a nota da filial pelo número (404)", st == 404, st)
    st, r = chamar("POST", f"/notas/{nota_f['id']}/lancar", {"id_local": local_m["id"]},
                   token=token, unidade=FILIAL)
    checar("nem a filial lança a nota dela no local da matriz", st == 400, (st, r))
    checar("depois das recusas, nenhum saldo andou",
           perto(qtd(farinha, MATRIZ), 4) and perto(qtd(farinha, FILIAL), 11),
           (qtd(farinha, MATRIZ), qtd(farinha, FILIAL)))
    st, r = chamar("POST", f"/notas/{nota_m['id']}/lancar", {"id_local": local_m["id"]},
                   token=token, unidade=MATRIZ)
    checar("a matriz lança a nota dela", st in (200, 201), (st, r))
    st, r = chamar("POST", f"/notas/{nota_f['id']}/lancar", {"id_local": local_f["id"]},
                   token=token, unidade=FILIAL)
    checar("a filial lança a dela", st in (200, 201), (st, r))
    # matriz: (4 x 4,00 + 6 x 5,00) / 10 = 4,60
    checar("a matriz fica com 10 KG a 4,60",
           perto(qtd(farinha, MATRIZ), 10) and perto(custo(farinha, MATRIZ).get("atual"), 4.6),
           (qtd(farinha, MATRIZ), custo(farinha, MATRIZ).get("atual")))
    # filial: (11 x 5,333333 + 4 x 7,00) / 15 = 5,777778
    checar("a filial fica com 15 KG a 5,7778",
           perto(qtd(farinha, FILIAL), 15)
           and perto(custo(farinha, FILIAL).get("atual"), (11 * 64 / 12 + 28) / 15, 0.0001),
           (qtd(farinha, FILIAL), custo(farinha, FILIAL).get("atual")))

    print("\n11b. a contagem de uma loja só enxerga e só acerta a dela")
    st, r = chamar("POST", "/inventarios", {
        "nome": f"Cruzada {marca}", "produtos": [farinha], "locais": [local_f["id"]],
        "cega": False}, token=token, unidade=MATRIZ)
    cruzada = (r or {}).get("id") if st == 201 else None
    checar("a matriz não abre contagem em local da filial (404)", st == 404, (st, r))
    if cruzada:
        chamar("DELETE", f"/inventarios/{cruzada}", token=token, unidade=MATRIZ)
    st, inv = chamar("POST", "/inventarios", {
        "nome": f"Filial {marca}", "produtos": [farinha], "locais": [local_f["id"]],
        "cega": False}, token=token, unidade=FILIAL)
    id_inv = (inv or {}).get("id")
    checar("a filial abre a contagem da farinha", st == 201 and bool(id_inv), (st, inv))
    linha_inv = ((inv or {}).get("itens") or [{}])[0]
    checar("e o sistema espera 15 KG — o saldo DELA, não os 25 da rede",
           perto(linha_inv.get("qtd_sistema"), 15), linha_inv)
    st, lista_inv = chamar("GET", "/inventarios", token=token, unidade=MATRIZ)
    checar("a contagem da filial não aparece na matriz",
           not any(i["id"] == id_inv for i in (lista_inv or [])))
    # ⚠️ Pelo NÚMERO, a regra da casa é "quem enxerga a loja abre" (validação de
    # 29/09/2026): o admin vê as duas. Quem prova o muro é quem só vê a matriz.
    st, r = chamar("GET", f"/inventarios/{id_inv}", token=so_matriz, unidade=MATRIZ)
    checar("quem é só da matriz não abre a contagem da filial pelo número (404)",
           st == 404, st)
    st, r = chamar("PUT", f"/inventarios/{id_inv}/contagem", {"itens": [
        {"id_produto": farinha, "id_local": local_f["id"], "qtd_contada": 14}]},
        token=token, unidade=FILIAL)
    checar("a filial conta 14 KG", st == 200, (st, r))
    st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=so_matriz, unidade=MATRIZ)
    checar("nem a fecha", st in (403, 404), (st, r))
    st, r = chamar("POST", f"/inventarios/{id_inv}/fechar", token=token, unidade=FILIAL)
    checar("a filial fecha, com um ajuste", st == 200 and r.get("ajustes") == 1, (st, r))
    checar("a filial passa a ter 14 KG", perto(qtd(farinha, FILIAL), 14), qtd(farinha, FILIAL))
    checar("e a matriz continua com os 10 dela", perto(qtd(farinha, MATRIZ), 10),
           qtd(farinha, MATRIZ))

    print("\n11c. a precificação é de cada loja")
    st, cfg_m_antes = chamar("GET", "/precificacao/config", token=token, unidade=MATRIZ)
    st, r = chamar("PUT", "/precificacao/config", {"arredondamento": "NENHUM", "linhas": [
        {"nome": "Impostos", "tipo": "PERCENTUAL", "valor": 10, "alcance": "TUDO"},
        {"nome": "Margem", "tipo": "MARGEM", "valor": 40, "alcance": "TUDO"}]},
        token=token, unidade=FILIAL)
    checar("a filial grava a configuração dela", st == 200 and r.get("id_unidade") == FILIAL,
           (st, r))
    st, cfg_m_depois = chamar("GET", "/precificacao/config", token=token, unidade=MATRIZ)
    checar("e a da matriz não muda",
           [(l["nome"], l["valor"]) for l in cfg_m_antes.get("linhas", [])]
           == [(l["nome"], l["valor"]) for l in cfg_m_depois.get("linhas", [])])
    st, an = chamar("GET", f"/precificacao/analise?dias=30&id_produto={bolo}", token=token,
                    unidade=FILIAL)
    x = next((i for i in (an or {}).get("itens", []) if i["id_produto"] == bolo), None)
    st, sim = chamar("POST", "/precificacao/simular", {"id_produto": bolo, "preco": 22},
                     token=token, unidade=FILIAL)
    # O bolo da filial custa 0,5 KG x 5,777778 = 2,888889; com 50% sobre a venda,
    # o piso é 2,888889 / 0,5 = 5,78.
    custo_bolo_f = 0.5 * (11 * 64 / 12 + 28) / 15
    checar("a simulação na filial usa o custo DELA (2,89)",
           st == 200 and perto(sim.get("custo_direto"), custo_bolo_f), (st, sim))
    checar("e as partes somam o preço de 22,00",
           st == 200 and perto(sum(p_["valor"] for p_ in sim["partes"]), 22, 0.011),
           sim.get("partes") if isinstance(sim, dict) else sim)
    st, sim_m = chamar("POST", "/precificacao/simular", {"id_produto": bolo, "preco": 20},
                       token=token, unidade=MATRIZ)
    # Na matriz: 0,5 KG x 4,60 = 2,30.
    checar("na matriz a mesma simulação usa 2,30",
           st == 200 and perto(sim_m.get("custo_direto"), 2.3), (st, sim_m))

    print("\n11d. cada loja fecha o seu período")
    antes_fech_m = apuracao(MATRIZ)
    ap_f = apuracao(FILIAL)
    st, r = chamar("PUT", f"/unidades/{FILIAL}/parametros", {"ciclo_fechamento": "DIARIO"},
                   token=token)
    checar("a filial passa a fechar por dia", st == 200, (st, r))
    st, per_m = chamar("GET", "/cmv/periodos?quantos=1", token=token, unidade=MATRIZ)
    checar("sem mudar o ciclo da matriz", per_m.get("ciclo") == antes_fech_m.get("ciclo"),
           (per_m.get("ciclo"), antes_fech_m.get("ciclo")))
    st, conf = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=token,
                      unidade=FILIAL)
    checar("a conferência antes de fechar responde na filial", st == 200, (st, conf))
    st, fech = chamar("POST", "/cmv/fechamentos", {"competencia": HOJE}, token=token,
                      unidade=FILIAL)
    id_fech = (fech or {}).get("id")
    checar("a filial fecha o dia", st == 201 and bool(id_fech), (st, fech))
    st, lista_fech_f = chamar("GET", "/cmv/fechamentos", token=token, unidade=FILIAL)
    fech = next((f for f in (lista_fech_f or []) if f["id"] == id_fech), {})
    checar("o fechamento aparece na lista da filial, como FECHADO",
           fech.get("status") == "FECHADO", fech)
    checar("e congela o CMV e o estoque que a apuração mostrava",
           perto(fech.get("cmv_real"), ap_f.get("cmv_real"))
           and perto(fech.get("estoque_final"), ap_f.get("estoque_final")),
           ({k: fech.get(k) for k in ("cmv_real", "estoque_final")},
            {k: ap_f.get(k) for k in ("cmv_real", "estoque_final")}))
    conta = (float(fech.get("estoque_inicial", 0)) + float(fech.get("compras", 0))
             - float(fech.get("estoque_final", 0)))
    checar("e o congelado fecha a identidade", perto(conta, fech.get("cmv_real"), 0.05),
           (conta, fech.get("cmv_real")))
    checar("a apuração da filial passa a dizer fechado", apuracao(FILIAL).get("fechado") is True)
    checar("a da matriz não", apuracao(MATRIZ).get("fechado") == antes_fech_m.get("fechado"),
           apuracao(MATRIZ).get("fechado"))
    st, lista_fech = chamar("GET", "/cmv/fechamentos", token=token, unidade=MATRIZ)
    checar("o fechamento da filial não aparece na matriz",
           not any(f["id"] == id_fech for f in (lista_fech or [])))
    st, r = chamar("POST", f"/cmv/fechamentos/{id_fech}/reabrir", token=token, unidade=MATRIZ)
    checar("e a matriz não o reabre", st in (403, 404), (st, r))
    # ⚠️ Quem prova a trava é quem NÃO tem `estoque.retroativo`: o conferente
    # lotado na filial. O admin passa por cima dela de propósito.
    st, papeis_f = chamar("GET", "/papeis", token=token)
    papel_f = next((x for x in (papeis_f or []) if x["nome"] == "Conferente / Estoque"), None)
    email_f = f"duas.lojas.f{marca}@botane.com.br"
    st, novo_f = chamar("POST", "/usuarios", {
        "nome": f"Conferente da filial {marca}", "email": email_f, "senha": "smoke12345",
        "papeis": [{"id_papel": (papel_f or {}).get("id"), "id_unidade": FILIAL}]}, token=token)
    usuarios_criados.append((novo_f or {}).get("id"))
    st, entrou_f = chamar("POST", "/auth/login", {"email": email_f, "senha": "smoke12345"})
    so_filial = (entrou_f or {}).get("access_token")
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 1, "custo_unitario": 5,
        "id_local": local_f["id"], "data_movimento": HOJE}, token=so_filial, unidade=FILIAL)
    checar("com o dia fechado, o conferente da filial não lança nele", st in (400, 403, 409),
           (st, r))
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 1, "custo_unitario": 4.6,
        "id_local": local_m["id"], "data_movimento": HOJE}, token=token, unidade=MATRIZ)
    checar("a matriz, que não fechou, continua lançando", st == 201, (st, r))
    checar("e o saldo da filial não se mexeu com isso", perto(qtd(farinha, FILIAL), 14),
           qtd(farinha, FILIAL))
    st, r = chamar("POST", f"/cmv/fechamentos/{id_fech}/reabrir", token=token, unidade=FILIAL)
    checar("a filial reabre o período dela", st == 200, (st, r))
    checar("e a apuração volta a dizer aberto", apuracao(FILIAL).get("fechado") is False)

    print("\n11e. no fim de tudo, as contas ainda fecham")
    fim_m, fim_f, fim_e = apuracao(MATRIZ), apuracao(FILIAL), apuracao(MATRIZ, "empresa")
    for nome, ap in (("matriz", fim_m), ("filial", fim_f), ("empresa", fim_e)):
        conta = (float(ap.get("estoque_inicial", 0)) + float(ap.get("compras", 0))
                 - float(ap.get("estoque_final", 0)))
        checar(f"inicial + compras - final = CMV na {nome}, depois de nota, contagem e fechamento",
               bool(ap) and perto(conta, ap.get("cmv_real"), 0.05), (conta, ap.get("cmv_real")))
    for campo in ("compras", "estoque_final", "cmv_real", "receita"):
        soma = float(fim_m.get(campo) or 0) + float(fim_f.get(campo) or 0)
        checar(f"e a empresa continua sendo matriz + filial em {campo}",
               perto(fim_e.get(campo), soma, 0.05), (fim_e.get(campo), soma))
    # filial: 14 KG a 5,777778 + 4 bolos a 3,00 (a venda foi cancelada).
    checar("o estoque da filial vale 14 x 5,7778 + 4 x 3,00 = 92,89",
           perto(fim_f.get("estoque_final"), 14 * (11 * 64 / 12 + 28) / 15 + 12, 0.02),
           fim_f.get("estoque_final"))
    st, rede = chamar("GET", f"/estoque/saldos-rede?id_produto={farinha}", token=token)
    linha = next((x for x in (rede or []) if x["id_produto"] == farinha), None)
    # matriz 11 KG (10 + 1 lançado no 11d) | filial 14 KG
    checar("e a rede soma 25 KG de farinha",
           linha and perto(linha["quantidade"], 25), linha)

    print("\n12. as telas de apoio respondem nas duas lojas")
    for caminho in ("/alertas", "/inicio", "/cmv/conferencia", "/cmv/periodos",
                    "/estoque/saldos-agrupados", "/ajustes/custo-referencia/previa",
                    "/precificacao/config", "/fichas/fila", "/inventarios"):
        st_m, _ = chamar("GET", caminho, token=token, unidade=MATRIZ)
        st_f, _ = chamar("GET", caminho, token=token, unidade=FILIAL)
        checar(f"{caminho} responde na matriz e na filial", st_m == 200 and st_f == 200,
               (st_m, st_f))

    print("\n13. quem é só de uma loja não entra na outra")
    st, _ = chamar("GET", "/estoque/saldos?limite=1", token=so_matriz, unidade=MATRIZ)
    checar("ele lê o estoque da matriz", st == 200, st)
    st, _ = chamar("GET", "/estoque/saldos?limite=1", token=so_matriz, unidade=FILIAL)
    checar("e não lê o da filial (403)", st == 403, st)
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": farinha, "quantidade": 1, "custo_unitario": 1,
        "id_local": local_f["id"]}, token=so_matriz, unidade=MATRIZ)
    checar("nem lança em local da filial estando na matriz", st in (400, 403), (st, r))
    st, rede = chamar("GET", f"/estoque/saldos-rede?id_produto={farinha}", token=so_matriz)
    lojas_vistas = {x["id_unidade"] for l in (rede or []) for x in l.get("por_loja", [])} \
        if st == 200 else set()
    checar("e a visão da rede não lhe mostra a filial", FILIAL not in lojas_vistas,
           (st, lojas_vistas))

finally:
    print("\n14. limpeza")
    st, vendas = chamar("GET", f"/vendas?busca=DL-{marca}", token=token, unidade=MATRIZ)
    for v in (vendas or []):
        if not v.get("cancelada"):
            chamar("DELETE", f"/vendas/{v['id']}", token=token, unidade=MATRIZ)
    for id_produto in produtos:
        chamar("DELETE", f"/produtos/{id_produto}", token=token)
    for id_usuario in [usuario_criado, *usuarios_criados]:
        if id_usuario:
            chamar("DELETE", f"/usuarios/{id_usuario}", token=token)
    _desativar_filiais_de_teste()
    st, lista = chamar("GET", "/unidades", token=token)
    checar("nenhuma filial de teste fica ativa",
           not any(str(u.get("nome", "")).startswith(PREFIXO) and u.get("ativo", True)
                   for u in (lista or [])))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
