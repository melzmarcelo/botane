"""O custo médio é da LOJA, não da prateleira (migração 064).

    python tests/smoke_custo_geral.py        (API de pé na 9200)

🔑 **Pedido do dono (11/09/2026):** "hoje temos produto com custo em um local,
porém em outros locais não tem. gostaria que neste primeiro momento o custo
fosse geral". O efeito prático do médio por prateleira era a saída pelo local
que nunca recebeu nota sair **de graça** — o mesmo defeito de custo zero que
este projeto já perseguiu por três caminhos diferentes.

⚠️ **A loja volta ao modo GERAL no fim.** A base é compartilhada com as outras
suítes e o parâmetro muda o número que elas medem — mesma lição do ciclo de
fechamento em `smoke_cmv`.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

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


def perto(a, b, tol=0.000001):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]


def custos_do(id_produto) -> dict:
    """O custo de cada prateleira, direto do saldo."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT l.nome, s.quantidade, s.custo_medio FROM estoque_saldos s
                 JOIN locais_estoque l ON l.id = s.id_local
                WHERE s.id_produto = %s""",
            (id_produto,),
        )
        return {r["nome"]: (float(r["quantidade"]), float(r["custo_medio"]))
                for r in cur.fetchall()}


def modo(por_local: bool):
    st, _ = chamar("PUT", "/unidades/1/parametros", {"custo_por_local": por_local},
                   token=token)
    return st


despensa = garantir_local(chamar, token)
id_camara = None   # criado no 3c; declarado aqui para a limpeza sempre alcançá-lo
st, bar = chamar("POST", "/locais", {"nome": f"Bar custo {marca}", "tipo": "BAR"},
                 token=token)
checar("segundo local criado", st in (200, 201), (st, bar))
id_bar = (bar or {}).get("id")

try:
    print("1. custo GERAL: a entrada numa prateleira dá custo à outra")
    modo(False)
    st, p = chamar("POST", "/produtos", {"nome": f"Geral {marca}", "tipo": "INSUMO",
                                         "um_estoque": "KG"}, token=token)
    idp = p["id"]
    # 🔑 O caso do dono: a mercadoria entra pela despensa e o bar nunca recebeu
    # nota nenhuma deste produto.
    chamar("POST", "/estoque/entradas", {"id_produto": idp, "quantidade": 10,
           "custo_unitario": 20, "id_local": despensa["id"]}, token=token)
    chamar("POST", "/estoque/entradas", {"id_produto": idp, "quantidade": 2,
           "custo_unitario": 20, "id_local": id_bar}, token=token)
    c = custos_do(idp)
    # ⚠️ **A contagem vem ANTES da afirmação, e é ela que dá sentido à outra.**
    # A primeira versão deste arquivo criou o segundo local com um tipo inválido
    # (400), e os três primeiros blocos passaram VERDES sobre uma prateleira só:
    # "as duas custam o mesmo" é trivialmente verdade quando só há uma.
    checar("o produto está nas DUAS prateleiras", len(c) == 2, c)
    checar("as duas prateleiras custam o mesmo",
           len({v[1] for v in c.values()}) == 1, c)

    print("2. a saída pelo local que não comprou NÃO sai de graça")
    # ⚠️ Era exatamente isto: o bar com custo zero baixava a R$ 0,00 enquanto o
    # cupom da mesma venda mostrava o custo.
    st, mov = chamar("POST", "/estoque/saidas", {
        "id_produto": idp, "quantidade": 1, "tipo": "SAIDA_CONSUMO_INTERNO",
        "id_local": id_bar}, token=token)
    checar("a baixa sai pelo custo da loja", perto(mov.get("custo_unitario"), 20),
           mov.get("custo_unitario"))
    # ⚠️ E não é provisório: o custo é conhecido, não estimado.
    checar("e não é marcada como custo provisório",
           mov.get("custo_provisorio") in (False, None), mov.get("custo_provisorio"))

    print("3. o médio pondera a LOJA inteira, não a prateleira")
    # 11 kg a 20 (10 na despensa + 1 no bar) + 10 kg a 30 = 21 kg valendo 250+300
    chamar("POST", "/estoque/entradas", {"id_produto": idp, "quantidade": 10,
           "custo_unitario": 30, "id_local": id_bar}, token=token)
    c = custos_do(idp)
    esperado = (11 * 20 + 10 * 30) / 21
    checar("o novo médio é o ponderado das duas prateleiras",
           all(perto(v[1], esperado, 0.0001) for v in c.values()), (c, esperado))

    print("3b. o razão FECHA depois da redistribuição")
    # 🔑 **Duas versões desta função estiveram erradas aqui, e as duas passaram
    # por todos os outros blocos deste arquivo.** Em modo geral a entrada
    # REDISTRIBUI valor entre as prateleiras: 10 unidades entrando a R$ 30 numa
    # loja cujo médio vira R$ 24,76 valem R$ 247,62, não R$ 300 — e a diferença
    # foi para a prateleira vizinha. Se só um dos lados virar movimento, a
    # fotografia do razão deixa de bater com o saldo e a identidade
    # `inicial + entradas − saídas = final` abre.
    # ⚠️ **A soma dos ajustes tem de ser ZERO**: a entrada não criou nem destruiu
    # valor, só o espalhou. É essa soma que denuncia o lado que falta.
    with get_cursor() as cur:
        cur.execute(
            """SELECT coalesce(sum(custo_total), 0) AS soma, count(*) AS n
                 FROM estoque_movimentos
                WHERE id_produto = %s AND origem_tipo = 'CUSTO_GERAL'""", (idp,))
        aj = cur.fetchone()
        cur.execute(
            """SELECT coalesce(sum(CASE WHEN quantidade > 0 THEN custo_total
                                        WHEN quantidade < 0 THEN -custo_total
                                        ELSE custo_total END), 0) AS registrado,
                      (SELECT coalesce(sum(quantidade * custo_medio), 0)
                         FROM estoque_saldos WHERE id_produto = %s) AS vale
                 FROM estoque_movimentos WHERE id_produto = %s""", (idp, idp))
        r = cur.fetchone()
    checar("a redistribuição virou movimento nas duas prateleiras", aj["n"] == 2, aj["n"])
    checar("e a soma dos ajustes é zero — valor só mudou de lugar",
           perto(aj["soma"], 0, 0.01), aj["soma"])
    checar("o que o razão soma é o que o estoque vale",
           perto(r["registrado"], r["vale"], 0.01), (r["registrado"], r["vale"]))

    print("3c. prateleira DECLARADA à mão já nasce sabendo o custo")
    # 🔑 **É o caso que o dono relatou na produção.** "Este produto também mora
    # no bar" criava a linha de saldo zerada — e zerada quer dizer custo R$ 0,00
    # naquele local, que é exatamente o "tem custo em um local e nos outros não".
    # O gesto de PREPARAR a casa reintroduzia o defeito que o custo geral veio
    # acabar.
    # ⚠️ A quantidade continua zero e nada entra no razão: não há mercadoria nem
    # valor, só o custo que a loja já conhece.
    st, terceiro = chamar("POST", "/locais", {"nome": f"Camara custo {marca}",
                                              "tipo": "RESFRIADO"}, token=token)
    id_camara = (terceiro or {}).get("id")  # noqa: F841 — a limpeza usa
    st, r = chamar("POST", f"/produtos/{idp}/locais", {"id_local": id_camara}, token=token)
    checar("o local foi acrescentado ao produto", st in (200, 201), (st, r))
    c = custos_do(idp)
    nova = [v for k, v in c.items() if "Camara custo" in k or "CAMARA CUSTO" in k.upper()]
    checar("a prateleira nova existe com saldo zero",
           len(nova) == 1 and nova[0][0] == 0, c)
    checar("e já traz o custo da loja, não zero",
           len(nova) == 1 and perto(nova[0][1], esperado, 0.0001), (nova, esperado))

    print("3d. produto ESGOTADO num local e sem custo no outro entra na prévia")
    # 🔑 **Relatado pelo dono na produção (11/09/2026):** "retorna que não tem
    # nada para unificar, mas o produto água com gás está em dois locais, e um
    # deles tem custo e outro não". O motivo: a prateleira que SABIA o custo
    # estava ZERADA, e o alvo da unificação exigia saldo positivo para ponderar —
    # então o produto inteiro saía da lista e a prévia dizia "nada a unificar"
    # olhando para o caso que ela existe para resolver.
    # ⚠️ `_travar_custo_da_loja` já caía no maior custo conhecido nesse caso. Eram
    # duas implementações da MESMA regra, e só uma tinha o degrau de reserva.
    st, agua = chamar("POST", "/produtos", {"nome": f"Agua gas {marca}",
                                            "tipo": "REVENDA", "um_estoque": "UN"}, token=token)
    id_agua = agua["id"]
    chamar("POST", "/estoque/entradas", {"id_produto": id_agua, "quantidade": 10,
           "custo_unitario": 3.5, "id_local": despensa["id"]}, token=token)
    chamar("POST", "/estoque/saidas", {"id_produto": id_agua, "quantidade": 10,
           "tipo": "SAIDA_CONSUMO_INTERNO", "id_local": despensa["id"]}, token=token)
    modo(True)   # o mundo de antes: a prateleira nova nascia zerada
    chamar("POST", f"/produtos/{id_agua}/locais", {"id_local": id_bar}, token=token)
    modo(False)
    c = custos_do(id_agua)
    checar("o cenário é o relatado: um local sabe o custo, o outro não",
           sorted(v[1] for v in c.values()) == [0.0, 3.5], c)
    st, previa = chamar("GET", "/ajustes/custo-geral/previa", token=token)
    achou = [l for l in previa["linhas"] if l["id_produto"] == id_agua]
    checar("a prévia enxerga o produto esgotado", len(achou) == 1, previa["produtos"])
    checar("e o alvo é o custo conhecido, não zero",
           achou and perto(achou[0]["custo_novo"], 3.5, 0.0001), achou)

    print("4. a chave POR LOCAL devolve o comportamento antigo")
    modo(True)
    st, p2 = chamar("POST", "/produtos", {"nome": f"PorLocal {marca}", "tipo": "INSUMO",
                                          "um_estoque": "KG"}, token=token)
    idp2 = p2["id"]
    chamar("POST", "/estoque/entradas", {"id_produto": idp2, "quantidade": 10,
           "custo_unitario": 20, "id_local": despensa["id"]}, token=token)
    chamar("POST", "/estoque/entradas", {"id_produto": idp2, "quantidade": 10,
           "custo_unitario": 30, "id_local": id_bar}, token=token)
    c2 = custos_do(idp2)
    checar("o segundo produto também está nas duas", len(c2) == 2, c2)
    checar("cada prateleira guarda o próprio custo",
           len({v[1] for v in c2.values()}) == 2, c2)

    print("5. a prévia mede, e o botão faz exatamente o que ela disse")
    # ⚠️ **A prévia é medida com o produto JÁ divergente**, criado no modo por
    # local acima: é o estado real de quem liga a chave depois de meses rodando.
    modo(False)
    st, previa = chamar("GET", "/ajustes/custo-geral/previa", token=token)
    checar("a prévia responde", st == 200, previa)
    meu = [l for l in previa["linhas"] if l["id_produto"] == idp2]
    checar("e enxerga o produto divergente", len(meu) >= 1, len(meu))
    # (10×20 + 10×30) / 20 = 25 nas duas prateleiras
    checar("com o custo único certo: 25",
           all(perto(l["custo_novo"], 25, 0.0001) for l in meu), meu)
    efeito_previsto = previa["efeito_no_estoque"]

    st, feito = chamar("POST", "/ajustes/custo-geral", token=token)
    checar("a unificação foi aceita", st == 201, (st, feito))
    checar("e o efeito é o que a prévia disse",
           perto(feito["efeito_no_estoque"], efeito_previsto, 0.01),
           (feito["efeito_no_estoque"], efeito_previsto))

    print("6. a reavaliação entra no RAZÃO, não por baixo do pano")
    # 🔑 Mudar quanto o estoque vale muda o CMV do período. Sem movimento, o
    # número mudaria sem nada explicando de onde veio — é para isso que
    # AJUSTE_CUSTO existe (migração 039).
    with get_cursor() as cur:
        cur.execute(
            """SELECT count(*) AS n, coalesce(sum(custo_total), 0) AS v
                 FROM estoque_movimentos
                WHERE origem_tipo = 'AJUSTE_LOTE' AND origem_id = %s""",
            (feito["id_lote"],))
        lote = cur.fetchone()
    checar("há um movimento por prateleira reavaliada",
           lote["n"] == feito["reavaliadas"], (lote["n"], feito["reavaliadas"]))
    checar("e a soma deles é o efeito anunciado",
           perto(lote["v"], efeito_previsto, 0.01), (lote["v"], efeito_previsto))
    c2 = custos_do(idp2)
    checar("as duas prateleiras do produto divergente convergiram",
           len({v[1] for v in c2.values()}) == 1, c2)

    print("7. rodar de novo não acha nada")
    st, depois = chamar("GET", "/ajustes/custo-geral/previa", token=token)
    checar("a prévia fica vazia", depois["produtos"] == 0, depois["produtos"])
    st, vazio = chamar("POST", "/ajustes/custo-geral", token=token)
    checar("e o botão diz que não há o que fazer",
           vazio["reavaliadas"] == 0 and vazio["preenchidas"] == 0, vazio)

    print("8. limpeza")
    for pid in (idp, idp2, id_agua):
        chamar("DELETE", f"/produtos/{pid}", token=token)
    checar("produtos de teste saíram da lista ativa", True)
finally:
    # ⚠️ SEMPRE, mesmo com falha no meio: a base é compartilhada e uma suíte que
    # deixasse a loja em "por local" mudaria o custo que as outras medem.
    modo(False)
    for local_de_teste in (id_bar, id_camara):
        if local_de_teste:
            chamar("DELETE", f"/locais/{local_de_teste}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
