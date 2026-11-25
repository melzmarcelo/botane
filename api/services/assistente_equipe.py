"""O assistente pelo WhatsApp, etapa 6 — os avisos à EQUIPE (migração 164).

🔑 **Pedido do dono (25/11/2026):** *"o cliente entra e reserva uma mesa. O sistema dispara para o
WhatsApp do cliente o aviso, e também para o WhatsApp da loja para avisar que tem uma nova reserva,
e este confirma … pode realizar ações na reserva pelo sistema ou pelo próprio WhatsApp da loja"* —
e, perguntado, o mesmo para os pedidos do site.

Decisões (25/11/2026, todas as recomendadas):
- **Quem recebe são USUÁRIOS vinculados ao assistente**, não uma lista de telefones: cada um liga
  "reserva nova" / "pedido novo" no Perfil, e só recebe quem tem a permissão de AGIR naquela loja
  (`reservas.editar`, `pedidos.operar`). O botão age com a permissão de quem tocou, conferida de
  novo no toque, e a auditoria marca `origem = whatsapp`.
- **O mesmo número dos clientes**: o assistente pode usar um número de loja (`assistente.conexao`,
  `id_whatsapp_loja`), e o webhook separa pela PESSOA e pelo botão (`assistente.e_da_equipe`).
- Reserva nova avisa só a que espera a casa (PENDENTE): a confirmada sozinha não pede nada, e
  entra na contagem do bom dia.

⚠️ **Mensagem que o sistema INICIA é sempre MODELO aprovado pela Meta**, com variáveis sem quebra
de linha: por isso o resumo é uma linha só e os itens do pedido vão separados por vírgula. Os dois
botões são de resposta rápida, e o payload volta no webhook como `type: button`.
"""

import re
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import auditoria

PREFIXO = "EQUIPE:"
BOTOES = ["Confirmar", "Recusar"]
IDIOMA_PADRAO = "pt_BR"

AVISOS: dict[str, dict] = {
    "reserva": {
        "titulo": "Reserva nova pelo site",
        "coluna": "avisos_reserva",
        "permissao": "reservas.editar",
        "modelo": "botane_reserva_nova",
        # {{1}} loja · {{2}} cliente · {{3}} dia · {{4}} hora · {{5}} pessoas · {{6}} telefone
        "texto": "Nova reserva pelo site no {{1}}: {{2}}, {{3}} às {{4}}, {{5}} pessoa(s). "
                 "Telefone: {{6}}. Confirme ou recuse pelos botões abaixo ou na agenda do sistema.",
    },
    "pedido": {
        "titulo": "Pedido novo pelo site",
        "coluna": "avisos_pedido",
        "permissao": "pedidos.operar",
        "modelo": "botane_pedido_novo",
        # {{1}} número · {{2}} loja · {{3}} cliente · {{4}} retirada/entrega · {{5}} quando ·
        # {{6}} itens · {{7}} total
        "texto": "Novo pedido nº {{1}} pelo site no {{2}}: {{3}}, {{4}} para {{5}}. Itens: {{6}}. "
                 "Total: R$ {{7}}. Confirme ou recuse pelos botões abaixo ou no painel de pedidos.",
    },
}
_STATUS_RESERVA = {"PENDENTE": "aguardando a casa", "CONFIRMADA": "confirmada",
                   "CHEGOU": "com o cliente já na casa", "ENCERRADA": "encerrada",
                   "CANCELADA": "cancelada", "NAO_COMPARECEU": "marcada como não compareceu"}


def configuracao(c: dict) -> dict:
    """Os avisos à equipe da casa, a partir da conexão do assistente (`assistente.conexao`)."""
    saida = {tipo: {"ligado": bool(c.get(f"equipe_{tipo}_ligado")),
                    "modelo": (c.get(f"equipe_{tipo}_modelo") or "").strip() or a["modelo"],
                    "titulo": a["titulo"], "texto_do_modelo": a["texto"]}
             for tipo, a in AVISOS.items()}
    saida["idioma"] = (c.get("equipe_idioma") or "").strip() or IDIOMA_PADRAO
    saida["botoes"] = BOTOES
    return saida


def _limpo(v, limite: int = 120) -> str:
    """Variável de modelo: sem quebra de linha, tabulação nem espaço repetido (a Meta recusa)."""
    t = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    return t if len(t) <= limite else t[:limite - 1].rstrip() + "…"


def _montar(texto: str, variaveis: list[str]) -> str:
    for n, v in enumerate(variaveis, start=1):
        texto = texto.replace("{{%d}}" % n, v)
    return texto


def _loja(cur, id_unidade: int) -> str:
    cur.execute("SELECT coalesce(nullif(apelido, ''), nome) AS n FROM unidades WHERE id = %s",
                (id_unidade,))
    linha = cur.fetchone()
    return linha["n"] if linha else "loja"


def destinatarios(cur, id_unidade: int, tipo: str) -> list[dict]:
    """Quem ligou o aviso, está vinculado e ativo, tem o assistente, pode AGIR e vê a loja."""
    from services import assistente
    a = AVISOS[tipo]
    cur.execute(
        f"""SELECT v.id_usuario, v.wa_id, u.nome
              FROM usuario_whatsapp v JOIN usuarios u ON u.id = v.id_usuario AND u.ativo
             WHERE v.wa_id IS NOT NULL AND v.{a['coluna']}
               AND EXISTS (SELECT 1 FROM usuario_papeis up
                             JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
                            WHERE up.id_usuario = v.id_usuario AND pp.chave = %s)
               AND EXISTS (SELECT 1 FROM usuario_papeis up
                             JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
                            WHERE up.id_usuario = v.id_usuario AND pp.chave = %s)
               AND EXISTS (SELECT 1 FROM usuario_papeis up
                            WHERE up.id_usuario = v.id_usuario
                              AND (up.id_unidade IS NULL OR up.id_unidade = %s))
             ORDER BY v.id_usuario""",
        (assistente.PERMISSAO, a["permissao"], id_unidade))
    return [dict(r) for r in cur.fetchall()]


def _enfileirar(cur, tipo: str, id_unidade: int, id_coisa: int, variaveis: list[str]) -> int:
    """Um modelo para cada pessoa que deve receber. ⚠️ A chave por pessoa e por coisa impede
    avisar duas vezes a mesma reserva (o site pode reenviar)."""
    from services import assistente
    c = assistente.conexao(cur)
    cfg = configuracao(c)
    if not (c["ativa"] and cfg[tipo]["ligado"]):
        return 0
    texto = _montar(AVISOS[tipo]["texto"], variaveis)
    botoes = [f"{PREFIXO}{tipo}:CONFIRMAR:{id_coisa}", f"{PREFIXO}{tipo}:RECUSAR:{id_coisa}"]
    n = 0
    for d in destinatarios(cur, id_unidade, tipo):
        n += assistente.responder(
            cur, f"equipe:{tipo}:{id_coisa}:{d['id_usuario']}", d["wa_id"], texto, d["id_usuario"],
            modelo={"nome": cfg[tipo]["modelo"], "idioma": cfg["idioma"], "variaveis": variaveis,
                    "botoes": botoes})
    return n


def reserva_nova(cur, id_unidade: int, id_reserva: int) -> int:
    """Chamado na MESMA transação da reserva feita pelo site. Só a que espera a casa avisa."""
    cur.execute("""SELECT id, nome, telefone, data, hora, pessoas, status FROM reservas
                    WHERE id = %s AND id_unidade = %s""", (id_reserva, id_unidade))
    r = cur.fetchone()
    if not r or r["status"] != "PENDENTE":
        return 0
    variaveis = [_limpo(_loja(cur, id_unidade), 60), _limpo(r["nome"] or "cliente", 80),
                 f"{r['data']:%d/%m}", f"{r['hora']:%H:%M}", str(r["pessoas"]),
                 _limpo(r["telefone"] or "não informado", 30)]
    return _enfileirar(cur, "reserva", id_unidade, r["id"], variaveis)


def _qtd(v) -> str:
    t = f"{v:f}".rstrip("0").rstrip(".") if v is not None else "1"
    return t.replace(".", ",")


def pedido_novo(cur, id_unidade: int, id_pedido: int) -> int:
    """Chamado na MESMA transação do pedido que o site gravou (retirada ou entrega)."""
    from config import FUSO_DA_CASA
    cur.execute("""SELECT id, numero, nome, modo, para_quando, total, situacao FROM pedidos
                    WHERE id = %s AND id_unidade = %s""", (id_pedido, id_unidade))
    p = cur.fetchone()
    if not p or p["situacao"] != "NOVO" or p["modo"] == "MESA":
        return 0
    cur.execute("SELECT nome, quantidade FROM pedido_itens WHERE id_pedido = %s ORDER BY ordem, id",
                (id_pedido,))
    itens = ", ".join(f"{_qtd(i['quantidade'])}x {i['nome']}" for i in cur.fetchall()) or "—"
    quando = (p["para_quando"].astimezone(ZoneInfo(FUSO_DA_CASA)).strftime("%d/%m às %H:%M")
              if p["para_quando"] else "o quanto antes")
    variaveis = [str(p["numero"]), _limpo(_loja(cur, id_unidade), 60), _limpo(p["nome"] or "cliente", 80),
                 "retirada na loja" if p["modo"] == "RETIRADA" else "entrega", quando,
                 _limpo(itens, 400), f"{p['total']:.2f}".replace(".", ",")]
    return _enfileirar(cur, "pedido", id_unidade, p["id"], variaveis)


# ---------------------------------------------------------------- o toque no botão
def _primeiro(nome: str | None) -> str:
    return (nome or "").split(" ")[0] or "tudo bem"


def tocou(cur, id_usuario: int, payload: str) -> str:
    """Confirmar / Recusar, com a permissão de QUEM TOCOU (conferida agora, não no envio).

    Devolve a frase de resposta. ⚠️ O id do botão é só um número: quem decide se pode é o
    usuário e a loja da reserva/pedido, nunca o fato de a mensagem ter chegado a ele.
    """
    from seguranca import carregar_contexto
    partes = payload.split(":")
    if len(partes) != 4 or partes[1] not in AVISOS or partes[2] not in ("CONFIRMAR", "RECUSAR") \
            or not partes[3].isdigit():
        return "Não entendi esse botão. Nada foi feito."
    tipo, acao, id_coisa = partes[1], partes[2], int(partes[3])
    try:
        ctx = carregar_contexto(id_usuario)
    except HTTPException:
        return "Seu usuário não está ativo. Nada foi feito."
    marca = auditoria.origem_do_pedido.set("whatsapp")
    try:
        if tipo == "reserva":
            return _reserva(cur, ctx, acao, id_coisa)
        return _pedido(cur, ctx, acao, id_coisa)
    finally:
        auditoria.origem_do_pedido.reset(marca)


def _reserva(cur, ctx, acao: str, id_reserva: int) -> str:
    from services import reservas_agenda as agenda
    from services import whatsapp
    cur.execute("""SELECT id, id_unidade, nome, data, hora, pessoas, status FROM reservas
                    WHERE id = %s FOR UPDATE""", (id_reserva,))
    r = cur.fetchone()
    if not r:
        return "Não encontrei essa reserva. Nada foi feito."
    loja = r["id_unidade"]
    if not (ctx.pode(AVISOS["reserva"]["permissao"]) and ctx.ve_unidade(loja)):
        return f"{_primeiro(ctx.nome)}, seu usuário não pode mudar as reservas dessa loja. Nada foi feito."
    resumo = f"a reserva de {r['nome']} ({r['data']:%d/%m} às {r['hora']:%H:%M}, {r['pessoas']} pessoa(s))"
    # ⚠️ Os botões respondem ao aviso de reserva NOVA: só agem sobre a que ainda espera a casa.
    # Sem isto, "Recusar" tocado depois de alguém confirmar pela tela CANCELAVA a reserva
    # (CONFIRMADA → CANCELADA é um caminho válido da agenda) — achado na suíte.
    if r["status"] != "PENDENTE":
        return f"Nada mudou: {resumo} já está {_STATUS_RESERVA.get(r['status'], r['status'].lower())}."
    novo = "CONFIRMADA" if acao == "CONFIRMAR" else "CANCELADA"
    feito = agenda.mudar_status(cur, loja, id_reserva, novo)
    whatsapp.reserva_mudou(cur, loja, id_reserva, pela_casa=True)
    auditoria.registrar(cur, ctx.id_usuario, "reserva", id_reserva, "status",
                        antes={"status": feito["de"]}, depois={"status": feito["para"]},
                        id_unidade=loja)
    if novo == "CONFIRMADA":
        return f"Feito, {_primeiro(ctx.nome)}: {resumo} está confirmada."
    return f"Feito, {_primeiro(ctx.nome)}: {resumo} foi recusada e está cancelada."


def _pedido(cur, ctx, acao: str, id_pedido: int) -> str:
    from services import pedidos
    cur.execute("SELECT id, id_unidade, numero, nome, situacao FROM pedidos WHERE id = %s", (id_pedido,))
    p = cur.fetchone()
    if not p:
        return "Não encontrei esse pedido. Nada foi feito."
    loja = p["id_unidade"]
    if not (ctx.pode(AVISOS["pedido"]["permissao"]) and ctx.ve_unidade(loja)):
        return f"{_primeiro(ctx.nome)}, seu usuário não pode mexer nos pedidos dessa loja. Nada foi feito."
    try:
        if acao == "CONFIRMAR":
            pedidos.confirmar(cur, loja, id_pedido, ctx.id_usuario, {})
        else:
            pedidos.recusar(cur, loja, id_pedido, ctx.id_usuario, "Recusado pelo WhatsApp")
    except HTTPException as e:
        if e.status_code != 409:
            raise
        cur.execute("SELECT situacao FROM pedidos WHERE id = %s", (id_pedido,))
        return f"Nada mudou: o pedido nº {p['numero']} já está {cur.fetchone()['situacao'].lower()}."
    auditoria.registrar(cur, ctx.id_usuario, "pedido", id_pedido,
                        "confirmar" if acao == "CONFIRMAR" else "recusar",
                        depois={"numero": p["numero"], "pelo_whatsapp": True}, id_unidade=loja)
    if acao == "CONFIRMAR":
        return f"Feito, {_primeiro(ctx.nome)}: o pedido nº {p['numero']} de {p['nome']} está confirmado."
    return f"Feito, {_primeiro(ctx.nome)}: o pedido nº {p['numero']} de {p['nome']} foi recusado."
