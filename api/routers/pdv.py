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

from psycopg2.extras import Json

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao, unidade_atual
from models.cmv import ImportarVendasRequest, VendaImportar
from routers import vendas as rota_vendas
from services import segredos
from services.pdv import cardapio, envio, importador
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
    # ⚠️ Nasce DESLIGADO. Ligar é decisão de quem paga a conta e responde
    # pelo cardápio: a busca errada custa uma venda não importada, o envio
    # errado custa o cardápio do cliente no meio do expediente.
    #
    # 🔑 **`None` MANTÉM o que está guardado — e isso não é conveniência.**
    # Este PUT substitui a linha inteira, e com `False` de padrão qualquer
    # chamada que não mandasse o campo **desligava o envio em silêncio**: um
    # cliente antigo, uma tela que só salva a agenda, um script de restauro.
    # Aconteceu com o restaurador da agenda na suíte de navegador, e o sintoma
    # é o pior possível — a tela de Exportação some do menu e nada explica.
    # É a mesma regra que a credencial já segue aqui: em branco, mantém.
    enviar_ao_pdv: bool | None = None
    agenda_frequencia: Literal["MANUAL", "HORARIA", "DIARIA"] = "MANUAL"
    agenda_hora: int = Field(default=4, ge=0, le=23)
    # Nulo = janela automática (desde a última venda importada, com 2 dias de
    # folga). Preencher varre um período fixo a cada rodada — e cada dia a mais
    # é uma requisição a mais.
    agenda_janela_dias: int | None = Field(default=None, ge=1, le=60)


def _filial(cur, id_unidade: int) -> int | None:
    """A filial da tabela de preços — uma só.

    ⚠️ Preço é POR filial, e mandar (ou comparar) o daqui contra a loja errada
    seria pior que não fazer nada. Com mais de uma configurada, devolve nulo.
    """
    cur.execute(
        "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO))
    linha = cur.fetchone()
    filiais = (segredos.decifrar(linha["credenciais"]) if linha else {}).get("filiais")
    so = [f.strip() for f in str(filiais or "").split(",") if f.strip()]
    return int(so[0]) if len(so) == 1 else None


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
                      ultima_mensagem, enviar_ao_pdv,
                      agenda_frequencia, agenda_hora, agenda_janela_dias,
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
        "enviar_ao_pdv": bool(linha["enviar_ao_pdv"]) if linha else False,
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
                                        enviar_ao_pdv,
                                        agenda_frequencia, agenda_hora, agenda_janela_dias,
                                        agenda_id_usuario)
               -- Linha NOVA: nulo vira falso — a integração nasce sem envio,
               -- e ligar é decisão explícita.
               VALUES (%s, %s, %s, %s, %s, coalesce(%s::boolean, false),
                       %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                       credenciais = EXCLUDED.credenciais,
                       -- ⚠️ **`EXCLUDED` não serve aqui.** Ele carrega a linha
                       -- já montada para inserir, onde o nulo virou `false` —
                       -- e o `coalesce` sobre ele nunca veria o nulo. Quem
                       -- responde "veio ou não veio?" é o parâmetro CRU, e por
                       -- isso ele entra duas vezes.
                       enviar_ao_pdv = coalesce(%s::boolean,
                                                integracoes.enviar_ao_pdv),
                       agenda_frequencia = EXCLUDED.agenda_frequencia,
                       agenda_hora = EXCLUDED.agenda_hora,
                       agenda_janela_dias = EXCLUDED.agenda_janela_dias,
                       agenda_id_usuario = EXCLUDED.agenda_id_usuario,
                       atualizado_em = now()""",
            (id_unidade, SERVICO, body.ativa, body.modo, segredos.cifrar(cred),
             body.enviar_ao_pdv,
             body.agenda_frequencia, body.agenda_hora, body.agenda_janela_dias,
             ctx.id_usuario,
             body.enviar_ao_pdv),
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
                                    "enviar_ao_pdv": body.enviar_ao_pdv,
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
        # ⚠️ O MODO viaja na resposta, como na busca do Omie. Sem ele, quem está
        # em simulado importa vendas de demonstração e não tem como saber — os
        # números aparecem no CMV como se fossem da casa.
        "modo": cliente.modo,
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
            r = cardapio.importar(cur, cliente, ctx.id_usuario, filial, criar_ausentes,
                                  id_unidade)
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


# ---------------------------------------------------------------------------
# A mão inversa: enviar cadastros daqui para o cardápio do PDV
# ---------------------------------------------------------------------------

def _envio_ligado(cur, id_unidade: int) -> None:
    """O interruptor é a primeira porta; a conta certa é a segunda."""
    cur.execute(
        "SELECT enviar_ao_pdv FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO),
    )
    linha = cur.fetchone()
    if not linha or not linha["enviar_ao_pdv"]:
        raise HTTPException(
            status_code=409,
            detail=("O envio ao PDV está desligado. Ligue em Integrações ▸ PDV Legal, "
                    "em 'Enviar informações ao PDV'."),
        )


@router.get("/envio/fila")
def envio_fila(ctx: Contexto = Depends(requer_permissao("integracao.pdv",
                                                        "admin.integracoes"))) -> dict:
    """As três abas: pendentes, integrados e erros.

    ⚠️ **Pendentes é uma CONSULTA, não uma tabela.** Ver `services/pdv/envio.py`:
    uma fila mantida à mão precisaria ser alimentada em todo lugar que salva um
    cadastro, e o próximo lugar — que vai existir — nasceria sem ela.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        _envio_ligado(cur, id_unidade)
        # ⚠️ O cliente vai junto: a fila PERGUNTA ao PDV o que já existe lá.
        # Sem isso ela mandaria CRIAR para os grupos que já estão no cardápio.
        try:
            return envio.fila(cur, id_unidade, _cliente(cur, id_unidade),
                              _filial(cur, id_unidade))
        except ErroPdv as e:
            # ⚠️ Falhar a leitura NÃO pode virar "então crie tudo": a tela diz
            # que não deu para falar com o PDV, e o padrão seguro é não agir.
            raise HTTPException(
                status_code=502,
                detail=(f"Não deu para ler o cardápio do PDV para saber o que já existe "
                        f"lá: {e}. Sem essa leitura a lista mostraria como 'criar' o que "
                        f"já está no cardápio."))


class EnvioPedido(BaseModel):
    """O que enviar. Vazio = tudo o que está pendente."""

    itens: list[dict] | None = None


@router.post("/envio")
def envio_disparar(body: EnvioPedido,
                   ctx: Contexto = Depends(requer_permissao("integracao.pdv",
                                                            "admin.integracoes"))) -> dict:
    """Envia os pendentes, um a um, e grava CADA tentativa.

    ⚠️ **Um a um, e o erro de um não derruba o lote.** O que falhou vai para a
    aba de erros com a mensagem do PDV ao lado do corpo mandado — "erro 400"
    sozinho não diz o que ajustar; com o payload, quem olha vê que faltou o
    grupo ou que o nome já existe.

    ⚠️ **Categoria antes de setor.** O produto no cardápio aponta para os dois,
    e a ordem evita que a aba de erros encha de falha de dependência — que não é
    erro, é ordem.
    """
    # ---- preparo: uma transação curta, que só LÊ ----
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        _envio_ligado(cur, id_unidade)
        cliente = _cliente(cur, id_unidade)

        cur.execute("SELECT cnpj FROM empresa WHERE id = 1")
        empresa = cur.fetchone()
        # 🔑 De quem é a conta — antes de escrever qualquer coisa.
        envio.conferir_a_conta(cliente, (empresa or {}).get("cnpj"))

        panorama = envio.fila(cur, id_unidade, cliente, _filial(cur, id_unidade))
        pendentes = panorama["pendentes"]

        # 🔑 **Pendência sem o que fazer FECHA aqui.** Tirar do PDV uma
        # categoria que já está desativada lá pede uma ação que não existe: a
        # pendência ficaria aberta para sempre, e uma fila com linhas que
        # ninguém consegue resolver é uma fila que ninguém mais lê. Fecha sem
        # `id_envio` — o registro diz "resolvida, e nada precisou ser enviado".
        for i in panorama["integrados"]:
            cur.execute(
                """UPDATE pdv_pendencias SET resolvido_em = now()
                    WHERE tipo = %s AND id_registro = %s AND resolvido_em IS NULL""",
                (i["tipo"], i["id_registro"]),
            )

    if body.itens:
        querem = {(i.get("tipo"), i.get("id_registro")) for i in body.itens}
        pendentes = [p for p in pendentes if (p["tipo"], p["id_registro"]) in querem]

    # Categoria primeiro: o produto do cardápio aponta para o grupo.
    ordem = {envio.CATEGORIA: 0, envio.SETOR: 1}
    pendentes.sort(key=lambda p: (ordem.get(p["tipo"], 9), p["nome"]))

    # A filial da tabela de preços: sem ela o preço não sai, e o cadastro sai
    # igual. ⚠️ Uma só — preço é POR filial, e mandar o daqui para a loja errada
    # seria pior que não mandar.
    with get_cursor() as cur:
        filial = _filial(cur, id_unidade)

    # ---- o envio: UMA TRANSAÇÃO POR ITEM ----
    # 🔑 **O PDV não volta atrás, e o banco daqui volta.** Na primeira versão o
    # laço inteiro rodava dentro de um `with get_cursor()`: o envio de um setor
    # levantou no fim, a transação foi desfeita, e os 29 registros das
    # categorias já adotadas no PDV sumiram daqui. Ficamos com o cardápio
    # alterado do outro lado e nenhum registro deste — o pior dos dois mundos,
    # porque a fila não sabia mais o que tinha mandado.
    #
    # Cada item agora grava a sua própria linha, comitada, antes do próximo.
    # ⚠️ Sobra uma janela de UM item (se o processo morrer entre a chamada ao
    # PDV e o commit), e ela é aceitável porque se conserta sozinha: a fila
    # relê o cardápio e vê que aquele registro já está adotado.
    enviados, falhas = 0, 0
    for item in pendentes:
        try:
            resposta = envio.enviar_um(cliente, item, filial)
            # 🔑 **Nem toda rota do PDV responde um OBJETO.** `impressoras/update`
            # devolve a STRING "Registry updated successfully!", como o `delete`
            # já fazia — e o `.get("id")` num `str` levanta AttributeError. O
            # envio do setor dava **500 com corpo vazio** depois de o PDV ter
            # gravado: a alteração ia, a pendência ficava aberta e a tela só
            # sabia dizer que falhou. O cliente já tolerava a string; quem supunha
            # o dicionário era esta linha.
            corpo_resposta = resposta if isinstance(resposta, dict) else {}
            codigo = str(corpo_resposta.get("id") or item.get("codigo_pdv") or "") or None
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO pdv_envios (id_unidade, tipo, id_registro, acao, estado,
                                               impressao, enviado, resposta, codigo_pdv,
                                               id_usuario)
                       VALUES (%s, %s, %s, %s, 'OK', %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (id_unidade, item["tipo"], item["id_registro"], item["acao"],
                     item["impressao"], Json(item["corpo"]), Json(resposta), codigo,
                     ctx.id_usuario),
                )
                id_envio = cur.fetchone()["id"] if cur.description else None
                # ⚠️ A impressora não tem código externo: sem guardar o código
                # dela aqui, o próximo envio criaria outra com o mesmo nome.
                if item["tipo"] == envio.SETOR and codigo:
                    cur.execute("UPDATE setores SET codigo_pdv = %s WHERE id = %s",
                                (codigo, item["id_registro"]))
                # 🔑 **O produto também guarda o código, e não guardava.** O
                # primeiro cadastro real foi criado no PDV (código 10735980) e o
                # vínculo não voltou para cá: `produtos.codigo_pdv` continuou
                # nulo. O que segurou a fila foi o `codRefExterna` gravado do
                # outro lado — mas ele é a rede, não o vínculo: `codigo_pdv` é o
                # que a tela mostra, o que o `enviar_preco` usa e o que sobrevive
                # a alguém limpar o campo externo lá.
                if item["tipo"] == envio.PRODUTO and codigo:
                    cur.execute(
                        """UPDATE produtos SET codigo_pdv = %s
                            WHERE id = %s AND codigo_pdv IS NULL""",
                        (codigo, item["id_registro"]))
                # 🔑 **A pendência só fecha com o envio que deu CERTO.** No erro
                # ela fica aberta de propósito: é o que faz o registro voltar
                # para Pendentes depois de alguém corrigir o cadastro, sem
                # precisar mexer no cadastro de novo só para "reenfileirar".
                cur.execute(
                    """UPDATE pdv_pendencias
                          SET resolvido_em = now(), id_envio = %s
                        WHERE tipo = %s AND id_registro = %s AND resolvido_em IS NULL""",
                    (id_envio, item["tipo"], item["id_registro"]),
                )
            enviados += 1
        except ErroPdv as e:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO pdv_envios (id_unidade, tipo, id_registro, acao, estado,
                                               impressao, enviado, erro, id_usuario)
                       VALUES (%s, %s, %s, %s, 'ERRO', %s, %s, %s, %s)""",
                    (id_unidade, item["tipo"], item["id_registro"], item["acao"],
                     item["impressao"], Json(item["corpo"]), str(e), ctx.id_usuario),
                )
            falhas += 1

    with get_cursor() as cur:
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "enviar",
                            depois={"enviados": enviados, "falhas": falhas,
                                    "pedidos": len(pendentes)},
                            id_unidade=id_unidade)

    if not pendentes:
        return {"enviados": 0, "falhas": 0, "message": "Nada pendente para enviar."}
    return {"enviados": enviados, "falhas": falhas,
            "message": (f"{enviados} enviado(s)"
                        + (f", {falhas} com erro" if falhas else ""))}
