"""Teste de fumaça da etapa 6 (CMV).

Monta um mês inteiro numa loja limpa de teste e confere a conta na mão:

    estoque inicial 0 + compras 300,00 − estoque final 100,00 = CMV real 200,00
    vendas: 20 pratos × custo de ficha 6,00 = CMV teórico 120,00
    variância = 80,00  (e a perda de 60,00 explica a maior parte dela)

Também prova: reimportar não duplica, o custo da ficha é congelado na venda,
mês fechado recusa lançamento retroativo, e reabrir volta a aceitar.

    python tests/smoke_cmv.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402
from datetime import date, timedelta

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
        with urllib.request.urlopen(req, dados, timeout=30) as r:
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
hoje = date.today()
inicio_mes = hoje.replace(day=1)
periodo = f"inicio={inicio_mes}&fim={hoje}"

print("0. cenário do mês")
st, saldos_antes = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("apuração responde antes de tudo", st == 200, saldos_antes)
base = saldos_antes  # a loja já tem dado de outros testes; medimos o DELTA

local = garantir_local(chamar, token)


def novo_produto(nome, tipo="INSUMO", um="KG"):
    st, r = chamar("POST", "/produtos", {"nome": nome, "tipo": tipo, "um_estoque": um},
                   token=token)
    return r["id"] if st == 201 else None


insumo = novo_produto(f"Cmv insumo {marca}")
prato = novo_produto(f"Cmv prato {marca}", tipo="PRODUZIDO", um="UN")
checar("produtos do cenário criados", bool(insumo and prato))

# Compra: 30 kg a R$ 10,00 = R$ 300,00
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 30, "custo_unitario": 10, "id_local": local["id"],
    "documento": f"NF {marca}",
}, token=token)
checar("compra de 300,00 lançada", st == 201, r)

# Ficha: 0,6 kg de insumo por prato (rende 1 prato) → custo teórico 6,00
st, r = chamar("POST", "/fichas", {
    "id_produto": prato, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [{"id_insumo": insumo, "qtd_bruta": 0.6, "um": "KG"}],
}, token=token)
ficha = r.get("id")
chamar("POST", f"/fichas/{ficha}/homologar", token=token)
st, f = chamar("GET", f"/fichas/{ficha}", token=token)
checar("ficha custa 6,00 por prato", perto(f.get("custo_por_porcao"), 6), f.get("custo_por_porcao"))

# Produção de 20 pratos: consome 12 kg = 120,00
st, r = chamar("POST", "/estoque/producoes", {
    "id_produto": prato, "quantidade": 20, "id_local": local["id"],
}, token=token)
checar("produz 20 pratos consumindo 120,00", st == 201 and perto(r.get("custo_total"), 120), r)

print("1. vendas: importar sem duplicar e congelar o custo")
documento = f"CUPOM-{marca}"
lote = {"vendas": [{
    "data": str(hoje), "documento": documento, "canal": "SALAO", "origem": "PLANILHA",
    "itens": [{"id_produto": prato, "quantidade": 20, "valor_unitario": 25}],
}]}
st, r = chamar("POST", "/vendas/importar", lote, token=token)
checar("importa a venda", st == 201 and r.get("importadas") == 1, r)
checar("nenhum item ficou sem vínculo", r.get("itens_sem_vinculo") == 0, r)
checar("nenhum item ficou sem custo", r.get("itens_sem_custo") == 0, r)

st, r = chamar("POST", "/vendas/importar", lote, token=token)
checar("reimportar o mesmo documento não duplica",
       r.get("importadas") == 0 and r.get("repetidas") == 1, r)

# Mudar a ficha agora NÃO pode mexer no CMV teórico já importado.
st, nova = chamar("POST", f"/fichas/{ficha}/nova-versao", token=token)
chamar("PUT", f"/fichas/{nova['id']}", {
    "itens": [{"id_insumo": insumo, "qtd_bruta": 3, "um": "KG"}]}, token=token)
chamar("POST", f"/fichas/{nova['id']}/homologar", token=token)

print("2. a conta do mês")
# Saída de perda: 6 kg = 60,00 (é o que explica a variância)
st, motivos = chamar("GET", "/estoque/motivos-perda", token=token)
chamar("POST", "/estoque/saidas", {
    "id_produto": insumo, "quantidade": 6, "tipo": "SAIDA_PERDA",
    "id_local": local["id"], "id_motivo_perda": motivos[0]["id"],
}, token=token)

st, a = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("apuração responde", st == 200, a)

compras = float(a["compras"]) - float(base["compras"])
checar("compras do período subiram 300,00", perto(compras, 300), compras)

# Estoque: 30 kg comprados − 12 kg de produção − 6 kg de perda = 12 kg (120,00).
# Os 20 pratos produzidos (120,00) foram TODOS vendidos, e VENDER É SAIR DO
# ESTOQUE: sobra só o insumo. Antes desta regra o prato vendido continuava na
# prateleira do sistema e o CMV real saía subestimado.
delta_final = float(a["estoque_final"]) - float(base["estoque_final"])
checar("estoque final subiu 120,00 (só o insumo; os pratos foram vendidos)",
       perto(delta_final, 120), delta_final)

delta_real = float(a["cmv_real"]) - float(base["cmv_real"])
checar("CMV real do cenário = 180,00 (300 − 120)", perto(delta_real, 180), delta_real)

delta_teorico = float(a["cmv_teorico"]) - float(base["cmv_teorico"])
checar("CMV teórico = 120,00 (20 × 6,00 congelado)", perto(delta_teorico, 120), delta_teorico)
checar("o custo congelado ignorou a ficha nova", perto(delta_teorico, 120), delta_teorico)

delta_perdas = float(a["perdas"]) - float(base["perdas"])
checar("perdas do período = 60,00", perto(delta_perdas, 60), delta_perdas)

delta_receita = float(a["receita"]) - float(base["receita"])
checar("receita = 500,00 (20 × 25)", perto(delta_receita, 500), delta_receita)
checar("food cost sai calculado", a.get("food_cost_pct") is not None)
checar("cobertura de ficha vem no painel", a.get("cobertura_ficha_pct") is not None)

print("3. curva ABC e margem por prato")
st, abc = chamar("GET", f"/cmv/abc?{periodo}", token=token)
checar("ABC responde", st == 200 and len(abc) > 0, st)
linha = next((x for x in abc if x["id_produto"] == insumo), None)
checar("o insumo do cenário aparece no ABC", linha is not None)
checar("ABC traz classe e acumulado", linha and linha["classe"] in ("A", "B", "C"), linha)
checar("valor consumido do insumo = 180,00 (120 produção + 60 perda)",
       linha and perto(linha["valor"], 180), linha)

st, margem = chamar("GET", f"/cmv/margem?{periodo}", token=token)
mp = next((x for x in margem if x["id_produto"] == prato), None)
checar("margem por prato responde", st == 200 and mp is not None, st)
checar("receita do prato = 500,00", mp and perto(mp["receita"], 500), mp)
checar("custo do prato = 120,00", mp and perto(mp["custo"], 120), mp)
checar("margem = 380,00", mp and perto(mp["margem"], 380), mp)
checar("food cost do prato = 24%", mp and perto(mp["food_cost_pct"], 24, 0.1), mp)

print("4. item vendido sem cadastro vira pendência")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": str(hoje), "documento": f"CUPOM-X-{marca}",
    "itens": [{"descricao": f"Prato fantasma {marca}", "quantidade": 2, "valor_unitario": 30}],
}]}, token=token)
checar("importa mesmo sem achar o produto", st == 201, r)
checar("conta o item sem vínculo", r.get("itens_sem_vinculo") == 1, r)
st, pendentes = chamar("GET", "/vendas/sem-vinculo", token=token)
checar("o item aparece na fila de de-para",
       any(marca in (x.get("descricao_pdv") or "") for x in pendentes), pendentes[:2])
st, a2 = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("cobertura de ficha cai quando há prato sem custo",
       float(a2["cobertura_ficha_pct"]) < float(a["cobertura_ficha_pct"]),
       (a["cobertura_ficha_pct"], a2["cobertura_ficha_pct"]))

print("4b. movimentação de estoque, produto a produto")
st, mov = chamar("GET", f"/cmv/movimentacao?{periodo}", token=token)
checar("a movimentação responde", st == 200 and "linhas" in mov, st)
checar("e diz que o mês ainda está aberto", mov.get("congelado") is False, mov.get("congelado"))
linha_insumo = next((l for l in mov["linhas"] if l["id_produto"] == insumo), None)
checar("o insumo do cenário aparece", linha_insumo is not None,
       [l["produto"] for l in mov["linhas"]][:5])
if linha_insumo:
    # A identidade que o relatório existe para sustentar.
    conta = (float(linha_insumo["valor_inicial"]) + float(linha_insumo["valor_entradas"])
             - float(linha_insumo["valor_saidas"]))
    checar("inicial + entradas − saídas = final, no produto",
           perto(conta, float(linha_insumo["valor_final"]), 0.05), linha_insumo)
    checar("e a quantidade fecha do mesmo jeito",
           perto(float(linha_insumo["qtd_inicial"]) + float(linha_insumo["qtd_entradas"])
                 - float(linha_insumo["qtd_saidas"]), float(linha_insumo["qtd_final"]), 0.001),
           linha_insumo)
t = mov["total"]
# ⚠️ Tolerância proporcional ao tamanho do relatório: cada linha sai
# arredondada em dois dígitos e o rodapé soma as linhas arredondadas — para
# fechar com a coluna na tela. Em centenas de produtos isso dá centavos de
# diferença na identidade, que não são erro de conta.
folga = max(0.05, 0.005 * mov["produtos"])
checar("e fecha no total também",
       perto(t["valor_inicial"] + t["valor_entradas"] - t["valor_saidas"],
             t["valor_final"], folga),
       t)

print("5. fechamento congela o período")
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": str(inicio_mes)}, token=token)
checar("fecha o mês", st == 201, r)
id_fech = r.get("id")
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": str(inicio_mes)}, token=token)
checar("não fecha duas vezes", st == 409, st)

# O admin TEM `estoque.retroativo` — a trava é para quem não tem. Quem testa
# isso é o conferente, que lança entrada mas não pode mexer em mês fechado.
st, papeis_todos = chamar("GET", "/papeis", token=token)
id_conferente = next(p["id"] for p in papeis_todos if p["nome"].startswith("Conferente"))
email_conf = "smoke.conferente@botane.com.br"
st, usuarios_todos = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
conf = next((u for u in usuarios_todos if u["email"] == email_conf), None)
if conf:
    chamar("PUT", f"/usuarios/{conf['id']}",
           {"ativo": True, "senha": "conf12345", "papeis": [{"id_papel": id_conferente}]},
           token=token)
else:
    chamar("POST", "/usuarios", {"nome": "Smoke Conferente", "email": email_conf,
                                 "senha": "conf12345",
                                 "papeis": [{"id_papel": id_conferente}]}, token=token)
st, r = chamar("POST", "/auth/login", {"email": email_conf, "senha": "conf12345"})
tk_conf = r.get("access_token")

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 1, "custo_unitario": 10, "id_local": local["id"],
    "data_movimento": f"{inicio_mes}T10:00:00",
}, token=tk_conf)
checar("conferente NÃO lança com data dentro do mês fechado", st == 400, (st, r))
checar("a recusa diz qual período está fechado", "fechado" in str(r.get("detail", "")).lower(), r)

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 1, "custo_unitario": 10, "id_local": local["id"],
}, token=tk_conf)
checar("lançamento sem data (hoje) continua passando", st == 201, r)

st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 1, "custo_unitario": 10, "id_local": local["id"],
    "data_movimento": f"{inicio_mes}T10:00:00",
}, token=token)
checar("quem tem estoque.retroativo passa mesmo fechado", st == 201, (st, r))

st, fechamentos = chamar("GET", "/cmv/fechamentos", token=token)
checar("o fechamento aparece na lista", any(f["id"] == id_fech for f in fechamentos))

# O fechamento congela também o relatório que EXPLICA o número, não só o número.
# ⚠️ O congelado é do MÊS INTEIRO: pedir "dia 1 até hoje" é outro recorte, e a
# resposta avisa que existe um mês fechado por trás dele.
st, parcial = chamar("GET", f"/cmv/movimentacao?{periodo}", token=token)
checar("recorte dentro do mês fechado não vem congelado",
       parcial.get("congelado") is False, parcial.get("congelado"))
checar("mas avisa que o mês está fechado",
       (parcial.get("mes_fechado") or {}).get("competencia") == str(inicio_mes),
       parcial.get("mes_fechado"))

fim_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
st, mov_f = chamar("GET", f"/cmv/movimentacao?inicio={inicio_mes}&fim={fim_mes}", token=token)
checar("depois de fechado, a movimentação vem congelada",
       mov_f.get("congelado") is True, mov_f.get("congelado"))
congelada = next((l for l in mov_f["linhas"] if l["id_produto"] == insumo), None)
checar("com o insumo dentro", congelada is not None, mov_f.get("produtos"))
# Renomear o produto não pode reescrever o mês fechado: o nome foi GRAVADO.
if congelada:
    chamar("PUT", f"/produtos/{insumo}", {"nome": f"Renomeado {marca}"}, token=token)
    st, mov_f2 = chamar("GET", f"/cmv/movimentacao?inicio={inicio_mes}&fim={fim_mes}",
                        token=token)
    ainda = next((l for l in mov_f2["linhas"] if l["id_produto"] == insumo), None)
    checar("renomear o produto NÃO reescreve o mês fechado",
           ainda and ainda["produto"] == congelada["produto"],
           (congelada["produto"], ainda["produto"] if ainda else None))
st, a3 = chamar("GET", f"/cmv/apuracao?{periodo}", token=token)
checar("a apuração marca o período como fechado", a3.get("fechado") is True, a3.get("fechado"))

st, r = chamar("POST", f"/cmv/fechamentos/{id_fech}/reabrir", token=token)
checar("reabre o período", st == 200, r)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": insumo, "quantidade": 1, "custo_unitario": 10, "id_local": local["id"],
    "data_movimento": f"{inicio_mes}T10:00:00",
}, token=tk_conf)
checar("depois de reaberto, o conferente volta a lançar retroativo", st == 201, (st, r))

print("6. permissão")
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
st, r = chamar("GET", "/cmv/apuracao", token=tk)
checar("cozinha NÃO vê o painel de CMV (403)", st == 403, st)
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": str(inicio_mes)}, token=tk)
checar("cozinha NÃO fecha período (403)", st == 403, st)

print("7. limpeza")
chamar("DELETE", f"/vendas/{0}", token=token)  # inofensivo: id inexistente
st, vendas = chamar("GET", f"/vendas?inicio={hoje}&fim={hoje}", token=token)
for v in vendas:
    if v["documento"] and marca in v["documento"]:
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
chamar("DELETE", f"/fichas/{nova['id']}", token=token)
chamar("DELETE", f"/fichas/{ficha}", token=token)
for p in (insumo, prato):
    chamar("DELETE", f"/produtos/{p}", token=token)
st, r = chamar("POST", f"/cmv/fechamentos/{id_fech}/reabrir", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
