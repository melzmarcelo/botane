"""Sessão: quando ela morre, quando ela dura, e a corrida que a matava cedo.

Duas queixas opostas ao mesmo tempo, em 28/08/2026: *"fecho o navegador e volto
logado ainda"* e *"aí durante o uso fecha"*. São defeitos diferentes:

* a sessão sobrevivia ao fechamento porque o token ficava sempre em
  `localStorage`, e o refresh valia 30 dias para todo mundo;
* a sessão caía no meio do uso porque o refresh é ROTATIVO e o cliente não
  tinha trava: várias chamadas paralelas levavam 401 juntas, todas renovavam
  com o MESMO token, a primeira revogava e as outras eram deslogadas.

O que este arquivo cobra:

1. login sem "manter conectado" nasce com validade CURTA
2. com "manter conectado", nasce com a validade longa
3. a rotação PRESERVA o modo — renovar não promove sessão curta a 30 dias
4. **a corrida não derruba a sessão**: dois refresh com o mesmo token, como
   duas abas fariam, e os dois passam pela janela de graça
5. token revogado FORA da janela continua recusado — a graça é curta, não é
   um perdão permanente
6. o logout revoga de verdade
7. o padrão do servidor é a sessão curta: cliente que não manda o campo não
   ganha 30 dias por omissão

    python tests/smoke_sessao.py            (API de pé na 9200)

⚠️ Cria as próprias sessões e as encerra no fim. Não mexe na senha de ninguém.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from config import REFRESH_EXPIRY_DIAS, REFRESH_SESSAO_HORAS  # noqa: E402
from database import get_cursor  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=30) as r:
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


def entrar(manter):
    st, r = chamar("POST", "/auth/login",
                   {"email": ADMIN[0], "senha": ADMIN[1], "manter_conectado": manter})
    return st, r


def horas_de_validade(refresh: str) -> float:
    """Quanto vale este refresh, lido do banco — o cliente não recebe isso."""
    import hashlib
    h = hashlib.sha256(refresh.encode()).hexdigest()
    with get_cursor() as cur:
        cur.execute(
            "SELECT persistente, extract(epoch FROM (expira_em - now()))/3600 AS h "
            "FROM sessoes WHERE refresh_hash = %s", (h,))
        linha = cur.fetchone()
    return (linha["h"], linha["persistente"]) if linha else (None, None)


print("1. sem 'manter conectado': sessão do navegador, validade curta")
st, curta = entrar(False)
checar("o login funciona", st == 200, (st, curta))
h, persistente = horas_de_validade(curta["refresh_token"])
checar(f"a sessão nasce NÃO persistente", persistente is False, persistente)
# ⚠️ A promessa "fecha com o navegador" é do front; quem a GARANTE é esta
# validade. Token copiado não está preso ao navegador de ninguém.
checar(f"e vale ~{REFRESH_SESSAO_HORAS}h, não {REFRESH_EXPIRY_DIAS} dias",
       h is not None and abs(h - REFRESH_SESSAO_HORAS) < 1, h)


print("\n2. com 'manter conectado': a validade longa de sempre")
st, longa = entrar(True)
h2, persistente2 = horas_de_validade(longa["refresh_token"])
checar("a sessão nasce persistente", persistente2 is True, persistente2)
checar(f"e vale ~{REFRESH_EXPIRY_DIAS} dias",
       h2 is not None and abs(h2 - REFRESH_EXPIRY_DIAS * 24) < 2, h2)


print("\n3. a rotação preserva o modo")
# ⚠️ Sem isso, renovar promoveria a sessão curta a 30 dias: a escolha da pessoa
# duraria até a primeira renovação e depois sumiria, sem nada avisando.
st, r = chamar("POST", "/auth/refresh", {"refresh_token": curta["refresh_token"]})
checar("renovar a sessão curta funciona", st == 200, (st, r))
h3, persistente3 = horas_de_validade(r["refresh_token"])
checar("e ela continua NÃO persistente", persistente3 is False, persistente3)
checar(f"com a validade curta de novo (~{REFRESH_SESSAO_HORAS}h)",
       h3 is not None and abs(h3 - REFRESH_SESSAO_HORAS) < 1, h3)
curta_atual = r["refresh_token"]


print("\n4. a CORRIDA não derruba mais a sessão")
# 🔑 O caso real: as telas disparam várias chamadas juntas (Integrações pede
# quatro). Quando o access vence, todas levam 401 e todas renovam com o MESMO
# refresh. Antes, a primeira revogava e as outras eram deslogadas no meio do
# trabalho. Aqui as duas chamadas usam o mesmo token de propósito.
st0, sessao = entrar(True)
token_repetido = sessao["refresh_token"]
with ThreadPoolExecutor(max_workers=3) as pool:
    respostas = list(pool.map(
        lambda _: chamar("POST", "/auth/refresh", {"refresh_token": token_repetido}),
        range(3)))
codigos = [c for c, _ in respostas]
checar("as três renovações simultâneas passam", all(c == 200 for c in codigos), codigos)
checar("e cada uma devolve um refresh próprio",
       len({r["refresh_token"] for _, r in respostas if r.get("refresh_token")}) == 3,
       codigos)


print("\n5. mas a graça é curta, não é perdão permanente")
# Envelhece a substituição à mão: é o token que sobrou de uma rotação de ontem.
# ⚠️ Quem governa a graça é `substituida_em`, NÃO `revogada_em` — envelhecer só
# a segunda deixava o token passar, e foi assim que este teste descobriu que os
# dois campos existem por motivos diferentes.
import hashlib  # noqa: E402
h_velho = hashlib.sha256(token_repetido.encode()).hexdigest()
with get_cursor() as cur:
    cur.execute("""UPDATE sessoes
                      SET revogada_em = now() - interval '1 hour',
                          substituida_em = now() - interval '1 hour'
                    WHERE refresh_hash = %s""", (h_velho,))
st, r = chamar("POST", "/auth/refresh", {"refresh_token": token_repetido})
checar("token substituído há uma hora é recusado", st == 401, (st, r))
checar("e a recusa manda entrar de novo",
       "expirada" in str(r.get("detail", "")).lower(), r.get("detail"))


print("\n6. o logout revoga de verdade")
st, nova = entrar(False)
st, r = chamar("POST", "/auth/logout", {"refresh_token": nova["refresh_token"]},
               token=nova["access_token"])
checar("o logout responde", st in (200, 204), (st, r))
st, r = chamar("POST", "/auth/refresh", {"refresh_token": nova["refresh_token"]})
# 🔑 **A regressão que este teste pegou.** A primeira versão da graça olhava só
# `revogada_em`, que o logout também preenche: sair da conta deixava o refresh
# valendo mais 30 segundos. Sair vale na hora, sempre — a folga é para a
# rotação, e só para ela.
checar("e o refresh dele não vale mais NA HORA (a graça não perdoa logout)",
       st == 401, (st, r))
with get_cursor() as cur:
    cur.execute("SELECT revogada_em, substituida_em FROM sessoes WHERE refresh_hash = %s",
                (hashlib.sha256(nova["refresh_token"].encode()).hexdigest(),))
    linha = cur.fetchone()
checar("o logout revoga sem marcar substituição",
       linha and linha["revogada_em"] is not None and linha["substituida_em"] is None,
       dict(linha) if linha else None)


print("\n7. o padrão do servidor é a sessão CURTA")
# ⚠️ Cliente antigo (ou script) que não mande o campo não pode ganhar 30 dias
# por omissão: a opção segura tem de ser a que vale para quem não escolheu.
st, sem_campo = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
checar("login sem o campo funciona", st == 200, st)
h7, persistente7 = horas_de_validade(sem_campo["refresh_token"])
checar("e a sessão nasce NÃO persistente", persistente7 is False, persistente7)

# limpeza: encerra o que este arquivo abriu
for s in (longa, sessao, sem_campo):
    if s.get("refresh_token"):
        chamar("POST", "/auth/logout", {"refresh_token": s["refresh_token"]},
               token=s.get("access_token"))
chamar("POST", "/auth/logout", {"refresh_token": curta_atual})

print(f"\n{ok} ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
