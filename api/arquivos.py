"""Guarda de arquivos enviados pela tela (hoje: a logo da empresa).

🔑 **Mora no BANCO, e não em disco — porque o disco do App Platform é
EFÊMERO.** `api/uploads/` some a cada deploy: a casa pôs a logo, publicou uma
versão e a logo sumiu, sem nada explicando. O risco estava previsto no preparo
da subida, com o Spaces como saída; para UMA imagem de até 2 MB o banco é a
resposta mais honesta — ele já sobrevive ao deploy, já entra no backup do
roteiro, e não pede bucket, chave nem segredo. Este projeto já perdeu duas
credenciais guardadas; a melhor credencial é a que não existe.

⚠️ **Quem chama continua recebendo uma URL, e não sabe de onde ela vem.** Foi
para isso que este módulo existe desde o começo. No dia em que houver foto de
produto ou anexo de nota — arquivo grande, muitos, servidos direto —, o Spaces
volta a ser a resposta, e é só este arquivo que muda.
"""

import secrets

from fastapi import HTTPException, UploadFile

from database import get_cursor

PREFIXO_URL = "/arquivos"

# SVG fica de fora de propósito: SVG é executável (pode carregar script) e a
# logo é exibida em página autenticada.
TIPOS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
LIMITE_BYTES = 2 * 1024 * 1024


def _nome_da_url(url: str | None) -> str | None:
    """O nome do arquivo dentro da URL, recusando qualquer outra coisa.

    ⚠️ A URL vem do banco, mas nada impede alguém de chamar a rota com um
    caminho inventado. Só passa o que tem exatamente uma barra depois do
    prefixo — sem `..`, sem subpasta, sem nome vazio.
    """
    if not url or not url.startswith(PREFIXO_URL + "/"):
        return None
    nome = url[len(PREFIXO_URL) + 1:]
    if not nome or "/" in nome or "\\" in nome or ".." in nome:
        return None
    return nome


async def ler_enviada(arquivo: UploadFile) -> tuple[bytes, str, str]:
    """Confere o que chegou e devolve `(conteúdo, tipo, extensão)`. Não toca no banco.

    🔑 **Separado da gravação de propósito.** Ler o corpo da requisição pode
    demorar (são até 2 MB vindos pela rede), e fazer isso com uma transação
    aberta prende uma conexão do pool durante todo o envio. Assim a conexão só
    é pedida quando já se tem os bytes na mão.
    """
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
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(conteudo)) as img:
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="O arquivo não é uma imagem válida.")

    return conteudo, arquivo.content_type or "image/png", extensao


def gravar(cur, conteudo: bytes, tipo: str, extensao: str, nome_base: str) -> str:
    """Insere a imagem NO CURSOR DE QUEM CHAMA e devolve a URL relativa.

    🔑 **Recebe o cursor, e essa é a correção que importa.** A versão anterior
    abria transação própria, inseria a nova imagem e **apagava a anterior** ali
    mesmo — e só depois, numa TERCEIRA transação, o chamador gravava a URL nova
    no registro. Entre uma e outra havia uma janela: falhando a última (a API
    reiniciada, a requisição abortada, um erro no meio), a imagem antiga já
    tinha sido apagada e o registro continuava apontando para ela. A logo e a
    foto da ficha **sumiam sem volta**, com o link quebrado e nada explicando.
    Agora inserir a nova, apontar para ela e apagar a velha são uma coisa só:
    ou as três acontecem, ou nenhuma.

    ⚠️ **E este não apaga nada** — quem apaga é `remover`, chamado pelo dono do
    registro DEPOIS de a nova URL estar gravada, no mesmo cursor.
    """
    # Sufixo aleatório troca o nome a cada envio: sem isso o navegador continua
    # mostrando a logo antiga do cache.
    nome = f"{nome_base}-{secrets.token_hex(4)}{extensao}"
    cur.execute(
        """INSERT INTO arquivos (nome, dono, tipo, conteudo, bytes)
           VALUES (%s, %s, %s, %s, %s)""",
        (nome, nome_base, tipo, conteudo, len(conteudo)),
    )
    return f"{PREFIXO_URL}/{nome}"


def ler(url: str | None) -> tuple[bytes, str] | None:
    """O CONTEÚDO do arquivo e o tipo dele, ou `None` quando não está lá.

    Serve a rota que entrega a imagem ao navegador e o PDF, que a **desenha** —
    pedir a si mesmo por rede para carimbar um cabeçalho seria uma requisição a
    mais por relatório, e falharia justamente onde o PDF é gerado sem navegador
    nenhum.

    ⚠️ **Devolve `None` em vez de levantar.** Logo ausente é estado normal — a
    casa pode nunca ter enviado uma —, e o cabeçalho tem de sair sem ela em vez
    de derrubar o relatório.
    """
    nome = _nome_da_url(url)
    if not nome:
        return None
    with get_cursor() as cur:
        cur.execute("SELECT conteudo, tipo FROM arquivos WHERE nome = %s", (nome,))
        linha = cur.fetchone()
    if not linha:
        return None
    return bytes(linha["conteudo"]), linha["tipo"]


def copiar(url: str | None, novo_dono: str, cur=None) -> str | None:
    """Duplica o arquivo sob outro dono e devolve a URL nova.

    🔑 **Existe por causa da nova versão da ficha.** Copiar só a URL deixaria
    duas fichas apontando para o MESMO arquivo, cujo dono continua sendo a
    versão velha — e `salvar_imagem` apaga as versões anteriores do mesmo dono.
    Trocar a foto da versão 1 apagaria a foto da versão 2, que ninguém tocou, e
    a imagem sumiria da tela sem nada explicando.

    ⚠️ Devolve `None` quando não há o que copiar: ficha sem foto é o caso comum,
    e a versão nova nasce sem uma em vez de falhar.
    """
    achado = ler(url)
    if not achado:
        return None
    conteudo, tipo = achado
    extensao = TIPOS.get(tipo or "", ".jpg")
    # ⚠️ No cursor de quem chama quando ele existe: a cópia e a ficha nova
    # nascem juntas ou não nascem — senão um rollback lá fora deixaria o
    # arquivo órfão no banco.
    if cur is not None:
        return gravar(cur, conteudo, tipo, extensao, novo_dono)
    with get_cursor() as proprio:
        return gravar(proprio, conteudo, tipo, extensao, novo_dono)


def remover(url: str | None, cur=None) -> None:
    """Apaga o arquivo. **Chamar só depois de o registro já apontar para outro.**

    ⚠️ Aceita o cursor de quem chama, e é assim que deve ser usado na TROCA de
    imagem: apontar para a nova e apagar a velha na mesma transação. Fora dela,
    um erro entre as duas deixaria o registro órfão de imagem.
    """
    nome = _nome_da_url(url)
    if not nome:
        return
    if cur is not None:
        cur.execute("DELETE FROM arquivos WHERE nome = %s", (nome,))
        return
    with get_cursor() as proprio:
        proprio.execute("DELETE FROM arquivos WHERE nome = %s", (nome,))
