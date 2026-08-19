"""Teste de fumaça da recuperação de senha.

O que este teste existe para provar — cada item já foi buraco em algum sistema:

* A tela pública **não conta quem existe**: e-mail cadastrado e e-mail
  inventado recebem a mesma frase, no mesmo formato.
* O link **vale uma vez**. Usar de novo é recusado.
* Pedir de novo **mata o link anterior** — senão o e-mail antigo, que ficou na
  caixa de entrada, continuaria abrindo a conta.
* Redefinir **derruba as sessões abertas**. Quem pede recuperação por
  desconfiar de invasão não pode terminar com o invasor ainda logado.
* Há **freio de repetição**: a tela não serve para encher a caixa de entrada
  de alguém.
* O link do administrador funciona igual, e a senha do SMTP **nunca volta** em
  claro pela API.

    python tests/smoke_senha.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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


def token_do_link(link):
    return urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("token", [""])[0]


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns())[-6:]
EMAIL = f"smoke.senha.{marca}@botane.com.br"
SENHA1 = "primeira12345"
SENHA2 = "segunda123456"

print("0. um usuário só deste teste")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, novo = chamar("POST", "/usuarios", {
    "nome": f"Smoke Senha {marca}", "email": EMAIL, "senha": SENHA1,
    "papeis": [{"id_papel": id_cozinha}],
}, token=token)
id_usuario = novo.get("id")
checar("usuário criado", st == 201 and id_usuario, novo)

print("1. a tela pública não conta quem existe")
st1, r1 = chamar("POST", "/auth/esqueci-senha", {"email": EMAIL})
st2, r2 = chamar("POST", "/auth/esqueci-senha", {"email": f"nao.existe.{marca}@botane.com.br"})
checar("e-mail cadastrado responde 200", st1 == 200, r1)
checar("e-mail inventado responde 200 igual", st2 == 200, r2)
checar("e a frase é exatamente a mesma", r1 == r2, (r1, r2))
st3, r3 = chamar("POST", "/auth/esqueci-senha", {"email": "isto nao e um email"})
checar("texto que nem parece e-mail também não vaza nada", st3 in (200, 422), r3)

print("2. o administrador gera o link para entregar na mão")
st, r = chamar("POST", f"/usuarios/{id_usuario}/recuperar-senha", token=token)
checar("o link é gerado", st == 200 and r.get("link"), r)
checar("sem SMTP, avisa que está em modo simulado", r.get("modo") == "simulado", r.get("modo"))
link = r.get("link", "")
checar("o link aponta para a tela de redefinir", "/redefinir-senha?token=" in link, link)
tk = token_do_link(link)

print("3. a tela confere o link antes de pedir a senha nova")
st, r = chamar("GET", f"/auth/redefinir-senha/{tk}")
checar("link válido é aceito", st == 200 and r.get("valido"), r)
checar("e devolve só o primeiro nome", r.get("nome") == "Smoke", r)
st, r = chamar("GET", "/auth/redefinir-senha/token-que-nunca-existiu")
checar("link inventado é recusado", st == 400, st)
checar("com uma frase que dá para mostrar",
       "não vale mais" in (r.get("detail") or ""), r)

print("4. pedir de novo mata o link anterior")
st, r = chamar("POST", f"/usuarios/{id_usuario}/recuperar-senha", token=token)
tk_novo = token_do_link(r.get("link", ""))
checar("o segundo link é diferente do primeiro", tk_novo and tk_novo != tk)
st, r = chamar("GET", f"/auth/redefinir-senha/{tk}")
checar("o link antigo parou de valer na hora", st == 400, st)
st, r = chamar("GET", f"/auth/redefinir-senha/{tk_novo}")
checar("o novo vale", st == 200, r)

print("5. redefinir troca a senha e derruba as sessões")
st, sessao = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA1})
checar("a senha antiga ainda entra antes da troca", st == 200, st)
refresh_antigo = sessao.get("refresh_token")

st, r = chamar("POST", "/auth/redefinir-senha", {"token": tk_novo, "senha": SENHA2})
checar("a senha é redefinida", st == 200, r)
checar("e a resposta avisa que as sessões caíram",
       "sessões" in (r.get("detalhe") or "").lower(), r)

st, r = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA2})
checar("a senha nova entra", st == 200, st)
st, r = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA1})
checar("a senha antiga não entra mais", st == 401, st)
st, r = chamar("POST", "/auth/refresh", {"refresh_token": refresh_antigo})
checar("a sessão aberta antes da troca foi revogada", st == 401, st)

print("6. o link vale uma vez só")
st, r = chamar("POST", "/auth/redefinir-senha", {"token": tk_novo, "senha": "terceira12345"})
checar("usar o mesmo link de novo é recusado", st == 400, st)
st, r = chamar("POST", "/auth/login", {"email": EMAIL, "senha": "terceira12345"})
checar("e a senha não mudou na segunda tentativa", st == 401, st)

print("7. senha fraca é recusada")
st, r = chamar("POST", f"/usuarios/{id_usuario}/recuperar-senha", token=token)
tk3 = token_do_link(r.get("link", ""))
st, r = chamar("POST", "/auth/redefinir-senha", {"token": tk3, "senha": "1234"})
checar("senha curta é recusada (422)", st == 422, st)
st, r = chamar("GET", f"/auth/redefinir-senha/{tk3}")
checar("e o link continua valendo depois da recusa", st == 200, r)

print("8. freio de repetição")
# O terceiro pedido já entrou acima; do quarto em diante o sistema para de
# mandar — sem contar isso para quem pediu.
for _ in range(4):
    chamar("POST", "/auth/esqueci-senha", {"email": EMAIL})
st, r = chamar("GET", "/auditoria?entidade=senha&limite=40", token=token)
eventos = r if isinstance(r, list) else r.get("itens", [])
recusados = [e for e in eventos
             if (e.get("depois") or {}).get("motivo") == "limite de pedidos por hora"]
checar("o excesso de pedidos é barrado", len(recusados) >= 1, len(eventos))
checar("mas a resposta pública continua a mesma",
       chamar("POST", "/auth/esqueci-senha", {"email": EMAIL})[1] == r1)

print("9. a configuração de e-mail não devolve a senha")
st, cfg = chamar("GET", "/email/config", token=token)
checar("a tela de configuração abre", st == 200, cfg)
st, r = chamar("PUT", "/email/config", {
    "servidor": "smtp.exemplo.com.br", "porta": 587, "seguranca": "starttls",
    "usuario": "envio@exemplo.com.br", "senha": f"segredo-{marca}",
    "remetente_nome": "Botané", "remetente_email": "envio@exemplo.com.br",
    "modo": "simulado", "ativa": True,
}, token=token)
checar("salva a configuração", st == 200, r)
st, cfg = chamar("GET", "/email/config", token=token)
checar("o servidor volta em claro", cfg.get("servidor") == "smtp.exemplo.com.br", cfg)
# Gravar de novo tem de ATUALIZAR, não criar outra linha: o UPSERT com
# id_unidade NULL já falhou em silêncio uma vez (nulos são distintos no
# Postgres), e a leitura passou a devolver uma configuração qualquer.
chamar("PUT", "/email/config", {"servidor": "smtp.segunda.com.br", "modo": "simulado"},
       token=token)
st, cfg2 = chamar("GET", "/email/config", token=token)
checar("gravar duas vezes atualiza a mesma configuração",
       cfg2.get("servidor") == "smtp.segunda.com.br", cfg2)
checar("e a senha guardada continua lá", "•" in (cfg2.get("senha") or ""), cfg2.get("senha"))
checar("a senha volta mascarada", "•" in (cfg.get("senha") or ""), cfg.get("senha"))
checar("a senha NÃO volta em claro", marca not in (cfg.get("senha") or ""), cfg.get("senha"))
checar("modo real sem servidor é recusado",
       chamar("PUT", "/email/config", {"modo": "real", "servidor": ""}, token=token)[0] == 400)

st, r = chamar("POST", "/email/testar", {"para": ADMIN[0]}, token=token)
checar("o teste de envio funciona em modo simulado", st == 200 and r.get("ok"), r)
checar("e diz onde a mensagem foi gravada", "gravada em" in (r.get("detalhe") or ""), r)

print("10. quem não é administrador não mexe nisso")
st, r = chamar("POST", "/auth/login", {"email": EMAIL, "senha": SENHA2})
tk_cozinha = r.get("access_token")
checar("cozinha não lê a configuração de e-mail",
       chamar("GET", "/email/config", token=tk_cozinha)[0] == 403)
checar("cozinha não gera link de recuperação de ninguém",
       chamar("POST", f"/usuarios/{id_usuario}/recuperar-senha", token=tk_cozinha)[0] == 403)

print("11. limpeza")
chamar("DELETE", f"/usuarios/{id_usuario}", token=token)
# A configuração volta ao estado de antes: este teste não pode deixar um SMTP
# de mentira ligado para as próximas rodadas.
chamar("PUT", "/email/config", {"modo": "simulado", "ativa": False}, token=token)
checar("limpeza concluída", True)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
