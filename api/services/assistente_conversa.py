"""O assistente pelo WhatsApp, etapa 2 — a conversa: o Claude responde consultas com as
ferramentas de LEITURA do conector, como o próprio usuário (migração 152).

🔑 **Pedido do dono (06/11/2026):** *"mando um texto pedindo quais as minhas pendências para
hoje. Aí ele retorna: para hoje precisa produzir 10 pães. Aí posso solicitar a receita…"*. E o
número é da casa: *"quando pergunto o que tenho de pendência, poderia encontrar coisas de duas
lojas"* — o Claude consulta cada loja que o usuário vê.

Como funciona:
1. O webhook guarda a pergunta (`guardar_pergunta`, status PENDENTE) e devolve 200.
2. Logo depois (tarefa do webhook) e, de reserva, no laço do WhatsApp, `processar_pendentes`
   pega as perguntas de UM usuário de cada vez, monta o histórico curto e chama o Claude.
3. O Claude pede ferramentas; cada uma é uma rota que JÁ EXISTE, chamada por dentro com uma
   credencial do usuário (`mcp_ferramentas.chamar`) — permissão, loja e setor são os da tela.
4. A resposta vai para a fila do assistente (`assistente.responder`) e sai pelo WhatsApp.

🔑 **Só leitura nesta etapa**: o Claude só RECEBE ferramentas de GET (`_FERRAMENTAS`), e uma
ferramenta de gravação pedida mesmo assim volta como erro, sem chamar nada. Lançar produção é a
etapa 4, com confirmação por botão.
⚠️ **A chave da Anthropic é a da casa**, a mesma da Tradução (Integrações ▸ Tradução).
⚠️ **HTTP direto, sem o SDK `anthropic`** — como `services/traducao.py`: o `requirements.txt`
é preso no que passou na bateria, e o SDK puxaria versões novas de `httpx`/`pydantic`.
"""

import asyncio
import json
import logging
from datetime import timedelta

import httpx

from config import DEBUG
from database import get_cursor
from relogio import agora_da_casa
from services import assistente, mcp_ferramentas, transcricao, traducao

log = logging.getLogger("botane.assistente")

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
MODELO_PADRAO = "claude-opus-5-5"
LIMITE_DIARIO_PADRAO = 40
MAX_VOLTAS = 10                 # pedidos de ferramenta numa mesma pergunta
HISTORICO = 12                  # falas anteriores que vão junto
JANELA_HISTORICO = timedelta(hours=3)
LIMITE_RESULTADO = 20_000       # caracteres de cada resultado de ferramenta
LIMITE_WHATSAPP = 3900          # o WhatsApp corta em 4096
TENTATIVAS = 3
GUARDAR_DIAS = 30

# 🔑 Só as de LEITURA, em ordem estável: a lista vai no começo de cada pedido e é cacheada —
# mudar a ordem a cada chamada invalidaria o cache.
_FERRAMENTAS = sorted((f for f in mcp_ferramentas.FERRAMENTAS if not f.grava), key=lambda f: f.nome)
_PERMITIDAS = {f.nome for f in _FERRAMENTAS}

# Modelos que aceitam o `fallbacks: "default"` (refaz em outro modelo quando a segurança recusa).
_COM_FALLBACK = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")
# Modelos antigos que não aceitam `output_config.effort`.
_SEM_EFFORT = ("claude-haiku-4", "claude-sonnet-4-5", "claude-3")

_APP = None


def registrar_app(app) -> None:
    """O app FastAPI, para as ferramentas serem chamadas por dentro (sem rede). Feito no main."""
    global _APP
    _APP = app


SISTEMA = """Você é o assistente do sistema de gestão de {casa}, uma casa de alimentação. \
Você conversa pelo WhatsApp com um funcionário já identificado.

Como responder:
- Português do Brasil, curto e direto, em texto de WhatsApp: *negrito* com um asterisco, \
listas com "•", sem tabelas, sem títulos com #. Quantidades sempre com a unidade.
- Use as ferramentas para buscar os dados de verdade. Nunca invente número, nome ou receita.
- As ferramentas enxergam só o que esse funcionário pode ver, nas lojas dele. Quando a pergunta \
vale para a casa (pendências, estoque, agenda), consulte CADA loja dele (parâmetro id_loja) e \
separe a resposta por loja; se ele só tem uma, não fale em loja.
- "Pendências de hoje": a agenda de produção do dia (agenda_producao), os alertas, os lotes \
vencendo, as etiquetas que vencem e os pedidos do cardápio em aberto. Diga o que for de hoje; \
o resto, só se for urgente.
- Receita = ficha técnica (fichas_tecnicas para achar, ficha_tecnica para ler). Para produzir \
uma quantidade, use necessario_para_produzir: ele já calcula os ingredientes e diz o que falta.
- Datas no formato AAAA-MM-DD nas ferramentas; para a pessoa, DD/MM.
- Erro 403 quer dizer que o funcionário não tem permissão para aquilo — diga isso, sem rodeio.
- Nesta versão você SÓ CONSULTA. Não lança produção, não mexe em estoque nem grava nada. Se \
pedirem, diga que lançar pelo WhatsApp chega em breve e mostre o que seria lançado.
- Se a pergunta não tiver a ver com a casa, responda em uma frase e volte ao trabalho."""


# ---------------------------------------------------------------- a configuração
def configuracao(cur) -> dict:
    """Modelo, limite e chave. ⚠️ `url_api` (a Anthropic falsa dos testes) só vale com DEBUG."""
    c = assistente.conexao(cur)
    chave = traducao._config(cur).get("chave") or ""
    url = (c["url_api"] or "").strip() if DEBUG else ""
    return {
        "modelo": c["modelo"] or MODELO_PADRAO,
        "limite_diario": c["limite_diario"] or LIMITE_DIARIO_PADRAO,
        "chave": chave or ("teste" if url else ""),
        "url": url or URL_API,
    }


# ---------------------------------------------------------------- o webhook
def guardar_pergunta(cur, id_usuario: int, texto: str, id_meta: str,
                     midia_id: str | None = None) -> bool:
    """A pergunta entra como PENDENTE. Devolve False se a Meta já tinha mandado essa mesma.

    153: com `midia_id` é um ÁUDIO — nasce com o texto "[áudio]", trocado pela transcrição.
    """
    cur.execute(
        """INSERT INTO assistente_conversa (id_usuario, papel, texto, id_meta, status, midia_id,
                                            de_audio)
           VALUES (%s, 'usuario', %s, %s, 'PENDENTE', %s, %s)
           ON CONFLICT (id_meta) DO NOTHING RETURNING id""",
        (id_usuario, texto[:4000], id_meta[:120], midia_id, bool(midia_id)))
    return cur.fetchone() is not None


def perguntas_hoje(cur, id_usuario: int) -> int:
    cur.execute("""SELECT count(*) AS n FROM assistente_conversa
                    WHERE id_usuario = %s AND papel = 'usuario'
                      AND criada_em >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo')
                                        AT TIME ZONE 'America/Sao_Paulo'""", (id_usuario,))
    return cur.fetchone()["n"]


# ---------------------------------------------------------------- o processamento
def processar_pendentes(limite_usuarios: int = 5) -> int:
    """Responde as perguntas pendentes, um usuário de cada vez. Nunca levanta.

    ⚠️ **Todas as pendentes de um usuário viram UMA pergunta**: quem manda "bom dia" e
    "minhas pendências" em sequência recebe uma resposta, não duas cruzadas.
    🔑 `FOR UPDATE SKIP LOCKED` + PROCESSANDO: dois processos (o webhook e o laço) nunca pegam a
    mesma; o que ficou PROCESSANDO por queda do contêiner volta a PENDENTE em 5 minutos.
    """
    feitos = 0
    try:
        with get_cursor() as cur:
            cur.execute("""UPDATE assistente_conversa SET status = 'PENDENTE', atualizada_em = now()
                            WHERE status = 'PROCESSANDO'
                              AND atualizada_em < now() - interval '5 minutes'""")
        for _ in range(limite_usuarios):
            lote = _pegar_lote()
            if not lote:
                break
            _responder_lote(lote)
            feitos += 1
    except Exception:  # noqa: BLE001 — agendador que morre some sem avisar
        log.exception("assistente: falha ao processar pendentes")
    return feitos


def _pegar_lote() -> list[dict] | None:
    with get_cursor() as cur:
        cur.execute("""SELECT id_usuario FROM assistente_conversa
                        WHERE status = 'PENDENTE' AND (tentar_apos IS NULL OR tentar_apos <= now())
                        ORDER BY criada_em LIMIT 1 FOR UPDATE SKIP LOCKED""")
        r = cur.fetchone()
        if not r:
            return None
        cur.execute("""SELECT id, id_usuario, texto, tentativas, de_audio, midia_id, transcrito_em
                         FROM assistente_conversa
                        WHERE id_usuario = %s AND status = 'PENDENTE'
                        ORDER BY criada_em, id FOR UPDATE SKIP LOCKED""", (r["id_usuario"],))
        lote = [dict(x) for x in cur.fetchall()]
        cur.execute("""UPDATE assistente_conversa SET status = 'PROCESSANDO', atualizada_em = now()
                        WHERE id = ANY(%s)""", ([x["id"] for x in lote],))
    return lote


def _responder_lote(lote: list[dict]) -> None:
    ids = [x["id"] for x in lote]
    id_usuario = lote[0]["id_usuario"]
    with get_cursor() as cur:
        cur.execute("""SELECT u.id, u.nome, u.email, u.ativo, v.wa_id FROM usuarios u
                         LEFT JOIN usuario_whatsapp v ON v.id_usuario = u.id
                        WHERE u.id = %s""", (id_usuario,))
        quem = cur.fetchone()
        cfg = configuracao(cur)
        historico = _historico(cur, id_usuario, ids)
        contexto = _contexto(cur, id_usuario, quem)
    if not quem or not quem["ativo"] or not quem["wa_id"]:
        _fechar(ids, "ERRO", erro="Usuário inativo ou sem WhatsApp vinculado.")
        return
    if not cfg["chave"]:
        _fechar(ids, "ERRO", erro="Sem chave da Anthropic.", resposta=(
            "O assistente ainda não tem a chave da Anthropic. Quem administra o sistema a "
            "cadastra em Integrações ▸ Tradução."), id_usuario=id_usuario, fone=quem["wa_id"])
        return

    try:
        ouvido = _transcrever_audios(lote)
    except transcricao.Definitivo as e:
        _adiar_ou_desistir(lote, ids, quem, e, definitivo=True, resposta=str(e))
        return
    except transcricao.Temporario as e:
        _adiar_ou_desistir(lote, ids, quem, e, definitivo=False, resposta=(
            "Não consegui ouvir o áudio agora — o serviço está ocupado. Tente de novo em alguns "
            "minutos, ou escreva."))
        return
    if not any(x["texto"].strip() for x in lote):
        _fechar(ids, "RESPONDIDA", resposta="Não consegui entender o áudio. Pode repetir ou "
                                            "escrever?", id_usuario=id_usuario, fone=quem["wa_id"])
        return
    if ouvido:
        contexto += " [Parte da pergunta veio de ÁUDIO transcrito: pode ter erro de transcrição.]"
    pergunta = "\n".join(x["texto"] for x in lote if x["texto"].strip())
    try:
        texto, uso = asyncio.run(_conversar(cfg, quem, historico, contexto, pergunta))
    except _Temporario as e:
        _adiar_ou_desistir(lote, ids, quem, e, definitivo=False, resposta=(
            "Não consegui responder agora — o serviço está ocupado. Tente de novo em alguns "
            "minutos."))
        return
    except _Definitivo as e:
        _fechar(ids, "ERRO", erro=str(e), id_usuario=id_usuario, fone=quem["wa_id"],
                resposta="Não consegui responder: a configuração do assistente tem um problema. "
                         "Avise quem administra o sistema.")
        return
    if ouvido:
        # 🔑 Mostra o que ouviu: a pessoa confere se foi entendida — e, quando vier a gravação
        # pelo WhatsApp, é o que impede lançar "10 pães" que eram "12".
        texto = _caber(f"🎤 _Ouvi: “{' / '.join(ouvido)}”_\n\n{texto}")
    _fechar(ids, "RESPONDIDA", resposta=texto, uso=uso, id_usuario=id_usuario, fone=quem["wa_id"])


def _transcrever_audios(lote: list[dict]) -> list[str]:
    """Troca o "[áudio]" de cada áudio do lote pelo texto dele. Devolve o que foi ouvido.

    ⚠️ Gravado na hora, áudio por áudio: se o segundo falhar e o lote voltar para nova tentativa,
    o primeiro não é baixado nem cobrado de novo (`transcrito_em`).
    """
    audios = [x for x in lote if x["de_audio"]]
    if not audios:
        return []
    with get_cursor() as cur:
        c = assistente.conexao(cur)
    cfg = transcricao.configuracao(c)
    ouvido = []
    for x in audios:
        if x["transcrito_em"] is None:
            if not cfg["ligada"]:
                raise transcricao.Definitivo("A transcrição de áudio foi desligada. Escreva, por favor.")
            dados, mime = transcricao.baixar_da_meta(c, x["midia_id"])
            x["texto"] = transcricao.transcrever(cfg, dados, mime)
            with get_cursor() as cur:
                cur.execute("""UPDATE assistente_conversa SET texto = %s, transcrito_em = now(),
                                      atualizada_em = now() WHERE id = %s""",
                            (x["texto"], x["id"]))
        if x["texto"].strip():
            ouvido.append(x["texto"].strip())
    return ouvido


def _adiar_ou_desistir(lote: list[dict], ids: list[int], quem: dict, erro: Exception, *,
                       definitivo: bool, resposta: str) -> None:
    """Falha temporária volta a PENDENTE (até TENTATIVAS); a definitiva — ou a temporária que
    esgotou as tentativas — responde a frase e encerra."""
    tentativas = max(x["tentativas"] for x in lote) + 1
    if not definitivo and tentativas < TENTATIVAS:
        with get_cursor() as cur:
            cur.execute("""UPDATE assistente_conversa
                              SET status = 'PENDENTE', tentativas = %s, erro = %s,
                                  tentar_apos = now() + %s * interval '20 seconds',
                                  atualizada_em = now()
                            WHERE id = ANY(%s)""", (tentativas, str(erro)[:500], tentativas, ids))
        return
    _fechar(ids, "ERRO", erro=str(erro), id_usuario=lote[0]["id_usuario"], fone=quem["wa_id"],
            resposta=resposta)


def _fechar(ids: list[int], status: str, *, erro: str | None = None, resposta: str | None = None,
            uso: dict | None = None, id_usuario: int | None = None, fone: str | None = None) -> None:
    with get_cursor() as cur:
        cur.execute("""UPDATE assistente_conversa SET status = %s, erro = %s, atualizada_em = now()
                        WHERE id = ANY(%s)""", (status, (erro or "")[:500] or None, ids))
        if resposta and id_usuario and fone:
            cur.execute("""INSERT INTO assistente_conversa (id_usuario, papel, texto, uso)
                           VALUES (%s, 'assistente', %s, %s) RETURNING id""",
                        (id_usuario, resposta, json.dumps(uso) if uso else None))
            id_resp = cur.fetchone()["id"]
            assistente.responder(cur, f"conversa:{id_resp}", fone, resposta, id_usuario)
    if resposta:
        assistente.processar_fila()


def _historico(cur, id_usuario: int, pendentes: list[int]) -> list[dict]:
    """As últimas falas respondidas (horas, não dias): é o que dá sentido a "e a receita dele?"."""
    cur.execute("""SELECT papel, texto FROM assistente_conversa
                    WHERE id_usuario = %s AND NOT (id = ANY(%s))
                      AND (papel = 'assistente' OR status = 'RESPONDIDA')
                      AND criada_em >= now() - %s
                    ORDER BY criada_em DESC, id DESC LIMIT %s""",
                (id_usuario, pendentes, JANELA_HISTORICO, HISTORICO))
    falas = list(reversed([dict(x) for x in cur.fetchall()]))
    # ⚠️ A API exige que comece pelo usuário e alterne: falas seguidas do mesmo lado se juntam.
    msgs: list[dict] = []
    for f in falas:
        papel = "user" if f["papel"] == "usuario" else "assistant"
        if not msgs and papel == "assistant":
            continue
        if msgs and msgs[-1]["role"] == papel:
            msgs[-1]["content"] += "\n" + f["texto"]
        else:
            msgs.append({"role": papel, "content": f["texto"]})
    if msgs and msgs[-1]["role"] == "user":
        msgs.pop()   # pergunta sem resposta guardada: não deixa dois "user" seguidos
    return msgs


def _contexto(cur, id_usuario: int, quem: dict | None) -> str:
    """O que muda a cada pergunta (data, nome, lojas). ⚠️ Vai na MENSAGEM, não no sistema: o
    sistema e as ferramentas ficam idênticos entre pedidos, e é isso que o cache aproveita."""
    from seguranca import carregar_contexto
    try:
        ctx = carregar_contexto(id_usuario)
    except Exception:  # noqa: BLE001
        return ""
    cur.execute("SELECT id, nome, apelido FROM unidades WHERE ativo ORDER BY matriz DESC, nome")
    lojas = [f"{r['apelido'] or r['nome']} (id {r['id']})" for r in cur.fetchall()
             if ctx.ve_unidade(r["id"])]
    agora = agora_da_casa()
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return (f"[Agora: {dias[agora.weekday()]}-feira, {agora:%d/%m/%Y %H:%M}. "
            f"Quem pergunta: {(quem or {}).get('nome') or 'funcionário'}. "
            f"Lojas que vê: {', '.join(lojas) or 'nenhuma'}.]").replace("sábado-feira", "sábado") \
        .replace("domingo-feira", "domingo")


# ---------------------------------------------------------------- o Claude
class _Temporario(Exception):
    """Vale tentar de novo (429, 5xx, rede)."""


class _Definitivo(Exception):
    """Não adianta repetir (chave inválida, pedido recusado pela API)."""


def _corpo(cfg: dict, casa: str, mensagens: list[dict]) -> dict:
    modelo = cfg["modelo"]
    corpo = {
        "model": modelo,
        "max_tokens": 16000,
        # 🔑 Sistema estável + breakpoint de cache: ferramentas e sistema (renderizados antes das
        # mensagens) saem do cache a partir da segunda pergunta.
        "system": [{"type": "text", "text": SISTEMA.format(casa=casa),
                    "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": f.nome, "description": f.descricao, "input_schema": f.esquema()}
                  for f in _FERRAMENTAS],
        "messages": mensagens,
    }
    if not modelo.startswith(_SEM_EFFORT):
        # Consulta de balcão, não engenharia: esforço baixo responde rápido e gasta pouco.
        corpo["output_config"] = {"effort": "low"}
    if modelo.startswith(_COM_FALLBACK):
        corpo["fallbacks"] = "default"
    return corpo


def _cabecalhos(cfg: dict) -> dict:
    cab = {"x-api-key": cfg["chave"], "anthropic-version": VERSAO_API,
           "content-type": "application/json"}
    if cfg["modelo"].startswith(_COM_FALLBACK):
        cab["anthropic-beta"] = "server-side-fallback-2026-07-01"
    return cab


def _pedir(cliente: httpx.AsyncClient, cfg: dict, corpo: dict):
    return cliente.post(cfg["url"], json=corpo, headers=_cabecalhos(cfg))


async def _conversar(cfg: dict, quem: dict, historico: list[dict], contexto: str,
                     pergunta: str) -> tuple[str, dict]:
    with get_cursor() as cur:
        casa = assistente_casa(cur)
    mensagens = historico + [{"role": "user", "content": f"{contexto}\n\n{pergunta}".strip()}]
    from seguranca import criar_access_token
    # 🔑 A credencial é do PRÓPRIO usuário, de vida curta: cada ferramenta passa pela mesma
    # conferência de permissão e loja de um pedido da tela.
    credencial, _ = criar_access_token(int(quem["id"]), quem["email"])
    uso = {"modelo": cfg["modelo"], "voltas": 0, "entrada": 0, "saida": 0, "cache_lido": 0,
           "cache_criado": 0, "ferramentas": []}
    async with httpx.AsyncClient(timeout=120) as cliente:
        for _ in range(MAX_VOLTAS):
            try:
                r = await _pedir(cliente, cfg, _corpo(cfg, casa, mensagens))
            except httpx.HTTPError as e:
                raise _Temporario(f"rede: {e}") from e
            if r.status_code == 429 or r.status_code >= 500:
                raise _Temporario(f"HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code >= 400:
                raise _Definitivo(f"HTTP {r.status_code}: {r.text[:300]}")
            resp = r.json()
            uso["voltas"] += 1
            u = resp.get("usage") or {}
            uso["entrada"] += u.get("input_tokens") or 0
            uso["saida"] += u.get("output_tokens") or 0
            uso["cache_lido"] += u.get("cache_read_input_tokens") or 0
            uso["cache_criado"] += u.get("cache_creation_input_tokens") or 0
            parada = resp.get("stop_reason")
            # ⚠️ Recusa vem com HTTP 200: olhar o stop_reason ANTES de ler o conteúdo.
            if parada == "refusal":
                return ("Não posso ajudar com isso por aqui. Pergunte sobre a casa: pendências, "
                        "receitas, estoque, vendas."), uso
            conteudo = resp.get("content") or []
            if parada != "tool_use":
                texto = "\n".join(b.get("text", "") for b in conteudo if b.get("type") == "text")
                return _caber(texto.strip() or "Não encontrei o que responder."), uso
            # 🔑 O conteúdo volta INTEIRO (pensamento incluso): é o que a API exige no laço.
            mensagens.append({"role": "assistant", "content": conteudo})
            resultados = []
            for b in conteudo:
                if b.get("type") != "tool_use":
                    continue
                uso["ferramentas"].append(b.get("name"))
                resultados.append(await _executar(credencial, b))
            mensagens.append({"role": "user", "content": resultados})
    return ("A pergunta ficou grande demais para responder de uma vez. Tente algo mais "
            "específico — uma loja, um produto ou um dia."), uso


async def _executar(credencial: str, bloco: dict) -> dict:
    nome, args = bloco.get("name"), bloco.get("input") or {}
    base = {"type": "tool_result", "tool_use_id": bloco.get("id")}
    if nome not in _PERMITIDAS:
        # ⚠️ Pedido de ferramenta que grava (ou inventada): nada é chamado.
        return base | {"is_error": True, "content": (
            f"A ferramenta {nome} não está disponível pelo WhatsApp: nesta versão o assistente "
            "só consulta.")}
    if _APP is None:
        return base | {"is_error": True, "content": "O sistema ainda está subindo; tente de novo."}
    try:
        texto = await mcp_ferramentas.chamar(_APP, credencial, nome, args)
    except mcp_ferramentas.ErroFerramenta as e:
        return base | {"is_error": True, "content": str(e)}
    except Exception as e:  # noqa: BLE001
        log.exception("assistente: ferramenta %s falhou", nome)
        return base | {"is_error": True, "content": f"Falha ao consultar: {e}"}
    if len(texto) > LIMITE_RESULTADO:
        texto = (texto[:LIMITE_RESULTADO] + f"\n…[CORTADO: {len(texto)} caracteres. Refaça com "
                 "filtro, período menor ou limite menor.]")
    return base | {"content": texto}


def _caber(texto: str) -> str:
    if len(texto) <= LIMITE_WHATSAPP:
        return texto
    return texto[:LIMITE_WHATSAPP].rsplit("\n", 1)[0] + "\n…(resposta cortada — peça por partes)"


def assistente_casa(cur) -> str:
    cur.execute("SELECT nome_fantasia, razao_social FROM empresa WHERE id = 1")
    e = cur.fetchone() or {}
    return e.get("nome_fantasia") or e.get("razao_social") or "uma casa de alimentação"


# ---------------------------------------------------------------- a faxina
def limpar(cur) -> None:
    """Conversa e fila do assistente somem em 30 dias: é conversa de funcionário, não registro."""
    cur.execute("DELETE FROM assistente_conversa WHERE criada_em < now() - %s * interval '1 day'",
                (GUARDAR_DIAS,))
    cur.execute("DELETE FROM assistente_mensagens WHERE criada_em < now() - %s * interval '1 day'",
                (GUARDAR_DIAS,))
