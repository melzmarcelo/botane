"""Vários WhatsApps por loja (um principal), o número do catálogo e o "entre em contato".

🔑 **Pedido do dono (30/10/2026)**, estudo em `docs/whatsapp-numeros-estudo.md`: a loja cadastra
mais de um WhatsApp e marca o principal; o catálogo escolhe o número que atende; e a opção
"permite entrar em contato" põe o botão no cabeçalho do catálogo (site e Cardápio Vivo).

    python tests/smoke_whatsapps_da_loja.py        (API de pé na 9200)
"""

import atexit
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_reserva  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
MARCA = str(time.time_ns() // 100)[-6:]
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

# 🔑 A suíte devolve os números da loja como os encontrou — com os MESMOS ids, que é o que os
# catálogos de verdade guardam.
with get_cursor() as cur:
    cur.execute("SELECT * FROM unidade_whatsapps WHERE id_unidade = %s", (U,))
    _numeros = [dict(x) for x in cur.fetchall()]
    cur.execute("SELECT whatsapp FROM unidades WHERE id = %s", (U,))
    _espelho = cur.fetchone()["whatsapp"]
    cur.execute("SELECT id, id_whatsapp FROM catalogos WHERE id_whatsapp IS NOT NULL")
    _dos_catalogos = [dict(x) for x in cur.fetchall()]


def _devolver():
    with get_cursor() as cur:
        cur.execute("DELETE FROM catalogos WHERE nome LIKE %s", (f"%{MARCA}%",))
        cur.execute("DELETE FROM unidade_whatsapps WHERE id_unidade = %s", (U,))
        # ⚠️ TODAS as colunas: desde a 146 a linha guarda a conexão com a Meta (token cifrado,
        # token de verificação do webhook) — devolver só rótulo e número a apagava.
        for n in _numeros:
            colunas = list(n)
            cur.execute(f"""INSERT INTO unidade_whatsapps ({', '.join(colunas)})
                            VALUES ({', '.join(['%s'] * len(colunas))})""", list(n.values()))
        cur.execute("UPDATE unidades SET whatsapp = %s WHERE id = %s", (_espelho, U))
        for c in _dos_catalogos:
            cur.execute("UPDATE catalogos SET id_whatsapp = %s WHERE id = %s",
                        (c["id_whatsapp"], c["id"]))


atexit.register(_devolver)
_st, par = chamar("GET", f"/unidades/{U}/parametros", token=token)
chamar("PUT", f"/unidades/{U}/parametros", {**par, "reservas_ligado": True}, token)


def loja():
    _st, lista = chamar("GET", "/unidades?incluir_inativas=true", token=token)
    return next(x for x in lista if x["id"] == U)


print("1. a loja cadastra vários WhatsApps e marca o principal")
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [
    {"rotulo": "Atendimento", "numero": "(99) 99999-0001", "principal": False},
    {"rotulo": "Encomendas", "numero": "(99) 99999-0002", "principal": True},
]}, token)
checar("grava a lista (só ela, sem reenviar a loja)", st == 200, (st, r))
l = loja()
checar("a lista volta com o principal primeiro",
       [w["rotulo"] for w in l["whatsapps"]] == ["Encomendas", "Atendimento"]
       and l["whatsapps"][0]["principal"], l.get("whatsapps"))
checar("e o campo da loja espelha o principal (o 'Entre em contato' de sempre)",
       l["whatsapp"] == "(99) 99999-0002", l.get("whatsapp"))
st, casa = chamar("GET", f"/publico/{U}/casa")
checar("o site recebe o principal, só dígitos", casa.get("whatsapp") == "99999990002", casa)
ENC, ATD = l["whatsapps"][0]["id"], l["whatsapps"][1]["id"]

st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [
    {"rotulo": "A", "numero": "(99) 99999-0001", "principal": True},
    {"rotulo": "B", "numero": "(99) 99999-0002", "principal": True}]}, token)
checar("dois principais: recusa", st == 422 and "principal" in r["detail"], (st, r))
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [
    {"rotulo": "A", "numero": "(99) 99999-0001"}, {"rotulo": "B", "numero": "99 999990001"}]}, token)
checar("o mesmo número duas vezes: recusa", st == 422 and "repetido" in r["detail"], (st, r))
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [{"rotulo": "A", "numero": "9999"}]}, token)
checar("número sem DDD: recusa", st == 422 and "incompleto" in r["detail"], (st, r))
checar("e nada mudou depois das recusas", [w["id"] for w in loja()["whatsapps"]] == [ENC, ATD])

print("\n2. o catálogo escolhe o número e liga o 'entre em contato'")
_st, cat = chamar("POST", "/catalogos", {"nome": f"Zap {MARCA}", "origem": "PRODUTOS"}, token)
ID = cat["id"]
chamar("POST", f"/catalogos/{ID}/categorias", {"nome": "Doces"}, token)
st, nums = chamar("GET", f"/catalogos/{ID}/whatsapps", token=token)
checar("o editor do catálogo lista os números da loja", st == 200 and {n["id"] for n in nums} == {ENC, ATD}, nums)
st, pv = chamar("GET", f"/catalogos/{ID}/previa-site", token=token)
checar("sem escolha: o catálogo usa o principal, e o botão vem desligado",
       pv.get("whatsapp") == "99999990002" and pv.get("contato") is False, pv)
st, c = chamar("PUT", f"/catalogos/{ID}", {"id_whatsapp": ATD, "permite_contato": True}, token)
checar("grava o número e o 'permite entrar em contato'",
       st == 200 and c["id_whatsapp"] == ATD and c["permite_contato"] is True, (st, c))
st, pv = chamar("GET", f"/catalogos/{ID}/previa-site", token=token)
checar("o site recebe o número DO CATÁLOGO e o botão ligado",
       pv.get("whatsapp") == "99999990001" and pv.get("contato") is True, pv)
st, r = chamar("PUT", f"/catalogos/{ID}", {"id_whatsapp": 999999}, token)
checar("número de fora da loja: recusa", st == 422, (st, r))
st, r = chamar("PUT", f"/catalogos/{ID}", {"situacao": "ATIVO"}, token)
st, pub = chamar("GET", f"/publico/{U}/catalogos/{ID}")
checar("no ar, o público recebe o mesmo número e o botão",
       st == 200 and pub.get("whatsapp") == "99999990001" and pub.get("contato") is True, (st, pub))

print("\n3. o Cardápio Vivo leva o botão no topo")
st, f = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID}", token=token)
checar("o feed recebe o contato com o número do catálogo",
       st == 200 and (f.get("contato") or {}).get("whatsapp") == "99999990001", (st, f.get("contato")))
chamar("PUT", f"/catalogos/{ID}", {"permite_contato": False}, token)
st, f = chamar("GET", f"/cardapio-vivo/previa?id_catalogo={ID}", token=token)
checar("desligado, o feed não traz o contato", st == 200 and f.get("contato") is None, f.get("contato"))
st, pub = chamar("GET", f"/publico/{U}/catalogos/{ID}")
checar("e o site também não, mas o número continua (é o do 'combinar o pagamento')",
       pub.get("contato") is False and pub.get("whatsapp") == "99999990001", pub)

print("\n4. apagar o número da lista devolve o catálogo ao principal")
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [
    {"id": ENC, "rotulo": "Encomendas", "numero": "(99) 99999-0002", "principal": True}]}, token)
checar("a lista fica só com o principal, o mesmo id", st == 200
       and [w["id"] for w in loja()["whatsapps"]] == [ENC], r)
st, c = chamar("GET", f"/catalogos/{ID}", token=token)
checar("o catálogo perdeu a escolha (volta ao principal)", c.get("id_whatsapp") is None, c)
_st, pub = chamar("GET", f"/publico/{U}/catalogos/{ID}")
checar("e o site passa a usar o principal", pub.get("whatsapp") == "99999990002", pub)
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": [
    {"rotulo": "Só um", "numero": "(99) 99999-0003"}]}, token)
checar("lista sem principal: o primeiro vira principal",
       loja()["whatsapps"][0]["principal"] and loja()["whatsapp"] == "(99) 99999-0003", loja())
st, r = chamar("PUT", f"/unidades/{U}", {"whatsapps": []}, token)
checar("lista vazia: a loja fica sem WhatsApp próprio (vale o da empresa)",
       st == 200 and loja()["whatsapps"] == [] and loja()["whatsapp"] is None, loja())
st, r = chamar("PUT", f"/unidades/{U}", {"telefone": loja()["telefone"]}, token)
checar("gravar a loja sem a lista não mexe nos números", st == 200 and loja()["whatsapps"] == [])

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
