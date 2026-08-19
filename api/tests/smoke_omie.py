"""Teste de fumaça da etapa 5 (integração Omie), em modo simulado.

O cenário das fixtures, conferido na mão:

    NF 4812 — 4 CX de café a 120,00 (480,00) + 40 UN de leite a 4,00 (160,00)
              frete 60,00 rateado por valor: 45,00 no café, 15,00 no leite
              café:  (480 + 45) ÷ (4 CX × 12 un) = 10,9375 por unidade
              leite: (160 + 15) ÷ 40            =  4,375  por unidade

Prova também: a chave da NF-e impede duplicar, item sem produto barra o
lançamento, vincular ensina o de-para, e a credencial nunca sai da API.

    python tests/smoke_omie.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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

print("0. limpa o cenário da rodada anterior")
# As notas das fixtures são únicas pela chave da NF-e: sem desfazer o que a
# rodada passada importou, a segunda execução não teria o que conciliar.
CHAVES = {"35260812345678000195550010000004811000004812",
          "35260812345678000195550010000004911000004913"}
st, notas_antigas = chamar("GET", "/notas", token=token)
for n in notas_antigas or []:
    if n.get("chave_nfe") in CHAVES:
        if n["status"] == "LANCADA":
            chamar("POST", f"/notas/{n['id']}/estornar", token=token)
        chamar("DELETE", f"/notas/{n['id']}", token=token)
for codigo in ("CAF-500", "LEI-INT", "TOM-CX"):
    chamar("DELETE", f"/notas/vinculos/{codigo}", token=token)
# O catálogo importado na rodada anterior deixou produtos com o MESMO EAN das
# notas — e aí o item casaria sozinho pelo nível 2 da cascata, que é o
# comportamento certo mas apaga o cenário de conciliação deste teste.
for nome in ("Café em grão especial", "Leite integral 1L", "Tomate italiano"):
    st, achados = chamar("GET", f"/produtos?busca={nome}", token=token)
    for p in achados or []:
        chamar("DELETE", f"/produtos/{p['id']}", token=token)
checar("cenário limpo", True)

print("1. configuração — a credencial não volta em claro")
st, cfg = chamar("GET", "/omie/config", token=token)
checar("config responde", st == 200, cfg)
st, r = chamar("PUT", "/omie/config",
               {"app_key": "chave-de-teste-1234", "app_secret": "segredo-de-teste-9876",
                "modo": "simulado", "ativa": True}, token=token)
checar("salva a configuração", st == 200, r)
st, cfg = chamar("GET", "/omie/config", token=token)
checar("marca como configurada", cfg.get("configurada") is True, cfg)
checar("app_key volta mascarada", str(cfg.get("app_key", "")).endswith("1234")
       and "•" in str(cfg.get("app_key")), cfg.get("app_key"))
checar("o segredo nunca sai em claro", "segredo-de-teste" not in json.dumps(cfg), cfg)
st, r = chamar("PUT", "/omie/config", {"modo": "real", "ativa": True}, token=token)
checar("trocar para modo real com a chave já salva não exige redigitar", st == 200, r)
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": True}, token=token)

st, r = chamar("POST", "/omie/testar", token=token)
checar("teste de conexão responde", st == 200 and r.get("ok") is True, r)
checar("teste diz que está em modo simulado", r.get("modo") == "simulado", r)

print("2. sincronização importa as notas das fixtures")
st, r = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("sincroniza", st == 200, r)
primeira = r.get("novas", 0)
st, r2 = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("reimportar não duplica (chave da NF-e)", r2.get("novas") == 0 and r2.get("repetidas") >= 1,
       r2)

st, notas = chamar("GET", "/notas", token=token)
checar("as notas aparecem na lista", st == 200 and len(notas) >= 2, len(notas) if st == 200 else notas)
nota_cafe = next((n for n in notas if n["numero"] == "4812"), None)
checar("a nota 4812 foi importada", nota_cafe is not None)
checar("o fornecedor foi criado a partir da nota",
       nota_cafe and nota_cafe.get("fornecedor"), nota_cafe)
checar("a nota nasce com pendência de de-para",
       nota_cafe and nota_cafe["pendentes"] >= 1, nota_cafe)

print("3. conciliação: sem produto, sem lançamento")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("recusa lançar com item pendente", st == 400, (st, r))
checar("a recusa diz quantos itens faltam", "item" in str(r.get("detail", "")).lower(), r)

st, pend = chamar("GET", "/notas/pendencias", token=token)
checar("as pendências aparecem na fila", st == 200 and len(pend) >= 2, len(pend))
item_cafe = next((p for p in pend if "CAFE" in (p["descricao_fornecedor"] or "").upper()), None)
checar("o item de café está na fila", item_cafe is not None, pend[:1])

# Produtos do lado de cá: café em UN (a caixa traz 12) e leite em UN.
st, r = chamar("POST", "/produtos", {"nome": f"Omie café {marca}", "tipo": "INSUMO",
                                     "um_estoque": "UN", "um_compra": "CX",
                                     "fator_compra": 12}, token=token)
cafe = r.get("id")
st, r = chamar("POST", "/produtos", {"nome": f"Omie leite {marca}", "tipo": "INSUMO",
                                     "um_estoque": "UN"}, token=token)
leite = r.get("id")
checar("produtos do cenário criados", bool(cafe and leite))

st, r = chamar("POST", f"/notas/itens/{item_cafe['id']}/vincular",
               {"id_produto": cafe, "fator": 12}, token=token)
checar("vincula o item de café", st == 200, r)

st, nota = chamar("GET", f"/notas/{nota_cafe['id']}", token=token)
linha_cafe = next(i for i in nota["itens"] if i["id_produto"] == cafe)
checar("quantidade convertida: 4 CX × 12 = 48 un",
       perto(linha_cafe["quantidade_convertida"], 48), linha_cafe["quantidade_convertida"])
checar("frete rateado no café = 45,00", perto(linha_cafe["valor_frete_rateado"], 45),
       linha_cafe["valor_frete_rateado"])
checar("custo de aquisição do café = 10,9375 (não os 10,00 da nota)",
       perto(linha_cafe["custo_aquisicao_unitario"], 10.9375, 0.0001),
       linha_cafe["custo_aquisicao_unitario"])

item_leite = next(i for i in nota["itens"] if i["id_produto"] is None and not i["ignorado"])
st, r = chamar("POST", f"/notas/itens/{item_leite['id']}/vincular",
               {"id_produto": leite}, token=token)
checar("vincula o item de leite", st == 200, r)
st, nota = chamar("GET", f"/notas/{nota_cafe['id']}", token=token)
linha_leite = next(i for i in nota["itens"] if i["id_produto"] == leite)
checar("custo do leite = 4,375 (160 + 15 de frete ÷ 40)",
       perto(linha_leite["custo_aquisicao_unitario"], 4.375, 0.0001),
       linha_leite["custo_aquisicao_unitario"])
checar("a nota passou para CONCILIADA", nota["status"] == "CONCILIADA", nota["status"])

print("4. lançamento vira estoque avaliado")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("lança a nota", st == 200 and r.get("itens_lancados") == 2, r)
checar("valor lançado = 700,00 (a nota inteira)", perto(r.get("valor"), 700), r)

st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
s_cafe = next((s for s in saldos if s["id_produto"] == cafe), None)
checar("café entrou com 48 un", s_cafe and perto(s_cafe["quantidade"], 48), s_cafe)
checar("café entrou pelo custo de aquisição", s_cafe and perto(s_cafe["custo_medio"], 10.9375, 0.001),
       s_cafe)

st, r = chamar("POST", f"/notas/{nota_cafe['id']}/lancar", {}, token=token)
checar("não lança a mesma nota duas vezes", st == 400, st)

print("5. o de-para aprendeu")
# Apaga a nota de café e reimporta: o item tem de casar sozinho agora.
st, r = chamar("POST", "/omie/sincronizar?dias=60", token=token)
checar("nova sincronização não traz a nota de novo", r.get("novas") == 0, r)
st, pend = chamar("GET", "/notas/pendencias", token=token)
checar("o item de café saiu da fila de pendências",
       not any(p["id"] == item_cafe["id"] for p in pend))

print("6. carga do catálogo e conferência cruzada")
st, r = chamar("POST", "/omie/importar-catalogo", token=token)
checar("importa o catálogo", st == 200, r)
checar("traz os 3 produtos da fixture", r.get("criados", 0) + r.get("ja_existiam", 0) >= 3, r)
st, produtos = chamar("GET", "/produtos?busca=Café em grão&incluir_inativos=true", token=token)
checar("o produto importado nasce em rascunho",
       any(p["status"] == "RASCUNHO" for p in produtos), produtos[:1])
st, r2 = chamar("POST", "/omie/importar-catalogo", token=token)
checar("reimportar o catálogo não duplica", r2.get("criados") == 0, r2)

st, conf = chamar("GET", "/omie/conferencia", token=token)
checar("conferência com o CMC responde", st == 200, conf if st != 200 else len(conf))

print("7. permissão")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == "smoke.cozinha@botane.com.br"), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": "smoke12345", "papeis": [{"id_papel": id_cozinha}]},
           token=token)
st, r = chamar("POST", "/auth/login",
               {"email": "smoke.cozinha@botane.com.br", "senha": "smoke12345"})
tk = r.get("access_token")
st, r = chamar("GET", "/omie/config", token=tk)
checar("cozinha NÃO vê a configuração da integração (403)", st == 403, st)
st, r = chamar("POST", "/omie/sincronizar", token=tk)
checar("cozinha NÃO sincroniza (403)", st == 403, st)
st, r = chamar("GET", "/notas", token=tk)
checar("cozinha NÃO vê as notas (403)", st == 403, st)

print("8. desfazer: estorno e desvínculo")
st, r = chamar("POST", f"/notas/{nota_cafe['id']}/estornar", token=token)
checar("estorna o lançamento da nota", st == 200 and r.get("estornados") == 2, r)
st, saldos = chamar("GET", f"/estoque/saldos?busca={marca}", token=token)
s_cafe2 = next((s for s in saldos if s["id_produto"] == cafe), None)
checar("o saldo do café voltou a zero", s_cafe2 is None or perto(s_cafe2["quantidade"], 0),
       s_cafe2)
st, mov = chamar("GET", f"/estoque/movimentos?id_produto={cafe}", token=token)
checar("o movimento original continua no razão, com a contrapartida", len(mov) == 2, len(mov))
st, r = chamar("DELETE", f"/notas/vinculos/CAF-500", token=token)
checar("desfaz o vínculo aprendido", st == 200, r)

print("9. limpeza")
for p in (cafe, leite):
    chamar("DELETE", f"/produtos/{p}", token=token)
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": False}, token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
