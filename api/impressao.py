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

# ⚠️ O que NÃO entra na conta: `__pycache__` é gerado e difere por versão de
# Python; `arquivos` e `uploads` são dados de operação (o .eml, a logo) e mudam
# sozinhos com o uso — dentro do hash, a impressão mudaria sem ninguém ter
# publicado nada.
IGNORAR = {"__pycache__", "arquivos", "uploads", ".venv", "venv", ".git"}


def _arquivos() -> list[str]:
    achados: list[str] = []
    for raiz, pastas, nomes in os.walk(BASE_DIR):
        pastas[:] = sorted(p for p in pastas if p not in IGNORAR)
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
