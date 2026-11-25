"""Os filtros da janela de impressão chegam ao relatório, e o "O que listar" do Estudo de vendas.

O que este arquivo cobra:

1. todo filtro declarado em `FILTROS` (fora os de período, que viajam como início/fim) é
   parâmetro da rota de exportação — senão a janela mostra a escolha e o arquivo sai com tudo
   (seis ficaram assim de 1.3.16 a 1.3.24)
2. o "O que listar" do Estudo de vendas (pedido do dono, 25/11/2026): só as formas de
   pagamento, a escolha vira o quadro da frente, os totais saem quando desmarcados, sem escolha
   sai tudo como antes
3. pela rota: a escolha chega (o título diz o quadro), e a situação das contas a pagar filtra

    python tests/smoke_exportacao_filtros.py      (API de pé na 9200)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=180) as r:
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


from database import get_cursor  # noqa: E402
from services import exportacao_catalogo as ec  # noqa: E402

print("1. todo filtro declarado é parâmetro da rota")
raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(raiz, "routers", "exportacoes.py"), encoding="utf-8") as arq:
    fonte = arq.read()
bloco = fonte[fonte.index("self.como_dict = {"):fonte.index("def preenchidos")]
na_rota = set(re.findall(r'"(\w+)":', bloco))
faltam = sorted(k for k, d in ec.FILTROS.items() if d.get("tipo") != "periodo" and k not in na_rota)
checar("nenhum filtro esquecido na rota", not faltam, faltam)

print("2. o que listar no Estudo de vendas")
hoje = date.today()
inicio = hoje - timedelta(days=30)
with get_cursor() as cur:
    tudo = ec._vendas(cur, 1, {"inicio": inicio, "fim": hoje})
    so_formas = ec._vendas(cur, 1, {"inicio": inicio, "fim": hoje, "secoes_vendas": ["pagamento"]})
    hora_e_totais = ec._vendas(cur, 1, {"inicio": inicio, "fim": hoje,
                                        "secoes_vendas": ["resumo", "hora", "categoria"]})
    inexistente = ec._vendas(cur, 1, {"inicio": inicio, "fim": hoje, "secoes_vendas": ["xyz"]})
titulos_tudo = [a[2] for a in tudo.anexos]
checar("sem escolha sai tudo, como antes: produtos na frente e os quadros atrás",
       "Por categoria" in titulos_tudo and "Por hora do cupom" in titulos_tudo
       and any(c[0] == "produto" for c in tudo.colunas), titulos_tudo)
tem_formas = "Por forma de pagamento" in titulos_tudo
if tem_formas:
    checar("só as formas: o quadro da frente são as formas, sem anexos",
           so_formas.titulo.endswith("Por forma de pagamento") and not so_formas.anexos
           and any(c[0] == "forma" for c in so_formas.colunas), (so_formas.titulo, so_formas.anexos))
    checar("só as formas: sem os totais (no máximo o custo das taxas)",
           all(x[0] == "Custo estimado das taxas" for x in so_formas.resumo), so_formas.resumo)
else:
    print("  (sem finalizadoras nos últimos 30 dias nesta base: o quadro das formas não existe)")
    checar("formas escolhidas sem formas no recorte: cai nos produtos, nunca vazio",
           any(c[0] == "produto" for c in so_formas.colunas), so_formas.colunas)
checar("hora + categoria + totais: a hora na frente, a categoria atrás, os totais ficam",
       hora_e_totais.titulo.endswith("Por hora do cupom")
       and [a[2] for a in hora_e_totais.anexos] == ["Por categoria"]
       and any(x[0] == "Cupons" for x in hora_e_totais.resumo),
       (hora_e_totais.titulo, [a[2] for a in hora_e_totais.anexos]))
checar("escolha que não existe: cai nos produtos",
       any(c[0] == "produto" for c in inexistente.colunas), inexistente.colunas)
opcoes = [o["valor"] for o in ec.FILTROS["secoes_vendas"]["opcoes"](None, 1)]
checar("as opções da janela incluem formas de pagamento e totais",
       "pagamento" in opcoes and "resumo" in opcoes, opcoes)
checar("o relatório de vendas oferece o filtro", "secoes_vendas" in ec.RELATORIOS["vendas"].filtros)

print("3. pela rota")
st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
q = urllib.parse.urlencode({"inicio": inicio, "fim": hoje, "secoes_vendas": "semana"})
s, d = chamar("GET", f"/exportar/vendas/dados?{q}", token=token)
checar("a escolha chega ao relatório (o título diz o quadro)",
       s == 200 and d["titulo"].endswith("Por dia da semana"), (s, (d or {}).get("titulo")))
# Uma conta cancelada do próprio teste: sem o filtro, o relatório traz só as não canceladas.
with get_cursor() as cur:
    cur.execute("SELECT id FROM fornecedores WHERE ativo ORDER BY id LIMIT 1")
    pessoa = cur.fetchone()["id"]
s, c = chamar("POST", "/contas-pagar", {"id_pessoa": pessoa, "descricao": "Filtro do relatório",
                                        "competencia": str(hoje), "vencimento": str(hoje),
                                        "valor": 1}, token=token)
try:
    chamar("POST", "/contas-pagar/cancelar", {"ids": [c["id"]]}, token=token)
    base_q = {"inicio": hoje - timedelta(days=1), "fim": hoje + timedelta(days=1)}
    s, d = chamar("GET", f"/exportar/contas-pagar/dados?{urllib.parse.urlencode({**base_q, 'situacao_pagar': 'CANCELADO'})}",
                  token=token)
    linhas = (d or {}).get("linhas", [])
    checar("a situação das contas a pagar filtra (só canceladas, e a do teste está lá)",
           s == 200 and linhas and all(any("Cancelado" in str(v) for v in l) for l in linhas)
           and any("Filtro do relatório" in str(l) for l in linhas), (s, linhas[:2]))
finally:
    with get_cursor() as cur:
        cur.execute("DELETE FROM contas_pagar WHERE id = %s", (c["id"],))

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
