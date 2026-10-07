"""Etiquetas de validade: produção, abertura, descongelamento, QR, baixa e descarte.

🔑 **Pedido do dono (28/09/2026):** *"um novo módulo, o de Etiquetas … para controlar
validade, quantidade e demais coisas úteis, em produtos produzidos e abertos para
consumo."* (migração 100, `services/etiquetas.py`).

    python tests/smoke_etiquetas.py        (API de pé na 9200)
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha, garantir_local  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
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
        return e.code, json.loads(e.read() or b"null")


def baixar(caminho, token):
    req = urllib.request.Request(BASE + caminho)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, None, e.read()


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def quando(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
cozinha = garantir_cozinha(chamar, token)
checar("a cozinha entra", bool(cozinha))
init_pool()
marca = str(time.time_ns() // 100)[-6:]
local = garantir_local(chamar, token)


def novo(nome, **extra):
    corpo = {"nome": nome, "tipo": "INSUMO", "um_estoque": "UN", "id_local_padrao": local["id"]}
    if extra.get("producao_propria"):
        corpo["tipo"] = "PRODUZIDO"
    st, r = chamar("POST", "/produtos", corpo | extra, token=token)
    return (r or {}).get("id")


print("0. cenário: um molho da casa (com lote), o tomate dele e um creme que se abre")
tomate = novo(f"Etq tomate {marca}")
molho = novo(f"Etq molho {marca}", producao_propria=True, controla_lote=True,
             controla_validade=True)
sem_regra = novo(f"Etq sem regra {marca}", producao_propria=True, controla_lote=True)
creme = novo(f"Etq creme {marca}")
checar("os produtos nascem", all([tomate, molho, sem_regra, creme]))
chamar("POST", "/estoque/entradas", {"id_produto": tomate, "quantidade": 100,
                                     "custo_unitario": 2, "id_local": local["id"]}, token=token)
chamar("POST", "/estoque/entradas", {"id_produto": creme, "quantidade": 10,
                                     "custo_unitario": 4, "id_local": local["id"]}, token=token)
for prod in (molho, sem_regra):
    st, r = chamar("POST", "/fichas", {
        "id_produto": prod, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
        "itens": [{"id_insumo": tomate, "qtd_bruta": 1, "um": "UN"}]}, token=token)
    chamar("POST", f"/fichas/{(r or {}).get('id')}/homologar", {}, token=token)

print("\n1. a validade por evento e conservação")
regras_molho = [
    {"evento": "PRODUCAO", "conservacao": "REFRIGERADO", "prazo": 3, "unidade": "DIAS",
     "padrao": True},
    {"evento": "PRODUCAO", "conservacao": "CONGELADO", "prazo": 60, "unidade": "DIAS"},
    {"evento": "DESCONGELAMENTO", "conservacao": "REFRIGERADO", "prazo": 24,
     "unidade": "HORAS"},
]
st, r = chamar("PUT", f"/etiquetas/validades/{molho}", {"regras": regras_molho}, token=token)
checar("grava as regras do molho", st == 200 and len(r.get("regras", [])) == 3, (st, r))
st, r = chamar("PUT", f"/etiquetas/validades/{creme}", {"regras": [
    {"evento": "ABERTURA", "conservacao": "REFRIGERADO", "prazo": 3, "unidade": "DIAS"}]},
    token=token)
checar("sem padrão marcado, a única regra do evento VIRA o padrão",
       st == 200 and r["regras"][0]["padrao"] is True, (st, r))
st, r = chamar("PUT", f"/etiquetas/validades/{creme}", {"regras": [
    {"evento": "ABERTURA", "conservacao": "REFRIGERADO", "prazo": 3},
    {"evento": "ABERTURA", "conservacao": "REFRIGERADO", "prazo": 5}]}, token=token)
checar("a mesma conservação duas vezes no evento é recusada", st == 422, (st, r))
st, r = chamar("PUT", f"/etiquetas/validades/{creme}", {"regras": []}, token=cozinha)
checar("a cozinha NÃO configura validade (403)", st == 403, (st, r))
st, r = chamar("GET", f"/etiquetas/validades/{molho}", token=cozinha)
checar("mas lê a validade para imprimir", st == 200 and len(r) == 3, (st, r))

# 🔑 **As validades moram no cadastro do PRODUTO** (06/10/2026, pedido do dono):
# quem cadastra produto grava as regras, mesmo sem `etiquetas.configurar` — é a
# pessoa que edita todo o resto daquela tela. O MODELO da etiqueta continua só de
# quem configura etiquetas: é a impressora da loja, não um dado do produto.
_st, _papeis = chamar("GET", "/papeis", token=token)
_conferente = next((x for x in (_papeis or []) if x["nome"] == "Conferente / Estoque"), None)
_email = f"etq.conferente.{marca}@botane.com.br"
_st, _novo = chamar("POST", "/usuarios", {
    "nome": f"Conferente etiquetas {marca}", "email": _email, "senha": "smoke12345",
    "papeis": [{"id_papel": (_conferente or {}).get("id")}]}, token=token)
_st, _entrou = chamar("POST", "/auth/login", {"email": _email, "senha": "smoke12345"})
cadastra = (_entrou or {}).get("access_token")
st, r = chamar("PUT", f"/etiquetas/validades/{creme}", {"regras": [
    {"evento": "ABERTURA", "conservacao": "REFRIGERADO", "prazo": 3, "unidade": "DIAS"}]},
    token=cadastra)
checar("quem cadastra produto GRAVA as validades dele", st == 200, (st, r))
st, r = chamar("GET", f"/etiquetas/validades/{creme}", token=cadastra)
checar("e as lê", st == 200 and len(r) == 1, (st, r))
st, cfg_atual = chamar("GET", "/etiquetas/configuracao", token=token)
st, r = chamar("PUT", "/etiquetas/configuracao", cfg_atual, token=cadastra)
checar("mas NÃO mexe no modelo da etiqueta da loja (403)", st == 403, (st, r))
if (_novo or {}).get("id"):
    chamar("DELETE", f"/usuarios/{_novo['id']}", token=token)
st, lista = chamar("GET", f"/etiquetas/produtos-com-validade?busca=Etq%20molho%20{marca}",
                   token=token)
checar("o molho aparece na lista de produtos com validade",
       st == 200 and any(p["id"] == molho for p in lista), (st, lista))

print("\n2. a sugestão, antes de imprimir")
st, s = chamar("GET", f"/etiquetas/sugestao?id_produto={molho}&evento=PRODUCAO", token=cozinha)
checar("sem conservação, vem a padrão (refrigerado)",
       st == 200 and s.get("conservacao") == "REFRIGERADO" and s.get("origem") == "regra", (st, s))
agora = datetime.now().astimezone()
checar("e vence em 3 dias",
       st == 200 and abs((quando(s["vence_em"]) - agora - timedelta(days=3)).total_seconds()) < 120,
       s.get("vence_em"))
st, s = chamar("GET", f"/etiquetas/sugestao?id_produto={molho}&evento=PRODUCAO"
                      "&conservacao=CONGELADO", token=cozinha)
checar("congelado, 60 dias",
       abs((quando(s["vence_em"]) - agora - timedelta(days=60)).total_seconds()) < 120, s)
st, s = chamar("GET", f"/etiquetas/sugestao?id_produto={sem_regra}&evento=PRODUCAO",
               token=cozinha)
checar("sem regra nenhuma, a sugestão diz que não sabe",
       st == 200 and s.get("vence_em") is None and s.get("origem") is None, s)

print("\n3. a produção nasce com LOTE e VALIDADE")
st, pr = chamar("POST", "/estoque/producoes", {"id_produto": molho, "quantidade": 10,
                                               "id_local": local["id"]}, token=token)
checar("produz 10 do molho", st == 201, (st, pr))
id_prod = (pr or {}).get("id")
checar("o lote é P<id da produção>", pr.get("lote") == f"P{id_prod}", pr.get("lote"))
checar("e vence daqui a 3 dias (a regra padrão)",
       pr.get("validade") == (date.today() + timedelta(days=3)).isoformat(), pr.get("validade"))
with get_cursor() as cur:
    cur.execute("SELECT quantidade, validade FROM estoque_lotes WHERE id_produto = %s AND lote = %s",
                (molho, f"P{id_prod}"))
    lote = dict(cur.fetchone() or {})
checar("o lote existe no estoque com os 10 (o FEFO e o alerta passam a enxergar)",
       float(lote.get("quantidade") or 0) == 10 and lote.get("validade") is not None, lote)
st, pr2 = chamar("POST", "/estoque/producoes", {"id_produto": sem_regra, "quantidade": 2,
                                                "id_local": local["id"]}, token=token)
checar("produto SEM validade continua produzindo sem lote (nada muda para ele)",
       st == 201 and pr2.get("lote") is None, (st, pr2))

print("\n4. etiquetas da produção: o porcionamento")
st, d = chamar("GET", f"/etiquetas/producao/{id_prod}", token=cozinha)
checar("a produção diz o que a etiqueta precisa", st == 200 and d.get("lote") == f"P{id_prod}"
       and d.get("etiquetas") == 0, (st, d))
st, r = chamar("POST", "/etiquetas", {"evento": "PRODUCAO", "id_producao": id_prod,
                                      "copias": 5}, token=cozinha)
checar("5 potes, 5 etiquetas", st == 201 and len(r.get("etiquetas", [])) == 5, (st, r))
etqs = (r or {}).get("etiquetas", [])
checar("cada uma com 2 (10 ÷ 5), o lote da produção e o responsável",
       all(float(e["quantidade"]) == 2 and e["lote"] == f"P{id_prod}"
           and e["responsavel"] == etqs[0]["responsavel"] for e in etqs)
       and etqs[0]["responsavel"], etqs[:1])
checar("códigos de 6, todos diferentes",
       len({e["codigo"] for e in etqs}) == 5 and all(len(e["codigo"]) == 6 for e in etqs))
checar("refrigerado, vencendo 3 dias depois da produção",
       all(e["conservacao"] == "REFRIGERADO" for e in etqs)
       and abs((quando(etqs[0]["vence_em"]) - quando(etqs[0]["feito_em"])).total_seconds()
               - 3 * 86400) < 1, etqs[:1])
st, d = chamar("GET", f"/etiquetas/producao/{id_prod}", token=cozinha)
checar("e a produção passa a contar 5 etiquetas", d.get("etiquetas") == 5, d)

print("\n5. o PDF")
ids = ",".join(str(e["id"]) for e in etqs)
st, tipo, corpo = baixar(f"/etiquetas/pdf?ids={ids}", cozinha)
checar("sai um PDF", st == 200 and tipo == "application/pdf" and corpo[:4] == b"%PDF", (st, tipo))
def paginas(pdf: bytes) -> int:
    # `/Type /Page` sem o `s` de `/Pages`, com o espaço que o reportlab quiser pôr.
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


checar("uma página por etiqueta (rolo 60x40)", paginas(corpo) == 5, paginas(corpo))
st, r = chamar("PUT", "/etiquetas/configuracao", {"tamanho": "A4", "texto_extra": "Botané"},
               token=token)
checar("o modelo muda para folha A4", st == 200 and r.get("tamanho") == "A4", (st, r))
st, tipo, corpo = baixar(f"/etiquetas/pdf?ids={ids}&reimpressao=true", cozinha)
checar("e o PDF A4 sai numa página só", st == 200 and paginas(corpo) == 1, (st, paginas(corpo)))
chamar("PUT", "/etiquetas/configuracao", {"tamanho": "60x40"}, token=token)
st, r = chamar("PUT", "/etiquetas/configuracao", {"tamanho": "60x40"}, token=cozinha)
checar("a cozinha não mexe no modelo (403)", st == 403, st)
st, e0 = chamar("GET", f"/etiquetas/codigo/{etqs[0]['codigo']}", token=cozinha)
checar("a reimpressão conta", e0.get("impressoes") == 2, e0.get("impressoes"))

print("\n6. abertura: a regra e o fabricante")
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "quantidade": 1}, token=cozinha)
aberto = (r or {}).get("etiquetas", [{}])[0]
checar("abre o creme: 3 dias refrigerado",
       st == 201 and aberto.get("evento") == "ABERTURA"
       and abs((quando(aberto["vence_em"]) - quando(aberto["feito_em"])).total_seconds()
               - 3 * 86400) < 1, (st, r))
amanha = date.today() + timedelta(days=1)
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "validade_fabricante": amanha.isoformat()}, token=cozinha)
e = (r or {}).get("etiquetas", [{}])[0]
checar("⚠️ aberto nunca vale mais que o fabricante: vence amanhã, não em 3 dias",
       st == 201 and quando(e["vence_em"]).date() == amanha
       and e.get("validade_fabricante") == amanha.isoformat(), (st, e.get("vence_em")))
ontem = date.today() - timedelta(days=1)
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "validade_fabricante": ontem.isoformat()}, token=cozinha)
checar("embalagem já vencida é recusada", st == 400, (st, r))
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "conservacao": "CONGELADO"}, token=cozinha)
checar("conservação sem regra e sem data informada é recusada, dizendo o que fazer",
       st == 400 and "Informe a validade" in str(r.get("detail")), (st, r))
manual = (datetime.now().astimezone() + timedelta(days=10)).isoformat()
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "conservacao": "CONGELADO", "vence_em": manual},
               token=cozinha)
checar("com a data informada, sai", st == 201, (st, r))
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "responsavel": "Ana da confeitaria"}, token=cozinha)
checar("no tablet de todos, o responsável pode ser outro nome",
       st == 201 and r["etiquetas"][0]["responsavel"] == "Ana da confeitaria", (st, r))
st, r = chamar("POST", "/etiquetas", {"evento": "ABERTURA", "id_produto": creme,
                                      "vence_em": "2020-01-01T10:00:00-03:00"}, token=cozinha)
checar("validade no passado é recusada", st == 400, (st, r))

print("\n7. o QR: consultar e dar baixa")
st, e = chamar("GET", f"/etiquetas/codigo/{etqs[0]['codigo'].lower()}", token=cozinha)
checar("o código acha a etiqueta (sem diferenciar maiúscula)",
       st == 200 and e.get("id") == etqs[0]["id"] and e.get("situacao") == "EM_DIA", (st, e))
checar("e diz se quem leu pode descartar", e.get("pode_descartar") is True, e)
st, e = chamar("GET", "/etiquetas/codigo/ZZZZZZ", token=cozinha)
checar("código que não existe: 404", st == 404, st)
st, r = chamar("POST", f"/etiquetas/{etqs[0]['id']}/usar", {}, token=cozinha)
checar("usei tudo: sai das ativas", st == 200 and r.get("status") == "USADA", (st, r))
st, r = chamar("POST", f"/etiquetas/{etqs[0]['id']}/usar", {}, token=cozinha)
checar("baixar de novo é recusado", st == 400, (st, r))

print("\n8. descartar é PERDA no razão")
st, motivos = chamar("GET", "/estoque/motivos-perda", token=cozinha)
id_motivo = (motivos or [{}])[0].get("id")
st, r = chamar("POST", f"/etiquetas/{etqs[1]['id']}/descartar",
               {"id_motivo_perda": id_motivo, "motivo": "passou do ponto"}, token=cozinha)
checar("descarta o pote 2", st == 200 and r.get("status") == "DESCARTADA"
       and r.get("id_movimento"), (st, r))
with get_cursor() as cur:
    cur.execute("SELECT tipo, quantidade, origem_tipo, id_local FROM estoque_movimentos WHERE id = %s",
                ((r or {}).get("id_movimento"),))
    mov = dict(cur.fetchone() or {})
    cur.execute("SELECT quantidade FROM estoque_lotes WHERE id_produto = %s AND lote = %s",
                (molho, f"P{id_prod}"))
    q_lote = float((cur.fetchone() or {}).get("quantidade") or -1)
checar("a perda é de 2, marcada como vinda da etiqueta",
       mov.get("tipo") == "SAIDA_PERDA" and float(mov.get("quantidade")) == -2
       and mov.get("origem_tipo") == "ETIQUETA", mov)
checar("e sai do LOTE da produção (10 → 8)", q_lote == 8, q_lote)
st, r = chamar("POST", f"/etiquetas/{aberto['id']}/descartar",
               {"id_motivo_perda": id_motivo, "lancar_perda": False}, token=cozinha)
checar("descartar sem lançar perda só tira das ativas",
       st == 200 and r.get("status") == "DESCARTADA" and r.get("id_movimento") is None, (st, r))

print("\n9. descongelar: nova etiqueta, a antiga deixa de valer")
st, r = chamar("POST", "/etiquetas", {"evento": "DESCONGELAMENTO", "id_origem": etqs[2]["id"]},
               token=cozinha)
nova = (r or {}).get("etiquetas", [{}])[0]
checar("nasce a etiqueta do descongelado, com o lote e a quantidade do pote",
       st == 201 and nova.get("lote") == f"P{id_prod}" and float(nova.get("quantidade")) == 2
       and nova.get("id_origem") == etqs[2]["id"], (st, r))
checar("24 horas (a regra do descongelado)",
       abs((quando(nova["vence_em"]) - quando(nova["feito_em"])).total_seconds() - 86400) < 1,
       nova.get("vence_em"))
st, e = chamar("GET", f"/etiquetas/codigo/{etqs[2]['codigo']}", token=cozinha)
checar("a antiga fica SUBSTITUÍDA", e.get("status") == "SUBSTITUIDA", e.get("status"))
st, r = chamar("POST", "/etiquetas", {"evento": "DESCONGELAMENTO", "id_origem": etqs[2]["id"]},
               token=cozinha)
checar("reetiquetar uma etiqueta já baixada é recusado", st == 400, (st, r))
st, r = chamar("POST", "/etiquetas", {"evento": "PRODUCAO", "id_origem": etqs[4]["id"],
                                      "copias": 2}, token=cozinha)
metades = (r or {}).get("etiquetas", [])
checar("dividir o pote em dois: cada metade com 1, e a MESMA validade (não renova)",
       st == 201 and len(metades) == 2 and all(float(m["quantidade"]) == 1 for m in metades)
       and all(m["vence_em"] == etqs[4]["vence_em"] for m in metades), (st, r))
etqs[4] = metades[0] if metades else etqs[4]

print("\n10. o painel e os alertas")
with get_cursor() as cur:
    cur.execute("UPDATE etiquetas SET vence_em = now() - interval '1 hour' WHERE id = %s",
                (etqs[3]["id"],))
st, r = chamar("POST", "/etiquetas", {"evento": "DESCONGELAMENTO", "id_origem": etqs[3]["id"]},
               token=cozinha)
checar("pote vencido não se reetiqueta: descarta", st == 400 and "descartar" in str(r), (st, r))
st, p = chamar("GET", "/etiquetas/painel", token=cozinha)
checar("o painel conta a vencida", st == 200 and p.get("vencidas", 0) >= 1, (st, p))
checar("e o valor descartado nos últimos 30 dias", p.get("valor_descartado_30d", 0) > 0, p)
st, lista = chamar("GET", "/etiquetas?situacao=vencidas&limite=200", token=cozinha)
checar("a lista de vencidas traz o pote", any(x["id"] == etqs[3]["id"] and
                                              x["situacao"] == "VENCIDA" for x in lista or []),
       (st, len(lista or [])))
st, lista = chamar("GET", f"/etiquetas?situacao=baixadas&busca=Etq%20molho%20{marca}", token=cozinha)
checar("as baixadas trazem o usado, o descartado e o substituído",
       {x["status"] for x in lista or []} >= {"USADA", "DESCARTADA", "SUBSTITUIDA"},
       [x["status"] for x in lista or []])
st, r = chamar("GET", "/etiquetas?situacao=inventada", token=cozinha)
checar("situação inventada: 400", st == 400, st)
st, al = chamar("GET", "/alertas", token=token)
checar("o alerta de etiqueta vencida aparece no Início",
       any(a.get("chave") == "etiquetas.vencidas" for a in (al if isinstance(al, list)
                                                            else (al or {}).get("alertas", []))),
       str(al)[:300])

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
