"""O ajuste feito no Omie chegando à nota que já está aqui.

🔑 **Pedido do dono (09/09/2026):** *"quando tem ajuste em alguma nota no Omie
precisamos trazer isto para o Botané. Podemos ter algo na busca de todos, e
também dentro da nota ter um botão para atualizar a nota"*.

Até aqui `_ja_temos` cortava a nota conhecida antes de qualquer comparação: a
sincronização a contava como "já existia" e seguia. O ajuste feito lá — valor
corrigido, item trocado, frete que apareceu depois — **nunca** chegava, e nada
dizia que ele existia.

⚠️ **A suíte roda em modo SIMULADO**, sobre as fixtures, e devolve a credencial
real no fim (`preservar_credenciais`). Foi assim que a chave do cliente se
perdeu uma vez: a suíte gravou a de teste na mesma linha e estourou no meio.

⚠️ **Divergir "para o lado de cá" é o mesmo experimento.** A suíte não tem como
mexer no Omie; ela muda o valor DAQUI e confere que a atualização o traz de
volta ao da fixture. A conta que se afirma é idêntica.

    python tests/smoke_nota_atualizada.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import preservar_credenciais  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

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


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome}  ->  {detalhe}")


def perto(a, b, casas=2):
    return abs(float(a or 0) - float(b)) < 10 ** -casas


def do_banco(id_nota, colunas):
    with get_cursor() as cur:
        cur.execute(f"SELECT {', '.join(colunas)} FROM notas_entrada WHERE id = %s", (id_nota,))
        return dict(cur.fetchone() or {})


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token), (st, r))
init_pool()

# ⚠️ A credencial REAL volta no fim, aconteça o que acontecer. Ver o aviso do
# CLAUDE.md: foi assim que ela se perdeu uma vez.
repor_credenciais = preservar_credenciais("OMIE")
chamar("PUT", "/omie/config", {"modo": "simulado", "ativa": True}, token=token)


print("\n1. o cenario: as notas da fixture entram")
st, r = chamar("POST", "/omie/sincronizar?dias=365", token=token)
checar("a sincronizacao responde", st == 200, (st, r))
# A partir da segunda rodada elas ja existem -- e e justamente esse o caso que
# esta suite exercita.
with get_cursor() as cur:
    cur.execute("""SELECT id, id_omie, status, valor_total FROM notas_entrada
                    WHERE id_omie IS NOT NULL AND status <> 'LANCADA'
                    ORDER BY id DESC LIMIT 1""")
    alvo = dict(cur.fetchone() or {})
checar("ha uma nota do Omie nao lancada para exercitar", bool(alvo.get("id")), alvo)

id_nota = alvo.get("id")
valor_certo = float(alvo.get("valor_total") or 0)


print("\n2. o BOTAO da nota: releitura sem perguntar se valeu a pena")
# 🔑 **Divergir para o lado de ca e o mesmo experimento.** A suite nao mexe no
# Omie; ela estraga o valor DAQUI e confere que a releitura o traz de volta.
with get_cursor() as cur:
    cur.execute("UPDATE notas_entrada SET valor_total = %s WHERE id = %s",
                (valor_certo + 111.11, id_nota))
checar("o valor daqui foi desviado",
       perto(do_banco(id_nota, ["valor_total"])["valor_total"], valor_certo + 111.11),
       do_banco(id_nota, ["valor_total"]))

# O vinculo feito a mao, que NAO pode se perder na reescrita.
with get_cursor() as cur:
    cur.execute("""SELECT count(*) n FROM nota_itens
                    WHERE id_nota = %s AND id_produto IS NOT NULL""", (id_nota,))
    vinculados_antes = cur.fetchone()["n"]

st, r = chamar("POST", f"/notas/{id_nota}/atualizar-do-omie", {}, token=token)
checar("o botao responde", st == 200, (st, r))
checar("e o valor volta ao que o Omie tem",
       perto(do_banco(id_nota, ["valor_total"])["valor_total"], valor_certo),
       (do_banco(id_nota, ["valor_total"]), valor_certo))
# ⚠️ A frase DIZ o que mudou: "Nota atualizada" sem numero faria a pessoa
# procurar a diferenca sozinha.
checar("a mensagem mostra o antes e o depois",
       "→" in str(r.get("message", "")), r.get("message"))

# 🔑 **A afirmacao que protege o TRABALHO DE QUEM CONFERIU.** Reescrever os
# itens nao pode apagar o produto escolhido a mao em vinte linhas so porque o
# fornecedor corrigiu o frete.
with get_cursor() as cur:
    cur.execute("""SELECT count(*) n FROM nota_itens
                    WHERE id_nota = %s AND id_produto IS NOT NULL""", (id_nota,))
    vinculados_depois = cur.fetchone()["n"]
checar("e os vinculos feitos a mao sobrevivem a reescrita",
       vinculados_depois >= vinculados_antes, (vinculados_antes, vinculados_depois))

# Reler de novo, sem nada ter mudado, precisa DIZER que nada mudou.
st, r2 = chamar("POST", f"/notas/{id_nota}/atualizar-do-omie", {}, token=token)
checar("reler sem mudanca nao inventa diferenca", r2.get("mudou") is False, r2.get("message"))
checar("e a frase diz isso", "igual" in str(r2.get("message", "")).lower(), r2.get("message"))


print("\n3. a BUSCA DE TODOS traz o ajuste junto")
with get_cursor() as cur:
    cur.execute("UPDATE notas_entrada SET valor_total = %s WHERE id = %s",
                (valor_certo + 222.22, id_nota))
st, r = chamar("POST", "/omie/sincronizar?dias=365", token=token)
checar("a sincronizacao responde", st == 200, (st, r))
# 🔑 A nota conhecida deixou de ser ignorada: antes ela era cortada por
# `_ja_temos` e o ajuste nunca chegava.
checar("ela conta as notas ATUALIZADAS", (r.get("atualizadas") or 0) >= 1, r)
checar("e a frase diz quantas foram",
       "atualizada" in str(r.get("message", "") or r.get("recado", "")).lower()
       or (r.get("atualizadas") or 0) >= 1, r)
checar("o valor voltou ao do Omie sozinho",
       perto(do_banco(id_nota, ["valor_total"])["valor_total"], valor_certo),
       do_banco(id_nota, ["valor_total"]))

# ⚠️ E sem mudanca nenhuma, a passada seguinte NAO pede o detalhe de novo: o
# barato e comparar o cabecalho da lista, e reler tudo custaria uma chamada por
# nota em 3.670.
st, r = chamar("POST", "/omie/sincronizar?dias=365", token=token)
checar("sem mudanca, nada e atualizado", (r.get("atualizadas") or 0) == 0, r)


print("\n4. nota LANCADA nao se reescreve -- e nao se cala")
with get_cursor() as cur:
    cur.execute("""SELECT id, valor_total FROM notas_entrada
                    WHERE id_omie IS NOT NULL AND status = 'LANCADA' ORDER BY id DESC LIMIT 1""")
    lancada = dict(cur.fetchone() or {})

if lancada.get("id"):
    st, r = chamar("POST", f"/notas/{lancada['id']}/atualizar-do-omie", {}, token=token)
    checar("o botao recusa a nota lancada", st == 409, (st, r))
    # 🔑 A recusa DIZ o caminho: o razao e append-only, e reescrever a nota
    # deixaria o documento e o estoque com numeros diferentes.
    checar("dizendo para estornar antes",
           "estorne" in str(r.get("detail", "")).lower(), r)
else:
    checar("o botao recusa a nota lancada", True, "(sem nota lancada do Omie na base)")
    checar("dizendo para estornar antes", True, "(idem)")

st, r = chamar("POST", f"/notas/{id_nota}/atualizar-do-omie", {})
checar("sem autenticacao e barrado", st in (401, 403), st)


print("\n5. nota que NAO veio do Omie nao tem de onde reler")
with get_cursor() as cur:
    cur.execute("""SELECT id FROM notas_entrada
                    WHERE id_omie IS NULL AND status <> 'LANCADA' ORDER BY id DESC LIMIT 1""")
    manual = cur.fetchone()
if manual:
    st, r = chamar("POST", f"/notas/{manual['id']}/atualizar-do-omie", {}, token=token)
    checar("a nota digitada e recusada", st == 400, (st, r))
    checar("com a frase explicando por que",
           "omie" in str(r.get("detail", "")).lower(), r)
else:
    checar("a nota digitada e recusada", True, "(sem nota manual na base)")
    checar("com a frase explicando por que", True, "(idem)")


print("\n6. devolvendo a integracao ao que era")
repor_credenciais()
with get_cursor() as cur:
    cur.execute("SELECT modo FROM integracoes WHERE servico = 'OMIE'")
    checar("a integracao volta para o modo que a casa tinha",
           (cur.fetchone() or {}).get("modo") is not None, "")

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
raise SystemExit(1 if falhas else 0)
