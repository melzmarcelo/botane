"""O PERÍODO DE CONSUMO: abre, acumula, fecha no pagamento — e cada um vê o seu.

🔑 **Pedido do dono (04/09/2026):** "o Administrador vai e abre um periodo de X
dias, de tal dia a tal dia. ai todos os consumos vão para este periodo. ai
quando for realizado o pagamento e fecha este periodo. e estes valores em aberto
podem ser consultados pelo usuario, para saber o valor do seu consumo".

⚠️ **A checagem mais importante desta suíte é a de VAZAMENTO** (seção 6): uma
pessoa não pode ver o consumo de outra. É a única aqui cuja falha não seria um
número errado, e sim dado de terceiro na tela de quem não devia.

⚠️ A segunda é a do CARIMBO: "em aberto" é a venda sem período, nunca uma conta
de datas. Fosse por data, corrigir as datas de um ciclo depois moveria dívida já
paga de volta para aberto.

    python tests/smoke_consumo_periodo.py     (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

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
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API nao respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

marca = str(time.time_ns())[-6:]
criados: dict = {"produtos": [], "vendas": [], "periodos": []}


def _limpar():
    # ⚠️ O periodo tem de ser REABERTO antes de a venda ser apagada: a venda
    # carimbada referencia o periodo, e apagar na ordem errada deixaria lixo.
    # E depois APAGADO: periodo aberto e um singleton por loja, entao um que
    # sobrasse faria a proxima rodada falhar no `abrir` — foi exatamente o que
    # uma sonda minha deixou para tras.
    for pid in criados["periodos"]:
        chamar("POST", f"/consumo/periodos/{pid}/reabrir", None, token=token)
        chamar("DELETE", f"/consumo/periodos/{pid}", token=token)
    for v in criados["vendas"]:
        if v:
            chamar("DELETE", f"/vendas/{v}", token=token)
    for p in criados["produtos"]:
        if p:
            chamar("DELETE", f"/produtos/{p}", token=token)


atexit.register(_limpar)


def _venda(id_pessoa, doc, qtd, valor, data="2026-09-03"):
    chamar("POST", "/vendas/importar", {"vendas": [{
        "data": data, "documento": doc, "origem": "MANUAL", "id_pessoa": id_pessoa,
        "itens": [{"id_produto": produto, "quantidade": qtd, "valor_unitario": valor}],
    }]}, token=token)
    st, lista = chamar("GET", f"/vendas?busca={doc}", token=token)
    vid = (lista or [{}])[0].get("id")
    criados["vendas"].append(vid)
    return vid


print("1. o cenario: um prato, duas pessoas e um login para uma delas")
st, prod = chamar("POST", "/produtos", {
    "codigo": f"PER-{marca}", "nome": f"PRATO PERIODO {marca}",
    "tipo": "PRODUZIDO", "um_estoque": "UN", "controla_estoque": False,
    "status": "ATIVO", "preco_venda": 40,
}, token=token)
produto = (prod or {}).get("id")
criados["produtos"].append(produto)

st, eu = chamar("POST", "/fornecedores", {
    "nome": f"EU {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 10}, token=token)
st, outro = chamar("POST", "/fornecedores", {
    "nome": f"OUTRO {marca}", "fornecedor": False,
    "cupom_base": "VENDA", "cupom_desconto_pct": 50}, token=token)

st, papeis = chamar("GET", "/papeis", token=token)
papel = (papeis or [{}])[0].get("id")
st, usuario = chamar("POST", "/usuarios", {
    "nome": f"EU {marca}", "email": f"eu{marca}@teste.com", "senha": "Senha!12345",
    "id_pessoa": eu["id"], "papeis": [{"id_papel": papel}],
}, token=token)
checar("o cenario nasce", bool(produto and eu.get("id") and usuario.get("id")),
       (produto, eu, usuario))

# 2 x 40 = 80 cheio, 10% off = 72
_venda(eu["id"], f"EU{marca}", 2, 40)
# 5 x 40 = 200 cheio, 50% off = 100 — e este NAO pode aparecer para o outro
_venda(outro["id"], f"OU{marca}", 5, 40)


print("\n2. antes de qualquer periodo, ja ha consumo EM ABERTO")
# 🔑 O consumo nao espera o ciclo existir: quem come hoje deve hoje, e o ciclo e
# so o momento em que se cobra. Exigir periodo aberto para lancar faria a casa
# parar de registrar consumo enquanto ninguem abrisse um.
st, lista = chamar("GET", "/consumo/periodos", token=token)
meu = next((l for l in lista["em_aberto"] if l["id_pessoa"] == eu["id"]), None)
checar("o consumo entra em aberto sem periodo nenhum", meu is not None, lista.get("em_aberto"))
checar("com o valor ja descontado: 80 cheio, 72 a pagar",
       meu and perto(meu["total_cheio"], 80) and perto(meu["total"], 72), meu)


print("\n3. abre o ciclo")
# ⚠️ **Periodo aberto e um SINGLETON por loja**, entao a suite nao pode presumir
# que nao ha nenhum: numa base de trabalho quase sempre ha. Se houver, ela o
# apaga — esta ABERTO, logo nada foi carimbado nele e nada se perde.
st, antes_de_tudo = chamar("GET", "/consumo/periodos", token=token)
if antes_de_tudo.get("aberto"):
    chamar("DELETE", f"/consumo/periodos/{antes_de_tudo['aberto']['id']}", token=token)
st, per = chamar("POST", "/consumo/periodos", {
    "inicio": "2026-09-01", "fim": "2026-09-30", "nome": f"Ciclo {marca}"}, token=token)
checar("o periodo abre", st == 201, (st, per))
periodo = per.get("id")
if periodo:
    criados["periodos"].append(periodo)

# ⚠️ Dois ciclos abertos disputariam o mesmo consumo, cada um fechando metade da
# divida — e a garantia e do indice unico, nao so da checagem em codigo.
st, dois = chamar("POST", "/consumo/periodos", {
    "inicio": "2026-10-01", "fim": "2026-10-31"}, token=token)
checar("um segundo periodo aberto e recusado", st == 409, (st, dois))

# ⚠️ Sobreposicao tambem: um mesmo dia em dois ciclos cobraria aquele dia duas
# vezes, e nada na tela denunciaria.
st, sobre = chamar("POST", "/consumo/periodos", {
    "inicio": "2026-09-15", "fim": "2026-09-20"}, token=token)
checar("e um periodo que se sobrepoe tambem", st == 409, (st, sobre))


print("\n4. o usuario ve o PROPRIO consumo")
st, entrou = chamar("POST", "/auth/login",
                    {"email": f"eu{marca}@teste.com", "senha": "Senha!12345"})
token_eu = entrou.get("access_token")
checar("o usuario entra", bool(token_eu), entrou)
st, meu_c = chamar("GET", "/consumo/meu", token=token_eu)
checar("e a tela responde", st == 200, (st, meu_c))
checar("dizendo que ele esta ligado a uma pessoa", meu_c.get("vinculado") is True, meu_c)
checar("com os 72 em aberto", perto(meu_c.get("total"), 72), meu_c.get("total"))
checar("e os 8 que ele economizou", perto(meu_c.get("desconto"), 8), meu_c.get("desconto"))
checar("o extrato traz o cupom dele",
       any(c.get("documento") == f"EU{marca}" for c in meu_c.get("cupons", [])),
       meu_c.get("cupons"))
checar("e o ciclo aberto aparece, para ele saber ate quando conta",
       (meu_c.get("periodo") or {}).get("id") == periodo, meu_c.get("periodo"))


print("\n5. e NAO ve o de mais ninguem")
# 🔑 **A checagem que mais importa aqui.** Falhar nesta nao daria um numero
# errado: daria a divida de um colega na tela de quem nao devia ver.
documentos = {c.get("documento") for c in meu_c.get("cupons", [])}
checar("o cupom da outra pessoa NAO aparece", f"OU{marca}" not in documentos, documentos)
checar("e o total nao inclui os 100 dela", not perto(meu_c.get("total"), 172),
       meu_c.get("total"))
# ⚠️ O escopo vem do vinculo no SERVIDOR. Se um `id_pessoa` do cliente fosse
# aceito, qualquer um leria o consumo de qualquer outro.
st, forjado = chamar("GET", f"/consumo/meu?id_pessoa={outro['id']}", token=token_eu)
checar("e mandar o id de outra pessoa na URL nao muda nada",
       perto(forjado.get("total"), 72), forjado.get("total"))


print("\n6. fecha o ciclo — o pagamento")
st, fechou = chamar("POST", f"/consumo/periodos/{periodo}/fechar", {}, token=token)
checar("o fechamento responde", st == 200, (st, fechou))
st, depois = chamar("GET", "/consumo/periodos", token=token)
ainda = next((l for l in depois["em_aberto"] if l["id_pessoa"] == eu["id"]), None)
# 🔑 **O carimbo e o que define "em aberto".** Fechado, o consumo sai da conta.
checar("depois de fechar, ele nao deve mais nada", ainda is None, ainda)
st, meu2 = chamar("GET", "/consumo/meu", token=token_eu)
checar("e a tela dele mostra zero em aberto", perto(meu2.get("total"), 0), meu2.get("total"))
# ⚠️ O recibo e o documento do pagamento: some da conta, mas nao da historia.
checar("com o ciclo pago no historico dele",
       any(h["id"] == periodo and perto(h["total"], 72) for h in meu2.get("historico", [])),
       meu2.get("historico"))

st, det = chamar("GET", f"/consumo/periodos/{periodo}", token=token)
linha = next((l for l in det["linhas"] if l["id_pessoa"] == eu["id"]), None)
checar("o recibo do ciclo guarda os 72 dele", linha and perto(linha["total"], 72), linha)
checar("e o ciclo aparece como fechado", det["periodo"]["status"] == "FECHADO",
       det["periodo"])


print("\n7. consumo NOVO depois do fechamento fica em aberto de novo")
# ⚠️ O ciclo fechado nao captura o que veio depois: cobrar hoje o consumo de
# amanha seria cobrar o que ainda nao aconteceu.
_venda(eu["id"], f"EU2{marca}", 1, 40)
st, novo = chamar("GET", "/consumo/meu", token=token_eu)
checar("o consumo seguinte volta a aparecer em aberto",
       perto(novo.get("total"), 36), novo.get("total"))
checar("e o historico do ciclo pago continua intacto",
       any(h["id"] == periodo and perto(h["total"], 72) for h in novo.get("historico", [])),
       novo.get("historico"))


print("\n8. reabrir desfaz o fechamento")
# 🔑 Existe porque fechar sem volta seria um beco: o fechamento reescreve
# centenas de vendas de uma vez, e fechar o ciclo errado e o engano mais
# provavel desta tela.
st, re1 = chamar("POST", f"/consumo/periodos/{periodo}/reabrir", None, token=token)
checar("o periodo reabre", st == 200, (st, re1))
st, volta = chamar("GET", "/consumo/meu", token=token_eu)
checar("e a divida volta inteira: 72 + 36 = 108",
       perto(volta.get("total"), 108), volta.get("total"))
checar("o historico daquele ciclo some junto — ele nao foi mais pago",
       not any(h["id"] == periodo for h in volta.get("historico", [])),
       volta.get("historico"))


print()
print("9. o ciclo aberto se APAGA; o fechado, nao")
# Sem isto, quem errasse as datas so sairia do periodo FECHANDO — e fechar
# carimba todo o consumo em aberto como pago. O conserto de um engano de
# digitacao nao pode ser cobrar todo mundo.
#
# A ORDEM importa: com um ciclo aberto, abrir outro e recusado (secao 3).
# Entao fecha-se o desta suite antes de criar o descartavel.
chamar("POST", f"/consumo/periodos/{periodo}/fechar", {}, token=token)
# O fechado nao se apaga: apaga-lo devolveria divida ja paga ao limbo, sem
# recibo e sem carimbo. Para isso existe o reabrir, que desfaz explicitamente.
st9, _q = chamar("DELETE", f"/consumo/periodos/{periodo}", token=token)
checar("um periodo FECHADO nao se apaga", st9 == 409, (st9, _q))

st, r9 = chamar("POST", "/consumo/periodos", {
    "inicio": "2027-01-01", "fim": "2027-01-31", "nome": "engano"}, token=token)
descartavel = r9.get("id")
checar("mas o aberto por engano se apaga",
       bool(descartavel)
       and chamar("DELETE", f"/consumo/periodos/{descartavel}", token=token)[0] == 200,
       (st, r9))
chamar("POST", f"/consumo/periodos/{periodo}/reabrir", None, token=token)


print("\n10. quem nao tem pessoa ligada e DITO, nao mostrado como zero")
# ⚠️ "Nao devo nada" e "nao estou ligado a um cadastro" sao coisas diferentes, e
# a segunda se resolve no cadastro de usuarios.
st, sem = chamar("GET", "/consumo/meu", token=token)
checar("a resposta diz se o login esta ligado a uma pessoa",
       "vinculado" in sem, list(sem.keys())[:6])


_limpar()
print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
