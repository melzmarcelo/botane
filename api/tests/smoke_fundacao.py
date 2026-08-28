"""Teste de fumaça da etapa 1, contra a API local.

Roda o caminho inteiro: login, /me, permissão negada, CRUD de usuário e papel,
rotação de refresh e auditoria. Cria e desativa o que usa — não mexe em dado alheio.

    python tests/smoke_fundacao.py            (API precisa estar de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
TESTE_EMAIL = "smoke.cozinha@botane.com.br"
TESTE_SENHA = "smoke12345"

ok = 0
falhas: list[str] = []


def chamar(metodo: str, caminho: str, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        corpo_erro = e.read()
        try:
            return e.code, json.loads(corpo_erro or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": corpo_erro.decode(errors="replace")}


def checar(nome: str, condicao: bool, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


print("0. saúde: qual código está de pé")
# ⚠️ Sem isso não dava para separar "a correção não funcionou" de "a correção
# não foi publicada" — e a diferença entre as duas é um dia de trabalho. A
# `versao` é um texto fixo e não muda de um deploy para o outro; a `impressao`
# é do código de verdade, e o mesmo cálculo roda na máquina de quem publica.
st, r = chamar("GET", "/saude")
checar("responde sem autenticação (é a checagem de infra)", st == 200, (st, r))
checar("e diz que o banco respondeu", r.get("status") == "ok", r)
checar("com a impressão do código que está rodando",
       isinstance(r.get("impressao"), str) and len(r["impressao"]) == 12, r)
checar("e quantos arquivos entraram na conta", (r.get("arquivos") or 0) > 50, r)
# 🔑 **O TETO é o que pega o defeito de verdade.** A primeira versão usava lista
# NEGRA (excluir o que eu sabia nomear) e contou 136 arquivos aqui contra
# **2.014 na produção**: o buildpack instala as dependências dentro da pasta da
# API, com um nome que ninguém tinha previsto. O hash passou a incluir
# biblioteca de terceiros — a ferramenta feita para comparar O NOSSO código
# comparava outra coisa. Só o piso acima passaria feliz nos dois casos.
checar("e SÓ o nosso código entrou (dependência instalada ficaria de fora)",
       (r.get("arquivos") or 0) < 400, r)
# ⚠️ Estável entre chamadas: se mudasse sozinha (por ler dado de operação, ou
# por pontas de linha), responderia sempre "não é o mesmo código" e viraria um
# alarme que ninguém escuta.
st, r2 = chamar("GET", "/saude")
checar("a impressão não muda entre duas chamadas",
       r2.get("impressao") == r.get("impressao"), (r.get("impressao"), r2.get("impressao")))
checar("e a última migração aplicada vai junto",
       isinstance(r.get("migracao"), str) and r["migracao"].endswith(".sql"), r)

print("1. login")
st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": "errada"})
checar("senha errada devolve 401", st == 401, st)
st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
checar("login do admin devolve 200", st == 200, r)
token = r.get("access_token")
refresh = r.get("refresh_token")
checar("veio access e refresh", bool(token and refresh))
# O admin so nasce com trocar_senha=True; depois que ele troca, fica False.
checar("login informa se a senha precisa ser trocada",
       isinstance(r.get("usuario", {}).get("trocar_senha"), bool))

print("2. identidade e permissões")
st, me = chamar("GET", "/auth/me", token=token)
checar("/me responde", st == 200, me)
checar("admin tem todas as permissões", len(me.get("permissoes", [])) >= 30, len(me.get("permissoes", [])))
checar("admin é papel Administrador", "Administrador" in me.get("papeis", []))
checar("enxerga a loja inicial", len(me.get("unidades", [])) >= 1)
checar("todas_unidades = true", me.get("todas_unidades") is True)

st, r = chamar("GET", "/auth/me")
checar("sem token devolve 401", st == 401, st)
st, r = chamar("GET", "/auth/me", token="lixo")
checar("token inválido devolve 401", st == 401, st)

print("3. empresa")
st, emp = chamar("GET", "/empresa", token=token)
checar("GET /empresa responde", st == 200, emp)
nome_original = emp.get("nome_fantasia")   # o teste devolve o valor no fim
st, r = chamar("PUT", "/empresa", {"nome_fantasia": "Teste de gravação"}, token=token)
checar("PUT /empresa grava", st == 200, r)
st, emp = chamar("GET", "/empresa", token=token)
checar("gravou mesmo", emp.get("nome_fantasia") == "Teste de gravação", emp.get("nome_fantasia"))
chamar("PUT", "/empresa", {"nome_fantasia": nome_original}, token=token)
st, emp = chamar("GET", "/empresa", token=token)
checar("restaurou o nome da casa", emp.get("nome_fantasia") == nome_original, emp.get("nome_fantasia"))

print("4. papéis e usuário limitado")
st, papeis = chamar("GET", "/papeis", token=token)
checar("lista de papéis de fábrica", st == 200 and len(papeis) >= 6, len(papeis) if st == 200 else papeis)
cozinha = next((p for p in papeis if p["nome"] == "Cozinha"), None)
checar("papel Cozinha existe", cozinha is not None)
checar("Cozinha NÃO tem fichas.custos", cozinha and "fichas.custos" not in cozinha["permissoes"])
checar("Cozinha tem fichas.editar", cozinha and "fichas.editar" in cozinha["permissoes"])

# incluir inativos: a limpeza da rodada anterior desativa este usuário,
# e sem isso a busca não o acha e o POST bate em 409
st, r = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in r if u["email"] == TESTE_EMAIL), None) if st == 200 else None
if existente:
    id_teste = existente["id"]
    chamar("PUT", f"/usuarios/{id_teste}",
           {"ativo": True, "senha": TESTE_SENHA, "papeis": [{"id_papel": cozinha["id"]}]},
           token=token)
else:
    st, r = chamar("POST", "/usuarios", {
        "nome": "Smoke Cozinha", "email": TESTE_EMAIL, "senha": TESTE_SENHA,
        "papeis": [{"id_papel": cozinha["id"]}],
    }, token=token)
    checar("cria usuário", st == 201, r)
    id_teste = r.get("id")

st, r = chamar("POST", "/auth/login", {"email": TESTE_EMAIL, "senha": TESTE_SENHA})
checar("usuário limitado entra", st == 200, r)
token_cozinha = r.get("access_token")

print("5. permissão é conferida no servidor")
st, r = chamar("PUT", "/empresa", {"nome_fantasia": "Invadido"}, token=token_cozinha)
checar("cozinha NÃO edita empresa (403)", st == 403, st)
st, r = chamar("GET", "/usuarios", token=token_cozinha)
checar("cozinha NÃO lista usuários (403)", st == 403, st)
st, r = chamar("GET", "/auditoria", token=token_cozinha)
checar("cozinha NÃO vê auditoria (403)", st == 403, st)
st, r = chamar("GET", "/empresa", token=token_cozinha)
checar("cozinha LÊ a empresa (leitura é livre)", st == 200, st)
st, me_coz = chamar("GET", "/auth/me", token=token_cozinha)
# Contar permissões fazia esta checagem quebrar a cada chave nova — ruído que
# ensina a ignorar o vermelho. O que importa é o RECORTE: a cozinha tem o que é
# da cozinha e não tem o que é da administração.
perms_coz = set(me_coz.get("permissoes", []))
checar("cozinha tem as chaves da cozinha",
       {"fichas.visualizar", "estoque.saidas"} <= perms_coz, sorted(perms_coz))
checar("e nenhuma de administração",
       not any(p.startswith(("admin.", "usuarios.", "papeis.")) for p in perms_coz),
       sorted(perms_coz))

print("6. refresh rotaciona")
st, r2 = chamar("POST", "/auth/refresh", {"refresh_token": refresh})
checar("refresh devolve novo par", st == 200 and r2.get("refresh_token") != refresh, st)
st, r3 = chamar("POST", "/auth/refresh", {"refresh_token": refresh})
# 🔑 **Esta checagem MUDOU de sentido em 28/08/2026, e a troca é deliberada.**
# Antes ela cobrava 401 no ato: rotacionou, o antigo morreu. Mas as telas
# disparam várias chamadas juntas, e quando o access vencia todas renovavam com
# o MESMO refresh — a primeira rotacionava e as outras eram DESLOGADAS no meio
# do trabalho. Era a queixa "durante o uso fecha".
#
# Agora há uma janela curta (`REFRESH_GRACA_SEGUNDOS`) em que o token recém
# substituído ainda serve. O que se cobra aqui é que a janela exista e seja
# só isso: quem detalha as duas pontas — dentro e fora da graça, e o logout
# valendo na hora — é `smoke_sessao.py`.
checar("dentro da graça, o refresh recém-rotacionado ainda serve", st == 200, st)
checar("e a resposta traz outro par, sem reaproveitar o antigo",
       r3.get("refresh_token") not in (None, refresh), r3.get("refresh_token"))
novo_refresh = r2.get("refresh_token")
st, r4 = chamar("POST", "/auth/logout", {"refresh_token": novo_refresh}, token=r2["access_token"])
checar("logout responde", st == 200, r4)
st, r5 = chamar("POST", "/auth/refresh", {"refresh_token": novo_refresh})
checar("refresh após logout não vale (401)", st == 401, st)

print("7. auditoria")
st, log = chamar("GET", "/auditoria?limite=20", token=token)
checar("auditoria responde", st == 200, log)
acoes = {(l["entidade"], l["acao"]) for l in log} if st == 200 else set()
checar("registrou o login", ("sessao", "login") in acoes, acoes)
checar("registrou a alteração da empresa", ("empresa", "atualizar") in acoes, acoes)
# A regra é a mesma que `auditoria._limpar` promete cumprir: estes campos não
# chegam ao histórico. Procurar a *palavra* "senha" seria mais fácil e estaria
# errado — `trocar_senha` é um sinalizador booleano, não um segredo, e acusá-lo
# esconderia o dia em que um segredo de verdade passar.
PROIBIDOS = {"senha", "senha_hash", "credenciais", "refresh_hash", "app_secret",
             "client_secret", "password"}
checar("nenhum campo de credencial chega ao log",
       all(not (PROIBIDOS & set((l.get("depois") or {}).keys())) for l in log),
       [set((l.get("depois") or {}).keys()) & PROIBIDOS for l in log if
        PROIBIDOS & set((l.get("depois") or {}).keys())])
tudo = json.dumps(log, ensure_ascii=False)
checar("e nenhuma senha usada neste teste aparece como valor",
       ADMIN[1] not in tudo and TESTE_SENHA not in tudo)

print("0b. a senha de desenvolvimento não sobe para produção")
# ⚠️ O primeiro deploy real subiu com `admin@botane.com.br` / `botane123` porque
# as variáveis não foram definidas no painel — e a senha está escrita no README,
# que é público. Nada avisou: a linha "administrador criado" saiu igual à de
# sempre. Agora, com DEBUG desligado, o start PARA. Parar é o único aviso que
# ninguém deixa passar.
import subprocess  # noqa: E402

_prova = subprocess.run(
    [sys.executable, "-c", """
import sys
sys.path.insert(0, ".")
import main, config

class Cur:
    def execute(self, sql, *a, **k): pass
    def fetchone(self): return {"n": 0, "id": 1}
class Ctx:
    def __enter__(self): return Cur()
    def __exit__(self, *a): return False

main.get_cursor = lambda: Ctx()
main.DEBUG = False
main.ADMIN_SENHA = config.ADMIN_SENHA_PADRAO
main.ADMIN_EMAIL = "dono@casa.com.br"
try:
    main.garantir_admin()
    print("CRIOU")
except RuntimeError as e:
    print("RECUSOU", "README" in str(e))
"""],
    capture_output=True, text=True, cwd=".",
)
checar("com DEBUG desligado, o start recusa a senha padrão",
       "RECUSOU" in _prova.stdout, (_prova.stdout[:120], _prova.stderr[:120]))
checar("e a recusa diz onde a senha está publicada",
       "True" in _prova.stdout, _prova.stdout[:120])

print("8. limpeza")
if id_teste:
    st, r = chamar("DELETE", f"/usuarios/{id_teste}", token=token)
    checar("desativa o usuário de teste", st == 200, r)
    st, r = chamar("POST", "/auth/login", {"email": TESTE_EMAIL, "senha": TESTE_SENHA})
    checar("usuário desativado não entra (403)", st == 403, st)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
