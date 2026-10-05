"""Teste de fumaça: a conferência antes de fechar o período do CMV.

Prova que a lista mede o PERÍODO pedido e reage ao que distorce o número:

    * uma nota digitada com data no período, sem lançar, entra em
      "nota do período ainda não lançada" (uma a mais, com o valor dela);
    * lançada, sai da lista — e descartada também;
    * o período vem da MESMA pergunta do fechamento (o ciclo da loja), não das
      datas que a tela mandar;
    * quem não fecha período não vê a conferência.

⚠️ **Mede por DELTA.** A base local tem notas abertas de verdade; a suíte conta
quanto havia antes e confere a diferença, sem supor que começa do zero.
⚠️ **Não fecha período nenhum**: fechar é o que `smoke_cmv` e `smoke_ciclos` já
exercitam, e é a mesma rota — aqui só se lê.

    python tests/smoke_cmv_conferencia.py      (API de pé na 9200)
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
HOJE = datetime.date.today()


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
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


def item(conferencia, chave):
    return next((i for i in conferencia.get("itens", []) if i["chave"] == chave),
                {"quantidade": 0, "valor": 0})


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
local = garantir_local(chamar, token)

print("1. a conferência responde, e o período é o da loja")
st, antes = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=token)
checar("responde", st == 200, (st, antes))
st, periodos = chamar("GET", "/cmv/apuracao", token=token)
checar("o período cobre o dia pedido",
       antes.get("inicio", "9") <= str(HOJE) <= antes.get("fim", "0"), antes)
checar("traz o nome do período, do servidor", bool(antes.get("rotulo")), antes.get("rotulo"))
checar("cada ponto diz quantos, o que é e onde resolver",
       all(i.get("quantidade") and i.get("titulo") and i.get("href", "").startswith("/")
           and i.get("peso") in ("distorce", "atencao") for i in antes.get("itens", [])),
       antes.get("itens"))
checar("e `limpo` concorda com a lista", antes.get("limpo") == (not antes.get("itens")), antes)
checar("`distorcem` conta só as que mudam o número",
       antes.get("distorcem") == sum(1 for i in antes["itens"] if i["peso"] == "distorce"))

print("\n2. nota do período sem lançar entra na lista")
st, fornecedores = chamar("GET", "/fornecedores?limite=1", token=token)
st, prod = chamar("POST", "/produtos", {
    "codigo": f"CF-{marca}", "nome": f"Conferencia {marca}", "tipo": "INSUMO",
    "um_estoque": "UN", "controla_estoque": True, "status": "ATIVO"}, token=token)
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": fornecedores[0]["id"], "numero": f"CF{marca}", "serie": "1",
    "data_emissao": str(HOJE), "id_local": local["id"],
    "itens": [{"id_produto": prod["id"], "quantidade": 3, "valor_unitario": 7}]}, token=token)
checar("a nota foi digitada", st == 200, (st, nota))
st, com = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=token)
a, d = item(antes, "notas_nao_lancadas"), item(com, "notas_nao_lancadas")
checar("uma nota a mais", d["quantidade"] == a["quantidade"] + 1, (a, d))
checar("com o valor dela: 3 x 7,00 = 21,00",
       abs((d["valor"] or 0) - (a["valor"] or 0) - 21) < 0.01, (a, d))
checar("e ela conta como algo que distorce o número", d.get("peso") == "distorce", d)

print("\n3. nota de OUTRO período não entra neste")
longe = HOJE - datetime.timedelta(days=400)
st, velha = chamar("POST", "/notas", {
    "id_fornecedor": fornecedores[0]["id"], "numero": f"CV{marca}", "serie": "1",
    "data_emissao": str(longe), "id_local": local["id"],
    "itens": [{"id_produto": prod["id"], "quantidade": 1, "valor_unitario": 9}]}, token=token)
st, com2 = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=token)
checar("a de 400 dias atrás não muda a contagem de hoje",
       item(com2, "notas_nao_lancadas")["quantidade"] == d["quantidade"],
       item(com2, "notas_nao_lancadas"))
st, la = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={longe}", token=token)
checar("mas aparece no período dela", item(la, "notas_nao_lancadas")["quantidade"] >= 1,
       item(la, "notas_nao_lancadas"))

print("\n4. lançada, a nota sai da lista")
st, r = chamar("POST", f"/notas/{nota['id']}/lancar", {"id_local": local["id"]}, token=token)
checar("lança", st == 200, (st, r))
st, depois = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=token)
checar("a contagem volta ao que era",
       item(depois, "notas_nao_lancadas")["quantidade"] == a["quantidade"],
       item(depois, "notas_nao_lancadas"))

print("\n4b. o PAINEL mostra a mesma lista, no recorte que ele tem na tela")
st, painel = chamar("GET", f"/cmv/conferencia?inicio={depois['inicio']}&fim={depois['fim']}",
                    token=token)
checar("a rota do painel responde", st == 200, (st, painel))
checar("com as mesmas pendências da janela de fechar, para o mesmo período",
       [(i["chave"], i["quantidade"]) for i in painel.get("itens", [])]
       == [(i["chave"], i["quantidade"]) for i in depois.get("itens", [])],
       (painel.get("itens"), depois.get("itens")))
st, corrente = chamar("GET", "/cmv/conferencia", token=token)
checar("sem datas, é o período corrente da loja", st == 200 and corrente.get("fim") == str(HOJE),
       (st, corrente.get("inicio"), corrente.get("fim")))

print("\n5. quem não fecha período não vê a conferência")
cozinha = garantir_cozinha(chamar, token)
st, _ = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={HOJE}", token=cozinha)
checar("a cozinha leva 403", st == 403, st)
st, _ = chamar("GET", "/cmv/fechamentos/conferencia", token=token)
checar("sem dizer o dia, 422", st == 422, st)

print("\n6. limpeza")
chamar("POST", f"/notas/{nota['id']}/estornar", {}, token=token)
chamar("DELETE", f"/notas/{nota['id']}", token=token)
chamar("DELETE", f"/notas/{velha['id']}", token=token)
chamar("DELETE", f"/produtos/{prod['id']}", token=token)
st, fim = chamar("GET", f"/cmv/fechamentos/conferencia?competencia={longe}", token=token)
checar("a nota velha saiu do período dela",
       item(fim, "notas_nao_lancadas")["quantidade"]
       == item(la, "notas_nao_lancadas")["quantidade"] - 1, item(fim, "notas_nao_lancadas"))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
