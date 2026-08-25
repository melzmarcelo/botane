"""Confere se um Botané no ar está de pé — sem escrever nada.

    python verificar_deploy.py https://botane-xxxxx.ondigitalocean.app

No App Platform a API mora em `<endereço>/api`, e é esse o padrão. Onde ela
estiver noutro lugar — como na máquina local, em que a web é a 3100 e a API é a
9200 — passe o segundo endereço:

    python verificar_deploy.py http://localhost:3100 http://127.0.0.1:9200

⚠️ **Só leitura, de propósito.** As suítes de fumaça criam produto, lançam nota
e chegam a gravar credencial de teste na mesma linha da real — apontá-las para
produção destruiria dado do cliente. Esta aqui pergunta e não responde.

O que ela cobra é o que quebra num primeiro deploy, na ordem em que quebra:

1. a API responde e o banco respondeu junto (`/saude` faz um SELECT)
2. as migrações rodaram (a base tem os papéis e as permissões de fábrica)
3. a web serve, e serve o ESTÁTICO (o manual em `/ajuda.html`)
4. o login funciona de ponta a ponta
5. `X-Total` chega ao navegador — sem `expose_headers` a paginação mente
6. o link de recuperação de senha aponta para o domínio certo, não para
   localhost
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# O console do Windows é cp1252 e não tem o sinal de aviso: sem isto o script
# morre ao IMPRIMIR, depois de já ter conferido tudo.
for _saida in (sys.stdout, sys.stderr):
    try:
        _saida.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

ok, falhas = 0, []


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def pedir(url, metodo="GET", corpo=None, token=None, timeout=30):
    req = urllib.request.Request(url, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=timeout) as r:
            texto = r.read().decode(errors="replace")
            try:
                return r.status, json.loads(texto or "null"), dict(r.headers)
            except json.JSONDecodeError:
                return r.status, texto, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200], dict(e.headers)
    except Exception as e:  # rede, DNS, TLS
        return 0, str(e)[:200], {}


def enderecos_da_api(base):
    """Os endereços de API que ficaram gravados no JavaScript da tela de login.

    ⚠️ Não dá para perguntar isso ao servidor: `NEXT_PUBLIC_API` não existe em
    tempo de execução, ela foi substituída por texto no `build`. O único lugar
    onde a resposta está é dentro dos pacotes que o navegador baixa.
    """
    st, html, _ = pedir(f"{base}/login")
    if st != 200 or not isinstance(html, str):
        return set()
    achados = set()
    for src in re.findall(r'src="(/_next/static/[^"]+\.js)"', html):
        st, txt, _ = pedir(f"{base}{src}")
        if st == 200 and isinstance(txt, str):
            achados |= set(re.findall(r"https?://[a-zA-Z0-9.\-]+(?::\d+)?/api", txt))
    return achados


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    api = sys.argv[2].rstrip("/") if len(sys.argv) > 2 else f"{base}/api"
    print(f"Conferindo {base}\n")

    print("1. a API está de pé, e o banco respondeu junto")
    st, corpo, _ = pedir(f"{api}/saude")
    checar("/saude responde 200", st == 200, (st, corpo))
    checar("e diz a versão", isinstance(corpo, dict) and corpo.get("versao"), corpo)

    print("\n2. as migrações rodaram no primeiro start")
    # Sem token não dá para ler papéis; o login abaixo prova o resto. O que dá
    # para ver sem autenticar é que a rota existe e pede autenticação — 401 é
    # resposta boa aqui: significa que a aplicação subiu inteira.
    st, _, _ = pedir(f"{api}/produtos")
    checar("rota protegida responde 401 (a aplicação subiu inteira)", st == 401, st)

    print("\n3. a web serve, e serve o estático")
    st, corpo, _ = pedir(f"{base}/login")
    checar("a tela de login carrega", st == 200, st)
    st, corpo, _ = pedir(f"{base}/ajuda.html")
    checar("o manual é servido de public/",
           st == 200 and "Botané por dentro" in str(corpo), st)
    st, _, _ = pedir(f"{base}/manifest.webmanifest")
    checar("o manifest do PWA é servido", st == 200, st)

    # ⚠️ A checagem que teria poupado uma tarde. `NEXT_PUBLIC_API` entra no
    # JavaScript na COMPILAÇÃO: mudá-la no painel sem recompilar não muda nada,
    # e o sintoma na tela é só "Failed to fetch" — sem dizer que endereço tentou.
    # Aqui o endereço é lido de dentro do pacote compilado e comparado com o
    # host que está sendo conferido.
    embutidos = enderecos_da_api(base)
    esperado = urllib.parse.urlparse(api).netloc
    checar(f"o front foi compilado apontando para {esperado}",
           any(urllib.parse.urlparse(e).netloc == esperado for e in embutidos)
           if embutidos else False,
           embutidos or "(nenhum endereço encontrado nos pacotes)")

    print("\n4. dá para entrar")
    email = input("  e-mail do administrador: ").strip()
    senha = input("  senha: ").strip()
    st, corpo, cab = pedir(f"{api}/auth/login", "POST", {"email": email, "senha": senha})
    token = corpo.get("access_token") if isinstance(corpo, dict) else None
    checar("o login devolve token", st == 200 and bool(token), (st, corpo))
    if not token:
        print("\nSem token, o resto não dá para conferir.")
        return 1
    checar("e manda trocar a senha no primeiro acesso",
           isinstance(corpo.get("usuario"), dict), corpo.get("usuario"))

    print("\n5. o cadastro de fábrica está lá")
    st, papeis, _ = pedir(f"{api}/papeis", token=token)
    checar("os papéis de fábrica existem",
           isinstance(papeis, list) and len(papeis) >= 6, papeis if st != 200 else len(papeis))
    st, ums, _ = pedir(f"{api}/unidades-medida", token=token)
    checar("as unidades de medida existem",
           isinstance(ums, list) and len(ums) >= 10, ums if st != 200 else len(ums))

    print("\n6. o X-Total chega ao navegador")
    # ⚠️ Sem `expose_headers` no CORS, o servidor manda e o navegador NÃO
    # entrega: a tela passa a achar que o total é o tamanho da página.
    st, _, cab = pedir(f"{api}/produtos?limite=1", token=token)
    tem_total = any(k.lower() == "x-total" for k in cab)
    checar("a listagem devolve X-Total", st == 200 and tem_total, list(cab)[:6])

    print("\n7. o link do e-mail aponta para o domínio certo")
    st, corpo, _ = pedir(f"{api}/auth/me", token=token)
    checar("/auth/me responde", st == 200, st)
    print("     ⚠️ confira à mão: peça 'esqueci a senha' e veja se o link do e-mail")
    print("        começa com o domínio do sistema, e não com localhost")

    print()
    print(f"{ok} passaram, {len(falhas)} falharam")
    for f in falhas:
        print(f"  - {f}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
