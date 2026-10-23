"""CONTAS A RECEBER DO CONSUMO: em aberto, lote de cobrança, baixa — e cada um vê o seu.

🔑 **Pedido do dono (22/10/2026):** "tirar esta questão de períodos [...] o usuário
possa lançar os documentos para a data que for necessário. Ai ter uma espécie de
contas a receber [...] gerar um lote, e quando receber, fazer a baixa destes
documentos." Decidido com ele: um lote por pessoa (gerados de várias de uma vez),
baixa só do lote inteiro, permuta entre as formas, relatório baixado e mandado por fora.

⚠️ **As checagens que mais importam:**
- VAZAMENTO (seção 4): uma pessoa não vê o consumo de outra;
- COBRAR DUAS VEZES (seções 5 e 11): um documento está em um lote só, inclusive
  com dois cliques ao mesmo tempo;
- documento em lote não muda (seção 6): o lote é o que foi mandado à pessoa.

    python tests/smoke_receber.py     (API de pé na 9200)
"""

import atexit
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, cru=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            bruto = r.read()
            return r.status, bruto if cru else json.loads(bruto or b"null")
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


def perto(a, b, tol=0.005):
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns() // 100)[-6:]
criados: dict = {"produtos": [], "vendas": [], "lotes": [], "pessoas": []}


def _limpar():
    # ⚠️ Os LOTES saem antes das vendas: venda em lote não se cancela (seção 6).
    # Recebido estorna a baixa, depois cancela; cancelado não faz nada.
    for lid in criados["lotes"]:
        chamar("POST", f"/receber/lotes/{lid}/estornar-baixa", None, token=token)
        chamar("POST", f"/receber/lotes/{lid}/cancelar", None, token=token)
    criados["lotes"].clear()
    for v in criados["vendas"]:
        if v:
            chamar("DELETE", f"/vendas/{v}", token=token)
    criados["vendas"].clear()
    for p in criados["produtos"]:
        if p:
            chamar("DELETE", f"/produtos/{p}", token=token)
    criados["produtos"].clear()
    for f in criados["pessoas"]:
        chamar("DELETE", f"/fornecedores/{f}", token=token)
    criados["pessoas"].clear()


atexit.register(_limpar)


def _venda(id_pessoa, doc, qtd, valor, data):
    st, r = chamar("POST", "/vendas/importar", {"vendas": [{
        "data": data, "documento": doc, "origem": "MANUAL", "id_pessoa": id_pessoa,
        "itens": [{"id_produto": produto, "quantidade": qtd, "valor_unitario": valor}],
    }]}, token=token)
    st2, lista = chamar("GET", f"/vendas?busca={doc}", token=token)
    vid = (lista or [{}])[0].get("id")
    criados["vendas"].append(vid)
    return st, vid


def _gerar(corpo, tk=None):
    st, r = chamar("POST", "/receber/lotes", corpo, token=tk or token)
    for l in (r or {}).get("lotes") or []:
        criados["lotes"].append(l["id"])
    return st, r


def _aberto_de(id_pessoa, q=""):
    st, r = chamar("GET", f"/receber/em-aberto?id_pessoa={id_pessoa}{q}", token=token)
    return st, next((l for l in (r or {}).get("linhas") or [] if l["id_pessoa"] == id_pessoa),
                    None), r


print("1. o cenario: um prato de 40, duas pessoas e um login para uma delas")
st, prod = chamar("POST", "/produtos", {
    "codigo": f"REC-{marca}", "nome": f"PRATO RECEBER {marca}",
    "tipo": "PRODUZIDO", "um_estoque": "UN", "controla_estoque": False,
    "status": "ATIVO", "preco_venda": 40,
}, token=token)
produto = (prod or {}).get("id")
criados["produtos"].append(produto)
st, eu = chamar("POST", "/fornecedores", {
    "nome": f"EU {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 10}, token=token)
st, outro = chamar("POST", "/fornecedores", {
    "nome": f"OUTRO {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 50}, token=token)
EU, OUTRO = eu.get("id"), outro.get("id")
criados["pessoas"] += [EU, OUTRO]
st, papeis = chamar("GET", "/papeis", token=token)
papel = (papeis or [{}])[0].get("id")
st, usuario = chamar("POST", "/usuarios", {
    "nome": f"EU {marca}", "email": f"eu{marca}@teste.com", "senha": "Senha!12345",
    "id_pessoa": EU, "papeis": [{"id_papel": papel}],
}, token=token)
checar("o cenario nasce", bool(produto and EU and OUTRO and usuario.get("id")),
       (produto, eu, outro, usuario))


print("\n2. o consumo se lanca em QUALQUER data, sem periodo aberto")
# 🔑 A trava do ciclo saiu: o documento entra na data em que aconteceu.
# 2 x 40 = 80 cheio, 10% off = 72 · 1 x 40 = 36 · 1 x 40 = 36
st1, EU1 = _venda(EU, f"EU1{marca}", 2, 40, "2026-09-01")
st2, EU2 = _venda(EU, f"EU2{marca}", 1, 40, "2026-09-10")
st3, EU3 = _venda(EU, f"EU3{marca}", 1, 40, "2026-09-20")
# 5 x 40 = 200 cheio, 50% off = 100 -- e este NAO pode aparecer para o outro
st4, OU1 = _venda(OUTRO, f"OU1{marca}", 5, 40, "2026-09-05")
checar("as vendas com pessoa entram sem ciclo nenhum",
       all(s == 201 for s in (st1, st2, st3, st4)) and all((EU1, EU2, EU3, OU1)),
       (st1, st2, st3, st4))


print("\n3. o que esta EM ABERTO, com e sem recorte de datas")
st, meu, tudo = _aberto_de(EU)
checar("a pessoa aparece em aberto com os tres documentos", meu and meu["cupons"] == 3, meu)
checar("com o valor ja descontado: 160 cheio, 144 a cobrar",
       meu and perto(meu["total_cheio"], 160) and perto(meu["total"], 144), meu)
checar("e com desde quando", meu and meu["desde"] == "2026-09-01", meu)
st, ate15, _ = _aberto_de(EU, "&ate=2026-09-15")
checar("ate 15/09: so os dois primeiros (108)",
       ate15 and ate15["cupons"] == 2 and perto(ate15["total"], 108), ate15)
st, faixa, _ = _aberto_de(EU, "&de=2026-09-05&ate=2026-09-15")
checar("de 05 a 15/09: so o do dia 10 (36)",
       faixa and faixa["cupons"] == 1 and perto(faixa["total"], 36), faixa)
st, r = chamar("GET", "/receber/em-aberto?de=2026-09-15&ate=2026-09-01", token=token)
checar("datas invertidas sao recusadas", st == 400, (st, r))
st, docs = chamar("GET", f"/receber/em-aberto/{EU}?ate=2026-09-15", token=token)
checar("os documentos em aberto de UMA pessoa vem com os itens",
       st == 200 and len(docs.get("documentos") or []) == 2
       and all(d.get("itens_do_documento") for d in docs["documentos"]), (st, docs))


print("\n4. o usuario ve o PROPRIO consumo — e NAO o de mais ninguem")
st, entrou = chamar("POST", "/auth/login",
                    {"email": f"eu{marca}@teste.com", "senha": "Senha!12345"})
token_eu = entrou.get("access_token")
checar("o usuario entra", bool(token_eu), entrou)
st, meu_c = chamar("GET", "/consumo/meu", token=token_eu)
checar("e a tela dele responde, ligada a uma pessoa",
       st == 200 and meu_c.get("vinculado") is True, (st, meu_c))
checar("com os 144 em aberto e os 16 economizados",
       perto(meu_c.get("total"), 144) and perto(meu_c.get("desconto"), 16),
       (meu_c.get("total"), meu_c.get("desconto")))
documentos = {c.get("documento") for c in meu_c.get("cupons", [])}
# 🔑 A checagem que mais importa: falhar nesta daria a divida de um colega na
# tela de quem nao devia ver.
checar("o cupom da outra pessoa NAO aparece", f"OU1{marca}" not in documentos, documentos)
st, forjado = chamar("GET", f"/consumo/meu?id_pessoa={OUTRO}", token=token_eu)
checar("e mandar o id de outra pessoa na URL nao muda nada",
       perto(forjado.get("total"), 144), forjado.get("total"))
st, sem = chamar("GET", "/consumo/meu", token=token)
checar("login sem pessoa ligada e DITO, nao mostrado como zero",
       "vinculado" in sem, list(sem.keys())[:6])


print("\n5. o LOTE de uma pessoa, ate uma data")
st, g = _gerar({"ate": "2026-09-15", "ids_pessoa": [EU]})
checar("o lote nasce", st == 201 and len(g.get("lotes") or []) == 1, (st, g))
LOTE = (g.get("lotes") or [{}])[0].get("id")
checar("com os dois documentos ate 15/09 e 108 a cobrar",
       g.get("lotes") and g["lotes"][0]["cupons"] == 2 and perto(g["total"], 108), g)
# ⚠️ O mesmo recorte de novo nao acha nada: o documento ja esta em um lote.
st, g2 = _gerar({"ate": "2026-09-15", "ids_pessoa": [EU]})
checar("gerar de novo o mesmo recorte NAO cobra duas vezes (409)", st == 409, (st, g2))
st, det = chamar("GET", f"/receber/lotes/{LOTE}", token=token)
checar("o lote mostra a pessoa, o valor e a situacao em cobranca",
       st == 200 and det["lote"]["id_pessoa"] == EU and det["lote"]["status"] == "ABERTO"
       and perto(det["lote"]["total"], 108) and perto(det["lote"]["total_cheio"], 120),
       (st, det.get("lote")))
checar("e os dois documentos, com os itens",
       {d["documento"] for d in det.get("documentos") or []} == {f"EU1{marca}", f"EU2{marca}"}
       and all(d.get("itens_do_documento") for d in det["documentos"]), det.get("documentos"))
st, meu, tudo = _aberto_de(EU)
checar("em aberto sobra so o do dia 20 (36), e 108 em cobranca",
       meu and perto(meu["total"], 36) and perto(meu["em_cobranca"], 108), meu)
st, meu_c = chamar("GET", "/consumo/meu", token=token_eu)
checar("e o usuario ve o lote em cobranca na tela dele",
       perto(meu_c.get("total"), 36)
       and any(l["id"] == LOTE and perto(l["total"], 108) for l in meu_c.get("em_cobranca", [])),
       (meu_c.get("total"), meu_c.get("em_cobranca")))
st, rel = chamar("GET", f"/vendas/por-pessoa?situacao=cobranca&id_pessoa={EU}", token=token)
checar("o relatorio 'em cobranca' traz o lote (108)",
       st == 200 and perto(rel.get("total"), 108), (st, rel.get("total")))
st, rel = chamar("GET", f"/vendas/por-pessoa?id_lote={LOTE}&detalhe=documento", token=token)
checar("e o relatorio de UM lote, por documento, diz o lote de cada linha",
       st == 200 and perto(rel.get("total"), 108)
       and all(l.get("id_lote") == LOTE for l in rel.get("linhas") or []), (st, rel))


print("\n6. documento em lote NAO muda: nem item novo, nem cancelamento")
st, ac = chamar("POST", f"/vendas/{EU1}/itens", {"itens": [
    {"id_produto": produto, "quantidade": 1, "valor_unitario": 40}]}, token=token)
checar("acrescentar item e recusado, dizendo o lote",
       st == 409 and f"nº {LOTE}" in str(ac.get("detail")), (st, ac))
st, ca = chamar("DELETE", f"/vendas/{EU1}", token=token)
checar("cancelar tambem", st == 409 and "lote" in str(ca.get("detail")), (st, ca))
st, dv = chamar("GET", f"/vendas/{EU1}", token=token)
checar("e o detalhe da venda diz o lote e por que nao acrescenta",
       dv.get("id_consumo_lote") == LOTE and dv.get("lote_status") == "ABERTO"
       and dv.get("pode_acrescentar") is False, (dv.get("id_consumo_lote"), dv.get("lote_status")))


print("\n7. tirar um documento do lote — o que nao foi pago fica para o proximo")
st, t = chamar("DELETE", f"/receber/lotes/{LOTE}/documentos/{EU2}", token=token)
checar("o documento sai e o lote se refaz em 72",
       st == 200 and t.get("cancelado") is False and perto(t.get("total"), 72), (st, t))
st, meu, _ = _aberto_de(EU)
checar("e ele volta para em aberto (36 + 36 = 72)",
       meu and perto(meu["total"], 72) and perto(meu["em_cobranca"], 72), meu)
st, t2 = chamar("DELETE", f"/receber/lotes/{LOTE}/documentos/{EU2}", token=token)
checar("tirar o que nao esta no lote responde 404", st == 404, (st, t2))


print("\n8. a BAIXA do lote inteiro — inclusive por permuta")
st, b = chamar("POST", f"/receber/lotes/{LOTE}/receber",
               {"recebido_em": "2026-09-30", "forma_pagamento": "BOLETO"}, token=token)
checar("forma de pagamento que nao existe e recusada (422)", st == 422, (st, b))
st, b = chamar("POST", f"/receber/lotes/{LOTE}/receber",
               {"recebido_em": "2026-09-30", "forma_pagamento": "PERMUTA",
                "observacao": "trocado por servico"}, token=token)
checar("a baixa por permuta responde", st == 200 and perto(b.get("total"), 72), (st, b))
st, det = chamar("GET", f"/receber/lotes/{LOTE}", token=token)
checar("o lote fica RECEBIDO, com a data e a forma",
       det["lote"]["status"] == "RECEBIDO" and det["lote"]["recebido_em"] == "2026-09-30"
       and det["lote"]["forma_pagamento"] == "PERMUTA" and det["lote"]["baixou"],
       det["lote"])
st, b2 = chamar("POST", f"/receber/lotes/{LOTE}/receber",
                {"recebido_em": "2026-09-30", "forma_pagamento": "PIX"}, token=token)
checar("dar baixa duas vezes e recusado (409)", st == 409, (st, b2))
st, c = chamar("POST", f"/receber/lotes/{LOTE}/cancelar", None, token=token)
checar("lote recebido nao se cancela sem estornar a baixa",
       st == 409 and "estorne" in str(c.get("detail")).lower(), (st, c))
st, t = chamar("DELETE", f"/receber/lotes/{LOTE}/documentos/{EU1}", token=token)
checar("nem perde documento", st == 409, (st, t))
st, meu_c = chamar("GET", "/consumo/meu", token=token_eu)
checar("o usuario ve o lote pago no historico dele, com os 72",
       any(h["id"] == LOTE and perto(h["total"], 72) and h["forma_pagamento"] == "PERMUTA"
           for h in meu_c.get("historico", [])) and not meu_c.get("em_cobranca"),
       (meu_c.get("historico"), meu_c.get("em_cobranca")))
st, rel = chamar("GET", f"/vendas/por-pessoa?situacao=recebido&id_pessoa={EU}", token=token)
checar("e o relatorio 'recebido' traz os 72", perto(rel.get("total"), 72), rel.get("total"))
st, dv = chamar("GET", f"/vendas/{EU1}", token=token)
checar("a venda de lote recebido diz para estornar a baixa",
       "Estorne a baixa" in str(dv.get("por_que_nao_acrescenta")),
       dv.get("por_que_nao_acrescenta"))


print("\n9. estornar a baixa e cancelar o lote — tudo volta para em aberto")
st, e = chamar("POST", f"/receber/lotes/{LOTE}/estornar-baixa", None, token=token)
checar("a baixa se estorna", st == 200, (st, e))
st, det = chamar("GET", f"/receber/lotes/{LOTE}", token=token)
checar("e o lote volta a estar em cobranca, sem data nem forma",
       det["lote"]["status"] == "ABERTO" and det["lote"]["recebido_em"] is None
       and det["lote"]["forma_pagamento"] is None, det["lote"])
st, c = chamar("POST", f"/receber/lotes/{LOTE}/cancelar", None, token=token)
checar("o lote em cobranca se cancela", st == 200 and EU1 in (c.get("vendas") or []), (st, c))
st, meu, _ = _aberto_de(EU)
checar("e a divida volta inteira em aberto: 144, nada em cobranca",
       meu and perto(meu["total"], 144) and perto(meu["em_cobranca"], 0), meu)
st, lista = chamar("GET", f"/receber/lotes?status=CANCELADO&id_pessoa={EU}", token=token)
checar("o lote cancelado fica no historico, nao some",
       any(l["id"] == LOTE for l in lista.get("lotes") or []), lista)


print("\n10. lotes de VARIAS pessoas de uma vez — um por pessoa")
st, g = _gerar({"ate": "2026-09-30", "ids_pessoa": [EU, OUTRO], "ids_venda": [EU3]})
checar("escolher documentos a dedo com duas pessoas e recusado (400)", st == 400, (st, g))
st, g = _gerar({"ate": "2026-09-01", "de": "2026-09-30", "ids_pessoa": [EU]})
checar("e datas invertidas tambem (400)", st == 400, (st, g))
st, g = _gerar({"ate": "2026-09-30", "ids_pessoa": [EU, OUTRO]})
por_pessoa = {l["id_pessoa"]: l for l in (g or {}).get("lotes") or []}
checar("dois lotes, um para cada pessoa",
       st == 201 and set(por_pessoa) == {EU, OUTRO}, (st, g))
checar("cada um com o seu valor: 144 e 100",
       por_pessoa and perto(por_pessoa[EU]["total"], 144)
       and perto(por_pessoa[OUTRO]["total"], 100), por_pessoa)
for l in por_pessoa.values():
    chamar("POST", f"/receber/lotes/{l['id']}/cancelar", None, token=token)
st, g = _gerar({"ate": "2026-09-30", "ids_pessoa": [EU], "ids_venda": [EU3]})
checar("com uma pessoa, escolher o documento a dedo leva SO ele (36)",
       st == 201 and g["lotes"][0]["cupons"] == 1 and perto(g["total"], 36), (st, g))
for l in g.get("lotes") or []:
    chamar("POST", f"/receber/lotes/{l['id']}/cancelar", None, token=token)


print("\n11. dois cliques ao MESMO tempo nao cobram o mesmo documento duas vezes")
# 🔑 Quem garante e o UPDATE (`id_consumo_lote IS NULL`), nao uma checagem antes.
respostas: list = []


def _clique():
    respostas.append(_gerar({"ate": "2026-09-30", "ids_pessoa": [EU]}))


fios = [threading.Thread(target=_clique) for _ in range(3)]
for f in fios:
    f.start()
for f in fios:
    f.join()
criados_agora = [l for st_, r_ in respostas if st_ == 201 for l in r_["lotes"]]
checar("um so lote nasce dos tres cliques",
       len(criados_agora) == 1 and sum(1 for st_, _ in respostas if st_ == 409) == 2,
       [s for s, _ in respostas])
checar("e com os tres documentos uma vez so (144)",
       criados_agora and criados_agora[0]["cupons"] == 3
       and perto(criados_agora[0]["total"], 144), criados_agora)
LOTE2 = criados_agora[0]["id"] if criados_agora else None


print("\n12. o documento do lote, para mandar a pessoa")
st, pdf = chamar("GET", f"/exportar/lote-consumo/{LOTE2}.pdf", token=token, cru=True)
checar("o PDF do lote sai", st == 200 and isinstance(pdf, bytes) and pdf[:5] == b"%PDF-", st)
st, csv = chamar("GET", f"/exportar/lote-consumo/{LOTE2}.csv?detalhe=documento",
                 token=token, cru=True)
texto = csv.decode("utf-8-sig", "replace") if isinstance(csv, bytes) else ""
checar("e a planilha nomeia o lote e a pessoa no cabecalho",
       f"Lote nº {LOTE2}" in texto.splitlines()[0] and f"EU {marca}" in texto.splitlines()[0],
       texto.splitlines()[:1])
checar("com os tres documentos e o total do lote",
       all(f"EU{n}{marca}" in texto for n in (1, 2, 3)) and "144" in texto, texto[:400])
st, nao = chamar("GET", "/exportar/lote-consumo/999999999.pdf", token=token)
checar("lote que nao existe responde 404", st == 404, (st, nao))


print("\n13. quem nao gere o consumo nao gera lote nem da baixa")
tk_cozinha = garantir_cozinha(chamar, token)
st, r = chamar("POST", "/receber/lotes", {"ate": "2026-09-30", "ids_pessoa": [EU]},
               token=tk_cozinha)
checar("gerar lote sem a chave: 403", st == 403, (st, r))
st, r = chamar("POST", f"/receber/lotes/{LOTE2}/receber",
               {"recebido_em": "2026-09-30", "forma_pagamento": "PIX"}, token=tk_cozinha)
checar("dar baixa sem a chave: 403", st == 403, (st, r))


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
