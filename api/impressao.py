"""A impressão digital do código que está rodando.

Existe por uma pergunta que custou uma ida e volta: **o que está no ar é o
commit que eu publiquei?** A `VERSAO` é um texto fixo no código e não muda de
um deploy para o outro; a lista de rotas só muda quando alguém cria um
endpoint; e uma correção de comportamento — um prazo de socket, por exemplo —
não deixa rastro nenhum de fora. Ficava impossível separar "a correção não
funcionou" de "a correção não foi publicada", que são coisas muito diferentes.

Aqui o `/saude` passa a devolver um resumo do PRÓPRIO código: o mesmo cálculo
roda na máquina de quem publicou e os dois números se comparam.

⚠️ **As pontas de linha são normalizadas antes do hash.** O repositório é
clonado com CRLF no Windows e com LF no contêiner Linux — sem normalizar, o
mesmo commit daria impressões diferentes nos dois lados, e a ferramenta feita
para responder "é o mesmo código?" responderia sempre "não". Um alarme que
sempre toca ninguém escuta.

⚠️ **Não é segredo, mas também não é o código.** Sai um hash curto e a
contagem de arquivos — nada que descreva o que está dentro.
"""

import hashlib
import os

from config import BASE_DIR

# 🔑 **Lista BRANCA, não lista negra — e isso não é preferência de estilo.**
# A primeira versão excluía o que eu sabia nomear (`__pycache__`, `.venv`,
# `arquivos`, `uploads`) e contou **136 arquivos aqui e 2.014 na produção**: o
# buildpack instala as dependências dentro da pasta da API, com um nome que eu
# não tinha previsto. O hash passou a incluir bibliotecas de terceiros — ou
# seja, a ferramenta feita para comparar O NOSSO código comparava outra coisa,
# e nunca ia bater com o cálculo local.
#
# A lista negra depende de eu adivinhar tudo o que pode aparecer; a branca só
# depende de eu saber o que é meu. Só a segunda é verdade estável.
#
# ⚠️ `arquivos` e `uploads` continuam fora de qualquer jeito: são dados de
# operação (o .eml, a logo) e mudam sozinhos com o uso — dentro do hash, a
# impressão mudaria sem ninguém ter publicado nada.
NOSSAS = ("db_scripts", "models", "routers", "services", "tests")


def _arquivos() -> list[str]:
    achados: list[str] = []
    # Os .py soltos na raiz da API (main, config, seguranca, database…).
    for n in sorted(os.listdir(BASE_DIR)):
        if n.endswith(".py") and os.path.isfile(os.path.join(BASE_DIR, n)):
            achados.append(os.path.join(BASE_DIR, n))
    for pasta in NOSSAS:
        for raiz, subpastas, nomes in os.walk(os.path.join(BASE_DIR, pasta)):
            subpastas[:] = sorted(p for p in subpastas if p != "__pycache__")
            for n in sorted(nomes):
                if n.endswith((".py", ".sql")):
                    achados.append(os.path.join(raiz, n))
    # Caminho relativo e com barra normal: o separador do Windows entraria no
    # hash e daria diferença onde não há.
    return sorted(achados, key=lambda c: os.path.relpath(c, BASE_DIR).replace("\\", "/"))


def calcular() -> dict:
    """Hash do código-fonte da API. Roda uma vez, no start."""
    h = hashlib.sha256()
    n = 0
    for caminho in _arquivos():
        rel = os.path.relpath(caminho, BASE_DIR).replace("\\", "/")
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except OSError:
            continue
        # O NOME entra junto: sem ele, renomear um arquivo sem mudar o conteúdo
        # não mudaria a impressão.
        h.update(rel.encode())
        h.update(dados.replace(b"\r\n", b"\n"))
        n += 1
    return {"impressao": h.hexdigest()[:12], "arquivos": n}


# Calculado no import: o código não muda enquanto o processo vive, e ler a
# árvore a cada chamada de /saude seria trabalho repetido à toa.
CODIGO = calcular()
