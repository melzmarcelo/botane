"""Guarda de arquivos enviados pela tela (hoje: a logo da empresa).

Local por enquanto — `api/uploads/`, servido em `/arquivos`. Quando houver
nuvem, só este módulo muda: quem chama recebe uma URL e não sabe de onde veio.
"""

import os
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PASTA = BASE_DIR / "uploads"
PREFIXO_URL = "/arquivos"

# SVG fica de fora de propósito: SVG é executável (pode carregar script) e a
# logo é exibida em página autenticada.
TIPOS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
LIMITE_BYTES = 2 * 1024 * 1024


def garantir_pasta() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)


async def salvar_imagem(arquivo: UploadFile, nome_base: str) -> str:
    """Grava a imagem e devolve a URL relativa. Recusa o que não é imagem."""
    extensao = TIPOS.get(arquivo.content_type or "")
    if not extensao:
        raise HTTPException(
            status_code=400,
            detail="Formato não aceito. Envie PNG, JPG ou WEBP.",
        )

    conteudo = await arquivo.read()
    if len(conteudo) > LIMITE_BYTES:
        raise HTTPException(status_code=413, detail="Imagem maior que 2 MB.")
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    # Confere que o conteúdo é mesmo uma imagem — content-type é só o que o
    # navegador diz, não o que o arquivo é.
    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(conteudo)) as img:
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="O arquivo não é uma imagem válida.")

    garantir_pasta()
    # Sufixo aleatório troca o nome a cada envio: sem isso o navegador continua
    # mostrando a logo antiga do cache.
    nome = f"{nome_base}-{secrets.token_hex(4)}{extensao}"
    (PASTA / nome).write_bytes(conteudo)

    # Limpa versões anteriores do mesmo dono.
    for antigo in PASTA.glob(f"{nome_base}-*"):
        if antigo.name != nome:
            antigo.unlink(missing_ok=True)

    return f"{PREFIXO_URL}/{nome}"


def caminho_local(url: str | None) -> Path | None:
    """A URL de volta ao arquivo em disco, para quem precisa do CONTEÚDO.

    O PDF **desenha** a logo, não a busca por HTTP — pedir a si mesmo por rede
    para carimbar um cabeçalho seria uma requisição a mais por relatório, e
    falharia justamente onde o PDF é gerado sem navegador nenhum.

    ⚠️ Mora aqui, e não em quem monta o PDF, pela mesma razão que `remover`:
    este é o único módulo que sabe onde os arquivos ficam. No dia do Spaces é
    só ele que muda — quem chama continua recebendo bytes.
    ⚠️ Devolve `None` quando o arquivo não está lá. No App Platform a pasta é
    EFÊMERA e some a cada deploy: o cabeçalho tem de sair sem a logo em vez de
    derrubar o relatório.
    """
    if not url or not url.startswith(PREFIXO_URL + "/"):
        return None
    alvo = PASTA / Path(url).name
    return alvo if alvo.parent == PASTA and alvo.exists() else None


def remover(url: str | None) -> None:
    if not url or not url.startswith(PREFIXO_URL + "/"):
        return
    alvo = PASTA / Path(url).name
    if alvo.parent == PASTA:
        alvo.unlink(missing_ok=True)
