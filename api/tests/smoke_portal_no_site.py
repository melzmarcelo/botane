"""Reservas e Fidelidade VISÍVEIS no site (migração 144).

🔑 **Pedido do dono (30/10/2026):** *"nas configurações das reservas, criar uma opção se as
reservas vão estar visíveis no site. Fazer isto também para a Fidelidade. Caso desmarcado, não
aparecerá o botão desta ação."* ⚠️ Esconder não é desligar: a fidelidade continua valendo
(o QR da mesa) e a configuração das reservas não muda.

    python tests/smoke_portal_no_site.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import init_pool  # noqa: E402

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
preservar_reserva(U)  # devolve a reserva_config inteira (as marcas novas também) no fim
chamar("PUT", f"/unidades/{U}/parametros", {"reservas_ligado": True}, token)


def configurar(**mudancas):
    _st, cfg = chamar("GET", "/reservas/configuracao", token=token)
    corpo = {**cfg, "fidelidade_ligada": True,
             "horarios": [{"dia_semana": d, "aberto": True, "abre": "00:00", "fecha": "23:59",
                           "ultima_reserva": "23:00"} for d in range(1, 8)],
             **mudancas}
    return chamar("PUT", "/reservas/configuracao", corpo, token)


print("1. o padrão: as duas visíveis")
_st, cfg = chamar("GET", "/reservas/configuracao", token=token)
checar("a configuração traz as duas marcas",
       "reservas_no_site" in cfg and "fidelidade_no_site" in cfg, list(cfg))
st, r = configurar(reservas_no_site=True, fidelidade_no_site=True)
checar("grava", st == 200, (st, r))
_st, casa = chamar("GET", f"/publico/{U}/casa")
checar("o site recebe as duas ligadas", casa.get("reservas_no_site") is True
       and casa.get("fidelidade_no_site") is True and casa.get("fidelidade") is not None, casa)

print("\n2. desmarcadas: o site esconde os botões")
st, r = configurar(reservas_no_site=False, fidelidade_no_site=False)
checar("grava as duas desmarcadas", st == 200 and r.get("reservas_no_site") is False
       and r.get("fidelidade_no_site") is False, (st, r))
_st, casa = chamar("GET", f"/publico/{U}/casa")
checar("o site recebe as duas desligadas",
       casa.get("reservas_no_site") is False and casa.get("fidelidade_no_site") is False, casa)
checar("e a fidelidade continua valendo (esconder não é desligar: o QR da mesa conta)",
       casa.get("fidelidade") is not None, casa.get("fidelidade"))
st, h = chamar("GET", f"/publico/{U}/horarios?dia=2030-01-02&pessoas=2")
checar("e a agenda continua respondendo", st == 200, (st, h))

print("\n3. uma sem a outra")
configurar(reservas_no_site=False, fidelidade_no_site=True)
_st, casa = chamar("GET", f"/publico/{U}/casa")
checar("só as reservas escondidas", casa.get("reservas_no_site") is False
       and casa.get("fidelidade_no_site") is True, casa)
st, r = chamar("GET", "/reservas/configuracao", token=token)
corpo = {k: v for k, v in r.items() if k not in ("reservas_no_site", "fidelidade_no_site")}
st, r = chamar("PUT", "/reservas/configuracao", corpo, token)
checar("cliente antigo (sem as marcas no corpo) deixa as duas visíveis, o padrão",
       st == 200 and r.get("reservas_no_site") is True and r.get("fidelidade_no_site") is True, (st, r))

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
