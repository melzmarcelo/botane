"""O Plano de ação das reservas — quem chamar de volta (services/reservas_plano.py).

🔑 **Pedido do dono (30/10/2026):** *"comece pelo plano de ação de reservas"* — a tela do
LeadsFood: VIPs em risco, organizadores de grupo sumidos e adormecidos, com WhatsApp.

O cenário é montado DIRETO no banco: a rota de reservar recusa data passada, e o plano só
existe sobre o passado. `preservar_reserva` devolve a loja como estava no fim.

    python tests/smoke_plano_de_acao.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request
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
U = (eu.get("unidades") or [{}])[0].get("id") or 1
preservar_reserva(U)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)

HOJE = date.today()
# Telefones que nenhuma pessoa de verdade tem (DDD 00), para não cruzar com a base.
F = {k: f"00900000{i:03d}" for i, k in enumerate(
    ("vip", "org", "dorm", "recente", "volta", "cancelou", "formatos", "faltou", "site"))}


def reserva(cur, fone_gravado, dias_atras, pessoas=2, status="ENCERRADA", nome="Pessoa teste",
            id_cliente=None):
    cur.execute(
        """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome, telefone,
                                 id_cliente)
           VALUES (%s, %s, '12:00', %s, %s, 'BALCAO', %s, %s, %s)""",
        (U, HOJE - timedelta(days=dias_atras), pessoas, status, nome, fone_gravado, id_cliente))


with get_cursor() as cur:
    for d in (200, 220, 240, 260):
        reserva(cur, F["vip"], d, nome="VIP sumido")
    reserva(cur, F["org"], 150, pessoas=8, nome="Organizador")
    reserva(cur, F["org"], 180, pessoas=10, nome="Organizador")
    reserva(cur, F["dorm"], 100, nome="Adormecido")
    reserva(cur, F["recente"], 30, nome="Veio mês passado")
    for d in (200, 220, 240):
        reserva(cur, F["volta"], d, nome="Já marcou de novo")
    reserva(cur, F["volta"], -5, status="CONFIRMADA", nome="Já marcou de novo")
    reserva(cur, F["cancelou"], 200, status="CANCELADA", nome="Só cancelou")
    # O mesmo telefone gravado de três jeitos — tem de ser UMA pessoa com três reservas.
    f = F["formatos"]
    reserva(cur, f"({f[:2]}) {f[2:7]}-{f[7:]}", 300, nome="Nome antigo")
    reserva(cur, f"+55 {f}", 280, nome="Nome antigo")
    reserva(cur, f, 260, nome="Nome mais recente")
    reserva(cur, F["faltou"], 120, nome="Faltou uma")
    reserva(cur, F["faltou"], 110, status="NAO_COMPARECEU", nome="Faltou uma")
    # Cliente do site, que pediu para não receber WhatsApp: o nome vem do cadastro.
    cur.execute("""INSERT INTO reserva_clientes (id_unidade, telefone, nome, whatsapp_optout_em)
                   VALUES (%s, %s, 'Nome do cadastro', now()) RETURNING id""", (U, F["site"]))
    id_site = cur.fetchone()["id"]
    reserva(cur, F["site"], 95, nome="Nome na reserva", id_cliente=id_site)


def por_fone(plano):
    achados = {}
    for lista in ("vips", "organizadores", "adormecidos"):
        for x in plano[lista]:
            achados[x["telefone"]] = (lista, x)
    return achados


print("1. o padrão (3 reservas/120 dias, 2 grupos de 6+/120 dias, até 2/90 dias)")
st, p = chamar("GET", "/reservas/plano-de-acao", token=token)
checar("responde", st == 200, (st, p))
a = por_fone(p)
checar("traz os critérios usados", p["criterios"]["vip_reservas"] == 3
       and p["criterios"]["adormecido_dias"] == 90, p["criterios"])
checar("VIP sumido cai em VIPs", a.get(F["vip"], ("",))[0] == "vips", a.get(F["vip"]))
checar("organizador de dois grupos cai em organizadores (e não em adormecidos)",
       a.get(F["org"], ("",))[0] == "organizadores", a.get(F["org"]))
org = a.get(F["org"], (None, {}))[1]
checar("o organizador traz grupos, pessoas e o maior grupo",
       org.get("grupos") == 2 and org.get("pessoas") == 18 and org.get("maior_grupo") == 10, org)
checar("quem veio uma vez há 100 dias é adormecido", a.get(F["dorm"], ("",))[0] == "adormecidos")
checar("quem veio há 30 dias não entra", F["recente"] not in a)
checar("quem já tem reserva marcada para frente não entra", F["volta"] not in a)
checar("quem só cancelou não entra (não houve visita)", F["cancelou"] not in a)
fmt = a.get(F["formatos"], (None, {}))
checar("o mesmo telefone em três formatos é UMA pessoa com três reservas (VIP)",
       fmt[0] == "vips" and fmt[1].get("reservas") == 3, fmt)
checar("e o nome é o da reserva mais recente", fmt[1].get("nome") == "Nome mais recente", fmt)
fal = a.get(F["faltou"], (None, {}))[1]
checar("a falta conta à parte, não como reserva",
       fal.get("reservas") == 1 and fal.get("faltas") == 1, fal)
checar("e o 'sumiu há' é a última visita, não a falta", fal.get("dias") == 120, fal)
site = a.get(F["site"], (None, {}))[1]
checar("cliente do site: nome do cadastro e o id dele",
       site.get("nome") == "Nome do cadastro" and site.get("id_cliente") == id_site, site)
checar("e a marca de quem pediu para não receber WhatsApp", site.get("nao_quer_whatsapp") is True)
checar("o resumo soma as listas", p["resumo"]["total"] == len(p["vips"]) + len(
    p["organizadores"]) + len(p["adormecidos"]), p["resumo"])
checar("traz o nome da loja (para a mensagem)", bool(p.get("loja")))

print("\n2. os critérios mudam as listas")
st, p = chamar("GET", "/reservas/plano-de-acao?vip_dias=300&adormecido_dias=150", token=token)
a = por_fone(p)
checar("com VIP a 300 dias, o VIP de 200 sai de todas as listas",
       st == 200 and F["vip"] not in a, a.get(F["vip"]))
checar("com adormecido a 150 dias, o de 100 sai", F["dorm"] not in a)
st, p = chamar("GET", "/reservas/plano-de-acao?grupo_pessoas=9", token=token)
a = por_fone(p)
checar("com grupo grande a partir de 9, o organizador de 8 e 10 vira adormecido",
       a.get(F["org"], ("",))[0] == "adormecidos", a.get(F["org"]))
st, _r = chamar("GET", "/reservas/plano-de-acao?vip_dias=0", token=token)
checar("critério fora da faixa é recusado (422)", st == 422, st)

print("\n3. com o módulo desligado, a rota recusa")
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": False}, token)
st, _r = chamar("GET", "/reservas/plano-de-acao", token=token)
checar("409", st == 409, st)
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
