"""Os documentos que não são venda, POR MOTIVO: filtro, quadros, comparativo e relatório.

🔑 **Pedido do dono (26/10/2026):** *"no painel de documentos filtros e quadros por
motivos, onde podemos realizar a impressão e comparativos"*.

O que esta suíte afirma:
1. `GET /vendas?motivo=` filtra: VENDA (só a venda de verdade), QUALQUER, um motivo; e
   recusa motivo desconhecido (422)
2. `GET /vendas/motivos`: o custo que SAIU DO ESTOQUE por motivo, documentos, itens,
   referência; cancelado fica de fora; venda de verdade não entra
3. o comparativo com o período anterior de mesmo tamanho (por motivo e no total)
4. os quadros: produto, pessoa, motivo da perda e documento (com a observação)
5. o filtro por motivo recorta tudo; a perda de Ajustes vem como referência só sem pessoa
6. o relatório `vendas-motivos` bate com a tela; `vendas-documentos` filtra pelo motivo

⚠️ Isola-se pela PESSOA da suíte: a base tem documentos de outras suítes no mesmo dia.

    python tests/smoke_vendas_motivos.py        (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_local  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=120) as r:
            bruto = r.read()
            return r.status, bruto if cru else json.loads(bruto or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def perto(a, b, tol=0.005):
    return a is not None and abs(float(a) - float(b)) <= tol


def numero(texto: str) -> float:
    texto = (texto or "").strip()
    return float(texto.replace(",", ".")) if texto else 0.0


def csv(caminho: str) -> tuple[int, list[list[str]]]:
    st, bruto = chamar("GET", caminho, token=token, cru=True)
    if st != 200 or not isinstance(bruto, bytes):
        return st, []
    return st, [l.split(";") for l in bruto.decode("utf-8-sig").splitlines()]


def linha_com(linhas, trecho: str):
    return next((l for l in linhas if any(trecho in c for c in l)), None)


def coluna(linhas, cabecalho: str, linha) -> str:
    for l in linhas:
        if cabecalho in l and len(l) == len(linha):
            return linha[l.index(cabecalho)]
    return ""


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
marca = str(time.time_ns() // 100)[-6:]
hoje = date.today()
ontem = hoje - timedelta(days=1)
antes = hoje - timedelta(days=2)       # cai no período anterior de [ontem, hoje]
local = garantir_local(chamar, token)

print("0. o cenário: um produto a R$ 4,00 de custo, R$ 10,00 de venda, e uma pessoa")
_st, prod = chamar("POST", "/produtos", {
    "nome": f"MOTIVO PAINEL {marca}", "tipo": "REVENDA", "um_estoque": "UN",
    "preco_venda": 10, "status": "ATIVO"}, token=token)
produto = (prod or {}).get("id")
chamar("PUT", f"/produtos/{produto}", {"id_local_padrao": local["id"]}, token=token)
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": produto, "quantidade": 40, "custo_unitario": 4, "id_local": local["id"],
    "documento": f"NF-MP-{marca}"}, token=token)
checar("40 unidades a R$ 4,00 em estoque", st == 201, r)
_st, pes = chamar("POST", "/fornecedores", {"nome": f"PESSOA MOTIVO PAINEL {marca}",
                                             "fornecedor": False}, token=token)
pessoa = (pes or {}).get("id")
_st, mps = chamar("GET", "/estoque/motivos-perda", token=token)
quebra = next((m for m in mps or [] if m["nome"] == "Quebra"), (mps or [{}])[0])


def lancar(doc, dia, qtd, **cab):
    corpo = {"data": str(dia), "documento": f"{doc}-{marca}", "origem": "MANUAL",
             "id_pessoa": pessoa,
             "itens": [{"id_produto": produto, "quantidade": qtd, "valor_unitario": 10}],
             **cab}
    st, r = chamar("POST", "/vendas/importar", {"vendas": [corpo]}, token=token)
    checar(f"lança {doc}", st == 201, (st, r))
    st, l = chamar("GET", f"/vendas?busca={doc}-{marca}", token=token)
    return (l or [{}])[0].get("id")


lancar("MPB", hoje, 2, motivo="BRINDE", motivo_observacao="aniversário da Ana")
lancar("MPP", hoje, 1, motivo="PERDA", id_motivo_perda=quebra.get("id"))
lancar("MPO", ontem, 3, motivo="OUTROS", motivo_observacao="festa da equipe")
lancar("MPC", hoje, 1, motivo="CONSUMO_INTERNO")
lancar("MPA", antes, 1, motivo="BRINDE")                 # o período anterior
cancelado = lancar("MPX", hoje, 5, motivo="PREMIO")
lancar("MPV", hoje, 1)                                    # venda de verdade
st, r = chamar("DELETE", f"/vendas/{cancelado}", token=token)
checar("o prêmio é cancelado", st == 200, (st, r))

print("\n1. o filtro de motivo na lista de documentos")


def docs(q):
    st, l = chamar("GET", f"/vendas?busca=-{marca}&limite=50&{q}", token=token)
    return st, sorted(x["documento"].split("-")[0] for x in (l or []))


st, d = docs("motivo=VENDA")
checar("VENDA traz só a venda de verdade", d == ["MPV"], (st, d))
st, d = docs("motivo=QUALQUER")
checar("QUALQUER traz todo documento com motivo (o cancelado também, marcado)",
       d == ["MPA", "MPB", "MPC", "MPO", "MPP", "MPX"], (st, d))
st, d = docs("motivo=BRINDE")
checar("BRINDE traz os dois brindes", d == ["MPA", "MPB"], (st, d))
st, d = docs(f"motivo=BRINDE&inicio={ontem}&fim={hoje}")
checar("e com o período, só o de dentro", d == ["MPB"], (st, d))
st, r = chamar("GET", "/vendas?motivo=XYZ", token=token)
checar("motivo desconhecido: 422", st == 422, (st, r))

print("\n2. o painel por motivo: o custo que saiu do estoque")
q = f"inicio={ontem}&fim={hoje}&id_pessoa={pessoa}&agrupar=dia"
st, p = chamar("GET", f"/vendas/motivos?{q}", token=token)
checar("responde", st == 200, (st, p))
p = p or {}
t = p.get("totais", {})
checar("4 documentos (cancelado e venda fora, anterior fora)", t.get("documentos") == 4, t)
checar("custo do estoque: 7 unidades × R$ 4 = R$ 28", perto(t.get("custo"), 28), t)
checar("itens 7 e referência R$ 70 (fora da receita)",
       perto(t.get("itens"), 7) and perto(t.get("referencia"), 70), t)
pm = {l["motivo"]: l for l in p.get("por_motivo", [])}
checar("brinde R$ 8, perda R$ 4, outros R$ 12, consumo interno R$ 4, prêmio zero",
       perto(pm["BRINDE"]["custo"], 8) and perto(pm["PERDA"]["custo"], 4)
       and perto(pm["OUTROS"]["custo"], 12) and perto(pm["CONSUMO_INTERNO"]["custo"], 4)
       and perto(pm["PREMIO"]["custo"], 0), pm)

print("\n3. o comparativo com o período anterior")
c = p.get("comparacao", {})
checar("o anterior é o de mesmo tamanho logo antes",
       c.get("inicio") == str(hoje - timedelta(days=3)) and c.get("fim") == str(antes), c)
checar("brinde: R$ 4 antes, +100%",
       perto(pm["BRINDE"]["anterior"]["custo"], 4) and pm["BRINDE"]["pct_custo"] == 100.0,
       pm["BRINDE"])
checar("total: R$ 4 antes, +600%", perto(c.get("custo"), 4) and c.get("pct_custo") == 600.0, c)
checar("motivo sem base para comparar vem nulo", pm["OUTROS"]["pct_custo"] is None, pm["OUTROS"])

print("\n4. os quadros")
serie = {s["periodo"]: s for s in p.get("serie", [])}
checar("a evolução por dia: ontem R$ 12 (outros), hoje R$ 16",
       perto(serie.get(str(ontem), {}).get("custo"), 12)
       and perto(serie.get(str(hoje), {}).get("custo"), 16)
       and perto(serie.get(str(hoje), {}).get("por_motivo", {}).get("BRINDE"), 8), serie)
prods = p.get("produtos", [])
checar("produto: 7 unidades, R$ 28",
       len(prods) == 1 and perto(prods[0]["quantidade"], 7) and perto(prods[0]["custo"], 28),
       prods)
pes_ = p.get("pessoas", [])
checar("pessoa: a da suíte, 4 documentos", len(pes_) == 1 and pes_[0]["id_pessoa"] == pessoa
       and pes_[0]["documentos"] == 4, pes_)
checar("motivo da perda: Quebra, R$ 4",
       [(x["nome"], round(x["custo"], 2)) for x in p.get("motivos_perda", [])]
       == [(quebra.get("nome"), 4.0)], p.get("motivos_perda"))
lista = p.get("documentos", [])
outros = next((x for x in lista if x["documento"].startswith("MPO")), {})
checar("os documentos vêm com a observação",
       len(lista) == 4 and outros.get("motivo_observacao") == "festa da equipe"
       and outros.get("rotulo") == "Outros", lista)
checar("com pessoa, a perda de Ajustes não vem como referência", p.get("perdas_ajuste") is None)

print("\n5. o filtro por motivo")
st, f = chamar("GET", f"/vendas/motivos?{q}&motivos=BRINDE&motivos=PERDA", token=token)
checar("brinde + perda: R$ 12 em 2 documentos, só as duas linhas",
       perto(f["totais"]["custo"], 12) and f["totais"]["documentos"] == 2
       and [l["motivo"] for l in f["por_motivo"]] == ["PERDA", "BRINDE"], f.get("totais"))
st, r = chamar("GET", f"/vendas/motivos?{q}&motivos=XYZ", token=token)
checar("motivo desconhecido: 422", st == 422, (st, r))
st, r = chamar("GET", f"/vendas/motivos?inicio={hoje}&fim={ontem}", token=token)
checar("fim antes do início: 400", st == 400, (st, r))
st, g = chamar("GET", f"/vendas/motivos?inicio={ontem}&fim={hoje}", token=token)
checar("sem pessoa, a perda de Ajustes vem como referência",
       st == 200 and isinstance(g.get("perdas_ajuste"), dict)
       and "custo" in g["perdas_ajuste"], g.get("perdas_ajuste"))
st, g = chamar("GET", f"/vendas/motivos?inicio={ontem}&fim={hoje}&motivos=BRINDE",
               token=token)
checar("e sem a perda entre os motivos, não vem", st == 200 and g.get("perdas_ajuste") is None)

print("\n6. os relatórios")
st, linhas = csv(f"/exportar/vendas-motivos.csv?inicio={ontem}&fim={hoje}"
                 f"&pessoas={pessoa}&agrupar=dia")
checar("vendas-motivos sai", st == 200 and linhas, st)
res = linha_com(linhas, "Custo que saiu do estoque")
checar("e o custo bate com a tela (R$ 28)", res and perto(numero(res[1]), 28), res)
brinde = linha_com(linhas, "MPB-")
checar("o brinde aparece com a observação",
       brinde and coluna(linhas, "Observação", brinde) == "aniversário da Ana", brinde)
checar("com os quadros por motivo, evolução, produto e pessoa",
       all(linha_com(linhas, x) for x in ("Por motivo", "Evolução por dia",
                                         "O que saiu do estoque, por produto", "Por pessoa")),
       linhas[-12:])
st, pdf = chamar("GET", f"/exportar/vendas-motivos.pdf?inicio={ontem}&fim={hoje}"
                        f"&pessoas={pessoa}", token=token, cru=True)
checar("e o PDF sai", st == 200 and pdf[:5] == b"%PDF-", st)
st, linhas = csv(f"/exportar/vendas-motivos.csv?inicio={ontem}&fim={hoje}"
                 f"&pessoas={pessoa}&motivos_venda=BRINDE")
res = linha_com(linhas, "Custo que saiu do estoque")
checar("filtrado em brinde: R$ 8, sem o documento de outros",
       res and perto(numero(res[1]), 8) and not linha_com(linhas, "MPO-"), res)
st, linhas = csv(f"/exportar/vendas-documentos.csv?inicio={ontem}&fim={hoje}"
                 f"&motivo_venda=VENDA")
checar("vendas-documentos filtrado em VENDA: a venda sim, o brinde não",
       st == 200 and linha_com(linhas, f"MPV-{marca}") and not linha_com(linhas, f"MPB-{marca}"),
       st)
st, linhas = csv(f"/exportar/vendas-documentos.csv?inicio={ontem}&fim={hoje}"
                 f"&motivo_venda=BRINDE&motivo_venda=OUTROS")
checar("e em brinde + outros: os dois, sem a venda",
       linha_com(linhas, f"MPB-{marca}") and linha_com(linhas, f"MPO-{marca}")
       and not linha_com(linhas, f"MPV-{marca}"), st)

print("\n7. limpeza: os documentos da suíte cancelados")
_st, todos = chamar("GET", f"/vendas?busca=-{marca}&limite=50", token=token)
for v in todos or []:
    if not v["cancelada"]:
        chamar("DELETE", f"/vendas/{v['id']}", token=token)
_st, todos = chamar("GET", f"/vendas?busca=-{marca}&limite=50", token=token)
checar("tudo cancelado", all(v["cancelada"] for v in todos or []), todos)
chamar("DELETE", f"/produtos/{produto}", token=token)

print(f"\n{ok} checagens ok, {len(falhas)} falharam")
sys.exit(1 if falhas else 0)
