"""Teste de fumaça dos relatórios do dono.

Dois relatórios, duas provas:

**CMV por setor / categoria.** O cenário monta dois setores com valores
diferentes e confere que cada um aparece com o seu, que a soma dos grupos
**fecha com o CMV total** do período (se não fechar, algum real sumiu no
caminho) e que produto sem setor aparece como "Sem setor" em vez de evaporar.

**Evolução de preço.** Compra o mesmo insumo três vezes, com preço subindo, e
confere que o relatório enxerga a alta, calcula o **impacto em reais** sobre o
volume comprado e diz de qual fornecedor veio o mais barato. A ordenação é por
impacto, não por percentual: item que subiu muito e se compra pouco não pode
passar na frente do que subiu pouco e entra toda semana.

    python tests/smoke_relatorios.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_local, garantir_setores  # noqa: E402
from datetime import date, timedelta

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

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
        with urllib.request.urlopen(req, dados, timeout=60) as r:
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


def perto(a, b, tol=0.02):
    return a is not None and abs(float(a) - float(b)) < tol


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 100)[-6:]

# O período começa hoje: o teste mede o DELTA que ele mesmo cria, porque o
# banco local já tem movimento de outras rodadas.
hoje = date.today()
periodo = f"?inicio={hoje}&fim={hoje}"

local = garantir_local(chamar, token)
# O relatório por grupo só prova o que promete com mais de um setor.
setores = garantir_setores(chamar, token, 2)
setor_a, setor_b = setores[0], setores[1] if len(setores) > 1 else setores[0]

print("0. dois setores, valores diferentes")
st, antes_grupo = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=setor", token=token)
checar("o relatório por setor responde", st == 200, antes_grupo)
base = {g["grupo"]: float(g["cmv"]) for g in (antes_grupo or [])}

produtos = {}
for rotulo, setor, custo in (("cozinha", setor_a, 10), ("bar", setor_b, 4)):
    st, p = chamar("POST", "/produtos", {
        "nome": f"Rel {rotulo} {marca}", "tipo": "INSUMO", "um_estoque": "KG",
        "id_setor": setor["id"],
    }, token=token)
    produtos[rotulo] = p.get("id")
    checar(f"produto de {rotulo} criado", st == 201, p)
    # Entra 10 e sai 6: o CMV do produto é 6 x custo.
    chamar("POST", "/estoque/entradas", {
        "id_produto": p["id"], "quantidade": 10, "custo_unitario": custo,
        "id_local": local["id"],
    }, token=token)
    chamar("POST", "/estoque/saidas", {
        "tipo": "SAIDA_PERDA", "id_produto": p["id"], "quantidade": 6,
        "id_local": local["id"], "id_motivo_perda": 1,
    }, token=token)

# Um produto sem setor nenhum: ele não pode sumir do relatório.
st, sem_setor = chamar("POST", "/produtos", {
    "nome": f"Rel sem setor {marca}", "tipo": "INSUMO", "um_estoque": "KG",
}, token=token)
chamar("POST", "/estoque/entradas", {
    "id_produto": sem_setor["id"], "quantidade": 5, "custo_unitario": 2,
    "id_local": local["id"],
}, token=token)
chamar("POST", "/estoque/saidas", {
    "tipo": "SAIDA_PERDA", "id_produto": sem_setor["id"], "quantidade": 5,
    "id_local": local["id"], "id_motivo_perda": 1,
}, token=token)

print("1. cada setor com o seu")
st, grupos = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=setor", token=token)
depois = {g["grupo"]: float(g["cmv"]) for g in grupos}
checar(f"o setor {setor_a['nome']} subiu 60,00 (6 x 10)",
       perto(depois.get(setor_a["nome"], 0) - base.get(setor_a["nome"], 0),
             60 if setor_a["id"] != setor_b["id"] else 84), depois)
if setor_a["id"] != setor_b["id"]:
    checar(f"o setor {setor_b['nome']} subiu 24,00 (6 x 4)",
           perto(depois.get(setor_b["nome"], 0) - base.get(setor_b["nome"], 0), 24), depois)
checar("produto sem setor aparece como 'Sem setor'",
       perto(depois.get("Sem setor", 0) - base.get("Sem setor", 0), 10), depois)

print("2. a soma dos grupos fecha com o CMV total")
st, apuracao = chamar("GET", f"/cmv/apuracao{periodo}", token=token)
soma = sum(float(g["cmv"]) for g in grupos)
checar("a apuração responde", st == 200, apuracao)
checar("a soma dos grupos é o CMV do período",
       perto(soma, apuracao.get("cmv_real"), 0.05), (soma, apuracao.get("cmv_real")))
checar("e as participações somam 100%",
       perto(sum(float(g["participacao_pct"]) for g in grupos), 100, 0.5),
       sum(float(g["participacao_pct"]) for g in grupos))

print("3. o mesmo por categoria")
st, cats = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=categoria", token=token)
checar("o relatório por categoria responde", st == 200, cats)
checar("e fecha com o mesmo total",
       perto(sum(float(g["cmv"]) for g in cats), apuracao.get("cmv_real"), 0.05),
       sum(float(g["cmv"]) for g in cats))
st, r = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar=fornecedor", token=token)
checar("agrupamento inventado e recusado (422)", st == 422, st)

print("3b. os eixos novos do recorte")
# 🔑 **Protótipo aprovado pelo dono (16/09/2026):** *"podendo ter a opcao de
# ser pela empresa, por loja, por local de estoque, setor, categoria, produto"*.
# Os tres saem de graca do grao que ja existe -- a conta e agregada em
# `(loja, produto, local)`, entao enrolar por prateleira ou por produto e trocar
# o `GROUP BY`. **Nenhum numero muda, so o eixo.**
# ⚠️ A afirmacao que importa e sempre a MESMA: a soma FECHA com o CMV do
# periodo. E ela que da sentido ao corte -- nao e rateio, e a mesma conta
# restrita a cada linha.
for eixo in ("local", "produto", "loja"):
    st, linhas = chamar("GET", f"/cmv/por-grupo{periodo}&agrupar={eixo}", token=token)
    checar(f"o recorte por {eixo} responde", st == 200 and isinstance(linhas, list),
           (st, str(linhas)[:120]))
    if st == 200 and linhas:
        checar(f"e a soma por {eixo} fecha com o CMV do periodo",
               perto(sum(float(g["cmv"]) for g in linhas), apuracao.get("cmv_real"), 0.05),
               (eixo, sum(float(g["cmv"]) for g in linhas), apuracao.get("cmv_real")))

# 🔑 **Empresa e o que o USUARIO enxerga**, e amplia ate o limite da permissao.
# Numa casa de uma loja so, o escopo de empresa devolve exatamente a mesma conta
# -- e e essa a prova de que ele nao inventa nada.
st, emp = chamar("GET", f"/cmv/apuracao{periodo}&escopo=empresa", token=token)
checar("a apuracao aceita o escopo de empresa", st == 200, (st, str(emp)[:120]))
checar("e numa casa de uma loja da o mesmo CMV",
       perto(emp.get("cmv_real"), apuracao.get("cmv_real"), 0.01),
       (emp.get("cmv_real"), apuracao.get("cmv_real")))
# ⚠️ Percentual NAO se soma nem se tira a media: a cobertura da empresa e
# `receita com ficha / receita`, refeita do total.
checar("com a cobertura de ficha refeita do total, nao somada",
       perto(emp.get("cobertura_ficha_pct"), apuracao.get("cobertura_ficha_pct"), 0.01),
       (emp.get("cobertura_ficha_pct"), apuracao.get("cobertura_ficha_pct")))
# 🔑 A receita COM ficha em reais: e o numerador da cobertura, e percentual
# nao se soma -- juntar duas lojas exige o numerador.
# ⚠️ **O numerador tem de ser LIQUIDO como o denominador.** Ele saia da soma
# BRUTA dos itens com ficha enquanto a receita ja vinha descontada, e numa base
# com cobertura alta a cobertura passava de 100% -- a tela dizia que a receita
# com ficha era MAIOR que a receita. O desconto e do CUPOM, entao ele e rateado
# proporcionalmente: a parte com ficha nunca passa do total do cupom.
checar("e a apuracao diz a receita que TEM ficha, em reais",
       apuracao.get("receita_com_custo") is not None
       and float(apuracao["receita_com_custo"]) <= float(apuracao["receita"]) + 0.01,
       (apuracao.get("receita_com_custo"), apuracao.get("receita")))
checar("e a cobertura de ficha nunca passa de 100%",
       float(apuracao.get("cobertura_ficha_pct") or 0) <= 100.01,
       apuracao.get("cobertura_ficha_pct"))
st, r = chamar("GET", f"/cmv/apuracao{periodo}&escopo=galaxia", token=token)
checar("escopo inventado e recusado (422)", st == 422, st)

print("3c. a memoria de calculo, em tela")
# 🔑 **Pedido da contabilidade (02/09/2026), agora como TELA.** A apuracao
# dizia o resultado em dez linhas e nao dizia de ONDE cada linha veio; o
# documento existe em PDF desde entao -- e a pergunta nasce OLHANDO o painel.
st, mem = chamar("GET", f"/cmv/memoria{periodo}&limite=10", token=token)
checar("a memoria de calculo responde", st == 200 and "composicao" in (mem or {}),
       (st, list(mem or {})))
if st == 200:
    comp = {c["linha"]: c["valor"] for c in mem["composicao"]}
    # ⚠️ A afirmacao central: os quadros FECHAM com as linhas da apuracao.
    # E isso que transforma a tabela em prova.
    checar("o quadro 1 fecha com o estoque inicial da apuracao",
           perto(mem["estoque_inicial"]["soma"], apuracao.get("estoque_inicial"), 0.05),
           (mem["estoque_inicial"]["soma"], apuracao.get("estoque_inicial")))
    checar("e o quadro 3 fecha com o estoque final",
           perto(mem["estoque_final"]["soma"], apuracao.get("estoque_final"), 0.05),
           (mem["estoque_final"]["soma"], apuracao.get("estoque_final")))
    checar("a composicao repete a conta do painel",
           perto(comp.get("(=) CMV real do periodo".replace("periodo", "per\u00edodo")),
                 apuracao.get("cmv_real"), 0.05), comp)
    # ⚠️ O quadro 4 e o que responde "por que a soma das notas nao e a linha
    # Compras" -- e a ultima linha dele TEM de ser a propria linha Compras.
    checar("e a conciliacao termina na linha Compras da apuracao",
           mem["conciliacao"] and perto(mem["conciliacao"][-1]["valor"],
                                        apuracao.get("compras"), 0.05),
           mem["conciliacao"][-1] if mem["conciliacao"] else None)
    # ⚠️ O corte e das LISTAS, nunca dos totais: o estoque final tem 1.331
    # produtos nesta base, e mandar todos trava a tela.
    checar("o limite corta a lista e nao o total",
           mem["estoque_final"]["mostrando"] <= 10
           and mem["estoque_final"]["total"] >= mem["estoque_final"]["mostrando"],
           (mem["estoque_final"]["mostrando"], mem["estoque_final"]["total"]))
    # ⚠️ id com virgula e o tipo de coisa que passa despercebida ate alguem
    # monta-lo numa URL.
    primeira = (mem["estoque_final"]["linhas"] or [{}])[0]
    checar("e o id do produto continua inteiro",
           isinstance(primeira.get("id_produto"), int), primeira.get("id_produto"))

print("4. evolução de preço: o que subiu, e quanto custa")
st, fornecedores = chamar("GET", "/fornecedores", token=token)
caro, barato = fornecedores[0], fornecedores[1] if len(fornecedores) > 1 else fornecedores[0]
st, insumo = chamar("POST", "/produtos", {
    "nome": f"Rel azeite {marca}", "tipo": "INSUMO", "um_estoque": "UN",
}, token=token)
# Três compras do mesmo item, subindo: 10,00 -> 12,00 -> 15,00, 10 un cada.
for i, (preco, fornecedor) in enumerate(((10, barato), (12, caro), (15, caro))):
    st, nota = chamar("POST", "/notas", {
        "id_fornecedor": fornecedor["id"], "numero": f"R{marca}{i}",
        "data_emissao": str(hoje - timedelta(days=2 - i)),
        "id_local": local["id"],
        "itens": [{"id_produto": insumo["id"], "quantidade": 10, "valor_unitario": preco}],
    }, token=token)
    checar(f"nota {i + 1} de {preco},00 registrada", st == 200, nota)
    st, r = chamar("POST", f"/notas/{nota['id']}/lancar", {"id_local": local["id"]}, token=token)
    checar(f"nota {i + 1} lançada no estoque", st == 200, r)

st, precos = chamar("GET", f"/cmv/precos?inicio={hoje - timedelta(days=3)}&fim={hoje}",
                    token=token)
linha = next((x for x in precos if x["id_produto"] == insumo["id"]), None)
checar("o insumo aparece no relatório de preços", linha is not None,
       [x["produto"] for x in precos[:5]])
checar("três compras contadas", linha and linha["compras"] == 3, linha)
checar("primeiro preço 10,00", linha and perto(linha["primeiro"], 10), linha)
checar("último preço 15,00", linha and perto(linha["ultimo"], 15), linha)
checar("alta de 50%", linha and perto(linha["variacao_pct"], 50, 0.1), linha)
# 30 unidades compradas x 5,00 de alta = 150,00. É o número da conversa.
checar("impacto de 150,00 no volume comprado", linha and perto(linha["impacto"], 150), linha)
checar("e diz de quem veio o mais barato",
       linha and linha["fornecedor_mais_barato"] == barato["nome"], linha)
if caro["id"] != barato["id"]:
    checar("e de quem veio a última compra",
           linha and linha["fornecedor_ultimo"] == caro["nome"], linha)

print("5. o detalhe por trás da variação")
st, serie = chamar("GET", f"/cmv/precos/{insumo['id']}", token=token)
checar("a série de compras responde", st == 200 and len(serie) == 3, serie)
checar("da mais recente para a mais antiga",
       serie and perto(serie[0]["preco"], 15) and perto(serie[-1]["preco"], 10), serie)
checar("com o fornecedor de cada compra", all(s.get("fornecedor") for s in serie), serie)

print("6. item comprado uma vez só não vira ruído")
st, unico = chamar("POST", "/produtos", {
    "nome": f"Rel unico {marca}", "tipo": "INSUMO", "um_estoque": "UN"}, token=token)
st, nota = chamar("POST", "/notas", {
    "id_fornecedor": caro["id"], "numero": f"U{marca}", "data_emissao": str(hoje),
    "id_local": local["id"],
    "itens": [{"id_produto": unico["id"], "quantidade": 1, "valor_unitario": 99}],
}, token=token)
chamar("POST", f"/notas/{nota['id']}/lancar", {"id_local": local["id"]}, token=token)
st, precos = chamar("GET", f"/cmv/precos?inicio={hoje - timedelta(days=3)}&fim={hoje}",
                    token=token)
checar("uma compra só não entra (não há variação a mostrar)",
       not any(x["id_produto"] == unico["id"] for x in precos))

print("7. a planilha do fornecedor")
import urllib.request as _u
req = _u.Request(BASE + f"/exportar/precos.csv?inicio={hoje - timedelta(days=3)}&fim={hoje}")
req.add_header("Authorization", f"Bearer {token}")
with _u.urlopen(req, timeout=60) as resp:
    csv = resp.read().decode("utf-8")
checar("o CSV sai", "Evolução de preço" in csv, csv[:80])
# ⚠️ `.upper()`: o nome do produto é normalizado pelo banco (migração
# 036), e a suíte afirma sobre o que foi GRAVADO, não sobre o que mandou.
checar("com o insumo do teste", f"Rel azeite {marca}".upper() in csv)
checar("e traz o quadro por setor no mesmo arquivo", "Onde o custo pesa" in csv)
checar("com o impacto somado no resumo", "Impacto somado" in csv)

print("7b. o arquivo do painel: a conta do CMV mais a aba em que a pessoa esta")
# 🔑 **Pedido do dono (16/09/2026):** *"alterar o baixar esta tabela para um
# botao de baixar... este deve baixar os numeros do CMV, abaixo do cabecalho, e
# os dados da aba posicionada"*. Eram cinco botoes espalhados pelo painel, cada
# um dando um arquivo diferente e nenhum com a conta junto: quem baixava a curva
# ABC recebia a curva ABC solta, sem o numero que ela explica.
st, cat = chamar("GET", "/exportar/catalogo", token=token)
rel_cmv = next((r for r in (cat or []) if r["chave"] == "cmv"), None)
checar("o catalogo declara o relatorio do CMV", rel_cmv is not None, [r["chave"] for r in (cat or [])])
if rel_cmv:
    porNome = {f["nome"]: f for f in rel_cmv["filtros"]}
    # 🔑 **Periodo COM opcoes: o front troca as duas datas por um seletor dos
    # ciclos.** ⚠️ Data digitada a mao e onde o engano entra -- "17/08 a 23/08"
    # com um dia a mais e o arquivo deixa de bater com o fechamento, sem nada
    # avisando, porque o numero continua saindo.
    periodo_cmv = porNome.get("periodo_cmv")
    checar("e o periodo dele vem com os ciclos da loja, nao datas soltas",
           bool(periodo_cmv) and periodo_cmv["tipo"] == "periodo"
           and len(periodo_cmv.get("opcoes") or []) > 0,
           periodo_cmv and {k: v for k, v in periodo_cmv.items() if k != "opcoes"})
    # ⚠️ O valor e `inicio|fim`: o contrato do servidor continua sendo as duas
    # pontas, e e o front que desmembra. Um parametro novo so para este
    # relatorio criaria uma segunda forma de dizer periodo.
    if periodo_cmv and periodo_cmv.get("opcoes"):
        checar("com o valor no formato inicio|fim",
               all(str(o["valor"]).count("|") == 1 for o in periodo_cmv["opcoes"]),
               periodo_cmv["opcoes"][0])
    aba_f = porNome.get("aba")
    checar("e a aba e escolha unica, nao doze caixinhas",
           bool(aba_f) and aba_f["tipo"] == "escolha"
           and len(aba_f.get("opcoes") or []) == 12,
           aba_f and {k: v for k, v in (aba_f or {}).items() if k != "opcoes"})

def baixar_cmv(aba: str) -> str:
    req = _u.Request(
        BASE + f"/exportar/cmv.csv?inicio={hoje - timedelta(days=3)}&fim={hoje}&aba={aba}")
    req.add_header("Authorization", f"Bearer {token}")
    with _u.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")

# ⚠️ **A conta vem SEMPRE na frente, em toda aba.** E ela que o quadro de tras
# explica; sem ela o arquivo e uma tabela sem o numero a que se refere.
esperado = {
    "conta": None,
    "quebra-setor": "Quebra por setor",
    "abc": "Curva ABC",
    "margem": "Margem por prato",
    "movimentacao": "Movimentação de estoque",
    "precos": "Evolução de preço",
    "memoria": "Quadro 4",
}
for aba, quadro in esperado.items():
    csv_aba = baixar_cmv(aba)
    checar(f"o arquivo da aba {aba} abre pela conta do CMV",
           "Composição do CMV" in csv_aba and "(=) CMV real" in csv_aba,
           csv_aba[:120])
    if quadro:
        checar(f"e traz o quadro da aba {aba} atras dela",
               quadro in csv_aba, csv_aba[:200])
    else:
        # ⚠️ "A conta" nao leva anexo, e e escolha: ela E a composicao, e
        # repeti-la como quadro dobraria a mesma tabela.
        checar("e a aba da conta sai sem quadro atras",
               "Margem por prato" not in csv_aba and "Curva ABC" not in csv_aba,
               csv_aba[:200])

# ⚠️ **Quem baixa de fora do painel continua recebendo o arquivo do contador.**
# Sem aba nenhuma o relatorio leva a margem por prato, como sempre levou.
checar("sem aba, o relatorio segue sendo o do contador",
       "Margem por prato" in baixar_cmv(""))
# ⚠️ Valor desconhecido cai no padrao em vez de dar 422: o catalogo ja diz o que
# existe, e um erro aqui viraria uma tela que nao baixa nada sem dizer por que.
checar("e uma aba que nao existe cai no padrao, sem erro",
       "Margem por prato" in baixar_cmv("inventada"))

# 🔑 **Dinheiro em centavos e percentual com uma casa, no quadro da quebra.**
# O motor encadeia custo unitario de seis casas, e a linha saia
# `6094,0000000000` / `92,84221351575725` -- num arquivo que vai ao contador
# isso nao e um valor em reais nem um percentual.
csv_quebra = baixar_cmv("quebra-setor")
linhas_quebra = [l for l in csv_quebra.splitlines() if l.count(";") >= 7][1:]
checar("o quadro da quebra sai arredondado, nao com as seis casas do motor",
       bool(linhas_quebra) and not any(
           any(len(c.split(",")[1]) > 2 for c in l.split(";")[1:6] if "," in c)
           for l in linhas_quebra),
       linhas_quebra[:2])

print("8. permissão")
st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
if tk:
    checar("cozinha não vê o CMV por setor",
           chamar("GET", f"/cmv/por-grupo{periodo}", token=tk)[0] == 403)
    checar("cozinha não vê o relatório de preços",
           chamar("GET", "/cmv/precos", token=tk)[0] == 403)
else:
    checar("usuário de cozinha disponível para o teste de permissão", False, r)

print()
print("8b. o setor do CMV vem de ONDE a mercadoria saiu")
# 🔑 **O caso do açúcar, descrito pelo dono.** O mesmo insumo é consumido por
# vários setores: ele entra no Estoque Central e de manhã Bar, Confeitaria,
# Cozinha e Cafeteria levam um pacote cada. Enquanto o relatório agrupava por
# `produtos.id_setor` — um setor só —, TODO o consumo de açúcar era atribuído a
# um deles, e a resposta para "a confeitaria está pesando mais que o bar?" era
# ficção. Quem sabe de onde a mercadoria saiu é o MOVIMENTO.
st, r = chamar("POST", "/setores", {"nome": f"Bar rel {marca}"}, token=token)
setor_bar = (r or {}).get("id")
st, r = chamar("POST", "/setores", {"nome": f"Confeitaria rel {marca}"}, token=token)
setor_conf = (r or {}).get("id")
st, r = chamar("POST", "/locais", {"nome": f"Canto do bar {marca}", "tipo": "SECO",
                                   "id_setor": setor_bar}, token=token)
local_bar = (r or {}).get("id")
st, r = chamar("POST", "/locais", {"nome": f"Canto da conf {marca}", "tipo": "SECO",
                                   "id_setor": setor_conf}, token=token)
local_conf = (r or {}).get("id")

# ⚠️ O cadastro do produto diz BAR — e é justamente o que NÃO pode mandar
# sozinho: o mesmo açúcar é consumido nos dois cantos.
st, r = chamar("POST", "/produtos", {
    "codigo": f"ACUREL{marca}", "nome": f"Acucar do relatorio {marca}", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "id_setor": setor_bar}, token=token)
acucar_rel = (r or {}).get("id")

for onde in (local_bar, local_conf):
    chamar("POST", "/estoque/entradas", {
        "id_produto": acucar_rel, "quantidade": 10, "custo_unitario": 5,
        "id_local": onde}, token=token)
# Cada canto consome o seu: 2 KG no bar (10,00) e 6 KG na confeitaria (30,00).
chamar("POST", "/estoque/saidas", {
    "id_produto": acucar_rel, "quantidade": 2, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": local_bar}, token=token)
chamar("POST", "/estoque/saidas", {
    "id_produto": acucar_rel, "quantidade": 6, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": local_conf}, token=token)

hoje_rel = date.today().isoformat()
st, por_setor = chamar(
    "GET", f"/cmv/por-grupo?agrupar=setor&inicio={hoje_rel}&fim={hoje_rel}", token=token)
linhas_setor = {l["grupo"]: l for l in (por_setor or [])}
nome_bar = f"Bar rel {marca}".upper()
nome_conf = f"Confeitaria rel {marca}".upper()
checar("o mesmo insumo aparece nos DOIS setores que o consumiram",
       nome_bar in linhas_setor and nome_conf in linhas_setor, sorted(linhas_setor)[:8])
# 🔑 O que prova a mudança: a confeitaria consumiu o TRIPLO do bar, e antes
# esses R$ 30,00 iriam para o bar — o setor do cadastro.
checar("e a confeitaria pesa o que ela de fato gastou",
       perto(float(linhas_setor.get(nome_conf, {}).get("cmv", 0)), 30),
       linhas_setor.get(nome_conf, {}).get("cmv"))
checar("enquanto o bar pesa só o dele",
       perto(float(linhas_setor.get(nome_bar, {}).get("cmv", 0)), 10),
       linhas_setor.get(nome_bar, {}).get("cmv"))

# 🔑 **A identidade continua fechando** — é ela que dá sentido ao corte por
# grupo, e é o que este relatório arriscava ao mudar de grão.
st, apur = chamar("GET", f"/cmv/apuracao?inicio={hoje_rel}&fim={hoje_rel}", token=token)
soma_setores = sum(float(l["cmv"]) for l in (por_setor or []))
folga = 0.01 * max(1, len(por_setor or []))
checar("e a soma dos setores continua fechando com o CMV do periodo",
       abs(soma_setores - float(apur.get("cmv_real", 0))) <= folga,
       (soma_setores, apur.get("cmv_real")))

# ⚠️ **Categoria e grupo NÃO mudaram um centavo**: são atributos do PRODUTO, e o
# grão fino só é enrolado depois. Somar é associativo.
st, por_cat = chamar(
    "GET", f"/cmv/por-grupo?agrupar=categoria&inicio={hoje_rel}&fim={hoje_rel}", token=token)
soma_cat = sum(float(l["cmv"]) for l in (por_cat or []))
checar("a soma por CATEGORIA fecha com a mesma conta",
       abs(soma_cat - soma_setores) <= folga, (soma_cat, soma_setores))

# ⚠️ **A reserva é o setor do PRODUTO**: prateleira sem setor não vira "Sem
# setor", senão toda casa que ainda não classificou os locais veria o relatorio
# inteiro virar uma linha só.
st, r = chamar("POST", "/locais", {"nome": f"Central rel {marca}", "tipo": "SECO"}, token=token)
local_central = (r or {}).get("id")
chamar("POST", "/estoque/entradas", {
    "id_produto": acucar_rel, "quantidade": 4, "custo_unitario": 5,
    "id_local": local_central}, token=token)
chamar("POST", "/estoque/saidas", {
    "id_produto": acucar_rel, "quantidade": 1, "tipo": "SAIDA_CONSUMO_INTERNO",
    "id_local": local_central}, token=token)
st, por_setor2 = chamar(
    "GET", f"/cmv/por-grupo?agrupar=setor&inicio={hoje_rel}&fim={hoje_rel}", token=token)
linhas2 = {l["grupo"]: l for l in (por_setor2 or [])}
# ⚠️ **A afirmação é a PROPRIEDADE, não um número que eu calculei de cabeça.**
# A primeira versão esperava 11,00 somando só a saída de 1 KG — e esqueceu que a
# entrada de 4 KG no central também é COMPRA, então o CMV daquele pedaço é
# 20 − 15 = 5, não 5 − 4. O que importa provar é que o movimento do central
# ENGORDOU a linha do setor do produto em vez de criar uma linha "Sem setor".
cmv_bar_antes = float(linhas_setor.get(nome_bar, {}).get("cmv", 0))
cmv_bar_depois = float(linhas2.get(nome_bar, {}).get("cmv", 0))
checar("saida de prateleira SEM setor cai no setor do produto",
       nome_bar in linhas2 and cmv_bar_depois > cmv_bar_antes,
       (cmv_bar_antes, cmv_bar_depois))
checar("e nao inventa uma linha 'Sem setor' para ela",
       float(linhas2.get("Sem setor", {}).get("cmv", 0))
       == float(linhas_setor.get("Sem setor", {}).get("cmv", 0)),
       (linhas_setor.get("Sem setor", {}).get("cmv"),
        linhas2.get("Sem setor", {}).get("cmv")))

chamar("DELETE", f"/produtos/{acucar_rel}", token=token)


print("9. limpeza")
for p in list(produtos.values()) + [sem_setor.get("id"), insumo.get("id"), unico.get("id")]:
    chamar("DELETE", f"/produtos/{p}", token=token)
# ⚠️ **Os SETORES do caso do açúcar também saem, e não saíam.** Cada rodada
# deixava "Bar rel" e "Confeitaria rel" ATIVOS — 39 de cada na base local. Setor
# é tabela de APOIO: ela não pagina no dia a dia porque se supõe curta, e uma
# suíte que a engorda a cada rodada quebra a checagem da rodada seguinte por um
# motivo que não tem nada a ver com o que se estava testando.
for id_setor in (setor_bar, setor_conf):
    if id_setor:
        chamar("PUT", f"/setores/{id_setor}", {"ativo": False}, token=token)
# ⚠️ Os LOCAIS idem — e aqui não se apaga: o razão aponta para eles e é
# append-only, então o `DELETE` da API é uma desativação.
for id_local in (local_bar, local_conf, local_central):
    if id_local:
        chamar("DELETE", f"/locais/{id_local}", token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
