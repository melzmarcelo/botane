"""O assistente pelo WhatsApp, etapa 5 — o "bom dia" com as pendências (migração 155).

🔑 Estudo em `docs/assistente-whatsapp-estudo.md`: às 7h (configurável), um modelo aprovado
"Bom dia, {{1}}! Para hoje: {{2}}. …" para quem ligou a opção no Perfil — {{2}} com a agenda de
produção e, desde a 164, as reservas do dia.

Por que assim:
- ⚠️ **Mensagem que o sistema inicia é sempre MODELO aprovado pela Meta** (fora da janela de
  24 h não existe texto livre), e variável de modelo não aceita quebra de linha. Uma lista de
  pendências não cabe ali — um número cabe.
- 🔑 **A contagem é do sistema, sem o Claude**: a agenda de cada loja da pessoa, pela rota de
  sempre, com a credencial dela. Custa zero e não falha por causa da Anthropic.
- 🔑 **O detalhe é sob demanda**: o botão "Ver pendências" volta pelo webhook, abre a janela de
  24 h e vira a pergunta "quais as minhas pendências de hoje?" — respondida pelo Claude por
  inteiro, sem custo de mensagem na Meta. "Parar o bom dia" desliga a opção da pessoa.

`varrer` roda a cada volta do laço do WhatsApp (30 s) e não faz nada fora da janela do horário
(da hora marcada até duas horas depois — o contêiner que reinicia às 7h10 ainda manda; o que
reinicia às 15h não manda um bom dia à tarde).
"""

import asyncio
import json
import logging
from datetime import datetime, time, timedelta

from database import get_cursor
from relogio import agora_da_casa

log = logging.getLogger("botane.assistente")

MODELO_PADRAO = "botane_bom_dia"
JANELA = timedelta(hours=2)
# O texto do modelo, pronto para a casa cadastrar na Meta (categoria Utilidade). {{1}} = o primeiro
# nome; {{2}} = o resumo ("3 itens na agenda de produção e 2 reservas (9 pessoas)"). Os botões são
# de resposta rápida, nesta ordem.
# 🔑 164 (25/11/2026): as reservas do dia entram aqui (decisão do dono: "no bom dia"), e por isso o
# texto deixou de dizer "na agenda de produção" fixo. ⚠️ A Meta recusa modelo que TERMINA em
# variável: a frase final existe por isso.
TEXTO_DO_MODELO = "Bom dia, {{1}}! Para hoje: {{2}}. Toque em Ver pendências para os detalhes."
BOTOES = [{"payload": "BOMDIA:VER", "titulo": "Ver pendências"},
          {"payload": "BOMDIA:PARAR", "titulo": "Parar o bom dia"}]
PERGUNTA = "Quais são as minhas pendências e as reservas de hoje?"


def configuracao(c: dict) -> dict:
    """O bom dia da casa, a partir da conexão do assistente (`assistente.conexao`)."""
    hora = c.get("bom_dia_hora") or "07:00"
    return {
        "ligado": bool(c.get("bom_dia_ligado")),
        "hora": hora,
        "dias": list(c.get("bom_dia_dias") or [1, 2, 3, 4, 5, 6]),
        "so_com_pendencia": c.get("bom_dia_so_com_pendencia") is not False,
        "modelo": (c.get("bom_dia_modelo") or "").strip() or MODELO_PADRAO,
        "idioma": (c.get("bom_dia_idioma") or "").strip() or "pt_BR",
    }


def _na_janela(cfg: dict, agora: datetime) -> bool:
    if agora.isoweekday() not in cfg["dias"]:
        return False
    h, m = (int(x) for x in cfg["hora"].split(":"))
    inicio = datetime.combine(agora.date(), time(h, m), tzinfo=agora.tzinfo)
    return inicio <= agora < inicio + JANELA


def _quantos(n: int) -> str:
    return "1 item" if n == 1 else f"{n} itens"


def resumo(producao: int, reservas: int, pessoas: int) -> str:
    """A variável {{2}}: "3 itens na agenda de produção e 2 reservas (9 pessoas)"."""
    partes = []
    if producao:
        partes.append(f"{_quantos(producao)} na agenda de produção")
    if reservas:
        partes.append(f"{reservas} reserva{'s' if reservas != 1 else ''} "
                      f"({pessoas} pessoa{'s' if pessoas != 1 else ''})")
    return " e ".join(partes) or "nada pendente"


def contar_reservas(id_usuario: int, dia) -> tuple[int, int]:
    """164: as reservas do dia (aguardando ou confirmadas) nas lojas em que a pessoa VÊ reservas."""
    from seguranca import carregar_contexto
    ctx = carregar_contexto(id_usuario)
    if not ctx.pode("reservas.ver"):
        return 0, 0
    with get_cursor() as cur:
        cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id")
        lojas = [r["id"] for r in cur.fetchall() if ctx.ve_unidade(r["id"])]
        cur.execute("""SELECT count(*) AS n, coalesce(sum(pessoas), 0) AS p FROM reservas
                        WHERE id_unidade = ANY(%s) AND data = %s
                          AND status IN ('PENDENTE', 'CONFIRMADA')""", (lojas, dia))
        r = cur.fetchone()
    return int(r["n"]), int(r["p"])


async def _contar(id_usuario: int, email: str) -> int:
    """As linhas de HOJE e as atrasadas, em cada loja que a pessoa vê — pela rota da agenda."""
    from seguranca import carregar_contexto, criar_access_token
    from services import assistente_conversa, mcp_ferramentas
    app = assistente_conversa._APP
    if app is None:
        raise RuntimeError("app não registrado")
    ctx = carregar_contexto(id_usuario)
    with get_cursor() as cur:
        cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id")
        lojas = [r["id"] for r in cur.fetchall() if ctx.ve_unidade(r["id"])]
    credencial, _ = criar_access_token(id_usuario, email)
    hoje = agora_da_casa().date().isoformat()
    total = 0
    for loja in lojas:
        try:
            bruto = await mcp_ferramentas.chamar(app, credencial, "agenda_producao", {"id_loja": loja})
        except mcp_ferramentas.ErroFerramenta:
            continue   # sem permissão de agenda naquela loja: não conta, não quebra
        for linha in (json.loads(bruto) or {}).get("linhas") or []:
            if str(linha.get("data_prevista"))[:10] <= hoje or linha.get("atrasada"):
                total += 1
    return total


def varrer(agora: datetime | None = None) -> int:
    """Manda o bom dia de quem pediu, uma vez por dia, dentro da janela. Devolve quantos saíram.

    🔑 **Reivindica antes de contar**: `bom_dia_em = hoje` num UPDATE condicional — o processo que
    pegou a pessoa é o único que manda, mesmo com o webhook e o laço rodando juntos.
    ⚠️ Nunca levanta (roda no laço).
    """
    agora = agora or agora_da_casa()
    enviados = 0
    try:
        from services import assistente
        with get_cursor() as cur:
            c = assistente.conexao(cur)
        cfg = configuracao(c)
        if not (c["ativa"] and cfg["ligado"] and _na_janela(cfg, agora)):
            return 0
        hoje = agora.date()
        while True:
            with get_cursor() as cur:
                cur.execute(
                    """UPDATE usuario_whatsapp v SET bom_dia_em = %s
                        WHERE v.id_usuario = (
                              SELECT x.id_usuario FROM usuario_whatsapp x
                                JOIN usuarios u ON u.id = x.id_usuario AND u.ativo
                               WHERE x.bom_dia AND x.wa_id IS NOT NULL
                                 AND x.bom_dia_em IS DISTINCT FROM %s
                                 AND EXISTS (SELECT 1 FROM usuario_papeis up
                                               JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
                                              WHERE up.id_usuario = x.id_usuario AND pp.chave = %s)
                               ORDER BY x.id_usuario LIMIT 1 FOR UPDATE OF x SKIP LOCKED)
                    RETURNING v.id_usuario, v.wa_id""",
                    (hoje, hoje, assistente.PERMISSAO))
                quem = cur.fetchone()
                if not quem:
                    break
                cur.execute("SELECT nome, email FROM usuarios WHERE id = %s", (quem["id_usuario"],))
                u = cur.fetchone()
            try:
                n = asyncio.run(_contar(quem["id_usuario"], u["email"]))
                reservas, pessoas = contar_reservas(quem["id_usuario"], hoje)
            except Exception:  # noqa: BLE001 — falhou a contagem de UM: os outros seguem
                log.exception("bom dia: falha ao contar as pendências de %s", quem["id_usuario"])
                continue
            if n == 0 and reservas == 0 and cfg["so_com_pendencia"]:
                continue
            primeiro = (u["nome"] or "").split(" ")[0] or "tudo bem"
            variaveis = [primeiro, resumo(n, reservas, pessoas)]
            texto = TEXTO_DO_MODELO.replace("{{1}}", variaveis[0]).replace("{{2}}", variaveis[1])
            with get_cursor() as cur:
                assistente.responder(
                    cur, f"bomdia:{quem['id_usuario']}:{hoje}", quem["wa_id"], texto,
                    quem["id_usuario"], modelo={"nome": cfg["modelo"], "idioma": cfg["idioma"],
                                                "variaveis": variaveis,
                                                "botoes": [b["payload"] for b in BOTOES]})
            enviados += 1
        if enviados:
            assistente.processar_fila()
    except Exception:  # noqa: BLE001
        log.exception("bom dia: falha na varredura")
    return enviados


def tocou(cur, id_usuario: int, payload: str) -> str | None:
    """O botão do bom dia. "Ver" vira pergunta (devolve None: o Claude responde); "Parar"
    desliga a opção e devolve a frase."""
    if payload == "BOMDIA:PARAR":
        cur.execute("UPDATE usuario_whatsapp SET bom_dia = false WHERE id_usuario = %s", (id_usuario,))
        return ("Pronto, não mando mais o bom dia. Para voltar a receber: Perfil ▸ Assistente no "
                "WhatsApp.")
    return None
