"""Teste de fumaça: a Precificação — configuração por loja, a conta e a aplicação.

O cenário, conferido na mão. Um produto de revenda que custa R$ 10,00:

    Impostos 6% + Cartão 2,5% + Custo operacional 25% + Margem 15% = 48,5%
    preço sugerido = 10 ÷ (1 − 0,485) = 19,4175 → R$ 19,42 (sem arredondar)
                                              → R$ 19,90 (para ,90)
                                              → R$ 19,50 (para ,00 ou ,50)
    ⚠️ "custo + 48,5%" daria R$ 14,85 — a suíte cobra que NÃO é essa a conta.

    vendido hoje a R$ 18,00:  lucro = 18 − 18 × 33,5% − 10 = R$ 1,97 (10,94%)
                              falta R$ 1,42 para o piso — abaixo da margem

E a precedência, que é o coração da decisão do dono ("único, por categoria, por
setor"): a linha mais específica de MESMO NOME substitui a geral, e categoria
ganha de setor.

    Custo operacional 20% só no SETOR do produto      → 43,5% → R$ 17,70
    + Custo operacional 30% na CATEGORIA do produto   → 53,5% → R$ 21,51

⚠️ **Guarda e devolve a configuração da loja**: a base local pode ter uma de
verdade, e a suíte grava por cima para medir.

    python tests/smoke_precificacao.py      (da pasta `api`, com a API de pé na 9200)
"""

import atexit
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_categorias, garantir_cozinha, garantir_local, garantir_setores  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
HOJE = datetime.date.today().isoformat()


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
        with urllib.request.urlopen(req, dados, timeout=90) as r:
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


def perto(a, b, tol=0.005):
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
st, eu = chamar("GET", "/auth/me", token=token)
st, lojas = chamar("GET", "/unidades", token=token)
ativas = [l for l in (lojas or []) if l.get("ativo", True)]
st, minha_config = chamar("GET", "/precificacao/config", token=token)
MINHA = minha_config["id_unidade"]
local = garantir_local(chamar, token)
categoria = garantir_categorias(chamar, token)[0]
setor = garantir_setores(chamar, token)[0]


def _corpo_de(k: dict) -> dict:
    return {"id_unidade_origem": k.get("id_unidade_origem"), "arredondamento": k["arredondamento"],
            "linhas": [] if k.get("id_unidade_origem") else [
                {x: l[x] for x in ("nome", "tipo", "valor", "alcance", "id_categoria", "id_setor")}
                for l in k["linhas"]]}


# ⚠️ Devolve a configuração da loja mesmo se a suíte estourar no meio.
_original = _corpo_de(minha_config)
atexit.register(lambda: chamar("PUT", "/precificacao/config", _original, token=token))

BASICAS = [
    {"nome": "Impostos", "tipo": "PERCENTUAL", "valor": 6, "alcance": "TUDO"},
    {"nome": "Taxa de cartão", "tipo": "PERCENTUAL", "valor": 2.5, "alcance": "TUDO"},
    {"nome": "Custo operacional", "tipo": "PERCENTUAL", "valor": 25, "alcance": "TUDO"},
    {"nome": "Margem", "tipo": "MARGEM", "valor": 15, "alcance": "TUDO"},
]


def configurar(linhas, arredondamento="NENHUM", unidade=None):
    return chamar("PUT", "/precificacao/config",
                  {"arredondamento": arredondamento, "linhas": linhas}, token=token,
                  unidade=unidade)


produtos = []
print("1. o cenário: um produto que custa R$ 10,00, vendido hoje a R$ 18,00")
st, p = chamar("POST", "/produtos", {
    "codigo": f"PRC-{marca}", "nome": f"PRECIFICAR {marca}", "tipo": "REVENDA",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO", "preco_venda": 18,
    "id_categoria": categoria["id"], "id_setor": setor["id"]}, token=token)
produto = (p or {}).get("id")
produtos.append(produto)
checar("o produto de teste nasce", bool(produto), (st, p))
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 10, "custo_unitario": 10, "id_local": local["id"]},
    token=token)
checar("a compra entra a R$ 10,00", st == 201, (st, r))
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": HOJE, "documento": f"PRC-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": produto, "quantidade": 2, "valor_unitario": 18}]}]}, token=token)
checar("e duas unidades são vendidas a R$ 18,00", st in (200, 201), (st, r))


def linha_da_analise():
    # ⚠️ Fixando o produto: a base local tem centenas de vendidos no mês, e o desta
    # rodada (duas unidades) nunca estaria entre os que mais faturam.
    st, a = chamar("GET", f"/precificacao/analise?dias=30&id_produto={produto}", token=token)
    return a, next((i for i in (a or {}).get("itens", []) if i["id_produto"] == produto), None)


print("\n2. a conta é uma DIVISÃO, com a margem dentro")
st, k = configurar(BASICAS)
checar("a configuração é gravada", st == 200 and k.get("configurada") is True, (st, k))
checar("e é desta loja (editável)", k.get("somente_leitura") is False, k)
a, x = linha_da_analise()
checar("o produto vendido está na análise", x is not None, a.get("resumo"))
checar("o custo direto é R$ 10,00", perto(x["custo_direto"], 10), x)
checar("a soma dos percentuais é 33,5% e a margem alvo 15%",
       perto(x["soma_pct"], 33.5) and perto(x["margem_alvo_pct"], 15), x)
checar("o sugerido é 10 ÷ (1 − 0,485) = R$ 19,42", perto(x["sugerido"], 19.42), x["sugerido"])
checar("e NÃO custo + 48,5% (R$ 14,85)", not perto(x["sugerido"], 14.85), x["sugerido"])
checar("no preço de R$ 18,00 sobra R$ 1,97", perto(x["lucro"], 1.97), x["lucro"])
checar("que é 10,94% do preço", perto(x["lucro_pct"], 10.94), x["lucro_pct"])
checar("faltam R$ 1,42 para o piso", perto(x["diferenca"], 1.42), x["diferenca"])
checar("está ABAIXO da margem", x["situacao"] == "abaixo", x["situacao"])
checar("e o impacto no mês é 1,42 × 2 vendidas = R$ 2,84", perto(x["impacto"], 2.84), x["impacto"])

print("\n3. o arredondamento é sempre para CIMA")
configurar(BASICAS, "NOVENTA")
_a, x = linha_da_analise()
checar("para ,90: R$ 19,90", perto(x["sugerido"], 19.90), x["sugerido"])
configurar(BASICAS, "MEIO")
_a, x = linha_da_analise()
checar("para ,00 ou ,50: R$ 19,50", perto(x["sugerido"], 19.50), x["sugerido"])

print("\n4. único, por setor, por categoria — a mais específica de mesmo nome substitui")
por_setor = {"nome": "Custo operacional", "tipo": "PERCENTUAL", "valor": 20,
             "alcance": "SETOR", "id_setor": setor["id"]}
st, k = configurar(BASICAS + [por_setor])
checar("a linha por setor é aceita junto da geral", st == 200, (st, k))
_a, x = linha_da_analise()
checar("o operacional do SETOR (20%) substitui o geral (25%): soma 28,5%",
       perto(x["soma_pct"], 28.5), x["soma_pct"])
checar("e o sugerido vira 10 ÷ 0,565 = R$ 17,70", perto(x["sugerido"], 17.70), x["sugerido"])
checar("a R$ 18,00 o produto passa a estar NA margem, com folga",
       x["situacao"] == "na_margem" and x["diferenca"] < 0 and x["impacto"] is None, x)
por_categoria = {"nome": "Custo operacional", "tipo": "PERCENTUAL", "valor": 30,
                 "alcance": "CATEGORIA", "id_categoria": categoria["id"]}
configurar(BASICAS + [por_setor, por_categoria])
_a, x = linha_da_analise()
checar("a CATEGORIA (30%) ganha do setor: soma 38,5%", perto(x["soma_pct"], 38.5), x["soma_pct"])
checar("e o sugerido vira 10 ÷ 0,465 = R$ 21,51", perto(x["sugerido"], 21.51), x["sugerido"])
outra_cat = {"nome": "Taxa do aplicativo", "tipo": "PERCENTUAL", "valor": 20,
             "alcance": "CATEGORIA", "id_categoria": 999999}
st, r = configurar(BASICAS + [outra_cat])
checar("categoria que não existe é recusada com frase, não com 500", st in (400, 404, 409, 422), (st, r))
margem_cat = {"nome": "Margem da categoria", "tipo": "MARGEM", "valor": 25,
              "alcance": "CATEGORIA", "id_categoria": categoria["id"]}
configurar(BASICAS + [margem_cat])
_a, x = linha_da_analise()
checar("a margem da categoria (25%) substitui a da loja, mesmo com outro nome",
       perto(x["margem_alvo_pct"], 25) and perto(x["sugerido"], 24.10), x)

print("\n5. custo por unidade entra no custo direto")
embalagem = {"nome": "Embalagem", "tipo": "VALOR", "valor": 1, "alcance": "TUDO"}
configurar(BASICAS + [embalagem])
_a, x = linha_da_analise()
checar("custo direto = 10,00 + 1,00 de embalagem", perto(x["custo_direto"], 11), x["custo_direto"])
checar("e o sugerido vira 11 ÷ 0,515 = R$ 21,36", perto(x["sugerido"], 21.36), x["sugerido"])

print("\n6. o que a configuração recusa")
st, r = configurar(BASICAS + [{"nome": "Exagero", "tipo": "PERCENTUAL", "valor": 60, "alcance": "TUDO"}])
checar("soma geral de 100% ou mais é recusada", st == 400 and "100" in str(r.get("detail")), (st, r))
st, r = configurar(BASICAS + [BASICAS[0]])
checar("a mesma linha duas vezes é recusada", st == 400, (st, r))
st, r = configurar([{"nome": "Sem setor", "tipo": "PERCENTUAL", "valor": 5, "alcance": "SETOR"}])
checar("linha por setor sem dizer o setor é 422", st == 422, st)
st, k = chamar("GET", "/precificacao/config", token=token)
checar("depois das recusas, vale a última configuração boa",
       any(l["nome"] == "Embalagem" for l in k["linhas"]) and len(k["linhas"]) == 5, k["linhas"])

print("\n7. a simulação decompõe o preço, e a soma fecha")
configurar(BASICAS)
st, s = chamar("POST", "/precificacao/simular", {"id_produto": produto, "preco": 18}, token=token)
checar("a simulação responde", st == 200, (st, s))
checar("as partes somam exatamente o preço",
       perto(sum(x["valor"] for x in s["partes"]), 18, tol=0.011), s["partes"])
checar("e o lucro é o mesmo da análise", perto(s["lucro"], 1.97), s["lucro"])
st, s9 = chamar("POST", "/precificacao/simular", {"id_produto": produto, "preco": 9}, token=token)
checar("abaixo do custo a parte final se chama Prejuízo",
       s9["partes"][-1]["tipo"] == "prejuizo" and s9["lucro"] < 0, s9["partes"][-1])
st, r = chamar("POST", "/precificacao/simular", {"id_produto": 99999999, "preco": 9}, token=token)
checar("produto inexistente é 404", st == 404, st)

print("\n8. aplicar: vale na hora, e diz a verdade sobre o PDV")
st, r = chamar("POST", "/precificacao/aplicar",
               {"itens": [{"id_produto": produto, "preco": 19.42}]}, token=token)
checar("o preço é aplicado", st == 200 and len(r.get("aplicados", [])) == 1, (st, r))
checar("a resposta traz de quanto para quanto",
       perto(r["aplicados"][0]["de"], 18) and perto(r["aplicados"][0]["para"], 19.42), r["aplicados"])
checar("e diz se a loja envia ao PDV (o parâmetro dela, não uma decisão daqui)",
       isinstance(r.get("envia_ao_pdv"), bool), r)
checar("numa casa de várias lojas o preço nasce DA LOJA; numa só, da casa",
       r["aplicados"][0]["da_loja"] == (len(ativas) > 1), (r["aplicados"][0], len(ativas)))
_a, x = linha_da_analise()
checar("na hora: a análise já mostra R$ 19,42 e o produto NA margem",
       perto(x["preco"], 19.42) and x["situacao"] == "na_margem", x)
st, r = chamar("POST", "/precificacao/aplicar",
               {"itens": [{"id_produto": produto, "preco": 19.42}]}, token=token)
checar("aplicar o mesmo preço de novo não cria histórico", r.get("sem_mudanca") == 1
       and r.get("aplicados") == [], r)
st, e = chamar("GET", f"/cmv/preco-custo/{produto}", token=token)
checar("e o preço novo aparece na tela de Preços", perto(e["pontos"][-1]["preco"], 19.42),
       e["pontos"][-1])
st, r = chamar("POST", "/precificacao/aplicar", {"itens": []}, token=token)
checar("lista vazia é 422", st == 422, st)

print("\n9. seguir a configuração de outra loja")
st, r = chamar("PUT", "/precificacao/config", {"id_unidade_origem": MINHA, "linhas": []}, token=token)
checar("a loja não segue a si mesma", st == 400, (st, r))
st, r = chamar("PUT", "/precificacao/config", {"id_unidade_origem": 999999, "linhas": []}, token=token)
checar("loja que não existe é 404", st == 404, (st, r))
# 🔑 Uma filial SÓ desta rodada, desativada no fim: a base local tem uma loja só,
# e "seguir outra loja" é metade da decisão do dono — não pode ficar sem medir.
st, filial = chamar("POST", "/unidades", {
    "nome": f"Filial precificacao {marca}", "cnpj": None, "ativo": True}, token=token)
OUTRA = (filial or {}).get("id")
checar("filial de teste criada", st in (200, 201) and bool(OUTRA), (st, filial))
atexit.register(lambda: OUTRA and chamar("PUT", f"/unidades/{OUTRA}", {"ativo": False}, token=token))
if OUTRA:
    st, antes_outra = chamar("GET", "/precificacao/config", token=token, unidade=OUTRA)
    original_outra = _corpo_de(antes_outra)
    atexit.register(lambda: chamar("PUT", "/precificacao/config", original_outra, token=token,
                                   unidade=OUTRA))
    st, k = chamar("PUT", "/precificacao/config", {"id_unidade_origem": MINHA, "linhas": []},
                   token=token, unidade=OUTRA)
    checar("a outra loja passa a seguir esta", st == 200 and k.get("somente_leitura") is True, (st, k))
    checar("e enxerga as MESMAS linhas, só para consulta",
           sorted(l["nome"] for l in k["linhas"]) == sorted(l["nome"] for l in BASICAS), k["linhas"])
    st, daqui = chamar("GET", "/precificacao/config", token=token)
    checar("esta loja sabe quem a segue", any(s["id"] == OUTRA for s in daqui["seguida_por"]),
           daqui["seguida_por"])
    st, r = chamar("PUT", "/precificacao/config", {"id_unidade_origem": OUTRA, "linhas": []},
                   token=token)
    checar("quem é seguida não pode passar a seguir outra (sem corrente)", st == 409, (st, r))
    st, k = chamar("PUT", "/precificacao/config", {"id_unidade_origem": None, "linhas": []},
                   token=token, unidade=OUTRA)
    checar("voltar para a própria sem mandar linhas COPIA a que era seguida",
           st == 200 and k.get("somente_leitura") is False and len(k["linhas"]) == len(BASICAS),
           (st, k.get("linhas")))
    st, r = chamar("PUT", "/precificacao/config", {"id_unidade_origem": OUTRA, "linhas": []},
                   token=token)
    st2, k2 = chamar("PUT", "/precificacao/config",
                     {"arredondamento": "NENHUM", "linhas": BASICAS}, token=token)
    # ⚠️ Com a filial de volta à configuração própria, ESTA loja pode segui-la —
    # e desfaz em seguida, para o resto da suíte e para a limpeza.
    checar("livre da seguidora, esta loja pode seguir a outra — e voltar",
           st == 200 and r.get("somente_leitura") is True and st2 == 200
           and k2.get("somente_leitura") is False, (st, st2))

print("\n10. cada porta com a sua chave")
cozinha = garantir_cozinha(chamar, token)
for metodo, caminho, corpo in [
        ("GET", "/precificacao/config", None), ("GET", "/precificacao/analise", None),
        ("PUT", "/precificacao/config", {"linhas": []}),
        ("POST", "/precificacao/simular", {"id_produto": produto, "preco": 10}),
        ("POST", "/precificacao/aplicar", {"itens": [{"id_produto": produto, "preco": 1}]}),
        ("GET", "/precificacao/faturamento", None)]:
    st, _r = chamar(metodo, caminho, corpo, token=cozinha)
    checar(f"a cozinha não passa em {metodo} {caminho}", st == 403, st)
st, fat = chamar("GET", "/precificacao/faturamento", token=token)
checar("o faturamento dos meses fechados responde em lista", st == 200 and isinstance(fat, list), (st, fat))
_a, x = linha_da_analise()
checar("o preço que a cozinha tentou aplicar NÃO entrou", perto(x["preco"], 19.42), x["preco"])

print("\n11. limpeza")
st, vendas = chamar("GET", f"/vendas?busca=PRC-{marca}", token=token)
for v in (vendas or []):
    if not v.get("cancelada"):
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
st, movs = chamar("GET", f"/estoque/movimentos?id_produto={produto}&limite=50", token=token)
entrada = next((m for m in (movs or []) if m.get("tipo") == "ENTRADA_MANUAL"), None)
if entrada:
    chamar("POST", f"/estoque/movimentos/{entrada['id']}/estornar", {"motivo": "limpeza da suíte"},
           token=token)
for id_produto in produtos:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
st, k = chamar("PUT", "/precificacao/config", _original, token=token)
checar("a configuração da loja volta a ser a de antes",
       st == 200 and len(k["linhas"]) == len(_original["linhas"]), (st, k.get("linhas")))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
