"""O assistente pelo WhatsApp, etapa 4 — LANÇAR produção, com confirmação por botão (migração 154).

🔑 **Pedido do dono (06/11/2026):** *"depois posso confirmar a produção e o sistema já lança e
coloca em estoque"*. Estudo em `docs/assistente-whatsapp-estudo.md`.

Como funciona:
1. O Claude pede uma ferramenta de gravação (`GRAVAVEIS`). **Nada é chamado.** `propor` monta a
   PRÉVIA com as rotas de leitura (o produto, a quantidade, o que sai do estoque, o que falta) e
   guarda a ação PENDENTE. Ao Claude volta "preparado, esperando o botão".
2. A pessoa recebe a prévia com dois botões. O id do botão carrega o id da ação.
3. O webhook entrega o toque a `tocou_botao`: confere que a ação é DESTA pessoa, está pendente e
   não venceu. Cancelar responde na hora; confirmar marca CONFIRMADA.
4. `processar_confirmadas` (logo depois do 200, e no laço de reserva) lança com um token da
   própria pessoa marcado `origem = whatsapp` — a auditoria diz por onde veio.

⚠️ **A prévia é do SISTEMA, não do Claude**: o texto do botão sai das rotas de leitura com os
MESMOS argumentos que vão ser gravados. O que a pessoa confirma é o que vai ser lançado, mesmo
que o Claude tenha escrito outra coisa na conversa.
⚠️ A rota ainda confere a permissão de produção da pessoa: `integracao.whatsapp_lancar` só abre o
caminho pelo WhatsApp.
"""

import asyncio
import json
import logging
from datetime import timedelta

from database import get_cursor

log = logging.getLogger("botane.assistente")

PERMISSAO = "integracao.whatsapp_lancar"
GRAVAVEIS = ("produzir_da_agenda", "produzir")
VALIDADE = timedelta(minutes=10)
LIMITE_BOTAO = 1000   # o corpo da mensagem com botões vai até 1024


def pode_lancar(cur, id_usuario: int) -> bool:
    cur.execute("""SELECT 1 FROM usuario_papeis up
                     JOIN papel_permissoes pp ON pp.id_papel = up.id_papel
                    WHERE up.id_usuario = %s AND pp.chave = %s LIMIT 1""", (id_usuario, PERMISSAO))
    return cur.fetchone() is not None


def _num(v) -> str:
    """10.0 → "10"; 2.5 → "2,5"; 0.125 → "0,125"."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    texto = f"{f:.3f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _itens(previsao: dict) -> list[str]:
    linhas = []
    itens = [i for i in previsao.get("itens") or [] if not i.get("sem_estoque")]
    for i in itens[:8]:
        qtd = i.get("necessario")
        um = i.get("um_estoque") or i.get("um_ficha") or ""
        linhas.append(f"• {i.get('produto')}: {_num(qtd)} {um}".rstrip())
    if len(itens) > 8:
        linhas.append(f"• … e mais {len(itens) - 8}")
    faltas = [i for i in itens if (i.get("falta") or 0) > 0]
    if faltas:
        linhas.append("⚠️ Falta no estoque: " + ", ".join(
            f"{i.get('produto')} ({_num(i['falta'])} {i.get('um_estoque') or ''})".replace(" )", ")")
            for i in faltas[:5]))
    return linhas


async def _ler(chamar, nome: str, args: dict) -> dict:
    return json.loads(await chamar(nome, args))


async def resumo(chamar, ferramenta: str, args: dict) -> str:
    """A prévia do que vai ser lançado, das rotas de LEITURA, com os mesmos argumentos.

    `chamar(nome, args)` executa uma ferramenta como a pessoa. Erro de leitura (linha que não
    existe, produto sem ficha) sobe como `ErroFerramenta` — e a ação nem nasce.
    """
    loja = {"id_loja": args["id_loja"]} if args.get("id_loja") is not None else {}
    if ferramenta == "produzir_da_agenda":
        linha = await _ler(chamar, "item_da_agenda", {"id_agenda": args["id_agenda"]} | loja)
        um = linha.get("um_estoque") or ""
        qtd = args.get("quantidade") or linha.get("quantidade")
        cab = f"*Produzir da agenda:* {_num(qtd)} {um} de *{linha.get('produto')}*".replace("  ", " ")
        if args.get("quantidade") and float(args["quantidade"]) != float(linha.get("quantidade") or 0):
            cab += f" (planejado: {_num(linha.get('quantidade'))})"
        previsao = linha.get("previsao") or {}
        if args.get("quantidade"):
            # A prévia da agenda é da quantidade PLANEJADA; com outra quantidade, refaz.
            previsao = await _ler(chamar, "necessario_para_produzir",
                                  {"id_produto": linha["id_produto"], "quantidade": args["quantidade"]} | loja)
    elif ferramenta == "produzir":
        previsao = await _ler(chamar, "necessario_para_produzir", {
            k: args[k] for k in ("id_produto", "quantidade", "medida", "id_local", "id_modo")
            if args.get(k) is not None} | loja)
        cab = (f"*Produzir:* {_num(previsao.get('quantidade'))} {previsao.get('um_estoque') or ''} "
               f"de *{previsao.get('produto')}*").replace("  ", " ")
    else:
        raise ValueError(ferramenta)
    partes = [cab]
    if previsao.get("local_destino"):
        partes.append(f"Entra em: {previsao['local_destino']}")
    itens = _itens(previsao)
    if itens:
        partes.append("Sai do estoque:\n" + "\n".join(itens))
    texto = "\n".join(partes)
    return texto[:LIMITE_BOTAO]


def criar(cur, id_usuario: int, ferramenta: str, args: dict, texto: str) -> int:
    """A ação pendente. ⚠️ Uma por pessoa: a anterior que ainda esperava o botão expira."""
    cur.execute("""UPDATE assistente_acoes SET status = 'EXPIRADA', atualizada_em = now()
                    WHERE id_usuario = %s AND status = 'PENDENTE'""", (id_usuario,))
    cur.execute("""INSERT INTO assistente_acoes (id_usuario, ferramenta, argumentos, resumo, expira_em)
                   VALUES (%s, %s, %s, %s, now() + %s) RETURNING id""",
                (id_usuario, ferramenta, json.dumps(args), texto, VALIDADE))
    return cur.fetchone()["id"]


def botoes(id_acao: int) -> list[dict]:
    """Os dois botões. ⚠️ O título vai até 20 caracteres; o id volta no webhook."""
    return [{"id": f"ACAO:CONFIRMAR:{id_acao}", "titulo": "✅ Confirmar"},
            {"id": f"ACAO:CANCELAR:{id_acao}", "titulo": "❌ Cancelar"}]


# ---------------------------------------------------------------- o toque no botão (webhook)
def tocou_botao(cur, id_usuario: int, payload: str) -> str | None:
    """Trata "ACAO:CONFIRMAR:<id>" / "ACAO:CANCELAR:<id>". Devolve a frase para responder na hora,
    ou None quando o lançamento fica para depois do 200 (confirmou)."""
    partes = payload.split(":")
    if len(partes) != 3 or partes[0] != "ACAO" or not partes[2].isdigit():
        return "Não reconheci esse botão."
    acao, id_acao = partes[1], int(partes[2])
    # ⚠️ A ação tem de ser DESTA pessoa: o id do botão é só um número.
    cur.execute("""SELECT id, status, expira_em < now() AS vencida FROM assistente_acoes
                    WHERE id = %s AND id_usuario = %s FOR UPDATE""", (id_acao, id_usuario))
    a = cur.fetchone()
    if not a:
        return "Não encontrei esse lançamento."
    if a["status"] != "PENDENTE":
        return {"EXECUTADA": "Esse lançamento já foi feito.",
                "CONFIRMADA": "Já estou lançando — um instante.",
                "CANCELADA": "Esse lançamento foi cancelado.",
                "EXPIRADA": "Essa confirmação não vale mais. Peça de novo, por favor.",
                "ERRO": "Esse lançamento já falhou antes. Peça de novo, por favor."}.get(
                    a["status"], "Esse lançamento não está mais esperando confirmação.")
    if a["vencida"]:
        cur.execute("UPDATE assistente_acoes SET status = 'EXPIRADA', atualizada_em = now() WHERE id = %s",
                    (id_acao,))
        return f"A confirmação valia {int(VALIDADE.total_seconds() // 60)} minutos e venceu. Peça de novo, por favor."
    if acao == "CANCELAR":
        cur.execute("UPDATE assistente_acoes SET status = 'CANCELADA', atualizada_em = now() WHERE id = %s",
                    (id_acao,))
        return "Cancelado. Nada foi lançado."
    if acao == "CONFIRMAR":
        cur.execute("""UPDATE assistente_acoes SET status = 'CONFIRMADA', confirmada_em = now(),
                              atualizada_em = now() WHERE id = %s""", (id_acao,))
        return None
    return "Não reconheci esse botão."


# ---------------------------------------------------------------- o lançamento
def processar_confirmadas(limite: int = 10) -> int:
    """Lança o que foi confirmado. Nunca levanta. ⚠️ `SKIP LOCKED`: nunca a mesma duas vezes."""
    feitos = 0
    try:
        for _ in range(limite):
            with get_cursor() as cur:
                cur.execute("""SELECT a.id, a.id_usuario, a.ferramenta, a.argumentos, a.resumo,
                                      u.email, u.ativo, v.wa_id
                                 FROM assistente_acoes a
                                 JOIN usuarios u ON u.id = a.id_usuario
                                 LEFT JOIN usuario_whatsapp v ON v.id_usuario = a.id_usuario
                                WHERE a.status = 'CONFIRMADA'
                                ORDER BY a.confirmada_em LIMIT 1 FOR UPDATE OF a SKIP LOCKED""")
                a = cur.fetchone()
                if not a:
                    break
                a = dict(a)
                ok, texto, resultado = _lancar(a)
                cur.execute("""UPDATE assistente_acoes SET status = %s, executada_em = now(),
                                      resultado = %s, erro = %s, atualizada_em = now()
                                WHERE id = %s""",
                            ("EXECUTADA" if ok else "ERRO", json.dumps(resultado) if resultado else None,
                             None if ok else texto[:500], a["id"]))
                _avisar(cur, a, texto)
            feitos += 1
    except Exception:  # noqa: BLE001
        log.exception("assistente: falha ao lançar ações confirmadas")
    if feitos:
        from services import assistente
        assistente.processar_fila()
    return feitos


def _lancar(a: dict) -> tuple[bool, str, dict | None]:
    from seguranca import criar_access_token
    from services import assistente_conversa, mcp_ferramentas
    if not a["ativo"]:
        return False, "❌ Não lancei: o seu usuário está inativo.", None
    credencial, _ = criar_access_token(a["id_usuario"], a["email"], origem="whatsapp")
    app = assistente_conversa._APP
    if app is None:
        return False, "❌ Não lancei: o sistema ainda estava subindo. Peça de novo.", None
    try:
        bruto = asyncio.run(mcp_ferramentas.chamar(
            app, credencial, a["ferramenta"], dict(a["argumentos"]),
            cabecalhos_extra={"X-Origem-Assistente": "1"}))
    except mcp_ferramentas.ErroFerramenta as e:
        motivo = str(e)
        if motivo.startswith("403"):
            motivo = "você não tem permissão para lançar essa produção no sistema."
        return False, f"❌ Não lancei: {motivo}", None
    try:
        resultado = json.loads(bruto)
    except ValueError:
        resultado = {"bruto": bruto[:500]}
    frase = resultado.get("message") if isinstance(resultado, dict) else None
    primeira = a["resumo"].split("\n", 1)[0].replace("*Produzir da agenda:*", "").replace("*Produzir:*", "")
    return True, f"✅ Lançado:{primeira}" + (f"\n{frase}" if frase else ""), resultado


def _avisar(cur, a: dict, texto: str) -> None:
    """A resposta ao toque, e a mesma frase na conversa — o Claude precisa saber, na próxima
    pergunta, que aquilo já foi lançado (ou não)."""
    from services import assistente
    cur.execute("""INSERT INTO assistente_conversa (id_usuario, papel, texto)
                   VALUES (%s, 'assistente', %s)""", (a["id_usuario"], texto))
    if a.get("wa_id"):
        assistente.responder(cur, f"acao:{a['id']}:resultado", a["wa_id"], texto, a["id_usuario"])


def limpar(cur) -> None:
    cur.execute("""UPDATE assistente_acoes SET status = 'EXPIRADA', atualizada_em = now()
                    WHERE status = 'PENDENTE' AND expira_em < now()""")
    cur.execute("DELETE FROM assistente_acoes WHERE criada_em < now() - interval '30 days'")
