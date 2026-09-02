"""A busca das vendas no PDV Legal rodando sozinha.

Até aqui alguém tinha de abrir Integrações e clicar em "Buscar vendas". Venda de
sábado que ninguém importa é receita que falta no CMV do fim de semana — e a
variância sai boa demais, porque o CMV teórico não conta o que foi vendido.

Três ritmos por loja, os mesmos do Omie: ``MANUAL`` (o padrão), ``HORARIA`` e
``DIARIA`` numa hora escolhida. A regra de "chegou a hora?" mora em
``services/agenda_integracao.py`` e é a mesma dos dois.

⚠️ **A busca do PDV é cara em REQUISIÇÕES, não em cota.** Cada dia da janela é
uma chamada (`dataInicial == dataFinal` é o único jeito sem teto de 100 cupons),
então uma janela de 30 dias são 30 idas ao servidor. Numa agenda HORÁRIA isso
seriam 720 chamadas por dia para reler o mesmo mês. Por isso a janela automática
é curta: sem `agenda_janela_dias`, o importador vai desde a última venda
importada com 2 dias de folga.

⚠️ **O que a agenda faz é GRAVAR VENDA** — não é só puxar dado para uma tabela
de integração, como a do Omie. Venda baixa estoque, entra no razão e vai para a
auditoria, e toda escrita dessas carrega um `id_usuario`. Quem ligou a agenda é
quem assina: ver `agenda_id_usuario` (migração 034) e `_contexto_de`.
"""

import asyncio
import traceback
from datetime import datetime

from database import get_cursor
from models.cmv import ImportarVendasRequest, VendaImportar
from seguranca import carregar_contexto
from services import agenda_integracao as regra
from services import segredos
from services.pdv import cardapio
from services.pdv import importador
from services.pdv.cliente import ClientePdv, ErroPdv

SERVICO = "PDV_LEGAL"

INTERVALO_DE_CHECAGEM = regra.INTERVALO_DE_CHECAGEM

# ⚠️ Chave do advisory lock. Número fixo, único no sistema e **diferente do
# Omie**: dois locks com o mesmo número se bloqueariam sem ter nada a ver um com
# o outro, e a busca de vendas ficaria esperando a de notas.
LOCK_AGENDA_PDV = 8_120_332


def _contexto_de(linha: dict):
    """A pessoa que ligou a agenda, com a loja da integração já escolhida.

    ⚠️ **Sem ela, não roda.** Gravar venda sem dono deixaria mil linhas de
    auditoria sem ninguém a quem perguntar, e um "usuário do sistema" inventado
    precisaria existir em `usuarios`, com senha e permissões — uma conta real
    que ninguém vigia. Quem ligou a agenda decidiu aquilo; é ela que assina.

    ⚠️ `unidade_pedida` vai preenchida porque a gravação chama
    `unidade_atual(cur, ctx)`: sem isso a venda de uma loja poderia cair na
    primeira loja do usuário, que pode ser outra.
    """
    id_usuario = linha.get("agenda_id_usuario")
    if not id_usuario:
        return None
    ctx = carregar_contexto(id_usuario)
    ctx.unidade_pedida = linha["id_unidade"]
    return ctx


def _filiais(cur, cliente: ClientePdv, cred: dict) -> str:
    """As filiais que a busca cobre — as configuradas, ou a única da conta.

    ⚠️ Com mais de uma filial e nenhuma configurada, o agendador **para e diz**:
    somar todas mudaria o CMV de cada loja, e escolher por conta própria seria
    escolher errado em silêncio.
    """
    escolhidas = (cred.get("filiais") or "").strip()
    if escolhidas:
        return escolhidas
    lista = cliente.get("/filial/get") or []
    codigos = [str(f.get("codigo")) for f in lista if f.get("codigo")]
    if len(codigos) != 1:
        raise ErroPdv(
            f"A conta tem {len(codigos)} filial(is). Diga quais entram na busca no campo "
            "Filiais da configuração — somar todas mudaria o CMV de cada loja."
        )
    return codigos[0]


def rodar_uma(cur, linha: dict) -> dict:
    """Busca e grava as vendas de uma loja. Marca o relógio ACONTEÇA O QUE ACONTECER.

    ⚠️ O relógio avança mesmo com erro. Sem isso, uma credencial vencida faria o
    agendador tentar de novo no minuto seguinte, para sempre — e serviço de
    autenticação conta tentativa falha. O erro fica em `agenda_ultimo_erro`, à
    vista na tela de Integrações.

    ⚠️ **A gravação é do importador de vendas**, chamado com o mesmo contexto: o
    mesmo de-para, o mesmo custo congelado da ficha e a mesma baixa de estoque do
    botão. Uma segunda cópia daria duas contas de CMV conforme a origem.
    """
    from routers import vendas as rota_vendas

    resultado: dict = {}
    erro: str | None = None
    try:
        ctx = _contexto_de(linha)
        if ctx is None:
            raise ErroPdv(
                "A agenda não sabe quem a ligou — a venda entraria sem dono. "
                "Abra Integrações e salve o agendamento de novo."
            )
        cred = segredos.decifrar(linha["credenciais"]) if linha["credenciais"] else {}
        cliente = ClientePdv(cred.get("username"), cred.get("password"),
                             cred.get("client_id"), cred.get("client_secret"), linha["modo"])

        filiais = _filiais(cur, cliente, cred)

        # 🔑 **O cardápio entra UMA VEZ POR DIA, não a cada disparo.** A agenda
        # pode ser HORÁRIA, e ler os 630 itens 24 vezes por dia para achar um
        # prato novo é caro sem ser mais útil: prato novo não nasce de hora em
        # hora. O botão "Buscar no PDV" sincroniza sempre — lá é alguém pedindo.
        # ⚠️ **Só criar e desativar**, nunca alinhar: rodar o alinhamento
        # sozinho desfaria calada a correção de quem arrumou a categoria de um
        # prato à mão, que é exatamente o que "ser manual" protegia.
        # ⚠️ **Falhar aqui não impede a busca de vendas**, e a ordem é essa de
        # propósito: venda não importada é receita faltando no CMV; cadastro não
        # sincronizado é um item que fica na fila mais um dia.
        if not cardapio.cadastros_de_hoje(cur, linha["id_unidade"]):
            try:
                resultado["cadastros"] = cardapio.sincronizar_cadastros(
                    cur, cliente, ctx.id_usuario, filiais.split(",")[0].strip(),
                    linha["id_unidade"])
            except ErroPdv as e:
                resultado["cadastros"] = {"erro": e.mensagem}

        r = importador.sincronizar(cur, cliente, linha["id_unidade"], filiais,
                                   dias=linha["agenda_janela_dias"], desde=None)
        vendas = r.pop("vendas")
        gravado = {"importadas": 0, "repetidas": 0}
        if vendas:
            gravado = rota_vendas.importar(
                ImportarVendasRequest(vendas=[VendaImportar(**v) for v in vendas]), ctx
            )
        resultado = {**resultado, **r, **gravado}

        cur.execute(
            """UPDATE integracoes
                  SET ultima_sincronizacao = now(), ultimo_status = 'OK', ultima_mensagem = %s
                WHERE id = %s""",
            (f"{gravado.get('importadas', 0)} venda(s) nova(s) ({r['janela']}) — agendada",
             linha["id"]),
        )
    except ErroPdv as e:
        erro = e.mensagem
    except Exception as e:  # noqa: BLE001 — o agendador não pode morrer por uma loja
        erro = f"{type(e).__name__}: {e}"

    if erro:
        cur.execute(
            "UPDATE integracoes SET ultimo_status = 'ERRO', ultima_mensagem = %s WHERE id = %s",
            (erro, linha["id"]),
        )
    regra.marcar(cur, linha["id"], erro)
    return {"id_unidade": linha["id_unidade"], "erro": erro, **resultado}


def rodar_pendentes() -> list[dict]:
    """Uma passada do agendador. Devolve o que rodou — vazio é o caso comum."""
    feitos: list[dict] = []
    with get_cursor() as cur:
        if not regra.peguei_o_lock(cur, LOCK_AGENDA_PDV):
            return feitos

        agora = datetime.now().astimezone()
        for linha in regra.pendentes(cur, SERVICO, agora):
            feitos.append(rodar_uma(cur, linha))
    return feitos


async def laco(parar: asyncio.Event) -> None:
    """O laço que acorda de minuto em minuto. Vive no `lifespan` da aplicação.

    ⚠️ **Roda em thread separada** (`asyncio.to_thread`): a busca é síncrona e
    faz uma requisição por dia da janela, o que leva dezenas de segundos. No laço
    de eventos, travaria a API inteira enquanto isso.

    ⚠️ **Nada aqui pode levantar exceção para cima.** Um agendador que morre no
    primeiro erro é pior que não ter agendador: some sem avisar, e meses depois
    alguém descobre que as vendas pararam de entrar.
    """
    while not parar.is_set():
        try:
            await asyncio.wait_for(parar.wait(), timeout=INTERVALO_DE_CHECAGEM)
            return  # o evento foi disparado: a aplicação está parando
        except asyncio.TimeoutError:
            pass

        try:
            for f in await asyncio.to_thread(rodar_pendentes):
                if f.get("erro"):
                    print(f"[botane] agenda PDV (loja {f['id_unidade']}): {f['erro']}")
                else:
                    print(f"[botane] agenda PDV (loja {f['id_unidade']}): "
                          f"{f.get('importadas', 0)} venda(s) nova(s)")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
