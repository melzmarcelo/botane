"""O cardápio do site em inglês e alemão (migração 103, `services/traducao.py`).

🔑 Pedido do dono (decidido em 29/09/2026): Claude Haiku, categorias também, site nos três
idiomas. Duas metades:
1. pela API: corrigir à mão, o site no idioma pedido com o PORTUGUÊS onde faltar, e a
   tradução automática desligada (sem chave) dizendo por quê;
2. no serviço, com o Claude TROCADO por uma resposta fixa: traduz, não sobrescreve o que foi
   corrigido à mão, só retraduz quando o português muda, e "gerar de novo" devolve tudo ao
   automático. ⚠️ Nenhuma chamada de verdade à Anthropic sai daqui.

    python tests/smoke_traducao.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
token = r["access_token"]
cozinha = garantir_cozinha(chamar, token)
init_pool()
# ⚠️ A chave da CASA fica guardada e volta no fim — a suíte roda sem ela e cadastra uma falsa.
with get_cursor() as cur:
    cur.execute("SELECT * FROM integracoes WHERE servico = 'ANTHROPIC' AND id_unidade IS NULL")
    CHAVE_DA_CASA = cur.fetchone()
    cur.execute("DELETE FROM integracoes WHERE servico = 'ANTHROPIC' AND id_unidade IS NULL")
MARCA = str(time.time_ns() // 100)[-6:]
_st, par = chamar("GET", "/unidades/1/parametros", token=token)
chamar("PUT", "/unidades/1/parametros", {**par, "reservas_ligado": True}, token)

print("0. cenário: um cardápio com uma categoria e um pão de queijo")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Trad {MARCA}", "origem": "PRODUTOS",
                                         "situacao": "ATIVO"}, token)
ID_CAT = cat["id"]
_st, g = chamar("POST", f"/catalogos/{ID_CAT}/categorias",
                {"nome": f"Salgados {MARCA}", "descricao": "Feitos na casa"}, token)
_st, p = chamar("POST", "/produtos", {"nome": f"PAO DE QUEIJO TRAD {MARCA}", "tipo": "INSUMO",
                                      "um_estoque": "UN", "controla_estoque": False}, token)
PID = p["id"]
_st, atual = chamar("GET", f"/produtos/{PID}", token=token)
chamar("PUT", f"/produtos/{PID}", {**atual, "integrado_pdv": True, "preco_venda": 8,
                                   "nome_catalogo": "Pão de queijo",
                                   "informacao_adicional": "Quentinho, com queijo da serra"}, token)
st, it = chamar("POST", f"/catalogos/categorias/{g['id']}/itens", {"id_produto": PID}, token)
checar("o produto entra no cardápio (e salvar não quebra sem a chave)", st == 201, (st, it))

print("\n1. a tradução automática desligada diz por quê")
st, e = chamar("GET", "/traducao/estado", token=token)
checar("sem a chave cadastrada, a tradução está desligada", st == 200 and e["ligada"] is False, e)
st, r = chamar("POST", f"/traducao/catalogo/{ID_CAT}/traduzir", token=token)
checar("traduzir o catálogo responde 503 dizendo que falta a chave e ONDE cadastrá-la",
       st == 503 and "Integrações" in str(r.get("detail")), (st, r))
st, r = chamar("GET", f"/traducao/catalogo/{ID_CAT}/pendentes", token=token)
checar("e conta o que está pendente (catálogo, categoria e produto)", r.get("pendentes") == 3, r)

print("\n2. corrigir à mão")
st, t = chamar("GET", f"/traducao/produto/{PID}", token=token)
checar("a origem é o NOME DE VITRINE, não o nome do cadastro",
       t["origem"]["nome"] == "Pão de queijo" and t["en"]["nome"] is None, t)
st, t = chamar("PUT", f"/traducao/produto/{PID}",
               {"en": {"nome": "Cheese bread", "descricao": "Warm, with mountain cheese"}}, token)
checar("grava a tradução inglesa à mão", st == 200 and t["en"]["nome"] == "Cheese bread", (st, t))
checar("e marca os dois campos como editados à mão",
       set(t["editada"]) == {"nome_catalogo_en", "informacao_adicional_en"}, t["editada"])
st, t = chamar("PUT", f"/traducao/categoria/{g['id']}", {"de": {"nome": "Snacks"}}, token)
checar("a categoria também (alemão)", st == 200 and t["de"]["nome"] == "Snacks", (st, t))
st, r = chamar("PUT", f"/traducao/produto/{PID}", {"en": {"nome": "x"}}, cozinha)
checar("quem não edita catálogo nem produto não corrige (403)", st == 403, st)

print("\n3. o site no idioma pedido — e o português onde faltar")
_st, pt = chamar("GET", f"/publico/1/catalogos/{ID_CAT}")
_st, en = chamar("GET", f"/publico/1/catalogos/{ID_CAT}?idioma=en")
_st, de = chamar("GET", f"/publico/1/catalogos/{ID_CAT}?idioma=de")
item = lambda c: c["categorias"][0]["itens"][0]  # noqa: E731
checar("em inglês: o produto traduzido", item(en)["nome"] == "Cheese bread"
       and item(en)["descricao"] == "Warm, with mountain cheese", item(en))
checar("e a categoria sem tradução inglesa cai no português",
       en["categorias"][0]["nome"] == f"Salgados {MARCA}", en["categorias"][0]["nome"])
checar("em alemão: a categoria traduzida e o produto em português",
       de["categorias"][0]["nome"] == "Snacks" and item(de)["nome"] == "Pão de queijo", de)
checar("sem idioma, tudo em português", item(pt)["nome"] == "Pão de queijo", item(pt))
st, _r = chamar("GET", f"/publico/1/catalogos/{ID_CAT}?idioma=fr")
checar("idioma que o site não tem é recusado (422)", st == 422, st)

print("\n4. a tradução automática, com o Claude trocado por uma resposta fixa")
from services import traducao as tr  # noqa: E402

pedidos: list = []


def falso(itens, cfg):
    pedidos.append(itens)
    return [{"chave": i["chave"],
             "en": {"nome": f"EN {i.get('nome', '')}", "descricao": f"EN {i.get('descricao', '')}"
                    if i.get("descricao") else ""},
             "de": {"nome": f"DE {i.get('nome', '')}", "descricao": f"DE {i.get('descricao', '')}"
                    if i.get("descricao") else ""}} for i in itens]


_config_de_verdade = tr._config
tr._config = lambda cur: {"ativa": True, "chave": "sk-ant-falsa", "modelo": "m", "ilegivel": False}
tr._chamar = falso
with get_cursor() as cur:
    r = tr.traduzir(cur, "produto", [PID])
    t = tr.obter(cur, "produto", PID)
checar("traduz o produto", r["traduzidos"] == 1, r)
checar("🔑 o inglês corrigido à mão FICA", t["en"]["nome"] == "Cheese bread", t["en"])
checar("e o alemão, que ninguém corrigiu, vem da tradução", t["de"]["nome"] == "DE Pão de queijo", t["de"])
with get_cursor() as cur:
    r = tr.traduzir(cur, "produto", [PID])
checar("de novo, sem o português mudar: nenhuma chamada", r["traduzidos"] == 0 and len(pedidos) == 1, r)
with get_cursor() as cur:
    cur.execute("UPDATE produtos SET informacao_adicional = 'Recheado' WHERE id = %s", (PID,))
    antes = tr.obter(cur, "produto", PID)
    r = tr.traduzir(cur, "produto", [PID])
    t = tr.obter(cur, "produto", PID)
checar("mudou o português: a tradução fica marcada desatualizada", antes["desatualizada"] is True, antes)
checar("e é refeita, sem tocar no que foi corrigido à mão",
       r["traduzidos"] == 1 and t["de"]["descricao"] == "DE Recheado"
       and t["en"]["descricao"] == "Warm, with mountain cheese", t)
with get_cursor() as cur:
    r = tr.traduzir(cur, "produto", [PID], forcar=True)
    t = tr.obter(cur, "produto", PID)
checar("'gerar de novo' devolve o corrigido à mão para o automático",
       t["en"]["nome"] == "EN Pão de queijo" and t["editada"] == [], t)
with get_cursor() as cur:
    r = tr.do_catalogo(cur, ID_CAT)
    falta = tr.pendentes_do_catalogo(cur, ID_CAT)
checar("o catálogo inteiro: nome e categoria traduzidos, nada pendente",
       r["traduzidos"] == 2 and falta == 0, (r, falta))
with get_cursor() as cur:
    g2 = tr.obter(cur, "categoria", g["id"])
checar("e a categoria corrigida à mão em alemão continua 'Snacks'",
       g2["de"]["nome"] == "Snacks" and g2["en"]["nome"] == f"EN Salgados {MARCA}", g2)
checar("a resposta com cerca de código também é lida",
       tr._ler_json('```json\n{"itens": [{"chave": "1"}]}\n```') == [{"chave": "1"}])
checar("o português é a reserva quando falta tradução",
       tr.escolher("Pão", None, None, "en") == "Pão" and tr.escolher("Pão", "Bread", None, "en") == "Bread")

tr._config = _config_de_verdade

print("\n5. a chave é cadastrada no SISTEMA (Integrações ▸ Tradução)")
try:
    st, c = chamar("GET", "/traducao/config", token=token)
    checar("sem chave: a configuração diz que está desligada", st == 200 and c["ligada"] is False
           and c["chave"] is None and c["modelo"] == "claude-haiku-4-5-20251001", (st, c))
    st, r = chamar("PUT", "/traducao/config", {"chave": "minha-chave"}, token)
    checar("o que não parece chave da Anthropic é recusado (422)", st == 422, (st, r))
    st, c = chamar("PUT", "/traducao/config", {"chave": "sk-ant-teste-fim7788", "ativa": True}, token)
    checar("🔑 grava a chave e devolve SÓ mascarada", st == 200 and c["ligada"] is True
           and c["chave"].endswith("7788") and "teste" not in c["chave"], (st, c))
    with get_cursor() as cur:
        cur.execute("SELECT credenciais FROM integracoes WHERE servico = 'ANTHROPIC' AND id_unidade IS NULL")
        bruto = bytes(cur.fetchone()["credenciais"])
    checar("e no banco ela está CIFRADA", b"sk-ant" not in bruto)
    st, e = chamar("GET", "/traducao/estado", token=token)
    checar("com a chave cadastrada, a tradução liga", e.get("ligada") is True, e)
    st, c = chamar("PUT", "/traducao/config", {"chave": "", "modelo": "claude-outro"}, token)
    checar("salvar sem chave MANTÉM a guardada", st == 200 and c["chave"].endswith("7788")
           and c["modelo"] == "claude-outro", c)
    st, c = chamar("PUT", "/traducao/config", {"ativa": False}, token)
    checar("desligar sem apagar a chave", c["ligada"] is False and c["chave"].endswith("7788"), c)
    st, c = chamar("DELETE", "/traducao/config/chave", token=token)
    checar("remover a chave desliga", st == 200 and c["chave"] is None and c["ligada"] is False, c)
    st, r = chamar("POST", "/traducao/config/testar", token=token)
    checar("testar sem chave é 400", st == 400, (st, r))
    st, _r = chamar("GET", "/traducao/config", token=cozinha)
    checar("quem não configura integração não vê a chave (403)", st == 403, st)
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM auditoria WHERE entidade = 'integracao' "
                    "AND id_entidade = 'ANTHROPIC' AND depois::text LIKE '%%sk-ant%%'")
        checar("a auditoria nunca guarda a chave", cur.fetchone()["n"] == 0)
finally:
    with get_cursor() as cur:
        cur.execute("DELETE FROM integracoes WHERE servico = 'ANTHROPIC' AND id_unidade IS NULL")
        if CHAVE_DA_CASA:
            cols = [k for k in CHAVE_DA_CASA if k != "id"]
            # ⚠️ `psycopg2`, o driver do projeto: com `psycopg` (o 3) o import estourava e a
            # chave da CASA não voltava — foi assim que a de verdade se perdeu (29/09/2026).
            from psycopg2.extras import Json
            cur.execute(f"INSERT INTO integracoes ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                        [Json(CHAVE_DA_CASA[k]) if k == "config" and CHAVE_DA_CASA[k] is not None
                         else CHAVE_DA_CASA[k] for k in cols])

with get_cursor() as cur:
    cur.execute("DELETE FROM catalogos WHERE id = %s", (ID_CAT,))
chamar("PUT", "/unidades/1/parametros", {"reservas_ligado": par.get("reservas_ligado")}, token)
print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
