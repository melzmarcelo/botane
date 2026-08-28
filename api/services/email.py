"""Envio de e-mail — e o modo simulado que faz o sistema funcionar sem SMTP.

A recuperação de senha não pode depender de o cliente ter contratado um
servidor de e-mail. Enquanto não houver, o sistema **grava a mensagem em
arquivo** (`api/arquivos/emails/*.eml`, que qualquer cliente de e-mail abre) e
segue em frente. Configurar o SMTP na tela de Integrações liga o envio real
sem mudar mais nada.

A configuração mora em `integracoes` (serviço `SMTP`): o que não é segredo vai
em `config` (servidor, porta, remetente), e a senha vai cifrada em
`credenciais`, do mesmo jeito que a chave do Omie — e, como ela, **nunca volta
pela API**.
"""

import os
import re
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from config import BASE_DIR
from services import segredos

SERVICO = "SMTP"
PASTA = os.path.join(BASE_DIR, "arquivos", "emails")

# ⚠️ **O orçamento é do envio INTEIRO, não de cada passo.** O `timeout=` do
# smtplib vale para CADA operação de socket, e são quatro em sequência:
# conectar, STARTTLS, autenticar e enviar. Com 20 s em cada, o pior caso era
# 80 s — e o roteamento do App Platform desiste em ~60, devolvendo **504 com
# uma página HTML**. Ou seja: o erro que a pessoa via não era o do SMTP, era o
# do gateway, e não dizia nada sobre a causa.
#
# 20 s no total é folgado para distinguir "servidor respondeu e recusou" de
# "os pacotes estão sendo descartados", que é a pergunta que este botão existe
# para responder. E sobra muito para o gateway responder antes de desistir.
ORCAMENTO_ENVIO = 20


def _resta(ate: float) -> float:
    """Quanto do orçamento sobrou. Nunca zero: 0 em socket é NÃO BLOQUEANTE.

    ⚠️ `settimeout(0)` põe o socket em modo não bloqueante e faz a operação
    falhar na hora com um erro que não parece tempo esgotado. O piso de 1 s
    garante que o último passo ainda tenha chance de dizer o que houve.
    """
    return max(1.0, ate - time.monotonic())


class ErroEmail(Exception):
    def __init__(self, mensagem: str):
        self.mensagem = mensagem
        super().__init__(mensagem)


def configuracao(cur) -> dict:
    """Lê a configuração de SMTP. Devolve sempre um dicionário utilizável."""
    cur.execute(
        """SELECT config, credenciais, ativa, modo FROM integracoes
            WHERE servico = %s AND id_unidade IS NULL""",
        (SERVICO,),
    )
    linha = cur.fetchone()
    if not linha:
        return {"modo": "simulado", "ativa": False}
    cfg = dict(linha["config"] or {})
    cfg["ativa"] = linha["ativa"]
    # Sem servidor não há como enviar, por mais que alguém marque "real".
    cfg["modo"] = linha["modo"] if (linha["modo"] == "real" and cfg.get("servidor")) else "simulado"
    cfg["senha"] = segredos.decifrar(linha["credenciais"]).get("senha")
    return cfg


def _remetente(cfg: dict) -> str:
    email = cfg.get("remetente_email") or cfg.get("usuario") or "botane@localhost"
    return formataddr((cfg.get("remetente_nome") or "Botané Deli e Café", email))


def _montar(cfg: dict, para: str, assunto: str, texto: str, html: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = _remetente(cfg)
    msg["To"] = para
    msg["Date"] = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    msg["Message-ID"] = make_msgid(domain="botane.local")
    # Sempre as duas versões: o texto puro é o que sobra em cliente antigo, em
    # leitor de tela e no filtro de spam que desconfia de e-mail só com HTML.
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _gravar(msg: EmailMessage, para: str) -> str:
    os.makedirs(PASTA, exist_ok=True)
    seguro = re.sub(r"[^a-z0-9._-]", "_", para.lower())
    nome = f"{datetime.now():%Y%m%d-%H%M%S}-{seguro}.eml"
    caminho = os.path.join(PASTA, nome)
    with open(caminho, "wb") as f:
        f.write(bytes(msg))
    return caminho


def enviar(cur, para: str, assunto: str, texto: str, html: str | None = None) -> dict:
    """Envia (ou grava, no modo simulado). Devolve o que aconteceu.

    O retorno **nunca** vai para uma resposta pública: o caminho do arquivo
    diria a quem pediu que aquele e-mail existe no sistema.
    """
    cfg = configuracao(cur)
    msg = _montar(cfg, para, assunto, texto, html)

    if cfg["modo"] != "real":
        return {"modo": "simulado", "arquivo": _gravar(msg, para)}

    entregar(cfg, msg)
    return {"modo": "real", "servidor": cfg["servidor"]}


def entregar(cfg: dict, msg: EmailMessage) -> None:
    """A conversa com o servidor SMTP, e só ela.

    Separada de `enviar` por dois motivos, e o segundo é o que importa:

    * **não toca no banco** — dá para exercitar o prazo contra um endereço que
      não responde sem pôr a configuração da casa em modo real, que é o rastro
      perigoso (o projeto já perdeu uma credencial assim);
    * é aqui que vive o ORÇAMENTO, num lugar só.
    """
    porta = int(cfg.get("porta") or 587)
    seguranca = (cfg.get("seguranca") or "starttls").lower()
    contexto = ssl.create_default_context()
    ate = time.monotonic() + ORCAMENTO_ENVIO
    try:
        if seguranca == "ssl":
            with smtplib.SMTP_SSL(cfg["servidor"], porta, context=contexto,
                                  timeout=_resta(ate)) as s:
                if cfg.get("usuario"):
                    s.sock.settimeout(_resta(ate))
                    s.login(cfg["usuario"], cfg.get("senha") or "")
                s.sock.settimeout(_resta(ate))
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["servidor"], porta, timeout=_resta(ate)) as s:
                if seguranca == "starttls":
                    s.sock.settimeout(_resta(ate))
                    s.starttls(context=contexto)
                    # ⚠️ O STARTTLS TROCA o socket por um embrulhado em TLS —
                    # o timeout do anterior não acompanha, e sem repor aqui os
                    # passos seguintes voltariam a ficar sem prazo nenhum.
                if cfg.get("usuario"):
                    s.sock.settimeout(_resta(ate))
                    s.login(cfg["usuario"], cfg.get("senha") or "")
                s.sock.settimeout(_resta(ate))
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        # ⚠️ **O log precisa dizer o motivo, não só o status.** Quem opera abre
        # o log da nuvem e via `POST /email/testar 502` e mais nada — o porquê
        # ia só para a tela de quem clicou, que quase nunca é a mesma pessoa.
        # Aqui, e não no router, porque são três chamadores (o botão de teste,
        # a criação de usuário e a recuperação de senha) e a recuperação é
        # rota PÚBLICA: é justamente a que ninguém está olhando quando falha.
        #
        # ⚠️ Servidor e porta entram na linha; usuário e senha **nunca** — log
        # é lido por mais gente do que a tela, e vaza para onde ninguém previu.
        print(f"[botane] e-mail NAO enviado por {cfg.get('servidor')}:{porta} "
              f"({seguranca}): {type(e).__name__}: {e}")
        # A frase leva o erro do socket porque é ELE que separa as causas:
        # "timed out" é pacote descartado (porta bloqueada na saída, o caso
        # comum em nuvem); "Connection refused" é servidor errado ou porta
        # fechada; "Name or service not known" é o endereço. Sem isso, os três
        # viram "não foi possível enviar" e mandam procurar no lugar errado.
        raise ErroEmail(f"Não foi possível enviar o e-mail: {e}") from e


def testar(cur, para: str) -> dict:
    """Manda um e-mail de teste — o botão da tela de Integrações."""
    r = enviar(
        cur,
        para,
        "Botané — teste de envio",
        "Se você está lendo isto, o envio de e-mail do Botané está funcionando.\n",
        "<p>Se você está lendo isto, o envio de e-mail do Botané está funcionando.</p>",
    )
    if r["modo"] == "simulado":
        return {"ok": True, "modo": "simulado",
                "detalhe": f"Sem SMTP configurado: a mensagem foi gravada em {r['arquivo']}"}
    return {"ok": True, "modo": "real", "detalhe": f"Enviado por {r['servidor']} para {para}"}
