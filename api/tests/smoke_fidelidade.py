"""A fidelidade do Portal de Clientes: check-in pelo QR da mesa, cartão e prêmio.

🔑 **Pedido do dono (24/09/2026):** *"O cupom será por visita … um QRCode na mesa, que
o cliente lê e realiza o check-in. Após 10, ele recebe um almoço grátis."* E: conta
de segunda a sexta, consome de segunda a sexta, "mas deixar configurado".

O que esta suíte cobra é o que a regra RECUSA tanto quanto o que ela aceita: QR
velho, dia que não conta, casa fechada, segunda visita no dia, termo antigo, prêmio
entregue duas vezes, vencido e fora do dia de consumo.

    python tests/smoke_fidelidade.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
FONE = "47999300001"

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&%"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=40) as r:
            corpo_r = r.read()
            return r.status, (corpo_r if bruto else json.loads(corpo_r or b"null"))
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


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
UNIDADE = (eu.get("unidades") or [{}])[0].get("id")
devolver_a_reserva = preservar_reserva(UNIDADE)

# ⚠️ A configuração da fidelidade é UMA linha da rede, e esta suíte a muda:
# fotografa agora e devolve no fim, mesmo estourando no meio.
with get_cursor() as cur:
    cur.execute("SELECT * FROM fidelidade_config WHERE id = 1")
    CFG_ANTES = dict(cur.fetchone())


def _devolver_config():
    with get_cursor() as cur:
        campos = [k for k in CFG_ANTES if k != "id"]
        cur.execute(
            f"UPDATE fidelidade_config SET {', '.join(f'{k} = %s' for k in campos)} WHERE id = 1",
            [CFG_ANTES[k] for k in campos])


with get_cursor() as cur:
    cur.execute("SELECT latitude, longitude FROM unidades WHERE id = %s", (UNIDADE,))
    LOCAL_ANTES = dict(cur.fetchone())


def _devolver_local():
    with get_cursor() as cur:
        cur.execute("UPDATE unidades SET latitude = %s, longitude = %s WHERE id = %s",
                    (LOCAL_ANTES["latitude"], LOCAL_ANTES["longitude"], UNIDADE))


atexit.register(_devolver_config)
atexit.register(_devolver_local)

HOJE = date.today()
DIA_HOJE = HOJE.isoweekday()
TODOS = list(range(1, 8))
SEM_HOJE = [d for d in TODOS if d != DIA_HOJE]


def config_reserva(**mudancas):
    _st, cfg = chamar("GET", "/reservas/configuracao", token=token)
    corpo = {**cfg, "aceita_online": False, "fidelidade_ligada": True,
             "horarios": [{"dia_semana": d, "aberto": True, "abre": "00:00", "fecha": "23:59",
                           "ultima_reserva": "23:00"} for d in TODOS],
             **mudancas}
    return chamar("PUT", "/reservas/configuracao", corpo, token)


def config_fidelidade(**mudancas):
    corpo = {"visitas": 3, "premio": "Almoco gratis", "validade_dias": 30,
             "dias_pontua": TODOS, "dias_consumo": TODOS, "so_no_horario": True,
             "site_url": "http://localhost:3200", "exige_local": False, "raio_m": 200,
             **mudancas}
    return chamar("PUT", "/fidelidade/configuracao", corpo, token)


def limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM reserva_clientes WHERE telefone = %s", (FONE,))
        cur.execute("DELETE FROM reserva_tentativas WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_bloqueios WHERE id_unidade = %s", (UNIDADE,))
        cur.execute("DELETE FROM reserva_dias_especiais WHERE id_unidade = %s", (UNIDADE,))


def checkin(tk=None, aceite=False, **posicao):
    with get_cursor() as cur:
        cur.execute("DELETE FROM reserva_tentativas WHERE id_unidade = %s", (UNIDADE,))
    return chamar("POST", f"/publico/{UNIDADE}/fidelidade/checkin",
                  {"telefone": FONE, "token": tk or TOKEN, "aceite_termo": aceite, **posicao})


print("\n0. o cenario: Portal ligado, casa aberta o dia todo, fidelidade de 3 visitas")
chamar("PUT", f"/unidades/{UNIDADE}/parametros", {"reservas_ligado": True}, token)
limpar()
st, r = config_reserva()
checar("a loja passa a usar fidelidade (flag do Portal)",
       st == 200 and r.get("fidelidade_ligada") is True, (st, r))
st, cfg = config_fidelidade()
checar("a configuracao da fidelidade grava", st == 200 and cfg.get("visitas") == 3, (st, cfg))
TOKEN = cfg.get("token")
checar("o link do QR leva a loja e o segredo, e nada do cliente",
       cfg.get("link") == f"http://localhost:3200/?loja={UNIDADE}&checkin={TOKEN}", cfg.get("link"))
checar("dia invalido na configuracao e recusado (422)",
       config_fidelidade(dias_pontua=[0, 8])[0] == 422)
checar("sem nenhum dia de consumo e recusado (422)",
       config_fidelidade(dias_consumo=[])[0] == 422)
config_fidelidade()

st, casa = chamar("GET", f"/publico/{UNIDADE}/casa")
checar("o site recebe as regras da fidelidade, SEM o segredo do QR",
       (casa.get("fidelidade") or {}).get("visitas") == 3
       and "token" not in json.dumps(casa.get("fidelidade")), casa.get("fidelidade"))

st, pdf = chamar("GET", "/fidelidade/qrcodes.pdf?quantidade=5&tamanho=P&numerar=true",
                 token=token, bruto=True)
checar("o PDF dos QR codes sai", st == 200 and isinstance(pdf, bytes) and pdf[:5] == b"%PDF-",
       st)
checar("tamanho invalido do QR e recusado (422)",
       chamar("GET", "/fidelidade/qrcodes.pdf?tamanho=X", token=token)[0] == 422)

print("\n1. quem pode participar")
st, r = chamar("POST", f"/publico/{UNIDADE}/fidelidade/cartao", {"telefone": FONE})
checar("sem cadastro, o cartao explica (404)", st == 404 and "Cadastre" in (r.get("detail") or ""),
       (st, r))
st, r = chamar("POST", f"/publico/{UNIDADE}/cliente",
               {"telefone": FONE, "nome": "Fidel Teste", "genero": "OUTRO", "cidade": "Blumenau",
                "nascimento": "1990-01-01", "aceite_termo": True})
checar("o cliente se cadastra pelo site", st == 200, (st, r))
st, c = chamar("POST", f"/publico/{UNIDADE}/fidelidade/cartao", {"telefone": FONE})
checar("o cartao nasce vazio: 0 de 3, faltam 3",
       st == 200 and c.get("no_cartao") == 0 and c.get("faltam") == 3, (st, c))
checar("e quem aceitou o termo em vigor nao precisa aceitar de novo",
       c.get("precisa_termo") is False, c)

print("\n2. o que o check-in RECUSA")
checar("QR velho (segredo errado) e recusado (403)", checkin(tk="naovale")[0] == 403)
config_fidelidade(dias_pontua=SEM_HOJE)
st, r = checkin()
checar("dia que nao conta e recusado dizendo os dias", st == 409 and "contam" in
       (r.get("detail") or ""), (st, r))
config_fidelidade()
config_reserva(horarios=[{"dia_semana": d, "aberto": d != DIA_HOJE, "abre": "00:00",
                          "fecha": "23:59", "ultima_reserva": "23:00"} for d in TODOS])
st, r = checkin()
checar("com a casa fechada, o check-in e recusado", st == 409 and "aberta" in
       (r.get("detail") or ""), (st, r))
config_fidelidade(so_no_horario=False)
st, r = checkin()
checar("mas sem a exigencia de horario, vale", st == 200 and r.get("no_cartao") == 1, (st, r))
st, r = checkin()
checar("a segunda visita no MESMO dia e recusada", st == 409 and "hoje" in
       (r.get("detail") or ""), (st, r))
config_reserva()
config_fidelidade()

print("\n2b. a localizacao: so conta na casa (migracao 092)")
LOJA = (-26.919000, -49.066000)


def sem_visita_hoje():
    with get_cursor() as cur:
        cur.execute("DELETE FROM fidelidade_checkins WHERE data = %s AND id_cliente = "
                    "(SELECT id FROM reserva_clientes WHERE telefone = %s)", (HOJE, FONE))


sem_visita_hoje()
with get_cursor() as cur:
    cur.execute("UPDATE unidades SET latitude = NULL, longitude = NULL WHERE id = %s", (UNIDADE,))
config_fidelidade(exige_local=True, raio_m=200)
st, r = checkin(latitude=LOJA[0], longitude=LOJA[1], precisao=10)
checar("loja sem coordenadas: recusa dizendo que a casa nao configurou",
       st == 409 and "configurou" in (r.get("detail") or ""), (st, r))
st, cfg = chamar("PUT", "/fidelidade/localizacao", {"latitude": LOJA[0], "longitude": LOJA[1]},
                 token)
checar("a loja grava as coordenadas", st == 200 and cfg.get("local") == {
    "latitude": LOJA[0], "longitude": LOJA[1]}, (st, cfg.get("local")))
st, casa = chamar("GET", f"/publico/{UNIDADE}/casa")
checar("o site sabe que precisa pedir a localizacao",
       (casa.get("fidelidade") or {}).get("exige_local") is True, casa.get("fidelidade"))
st, r = checkin()
checar("sem a posicao do celular, pede a permissao", st == 409 and "localiza" in
       (r.get("detail") or ""), (st, r))
st, r = checkin(latitude=LOJA[0] + 0.05, longitude=LOJA[1], precisao=10)
checar("a 5,6 km, recusa dizendo a distancia", st == 409 and "km" in (r.get("detail") or ""),
       (st, r))
st, r = checkin(latitude=LOJA[0], longitude=LOJA[1], precisao=3000)
checar("localizacao imprecisa demais (so pela rede) pede o GPS", st == 409 and "GPS" in
       (r.get("detail") or ""), (st, r))
# ~330 m da loja, com o celular dizendo +-150 m: 330 - 150 = 180, dentro dos 200.
st, r = checkin(latitude=LOJA[0] + 0.003, longitude=LOJA[1], precisao=150)
checar("a margem de erro do celular e descontada", st == 200, (st, r))
sem_visita_hoje()
# ⚠️ Mas nunca mais que o raio: +-3.000 m de margem nao aprova quem esta a 900 m.
st, r = checkin(latitude=LOJA[0] + 0.008, longitude=LOJA[1], precisao=900)
checar("e a margem nao passa do raio", st == 409, (st, r))
st, r = checkin(latitude=LOJA[0] + 0.0004, longitude=LOJA[1], precisao=20)
checar("no salao (~45 m), conta", st == 200 and r.get("no_cartao") == 1, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT distancia_m FROM fidelidade_checkins WHERE data = %s AND id_cliente = "
                "(SELECT id FROM reserva_clientes WHERE telefone = %s)", (HOJE, FONE))
    d = (cur.fetchone() or {}).get("distancia_m")
checar("grava so a DISTANCIA do check-in, nao a posicao", d is not None and 40 <= d <= 50, d)
checar("raio fora da faixa e recusado (422)", config_fidelidade(raio_m=5)[0] == 422)
config_fidelidade()

print("\n3. o termo antigo")
with get_cursor() as cur:
    cur.execute("DELETE FROM fidelidade_checkins WHERE id_cliente = "
                "(SELECT id FROM reserva_clientes WHERE telefone = %s)", (FONE,))
    cur.execute("UPDATE reserva_clientes SET termo_versao = '2026-09-24' WHERE telefone = %s",
                (FONE,))
st, c = chamar("POST", f"/publico/{UNIDADE}/fidelidade/cartao", {"telefone": FONE})
checar("quem aceitou so o termo anterior e avisado", c.get("precisa_termo") is True, c)
st, r = checkin()
checar("e sem aceitar o novo, o check-in nao conta (409)", st == 409 and "termo" in
       (r.get("detail") or ""), (st, r))
st, r = checkin(aceite=True)
checar("aceitando, conta", st == 200 and r.get("no_cartao") == 1 and not r.get("precisa_termo"),
       (st, r))

print("\n4. o cartao completo vira premio")
with get_cursor() as cur:
    cur.execute("SELECT id FROM reserva_clientes WHERE telefone = %s", (FONE,))
    ID_CLIENTE = cur.fetchone()["id"]
    cur.execute("DELETE FROM fidelidade_checkins WHERE id_cliente = %s", (ID_CLIENTE,))
    for n in (3, 2):
        cur.execute("INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data) "
                    "VALUES (%s, %s, %s)", (ID_CLIENTE, UNIDADE, HOJE - timedelta(days=n)))
st, r = checkin()
premio = r.get("premio_novo") or {}
checar("a terceira visita fecha o cartao e gera o premio",
       st == 200 and premio.get("premio") == "Almoco gratis" and len(premio.get("codigo") or "") == 6,
       (st, r))
checar("e o cartao recomeca do zero", r.get("no_cartao") == 0 and r.get("faltam") == 3, r)
checar("o premio aparece no cartao, disponivel",
       any(p["codigo"] == premio.get("codigo") and p["status"] == "DISPONIVEL"
           for p in r.get("premios") or []), r.get("premios"))
CODIGO = premio.get("codigo")

st, lista = chamar("GET", f"/fidelidade/premios?busca={CODIGO}", token=token)
checar("o balcao acha o premio pelo codigo", st == 200 and len(lista) == 1
       and lista[0]["nome"] == "Fidel Teste" and lista[0]["pode_hoje"] is True, (st, lista))
st, cl = chamar("GET", f"/reservas/clientes?busca={FONE[-6:]}", token=token)
checar("o grid de clientes mostra o premio ganho", st == 200 and cl
       and cl[0].get("premios") == 1 and cl[0].get("no_cartao") == 0, cl)

print("\n5. a entrega no balcao")
# 🔑 Os dias de consumo sao CONGELADOS no premio: mudar a configuracao nao muda o ganho.
config_fidelidade(dias_consumo=SEM_HOJE)
with get_cursor() as cur:
    cur.execute("UPDATE fidelidade_premios SET dias_consumo = %s WHERE codigo = %s",
                (SEM_HOJE, CODIGO))
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": CODIGO}, token)
checar("fora do dia de consumo do premio, a entrega e recusada", st == 409 and "vale de" in
       (r.get("detail") or ""), (st, r))
with get_cursor() as cur:
    cur.execute("UPDATE fidelidade_premios SET dias_consumo = %s WHERE codigo = %s",
                (TODOS, CODIGO))
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": CODIGO.lower()}, token)
checar("no dia certo, entrega (e o codigo vale em minusculas)", st == 200, (st, r))
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": CODIGO}, token)
checar("entregar DE NOVO e recusado", st == 409 and "entregue" in (r.get("detail") or ""), (st, r))
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": "ZZZZZZ"}, token)
checar("codigo que nao existe: 404", st == 404, (st, r))
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                           dias_consumo, vence_em)
           VALUES (%s, %s, 'VNC234', 'Almoco', 3, %s, %s)""",
        (ID_CLIENTE, UNIDADE, TODOS, HOJE - timedelta(days=1)))
st, r = chamar("POST", "/fidelidade/premios/entregar", {"codigo": "VNC234"}, token)
checar("premio vencido e recusado", st == 409 and "venceu" in (r.get("detail") or ""), (st, r))
st, lista = chamar("GET", "/fidelidade/premios?status=VENCIDO&busca=VNC234", token=token)
checar("e aparece como vencido no grid", st == 200 and len(lista) == 1
       and lista[0]["status"] == "VENCIDO", (st, lista))
st, lista = chamar("GET", f"/fidelidade/premios?status=USADO&busca={CODIGO}", token=token)
checar("o entregue aparece como usado", st == 200 and len(lista) == 1
       and lista[0]["usado_em"], (st, lista))

print("\n6. a loja que nao participa")
config_reserva(fidelidade_ligada=False)
st, casa = chamar("GET", f"/publico/{UNIDADE}/casa")
checar("o site nao mostra fidelidade", casa.get("fidelidade") is None, casa.get("fidelidade"))
st, r = chamar("POST", f"/publico/{UNIDADE}/fidelidade/cartao", {"telefone": FONE})
checar("e o cartao responde 404", st == 404, (st, r))

st, cfg = chamar("POST", "/fidelidade/token", token=token)
checar("gerar outro QR troca o segredo", st == 200 and cfg.get("token") != TOKEN, (st, cfg))

print("\n7. limpeza")
limpar()
_devolver_config()
devolver_a_reserva()

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
