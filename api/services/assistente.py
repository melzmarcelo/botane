"""O assistente pelo WhatsApp — etapa 1: o número do assistente e o vínculo telefone ↔ usuário.

🔑 **Pedido do dono (06/11/2026):** o funcionário vincula o próprio telefone no usuário e
conversa com o sistema pelo WhatsApp (pendências, receita, lançar produção). Estudo em
`docs/assistente-whatsapp-estudo.md`. Esta etapa só reconhece quem escreve e responde um
"olá" — as consultas e gravações vêm nas próximas.

🔑 **UM número, da casa toda** (*"poderia ser compartilhado entre lojas … quando pergunto o que
tenho de pendência, poderia encontrar coisas de duas lojas"*). A conexão mora em `integracoes`
(serviço `WHATSAPP_ASSISTENTE`, `id_unidade` nulo) e se configura em Integrações ▸ Assistente.
Quem decide o que a pessoa vê é o usuário dela, não o número.

Como o vínculo nasce:
1. Em Perfil, a pessoa pede um código (`gerar_codigo`). Vale 15 minutos e fica só o hash.
2. Ela manda o código do PRÓPRIO WhatsApp para o número do assistente (o link da tela já leva
   o texto pronto).
3. O webhook (o mesmo das lojas, `whatsapp.receber`, que desvia o que é do assistente) entrega a
   mensagem a `receber`: o código casa, e o `from` da Meta vira o `wa_id` do usuário. ⚠️ **É o
   `from`, nunca o que a pessoa digitou** — prova a posse e evita o nono dígito, que a Meta às
   vezes tira do celular brasileiro.

⚠️ **As respostas são texto livre**: quem escreveu primeiro foi o funcionário, e isso abre a
janela de 24 h da Meta. Vão para a fila PRÓPRIA (`assistente_mensagens`), fora do histórico das
lojas — a conversa é do funcionário, não de uma loja.
⚠️ **Modo simulado** (padrão): a resposta fica na fila como SIMULADA e não sai — o mesmo
desenho do WhatsApp das lojas e do Omie.
"""

import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import quote

import httpx
from fastapi import HTTPException

import auditoria
from database import get_cursor
from relogio import agora_da_casa
from services import segredos

PERMISSAO = "integracao.whatsapp_assistente"
SERVICO = "WHATSAPP_ASSISTENTE"
API_VERSAO_PADRAO = "v21.0"
TENTATIVAS_MAXIMAS = 3
VALIDADE = timedelta(minutes=15)
# Sem 0/O, 1/I/L: o código é lido na tela e, no pior caso, digitado à mão.
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO = 8
PREFIXO = "BOTANE"
_CODIGO = re.compile(r"\b[A-Z0-9]{%d}\b" % TAMANHO)


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.upper().encode()).hexdigest()


def _digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _wa_me(numero: str | None) -> str | None:
    d = _digitos(numero)
    if len(d) in (10, 11):
        return "55" + d
    return d if len(d) >= 12 else None


def formatar(wa_id: str | None) -> str | None:
    """"5547999105033" → "+55 (47) 99910-5033" (o que der para formatar; senão, os dígitos)."""
    d = _digitos(wa_id)
    if not d:
        return None
    if d.startswith("55") and len(d) in (12, 13):
        ddd, num = d[2:4], d[4:]
        return f"+55 ({ddd}) {num[:-4]}-{num[-4:]}"
    return "+" + d


# ---------------------------------------------------------------- a conexão (Integrações)
def conexao(cur) -> dict:
    """A conexão do número do assistente, com as credenciais decifradas. Sem linha: desligada."""
    cur.execute("""SELECT ativa, modo, credenciais, config, ultimo_status, ultima_mensagem
                     FROM integracoes WHERE servico = %s AND id_unidade IS NULL""", (SERVICO,))
    l = cur.fetchone()
    cfg = dict((l or {}).get("config") or {})
    return {
        "ativa": bool(l and l["ativa"]), "modo": (l or {}).get("modo") or "simulado",
        "numero": cfg.get("numero") or "", "phone_number_id": cfg.get("phone_number_id") or "",
        "waba_id": cfg.get("waba_id") or "", "api_versao": cfg.get("api_versao") or API_VERSAO_PADRAO,
        "verify_token": cfg.get("verify_token") or "",
        # 152: a conversa — o modelo do Claude e quantas perguntas por pessoa por dia.
        "modelo": (cfg.get("modelo") or "").strip(),
        "limite_diario": int(cfg.get("limite_diario") or 0),
        # ⚠️ Só para os testes (uma Anthropic falsa); ignorado fora de DEBUG.
        "url_api": cfg.get("url_api") or "",
        "cred": segredos.decifrar(l["credenciais"]) if l and l["credenciais"] else {},
        "ultimo_status": (l or {}).get("ultimo_status"),
        "ultima_mensagem": (l or {}).get("ultima_mensagem"),
        "existe": bool(l),
    }


def _gravar_linha(cur, ativa: bool, modo: str, config: dict, cred: dict) -> None:
    cur.execute(
        # ⚠️ O índice parcial da 012 (serviço da casa toda, id_unidade nulo) — o mesmo do SMTP.
        """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais, config)
           VALUES (NULL, %s, %s, %s, %s, %s)
           ON CONFLICT (servico) WHERE id_unidade IS NULL DO UPDATE
               SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                   credenciais = EXCLUDED.credenciais, config = EXCLUDED.config,
                   atualizado_em = now()""",
        (SERVICO, ativa, modo, segredos.cifrar(cred) if cred else None, json.dumps(config)))


_CHAVES_CONFIG = ("numero", "phone_number_id", "waba_id", "api_versao", "verify_token", "modelo",
                  "limite_diario", "url_api")


def _config_de(c: dict) -> dict:
    return {k: c[k] for k in _CHAVES_CONFIG}


def configuracao(cur, url_publica: str) -> dict:
    """A aba da tela. ⚠️ O token e o segredo NUNCA voltam — só "configurado"."""
    c = conexao(cur)
    if not c["verify_token"]:
        # O token de verificação do webhook nasce na primeira visita: a casa o cola na Meta.
        c["verify_token"] = secrets.token_urlsafe(18)
        _gravar_linha(cur, c["ativa"], c["modo"], _config_de(c), c["cred"])
    return {
        "ativa": c["ativa"], "modo": c["modo"], "numero": c["numero"],
        "phone_number_id": c["phone_number_id"], "waba_id": c["waba_id"],
        "api_versao": c["api_versao"], "verify_token": c["verify_token"],
        "webhook_url": f"{url_publica}/publico/whatsapp/webhook",
        "token_configurado": bool(c["cred"].get("token")),
        "segredo_configurado": bool(c["cred"].get("app_secret")),
        "ultimo_status": c["ultimo_status"], "ultima_mensagem": c["ultima_mensagem"],
        # 152: a conversa. A chave da Anthropic é a da Tradução — aqui só se diz se existe.
        "modelo": c["modelo"], "modelo_padrao": _conversa().MODELO_PADRAO,
        "limite_diario": c["limite_diario"] or _conversa().LIMITE_DIARIO_PADRAO,
        "chave_anthropic": bool(_traducao_chave(cur)),
    }


def _conversa():
    from services import assistente_conversa
    return assistente_conversa


def _traducao_chave(cur) -> str:
    from services import traducao
    return traducao._config(cur).get("chave") or ""


def salvar(cur, body) -> None:
    """Grava a conexão. ⚠️ Token/segredo em branco = mantém o que já está."""
    c = conexao(cur)
    numero = (body.numero or "").strip()
    if numero and not _wa_me(numero):
        raise HTTPException(status_code=422, detail=f"O número “{numero}” está incompleto: use DDD e número.")
    pnid = (body.phone_number_id or "").strip()
    if pnid:
        cur.execute("SELECT 1 FROM unidade_whatsapps WHERE phone_number_id = %s", (pnid,))
        if cur.fetchone():
            raise HTTPException(status_code=422, detail=(
                f"O identificador {pnid} da Meta já é de um número de loja: o assistente precisa "
                "de um número só dele."))
    cred = dict(c["cred"])
    if (body.token or "").strip():
        cred["token"] = body.token.strip()
    if (body.app_secret or "").strip():
        cred["app_secret"] = body.app_secret.strip()
    if body.ativa and not numero:
        raise HTTPException(status_code=400, detail="Informe o número do assistente antes de ligar.")
    if body.ativa and body.modo == "real" and not (pnid and cred.get("token")):
        raise HTTPException(status_code=400, detail=(
            "Para enviar de verdade, informe o identificador do número e o token da Meta."))
    _gravar_linha(cur, body.ativa, body.modo, {
        "numero": numero, "phone_number_id": pnid, "waba_id": (body.waba_id or "").strip(),
        "api_versao": (body.api_versao or "").strip() or API_VERSAO_PADRAO,
        "verify_token": c["verify_token"] or secrets.token_urlsafe(18),
        "modelo": (body.modelo or "").strip(),
        "limite_diario": body.limite_diario,
        # ⚠️ Mandado em branco, mantém (a tela não tem o campo: é dos testes).
        "url_api": c["url_api"] if body.url_api is None else body.url_api.strip()}, cred)


def do_assistente(cur, phone_number_id: str | None) -> dict | None:
    """A conexão, se o webhook veio para o número do assistente. Usado por `whatsapp.receber`."""
    if not phone_number_id:
        return None
    c = conexao(cur)
    return c if c["existe"] and c["phone_number_id"] == str(phone_number_id) else None


def token_de_verificacao(cur, token: str | None) -> bool:
    c = conexao(cur)
    return bool(token) and bool(c["verify_token"]) and hmac.compare_digest(c["verify_token"], token)


# ---------------------------------------------------------------- a tela (Perfil)
def _numero_para_chamar(cur) -> dict | None:
    c = conexao(cur)
    digitos = _wa_me(c["numero"])
    if not (c["ativa"] and digitos):
        return None
    return {"numero": c["numero"], "digitos": digitos}


def estado(cur, ctx) -> dict:
    """O que a tela mostra: vinculado a qual número, se há código pendente (sem o código) e para
    qual número mandar."""
    cur.execute("SELECT * FROM usuario_whatsapp WHERE id_usuario = %s", (ctx.id_usuario,))
    v = cur.fetchone() or {}
    pendente = bool(v.get("codigo_hash") and v.get("codigo_expira_em")
                    and v["codigo_expira_em"] > agora_da_casa())
    return {
        "vinculado": bool(v.get("wa_id")),
        "telefone": formatar(v.get("wa_id")),
        "verificado_em": v["verificado_em"].isoformat() if v.get("verificado_em") else None,
        "codigo_pendente": pendente,
        "codigo_expira_em": v["codigo_expira_em"].isoformat() if pendente else None,
        "assistente": _numero_para_chamar(cur),
    }


def gerar_codigo(cur, ctx) -> dict:
    """Um código novo (o anterior deixa de valer). ⚠️ O código em claro só volta AQUI, uma vez.

    O vínculo que já existe continua valendo até o código ser usado: trocar de aparelho não
    deixa a pessoa sem assistente no meio do caminho.
    """
    if not _numero_para_chamar(cur):
        raise HTTPException(status_code=409, detail=(
            "O número do assistente ainda não está ligado. Quem administra o sistema o configura "
            "em Integrações ▸ Assistente."))
    while True:
        codigo = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
        cur.execute("SELECT 1 FROM usuario_whatsapp WHERE codigo_hash = %s", (_hash(codigo),))
        if not cur.fetchone():
            break
    cur.execute(
        """INSERT INTO usuario_whatsapp (id_usuario, codigo_hash, codigo_expira_em)
           VALUES (%s, %s, %s)
           ON CONFLICT (id_usuario) DO UPDATE
               SET codigo_hash = EXCLUDED.codigo_hash,
                   codigo_expira_em = EXCLUDED.codigo_expira_em, atualizado_em = now()""",
        (ctx.id_usuario, _hash(codigo), agora_da_casa() + VALIDADE))
    texto = f"{PREFIXO} {codigo}"
    saida = estado(cur, ctx)
    saida["codigo"] = codigo
    saida["mensagem"] = texto
    saida["assistente"]["link"] = f"https://wa.me/{saida['assistente']['digitos']}?text={quote(texto)}"
    return saida


def desvincular(cur, ctx) -> bool:
    cur.execute("SELECT wa_id FROM usuario_whatsapp WHERE id_usuario = %s", (ctx.id_usuario,))
    v = cur.fetchone()
    if not v:
        return False
    cur.execute("DELETE FROM usuario_whatsapp WHERE id_usuario = %s", (ctx.id_usuario,))
    if v["wa_id"]:
        auditoria.registrar(cur, ctx.id_usuario, "assistente_whatsapp", ctx.id_usuario,
                            "desvincular", antes={"telefone": formatar(v["wa_id"])})
    return True


# ---------------------------------------------------------------- a fila e o envio
def responder(cur, chave: str, fone: str, texto: str, id_usuario: int | None = None) -> bool:
    cur.execute(
        """INSERT INTO assistente_mensagens (chave, id_usuario, telefone, texto)
           VALUES (%s, %s, %s, %s) ON CONFLICT (chave) DO NOTHING RETURNING id""",
        (chave[:120], id_usuario, fone, texto))
    return cur.fetchone() is not None


def _enviar_um(cur, msg: dict, c: dict) -> None:
    if not c["ativa"]:
        cur.execute("""UPDATE assistente_mensagens SET status = 'CANCELADA', atualizada_em = now(),
                              erro = 'O número do assistente foi desligado.' WHERE id = %s""",
                    (msg["id"],))
        return
    if c["modo"] != "real":
        cur.execute("""UPDATE assistente_mensagens SET status = 'SIMULADA', enviada_em = now(),
                              atualizada_em = now() WHERE id = %s""", (msg["id"],))
        return
    url = f"https://graph.facebook.com/{c['api_versao']}/{c['phone_number_id']}/messages"
    try:
        r = httpx.post(url, timeout=15, headers={"Authorization": f"Bearer {c['cred'].get('token')}"},
                       json={"messaging_product": "whatsapp", "to": msg["telefone"], "type": "text",
                             "text": {"body": msg["texto"]}})
        dados = r.json() if r.content else {}
        if r.status_code >= 400:
            raise RuntimeError((dados.get("error") or {}).get("message") or f"HTTP {r.status_code}")
        wamid = ((dados.get("messages") or [{}])[0]).get("id")
        cur.execute("""UPDATE assistente_mensagens SET status = 'ENVIADA', enviada_em = now(),
                              id_meta = %s, erro = NULL, atualizada_em = now() WHERE id = %s""",
                    (wamid, msg["id"]))
        cur.execute("""UPDATE integracoes SET ultimo_status = 'ok', ultima_mensagem = NULL
                        WHERE servico = %s AND id_unidade IS NULL""", (SERVICO,))
    except Exception as e:  # noqa: BLE001
        tentativas = int(msg["tentativas"]) + 1
        cur.execute(
            """UPDATE assistente_mensagens
                  SET tentativas = %s, erro = %s, atualizada_em = now(),
                      status = CASE WHEN %s THEN 'FALHOU' ELSE 'FILA' END,
                      agendada_para = now() + interval '1 minute'
                WHERE id = %s""",
            (tentativas, str(e)[:500], tentativas >= TENTATIVAS_MAXIMAS, msg["id"]))
        cur.execute("""UPDATE integracoes SET ultimo_status = 'erro', ultima_mensagem = %s
                        WHERE servico = %s AND id_unidade IS NULL""", (str(e)[:500], SERVICO))


def processar_fila(limite: int = 20) -> int:
    """Envia o que venceu. Chamado logo depois do webhook (a resposta não espera o laço) e, de
    reserva, pelo laço do WhatsApp a cada 30 s. ⚠️ `SKIP LOCKED`: nunca a mesma duas vezes."""
    with get_cursor() as cur:
        cur.execute("""SELECT id, telefone, texto, tentativas FROM assistente_mensagens
                        WHERE status = 'FILA' AND agendada_para <= now()
                        ORDER BY agendada_para, id LIMIT %s FOR UPDATE SKIP LOCKED""", (limite,))
        msgs = [dict(r) for r in cur.fetchall()]
        if msgs:
            c = conexao(cur)
            for m in msgs:
                _enviar_um(cur, m, c)
    return len(msgs)


# ---------------------------------------------------------------- o webhook
_ORDEM = {"FILA": 0, "SIMULADA": 1, "ENVIADA": 1, "ENTREGUE": 2, "LIDA": 3, "FALHOU": 1,
          "CANCELADA": 0}
_DA_META = {"sent": "ENVIADA", "delivered": "ENTREGUE", "read": "LIDA", "failed": "FALHOU"}


def estado_da_meta(cur, st: dict) -> int:
    """Entregue / lida / falhou de uma resposta do assistente. Só avança."""
    novo = _DA_META.get(st.get("status"))
    if not novo:
        return 0
    cur.execute("SELECT id, status FROM assistente_mensagens WHERE id_meta = %s", (st.get("id"),))
    m = cur.fetchone()
    if not m or not (_ORDEM.get(novo, 0) > _ORDEM.get(m["status"], 0) or novo == "FALHOU"):
        return 0
    erro = ((st.get("errors") or [{}])[0]).get("title") if novo == "FALHOU" else None
    cur.execute("""UPDATE assistente_mensagens SET status = %s, erro = coalesce(%s, erro),
                          atualizada_em = now() WHERE id = %s""", (novo, erro, m["id"]))
    return 1


def _tem_permissao(cur, id_usuario: int) -> bool:
    cur.execute("""SELECT 1 FROM usuario_papeis up
                     JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
                    WHERE up.id_usuario = %s AND pp.chave = %s LIMIT 1""",
                (id_usuario, PERMISSAO))
    return cur.fetchone() is not None


def _primeiro(nome: str | None) -> str:
    return (nome or "").split(" ")[0] or "tudo bem"


def _verificar_codigo(cur, texto: str, fone: str) -> dict | None:
    """O código da mensagem casa com um pendente e válido? Então liga o `from` ao usuário."""
    for candidato in _CODIGO.findall(texto.upper()):
        cur.execute(
            """SELECT v.id_usuario, v.wa_id, u.nome FROM usuario_whatsapp v
                 JOIN usuarios u ON u.id = v.id_usuario AND u.ativo
                WHERE v.codigo_hash = %s AND v.codigo_expira_em > now() FOR UPDATE OF v""",
            (_hash(candidato),))
        v = cur.fetchone()
        if not v:
            continue
        # 🔑 Quem provou a posse fica com o número: se ele estava ligado a outro usuário (o
        # aparelho mudou de mãos), sai de lá — e a auditoria conta.
        cur.execute("""SELECT id_usuario FROM usuario_whatsapp
                        WHERE wa_id = %s AND id_usuario <> %s""", (fone, v["id_usuario"]))
        anterior = cur.fetchone()
        if anterior:
            cur.execute("""UPDATE usuario_whatsapp SET wa_id = NULL, verificado_em = NULL,
                                  atualizado_em = now() WHERE id_usuario = %s""",
                        (anterior["id_usuario"],))
        cur.execute(
            """UPDATE usuario_whatsapp
                  SET wa_id = %s, verificado_em = now(), codigo_hash = NULL,
                      codigo_expira_em = NULL, atualizado_em = now()
                WHERE id_usuario = %s""",
            (fone, v["id_usuario"]))
        auditoria.registrar(
            cur, v["id_usuario"], "assistente_whatsapp", v["id_usuario"], "vincular",
            antes={"telefone": formatar(v["wa_id"])} if v["wa_id"] else None,
            depois={"telefone": formatar(fone),
                    "tirado_do_usuario": anterior["id_usuario"] if anterior else None})
        return dict(v)
    return None


def receber(cur, msg: dict) -> int:
    """Uma mensagem que chegou no número do assistente. Devolve 1 se tratou, 0 se ignorou.

    ⚠️ **A chave da resposta é o id da mensagem da Meta**: a Meta reenvia o webhook quando
    não recebe 200 a tempo, e o índice único da fila impede responder duas vezes.
    """
    fone = _digitos(msg.get("from"))
    if not fone:
        return 0
    chave = str(msg.get("id") or hashlib.sha256(
        json.dumps(msg, sort_keys=True).encode()).hexdigest()[:40])
    tipo = msg.get("type")
    texto = ((msg.get("text") or {}).get("body") or "").strip() if tipo == "text" else ""

    # ⚠️ **Reenvio da Meta: a mensagem já tratada não volta a ser tratada, por caminho nenhum.**
    # O código de vínculo reenviado chegava depois de a pessoa já estar vinculada e virava uma
    # pergunta ao Claude ("Olá! botane K7XM…").
    cur.execute("""SELECT 1 FROM assistente_mensagens WHERE chave = %s
                   UNION ALL SELECT 1 FROM assistente_conversa WHERE id_meta = %s LIMIT 1""",
                (chave, chave))
    if cur.fetchone():
        return 0

    if texto:
        novo = _verificar_codigo(cur, texto, fone)
        if novo:
            responder(cur, chave, fone,
                      f"Pronto, {_primeiro(novo['nome'])}! Este WhatsApp agora está ligado ao seu "
                      "usuário no Botané. Em breve vou responder suas pendências, receitas e "
                      "lançar produção por aqui.", novo["id_usuario"])
            return 1

    cur.execute("""SELECT v.id_usuario, u.nome FROM usuario_whatsapp v
                     JOIN usuarios u ON u.id = v.id_usuario AND u.ativo
                    WHERE v.wa_id = %s""", (fone,))
    quem = cur.fetchone()
    if not quem:
        # ⚠️ Número desconhecido recebe UMA resposta por dia, e nada sobre o sistema: o webhook
        # não pode virar um jeito de descobrir quem é funcionário.
        responder(cur, f"desconhecido:{fone}:{agora_da_casa().date()}", fone,
                  "Este número não está ligado a nenhum usuário. Para ligar, entre no sistema e "
                  "abra Perfil ▸ Assistente no WhatsApp.")
        return 1
    nome, id_u = _primeiro(quem["nome"]), quem["id_usuario"]
    if not _tem_permissao(cur, id_u):
        responder(cur, chave, fone, f"Olá, {nome}. Seu usuário não tem o assistente liberado — "
                                    "fale com o administrador.", id_u)
    elif tipo != "text" or not texto:
        responder(cur, chave, fone, f"Olá, {nome}! Por enquanto só entendo mensagens de texto.", id_u)
    else:
        # 152: a pergunta fica guardada e o Claude responde logo depois do 200 do webhook.
        conversa = _conversa()
        limite = conversa.configuracao(cur)["limite_diario"]
        if conversa.perguntas_hoje(cur, id_u) >= limite:
            responder(cur, f"limite:{fone}:{agora_da_casa().date()}", fone,
                      f"{nome}, você chegou ao limite de {limite} perguntas por hoje. Amanhã eu volto "
                      "a responder — ou peça a quem administra o sistema para aumentar o limite.", id_u)
        else:
            conversa.guardar_pergunta(cur, id_u, texto, chave)
    return 1
