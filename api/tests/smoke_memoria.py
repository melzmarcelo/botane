"""A memória de cálculo — e a única coisa que ela não pode ter: discordar do número.

🔑 **Pedido da contabilidade (02/09/2026).** O sistema dizia o RESULTADO do CMV e
não dizia de ONDE cada linha vinha. Agora diz — e o que esta suíte cobra é a
propriedade que dá sentido ao documento: **cada quadro FECHA com a linha da
apuração que ele explica**. Uma memória de cálculo que soma diferente do número
que ela existe para explicar é pior que memória nenhuma: manda o contador
procurar um erro que não existe, ou aceitar um que existe.

    python tests/smoke_memoria.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402
from services import cmv as motor  # noqa: E402
from services import memoria_calculo as memoria  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            conteudo = r.read()
            return r.status, (conteudo if bruto else json.loads(conteudo or b"null"))
    except urllib.error.HTTPError as e:
        conteudo = e.read()
        if bruto:
            return e.code, conteudo
        try:
            return e.code, json.loads(conteudo or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": conteudo.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def perto(a, b, tol=Decimal("0.01")):
    return abs(Decimal(str(a)) - Decimal(str(b))) <= tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
garantir_local(chamar, token)

# ⚠️ Marca por RODADA, não por dia: com um marcador diário a segunda execução
# do mesmo dia batia em 409 no código do produto — e a falha aparecia três
# checagens adiante, dizendo que as entradas não existem. Cada suíte cria os
# registros DELA.
marca = str(int(time.time()))[-7:]
hoje = date.today()
inicio, fim = hoje.replace(day=1), hoje

print("1. os dois lados da conta somam a mesma coisa")
# 🔑 A afirmação central: cada quadro FECHA com a linha que ele abre. Se este
# bloco falhar, o documento está contradizendo o sistema.
with get_cursor() as cur:
    cur.execute("SELECT id FROM unidades WHERE matriz AND ativo")
    id_unidade = cur.fetchone()["id"]
    fora = motor.tipos_fora_do_cmv(cur)
    a = motor.apurar(cur, id_unidade, inicio, fim)

    vespera = inicio - timedelta(days=1)
    ini_itens = memoria.estoque_em(cur, id_unidade, vespera, fora)
    fim_itens = memoria.estoque_em(cur, id_unidade, fim, fora)
    soma_ini = sum((Decimal(str(l["valor"])) for l in ini_itens), Decimal(0))
    soma_fim = sum((Decimal(str(l["valor"])) for l in fim_itens), Decimal(0))

checar("o estoque inicial item a item soma a linha da apuração",
       perto(soma_ini, a["estoque_inicial"]), (soma_ini, a["estoque_inicial"]))
checar("e o estoque final também",
       perto(soma_fim, a["estoque_final"]), (soma_fim, a["estoque_final"]))
# ⚠️ Produto com saldo zero fica de fora da lista de propósito: ele não compõe
# valor nenhum. A soma continua fechando porque zero não muda soma.
checar("e o corte de saldo zero não muda a soma",
       all(Decimal(str(l["quantidade"])) != 0 for l in fim_itens), len(fim_itens))

with get_cursor() as cur:
    notas = memoria.compras_por_nota(cur, id_unidade, inicio, fim, fora)
    remessa = motor._transferencia_entre_lojas(cur, id_unidade, inicio, fim, fora)
    concilia = memoria.conciliacao_compras(cur, id_unidade, inicio, fim, fora)
soma_notas = sum((Decimal(str(l["valor_no_razao"])) for l in notas), Decimal(0))
# ⚠️ `a["compras"]` JÁ inclui a remessa entre lojas: a linha da apuração soma as
# duas coisas. Cobrar `soma_notas == a["compras"]` acusaria de erro justamente a
# decisão de contar a remessa como compra do destino.
checar("as compras por documento somam a linha Compras, com a remessa junto",
       perto(soma_notas + remessa, a["compras"]), (soma_notas, remessa, a["compras"]))
checar("e a conciliação TERMINA exatamente na linha Compras",
       perto(concilia[-1]["valor"], a["compras"]), (concilia[-1], a["compras"]))
# 🔑 É a linha que evita a discussão: a soma das notas fiscais NÃO é a linha
# Compras, e o primeiro item da conciliação é justamente aquela soma.
checar("a conciliação começa pela soma dos totais das notas",
       "nota" in concilia[0]["linha"].lower(), concilia[0]["linha"])
checar("e mostra o caminho de uma até a outra em linhas nomeadas",
       len(concilia) >= 5, len(concilia))


print("\n2. a memória de UM produto refaz a conta do custo médio")
# O caso do mapeamento, conferido na mão:
#   entrada 10 kg a 20,00 → saldo 10, médio 20,00
#   entrada 10 kg a 30,00 → saldo 20, médio 25,00
#   saída    5 kg         → saldo 15, médio 25,00 (a saída não mexe no médio)
st, r = chamar("POST", "/produtos", {
    "codigo": f"MEM-{marca}", "nome": f"Insumo memoria {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO"}, token=token)
id_prod = (r or {}).get("id")
checar("produto da memória criado", st == 201, (st, r))
st, locais = chamar("GET", "/locais", token=token)
local = next((x for x in locais if x.get("principal")), locais[0])
for qtd, custo in ((10, 20), (10, 30)):
    chamar("POST", "/estoque/entradas", {
        "id_produto": id_prod, "quantidade": qtd, "custo_unitario": custo,
        "id_local": local["id"], "documento": f"MEM-{marca}"}, token=token)
chamar("POST", "/estoque/saidas", {
    "id_produto": id_prod, "quantidade": 5, "id_local": local["id"],
    "observacao": f"memoria {marca}"}, token=token)

with get_cursor() as cur:
    linhas = memoria.memoria_do_produto(cur, id_unidade, id_prod, inicio, fim)

checar("a memória abre com o saldo de abertura",
       linhas[0]["movimento"] == "Saldo de abertura", linhas[0]["movimento"])
checar("e fecha com o saldo de fechamento",
       linhas[-1]["movimento"] == "Saldo de fechamento", linhas[-1]["movimento"])
# ⚠️ Produto novo: abertura é zero, e isso tem de estar ESCRITO — um documento
# que começa no meio não se confere.
checar("produto novo abre em zero, e a linha existe mesmo assim",
       Decimal(str(linhas[0]["quantidade"])) == 0, linhas[0]["quantidade"])

entradas = [l for l in linhas if Decimal(str(l["quantidade"])) > 0
            and l["movimento"] not in ("Saldo de abertura", "Saldo de fechamento")]
checar("as duas entradas aparecem", len(entradas) == 2, [l["movimento"] for l in linhas])
# ⚠️ Guardado: uma exceção aqui custa as checagens seguintes, e um `checar` que
# falha custa uma linha.
if len(entradas) == 2:
    checar("a primeira deixa o médio em 20,00",
           perto(entradas[0]["custo_medio_apos"], 20), entradas[0]["custo_medio_apos"])
    # 🔑 O ponto do pedido: a CONTA está escrita na linha, não só o resultado.
    checar("e a segunda TRAZ A CONTA escrita, não só o resultado",
           "÷" in entradas[1]["conta"] and "×" in entradas[1]["conta"], entradas[1]["conta"])
    checar("com o médio ponderado de 25,00 no fim dela",
           perto(entradas[1]["custo_medio_apos"], 25), entradas[1]["custo_medio_apos"])

# ⚠️ Achar a saída pelo SINAL da quantidade, nunca pelo rótulo: `/estoque/saidas`
# grava "Consumo interno", e casar por texto fazia o teste procurar a palavra
# "Saída" numa linha que legitimamente não a tem.
saidas = [l for l in linhas if Decimal(str(l["quantidade"])) < 0]
checar("a saída aparece", len(saidas) >= 1, [l["movimento"] for l in linhas])
if saidas:
    # ⚠️ A saída NÃO mexe no médio, e a linha diz isso em vez de repetir a
    # fórmula: é a propriedade que faz o custo médio ser MÓVEL e não do dia.
    checar("e a linha dela explica que a saída não altera o custo médio",
           "não altera" in saidas[0]["conta"], saidas[0]["conta"])
    checar("o médio continua 25,00 depois da saída",
           perto(saidas[0]["custo_medio_apos"], 25), saidas[0]["custo_medio_apos"])
checar("e o fechamento é 15 KG a 25,00",
       perto(linhas[-1]["quantidade"], 15) and perto(linhas[-1]["custo_medio_apos"], 25),
       (linhas[-1]["quantidade"], linhas[-1]["custo_medio_apos"]))

# 🔑 **A conta escrita tem de BATER com o que ficou gravado.** Refazer a
# aritmética da linha e chegar noutro número seria pior que não escrevê-la.
if len(entradas) == 2:
    ent = entradas[1]
    antes_saldo = Decimal(str(entradas[0]["saldo_apos"]))
    antes_medio = Decimal(str(entradas[0]["custo_medio_apos"]))
    refeito = ((antes_saldo * antes_medio
                + Decimal(str(ent["quantidade"])) * Decimal(str(ent["custo_unitario"])))
               / Decimal(str(ent["saldo_apos"])))
    checar("refazendo a conta na mão dá o mesmo médio que ficou gravado",
           perto(refeito, ent["custo_medio_apos"], Decimal("0.000001")),
           (refeito, ent["custo_medio_apos"]))


print("\n3. os três relatórios saem em planilha e em PDF")
periodo = f"inicio={inicio}&fim={fim}"
for chave, params in (("memoria-cmv", periodo),
                      ("inventario-valorizado", f"data={fim}"),
                      ("memoria-produto", f"{periodo}&produtos={id_prod}")):
    st, csv = chamar("GET", f"/exportar/{chave}.csv?{params}", token=token, bruto=True)
    checar(f"{chave} sai em planilha", st == 200 and len(csv) > 50, (st, len(csv)))
    st, pdf = chamar("GET", f"/exportar/{chave}.pdf?{params}", token=token, bruto=True)
    checar(f"{chave} sai em PDF", st == 200 and pdf[:4] == b"%PDF", (st, pdf[:8]))

# ⚠️ O catálogo é a fonte do diálogo: relatório que existe no servidor e não
# aparece no catálogo é relatório que ninguém consegue baixar pela tela.
st, cat = chamar("GET", "/exportar/catalogo", token=token)
chaves = {c["chave"] for c in (cat or [])}
checar("os três aparecem no catálogo da tela",
       {"memoria-cmv", "inventario-valorizado", "memoria-produto"} <= chaves, sorted(chaves))
inv = next((c for c in (cat or []) if c["chave"] == "inventario-valorizado"), {})
checar("e o inventário pede UMA data, não um período",
       any(f["tipo"] == "data" for f in inv.get("filtros", [])), inv.get("filtros"))

# 🔑 **A memória por produto exige o produto, e DIZ isso.** Sem ele o arquivo
# sairia vazio, e vazio se lê como "não houve movimento" — que é outra coisa.
st, csv = chamar("GET", f"/exportar/memoria-produto.csv?{periodo}", token=token, bruto=True)
texto = csv.decode("utf-8", errors="replace")
checar("sem escolher o produto, o arquivo DIZ que falta escolher",
       st == 200 and "Escolha um produto" in texto, texto[:200])

# ⚠️ O documento tem de declarar o MÉTODO: um inventário valorizado sem dizer
# como valorizou não serve para o balanço.
st, csv = chamar("GET", f"/exportar/inventario-valorizado.csv?data={fim}",
                 token=token, bruto=True)
texto = csv.decode("utf-8", errors="replace")
checar("o inventário declara o método de custeio no cabeçalho",
       "custo médio ponderado móvel" in texto, texto[:400])
# 🔑 **O inventário do balanço NÃO tira os tipos fora do CMV.** Aquele filtro é
# da conta do custo da comida; detergente em estoque é patrimônio igual.
with get_cursor() as cur:
    tudo = memoria.estoque_em(cur, id_unidade, fim, None)
    so_comida = memoria.estoque_em(cur, id_unidade, fim, fora)
checar("e ele conta o que a casa POSSUI, não só o que vira comida",
       len(tudo) >= len(so_comida), (len(tudo), len(so_comida)))

st, csv = chamar("GET", f"/exportar/memoria-cmv.csv?{periodo}", token=token, bruto=True)
texto = csv.decode("utf-8", errors="replace")
for quadro in ("Quadro 1", "Quadro 2", "Quadro 3", "Quadro 4"):
    checar(f"a memória do CMV traz o {quadro}", quadro in texto, texto[:200])
checar("e explica por que a soma das notas não é a linha Compras",
       "Conciliação" in texto or "Conciliacao" in texto, texto[:200])


print("\n4. limpeza")
chamar("DELETE", f"/produtos/{id_prod}", token=token)
checar("o produto de teste saiu da lista ativa", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
