"""Ordem de compra: pedir, comprar (inteiro ou em parte), voltar e cancelar.

O que este arquivo cobra:

1. pedir do cadastro e fora dele; a validação recusa o que não identifica o item
2. somar em pedido aberto, e só no mesmo produto e unidade
3. comprar inteiro; comprar parte divide a linha; comprar a mais guarda o pedido
4. a segunda pessoa a marcar recebe 409 dizendo quem comprou
5. voltar à lista junta a parte com a origem
6. cancelar tira da lista e não se cancela duas vezes
7. permissões: quem só pede não marca, e não mexe no pedido dos outros
8. cada loja vê a sua lista
9. **comprar não mexe no saldo**
10. fusão leva o pedido; troca de unidade converte o aberto
11. o relatório sai
12. etapa 2: produzido fora da busca e da lista; sugestões do mínimo (sem saldo também, até o
    máximo, em embalagem arredondada, descontando o que já está na lista); lote soma no aberto
13. para quando (159): padrão, ordem por urgência, somar fica com a maior, corrigir, a parte
    comprada leva junto, relatório

    python tests/smoke_ordens_compra.py       (API de pé na 9200)

⚠️ Cria filial e desativa no `atexit`: duas lojas ativas mudam a barra superior.
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


def igual(a, b):
    return a is not None and abs(float(a) - float(b)) < 0.0001


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]


def _desativar_filiais():
    try:
        _s, lista = chamar("GET", "/unidades?incluir_inativas=true", token=token)
        # ⚠️ As linhas da rodada saem da lista: senão a tela do dono acumula item de teste.
        for u in (lista or []):
            if not u.get("ativo"):
                continue
            _s, comprados = chamar("GET", f"/ordens-compra?status=COMPRADO&busca={marca}&limite=200",
                                   token=token, unidade=u["id"])
            if comprados:
                chamar("POST", "/ordens-compra/voltar", {"ids": [x["id"] for x in comprados]},
                       token=token, unidade=u["id"])
            _s, abertos = chamar("GET", f"/ordens-compra?status=A_COMPRAR&busca={marca}&limite=200",
                                 token=token, unidade=u["id"])
            for x in (abertos or []):
                chamar("POST", f"/ordens-compra/{x['id']}/cancelar", {}, token=token, unidade=u["id"])
        for u in (lista or []):
            if u.get("ativo") and str(u.get("nome", "")).startswith("Filial ordem"):
                chamar("PUT", f"/unidades/{u['id']}", {"ativo": False}, token=token)
        # ⚠️ Os produtos com mínimo apareceriam para sempre nas sugestões da base local.
        for id_produto in com_minimo:
            chamar("DELETE", f"/produtos/{id_produto}", token=token)
    except Exception:
        pass


com_minimo: list[int] = []
atexit.register(_desativar_filiais)


def api(metodo, caminho, corpo=None, tk=None, unidade=None):
    return chamar(metodo, caminho, corpo, token=tk or token, unidade=unidade or matriz_id)


def novo_produto(sufixo):
    s, p = chamar("POST", "/produtos", {
        "codigo": f"OC{marca}{sufixo}", "nome": f"Insumo ordem {marca} {sufixo}", "tipo": "INSUMO",
        "um_estoque": "UN", "um_compra": "UN", "fator_compra": 1, "status": "ATIVO",
    }, token=token, unidade=matriz_id)
    checar(f"produto {sufixo} nasce", s == 201, (s, p))
    return p["id"]


def linha(id_item, status="A_COMPRAR", unidade=None):
    _s, l = api("GET", f"/ordens-compra?status={status}&limite=200", unidade=unidade)
    return next((x for x in (l or []) if x["id"] == id_item), None)


print("0. preparo")
local = garantir_local(chamar, token)
matriz_id = None
_s, unidades = chamar("GET", "/unidades", token=token)
matriz_id = next(u["id"] for u in unidades if u.get("matriz"))
id_local = local if isinstance(local, int) else local.get("id")
produto = novo_produto("A")
outro = novo_produto("B")

print("1. pedir")
s, a = api("POST", "/ordens-compra", {"id_produto": produto, "quantidade": 10, "um": "UN",
                                      "observacao": "a de sempre"})
checar("pede do cadastro", s == 201 and a.get("id"), (s, a))
l = linha(a["id"])
checar("aparece em A comprar com a observação",
       l and igual(l["quantidade"], 10) and l["observacao"] == "a de sempre", l)
s, livre = api("POST", "/ordens-compra", {"descricao_livre": f"Guardanapo {marca}",
                                          "quantidade": 3, "um": "UN"})
checar("pede fora do cadastro", s == 201, (s, livre))
checar("e a linha diz que é fora do cadastro", linha(livre["id"])["fora_do_cadastro"] is True)
s, _ = api("POST", "/ordens-compra", {"quantidade": 1, "um": "UN"})
checar("sem produto nem texto: 422", s == 422, s)
s, _ = api("POST", "/ordens-compra", {"id_produto": produto, "descricao_livre": "x",
                                      "quantidade": 1, "um": "UN"})
checar("com os dois: 422", s == 422, s)
s, _ = api("POST", "/ordens-compra", {"id_produto": produto, "quantidade": 0, "um": "UN"})
checar("quantidade zero: 422", s == 422, s)
s, _ = api("POST", "/ordens-compra", {"id_produto": produto, "quantidade": 1, "um": "KG"})
checar("unidade em que o produto não se pede: 400", s == 400, s)
s, op = api("GET", f"/ordens-compra/produto/{produto}")
checar("as opções mostram o pedido aberto",
       s == 200 and any(x["id"] == a["id"] for x in op["abertos"]), op)

print("2. somar")
s, r = api("POST", "/ordens-compra", {"id_produto": produto, "quantidade": 2, "um": "UN",
                                      "observacao": "urgente", "somar_em": a["id"]})
checar("soma no aberto", s == 201 and r["somado"] and r["id"] == a["id"], (s, r))
l = linha(a["id"])
checar("10 + 2 = 12, com as duas observações",
       igual(l["quantidade"], 12) and "urgente" in l["observacao"] and "sempre" in l["observacao"], l)
s, _ = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN",
                                      "somar_em": a["id"]})
checar("não soma em outro produto", s == 400, s)

print("3. comprar")
s, parte = api("POST", "/ordens-compra/comprar", {"itens": [{"id": a["id"], "quantidade": 7}]})
checar("compra parcial", s == 201 and parte["parciais"] == 1, (s, parte))
id_parte = parte["ids"][0]
checar("os 5 que faltam continuam na lista", igual(linha(a["id"])["quantidade"], 5))
c = linha(id_parte, "COMPRADO")
checar("os 7 entram em Comprados, ligados à origem",
       c and igual(c["quantidade"], 7) and c["id_item_origem"] == a["id"], c)
s, r = api("POST", "/ordens-compra/voltar", {"ids": [id_parte]})
checar("voltar a parte", s == 201, (s, r))
checar("junta na origem: 12 de novo", igual(linha(a["id"])["quantidade"], 12))
checar("e a parte sai de Comprados", linha(id_parte, "COMPRADO") is None)

s, r = api("POST", "/ordens-compra/comprar", {"itens": [{"id": a["id"], "quantidade": 15}]})
checar("comprar a mais", s == 201 and r["ids"] == [a["id"]], (s, r))
c = linha(a["id"], "COMPRADO")
checar("fica 15, guardando os 12 pedidos",
       igual(c["quantidade"], 15) and igual(c["quantidade_pedida"], 12), c)
s, dupla = api("POST", "/ordens-compra/comprar", {"itens": [{"id": a["id"]}]})
checar("segunda marcação: 409 dizendo quem", s == 409 and "já foi comprado" in dupla["detail"], (s, dupla))
s, _ = api("POST", "/ordens-compra/voltar", {"ids": [a["id"]]})
l = linha(a["id"])
checar("voltar restaura os 12", s == 201 and l and igual(l["quantidade"], 12), l)
s, _ = api("POST", "/ordens-compra/voltar", {"ids": [a["id"]]})
checar("voltar o que não está em Comprados: 409", s == 409, s)

s, r = api("POST", "/ordens-compra/comprar", {
    "itens": [{"id": a["id"], "quantidade": 1}, {"id": 999999999}]})
checar("lote com item inexistente: 404", s == 404, s)
checar("e nada foi marcado (tudo ou nada)", igual(linha(a["id"])["quantidade"], 12))

print("4. corrigir e cancelar")
s, _ = api("PUT", f"/ordens-compra/{livre['id']}", {"quantidade": 4, "um": "UN", "observacao": "azul"})
l = linha(livre["id"])
checar("corrige", s == 200 and igual(l["quantidade"], 4) and l["observacao"] == "azul", l)
s, _ = api("POST", f"/ordens-compra/{livre['id']}/cancelar", {})
checar("cancela e sai da lista", s == 201 and linha(livre["id"]) is None, s)
s, _ = api("POST", f"/ordens-compra/{livre['id']}/cancelar", {})
checar("não cancela duas vezes", s == 409, s)

print("5. permissões")
s, papeis = api("GET", "/papeis")
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
email = f"ordem{marca}@teste.botane"
s, u = api("POST", "/usuarios", {"nome": f"Pede {marca}", "email": email, "senha": "Teste#12345",
                                 "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz_id}]})
checar("usuário da cozinha nasce", s in (200, 201), (s, u))
s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
tk = (lg or {}).get("access_token")
checar("e entra", bool(tk), (s, lg))
if tk:
    s, meu = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN"}, tk=tk)
    checar("a cozinha pede", s == 201, (s, meu))
    s, _ = api("POST", "/ordens-compra/comprar", {"itens": [{"id": meu["id"]}]}, tk=tk)
    checar("a cozinha não marca comprado", s == 403, s)
    s, _ = api("PUT", f"/ordens-compra/{a['id']}", {"quantidade": 1, "um": "UN"}, tk=tk)
    checar("não corrige pedido dos outros", s == 403, s)
    s, _ = api("POST", f"/ordens-compra/{a['id']}/cancelar", {}, tk=tk)
    checar("não cancela pedido dos outros", s == 403, s)
    s, _ = api("PUT", f"/ordens-compra/{meu['id']}", {"quantidade": 2, "um": "UN"}, tk=tk)
    checar("corrige o próprio", s == 200, s)
    s, _ = api("POST", f"/ordens-compra/{meu['id']}/cancelar", {}, tk=tk)
    checar("cancela o próprio", s == 201, s)

print("6. lojas")
s, filial = chamar("POST", "/unidades", {"nome": f"Filial ordem {marca}", "apelido": f"O{marca}"},
                   token=token)
id_filial = filial["id"]
checar("a filial não vê a lista da matriz", linha(a["id"], unidade=id_filial) is None)
s, _ = api("POST", "/ordens-compra/comprar", {"itens": [{"id": a["id"]}]}, unidade=id_filial)
checar("e não marca item da matriz", s == 404, s)
s, f = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN"},
           unidade=id_filial)
checar("a filial tem a própria linha", s == 201 and linha(f["id"], unidade=id_filial) is not None, (s, f))
checar("que a matriz não vê", linha(f["id"]) is None)

print("7. não mexe no estoque")
s, _ = api("POST", "/estoque/entradas", {"id_produto": produto, "quantidade": 5, "custo_unitario": 2,
                                        "id_local": id_local})
checar("entrada de preparo", s in (200, 201), s)
def saldo():
    _s, d = api("GET", f"/estoque/saldos?busca=OC{marca}A&limite=50")
    return sum(float(x["quantidade"]) for x in (d or []) if x.get("id_produto") == produto)
antes = saldo()
s, _ = api("POST", "/ordens-compra/comprar", {"itens": [{"id": a["id"]}]})
checar("comprar", s == 201, s)
checar("o saldo não andou", igual(saldo(), antes) and igual(antes, 5), (antes, saldo()))
s, _ = api("POST", "/ordens-compra/voltar", {"ids": [a["id"]]})

print("8. fusão e troca de unidade")
p1 = novo_produto("C")
p2 = novo_produto("D")
s, x = api("POST", "/ordens-compra", {"id_produto": p2, "quantidade": 3, "um": "UN"})
s, r = api("POST", "/produtos/duplicados/fundir", {"id_principal": p1, "ids_que_saem": [p2]})
checar("funde", s == 200, (s, r))
l = linha(x["id"])
checar("o pedido passa para o que fica", l and l["id_produto"] == p1, l)

p3 = novo_produto("E")
s, y = api("POST", "/ordens-compra", {"id_produto": p3, "quantidade": 2, "um": "UN"})
s, det = api("GET", f"/produtos/{p3}")
s, r = api("PUT", f"/produtos/{p3}", {**{k: det.get(k) for k in ("codigo", "nome", "tipo")},
                                      "um_estoque": "KG", "fator_troca_unidade": 5})
if s == 200:
    l = linha(y["id"])
    checar("a troca de unidade converte o pedido aberto",
           l and l["um"] == "KG" and igual(l["quantidade"], 10), l)
else:
    print("  (troca de unidade pediu outro formato:", s, r, ")")
    falhas.append("troca de unidade não exercitada")

print("9. relatório")
s, rel = api("GET", "/exportar/ordens-compra/dados")
checar("o relatório responde", s == 200, (s, rel))
texto = json.dumps(rel, ensure_ascii=False)
checar("e traz o item aberto", f"INSUMO ORDEM {marca} A" in texto.upper(), texto[:200])

print("10. só o que se compra (etapa 2)")
s, prod = chamar("POST", "/produtos", {
    "codigo": f"OC{marca}P", "nome": f"Molho ordem {marca}", "tipo": "PRODUZIDO",
    "um_estoque": "UN", "um_compra": "UN", "fator_compra": 1, "status": "ATIVO",
    "estoque_minimo": 5}, token=token, unidade=matriz_id)
checar("produzido de teste nasce", s == 201, (s, prod))
com_minimo.append(prod["id"])
s, r = api("POST", "/ordens-compra", {"id_produto": prod["id"], "quantidade": 1, "um": "UN"})
checar("produzido não entra na ordem: 409 apontando a agenda",
       s == 409 and "agenda de produção" in r["detail"], (s, r))
s, _ = api("GET", f"/ordens-compra/produto/{prod['id']}")
checar("nem as opções dele abrem", s == 409, s)
s, l = api("GET", f"/produtos?busca=OC{marca}&comprado=true&limite=50")
codigos = {x["codigo"] for x in (l or [])}
checar("a busca de comprados deixa o produzido de fora",
       f"OC{marca}P" not in codigos and f"OC{marca}A" in codigos, codigos)
s, l = api("GET", f"/produtos?busca=OC{marca}P&comprado=false&limite=50")
checar("e o avesso traz só ele", [x["codigo"] for x in (l or [])] == [f"OC{marca}P"], l)


def novo_com_minimo(sufixo, minimo, maximo=None):
    s, p = chamar("POST", "/produtos", {
        "codigo": f"OC{marca}{sufixo}", "nome": f"Insumo ordem {marca} {sufixo}", "tipo": "INSUMO",
        "um_estoque": "UN", "um_compra": "UN", "fator_compra": 1, "status": "ATIVO",
        "estoque_minimo": minimo, "estoque_maximo": maximo}, token=token, unidade=matriz_id)
    checar(f"produto {sufixo} nasce com mínimo", s == 201, (s, p))
    com_minimo.append(p["id"])
    return p["id"]


def sugestao(id_produto):
    _s, l = api("GET", "/ordens-compra/sugestoes")
    return next((x for x in (l or []) if x["id_produto"] == id_produto), None)


caixa = novo_com_minimo("F", 30, 60)
s, _ = api("PUT", f"/produtos/{caixa}/unidades", {"itens": [{"um": "CX", "fator": 12, "padrao": True}]})
checar("a caixa de 12 é a unidade padrão", s == 200, s)
cheio = novo_com_minimo("G", 10)
api("POST", "/estoque/entradas", {"id_produto": cheio, "quantidade": 20, "custo_unitario": 1,
                                  "id_local": id_local})
pouco = novo_com_minimo("H", 8)
api("POST", "/estoque/entradas", {"id_produto": pouco, "quantidade": 3, "custo_unitario": 1,
                                  "id_local": id_local})

sg = sugestao(caixa)
checar("sem nenhuma linha de saldo, aparece (o painel não mostrava)", sg is not None, sg)
checar("repõe até o máximo, em caixas arredondadas para cima: 60/12 = 5 CX",
       sg and sg["um"] == "CX" and igual(sg["sugerida"], 5) and sg["ate_o_maximo"], sg)
checar("acima do mínimo não aparece", sugestao(cheio) is None)
checar("produzido abaixo do mínimo não aparece", sugestao(prod["id"]) is None)
sg = sugestao(pouco)
checar("sem máximo, repõe até o mínimo: 8 - 3 = 5 UN",
       sg and sg["um"] == "UN" and igual(sg["sugerida"], 5) and not sg["ate_o_maximo"], sg)

s, ab = api("POST", "/ordens-compra", {"id_produto": caixa, "quantidade": 2, "um": "CX"})
sg = sugestao(caixa)
checar("o que já está na lista é descontado: 5 - 2 = 3 CX",
       sg and igual(sg["sugerida"], 3) and sg["na_lista"], sg)

s, r = api("POST", "/ordens-compra/lote", {"itens": [
    {"id_produto": caixa, "quantidade": 3, "um": "CX"},
    {"id_produto": pouco, "quantidade": 5, "um": "UN"}]})
checar("põe as sugestões de uma vez", s == 201 and len(r["ids"]) == 2, (s, r))
l = linha(ab["id"])
checar("a caixa soma na linha aberta: 2 + 3 = 5 CX, sem linha nova",
       l and igual(l["quantidade"], 5) and r["ids"][0] == ab["id"], l)
sg = sugestao(caixa)
checar("coberta, a sugestão vem com zero (já na lista)", sg and igual(sg["sugerida"], 0), sg)

s, r = api("POST", "/ordens-compra/lote", {"itens": [
    {"id_produto": cheio, "quantidade": 1, "um": "UN"},
    {"id_produto": prod["id"], "quantidade": 1, "um": "UN"}]})
checar("lote com produzido: 409", s == 409, (s, r))
_s, abertos = api("GET", f"/ordens-compra?status=A_COMPRAR&busca=OC{marca}G&limite=50")
checar("e nada do lote entrou (tudo ou nada)", not abertos, abertos)

print("11. para quando (migração 159)")
s, sem = api("POST", "/ordens-compra", {"descricao_livre": f"Pano {marca}", "quantidade": 1, "um": "UN"})
checar("sem dizer, o pedido é para esta semana", linha(sem["id"])["urgencia"] == "SEMANA", linha(sem["id"]))
s, hoje = api("POST", "/ordens-compra", {"descricao_livre": f"Gelo {marca}", "quantidade": 2, "um": "UN",
                                         "urgencia": "HOJE"})
s, espera = api("POST", "/ordens-compra", {"descricao_livre": f"Vela {marca}", "quantidade": 1, "um": "UN",
                                           "urgencia": "PODE_ESPERAR"})
s, _ = api("POST", "/ordens-compra", {"descricao_livre": "x", "quantidade": 1, "um": "UN",
                                      "urgencia": "ONTEM"})
checar("urgência que não existe: 422", s == 422, s)
_s, l = api("GET", f"/ordens-compra?status=A_COMPRAR&busca={marca}&limite=200")
ordem = [x["id"] for x in l if x["id"] in (sem["id"], hoje["id"], espera["id"])]
checar("A comprar vem com o urgente primeiro e o que pode esperar por último",
       ordem == [hoje["id"], sem["id"], espera["id"]], ordem)
checar("e a linha traz o setor de quem pediu (ou nulo)", "setor_pedido" in l[0], l[0])
s, r = api("POST", "/ordens-compra", {"descricao_livre": f"Pano {marca}", "quantidade": 1, "um": "UN"})
s, p_hoje = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN",
                                           "urgencia": "PODE_ESPERAR"})
s, r = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN",
                                      "urgencia": "HOJE", "somar_em": p_hoje["id"]})
checar("somar fica com o mais urgente dos dois", linha(p_hoje["id"])["urgencia"] == "HOJE", linha(p_hoje["id"]))
s, r = api("POST", "/ordens-compra", {"id_produto": outro, "quantidade": 1, "um": "UN",
                                      "urgencia": "PODE_ESPERAR", "somar_em": p_hoje["id"]})
checar("e não volta a ser menos urgente", linha(p_hoje["id"])["urgencia"] == "HOJE")
s, _ = api("PUT", f"/ordens-compra/{espera['id']}", {"quantidade": 1, "um": "UN", "urgencia": "HOJE"})
checar("corrigir muda a urgência", s == 200 and linha(espera["id"])["urgencia"] == "HOJE")
s, _ = api("PUT", f"/ordens-compra/{espera['id']}", {"quantidade": 3, "um": "UN"})
checar("corrigir sem urgência mantém a que estava", linha(espera["id"])["urgencia"] == "HOJE")
s, parte = api("POST", "/ordens-compra/comprar", {"itens": [{"id": hoje["id"], "quantidade": 1}]})
c = linha(parte["ids"][0], "COMPRADO")
checar("a parte comprada leva a urgência", c and c["urgencia"] == "HOJE", c)
s, rel = api("GET", "/exportar/ordens-compra/dados")
texto = json.dumps(rel, ensure_ascii=False)
checar("o relatório tem Para quando", "Para quando" in texto and "Urgente — hoje" in texto, texto[:200])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
