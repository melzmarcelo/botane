"""PDV Legal — credencial, autenticação e a busca das vendas.

O catálogo de endpoints da Tablet Cloud não é público, mas apareceu em
`GET /help` — a página de ajuda do ASP.NET, que só responde com o Bearer token.
O que se sabe dele está em `docs/pdv-legal-api.md`, conferido contra a conta
real do cliente.

⚠️ **A gravação da venda NÃO acontece aqui.** A sincronização busca, traduz e
entrega ao mesmo `/vendas/importar` que a planilha usa — com o mesmo de-para, o
mesmo congelamento do custo da ficha e a mesma baixa de estoque. Era o que o
mapeamento previa: *"quando a API abrir, muda a fonte e não o resto"*. Duas
gravações de venda seriam duas contas de CMV conforme a origem.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao, unidade_atual
from models.cmv import ImportarVendasRequest, VendaImportar
from routers import vendas as rota_vendas
from services import segredos
from services.pdv import cardapio, importador
from services.pdv.cliente import ClientePdv, ErroPdv

router = APIRouter(prefix="/pdv", tags=["PDV Legal"])

SERVICO = "PDV_LEGAL"


class ConfigPdv(BaseModel):
    # ⚠️ Os quatro em branco mantêm o que já estava: a tela mostra mascarado, e
    # exigir redigitar a senha para mudar o modo é o caminho mais curto para
    # alguém guardar a credencial num bloco de notas.
    # ⚠️ As filiais que a busca cobre — uma lista separada por vírgula, como a
    # API pede ("37622" ou "10,20,30"). Em branco, a sincronização descobre
    # sozinha em `filial/get`: uma casa com uma filial só não deveria precisar
    # digitar o código dela em lugar nenhum.
    filiais: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=200)
    # O `client_id` é o código do grupo econômico; o `client_secret`, o token do
    # grupo. Nomes deles, não nossos.
    client_id: str | None = Field(default=None, max_length=120)
    client_secret: str | None = Field(default=None, max_length=200)
    modo: str = "simulado"          # simulado | real
    ativa: bool = False
    # ⚠️ **A busca automática nasce DESLIGADA e assim continua até alguém
    # ligar.** Cada dia da janela é uma requisição ao PDV (é o único jeito sem
    # teto de 100 cupons), então uma agenda horária com janela de 30 dias são
    # 720 chamadas por dia para reler o mesmo mês. Ligar é decisão de quem
    # opera, não padrão que aparece sozinho.
    agenda_frequencia: Literal["MANUAL", "HORARIA", "DIARIA"] = "MANUAL"
    agenda_hora: int = Field(default=4, ge=0, le=23)
    # Nulo = janela automática (desde a última venda importada, com 2 dias de
    # folga). Preencher varre um período fixo a cada rodada — e cada dia a mais
    # é uma requisição a mais.
    agenda_janela_dias: int | None = Field(default=None, ge=1, le=60)


def _cliente(cur, id_unidade: int) -> ClientePdv:
    cur.execute(
        "SELECT credenciais, modo FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO),
    )
    linha = cur.fetchone()
    if not linha:
        return ClientePdv(modo="simulado")
    c = segredos.decifrar(linha["credenciais"])
    return ClientePdv(c.get("username"), c.get("password"), c.get("client_id"),
                      c.get("client_secret"), linha["modo"])


@router.get("/config")
def config(ctx: Contexto = Depends(requer_permissao("integracao.pdv", "admin.integracoes"))
           ) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT modo, ativa, credenciais, ultima_sincronizacao, ultimo_status,
                      ultima_mensagem, agenda_frequencia, agenda_hora, agenda_janela_dias,
                      agenda_rodou_em, agenda_ultimo_erro, agenda_id_usuario
                 FROM integracoes WHERE id_unidade = %s AND servico = %s""",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()

    cred = segredos.decifrar(linha["credenciais"]) if linha else {}
    return {
        "configurada": bool(cred.get("username") and cred.get("client_id")),
        "modo": linha["modo"] if linha else "simulado",
        "ativa": linha["ativa"] if linha else False,
        # ⚠️ Nada volta em claro — nem o usuário. A senha e o segredo do grupo
        # são credencial; o usuário e o código do grupo identificam a conta, e
        # mascarados ainda dão para reconhecer qual foi configurada.
        "username": segredos.mascarar(cred.get("username")),
        "password": segredos.mascarar(cred.get("password")),
        "client_id": segredos.mascarar(cred.get("client_id")),
        "client_secret": segredos.mascarar(cred.get("client_secret")),
        "filiais": cred.get("filiais"),
        "ultima_sincronizacao": linha["ultima_sincronizacao"] if linha else None,
        "ultimo_status": linha["ultimo_status"] if linha else None,
        "ultima_mensagem": linha["ultima_mensagem"] if linha else None,
        # A agenda: o que está configurado e o que aconteceu na última rodada.
        # ⚠️ `agenda_rodou_em` é quando o agendador RODOU, não quando trouxe
        # venda — uma casa fechada no domingo tem as duas coisas diferentes, e
        # mostrar a segunda faria parecer que a agenda parou.
        "agenda_frequencia": linha["agenda_frequencia"] if linha else "MANUAL",
        "agenda_hora": linha["agenda_hora"] if linha else 4,
        "agenda_janela_dias": linha["agenda_janela_dias"] if linha else None,
        "agenda_rodou_em": linha["agenda_rodou_em"] if linha else None,
        "agenda_ultimo_erro": linha["agenda_ultimo_erro"] if linha else None,
        # ⚠️ A agenda grava VENDA, e venda tem dono. Sem isto o agendador recusa
        # rodar e diz por quê — a tela precisa poder avisar antes.
        "agenda_assinada": bool(linha and linha["agenda_id_usuario"]),
        # O catálogo chegou em 26/08/2026 (ver `docs/pdv-legal-api.md`), então a
        # venda entra sozinha. O campo fica porque a TELA muda de cara com ele.
        "importador_disponivel": True,
    }


@router.put("/config")
def salvar_config(body: ConfigPdv,
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
        for campo in ("username", "password", "client_id", "client_secret"):
            valor = getattr(body, campo)
            if valor:
                cred[campo] = valor.strip()
        # Não é segredo: é o recorte da busca, e quem configura precisa vê-lo.
        if body.filiais is not None:
            cred["filiais"] = body.filiais.strip() or None

        # ⚠️ Modo real sem os quatro é promessa que a primeira chamada quebra —
        # e o erro apareceria como "não autorizado", que manda quem configurou
        # procurar a credencial errada.
        if body.modo == "real" and not all(cred.get(c) for c in
                                           ("username", "password", "client_id",
                                            "client_secret")):
            raise HTTPException(
                status_code=400,
                detail=("Para o modo real faltam credenciais. O PDV Legal precisa dos "
                        "quatro: usuário, senha, código do grupo econômico (client_id) e "
                        "token do grupo (client_secret)."),
            )

        # ⚠️ **Quem salva a agenda passa a assiná-la.** A busca automática grava
        # venda, e venda baixa estoque e entra no razão — toda escrita dessas
        # carrega um `id_usuario`, e o agendador não tem sessão. Inventar um
        # "usuário do sistema" criaria uma conta real que ninguém vigia; quem
        # ligou decidiu aquilo, e é quem responde por ela.
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
        # ⚠️ Salvar limpa o erro anterior: manter a mensagem velha faria a tela
        # acusar uma falha já tratada, e quem acabou de arrumar a credencial
        # veria o mesmo aviso de antes.
        cur.execute(
            "UPDATE integracoes SET agenda_ultimo_erro = NULL "
            " WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        # A auditoria registra a mudança sem registrar o segredo.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "configurar",
                            depois={"modo": body.modo, "ativa": body.ativa,
                                    "agenda": body.agenda_frequencia,
                                    "username": segredos.mascarar(cred.get("username"))},
                            id_unidade=id_unidade)
    return {"message": "Integração do PDV Legal salva"}


@router.post("/testar")
def testar(ctx: Contexto = Depends(requer_permissao("integracao.pdv", "admin.integracoes"))
           ) -> dict:
    """Pede um token e diz se veio. É a única chamada real que existe hoje.

    ⚠️ Registra o resultado em `integracoes`, inclusive a falha: quem configurou
    fecha a tela, e a próxima pessoa precisa ver que a última tentativa não
    passou — sem isso, "configurada" pareceria "funcionando".
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = _cliente(cur, id_unidade).testar()
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultimo_status,
                                        ultima_mensagem)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultimo_status = EXCLUDED.ultimo_status,
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, r["modo"], "OK" if r["ok"] else "ERRO", r["detalhe"]),
        )
    return r


@router.post("/sincronizar")
def sincronizar(
    dias: int | None = None,
    desde: date | None = None,
    ctx: Contexto = Depends(requer_permissao("integracao.pdv")),
) -> dict:
    """Busca as vendas do PDV Legal e as grava pelo caminho de sempre.

    ⚠️ **Dia a dia.** O `cupom/get` devolve no máximo 100 registros num intervalo
    de até 10 dias — *exceto* quando a data inicial é igual à final, e aí não há
    teto. Uma casa com 48 cupons por dia estoura os 100 em três dias de janela, e
    o corte seria silencioso: 100 é um número plausível, ninguém veria falta, e o
    CMV do período sairia com receita a menos.

    ⚠️ **A gravação é do importador de vendas**, não daqui: o mesmo de-para, o
    mesmo custo congelado da ficha e a mesma baixa de estoque da planilha.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            "SELECT credenciais, modo FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()
        cred = segredos.decifrar(linha["credenciais"]) if linha else {}
        cliente = _cliente(cur, id_unidade)

        # ⚠️ Sem filial configurada, descobre sozinho — uma casa com uma filial
        # só não deveria precisar digitar o código dela em lugar nenhum. Só
        # pergunta quando há mais de uma: aí a escolha é de quem configura, e
        # somar todas mudaria o CMV de cada loja.
        filiais = (cred.get("filiais") or "").strip()
        if not filiais:
            try:
                lista = cliente.get("/filial/get") or []
            except ErroPdv as e:
                raise HTTPException(status_code=502, detail=f"PDV Legal: {e.mensagem}")
            codigos = [str(f.get("codigo")) for f in lista if f.get("codigo")]
            if len(codigos) != 1:
                raise HTTPException(
                    status_code=400,
                    detail=(f"A conta tem {len(codigos)} filial(is). Diga quais entram na "
                            "busca no campo Filiais da configuração, separadas por vírgula."),
                )
            filiais = codigos[0]

        try:
            r = importador.sincronizar(cur, cliente, id_unidade, filiais, dias, desde)
        except ErroPdv as e:
            cur.execute(
                """INSERT INTO integracoes (id_unidade, servico, modo, ultimo_status,
                                            ultima_mensagem)
                   VALUES (%s, %s, %s, 'ERRO', %s)
                   ON CONFLICT (id_unidade, servico) DO UPDATE
                       SET ultimo_status = 'ERRO', ultima_mensagem = EXCLUDED.ultima_mensagem""",
                (id_unidade, SERVICO, cliente.modo, e.mensagem),
            )
            raise HTTPException(status_code=502, detail=f"PDV Legal: {e.mensagem}")

    vendas = r.pop("vendas")
    gravado: dict = {"importadas": 0, "repetidas": 0}
    if vendas:
        # ⚠️ Chamada direta à função da rota de vendas, com o MESMO contexto:
        # `Depends` só vale quando o FastAPI a roteia. É o que garante um
        # caminho de gravação só — o de-para, o custo da ficha e a baixa de
        # estoque moram lá, e uma segunda cópia divergiria na primeira mudança.
        gravado = rota_vendas.importar(
            ImportarVendasRequest(vendas=[VendaImportar(**v) for v in vendas]), ctx
        )

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultima_sincronizacao,
                                        ultimo_status, ultima_mensagem)
               VALUES (%s, %s, %s, now(), 'OK', %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultima_sincronizacao = now(), ultimo_status = 'OK',
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, cliente.modo,
             f"{gravado.get('importadas', 0)} venda(s) nova(s) ({r['janela']})"),
        )
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "sincronizar",
                            depois={**r, **{k: gravado.get(k) for k in
                                            ("importadas", "repetidas", "sem_vinculo")}},
                            id_unidade=id_unidade)

    return {
        **r, **gravado,
        "message": (f"{gravado.get('importadas', 0)} venda(s) nova(s) de {r['cupons']} "
                    f"cupom(ns) — {r['janela']}"),
    }


@router.post("/cardapio")
def importar_cardapio(
    criar_ausentes: bool = True,
    ctx: Contexto = Depends(requer_permissao("integracao.pdv")),
) -> dict:
    """Traz o cardápio do PDV e monta o de-para.

    ⚠️ **Sem isto o CMV teórico é zero.** A venda entra, a receita aparece, e a
    variância — que é o número que interessa — não tem com o que comparar.

    ⚠️ **Reconcilia as vendas que já entraram** logo em seguida: a ordem real é
    a venda chegar antes de o cardápio estar ligado, e sem isso os itens que
    entraram sem produto ficariam pendentes para sempre.

    ⚠️ **A filial é o que traz o PREÇO** (`tabelapreco/get/{filial}`), que mora
    em outra rota e não no cadastro do produto. Sem ela o cardápio entra sem
    preço nenhum — foi assim durante toda a primeira versão, com o número a uma
    chamada de distância. Preço é POR FILIAL: na dúvida, nenhum é melhor que o
    de outra loja.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cliente = _cliente(cur, id_unidade)
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()
        cred = segredos.decifrar(linha["credenciais"]) if linha else {}
        filial = (cred.get("filiais") or "").split(",")[0].strip()
        if not filial:
            try:
                lista = cliente.get("/filial/get") or []
            except ErroPdv:
                lista = []
            codigos = [str(f.get("codigo")) for f in lista if f.get("codigo")]
            filial = codigos[0] if len(codigos) == 1 else ""
        try:
            r = cardapio.importar(cur, cliente, ctx.id_usuario, filial, criar_ausentes)
        except ErroPdv as e:
            raise HTTPException(status_code=502, detail=f"PDV Legal: {e.mensagem}")
        depois = cardapio.reconciliar(cur, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "cardapio",
                            depois={**r, **depois}, id_unidade=id_unidade)

    return {**r, "reconciliados": depois["vinculados"],
            "com_custo": depois["com_custo"], "sem_custo": depois["sem_custo"],
            # ⚠️ `ean_de_outro` sai na frase porque é um achado, não um detalhe:
            # dois cadastros disputando o mesmo EAN são o mesmo produto, e quem
            # resolve isso é a tela de duplicados — que sabe mover o de-para, os
            # itens de venda e o custo junto.
            "message": (f"{r['itens']} item(ns) do cardápio — {r['vinculados']} vinculado(s), "
                        f"{r['criados']} criado(s) em rascunho, "
                        f"{depois['vinculados']} venda(s) reconciliada(s)"
                        + (f", {r['precos']} preço(s) de venda" if r.get("precos") else "")
                        + (f". {r['ean_de_outro']} item(ns) trazem EAN que já é de outro "
                           "cadastro — abra o produto e use Vincular"
                           if r.get("ean_de_outro") else ""))}


@router.post("/reconciliar")
def reconciliar(ctx: Contexto = Depends(requer_permissao("integracao.pdv"))) -> dict:
    """Passa o de-para de novo nos itens de venda sem produto.

    Existe separado do cardápio porque o de-para também se arruma **à mão**, na
    tela de Vendas: depois de ligar meia dúzia de itens ali, é isto que faz o
    CMV teórico do mês passado enxergar o conserto.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = cardapio.reconciliar(cur, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "reconciliar",
                            depois=r, id_unidade=id_unidade)
    return {**r, "message": f"{r['vinculados']} item(ns) de venda vinculado(s)"}
