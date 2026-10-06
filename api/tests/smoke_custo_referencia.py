"""A conferência do custo de referência: achar o que está furado e corrigir.

    python tests/smoke_custo_referencia.py        (API de pé na 9200)

🔑 **Pedido do dono (05/10/2026)**: o ANA & GRAZI VINHO ROSÉ, vendido a R$ 109,00,
aparecia custando R$ 264,00 — o preço da CAIXA de seis —, enquanto o razão do
mesmo produto saía a R$ 44,00 a garrafa. O custo de referência não tem tela de
edição: o número ficava errado até a primeira nota chegar.

⚠️ **A referência vai direto no cadastro**, como nas outras suítes de custo: o
caminho que a grava de verdade é a carga do Omie, e simular o Omie aqui deixaria
rastro na credencial da loja.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
from comum import garantir_cozinha, garantir_local  # noqa: E402

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
HOJE = date.today().isoformat()

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
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
marca = str(time.time_ns() // 100)[-6:]
local = garantir_local(chamar, token)
produtos: list[int] = []


def criar(sufixo: str, **campos) -> int:
    corpo = {"codigo": f"REF{sufixo}-{marca}", "nome": f"REFERENCIA {sufixo} {marca}",
             "tipo": "REVENDA", "um_estoque": "UN", "controla_estoque": True,
             "status": "ATIVO", "id_local_padrao": local["id"], **campos}
    st, p = chamar("POST", "/produtos", corpo, token=token)
    if st not in (200, 201):
        print("não criou o produto:", st, p)
        sys.exit(1)
    produtos.append(p["id"])
    return p["id"]


def referencia(id_produto: int, valor) -> None:
    with get_cursor() as cur:
        cur.execute(
            """UPDATE produtos SET custo_referencia = %s, custo_referencia_em = now(),
                                   custo_referencia_origem = 'OMIE' WHERE id = %s""",
            (valor, id_produto),
        )


def vender(id_produto: int, doc: str, preco: float):
    return chamar("POST", "/vendas/importar", {"vendas": [{
        "data": HOJE, "documento": f"REF-{marca}-{doc}", "origem": "MANUAL",
        "itens": [{"id_produto": id_produto, "quantidade": 1, "valor_unitario": preco}]}]},
        token=token)


def custo_congelado(id_produto: int) -> list[tuple[float, str]]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT vi.custo_ficha_unitario, vi.origem_custo FROM venda_itens vi
                WHERE vi.id_produto = %s ORDER BY vi.id""",
            (id_produto,),
        )
        return [(float(r["custo_ficha_unitario"] or 0), r["origem_custo"])
                for r in cur.fetchall()]


def previa() -> tuple[dict, dict]:
    st, p = chamar("GET", "/ajustes/custo-referencia/previa", token=token)
    return p, {l["id_produto"]: l for l in (p or {}).get("linhas", [])}


try:
    print("1. o caso do dono: a referência vira o preço da caixa depois da primeira venda")
    vinho = criar("A", um_compra="CX", fator_compra=6, preco_venda=109)
    referencia(vinho, 44)
    st, r = vender(vinho, "1", 109)
    checar("a garrafa é vendida sem saldo, a R$ 44,00 de referência", st in (200, 201), (st, r))
    referencia(vinho, 264)
    st, r = vender(vinho, "2", 109)
    checar("e é vendida de novo depois de a referência virar R$ 264,00", st in (200, 201), (st, r))
    st, c = chamar("GET", f"/produtos/{vinho}/custo", token=token)
    checar("o custo de hoje sai da referência: R$ 264,00",
           perto(c.get("atual"), 264) and c.get("origem") == "referencia", c)
    congelados = custo_congelado(vinho)
    checar("a segunda venda congelou R$ 264,00, vindo da referência",
           len(congelados) == 2 and perto(congelados[1][0], 264)
           and congelados[1][1] == "referencia", congelados)

    p, linhas = previa()
    x = linhas.get(vinho)
    checar("a conferência acha o produto", x is not None, p.get("suspeitos"))
    checar("mostra a referência e o custo do razão",
           x and perto(x["referencia"], 264) and perto(x["razao"], 44), x)
    checar("sugere R$ 44,00", x and perto(x["sugerido"], 44), x)
    checar("com confiança alta, porque a razão entre os dois é a caixa de 6",
           x and x["confianca"] == "alta" and "CX" in x["motivo"], x)

    print("\n2. sem razão: o preço de venda é a testemunha, e a sugestão é palpite")
    sem_razao = criar("B", um_compra="CX", fator_compra=6, preco_venda=109)
    referencia(sem_razao, 264)
    sem_fator = criar("C", preco_venda=10)
    referencia(sem_fator, 30)
    p, linhas = previa()
    x = linhas.get(sem_razao)
    checar("custo acima do preço entra na lista", x is not None)
    checar("dividido pela caixa dá R$ 44,00", x and perto(x["sugerido"], 44), x)
    checar("mas vem para CONFERIR, não marcado", x and x["confianca"] == "conferir", x)
    y = linhas.get(sem_fator)
    checar("sem embalagem que explique, entra sem sugestão",
           y is not None and y["sugerido"] is None, y)

    print("\n3. o que NÃO é suspeito")
    normal = criar("D", um_compra="CX", fator_compra=6, preco_venda=109)
    referencia(normal, 50)
    com_saldo = criar("E", um_compra="CX", fator_compra=6, preco_venda=109)
    referencia(com_saldo, 264)
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": com_saldo, "quantidade": 2, "custo_unitario": 44,
        "id_local": local["id"]}, token=token)
    checar("um produto recebe compra de verdade", st == 201, (st, r))
    p, linhas = previa()
    checar("referência abaixo do preço e sem razão: fora da lista", normal not in linhas)
    checar("quem tem médio de verdade não é custeado pela referência: fora da lista",
           com_saldo not in linhas)
    checar("os de confiança alta vêm primeiro",
           [l["confianca"] for l in p["linhas"]]
           == sorted((l["confianca"] for l in p["linhas"]), key=lambda c: c != "alta"))

    print("\n4. corrigir grava o que a pessoa confirmou")
    st, r = chamar("POST", "/ajustes/custo-referencia",
                   {"itens": [{"id_produto": vinho, "custo": 44},
                              {"id_produto": sem_fator, "custo": 6.5}]}, token=token)
    checar("a correção é aceita", st == 200 and r.get("corrigidos") == 2, (st, r))
    st, c = chamar("GET", f"/produtos/{vinho}/custo", token=token)
    checar("o custo do vinho passa a R$ 44,00", perto(c.get("atual"), 44), c)
    st, d = chamar("GET", f"/produtos/{vinho}", token=token)
    checar("a origem diz que foi correção", d.get("custo_referencia_origem") == "CORRECAO", d)
    congelados = custo_congelado(vinho)
    checar("a venda que congelou R$ 264,00 é recalculada para R$ 44,00",
           perto(congelados[1][0], 44), congelados)
    checar("e a resposta conta os itens de venda recalculados",
           r.get("vendas_recalculadas", 0) >= 1, r)
    with get_cursor() as cur:
        cur.execute(
            """SELECT antes, depois FROM auditoria
                WHERE entidade = 'produto' AND id_entidade::text = %s
                  AND acao = 'custo_referencia_corrigido'""",
            (str(vinho),),
        )
        rastro = cur.fetchone()
    checar("a auditoria guarda o antes (264) e o depois (44)",
           rastro and perto(rastro["antes"]["custo_referencia"], 264)
           and perto(rastro["depois"]["custo_referencia"], 44), rastro)
    p, linhas = previa()
    checar("os corrigidos saem da conferência", vinho not in linhas and sem_fator not in linhas)
    checar("o que não foi marcado continua lá", sem_razao in linhas)
    st, r = chamar("POST", "/ajustes/custo-referencia",
                   {"itens": [{"id_produto": vinho, "custo": 44}]}, token=token)
    checar("repetir a mesma correção não muda nada", st == 200 and r.get("corrigidos") == 0, r)

    print("\n5. as recusas")
    st, r = chamar("POST", "/ajustes/custo-referencia",
                   {"itens": [{"id_produto": vinho, "custo": 0}]}, token=token)
    checar("custo zero é recusado", st == 422, st)
    st, r = chamar("POST", "/ajustes/custo-referencia", {"itens": []}, token=token)
    checar("lista vazia é recusada", st == 422, st)
    st, r = chamar("POST", "/ajustes/custo-referencia",
                   {"itens": [{"id_produto": 99999999, "custo": 5}]}, token=token)
    checar("produto que não existe devolve 404", st == 404, st)
    cozinha = garantir_cozinha(chamar, token)
    st, _ = chamar("GET", "/ajustes/custo-referencia/previa", token=cozinha)
    checar("a cozinha não vê a conferência", st == 403, st)
    st, _ = chamar("POST", "/ajustes/custo-referencia",
                   {"itens": [{"id_produto": sem_razao, "custo": 1}]}, token=cozinha)
    checar("nem corrige", st == 403, st)
    st, c = chamar("GET", f"/produtos/{sem_razao}/custo", token=token)
    checar("e o custo que ela tentou gravar NÃO entrou", perto(c.get("atual"), 264), c)

finally:
    print("\n6. limpeza")
    st, vendas = chamar("GET", f"/vendas?busca=REF-{marca}", token=token)
    for v in (vendas or []):
        if not v.get("cancelada"):
            chamar("DELETE", f"/vendas/{v['id']}", token=token)
    for id_produto in produtos:
        st, movs = chamar("GET", f"/estoque/movimentos?id_produto={id_produto}&limite=50",
                          token=token)
        for m in (movs or []):
            if m.get("tipo") == "ENTRADA_MANUAL" and not m.get("estornado"):
                chamar("POST", f"/estoque/movimentos/{m['id']}/estornar",
                       {"motivo": "limpeza da suíte"}, token=token)
        chamar("DELETE", f"/produtos/{id_produto}", token=token)
    st, sobrou = chamar("GET", f"/vendas?busca=REF-{marca}", token=token)
    checar("as vendas da suíte ficam canceladas",
           all(v.get("cancelada") for v in (sobrou or [])), sobrou)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
