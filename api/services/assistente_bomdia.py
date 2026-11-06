"""O assistente pelo WhatsApp, etapa 5 — o "bom dia" com as pendências (migração 155).

🔑 Estudo em `docs/assistente-whatsapp-estudo.md`: às 7h (configurável), um modelo aprovado
"Bom dia, {{1}}! Hoje você tem {{2}} na agenda de produção." para quem ligou a opção no Perfil.

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
# nome; {{2}} = "3 itens" / "1 item". Os botões são de resposta rápida, nesta ordem.
TEXTO_DO_MODELO = "Bom dia, {{1}}! Hoje você tem {{2}} na agenda de produção."
BOTOES = [{"payload": "BOMDIA:VER", "titulo": "Ver pendências"},
          {"payload": "BOMDIA:PARAR", "titulo": "Parar o bom dia"}]
PERGUNTA = "Quais são as minhas pendências de hoje?"


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
            except Exception:  # noqa: BLE001 — falhou a contagem de UM: os outros seguem
                log.exception("bom dia: falha ao contar as pendências de %s", quem["id_usuario"])
                continue
            if n == 0 and cfg["so_com_pendencia"]:
                continue
            primeiro = (u["nome"] or "").split(" ")[0] or "tudo bem"
            variaveis = [primeiro, _quantos(n) if n else "nada"]
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
