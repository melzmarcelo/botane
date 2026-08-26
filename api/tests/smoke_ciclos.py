"""Teste de fumaça dos ciclos de fechamento do CMV.

A casa não fecha o custo sempre no fim do mês: a que apresentou o sistema fecha
toda semana, e quem confere o caixa fecha todo dia. Aqui se prova que os três
ritmos existem de verdade — não só na tela.

O que este arquivo cobra, na ordem em que a coisa quebra:

1. o padrão continua MENSAL, com o mês do calendário (nada mudou para quem já usava)
2. a prévia mostra o calendário ANTES de salvar, e é a mesma conta do fechamento
3. no ritmo semanal, o período vai do dia seguinte ao fechamento até o dia dele
4. período que ainda não terminou não fecha — a guarda que impede congelar amanhã
5. períodos fechados não se sobrepõem
6. o razão nomeia o PERÍODO na recusa, não o mês
7. o mês que começa no dia 26 (quem fecha junto com o fornecedor)

    python tests/smoke_ciclos.py            (API de pé na 9200)

⚠️ **A loja volta a MENSAL no fim, registrado no `atexit`.** A base é
compartilhada com as outras suítes: deixá-la em SEMANAL faria a apuração do
`cenario_cafeteria` abrir noutro período e acusar diferença sem que nada
tivesse quebrado. Repor no fim do roteiro não basta — se este arquivo estourar
no meio, o `atexit` repõe do mesmo jeito. Mesma lição do modo `simulado` do
Omie e do `preservar_credenciais`.
"""

import atexit
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "tests")
from comum import garantir_local  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=40) as r:
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


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]

UNIDADE = 1
hoje = date.today()


def ritmo(**mudanca):
    return chamar("PUT", f"/unidades/{UNIDADE}/parametros", mudanca, token=token)


def restaurar():
    """Devolve a loja ao ritmo de fábrica, dê certo ou não este arquivo."""
    ritmo(ciclo_fechamento="MENSAL", dia_fechamento_cmv=1, fechamento_dia_semana=7)


atexit.register(restaurar)

# O que este arquivo fechar é reaberto no fim: fechamento trava lançamento
# retroativo, e as outras suítes lançam com data.
fechados: list[int] = []


print("1. o padrão não mudou: mensal, mês do calendário")
restaurar()
st, r = chamar("GET", "/cmv/periodos?quantos=3", token=token)
checar("o ciclo padrão é MENSAL", r.get("ciclo") == "MENSAL", r.get("ciclo"))
periodos = r.get("periodos", [])
atual = next((p for p in periodos if p["corrente"]), None)
checar("o período corrente começa no dia 1",
       atual and atual["inicio"] == str(hoje.replace(day=1)), atual)
checar("e não é fechável, porque ainda está em curso",
       atual and atual["fechavel"] is False, atual)
st, a = chamar("GET", "/cmv/apuracao", token=token)
checar("a apuração sem datas abre no mês", a.get("inicio") == str(hoje.replace(day=1)), a.get("inicio"))
# ⚠️ O mês CORRENTE não se chama "agosto de 2026" na apuração: ela vai até hoje,
# e o período ainda não fechou. O nome curto é reservado ao período inteiro —
# chamar de "agosto" um recorte que para no dia 25 é o mesmo engano que a
# movimentação evita ao dizer se o número é congelado.
checar("e o rótulo mostra as pontas, porque o mês ainda está em curso",
       " a " in str(a.get("rotulo")), a.get("rotulo"))


print("\n2. a prévia mostra o calendário antes de salvar")
st, p = chamar("GET",
               f"/unidades/{UNIDADE}/parametros/previa-fechamento?ciclo=SEMANAL&dia_semana=3",
               token=token)
checar("a prévia responde", st == 200, st)
checar("e explica o que vai acontecer",
       "quarta" in str(p.get("descricao")), p.get("descricao"))
checar("com três períodos de exemplo", len(p.get("periodos", [])) == 3, p.get("periodos"))
# ⚠️ A prévia NÃO pode ter salvado nada: ela é do formulário, não do banco.
st, r = chamar("GET", "/cmv/periodos?quantos=1", token=token)
checar("a prévia não altera a configuração", r.get("ciclo") == "MENSAL", r.get("ciclo"))


print("\n3. semanal: o período termina no dia escolhido")
st, r = ritmo(ciclo_fechamento="SEMANAL", fechamento_dia_semana=7)
checar("a loja passa a fechar por semana", st == 200, r)
st, r = chamar("GET", "/cmv/periodos?quantos=4", token=token)
checar("o ciclo virou SEMANAL", r.get("ciclo") == "SEMANAL", r.get("ciclo"))
semanas = r.get("periodos", [])
checar("cada período tem sete dias",
       all((date.fromisoformat(p["fim"]) - date.fromisoformat(p["inicio"])).days == 6
           for p in semanas),
       [(p["inicio"], p["fim"]) for p in semanas])
checar("e termina sempre num domingo",
       all(date.fromisoformat(p["fim"]).isoweekday() == 7 for p in semanas),
       [p["fim"] for p in semanas])
# ⚠️ As semanas se encostam sem buraco e sem repetição: o fim de uma é a
# véspera do início da anterior. Um dia de folga entre elas sumiria do CMV.
encaixe = all(
    date.fromisoformat(semanas[i]["inicio"]) - timedelta(days=1)
    == date.fromisoformat(semanas[i + 1]["fim"])
    for i in range(len(semanas) - 1)
)
checar("e as semanas se encaixam sem buraco", encaixe, [(p["inicio"], p["fim"]) for p in semanas])

st, r = ritmo(fechamento_dia_semana=3)
st, r = chamar("GET", "/cmv/periodos?quantos=2", token=token)
checar("mudando o dia, o período acompanha",
       all(date.fromisoformat(p["fim"]).isoweekday() == 3 for p in r["periodos"]),
       [p["fim"] for p in r["periodos"]])
ritmo(fechamento_dia_semana=7)


print("\n4. período em curso não fecha")
st, r = chamar("GET", "/cmv/periodos?quantos=3", token=token)
corrente = next(p for p in r["periodos"] if p["corrente"])
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": corrente["inicio"]}, token=token)
# Se a semana corrente terminar HOJE (domingo), fechar é legítimo: o dia do
# fechamento pertence ao período que ele encerra.
if corrente["fim"] == str(hoje):
    checar("a semana que termina hoje pode ser fechada", st == 201, (st, r))
    if st == 201:
        fechados.append(r["id"])
else:
    checar("a semana em curso é recusada", st == 400, (st, r))
    checar("e a recusa diz até quando ela vai",
           corrente["fim"][-2:] in str(r.get("detail", "")), r.get("detail"))

st, r = chamar("GET", "/cmv/periodos?quantos=3", token=token)
anterior = next(p for p in r["periodos"] if p["fechavel"])
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": anterior["inicio"]}, token=token)
checar("a semana passada fecha", st == 201, (st, r))
id_semana = r.get("id")
if id_semana:
    fechados.append(id_semana)
checar("e o nome do período vai na resposta",
       str(r.get("rotulo", "")).startswith("semana de"), r.get("rotulo"))
# ⚠️ Qualquer dia DENTRO do período aponta para o mesmo fechamento: quem manda
# a data do meio da semana não pode abrir um segundo congelado.
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": anterior["fim"]}, token=token)
checar("qualquer dia da semana cai no mesmo período (409)", st == 409, (st, r))


print("\n5. períodos fechados não se sobrepõem")
ritmo(ciclo_fechamento="DIARIO")
dentro = date.fromisoformat(anterior["inicio"]) + timedelta(days=2)
st, r = chamar("POST", "/cmv/fechamentos", {"competencia": str(dentro)}, token=token)
checar("o dia dentro da semana fechada é recusado", st == 409, (st, r))
checar("e a recusa nomeia o período que está no caminho",
       "sobrep" in str(r.get("detail", "")).lower(), r.get("detail"))


print("\n6. o razão nomeia o período, não o mês")
local = garantir_local(chamar, token)
st, produtos = chamar("GET", "/produtos?limite=200&ativo=true", token=token)
lista = produtos if isinstance(produtos, list) else []
alvo = next((p for p in lista if p.get("controla_estoque") and p.get("um_estoque")), None)
if not alvo:
    checar("há produto com unidade para lançar", False, "nenhum produto serve")
else:
    # O admin tem `estoque.retroativo` e passaria pela trava — quem prova a
    # recusa é o conferente, como no smoke_cmv.
    st, papeis = chamar("GET", "/papeis", token=token)
    id_conf = next(p["id"] for p in papeis if p["nome"].startswith("Conferente"))
    email = "smoke.conferente@botane.com.br"
    st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
    conf = next((u for u in usuarios if u["email"] == email), None)
    if conf:
        chamar("PUT", f"/usuarios/{conf['id']}",
               {"ativo": True, "senha": "conf12345", "papeis": [{"id_papel": id_conf}]},
               token=token)
    else:
        chamar("POST", "/usuarios", {"nome": "Smoke Conferente", "email": email,
                                     "senha": "conf12345",
                                     "papeis": [{"id_papel": id_conf}]}, token=token)
    st, r = chamar("POST", "/auth/login", {"email": email, "senha": "conf12345"})
    tk = r.get("access_token")
    st, r = chamar("POST", "/estoque/entradas", {
        "id_produto": alvo["id"], "quantidade": 1, "custo_unitario": 1,
        "id_local": local["id"], "data_movimento": f"{dentro}T10:00:00",
    }, token=tk)
    checar("lançar dentro da semana fechada é recusado", st == 400, (st, r))
    checar("e a recusa diz SEMANA, não o mês",
           "semana de" in str(r.get("detail", "")), r.get("detail"))


print("\n7. o mês que começa no dia 26")
st, r = ritmo(ciclo_fechamento="MENSAL", dia_fechamento_cmv=26)
checar("aceita o dia de virada", st == 200, r)
st, r = chamar("GET", "/cmv/periodos?quantos=2", token=token)
p0 = r["periodos"][0]
checar("o período começa no dia 26",
       date.fromisoformat(p0["inicio"]).day == 26, p0)
checar("e termina no dia 25", date.fromisoformat(p0["fim"]).day == 25, p0)
# ⚠️ O rótulo curto ("agosto de 2026") só vale para o mês do calendário: um
# ciclo 26–25 chamado de "agosto" mandaria ao contador o período errado.
checar("e o rótulo mostra as duas pontas, não o nome do mês",
       " a " in p0["rotulo"] and "de 20" not in p0["rotulo"], p0["rotulo"])
st, r = ritmo(dia_fechamento_cmv=29)
checar("dia acima de 28 é recusado (fevereiro não tem)", st == 422, st)


print("\n8. limpeza")
for id_f in fechados:
    st, r = chamar("POST", f"/cmv/fechamentos/{id_f}/reabrir", token=token)
    checar(f"reabre o fechamento {id_f}", st == 200, (st, r))
restaurar()
st, r = chamar("GET", "/cmv/periodos?quantos=1", token=token)
checar("a loja volta ao ritmo mensal", r.get("ciclo") == "MENSAL", r.get("ciclo"))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
