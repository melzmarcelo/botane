"""A importação do LeadsFood (services/importacao_leadsfood.py, migração 145).

🔑 **Pedido do dono (30/10/2026):** *"siga para a importação do LeadsFood"*. Os CSVs aqui são
SINTÉTICOS, no formato dos arquivos do LeadsFood, com telefones de DDD 00 (ninguém tem).
`preservar_reserva` devolve a loja como estava — clientes, reservas e fidelidade.

    python tests/smoke_importacao_leadsfood.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
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


def importar(arquivos: dict[str, str], simular: bool):
    """POST multipart com os CSVs (texto) — `arquivos` = {campo: conteúdo}."""
    limite = uuid.uuid4().hex
    partes = []
    for campo, texto in arquivos.items():
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; "
                      f"filename=\"{campo}.csv\"\r\nContent-Type: text/csv\r\n\r\n".encode()
                      + ("﻿" + texto).encode("utf-8") + b"\r\n")
    corpo = b"".join(partes) + f"--{limite}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/reservas/importar-leadsfood?simular={'true' if simular else 'false'}",
        data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Unidade", str(U))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()
_st, eu = chamar("GET", "/auth/me", token=token)
U = (eu.get("unidades") or [{}])[0].get("id") or 1
preservar_reserva(U)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)


def sql(q, p=()):
    with get_cursor() as cur:
        cur.execute(q, p)
        return [dict(x) for x in cur.fetchall()] if cur.description else []


HOJE = sql("SELECT current_date AS d")[0]["d"]
br = lambda d: d.strftime("%d/%m/%Y")  # noqa: E731
F = {k: f"00900003{i:03d}" for i, k in enumerate(("ana", "beto", "caio", "site", "dani"))}
# O cliente que já existe AQUI (cadastro do site): nome e cidade dele valem.
with get_cursor() as cur:
    cur.execute("""INSERT INTO reserva_clientes (id_unidade, telefone, nome, cidade)
                   VALUES (%s, %s, 'Nome do site', 'Cidade do site')""", (U, F["site"]))

CAB_C = ("Nome completo,Nome,Sobrenome,Celular,E-mail,Gênero,Nascimento,Aniversário,Origem,"
         "Cidade,Estado,Tags,Total reservas,Total filas,Total checkins,Total vouchers,"
         "Total avaliações,Data de criação")
CONTATOS = "\n".join([CAB_C,
    f'Ana Teste,Ana,Teste,55{F["ana"]},ana@x.com,F,10/05/1990,10/05,Conversão,Blumenau,SC,'
    f'"Cardápio - Link bio,Whatsapp",1,0,3,1,0,15/03/2026 10:20',
    f'Beto Teste,Beto,Teste,+55 ({F["beto"][:2]}) {F["beto"][2:7]}-{F["beto"][7:]},,M,,,Reservas,'
    f'Gaspar,SC,,0,0,0,0,0,01/12/2025 09:00',
    f'Outro Nome,Outro,Nome,55{F["site"]},site@x.com,F,01/01/1985,01/01,Fidelidade,Outra,SC,'
    f'Whatsapp,0,0,0,0,0,01/01/2025 08:00',
    'Estrangeiro,E,X,353123456789,,M,,,Conversão,,,,0,0,0,0,0,01/01/2026 08:00'])

CAB_R = ("Nome completo,Celular,Origem,Pessoas,Data e hora,Mesa,Status,Ambiente,Objetivo,"
         "Observações,Notas,Valor,Valor total,Taxa,Pago em,Data de criação,Última atualização")
d1, d2, d3 = HOJE - timedelta(days=40), HOJE - timedelta(days=20), HOJE - timedelta(days=10)
RESERVAS = "\n".join([CAB_R,
    f"Ana Teste,55{F['ana']},Reservas,4,{br(d1)} 12:00,mesa 05,Compareceu,Botané,Aniversário,"
    f"Bolo às 13h,,,,,,{br(d1 - timedelta(days=5))} 10:00,{br(d1)} 14:00",
    f"Ana Teste,55{F['ana']},Reservas,2,{br(d2)} 12:30,,Não compareceu,Botané,,,,,,,,"
    f"{br(d2)} 08:00,{br(d2)} 15:00",
    f"Caio Teste,55{F['caio']},Conversão,8,{br(d3)} 13:00,,Confirmado,Botané,Outro,,,,,,,"
    f"{br(d3)} 08:00,{br(d3)} 08:00",
    f"Caio Teste,55{F['caio']},Conversão,3,{br(d3)} 16:00,,Cancelado pelo cliente,Botané,,,,,,,,"
    f"{br(d3)} 08:00,{br(d3)} 09:00"])

s1, s2 = HOJE - timedelta(days=30), HOJE - timedelta(days=15)
SELOS = "\n".join(["nome,celular,pin,campanha,status,criado_em",
    f"Ana Teste,55{F['ana']},AAA111,10 pratos,Confirmado,{br(s1)} 12:01:00",
    f"Ana Teste,55{F['ana']},AAA112,10 pratos,Confirmado,{br(s1)} 12:02:00",
    f"Ana Teste,55{F['ana']},AAA113,10 pratos,Confirmado,{br(s1)} 12:03:00",
    f"Ana Teste,55{F['ana']},AAA114,10 pratos,Confirmado,{br(s2)} 12:00:00",
    f"Dani Teste,55{F['dani']},DDD111,10 pratos,Confirmado,{br(s2)} 13:00:00"])

CAB_P = ("Nome completo,Celular,Remetente,Celular remetente,Campanha,Descrição,Expiração,Valor,"
         "Status,Data utilização")
v_aberto, v_usado, v_vencido = HOJE + timedelta(days=20), HOJE - timedelta(days=5), HOJE - timedelta(days=60)
PREMIOS = "\n".join([CAB_P,
    f"Ana Teste,55{F['ana']},,,10 pratos,Almoço cortesia,{br(v_aberto)},,Não utilizado,",
    f"Beto Teste,55{F['beto']},,,10 pratos,Almoço cortesia,{br(v_usado)},,Utilizado,{br(v_usado - timedelta(days=10))}",
    f"Beto Teste,55{F['beto']},,,10 pratos,Almoço cortesia,{br(v_vencido)},,Expirado,"])

TODOS = {"contatos": CONTATOS, "reservas": RESERVAS, "selos": SELOS, "premios": PREMIOS}
cliente = lambda f: (sql("SELECT * FROM reserva_clientes WHERE telefone = %s", (f,)) or [None])[0]  # noqa: E731

print("1. a prévia não grava")
st, p = importar(TODOS, simular=True)
checar("responde", st == 200, (st, p))
checar("conta os clientes novos (ana, beto, caio, dani) e o completado (o do site)",
       p["clientes"]["novos"] == 4 and p["clientes"]["completados"] == 1, p["clientes"])
checar("recusa o celular estrangeiro, com o motivo", len(p["recusados"]) == 1
       and p["recusados"][0]["arquivo"] == "contatos" and "celular" in p["recusados"][0]["motivo"],
       p["recusados"])
checar("e NADA foi gravado", cliente(F["ana"]) is None and p["aplicado"] is False)

print("\n2. importar")
st, p = importar(TODOS, simular=False)
checar("grava", st == 200 and p["aplicado"] is True, (st, p))
ana = cliente(F["ana"])
checar("a cliente nova com gênero, nascimento, e-mail, cidade, UF e origem",
       ana and ana["genero"] == "FEMININO" and str(ana["nascimento"]) == "1990-05-10"
       and ana["email"] == "ana@x.com" and ana["cidade"] == "Blumenau" and ana["uf"] == "SC"
       and ana["origem"] == "Conversão", ana)
checar("as etiquetas separadas", ana["etiquetas"] == ["Cardápio - Link bio", "Whatsapp"], ana["etiquetas"])
checar("a data de cadastro é a do LeadsFood", ana["criado_em"].date() == date(2026, 3, 15), ana["criado_em"])
checar("e a marca de importado", ana["importado_de"] == "LEADSFOOD")
checar("o celular com +55, parênteses e traço vira o mesmo número",
       cliente(F["beto"]) and cliente(F["beto"])["genero"] == "MASCULINO")
site = cliente(F["site"])
checar("o cliente do site mantém nome e cidade; só ganha o vazio (e-mail, gênero, nascimento)",
       site["nome"] == "Nome do site" and site["cidade"] == "Cidade do site"
       and site["email"] == "site@x.com" and site["genero"] == "FEMININO", site)
checar("e o cadastro dele recua para o primeiro contato (lá)", site["criado_em"].date() == date(2025, 1, 1))

rs = sql("""SELECT data, hora, pessoas, status, id_cliente, objetivo, observacao_cliente,
                   observacao_interna, origem FROM reservas
             WHERE id_unidade = %s AND importado_de = 'LEADSFOOD' AND telefone LIKE '00900003%%'
             ORDER BY data, hora""", (U,))
checar("4 reservas", len(rs) == 4, len(rs))
st_ = {(str(x["data"]), str(x["hora"])[:5]): x for x in rs}
checar("Compareceu → ENCERRADA, Não compareceu → NAO_COMPARECEU, Confirmado → CONFIRMADA, "
       "Cancelado → CANCELADA",
       [st_[(str(d), h)]["status"] for d, h in ((d1, "12:00"), (d2, "12:30"), (d3, "13:00"), (d3, "16:00"))]
       == ["ENCERRADA", "NAO_COMPARECEU", "CONFIRMADA", "CANCELADA"], [x["status"] for x in rs])
r1 = st_[(str(d1), "12:00")]
checar("ligada ao cliente, com objetivo, observação e a mesa de lá na nota interna",
       r1["id_cliente"] == ana["id"] and r1["objetivo"] == "Aniversário"
       and r1["observacao_cliente"] == "Bolo às 13h" and "mesa 05" in (r1["observacao_interna"] or ""), r1)

selos = sql("""SELECT data, selos, parte, origem, motivo FROM fidelidade_checkins
                WHERE id_cliente = %s ORDER BY data""", (ana["id"],))
checar("três check-ins no mesmo dia viram UMA visita de 3 selos", len(selos) == 2
       and selos[0]["selos"] == 3 and selos[0]["parte"] == 0 and selos[1]["selos"] == 1, selos)
checar("com o motivo 'Importado do LeadsFood'", selos[0]["motivo"] == "Importado do LeadsFood")
checar("quem só aparece nos selos ganha cadastro mínimo", cliente(F["dani"]) is not None)
_st, lista = chamar("GET", f"/reservas/clientes?busca={F['ana']}&limite=5&offset=0", token=token)
checar("a lista de Clientes traz origem, etiquetas e a marca de importado",
       _st == 200 and lista and lista[0]["origem"] == "Conversão"
       and lista[0]["etiquetas"] == ["Cardápio - Link bio", "Whatsapp"]
       and lista[0]["importado_de"] == "LEADSFOOD", (_st, lista))

pr = sql("""SELECT p.vence_em, p.usado_em, p.vale_de, p.codigo, c.telefone FROM fidelidade_premios p
             JOIN reserva_clientes c ON c.id = p.id_cliente
            WHERE p.importado_de = 'LEADSFOOD' AND c.telefone = ANY(%s) ORDER BY p.vence_em""",
         ([F["ana"], F["beto"]],))
checar("3 prêmios, cada um com código próprio", len(pr) == 3 and len({x["codigo"] for x in pr}) == 3, pr)
usado = next(x for x in pr if x["vence_em"] == v_usado)
checar("o usado guarda o dia do uso", usado["usado_em"] and usado["usado_em"].date() == v_usado - timedelta(days=10))
aberto = next(x for x in pr if x["vence_em"] == v_aberto)
checar("o aberto fica para usar, e vale desde antes de hoje",
       aberto["usado_em"] is None and aberto["vale_de"] <= HOJE, aberto)
abertos = sql("""SELECT coalesce(sum(selos), 0) AS n FROM fidelidade_checkins
                   WHERE id_cliente = %s AND id_premio IS NULL""", (ana["id"],))[0]["n"]
checar("o cartão da Ana fica com os 4 selos em aberto", abertos == 4, abertos)
_st, ficha = chamar("GET", f"/fidelidade/participantes/{ana['id']}", token=token)
checar("e a ficha da fidelidade abre", _st == 200, _st)

print("\n3. importar de novo não duplica")
st, p = importar(TODOS, simular=False)
checar("nenhum cliente, reserva ou prêmio novo", p["clientes"]["novos"] == 0
       and p["reservas"]["novas"] == 0 and p["premios"]["novos"] == 0, p)
checar("as reservas iguais e os selos 'já importados'", p["reservas"]["iguais"] == 4
       and p["selos"]["ja_tinham"] == 3 and p["selos"]["dias"] == 0, (p["reservas"], p["selos"]))
checar("o banco continua com 4 reservas", len(sql(
    "SELECT 1 FROM reservas WHERE id_unidade = %s AND importado_de = 'LEADSFOOD'"
    " AND telefone LIKE '00900003%%'", (U,))) == 4)

print("\n4. arquivos mais novos")
novas_r = RESERVAS.replace(f"{br(d3)} 13:00,,Confirmado", f"{br(d3)} 13:00,,Compareceu")
# A Ana completou o cartão lá: o dia s1 sumiu da lista de abertos.
novos_s = "\n".join(l for l in SELOS.split("\n") if br(s1) not in l)
novos_p = PREMIOS.replace(f"{br(v_aberto)},,Não utilizado,", f"{br(v_aberto)},,Utilizado,{br(HOJE)}")
st, p = importar({"reservas": novas_r, "selos": novos_s, "premios": novos_p}, simular=False)
checar("a reserva que mudou de status é atualizada", p["reservas"]["atualizadas"] == 1, p["reservas"])
checar("o selo importado que sumiu do arquivo sai (a foto)", p["selos"]["retirados"] == 1, p["selos"])
checar("o prêmio que foi usado lá passa a usado aqui", p["premios"]["atualizados"] == 1, p["premios"])
selos = sql("SELECT data FROM fidelidade_checkins WHERE id_cliente = %s", (ana["id"],))
checar("a Ana fica só com o selo do dia s2", [x["data"] for x in selos] == [s2], selos)

print("\n5. a visita marcada aqui vale mais que a de lá")
with get_cursor() as cur:
    cur.execute("""INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, selos, parte, origem)
                   VALUES (%s, %s, %s, 1, 0, 'QRCODE')""", (ana["id"], U, s1))
st, p = importar({"selos": SELOS}, simular=False)
checar("o dia em que já há visita daqui é conflito, e não entra", p["selos"]["conflitos"] == 1, p["selos"])
checar("e a visita daqui não foi tocada", sql(
    "SELECT origem FROM fidelidade_checkins WHERE id_cliente = %s AND data = %s",
    (ana["id"], s1)) == [{"origem": "QRCODE"}])

print("\n6. arquivo no campo errado")
st, p = importar({"contatos": RESERVAS}, simular=True)
checar("400 dizendo que parece o de reservas", st == 400 and "reservas" in p["detail"], (st, p))
st, p = importar({}, simular=True)
checar("sem arquivo nenhum, 400", st == 400 or st == 422, st)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
