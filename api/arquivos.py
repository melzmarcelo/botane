"""Guarda de arquivos enviados pela tela (a logo da empresa e o PDF do catálogo).

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

# 🔑 **O PDF do catálogo tem porta própria** (21/09/2026), e não entra em
# `TIPOS`: aquela lista é de IMAGEM, usada pela logo e pela foto da ficha, e um
# PDF caindo ali viraria `<img src>` quebrada na próxima tela que reaproveitasse
# a função.
PDF_TIPO = "application/pdf"
# ⚠️ **10 MB, não 2.** O cardápio é ilustrado: as fotos dos pratos fazem um PDF
# passar dos 2 MB da logo com folga, e recusar o arquivo da casa por um limite
# pensado para um logotipo seria recusar o caso de uso inteiro.
PDF_LIMITE_BYTES = 10 * 1024 * 1024


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


# O que o Pillow diz que a imagem É → o tipo que se grava. Pelo CONTEÚDO, não pelo
# que quem mandou declarou.
_FORMATOS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def ler_base64(texto: str) -> tuple[bytes, str, str]:
    """A imagem que chega em BASE64 — a porta do conector do Claude, que só fala JSON.

    🔑 **Pedido do dono (26/09/2026):** *"ao importar um PDF no Claude de uma ficha
    técnica que tem foto, permitir gravar esta imagem na ficha."* O upload da tela é
    multipart; o MCP não tem como mandar arquivo, só texto. Mesmas regras de
    `ler_enviada`: PNG, JPG ou WEBP, até 2 MB, conferida pelo conteúdo.
    ⚠️ Aceita o prefixo `data:image/...;base64,`, que é como o modelo costuma escrever.
    """
    import base64
    import binascii
    from io import BytesIO

    from PIL import Image

    bruto = (texto or "").strip()
    if bruto.startswith("data:") and "," in bruto:
        bruto = bruto.split(",", 1)[1]
    bruto = "".join(bruto.split())  # quebras de linha no meio do base64
    try:
        conteudo = base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="A imagem não é um base64 válido.")
    if not conteudo:
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    if len(conteudo) > LIMITE_BYTES:
        raise HTTPException(status_code=413, detail="Imagem maior que 2 MB.")
    try:
        with Image.open(BytesIO(conteudo)) as img:
            formato = img.format
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="O conteúdo não é uma imagem válida.")
    tipo = _FORMATOS.get(formato or "")
    if not tipo:
        raise HTTPException(status_code=400, detail="Formato não aceito. Envie PNG, JPG ou WEBP.")
    return conteudo, tipo, TIPOS[tipo]


async def ler_pdf(arquivo: UploadFile) -> tuple[bytes, str, str]:
    """Confere o PDF que chegou e devolve `(conteúdo, tipo, extensão)`.

    🔑 **Pedido do dono (21/09/2026):** *"tenho que poder carregar o PDF, neste
    caso para ele ser exibido"*. É a mesma forma de `ler_enviada`, pelo mesmo
    motivo: ler o corpo pode demorar, e fazer isso com transação aberta prende
    uma conexão do pool durante todo o envio.

    ⚠️ **O `content-type` é só o que o NAVEGADOR diz, não o que o arquivo é.**
    Por isso a conferência dos primeiros bytes: todo PDF começa com `%PDF-`, e
    quem renomeia um `.exe` para `.pdf` para de passar aqui. É a mesma
    desconfiança que `ler_enviada` tem com a imagem.
    """
    if (arquivo.content_type or "") != PDF_TIPO:
        raise HTTPException(
            status_code=400,
            detail="Formato não aceito. Envie um arquivo PDF.",
        )

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(conteudo) > PDF_LIMITE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"PDF maior que {PDF_LIMITE_BYTES // (1024 * 1024)} MB. "
                    f"Um cardápio costuma caber bem abaixo disso — se o seu passa, "
                    f"provavelmente dá para reduzir as imagens dentro dele."),
        )
    # ⚠️ `%PDF-` pode vir depois de alguns bytes de lixo em arquivos gerados por
    # ferramentas antigas; os leitores toleram isso no começo do arquivo. Mil
    # bytes é folga suficiente sem abrir a porta para um arquivo que só TEM a
    # assinatura perdida no meio.
    if b"%PDF-" not in conteudo[:1024]:
        raise HTTPException(
            status_code=400,
            detail="O arquivo não é um PDF válido — ele não começa como um PDF.",
        )

    return conteudo, PDF_TIPO, ".pdf"


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


# ---------------------------------------------------------------------------
# Cardápio Vivo (113): o vídeo do prato e a imagem no tamanho da tela
# ---------------------------------------------------------------------------

# 🔑 **O que chega pode ser o vídeo cru do celular**; o que se GUARDA é o convertido.
# 40 MB cobre um minuto de 1080p de telefone — e só os primeiros 15 s ficam.
VIDEO_TIPOS = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v", "video/3gpp"}
VIDEO_LIMITE_ENVIO = 40 * 1024 * 1024
VIDEO_SEGUNDOS = 15
VIDEO_TIPO = "video/mp4"


async def ler_video(arquivo: UploadFile) -> bytes:
    """Confere o vídeo enviado e devolve os bytes crus. Não toca no banco.

    ⚠️ O `content-type` é só o que o navegador diz: quem confere o conteúdo é o
    ffmpeg, na conversão — um arquivo que não é vídeo para ali com a frase certa.
    """
    if (arquivo.content_type or "") not in VIDEO_TIPOS:
        raise HTTPException(status_code=400,
                            detail="Formato não aceito. Envie um vídeo MP4, MOV ou WEBM.")
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(conteudo) > VIDEO_LIMITE_ENVIO:
        raise HTTPException(
            status_code=413,
            detail=f"Vídeo maior que {VIDEO_LIMITE_ENVIO // (1024 * 1024)} MB. "
                   f"Só os primeiros {VIDEO_SEGUNDOS} segundos são usados — corte antes de enviar.")
    return conteudo


def converter_video(conteudo: bytes) -> tuple[bytes, bytes, float]:
    """O vídeo como o cardápio serve: `(mp4, capa_webp, segundos)`.

    🔑 **MP4 H.264, 720p no lado MENOR, mudo, até 15 s, ~2 MB** — o que qualquer
    celular toca sem plugin e o 4G fraco aguenta. `+faststart` põe o índice no
    começo: sem ele o navegador baixa o arquivo inteiro antes do primeiro quadro.
    ⚠️ **O lado menor, não a altura**: o vídeo de celular é em pé (1080×1920), e
    "altura 720" o deixaria com 405 de largura.
    ⚠️ Passou de 3 MB (cena com muito movimento), refaz com taxa menor em vez de
    recusar — quem filmou o prato não tem como "comprimir melhor".
    """
    import os
    import re
    import subprocess
    import tempfile
    from io import BytesIO

    import imageio_ffmpeg
    from PIL import Image

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    escala = ("scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'")
    with tempfile.TemporaryDirectory() as pasta:
        entrada = os.path.join(pasta, "entrada")
        saida = os.path.join(pasta, "saida.mp4")
        capa = os.path.join(pasta, "capa.png")
        with open(entrada, "wb") as f:
            f.write(conteudo)

        def rodar(taxa: int) -> subprocess.CompletedProcess:
            return subprocess.run(
                [exe, "-y", "-hide_banner", "-i", entrada, "-t", str(VIDEO_SEGUNDOS), "-an",
                 "-vf", f"{escala},fps=30", "-c:v", "libx264", "-profile:v", "main",
                 "-pix_fmt", "yuv420p", "-preset", "veryfast",
                 "-b:v", f"{taxa}k", "-maxrate", f"{taxa}k", "-bufsize", f"{taxa * 2}k",
                 "-movflags", "+faststart", saida],
                capture_output=True, timeout=180)

        try:
            r = rodar(950)
            if r.returncode == 0 and os.path.getsize(saida) > 3 * 1024 * 1024:
                r = rodar(600)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=422, detail="A conversão do vídeo demorou demais.")
        if r.returncode != 0 or not os.path.exists(saida):
            raise HTTPException(status_code=400,
                                detail="Não foi possível ler este arquivo como vídeo.")

        # A duração sai do que o ffmpeg contou ao ler a ENTRADA, limitada aos 15 s.
        texto = r.stderr.decode("utf-8", "ignore")
        achado = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", texto)
        segundos = float(VIDEO_SEGUNDOS)
        if achado:
            h, m, s = achado.groups()
            segundos = min(float(VIDEO_SEGUNDOS), int(h) * 3600 + int(m) * 60 + float(s))

        # 🔑 A CAPA (poster) é o primeiro quadro firme, em WebP: é o que aparece antes do
        # vídeo carregar e o que fica no lugar dele com economia de dados.
        subprocess.run([exe, "-y", "-hide_banner", "-ss", "0.3", "-i", saida,
                        "-frames:v", "1", capa], capture_output=True, timeout=60)
        if not os.path.exists(capa):
            subprocess.run([exe, "-y", "-hide_banner", "-i", saida, "-frames:v", "1", capa],
                           capture_output=True, timeout=60)
        if not os.path.exists(capa):
            raise HTTPException(status_code=400, detail="O vídeo não tem um quadro legível.")
        with open(saida, "rb") as f:
            mp4 = f.read()
        with Image.open(capa) as img:
            buf = BytesIO()
            img.convert("RGB").save(buf, "WEBP", quality=80, method=4)
    return mp4, buf.getvalue(), round(segundos, 2)


# 🔑 **As larguras que a tela pede**, fechadas: aceitar qualquer número faria cada
# `?w=` diferente gerar e guardar uma imagem nova — uma porta para encher a memória.
LARGURAS = (320, 480, 720, 960, 1280)


def _largura_permitida(largura: int) -> int:
    return next((l for l in LARGURAS if l >= largura), LARGURAS[-1])


from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=256)
def _redimensionada(nome: str, largura: int) -> bytes | None:
    """A imagem em WebP com no máximo `largura` px. Guardada em memória.

    ⚠️ **O nome nunca muda de conteúdo** (sufixo aleatório a cada envio), então o
    cache não envelhece: a foto nova tem outro nome.
    """
    from io import BytesIO

    from PIL import Image, ImageOps

    achado = ler(f"{PREFIXO_URL}/{nome}")
    if not achado or achado[1] not in TIPOS:
        return None
    with Image.open(BytesIO(achado[0])) as img:
        img = ImageOps.exif_transpose(img)
        if img.width > largura:
            img = img.resize((largura, round(img.height * largura / img.width)),
                             Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(
            buf, "WEBP", quality=78, method=4)
        return buf.getvalue()


def redimensionada(url: str | None, largura: int) -> bytes | None:
    """A imagem no tamanho da tela, em WebP — ou `None` se não é imagem nossa."""
    nome = _nome_da_url(url)
    if not nome:
        return None
    return _redimensionada(nome, _largura_permitida(largura))
