"""Recuperação de senha: o link que chega por e-mail e o que ele pode fazer.

As decisões que sustentam isto, e por quê:

* **O token vale uma vez e por pouco tempo.** Trinta minutos e um uso. E-mail
  fica aberto em aparelho compartilhado; link eterno é senha eterna.
* **O pedido nunca conta se o e-mail existe.** A tela responde a mesma frase
  para endereço cadastrado e para endereço inventado — senão a página vira um
  verificador de quem trabalha na casa.
* **Redefinir derruba todas as sessões.** É o caso em que alguém pede a
  recuperação *porque* desconfia que outra pessoa entrou. Trocar a senha e
  deixar a sessão do invasor viva não resolveria nada.
* **Um pedido novo mata os anteriores.** Quem clicou três vezes recebe três
  e-mails, e só o último funciona; o resto morre na hora.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from config import SENHA_PEDIDOS_HORA, SENHA_TOKEN_MINUTOS, WEB_URL
from seguranca import hash_senha
from html import escape

from services import email as correio
from services import marca


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- a mensagem


def _corpo(nome: str, link: str, minutos: int, casa: str) -> tuple[str, str]:
    primeiro = (nome or "").split(" ")[0] or "Olá"
    texto = (
        f"{primeiro}, alguém pediu para redefinir a senha do seu acesso ao sistema de {casa}.\n\n"
        f"Para escolher uma senha nova, abra este endereço:\n{link}\n\n"
        f"O link vale por {minutos} minutos e só pode ser usado uma vez.\n\n"
        "Se não foi você quem pediu, ignore esta mensagem: sua senha continua a "
        "mesma e ninguém entrou na sua conta.\n"
    )
    html = f"""<!doctype html>
<html lang="pt-BR"><body style="margin:0;background:#f3f5ef;padding:28px 16px;
  font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#14201a">
  <div style="max-width:520px;margin:0 auto;background:#fcfdfa;border:1px solid #d8ded0;
              border-radius:6px;padding:28px">
    <p style="margin:0 0 4px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;
              color:#5d6c61">{escape(casa)}</p>
    <h1 style="margin:0 0 16px;font-size:22px">Redefinir a senha</h1>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6">{primeiro}, alguém pediu para
      redefinir a senha do seu acesso.</p>
    <p style="margin:0 0 24px">
      <a href="{link}" style="display:inline-block;background:#2c6a4a;color:#fff;
         text-decoration:none;padding:11px 20px;border-radius:4px;font-weight:600;
         font-size:15px">Escolher uma senha nova</a>
    </p>
    <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#5d6c61">
      O link vale por {minutos} minutos e só pode ser usado uma vez. Se o botão não abrir,
      copie e cole este endereço no navegador:<br>
      <span style="word-break:break-all;font-size:13px">{link}</span></p>
    <p style="margin:0;font-size:14px;line-height:1.6;color:#5d6c61">
      Se não foi você quem pediu, ignore esta mensagem: sua senha continua a mesma e
      ninguém entrou na sua conta.</p>
  </div>
</body></html>"""
    return texto, html


# ---------------------------------------------------------------- o pedido


def criar_token(cur, id_usuario: int, ip: str | None = None, origem: str = "PUBLICA") -> str:
    """Gera o token, guarda só o hash e invalida os anteriores do usuário."""
    cur.execute(
        """UPDATE senha_tokens SET usado_em = now()
            WHERE id_usuario = %s AND usado_em IS NULL""",
        (id_usuario,),
    )
    token = secrets.token_urlsafe(32)
    cur.execute(
        """INSERT INTO senha_tokens (id_usuario, token_hash, expira_em, origem, ip)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_usuario, _hash(token),
         datetime.now(timezone.utc) + timedelta(minutes=SENHA_TOKEN_MINUTOS), origem, ip),
    )
    return token


def link_de(token: str) -> str:
    return f"{WEB_URL.rstrip('/')}/redefinir-senha?token={token}"


def preparar_link(cur, u: dict, ip: str | None = None, origem: str = "PUBLICA") -> dict:
    """Cria o token e monta a mensagem — SEM enviar. Devolve o link e o `_envio`.

    🔴 **O envio sai depois do `with get_cursor()`, com `despachar`** (11/11/2026).
    Antes a conversa com o SMTP acontecia dentro da transação (ver
    `email.preparar`), e uma falha do envio desfazia o TOKEN: o administrador
    ficava sem o link justamente quando não há SMTP que funcione, que é o caso
    para o qual o link na tela existe. Agora o token está gravado antes de
    qualquer tentativa de envio.

    Quem chama decide se o link pode aparecer para alguém: no pedido público,
    não; na tela do administrador, sim — é o que resolve o esquecimento da
    equipe enquanto não há SMTP.
    """
    token = criar_token(cur, u["id"], ip, origem)
    link = link_de(token)
    casa = marca.nome_da_casa(cur)
    texto, html = _corpo(u["nome"], link, SENHA_TOKEN_MINUTOS, casa)
    cfg, msg = correio.preparar(cur, u["email"], f"{casa} — redefinir sua senha", texto, html)
    return {"link": link, "email": u["email"], "modo": cfg["modo"], "_envio": (cfg, msg)}


def despachar(preparado: dict) -> dict:
    """Envia o que `preparar_link`/`pedir` montaram. Sem banco: chamar FORA da transação.

    Nunca levanta: a falha vira `modo = "falhou"` com o `motivo`, porque nos dois
    chamadores o token já está gravado e continua valendo.
    """
    r = dict(preparado)
    envio = r.pop("_envio", None)
    if not envio:
        return r
    try:
        r.update(correio.despachar(*envio))
    except correio.ErroEmail as e:
        r.update(modo="falhou", motivo=e.mensagem)
    return r


def pedir(cur, email: str, ip: str | None = None) -> dict:
    """Trata o pedido público. O retorno é para o log, **nunca** para a resposta.

    Note que todo caminho de saída é silencioso: usuário inexistente, inativo e
    excesso de pedidos saem igual para quem está do outro lado.
    """
    cur.execute(
        "SELECT id, nome, email, ativo FROM usuarios WHERE lower(email) = lower(%s)",
        (email.strip(),),
    )
    u = cur.fetchone()
    if not u:
        return {"enviado": False, "motivo": "e-mail não cadastrado"}
    if not u["ativo"]:
        return {"enviado": False, "motivo": "usuário inativo"}

    cur.execute(
        """SELECT count(*) AS n FROM senha_tokens
            WHERE id_usuario = %s AND criado_em > now() - interval '1 hour'""",
        (u["id"],),
    )
    if cur.fetchone()["n"] >= SENHA_PEDIDOS_HORA:
        # Não é erro para quem pediu: é o freio contra usar a tela para encher a
        # caixa de entrada de alguém.
        return {"enviado": False, "motivo": "limite de pedidos por hora"}

    r = preparar_link(cur, dict(u), ip)
    # O link some aqui: o retorno de `pedir` vai para a auditoria, e link em
    # log é link vazado. ⚠️ O `_envio` fica: quem chama despacha DEPOIS de fechar
    # a transação (`despachar`), e tira o `_envio` antes de auditar.
    r.pop("link", None)
    return {"enviado": True, "id_usuario": u["id"], **r}


# ---------------------------------------------------------------- o uso


def usuario_do_token(cur, token: str) -> dict:
    """Valida o token e devolve de quem ele é. Levanta 400 com o motivo."""
    cur.execute(
        """SELECT t.id, t.usado_em, t.expira_em, u.id AS id_usuario, u.nome, u.email, u.ativo
             FROM senha_tokens t JOIN usuarios u ON u.id = t.id_usuario
            WHERE t.token_hash = %s""",
        (_hash(token or ""),),
    )
    t = cur.fetchone()
    # Link inválido e link já usado dizem a mesma coisa a quem chegou pelo
    # endereço: o que interessa é "peça outro".
    if not t or t["usado_em"]:
        raise HTTPException(
            status_code=400,
            detail="Este link não vale mais. Peça a recuperação de novo.",
        )
    if t["expira_em"] <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail=f"O link venceu (ele vale {SENHA_TOKEN_MINUTOS} minutos). Peça outro.",
        )
    if not t["ativo"]:
        raise HTTPException(status_code=403, detail="Usuário inativo")
    return dict(t)


def redefinir(cur, token: str, senha: str) -> dict:
    """Troca a senha, queima o token e derruba todas as sessões do usuário."""
    t = usuario_do_token(cur, token)
    cur.execute(
        """UPDATE usuarios
              SET senha_hash = %s, trocar_senha = false, tentativas_login = 0,
                  bloqueado_ate = NULL
            WHERE id = %s""",
        (hash_senha(senha), t["id_usuario"]),
    )
    cur.execute("UPDATE senha_tokens SET usado_em = now() WHERE id = %s", (t["id"],))
    cur.execute(
        """UPDATE sessoes SET revogada_em = now()
            WHERE id_usuario = %s AND revogada_em IS NULL""",
        (t["id_usuario"],),
    )
    return {"id_usuario": t["id_usuario"], "nome": t["nome"], "email": t["email"]}
