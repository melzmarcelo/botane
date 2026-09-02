"""Integração com o Omie: credencial, sincronização e catálogo.

O ciclo da nota (conferir, vincular, lançar, estornar) mora em `notas.py`, porque
é o mesmo para as notas que vêm do XML e para as digitadas na mão.

Enquanto não há credencial, tudo roda em **modo simulado** sobre respostas
gravadas em arquivo — o que permite construir, testar e demonstrar o importador
inteiro. Ao configurar a chave, o mesmo código passa a falar com a conta real.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Literal

from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import segredos
from services.omie import importador
from services.omie.cliente import ClienteOmie, testar

router = APIRouter(prefix="/omie", tags=["Omie"])

SERVICO = "OMIE"


class ConfigOmie(BaseModel):
    app_key: str | None = Field(default=None, max_length=120)
    app_secret: str | None = Field(default=None, max_length=200)
    modo: str = "simulado"          # simulado | real
    ativa: bool = False
    # ⚠️ No Omie, cliente e fornecedor moram na MESMA lista, separados por
    # etiqueta. Sem esta, importar o cadastro trazia os clientes da casa como
    # fornecedores — numa conta real, 888 pessoas físicas viraram fornecedor.
    # Vazio = traz todo mundo (para conta que não usa etiqueta).
    tag_fornecedor: str | None = Field(default="Fornecedor", max_length=60)

    # ⚠️ **A busca automática nasce DESLIGADA e assim continua até alguém
    # ligar.** Cada busca consome cota da conta do cliente, e o Omie bloqueia
    # quem consome demais — o bloqueio pega a integração inteira. Ligar é
    # decisão de quem paga a conta, não padrão que aparece sozinho.
    agenda_frequencia: Literal["MANUAL", "HORARIA", "DIARIA"] = "MANUAL"
    agenda_hora: int = Field(default=3, ge=0, le=23)
    # Nulo = janela automática (desde a última sincronização, com 7 dias de
    # folga). Preencher só faz sentido para quem quer varrer um mês a cada
    # rodada — e aí custa mais cota.
    agenda_janela_dias: int | None = Field(default=None, ge=1, le=365)


def _cliente(cur, id_unidade: int) -> ClienteOmie:
    cur.execute(
        "SELECT credenciais, modo, ativa FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO),
    )
    linha = cur.fetchone()
    if not linha:
        return ClienteOmie(modo="simulado")
    cred = segredos.decifrar(linha["credenciais"])
    return ClienteOmie(cred.get("app_key"), cred.get("app_secret"), linha["modo"])


# ---------------------------------------------------------------- configuração


@router.get("/config")
def config(ctx: Contexto = Depends(requer_permissao("integracao.omie", "admin.integracoes"))):
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT modo, ativa, credenciais, ultima_sincronizacao, ultimo_status,
                      ultima_mensagem, agenda_frequencia, agenda_hora,
                      agenda_janela_dias, agenda_rodou_em, agenda_ultimo_erro
                 FROM integracoes WHERE id_unidade = %s AND servico = %s""",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()
        cur.execute(
            """SELECT chamada, status, registros, mensagem, modo, iniciado_em
                 FROM sync_log WHERE servico LIKE %s ORDER BY iniciado_em DESC LIMIT 10""",
            ("%",),
        )
        historico = [dict(r) for r in cur.fetchall()]

    cred = segredos.decifrar(linha["credenciais"]) if linha else {}
    return {
        "configurada": bool(cred.get("app_key")),
        "modo": linha["modo"] if linha else "simulado",
        "ativa": linha["ativa"] if linha else False,
        # A chave nunca sai daqui em claro — só o suficiente para reconhecê-la.
        "app_key": segredos.mascarar(cred.get("app_key")),
        "app_secret": segredos.mascarar(cred.get("app_secret")),
        # Não é segredo: é a regra que separa fornecedor de cliente, e quem
        # configura precisa vê-la para saber por que faltou alguém.
        "tag_fornecedor": cred.get("tag_fornecedor", "Fornecedor"),
        "ultima_sincronizacao": linha["ultima_sincronizacao"] if linha else None,
        "ultimo_status": linha["ultimo_status"] if linha else None,
        "ultima_mensagem": linha["ultima_mensagem"] if linha else None,
        # A agenda: o que está configurado e o que aconteceu na última rodada.
        # ⚠️ `agenda_rodou_em` é quando o agendador RODOU, não quando trouxe
        # nota — a tela precisa dos dois para distinguir "não roda" de "roda e
        # não acha nada".
        "agenda_frequencia": linha["agenda_frequencia"] if linha else "MANUAL",
        "agenda_hora": linha["agenda_hora"] if linha else 3,
        "agenda_janela_dias": linha["agenda_janela_dias"] if linha else None,
        "agenda_rodou_em": linha["agenda_rodou_em"] if linha else None,
        "agenda_ultimo_erro": linha["agenda_ultimo_erro"] if linha else None,
        "historico": historico,
    }


@router.put("/config")
def salvar_config(body: ConfigOmie,
                  ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    if body.modo not in ("simulado", "real"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'simulado' ou 'real'.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        atual = cur.fetchone()
        cred = segredos.decifrar(atual["credenciais"]) if atual else {}
        # Campo em branco mantém o que já estava: a tela mostra mascarado.
        if body.app_key:
            cred["app_key"] = body.app_key.strip()
        if body.app_secret:
            cred["app_secret"] = body.app_secret.strip()
        cred["tag_fornecedor"] = (body.tag_fornecedor or "").strip() or None
        # A tela mostra a chave mascarada; trocar para "real" não pode exigir
        # redigitar o que já está guardado.
        if body.modo == "real" and not (cred.get("app_key") and cred.get("app_secret")):
            raise HTTPException(
                status_code=400,
                detail="Para o modo real é preciso informar app_key e app_secret.",
            )

        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais,
                                        agenda_frequencia, agenda_hora, agenda_janela_dias,
                                        agenda_id_usuario)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                       credenciais = EXCLUDED.credenciais,
                       agenda_frequencia = EXCLUDED.agenda_frequencia,
                       agenda_hora = EXCLUDED.agenda_hora,
                       agenda_janela_dias = EXCLUDED.agenda_janela_dias,
                       agenda_id_usuario = EXCLUDED.agenda_id_usuario,
                       atualizado_em = now()""",
            (id_unidade, SERVICO, body.ativa, body.modo, segredos.cifrar(cred),
             body.agenda_frequencia, body.agenda_hora, body.agenda_janela_dias,
             ctx.id_usuario),
        )
        # ⚠️ Ligar o agendamento limpa o erro anterior: manter a mensagem velha
        # faria a tela acusar uma falha que já foi tratada — e quem acabou de
        # arrumar a credencial veria o mesmo aviso de antes.
        cur.execute(
            "UPDATE integracoes SET agenda_ultimo_erro = NULL "
            " WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        # A auditoria registra a mudança sem registrar o segredo.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "configurar",
                            depois={"modo": body.modo, "ativa": body.ativa,
                                    "agenda": body.agenda_frequencia,
                                    "app_key": segredos.mascarar(cred.get("app_key"))},
                            id_unidade=id_unidade)
    return {"message": "Integração salva"}


@router.post("/testar")
def testar_conexao(ctx: Contexto = Depends(requer_permissao("integracao.omie",
                                                            "admin.integracoes"))) -> dict:
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
    return testar(cliente)


# ---------------------------------------------------------------- sincronização


@router.post("/sincronizar")
def sincronizar(dias: int | None = Query(default=None, ge=1, le=365),
                desde: date | None = None,
                ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Puxa as notas de entrada do Omie.

    Sem parâmetro nenhum, a janela **se adapta**: vai desde a última
    sincronização, com folga. `desde` faz a carga inicial do histórico; `dias`
    fixa uma janela.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cliente = _cliente(cur, id_unidade)
        r = importador.sincronizar(cur, id_unidade, cliente, dias, desde)
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultima_sincronizacao,
                                        ultimo_status, ultima_mensagem)
               VALUES (%s, %s, %s, now(), 'OK', %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultima_sincronizacao = now(), ultimo_status = 'OK',
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, cliente.modo,
             f"{r['novas']} nova(s), {r['repetidas']} já existiam ({r['janela']})"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "sincronizar", depois=r,
                            id_unidade=id_unidade)
    return r | {"message": (f"{r['novas']} nota(s) nova(s) importada(s) — "
                           f"{r['janela']}, {r['repetidas']} já existiam")}


@router.post("/importar-catalogo")
def importar_catalogo(ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Traz os produtos do Omie como rascunho — a carga inicial do cadastro."""
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
        r = importador.importar_catalogo(cur, cliente, ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "importar_catalogo",
                            depois=r)
    faltou = r.get("faltou_varrer") or {}
    return r | {"message": f"{r['criados']} produto(s) criado(s) em rascunho"
                + (f" — {r['sem_unidade']} sem unidade conhecida, para conferir"
                   if r.get("sem_unidade") else "")
                + (f". ⚠️ A varredura parou no limite: {faltou['trazidos']} de "
                   f"{faltou['total_no_omie']} — rode de novo para trazer o resto"
                   if faltou else "")}


@router.post("/importar-fornecedores")
def importar_fornecedores(
    apenas_completar: bool = False,
    ctx: Contexto = Depends(requer_permissao("integracao.omie")),
) -> dict:
    """Traz (ou completa) o cadastro de fornecedores do Omie.

    ⚠️ No Omie, cliente e fornecedor moram na mesma lista, separados por
    ETIQUETA — e é a etiqueta configurada que decide quem desce. Com
    `apenas_completar`, nada novo é criado: só se preenche o que está em branco
    nos fornecedores que já existem aqui.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()
        cred = segredos.decifrar(linha["credenciais"]) if linha else {}
        r = importador.importar_fornecedores(
            cur, _cliente(cur, id_unidade), ctx.id_usuario, apenas_completar,
            tag=cred.get("tag_fornecedor", "Fornecedor"))
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO,
                            "importar_fornecedores", depois=r)
    return r | {"message": (f"{r['criados']} fornecedor(es) criado(s), "
                            f"{r['completados']} completado(s)"
                            + (f" — só os marcados como “{r['tag']}” no Omie"
                               if r.get("tag") else " — sem filtro de etiqueta"))}


@router.get("/conferencia-notas")
def conferencia_notas(
    inicio: date | None = None,
    fim: date | None = None,
    ctx: Contexto = Depends(requer_permissao("integracao.omie")),
) -> dict:
    """Quais notas o Omie tem no período e não existem aqui.

    "0 novas" é ambíguo — pode não haver nada novo, ou a janela pode ter passado
    por cima de uma nota lançada com atraso. Isto responde a pergunta certa:
    **quais** faltam.
    """
    hoje = date.today()
    fim = fim or hoje
    inicio = inicio or (fim - timedelta(days=30))
    if inicio > fim:
        raise HTTPException(status_code=400, detail="O início não pode ser depois do fim.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        return importador.conferir_notas(cur, id_unidade, _cliente(cur, id_unidade), inicio, fim)


@router.get("/custos-iniciais/previa")
def previa_custos_iniciais(
    ctx: Contexto = Depends(requer_permissao("integracao.omie")),
) -> dict:
    """Quantos produtos receberiam custo do Omie, e quais — antes de gravar.

    ⚠️ Existe pelo mesmo motivo da prévia do inventário e da exportação: 2.323
    produtos é grande demais para se descobrir o efeito depois. A varredura é a
    mesma; o que muda é não escrever nada.
    """
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
        return importador.custos_iniciais(cur, cliente, ctx.id_usuario, aplicar=False)


@router.post("/custos-iniciais")
def aplicar_custos_iniciais(
    ctx: Contexto = Depends(requer_permissao("integracao.omie")),
) -> dict:
    """Grava o custo médio do Omie nos produtos que aqui não têm custo nenhum.

    🔑 **É REFERÊNCIA, não movimento**: nada entra no razão e nenhum saldo muda.
    O CMV real continua saindo do que a casa comprou e contou; o que isto
    destrava é a ficha, o CMV teórico e a margem dos produtos que hoje entram na
    conta valendo zero.

    ⚠️ **Só quem NÃO tem custo.** O médio do razão e o último preço do
    fornecedor ganham sempre — o primeiro é o que a casa pagou com o frete dela
    dentro, o segundo é o que ela negociou.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cliente = _cliente(cur, id_unidade)
        r = importador.custos_iniciais(cur, cliente, ctx.id_usuario, aplicar=True)
        auditoria.registrar(
            cur, ctx.id_usuario, "integracao", SERVICO, "custos_iniciais",
            depois={k: v for k, v in r.items() if k != "linhas"}, id_unidade=id_unidade)
    return r


@router.get("/conferencia")
def conferencia(so_divergentes: bool = True,
                ctx: Contexto = Depends(requer_permissao("integracao.omie"))) -> dict:
    """Saldo e custo médio daqui × posição de estoque do Omie.

    Divergência quer dizer que alguma entrada não foi conciliada de um dos lados
    — a conferência cruzada mais barata que existe, porque o Omie já mantém o
    número por outros motivos.

    ⚠️ **A resposta virou objeto, não lista.** Lista sozinha não conseguia dizer
    quantos foram conferidos, quantos não têm cadastro aqui, nem que a varredura
    parou no teto de páginas — e "lista vazia" se lê como "está tudo certo"
    quando pode ser "não achei nenhum produto".
    """
    with get_cursor() as cur:
        cliente = _cliente(cur, unidade_atual(cur, ctx))
        return importador.conferir_estoque(cur, cliente, so_divergentes)
