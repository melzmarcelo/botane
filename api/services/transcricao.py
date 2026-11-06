"""O assistente pelo WhatsApp, etapa 3 — o áudio vira texto (migração 153).

🔑 **Pedido do dono (06/11/2026):** *"pela manhã mando um áudio ou um texto…"*. Estudo em
`docs/assistente-whatsapp-estudo.md`.

Dois passos:
1. **Baixar da Meta** (`baixar_da_meta`): o webhook traz só o id da mídia; a Graph API devolve
   uma URL temporária, que se baixa com o mesmo token do número do assistente.
2. **Transcrever** (`transcrever`): OpenAI e Groq falam o MESMO formato
   (`POST {base}/audio/transcriptions`, multipart com `file` e `model`), então um cliente só
   serve aos dois — a casa escolhe o provedor e cadastra a chave em Integrações ▸ Assistente.

⚠️ **O áudio não é guardado**: os bytes ficam só na memória deste processo. Vai, sim, para o
provedor escolhido — é o que a tela diz ao lado da chave.
⚠️ A API do Claude não recebe áudio (conferido na referência em 06/11/2026); se um dia receber,
o passo 2 pode sumir.
"""

import httpx

from config import DEBUG

PROVEDORES = {
    "openai": {"nome": "OpenAI", "url": "https://api.openai.com/v1",
               "modelo": "gpt-4o-mini-transcribe"},
    "groq": {"nome": "Groq", "url": "https://api.groq.com/openai/v1",
             "modelo": "whisper-large-v3-turbo"},
}
GRAPH = "https://graph.facebook.com"
# Os dois provedores aceitam até 25 MB; nota de voz de 10 minutos tem ~1 MB. O teto é contra
# arquivo que não é nota de voz (um áudio encaminhado de uma hora).
LIMITE_BYTES = 8 * 1024 * 1024


class Temporario(Exception):
    """Vale tentar de novo (429, 5xx, rede)."""


class Definitivo(Exception):
    """Não adianta repetir — e a frase vai para quem mandou o áudio."""


def configuracao(c: dict) -> dict:
    """O provedor, o modelo, a chave e os endereços, a partir da conexão do assistente.

    ⚠️ `url_meta` e `url_transcricao` (os serviços falsos dos testes) só valem com DEBUG.
    """
    prov = PROVEDORES.get(c.get("transcricao_provedor") or "")
    if not prov:
        return {"ligada": False}
    chave = (c.get("cred") or {}).get("transcricao_chave") or ""
    url_falsa = (c.get("url_transcricao") or "").strip() if DEBUG else ""
    return {
        "ligada": bool(chave or url_falsa),
        "provedor": c["transcricao_provedor"],
        "modelo": (c.get("transcricao_modelo") or "").strip() or prov["modelo"],
        "chave": chave or "teste",
        "url": (url_falsa or prov["url"]).rstrip("/"),
    }


def _graph(c: dict) -> str:
    falsa = (c.get("url_meta") or "").strip() if DEBUG else ""
    return (falsa or GRAPH).rstrip("/")


def baixar_da_meta(c: dict, midia_id: str) -> tuple[bytes, str]:
    """Os bytes do áudio e o tipo dele. Precisa do token do número do assistente."""
    token = (c.get("cred") or {}).get("token")
    if not token and not (DEBUG and c.get("url_meta")):
        raise Definitivo("Para ouvir áudio, o número do assistente precisa do token da Meta "
                         "(Integrações ▸ Assistente).")
    cab = {"Authorization": f"Bearer {token or 'teste'}"}
    try:
        r = httpx.get(f"{_graph(c)}/{c.get('api_versao') or 'v21.0'}/{midia_id}", headers=cab,
                      timeout=20)
        if r.status_code == 429 or r.status_code >= 500:
            raise Temporario(f"Meta {r.status_code}")
        if r.status_code >= 400:
            raise Definitivo("Não consegui baixar o áudio da Meta — ele pode ter expirado. "
                             "Mande de novo?")
        info = r.json()
        if int(info.get("file_size") or 0) > LIMITE_BYTES:
            raise Definitivo("Esse áudio é longo demais para mim. Mande um mais curto, por favor.")
        a = httpx.get(info["url"], headers=cab, timeout=60, follow_redirects=True)
        if a.status_code >= 500:
            raise Temporario(f"Meta (mídia) {a.status_code}")
        if a.status_code >= 400:
            raise Definitivo("Não consegui baixar o áudio da Meta. Mande de novo?")
    except httpx.HTTPError as e:
        raise Temporario(f"rede (Meta): {e}") from e
    if len(a.content) > LIMITE_BYTES:
        raise Definitivo("Esse áudio é longo demais para mim. Mande um mais curto, por favor.")
    return a.content, (info.get("mime_type") or "audio/ogg").split(";")[0]


def transcrever(cfg: dict, dados: bytes, mime: str) -> str:
    """O texto do áudio, em português. Vazio = não deu para entender nada."""
    extensao = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "m4a",
                "audio/amr": "amr", "audio/wav": "wav"}.get(mime, "ogg")
    try:
        r = httpx.post(f"{cfg['url']}/audio/transcriptions", timeout=90,
                       headers={"Authorization": f"Bearer {cfg['chave']}"},
                       files={"file": (f"audio.{extensao}", dados, mime)},
                       data={"model": cfg["modelo"], "language": "pt", "response_format": "json"})
    except httpx.HTTPError as e:
        raise Temporario(f"rede (transcrição): {e}") from e
    if r.status_code == 429 or r.status_code >= 500:
        raise Temporario(f"transcrição {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        # Chave errada, modelo que não existe, formato recusado: é configuração.
        raise Definitivo("Não consegui transcrever o áudio: a configuração da transcrição tem um "
                         "problema. Avise quem administra o sistema — e, por enquanto, escreva.")
    return ((r.json() or {}).get("text") or "").strip()
