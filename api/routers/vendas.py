"""Vendas — a outra metade do CMV.

Enquanto a API do PDV Legal não abre, a venda entra por planilha ou na mão. O
destino é o mesmo que a integração vai preencher, e o **custo da ficha é
congelado na importação**: o CMV teórico de março não muda quando alguém corrige
uma receita em abril.
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg2 import errors as erros_pg

import auditoria
import relogio
from database import get_cursor
from paginacao import pagina
from models.cmv import (AcrescentarItensRequest, ImportarVendasRequest, PreviaCupomRequest,
                        VendaAlterar, VendaResponse)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import cmv as motor
from services import consumo_pessoa as consumo
from services import estoque as motor_estoque
from services import painel_vendas
from services import precos
from services import producao_agenda as agenda

router = APIRouter(prefix="/vendas", tags=["vendas"])

_ver = requer_permissao("cmv.painel", "cmv.relatorios")
_editar = requer_permissao("cmv.fechamento", "cmv.painel")


@router.get("", response_model=list[VendaResponse])
def listar(
    inicio: date | None = None,
    fim: date | None = None,
    # A busca vai ao SERVIDOR: com 1.375 vendas num mês, filtrar a página
    # carregada acharia o documento só quando ele já estivesse na tela.
    busca: str | None = None,
    origem: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    """As vendas da loja atual, da mais recente para a mais antiga.

    ⚠️ **Filtra por `id_unidade`, e isso não estava aqui.** Toda tabela de
    movimento carrega a loja desde o começo, mas a listagem somava as de todas —
    numa casa com duas lojas, a tela de uma mostraria as vendas da outra e o
    total não bateria com o CMV daquela loja.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        alvo = f"%{busca.strip()}%" if busca and busca.strip() else None
        return pagina(
            cur,
            """SELECT v.id, v.data, v.hora, v.origem, v.canal, v.documento, v.valor_total,
                      v.cancelada, v.consumo_interno, v.motivo,
                      count(vi.id) AS itens,
                      count(*) FILTER (WHERE vi.custo_ficha_unitario IS NULL) AS sem_custo
                 FROM vendas v
                 LEFT JOIN venda_itens vi ON vi.id_venda = v.id
                WHERE v.id_unidade = %s
                  AND (%s::date IS NULL OR v.data >= %s)
                  AND (%s::date IS NULL OR v.data <= %s)
                  AND (%s::text IS NULL OR v.origem = %s)
                  AND (%s::text IS NULL OR v.documento ILIKE %s)
                GROUP BY v.id
                -- Com a hora gravada, a ordem do DIA passa a ser a do relógio:
                -- quem procura "a venda das 14h" não a acha pela ordem de
                -- importação. NULLS LAST porque a planilha não tem hora.
                ORDER BY v.data DESC, v.hora DESC NULLS LAST, v.id DESC""",
            (id_unidade, inicio, inicio, fim, fim, origem, origem, alvo, alvo),
            limite=limite, offset=offset, resposta=resposta,
        )


def _politica_da_pessoa(cur, id_pessoa: int | None) -> dict | None:
    """A política de cupom da pessoa — ou nada, que é o caso comum.

    ⚠️ Política que não muda nada devolve nada: base VENDA sem desconto é
    exatamente o comportamento padrão, e devolvê-la faria a resposta anunciar um
    ajuste que não houve.
    """
    if not id_pessoa:
        return None
    cur.execute(
        """SELECT id, nome, cupom_base, cupom_desconto_pct FROM fornecedores
            WHERE id = %s AND ativo""",
        (id_pessoa,),
    )
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada ou inativa.")
    if p["cupom_base"] == "VENDA" and not float(p["cupom_desconto_pct"] or 0):
        return None
    return dict(p)


def _aplicar_politica(cur, id_unidade: int, venda, politica: dict,
                      cache: dict) -> list[int]:
    """Reescreve o valor unitário dos itens conforme a política — antes de gravar.

    ⚠️ **Pelo CUSTO usa `custo_teorico_do_produto`**, a mesma cascata da ficha e
    do CMV. Uma segunda conta aqui faria a venda ao funcionário discordar do
    custo que o próprio sistema atribui ao prato.

    ⚠️ **Item sem produto ou sem custo conhecido fica como está.** Zerá-lo faria
    a venda sair de graça, e o CMV contaria receita zero contra custo real — o
    oposto do que a política quer dizer.

    🔑 **E devolve QUAIS ficaram**, para que a tela e a resposta possam dizê-lo.
    Uma linha que sai pelo preço cheio dentro de um cupom "pelo custo" é uma
    diferença silenciosa: quem lança presume que valeu para tudo, e só descobre
    na hora de cobrar.
    """
    sem_custo: list[int] = []
    desconto = Decimal(str(politica["cupom_desconto_pct"] or 0)) / Decimal(100)
    for n, item in enumerate(venda.itens):
        # 🔑 **O preço de tabela guardado ANTES de qualquer reescrita**
        # (04/09/2026). Sem ele, `cheio - cobrado` — a única conta honesta do
        # desconto — perde um dos lados, e o cupom não teria como mostrar o que
        # a pessoa deixou de pagar.
        # ⚠️ Fica NULO quando a linha não muda (item sem produto, ou sem custo
        # conhecido na base CUSTO): repetir o mesmo valor nos dois campos faria
        # o relatório anunciar um desconto de zero onde não houve política
        # alguma, e "sem desconto" e "não se aplica" são coisas diferentes.
        antes = item.valor_unitario
        if politica["cupom_base"] == "CUSTO":
            if not item.id_produto:
                sem_custo.append(n)
                continue
            if item.id_produto not in cache:
                cache[item.id_produto] = motor.custo_teorico_do_produto(
                    cur, item.id_produto, id_unidade=id_unidade)
            custo, _origem = cache[item.id_produto]
            if custo is None:
                # ⚠️ O desconto TAMBÉM não se aplica aqui, e é deliberado: 10%
                # sobre o preço de venda não é 10% sobre o custo, e cobrar quase
                # o preço cheio de quem foi configurado para pagar o custo seria
                # pior do que dizer que não deu para calcular.
                sem_custo.append(n)
                continue
            item.valor_unitario = float(custo)
        if desconto:
            item.valor_unitario = float(
                (Decimal(str(item.valor_unitario)) * (Decimal(1) - desconto))
                .quantize(Decimal("0.01")))
        if item.valor_unitario != antes:
            item.valor_unitario_cheio = antes
    return sem_custo


def _frase_da_politica(politica: dict) -> str:
    """O que a política fez, em português — a MESMA frase na prévia e na resposta.

    ⚠️ Escrita duas vezes, ela divergiria: a tela diria uma coisa antes de
    gravar e outra depois, sobre o mesmo cupom.
    """
    return (
        f"{politica['nome']}: "
        + ("lançado pelo CUSTO" if politica["cupom_base"] == "CUSTO"
           else "pelo preço de venda")
        + (f", com {float(politica['cupom_desconto_pct']):g}% de desconto"
           if float(politica["cupom_desconto_pct"] or 0) else ""))


@router.post("/previa")
def previa(body: PreviaCupomRequest, ctx: Contexto = Depends(_editar)) -> dict:
    """Quanto este cupom vai sair — antes de gravar.

    🔑 **A percepção visual pedida pelo dono** (04/09/2026): ao escolher a
    pessoa e os itens, a tela mostra o que cada linha vai custar de verdade, em
    vez de só avisar que "o servidor vai ajustar".

    ⚠️ **A tela NÃO recalcula por conta própria, e não deve.** O desconto ela
    até saberia aplicar, mas o CUSTO vem da cascata da ficha — a segunda
    implementação divergiria no dia em que a cascata mudasse, e o número
    prometido na tela não seria o gravado. Aqui a prévia sai do MESMO
    `_aplicar_politica` que o lançamento usa.

    ⚠️ **O valor ajustado NÃO volta para o campo editável da tela.** Ele é o
    preço CHEIO que viaja no lançamento; devolver o ajustado ali faria o envio
    seguinte trazer o valor já descontado e o servidor descontaria de novo —
    20% viraria 36%, calado.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        politica = _politica_da_pessoa(cur, body.id_pessoa)

        cheios = [float(i.valor_unitario or 0) for i in body.itens]
        if politica:
            # A cópia existe para o pedido não ser alterado: quem chama a prévia
            # continua com os preços de tabela que digitou.
            copia = SimpleNamespace(itens=[i.model_copy() for i in body.itens])
            sem_custo = _aplicar_politica(cur, id_unidade, copia, politica, {})
            ajustados = [float(i.valor_unitario or 0) for i in copia.itens]
        else:
            ajustados, sem_custo = list(cheios), []

        linhas, total_cheio, total = [], 0.0, 0.0
        for item, cheio, saiu in zip(body.itens, cheios, ajustados):
            qtd = float(item.quantidade or 0)
            linhas.append({
                "id_produto": item.id_produto,
                "valor_unitario_cheio": round(cheio, 2),
                "valor_unitario": round(saiu, 2),
                # ⚠️ `mudou` é o que a tela usa para destacar a linha. Comparar
                # os números na tela daria diferente por arredondamento de
                # ponto flutuante em linha que não mudou nada.
                "mudou": abs(saiu - cheio) >= 0.005,
                "total": round(qtd * saiu, 2),
            })
            total_cheio += qtd * cheio
            total += qtd * saiu

        return {
            "politica": _frase_da_politica(politica) if politica else None,
            # 🔑 **Quantas linhas o custo não alcançou.** Elas saem pelo preço
            # cheio dentro de um cupom "pelo custo" — a tela precisa dizer isso,
            # senão quem lança presume que a política valeu para tudo.
            "sem_custo": len(sem_custo),
            "base": (politica or {}).get("cupom_base"),
            "desconto_pct": float((politica or {}).get("cupom_desconto_pct") or 0),
            "itens": linhas,
            "total_cheio": round(total_cheio, 2),
            "total": round(total, 2),
            "desconto": round(total_cheio - total, 2),
        }


@router.get("/precos")
def precos_na_data(data: date, ids: list[int] = Query(default=[]),
                   ctx: Contexto = Depends(_editar)) -> dict:
    """O preço de venda de cada produto NO DIA da venda — para a tela preencher.

    🔑 **Pedido do dono (20/10/2026):** a venda lançada com outra data saía pelo preço
    de hoje. A tela pergunta aqui quando escolhe o produto e quando muda a data.
    ⚠️ Chave em TEXTO: o JSON não tem chave inteira, e a tela lê `r.precos["12"]`.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        achados = {}
        for id_produto in dict.fromkeys(ids):
            preco = precos.na_data(cur, id_produto, id_unidade, data)
            achados[str(id_produto)] = float(preco) if preco is not None else None
    return {"data": data.isoformat(), "precos": achados}


def _motivo(e: Exception) -> str:
    """O erro numa linha, para a tela e para a agenda.

    ⚠️ Só a primeira linha do erro do banco: o resto é `DETAIL`/`CONTEXT`, útil
    no log e ilegível numa frase de resultado.
    """
    if isinstance(e, HTTPException):
        return str(e.detail)
    return f"{type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else ''}"


def frase_das_falhas(falhas: list[dict]) -> str:
    """" — N NÃO gravada(s): doc (motivo); …", ou nada quando não houve.

    Pública porque a busca do PDV monta a frase dela e precisa dizer o mesmo.
    """
    if not falhas:
        return ""
    return (f" — {len(falhas)} NÃO gravada(s): "
            + "; ".join(f"{f['documento'] or 'sem documento'} ({f['erro']})"
                        for f in falhas[:3])
            + (f" e mais {len(falhas) - 3}" if len(falhas) > 3 else ""))


def _quando(data, hora):
    """A data da venda COM a hora dela, para o razão.

    🔑 **Relatado pelo dono (16/09/2026):** *"em Saldos e movimentos as vendas
    estão vindo sem a hora"*. E estavam: a venda guarda `data` (date) e `hora`
    (time) em colunas separadas, e a baixa mandava só a data — todo movimento de
    venda nascia às 00:00. Na coluna "Quando", quarenta vendas do dia viravam
    quarenta linhas idênticas, e a ordem entre elas deixava de existir.

    ⚠️ **Sem hora, continua sendo a data pura.** A planilha não tem hora, e
    inventar meia-noite explicitamente seria a mesma mentira com mais código.
    """
    return datetime.combine(data, hora) if hora else data


def _preparar_itens(cur, id_unidade: int, origem: str, data, itens) -> None:
    """O produto e o preço de cada linha, ANTES da política e da gravação.

    🔑 **O produto resolvido antes do preço** (20/10/2026). A linha da planilha chega
    pelo código ou pelo nome; achar o produto aqui é o que deixa a linha sem valor
    sair pelo preço DO DIA da venda.
    🔑 **Sem valor, vale o preço do DIA DA VENDA** (pedido do dono, 20/10/2026:
    "considerar o preço de venda como o do dia da venda não do dia do lançamento").
    ⚠️ Só no lançamento da CASA (à mão e planilha): o cupom do PDV traz o valor
    cobrado, e zero ali é zero.
    """
    for item in itens:
        if not item.id_produto and item.codigo:
            cur.execute("SELECT id FROM produtos WHERE lower(codigo) = lower(%s)",
                        (item.codigo,))
            achado = cur.fetchone()
            item.id_produto = achado["id"] if achado else None
        if not item.id_produto and item.descricao:
            # Último recurso: nome exato. Semelhança só sugere, nunca vincula.
            cur.execute("SELECT id FROM produtos WHERE lower(nome) = lower(%s) AND ativo",
                        (item.descricao,))
            achado = cur.fetchone()
            item.id_produto = achado["id"] if achado else None
        if origem in ("MANUAL", "PLANILHA") and item.id_produto and not item.valor_unitario:
            preco = precos.na_data(cur, item.id_produto, id_unidade, data)
            if preco is not None:
                item.valor_unitario = float(preco)
        # 🔑 **A linha da casa leva o NOME CURTO e o código do PDV** (22/10/2026, pedido
        # do dono: "ao lançar um documento de venda a mão, considerar o nome como o nome
        # curto, que é igual ao do PDV"). A linha escolhida à mão chegava só com o
        # `id_produto`, e o item ficava sem descrição — diferente do cupom do PDV, que
        # traz as duas. ⚠️ Só preenche o que veio EM BRANCO: a descrição colada da
        # planilha é o que o relatório dizia, e fica.
        if origem in ("MANUAL", "PLANILHA") and item.id_produto and (
                not item.descricao or not item.codigo):
            cur.execute("SELECT nome, nome_curto, codigo_pdv FROM produtos WHERE id = %s",
                        (item.id_produto,))
            p = cur.fetchone()
            if p:
                item.descricao = item.descricao or (p["nome_curto"] or p["nome"])[:200]
                item.codigo = item.codigo or p["codigo_pdv"]


ROTULOS_MOTIVO = {
    "CONSUMO_INTERNO": "Consumo interno",
    "PERDA": "Perda",
    "PREMIO": "Prêmio",
    "BRINDE": "Brinde/Aniversário",
    "OUTROS": "Outros",
}


def _normalizar_motivo(cur, venda) -> None:
    """O motivo de um documento que não é venda, conferido ANTES de gravar.

    🔑 **Pedido do dono (26/10/2026, migração 134)**: Perda, Prêmio, Brinde/Aniversário e
    Outros — e a antiga caixa "consumo interno" virou o motivo CONSUMO_INTERNO. Todo
    motivo põe o documento FORA da receita (`consumo_interno`), e a saída é pelo custo.
    ⚠️ Quem manda só `consumo_interno=true` (a tela antiga, o conector) continua valendo:
    vira o motivo CONSUMO_INTERNO.
    ⚠️ CONSUMO_INTERNO exige pessoa (095: sem dono, é perda); PERDA exige o motivo da
    perda, da mesma lista de Ajustes ▸ Perda; OUTROS exige a observação — "outros" sem
    explicação é o buraco que o motivo existe para fechar.
    """
    if venda.consumo_interno and not venda.motivo:
        venda.motivo = "CONSUMO_INTERNO"
    venda.motivo_observacao = (venda.motivo_observacao or "").strip() or None
    if not venda.motivo:
        venda.motivo_observacao = None
        venda.id_motivo_perda = None
        return
    venda.consumo_interno = True
    if venda.motivo != "PERDA":
        venda.id_motivo_perda = None
    if venda.motivo == "CONSUMO_INTERNO" and not venda.id_pessoa:
        raise HTTPException(
            status_code=422,
            detail="Consumo interno precisa de uma pessoa: informe para quem é o lançamento.")
    if venda.motivo == "PERDA":
        if not venda.id_motivo_perda:
            raise HTTPException(status_code=422, detail="Informe o motivo da perda.")
        cur.execute("SELECT 1 FROM perda_motivos WHERE id = %s AND ativo",
                    (venda.id_motivo_perda,))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail="Motivo de perda não encontrado.")
    if venda.motivo == "OUTROS" and not venda.motivo_observacao:
        raise HTTPException(status_code=422,
                            detail="Com o motivo Outros, a observação é obrigatória.")


def _tipo_da_saida(venda) -> str:
    """Como o documento sai do estoque: venda, perda ou consumo interno (095/134)."""
    if getattr(venda, "motivo", None) == "PERDA":
        return "SAIDA_PERDA"
    return "SAIDA_CONSUMO_INTERNO" if venda.consumo_interno else "SAIDA_VENDA"


def _motivo_perda_da_venda(venda) -> int | None:
    return getattr(venda, "id_motivo_perda", None) if _tipo_da_saida(venda) == "SAIDA_PERDA" \
        else None


def _rotulo_do_motivo(venda) -> str:
    """A observação do movimento: o motivo e, se houver, o que a pessoa escreveu."""
    rotulo = ROTULOS_MOTIVO.get(getattr(venda, "motivo", None) or "CONSUMO_INTERNO",
                                "Consumo interno")
    obs = getattr(venda, "motivo_observacao", None)
    return f"{rotulo}: {obs}"[:500] if obs else rotulo


def _gravar_item(cur, id_unidade: int, id_venda: int, venda, item, id_usuario: int,
                 custos_cache: dict) -> dict:
    """Grava UMA linha da venda: congela o custo e baixa o estoque.

    ⚠️ **Uma função só para a importação e para o "acrescentar itens"** (20/10/2026):
    a linha que entra depois tem de custar e baixar exatamente como a que entrou junto,
    senão o mesmo cupom teria duas contas de CMV conforme o momento em que a linha veio.
    `venda` é o cabeçalho: data, hora, documento, cancelada e consumo interno.
    """
    id_produto = item.id_produto
    r = {"sem_vinculo": 0, "sem_custo": 0, "de_rascunho": 0, "produzido": 0, "baixado": 0}
    custo, origem = (None, "sem_produto")
    if id_produto:
        if id_produto not in custos_cache:
            # 🔑 A loja vai junto: este custo é CONGELADO no item de venda. Calculado
            # com o estoque das duas lojas, o erro fica gravado no CMV daquele mês.
            custos_cache[id_produto] = motor.custo_teorico_do_produto(
                cur, id_produto, id_unidade=id_unidade)
        custo, origem = custos_cache[id_produto]
    else:
        r["sem_vinculo"] = 1
    if custo is None:
        r["sem_custo"] = 1
    if origem.startswith("ficha_rascunho"):
        r["de_rascunho"] = 1

    cur.execute(
        """INSERT INTO venda_itens (id_venda, codigo_pdv, descricao_pdv, id_produto,
                                    quantidade, valor_unitario, valor_total,
                                    valor_unitario_cheio,
                                    custo_ficha_unitario, origem_custo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_venda, item.codigo, item.descricao, id_produto, item.quantidade,
         item.valor_unitario, item.quantidade * item.valor_unitario,
         item.valor_unitario_cheio, custo, origem),
    )

    # VENDER É SAIR DO ESTOQUE. Sem esta baixa, o que foi vendido
    # continuava na prateleira do sistema: o CMV real ficava
    # subestimado e a primeira contagem cobria o buraco inteiro
    # como "ajuste de inventário", que é onde a diferença some.
    #
    # O que é feito NA HORA nasce e morre aqui: produz e baixa no
    # mesmo lançamento, e o saldo volta a zero. O que é PARA
    # ESTOQUE só baixa — foi produzido antes.
    # ⚠️ **Cupom cancelado NÃO baixa estoque**, e é a razão de ele
    # poder entrar. Ele existe aqui para a conferência com o PDV
    # fechar e para aparecer no painel — mercadoria que voltou para
    # a prateleira (ou nunca saiu) não pode sair do razão, que é
    # append-only e não teria como desfazer.
    if id_produto and not venda.cancelada:
        cur.execute(
            # 🔑 **De onde a venda baixa é o `id_local_venda`, quando
            # ele existe** (migração 066, pedido do dono). A mesma
            # massa de pizza pode estar na câmara como insumo e na
            # vitrine para vender: a venda tem de tirar da VITRINE, e
            # o consumo da receita da pizza, da câmara.
            # ⚠️ `id_local_padrao` continua respondendo por quem não
            # configurou nada — que é o caso de todos os produtos de
            # hoje. O `coalesce` é o que faz esta mudança não mexer em
            # nenhum deles.
            """SELECT controla_estoque,
                      coalesce(id_local_venda, id_local_padrao) AS id_local_padrao
                 FROM produtos WHERE id = %s""",
            (id_produto,),
        )
        p_venda = cur.fetchone() or {}
        if p_venda.get("controla_estoque"):
            feito = agenda.producao_da_venda(
                cur, id_unidade, id_produto, item.quantidade, id_usuario,
                documento=venda.documento, id_venda=id_venda)
            if feito:
                r["produzido"] = 1
            motor_estoque.lancar(
                cur, id_unidade=id_unidade,
                id_local=(feito or {}).get("id_local")
                         or p_venda.get("id_local_padrao"),
                id_produto=id_produto,
                # 🔑 **Consumo interno sai como CONSUMO INTERNO** (095): é
                # o que o põe na linha "dos quais: consumo interno" da
                # apuração, com o custo dele. E a PERDA pelo motivo (134) sai
                # como perda, com o motivo dela. ⚠️ A origem continua VENDA:
                # é por ela que o cancelamento acha o movimento a estornar.
                tipo=_tipo_da_saida(venda),
                id_motivo_perda=_motivo_perda_da_venda(venda),
                quantidade=item.quantidade,
                data_movimento=_quando(venda.data, venda.hora),
                origem_tipo="VENDA", origem_id=id_venda,
                documento=venda.documento, id_usuario=id_usuario,
                observacao=(_rotulo_do_motivo(venda) if venda.consumo_interno
                            else "Produzido e vendido na hora" if feito
                            else "Baixa da venda"),
            )
            r["baixado"] = 1
    return r


@router.post("/importar", status_code=201)
def importar(body: ImportarVendasRequest, ctx: Contexto = Depends(_editar)) -> dict:
    """Importa um lote. Documento repetido é ignorado — reimportar não duplica."""
    if not body.vendas:
        raise HTTPException(status_code=400, detail="Nenhuma venda na importação.")

    importadas, repetidas, itens_total, sem_vinculo, sem_custo = 0, 0, 0, 0, 0
    # Cupons que entraram MARCADOS como cancelados: contam para a conferência
    # com o PDV e para nada mais.
    canceladas = 0
    # O que a política da pessoa fez em cada venda, em português, para a tela.
    politicas_aplicadas: list[str] = []
    # Itens que a política "pelo custo" não conseguiu custear — saíram pelo
    # preço de venda, e a resposta diz quantos.
    politicas_sem_custo = 0
    # Itens cujo custo saiu de uma ficha ainda em RASCUNHO.
    de_rascunho = 0
    produzidos_na_hora, baixados = 0, 0
    custos_cache: dict[int, tuple] = {}
    # As vendas que o banco recusou — o lote segue sem elas (ver o SAVEPOINT).
    falhas: list[dict] = []
    primeira_falha: Exception | None = None

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)

        # 🔑 **Consumo de pessoa NÃO exige mais ciclo** (22/10/2026, pedido do
        # dono): o período de consumo deu lugar às contas a receber. A venda com
        # pessoa entra na data em que aconteceu e fica EM ABERTO (sem lote) até a
        # casa gerar o lote de cobrança dela — ver `services/receber.py`.
        # ⚠️ **Consumo interno é de ALGUÉM** (migração 095): é o campo que a tela só
        # habilita depois de escolher a pessoa. Sem ela, "consumo interno" seria
        # mercadoria saindo sem dono — isso é perda, e tem tela própria.
        for v in body.vendas:
            _normalizar_motivo(cur, v)

        for venda in body.vendas:
            if venda.documento:
                cur.execute(
                    """SELECT 1 FROM vendas
                        WHERE id_unidade = %s AND origem = %s AND documento = %s""",
                    (id_unidade, venda.origem, venda.documento),
                )
                if cur.fetchone():
                    repetidas += 1
                    continue

            # 🔑 **Cada venda num SAVEPOINT** (14/10/2026). O lote era uma transação
            # só: um item que o banco recusava derrubava TODAS as vendas do período,
            # e a busca do PDV ficou de 09 a 11/10 sem gravar nada por causa de um
            # rótulo que não cabia na coluna. Agora a venda que falha volta sozinha,
            # as outras entram, e a resposta diz qual ficou de fora e por quê.
            # ⚠️ **Os contadores voltam junto.** A venda desfeita já tinha somado
            # itens, baixas e frases de política; sem restaurar, a resposta contaria
            # o que o banco não guardou.
            # ⚠️ **Falhou TUDO, a exceção sobe como antes.** É o caso da venda única
            # digitada na tela: quem lança precisa do erro, não de um "0 importadas".
            fotografia = (importadas, canceladas, itens_total, sem_vinculo, sem_custo,
                          de_rascunho, produzidos_na_hora, baixados, politicas_sem_custo,
                          len(politicas_aplicadas))
            cur.execute("SAVEPOINT uma_venda")
            try:
                _preparar_itens(cur, id_unidade, venda.origem, venda.data, venda.itens)

                # 🔑 **A política de cupom da PESSOA** (04/09/2026, pedido do dono).
                # A venda à mão sempre puxa o preço de venda; informando a pessoa,
                # o item passa a valer o CUSTO, ou o preço com desconto. É o
                # desconto de funcionário e o consumo do proprietário com a mesma
                # mecânica — o que muda é a política no cadastro dela.
                #
                # ⚠️ **A conta acontece AQUI, no servidor.** Se a regra vivesse na
                # tela, uma venda lançada por outro caminho sairia com outro número
                # — e o custo congelado no item ficaria errado para sempre.
                # ⚠️ **O que o cliente mandou como preço cheio é DESCARTADO.** Só
                # `_aplicar_politica` o preenche; aceitá-lo de fora deixaria
                # qualquer chamador declarar um desconto que nunca houve, e o
                # relatório de consumo somaria um desconto inventado.
                for item in venda.itens:
                    item.valor_unitario_cheio = None

                politica = _politica_da_pessoa(cur, venda.id_pessoa)
                if politica:
                    nao_custeados = _aplicar_politica(
                        cur, id_unidade, venda, politica, custos_cache)
                    if nao_custeados:
                        politicas_sem_custo += len(nao_custeados)
                    # 🔑 **A tela precisa DIZER o que aconteceu** (pedido do dono:
                    # "apresente uma mensagem", "demonstrando isto"). Um cupom que
                    # sai por outro valor sem explicar por quê é indistinguível de
                    # erro de digitação.
                    politicas_aplicadas.append(_frase_da_politica(politica))

                bruto = sum(i.quantidade * i.valor_unitario for i in venda.itens)
                # ⚠️ **`valor_total` guarda o LÍQUIDO**, que é o que a casa recebeu e
                # o que o PDV informa no cupom. O bruto continua reconstituível pela
                # soma dos itens, e o desconto vai na coluna própria — assim a
                # conferência com o PDV fecha sem ninguém precisar refazer a conta.
                total = bruto - (venda.desconto or 0)
                cur.execute(
                    """INSERT INTO vendas (id_unidade, data, hora, origem, canal, documento,
                                           valor_total, desconto, cancelada, id_pessoa,
                                           consumo_interno, motivo, motivo_observacao,
                                           id_motivo_perda,
                                           cupom_base, cupom_desconto_pct, id_usuario)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s)
                       RETURNING id""",
                    (id_unidade, venda.data, venda.hora, venda.origem, venda.canal,
                     venda.documento, total, venda.desconto or 0, venda.cancelada,
                     venda.id_pessoa, bool(venda.consumo_interno), venda.motivo,
                     venda.motivo_observacao, venda.id_motivo_perda,
                     # 🔑 A política CONGELADA, como o custo da ficha: ela muda no
                     # cadastro, e sem isto o relatório de março passaria a se
                     # explicar por uma regra de setembro.
                     (politica or {}).get("cupom_base"),
                     (politica or {}).get("cupom_desconto_pct"), ctx.id_usuario),
                )
                id_venda = cur.fetchone()["id"]
                if venda.cancelada:
                    canceladas += 1
                else:
                    importadas += 1

                for item in venda.itens:
                    r_item = _gravar_item(cur, id_unidade, id_venda, venda, item,
                                          ctx.id_usuario, custos_cache)
                    itens_total += 1
                    sem_vinculo += r_item["sem_vinculo"]
                    sem_custo += r_item["sem_custo"]
                    de_rascunho += r_item["de_rascunho"]
                    produzidos_na_hora += r_item["produzido"]
                    baixados += r_item["baixado"]
                cur.execute("RELEASE SAVEPOINT uma_venda")
            except Exception as e:  # noqa: BLE001 — uma venda não derruba o lote
                cur.execute("ROLLBACK TO SAVEPOINT uma_venda")
                (importadas, canceladas, itens_total, sem_vinculo, sem_custo, de_rascunho,
                 produzidos_na_hora, baixados, politicas_sem_custo, n_frases) = fotografia
                del politicas_aplicadas[n_frases:]
                # ⚠️ O índice único barrou: outra gravação (o agendador e o botão
                # ao mesmo tempo) chegou primeiro. É a idempotência funcionando,
                # não falha — conta como repetida, que é o que ela é.
                if isinstance(e, erros_pg.UniqueViolation):
                    repetidas += 1
                    continue
                primeira_falha = primeira_falha or e
                falhas.append({"documento": venda.documento, "data": venda.data.isoformat(),
                               "erro": _motivo(e)})

        if falhas and not (importadas or canceladas or repetidas):
            raise primeira_falha

        auditoria.registrar(cur, ctx.id_usuario, "vendas", None, "importar",
                            depois={"vendas": importadas, "canceladas": canceladas,
                                    "itens": itens_total,
                                    "repetidas": repetidas, "sem_vinculo": sem_vinculo,
                                    "produzidos_na_hora": produzidos_na_hora,
                                    "baixados": baixados, "falhas": falhas},
                            id_unidade=id_unidade)

    return {
        "importadas": importadas,
        "canceladas": canceladas,
        "politicas": politicas_aplicadas,
        "politica_sem_custo": politicas_sem_custo,
        "repetidas": repetidas,
        "itens": itens_total,
        "itens_sem_vinculo": sem_vinculo,
        "itens_sem_custo": sem_custo,
        "itens_ficha_rascunho": de_rascunho,
        "produzidos_na_hora": produzidos_na_hora,
        "itens_baixados": baixados,
        "falhas": falhas,
        "message": f"{importadas} venda(s) importada(s)"
        # ⚠️ Logo depois do número: é a parte que pede ação.
        + frase_das_falhas(falhas)
        + (f", {repetidas} já existiam" if repetidas else "")
        + (f", {baixados} item(ns) baixado(s) do estoque" if baixados else "")
        + (f" ({produzidos_na_hora} produzido[s] na hora)" if produzidos_na_hora else "")
        # ⚠️ Só quando ACONTECEU: "0 item com ficha em rascunho" em toda
        # importação é ruído, e ruído esconde o dia em que o número não é zero.
        + (f" — {de_rascunho} item(ns) custeado(s) por ficha em RASCUNHO"
           if de_rascunho else "")
        # 🔑 A política entra na FRASE, e não só num campo: quem lança precisa
        # ver por que o cupom saiu por outro valor, na mesma linha em que soube
        # que ele foi gravado.
        + (" · " + "; ".join(politicas_aplicadas) if politicas_aplicadas else "")
        # ⚠️ Dito na resposta, e não só na tela: quem lança por outro caminho
        # (planilha, integração) também precisa saber que parte do cupom saiu
        # pelo preço cheio.
        + (f" · {politicas_sem_custo} item(ns) sem custo conhecido saíram pelo "
           "preço de venda" if politicas_sem_custo else ""),
    }


def _por_que_esta_em_lote(cur, venda: dict, para: str) -> str | None:
    """Se a venda está num lote de cobrança, a frase que diz qual e o que fazer.

    🔑 **Documento em lote não muda** (22/10/2026): o lote é o que foi mandado à
    pessoa, e um item a mais ou um cancelamento faria o valor cobrado deixar de
    bater com o relatório que ela recebeu. Cancelado não conta — o lote cancelado
    já devolveu os documentos.
    """
    if not venda.get("id_consumo_lote"):
        return None
    cur.execute("SELECT id, status FROM consumo_lotes WHERE id = %s",
                (venda["id_consumo_lote"],))
    l = cur.fetchone()
    if not l:
        return None
    if l["status"] == "RECEBIDO":
        return (f"Esta venda está no lote de cobrança nº {l['id']}, que já foi recebido. "
                f"Estorne a baixa e tire o documento do lote para {para}.")
    return (f"Esta venda está no lote de cobrança nº {l['id']}, em cobrança. Tire o "
            f"documento do lote (Contas a receber) para {para}.")


def _por_que_nao_edita(cur, id_unidade: int, venda: dict) -> str | None:
    """Por que esta venda NÃO aceita item novo — ou nada, se aceita.

    🔑 **A regra do dono (20/10/2026):** *"permitir editar um documento, adicionar mais
    itens, desde que o período que ele esteja já não foi fechado"*. Fechado aqui é
    qualquer um dos dois que fotografam a venda: o PERÍODO do CMV (o fechamento
    congela a apuração) e o LOTE de cobrança da pessoa (foi mandado a ela).
    ⚠️ **Venda do PDV não se edita aqui.** O cupom é do PDV, e a importação seguinte o
    compararia com um documento que o PDV nunca emitiu; a correção é lá.
    ⚠️ **Sem exceção para `estoque.retroativo`**: o pedido é "desde que não foi fechado",
    e quem precisa mexer num período fechado o reabre — fica registrado quem foi.
    """
    if venda["cancelada"]:
        return "Esta venda está cancelada."
    if venda["origem"] not in ("MANUAL", "PLANILHA"):
        return ("Esta venda veio do PDV: o cupom é dele, e a correção se faz lá — a próxima "
                "busca traz o documento corrigido.")
    motivo_lote = _por_que_esta_em_lote(cur, venda, "acrescentar itens")
    if motivo_lote:
        return motivo_lote
    cur.execute(
        """SELECT inicio, fim, ciclo FROM cmv_fechamentos
            WHERE id_unidade = %s AND status = 'FECHADO' AND %s BETWEEN inicio AND fim""",
        (id_unidade, venda["data"]),
    )
    fechado = cur.fetchone()
    if fechado:
        from services import periodos

        nome = periodos.rotulo(fechado["inicio"], fechado["fim"], fechado["ciclo"] or "MENSAL")
        return (f"O período de {nome} está fechado no CMV. Reabra o período para "
                "acrescentar itens a esta venda.")
    return None


def _periodo_fechado_em(cur, id_unidade: int, dia) -> str | None:
    """O nome do período do CMV FECHADO que contém `dia`, ou nada."""
    cur.execute(
        """SELECT inicio, fim, ciclo FROM cmv_fechamentos
            WHERE id_unidade = %s AND status = 'FECHADO' AND %s BETWEEN inicio AND fim""",
        (id_unidade, dia),
    )
    fechado = cur.fetchone()
    if not fechado:
        return None
    from services import periodos

    return periodos.rotulo(fechado["inicio"], fechado["fim"], fechado["ciclo"] or "MENSAL")


def _por_que_nao_altera(cur, id_unidade: int, venda: dict) -> str | None:
    """Por que a data e o número desta venda NÃO podem mudar — ou nada, se podem.

    🔑 **A regra do dono (23/10/2026):** *"Para documentos lançados a mão, que ainda
    não estão em algum lote baixado, permitir alterar a data e numero do documento"*.
    ⚠️ **Lote EM COBRANÇA não impede** (só o recebido): a correção do cabeçalho não
    muda o valor cobrado. Item novo continua barrado em lote de qualquer situação
    (`_por_que_nao_edita`).
    ⚠️ **Só MANUAL**: a da planilha se reimporta pelo número, e trocá-lo faria a
    próxima importação da mesma planilha lançar o documento de novo.
    """
    if venda["cancelada"]:
        return "Esta venda está cancelada."
    if venda["origem"] != "MANUAL":
        return ("Só o documento lançado à mão muda de data e número: "
                + ("o da planilha se reimporta pelo número, e trocá-lo o lançaria de novo."
                   if venda["origem"] == "PLANILHA" else "o do PDV se corrige lá."))
    if venda.get("id_consumo_lote"):
        cur.execute("SELECT id, status FROM consumo_lotes WHERE id = %s",
                    (venda["id_consumo_lote"],))
        l = cur.fetchone()
        if l and l["status"] == "RECEBIDO":
            return (f"Esta venda está no lote de cobrança nº {l['id']}, que já foi recebido. "
                    "Estorne a baixa do lote para alterar a data ou o número.")
    return None


@router.put("/{id_venda}")
def alterar(id_venda: int, body: VendaAlterar, ctx: Contexto = Depends(_editar)) -> dict:
    """Muda a data e/ou o número de um documento lançado à mão (23/10/2026).

    🔑 **A data leva a baixa de estoque junto.** A saída da venda nasce na data dela
    (`_quando`), e o razão é append-only: cada saída viva é ESTORNADA na data em que
    estava e lançada de novo na data nova — o dia antigo zera, o novo ganha a saída,
    e o CMV de cada período continua batendo. A produção "na hora" não se mexe: ela
    sempre foi datada no momento do lançamento, não na data da venda.
    ⚠️ **Período do CMV fechado trava as DUAS pontas**: sair de um período fechado
    mudaria a apuração dele, e entrar num também.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT id, data, hora, origem, documento, cancelada, id_consumo_lote
                 FROM vendas WHERE id = %s AND id_unidade = %s FOR UPDATE""",
            (id_venda, id_unidade),
        )
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")
        venda = dict(venda)
        motivo = _por_que_nao_altera(cur, id_unidade, venda)
        if motivo:
            raise HTTPException(status_code=409, detail=motivo)

        nova_data = body.data or venda["data"]
        novo_doc = (body.documento or "").strip() or venda["documento"]
        muda_data = nova_data != venda["data"]
        muda_doc = novo_doc != venda["documento"]
        if not (muda_data or muda_doc):
            return {"id": id_venda, "estornados": 0, "message": "Nada mudou"}

        if muda_data:
            if nova_data > relogio.hoje_da_casa():
                raise HTTPException(status_code=422,
                                    detail="A data da venda não pode ser no futuro.")
            for dia in (venda["data"], nova_data):
                nome = _periodo_fechado_em(cur, id_unidade, dia)
                if nome:
                    raise HTTPException(
                        status_code=409,
                        detail=f"O período de {nome} está fechado no CMV. Reabra o período "
                               "para mudar a data desta venda.")
        if muda_doc:
            cur.execute(
                """SELECT id FROM vendas WHERE id_unidade = %s AND origem = %s
                      AND documento = %s AND id <> %s""",
                (id_unidade, venda["origem"], novo_doc, id_venda))
            outra = cur.fetchone()
            if outra:
                raise HTTPException(
                    status_code=409,
                    detail=f"Já existe uma venda lançada à mão com o documento {novo_doc} "
                           f"(venda nº {outra['id']}).")

        refeitos = 0
        if muda_data:
            cur.execute(
                """SELECT m.id, m.id_local, m.id_produto, m.tipo, m.quantidade,
                          m.data_movimento, m.observacao, m.id_motivo_perda
                     FROM estoque_movimentos m
                    WHERE m.origem_tipo = 'VENDA' AND m.origem_id = %s
                      AND m.id_estorno_de IS NULL
                      AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                       WHERE e.id_estorno_de = m.id)
                    ORDER BY m.id""",
                (id_venda,))
            vivos = [dict(r) for r in cur.fetchall()]
            for m in reversed(vivos):
                motor_estoque.estornar(
                    cur, m["id"], ctx.id_usuario,
                    f"Venda #{id_venda} mudou de data ({venda['data']:%d/%m/%Y} → "
                    f"{nova_data:%d/%m/%Y})",
                    data_movimento=m["data_movimento"])
            for m in vivos:
                motor_estoque.lancar(
                    cur, id_unidade=id_unidade, id_local=m["id_local"],
                    # ⚠️ No razão a saída tem SINAL (-2); `lancar` quer o positivo.
                    id_produto=m["id_produto"], tipo=m["tipo"],
                    quantidade=abs(m["quantidade"]),
                    # ⚠️ A perda lançada pelo motivo da venda (134) volta COM o motivo
                    # dela: sem ele, `lancar` recusa a perda e a data não muda.
                    id_motivo_perda=m["id_motivo_perda"],
                    data_movimento=_quando(nova_data, venda["hora"]),
                    origem_tipo="VENDA", origem_id=id_venda, documento=novo_doc,
                    id_usuario=ctx.id_usuario, observacao=m["observacao"])
            refeitos = len(vivos)

        cur.execute("UPDATE vendas SET data = %s, documento = %s WHERE id = %s",
                    (nova_data, novo_doc, id_venda))
        # O "desde" do lote em cobrança acompanha a data nova; o valor não muda.
        if muda_data and venda["id_consumo_lote"]:
            from services import receber as receber_motor

            receber_motor._recalcular(cur, venda["id_consumo_lote"])
        auditoria.registrar(cur, ctx.id_usuario, "vendas", id_venda, "alterar",
                            antes={"data": str(venda["data"]), "documento": venda["documento"]},
                            depois={"data": str(nova_data), "documento": novo_doc,
                                    "movimentos_refeitos": refeitos},
                            id_unidade=id_unidade)

    partes = []
    if muda_doc:
        partes.append(f"documento {novo_doc}")
    if muda_data:
        partes.append(f"data {nova_data:%d/%m/%Y}")
    return {"id": id_venda, "data": str(nova_data), "documento": novo_doc,
            "estornados": refeitos,
            "message": "Venda alterada: " + " e ".join(partes)
                       + (f" — {refeitos} baixa(s) de estoque refeita(s) na data nova"
                          if refeitos else "")}


@router.post("/{id_venda}/itens", status_code=201)
def acrescentar_itens(id_venda: int, body: AcrescentarItensRequest,
                      ctx: Contexto = Depends(_editar)) -> dict:
    """Acrescenta itens a uma venda já lançada — o mesmo documento, mais linhas.

    🔑 **Pedido do dono (20/10/2026).** Antes, o item esquecido virava uma segunda venda
    com outro documento (ou cancelar e lançar tudo de novo), e o cupom deixava de ser um.
    ⚠️ **Só acrescenta.** O que já entrou está no razão, que é append-only; tirar uma
    linha é cancelar a venda (o estorno devolve tudo) e lançar de novo.
    ⚠️ A política vale a CONGELADA na venda, não a de hoje do cadastro: o cupom inteiro
    tem de sair pela mesma regra.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT v.id, v.data, v.hora, v.origem, v.documento, v.cancelada, v.id_pessoa,
                      v.consumo_interno, v.motivo, v.motivo_observacao, v.id_motivo_perda,
                      v.cupom_base, v.cupom_desconto_pct,
                      v.id_consumo_lote, v.valor_total, f.nome AS pessoa
                 FROM vendas v
                 LEFT JOIN fornecedores f ON f.id = v.id_pessoa
                WHERE v.id = %s AND v.id_unidade = %s
                  FOR UPDATE OF v""",
            (id_venda, id_unidade),
        )
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")
        venda = dict(venda)
        motivo = _por_que_nao_edita(cur, id_unidade, venda)
        if motivo:
            raise HTTPException(status_code=409, detail=motivo)

        _preparar_itens(cur, id_unidade, venda["origem"], venda["data"], body.itens)
        for item in body.itens:
            item.valor_unitario_cheio = None
        custos_cache: dict[int, tuple] = {}
        sem_custo_politica = 0
        if venda["cupom_base"]:
            politica = {"nome": venda["pessoa"] or "", "cupom_base": venda["cupom_base"],
                        "cupom_desconto_pct": venda["cupom_desconto_pct"]}
            sem_custo_politica = len(_aplicar_politica(
                cur, id_unidade, SimpleNamespace(itens=body.itens), politica, custos_cache))

        cabecalho = SimpleNamespace(data=venda["data"], hora=venda["hora"],
                                    documento=venda["documento"], cancelada=False,
                                    consumo_interno=bool(venda["consumo_interno"]),
                                    # A linha que chega depois sai pelo MESMO motivo (134).
                                    motivo=venda["motivo"],
                                    motivo_observacao=venda["motivo_observacao"],
                                    id_motivo_perda=venda["id_motivo_perda"])
        soma = {"sem_vinculo": 0, "sem_custo": 0, "de_rascunho": 0, "produzido": 0, "baixado": 0}
        for item in body.itens:
            r_item = _gravar_item(cur, id_unidade, id_venda, cabecalho, item,
                                  ctx.id_usuario, custos_cache)
            for k in soma:
                soma[k] += r_item[k]
        acrescimo = round(sum(i.quantidade * i.valor_unitario for i in body.itens), 2)
        # ⚠️ `valor_total` é o LÍQUIDO: o desconto do cabeçalho continua o mesmo, e a
        # linha nova soma inteira.
        cur.execute("UPDATE vendas SET valor_total = valor_total + %s WHERE id = %s",
                    (acrescimo, id_venda))
        auditoria.registrar(cur, ctx.id_usuario, "vendas", id_venda, "acrescentar_itens",
                            antes={"valor_total": float(venda["valor_total"])},
                            depois={"itens": len(body.itens), "acrescimo": acrescimo,
                                    "baixados": soma["baixado"]},
                            id_unidade=id_unidade)

    return {
        "itens": len(body.itens),
        "acrescimo": acrescimo,
        "valor_total": round(float(venda["valor_total"]) + acrescimo, 2),
        "itens_sem_vinculo": soma["sem_vinculo"],
        "itens_sem_custo": soma["sem_custo"],
        "itens_baixados": soma["baixado"],
        "message": (f"{len(body.itens)} item(ns) acrescentado(s) — mais R$ {acrescimo:.2f}"
                    .replace(".", ",")
                    + (f", {soma['baixado']} baixado(s) do estoque" if soma["baixado"] else "")
                    + (f" · {sem_custo_politica} sem custo conhecido saíram pelo preço de venda"
                       if sem_custo_politica else "")),
    }


@router.delete("/{id_venda}")
def cancelar(id_venda: int, ctx: Contexto = Depends(_editar)) -> dict:
    """Cancela a venda para o CMV — não apaga, para o histórico continuar fiel.

    A baixa de estoque que a venda causou volta como ESTORNO. Cancelar sem
    devolver deixaria o produto vendido fora da prateleira e fora do caixa ao
    mesmo tempo — a diferença apareceria na contagem, sem nome.
    """
    with get_cursor() as cur:
        # ⚠️ A loja entra na busca: sem ela, um id de outra loja seria cancelado
        # por quem nem enxerga aquela venda na tela.
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT cancelada, id_consumo_lote FROM vendas "
                    "WHERE id = %s AND id_unidade = %s FOR UPDATE",
                    (id_venda, id_unidade))
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")
        if venda["cancelada"]:
            raise HTTPException(status_code=400, detail="Esta venda já está cancelada.")
        # ⚠️ Documento em lote de cobrança não se cancela: o lote foi mandado à
        # pessoa com ele dentro (22/10/2026).
        motivo_lote = _por_que_esta_em_lote(cur, dict(venda), "cancelar")
        if motivo_lote:
            raise HTTPException(status_code=409, detail=motivo_lote)

        # 🔑 **A produção que a venda disparou volta JUNTO** (110). O produto
        # NA_HORA produz e baixa no mesmo lançamento; a baixa nasce com origem
        # VENDA, mas a produção grava os movimentos dela com origem PRODUCAO.
        # Procurar só por VENDA devolvia o café e deixava o pó consumido — e o
        # produzido com saldo, que "na hora" nunca tem.
        # ⚠️ `ORDER BY m.id DESC` é a ordem inversa do que aconteceu: primeiro
        # volta a saída da venda, depois sai a entrada da produção, por último
        # voltam os insumos. Em outra ordem o produzido passaria por negativo.
        cur.execute(
            """SELECT m.id FROM estoque_movimentos m
                WHERE ((m.origem_tipo = 'VENDA' AND m.origem_id = %s)
                       OR (m.origem_tipo = 'PRODUCAO'
                           AND m.origem_id IN (SELECT p.id FROM producoes p
                                                WHERE p.id_venda = %s)))
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                   WHERE e.id_estorno_de = m.id)
                ORDER BY m.id DESC""",
            (id_venda, id_venda),
        )
        movimentos = [r["id"] for r in cur.fetchall()]
        for id_movimento in movimentos:
            motor_estoque.estornar(cur, id_movimento, ctx.id_usuario,
                                   f"Cancelamento da venda #{id_venda}")

        cur.execute("UPDATE vendas SET cancelada = true WHERE id = %s", (id_venda,))
        auditoria.registrar(cur, ctx.id_usuario, "vendas", id_venda, "cancelar",
                            depois={"movimentos_estornados": len(movimentos)})
    return {"estornados": len(movimentos),
            "message": "Venda cancelada"
                       + (f" — {len(movimentos)} movimento(s) devolvido(s) ao estoque"
                          if movimentos else "")}


@router.get("/sem-baixa/previa")
def previa_sem_baixa(ctx: Contexto = Depends(_ver)) -> dict:
    """Vendas de produto que controla estoque e que NUNCA saíram do razão.

    🔑 **O buraco que a reconciliação do PDV deixava** (10/09/2026, achado na
    varredura). Item de venda que entra sem produto — o código do cardápio ainda
    não estava vinculado — não baixa estoque, e está certo: não há de onde tirar.
    Quando alguém faz a ligação, `cardapio.reconciliar` reaponta o item e
    recalcula o custo congelado, mas **não lança a saída que nunca aconteceu**.

    🔑 **A fusão já fechava esse mesmo buraco** (`produtos_vinculo._baixa_pendente`),
    com a justificativa escrita lá: *"comprou 15, vendeu 10, e o saldo dizendo
    15. Na primeira contagem faltariam 10, aparecendo como ajuste de inventário —
    que é onde a diferença some sem nome."* A mesma situação, dois caminhos, e só
    um resolvia.

    ⚠️ **O sintoma não aparece nos números da tela.** O saldo fica apenas
    negativo, não "negativo e mais 128 que nem chegaram a sair" — foi assim que
    128 unidades de um produto real passaram despercebidas por dez dias.

    ⚠️ **Venda CANCELADA fica de fora**: ela não consumiu nada, e baixar por ela
    inventaria um consumo que não houve.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        # 🔑 **A conta é AGREGADA por produto: vendido menos o que já saiu.**
        # A primeira versão perguntava, por VENDA, se existia movimento com
        # `origem_id = venda.id` — e errava feio. A baixa que a FUSÃO faz
        # (`produtos_vinculo`, "o que foi vendido e nunca saiu") é **um
        # movimento agregado** com `origem_tipo = 'VINCULO'`, cobrindo todas as
        # vendas do cadastro absorvido de uma vez. Nenhuma delas casa por
        # `origem_id`, então a prévia as dava como pendentes.
        # ⚠️ **Medido, e por pouco não foi ao ar:** a água mineral tinha 138
        # vendidas e 138 já fora do estoque (128 pela fusão, 10 por venda), e a
        # prévia anunciava 128 faltando. O botão teria baixado em DOBRO.
        # ⚠️ Movimento ESTORNADO não conta como saída: a contrapartida devolveu
        # a mercadoria, e a venda voltou a dever baixa.
        cur.execute(
            """WITH vendido AS (
                 SELECT vi.id_produto, sum(vi.quantidade) AS qtd,
                        count(*) AS itens, min(v.data) AS desde, max(v.data) AS ate
                   FROM venda_itens vi
                   JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                  WHERE v.id_unidade = %s AND vi.id_produto IS NOT NULL
                  GROUP BY vi.id_produto
               ), saiu AS (
                 SELECT m.id_produto, sum(abs(m.quantidade)) AS qtd
                   FROM estoque_movimentos m
                  WHERE m.id_unidade = %s
                    -- ⚠️ O consumo interno lançado como VENDA (095) também é
                    -- saída da venda: sem ele aqui, a tela o daria como "não
                    -- baixado" e o botão baixaria de novo.
                    -- E a perda pelo motivo da venda (134), pelo mesmo motivo.
                    AND (m.tipo = 'SAIDA_VENDA'
                         OR (m.tipo IN ('SAIDA_CONSUMO_INTERNO', 'SAIDA_PERDA')
                             AND m.origem_tipo = 'VENDA'))
                    AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                     WHERE e.id_estorno_de = m.id)
                  GROUP BY m.id_produto
               )
               SELECT p.id AS id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                      p.id_local_padrao, l.nome AS local_destino,
                      vd.itens, vd.desde, vd.ate,
                      vd.qtd AS vendido, coalesce(sa.qtd, 0) AS ja_saiu,
                      vd.qtd - coalesce(sa.qtd, 0) AS quantidade
                 FROM vendido vd
                 JOIN produtos p ON p.id = vd.id_produto
                                AND p.controla_estoque AND p.ativo
                 LEFT JOIN saiu sa ON sa.id_produto = vd.id_produto
                 LEFT JOIN locais_estoque l ON l.id = p.id_local_padrao
                WHERE vd.qtd - coalesce(sa.qtd, 0) > 0.0001
                ORDER BY vd.qtd - coalesce(sa.qtd, 0) DESC""",
            (id_unidade, id_unidade),
        )
        linhas = [dict(r) for r in cur.fetchall()]

        # ⚠️ **A prévia resolve a RESERVA do local, como o lançamento vai fazer.**
        # Sem isso a coluna dizia "—" para todo produto sem `id_local_padrao` —
        # que é a maioria — e quem confirma não via para onde a mercadoria ia
        # sair. Prévia que esconde o destino não é prévia.
        cur.execute("SELECT id, nome FROM locais_estoque WHERE id_unidade = %s AND ativo "
                    "ORDER BY principal DESC, id LIMIT 1", (id_unidade,))
        reserva = cur.fetchone()
        for linha in linhas:
            if not linha["local_destino"] and reserva:
                linha["local_destino"] = reserva["nome"]
                linha["destino_por_reserva"] = True

        # ⚠️ **O saldo DEPOIS entra na prévia.** Quase toda baixa destas vai
        # deixar o saldo negativo — o razão aceita e a saída sai por custo
        # provisório —, mas quem confirma precisa ver antes, não descobrir na
        # contagem. Mesma escolha da prévia da fusão.
        for linha in linhas:
            cur.execute(
                """SELECT coalesce(sum(quantidade), 0) AS saldo FROM estoque_saldos
                    WHERE id_produto = %s AND id_unidade = %s""",
                (linha["id_produto"], id_unidade))
            saldo = float(cur.fetchone()["saldo"] or 0)
            linha["saldo_hoje"] = saldo
            linha["saldo_depois"] = saldo - float(linha["quantidade"])
    return {
        "itens": linhas,
        "produtos": len(linhas),
        "unidades": float(sum(float(l["quantidade"]) for l in linhas)),
    }


@router.post("/sem-baixa/baixar")
def baixar_sem_baixa(id_produto: int | None = None,
                     ctx: Contexto = Depends(requer_permissao("estoque.saidas"))) -> dict:
    """Lança as saídas que faltaram, uma por venda.

    ⚠️ **Uma saída por VENDA, não uma somada por produto.** O razão é o extrato
    do que aconteceu: um lançamento de 128 no dia de hoje diria que a casa
    consumiu 128 hoje, e o CMV de cada dia ficaria errado nos dois sentidos.
    Cada saída leva a data e o documento da venda que a originou.

    ⚠️ **`pode_retroativo` vem da permissão de quem clica.** Venda de mês FECHADO
    não pode virar movimento: o relatório daquele mês já foi ao contador, e o
    razão não se reescreve. A trava de período recusa, e está certo — quem
    precisar acertar mês fechado faz pelo inventário.

    ⚠️ **Recalcula a lista no servidor**, como o repontar das notas: entre ver a
    prévia e clicar, uma importação pode ter trazido venda nova.

    ⚠️ **`id_produto` limita a UM produto.** A tela não usa — o botão é único,
    como pedido —, mas existe por duas razões: dá para acertar um item de cada
    vez quando o acervo é grande, e é o que permite a suíte provar o ciclo sem
    baixar a base inteira. Sem ele, cada rodada do teste mexia no estoque de
    todos os produtos da casa, e os cenários que medem a identidade da
    movimentação acusavam a diferença — que é a armadilha que a memória de
    estoque já registra sobre saldo negativo.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        # 🔑 **Quanto falta é AGREGADO; de QUAIS vendas sai é cronológico.** O
        # quanto vem da mesma conta da prévia (vendido − já saiu), porque a
        # baixa que a fusão faz é um movimento único cobrindo várias vendas e
        # não casa por `origem_id`. O de quais vendas sai é a ordem do tempo: as
        # mais ANTIGAS primeiro, até cobrir o que falta.
        # ⚠️ **Assim a data de cada saída continua sendo a da venda que a
        # originou** — o razão é o extrato do que aconteceu, e um lançamento
        # somado hoje diria que a casa consumiu tudo hoje.
        cur.execute(
            """WITH vendido AS (
                 SELECT vi.id_produto, sum(vi.quantidade) AS qtd
                   FROM venda_itens vi
                   JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                  WHERE v.id_unidade = %s AND vi.id_produto IS NOT NULL
                  GROUP BY vi.id_produto
               ), saiu AS (
                 SELECT m.id_produto, sum(abs(m.quantidade)) AS qtd
                   FROM estoque_movimentos m
                  WHERE m.id_unidade = %s
                    -- ⚠️ O consumo interno lançado como VENDA (095) também é
                    -- saída da venda: sem ele aqui, a tela o daria como "não
                    -- baixado" e o botão baixaria de novo.
                    -- E a perda pelo motivo da venda (134), pelo mesmo motivo.
                    AND (m.tipo = 'SAIDA_VENDA'
                         OR (m.tipo IN ('SAIDA_CONSUMO_INTERNO', 'SAIDA_PERDA')
                             AND m.origem_tipo = 'VENDA'))
                    AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                     WHERE e.id_estorno_de = m.id)
                  GROUP BY m.id_produto
               )
               SELECT vd.id_produto, vd.qtd - coalesce(sa.qtd, 0) AS falta,
                      p.id_local_padrao
                 FROM vendido vd
                 JOIN produtos p ON p.id = vd.id_produto
                                AND p.controla_estoque AND p.ativo
                 LEFT JOIN saiu sa ON sa.id_produto = vd.id_produto
                WHERE vd.qtd - coalesce(sa.qtd, 0) > 0.0001
                  AND (%s::int IS NULL OR vd.id_produto = %s)""",
            (id_unidade, id_unidade, id_produto, id_produto),
        )
        faltas = {r["id_produto"]: [float(r["falta"]), r["id_local_padrao"]]
                  for r in cur.fetchall()}
        pendentes = []
        if faltas:
            cur.execute(
                """SELECT vi.id, vi.id_produto, vi.quantidade, v.id AS id_venda, v.data,
                          v.hora, v.documento, v.consumo_interno, v.motivo,
                          v.motivo_observacao, v.id_motivo_perda
                     FROM venda_itens vi
                     JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                    WHERE v.id_unidade = %s AND vi.id_produto = ANY(%s)
                    ORDER BY v.data, v.id""",
                (id_unidade, list(faltas)),
            )
            for item in cur.fetchall():
                restante, local = faltas[item["id_produto"]]
                if restante <= 0.0001:
                    continue
                # ⚠️ A última venda pode entrar PARCIAL: o que falta raramente
                # cai exatamente no fim de uma venda. Baixar a venda inteira
                # tiraria mais do que se deve.
                qtd = min(float(item["quantidade"]), restante)
                faltas[item["id_produto"]][0] = restante - qtd
                pendentes.append({**dict(item), "quantidade": qtd,
                                  "id_local_padrao": local})
        cur.execute("SELECT id FROM locais_estoque WHERE id_unidade = %s AND ativo "
                    "ORDER BY principal DESC, id LIMIT 1", (id_unidade,))
        reserva = (cur.fetchone() or {}).get("id")
        baixados, recusados = 0, []
        for item in pendentes:
            try:
                motor_estoque.lancar(
                    cur, id_unidade=id_unidade,
                    id_local=item["id_local_padrao"] or reserva,
                    id_produto=item["id_produto"],
                    # O consumo interno (095) sai como consumo interno, também aqui;
                    # e a perda pelo motivo (134), como perda.
                    tipo=_tipo_da_saida(SimpleNamespace(**item)),
                    id_motivo_perda=_motivo_perda_da_venda(SimpleNamespace(**item)),
                    quantidade=item["quantidade"],
                    data_movimento=_quando(item["data"], item["hora"]),
                    origem_tipo="VENDA", origem_id=item["id_venda"],
                    documento=item["documento"], id_usuario=ctx.id_usuario,
                    observacao="Baixa da venda que ficou para trás do vínculo",
                    pode_retroativo=ctx.pode("estoque.retroativo"),
                )
                baixados += 1
            except HTTPException as e:
                # ⚠️ Uma recusa não derruba as outras: mês fechado costuma pegar
                # só as vendas mais antigas, e parar tudo por causa delas
                # deixaria o resto do buraco aberto.
                recusados.append({"id_venda": item["id_venda"], "motivo": e.detail})
        if baixados:
            auditoria.registrar(cur, ctx.id_usuario, "vendas", None, "baixar_sem_baixa",
                                depois={"baixados": baixados, "recusados": len(recusados)},
                                id_unidade=id_unidade)
    return {
        "baixados": baixados, "recusados": recusados,
        "message": (f"{baixados} venda(s) baixada(s) do estoque"
                    + (f" — {len(recusados)} recusada(s), veja o motivo." if recusados else "")
                    if baixados else "Nada a baixar: toda venda já saiu do estoque."),
    }


@router.get("/sem-vinculo")
def sem_vinculo(busca: str | None = None, ctx: Contexto = Depends(_ver)) -> list[dict]:
    """Itens vendidos que não achamos no cadastro — a fila de de-para do PDV.

    ⚠️ **A lista é cortada no topo por RECEITA, e por isso tem busca.** São os
    100 que mais pesam; num cardápio grande, o item que alguém quer resolver
    raramente está entre eles — e não achá-lo lê como "já foi resolvido", que é
    outra coisa. É a mesma lição do ranking de margem, que ganhou `id_produto`
    pelo mesmo motivo.
    """
    alvo = f"%{busca.strip()}%" if busca and busca.strip() else None
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT vi.codigo_pdv, vi.descricao_pdv, count(*) AS ocorrencias,
                      sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita
                 FROM venda_itens vi
                 JOIN vendas v ON v.id = vi.id_venda
                WHERE vi.id_produto IS NULL AND NOT v.cancelada AND v.id_unidade = %(u)s
                  AND (%(alvo)s::text IS NULL
                       OR vi.codigo_pdv ILIKE %(alvo)s
                       OR vi.descricao_pdv ILIKE %(alvo)s)
                GROUP BY vi.codigo_pdv, vi.descricao_pdv
                ORDER BY receita DESC LIMIT 100""",
            {"u": id_unidade, "alvo": alvo},
        )
        return [dict(r) for r in cur.fetchall()]


# ⚠️ **`/{id_venda}` vem DEPOIS de `/sem-vinculo`, e a ordem é o que faz as duas
# funcionarem.** O FastAPI casa as rotas na ordem em que foram declaradas: com o
# parâmetro na frente, "sem-vinculo" viraria um id e o pedido morreria em 422
# antes de chegar à fila de de-para.
@router.get("/por-pessoa")
def por_pessoa(
    situacao: str = Query(default="aberto", pattern="^(aberto|cobranca|recebido|todos)$"),
    de: date | None = None,
    ate: date | None = None,
    id_lote: int | None = None,
    id_pessoa: int | None = Query(default=None),
    detalhe: str = Query(default="sintetico",
                         pattern="^(sintetico|analitico|documento|documento_itens)$"),
    ctx: Contexto = Depends(_ver),
) -> dict:
    """O que cada pessoa consumiu, e quanto deixou de pagar.

    🔑 **O caso do dono** (04/09/2026): "o funcionário vai comprar, lançamos e
    depois cobramos o valor dele" — o relatório é o documento dessa cobrança, e
    precisa mostrar as duas colunas para ser aceito por quem paga: o que
    custaria e o que está sendo cobrado.

    ⚠️ **Cupom CANCELADO fica de fora.** Ele entra na base para a conferência
    com o PDV bater, mas cobrar de alguém um cupom cancelado seria cobrar o que
    não foi consumido. É a mesma regra de todo lugar que soma dinheiro.

    ⚠️ **As somas dos ITENS saem de uma CTE, nunca do mesmo SELECT do
    cabeçalho.** Juntar `vendas` com `venda_itens` repete o cabeçalho uma vez
    por linha, e um `sum(v.desconto)` ali multiplicaria o desconto pelo número
    de itens do cupom — a armadilha que já custou a conferência do dia 02/09.

    ⚠️ **O preço cheio da linha cai no cobrado quando é NULO.** Nulo quer dizer
    "a política não tocou nesta linha": tratá-lo como zero faria o relatório
    anunciar um desconto de 100%.
    """
    if de and ate and ate < de:
        raise HTTPException(status_code=400, detail="A data final é anterior à inicial.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        if id_lote is not None:
            cur.execute("SELECT 1 FROM consumo_lotes WHERE id = %s AND id_unidade = %s",
                        (id_lote, id_unidade))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Lote não encontrado.")
        # 🔑 **O recorte é a SITUAÇÃO do documento e as datas** (22/10/2026): o ciclo
        # saiu com as contas a receber. Ver `consumo_pessoa.recorte`.
        # ⚠️ A consulta mora no serviço porque a EXPORTAÇÃO usa a mesma: escrita
        # duas vezes, a tela e o arquivo entregue ao funcionário divergiriam
        # numa discussão sobre dinheiro.
        filtro = {"situacao": situacao, "de": de, "ate": ate, "id_lote": id_lote}
        linhas = consumo.apurar(cur, id_unidade, filtro,
                                [id_pessoa] if id_pessoa else None, detalhe)
        return {
            "situacao": situacao, "de": de, "ate": ate, "id_lote": id_lote,
            "detalhe": detalhe,
            "linhas": linhas,
            "total_cheio": round(sum(float(l["total_cheio"] or 0) for l in linhas), 2),
            "total": round(sum(float(l["total"] or 0) for l in linhas), 2),
            "desconto": round(
                sum(float(l["total_cheio"] or 0) - float(l["total"] or 0) for l in linhas), 2),
        }


@router.get("/por-pessoa/{id_pessoa}/em-aberto")
def consumo_em_aberto(id_pessoa: int, ctx: Contexto = Depends(_ver)) -> dict:
    """O consumo desta pessoa ainda não cobrado, e o que está em cobrança — para o
    cartão do cadastro dela.

    🔑 **Pedido do dono (26/09/2026):** *"no cadastro da pessoa, incluir um item
    referente a consumos no período aberto atual."* Desde 22/10/2026 não há período:
    o cartão mostra o que está EM ABERTO (sem lote) e soma o que já foi mandado em
    lote e ainda não voltou.
    ⚠️ **A mesma consulta do relatório** (`consumo_pessoa.apurar`, por documento com
    os itens) — o cartão e o PDF entregue ao funcionário não podem discordar.
    ⚠️ **Mesma chave do relatório**: consumo é dinheiro de alguém, e ver a ficha da
    pessoa (`cadastros.fornecedores`) não é o mesmo que ver o que ela deve.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        docs = consumo.apurar(cur, id_unidade, {"situacao": "aberto"}, [id_pessoa],
                              "documento_itens")
        cur.execute(
            """SELECT count(*) AS lotes, coalesce(sum(total), 0) AS total
                 FROM consumo_lotes
                WHERE id_unidade = %s AND id_pessoa = %s AND status = 'ABERTO'""",
            (id_unidade, id_pessoa))
        cobranca = dict(cur.fetchone())
    cheio = round(sum(float(d["total_cheio"] or 0) for d in docs), 2)
    total = round(sum(float(d["total"] or 0) for d in docs), 2)
    return {
        "documentos": docs,
        "total_cheio": cheio,
        "desconto": round(cheio - total, 2),
        "total": total,
        "lotes_em_cobranca": cobranca["lotes"],
        "em_cobranca": float(cobranca["total"]),
    }


# ⚠️ **Antes de `/{id_venda}`**, como `/sem-vinculo` e `/por-pessoa`: a rota com
# parâmetro engoliria "painel" e responderia 422.
@router.get("/painel")
def painel(inicio: date | None = None, fim: date | None = None,
           agrupar: str = "dia", ordem: str = "receita",
           limite: int = Query(20, ge=1, le=500),
           categorias: list[int] | None = Query(None),
           setores: list[int] | None = Query(None),
           produtos: list[int] | None = Query(None),
           ctx: Contexto = Depends(_ver)) -> dict:
    """O estudo de vendas de um recorte (pedido do dono, 21/10/2026).

    🔑 **Sem datas, abre no dia da ÚLTIMA venda**, como a faixa da tela inicial
    — de onde se chega aqui clicando. Um painel aberto num "hoje" ainda sem
    busca no PDV diria que a casa não vendeu.
    ⚠️ Até dois anos por recorte: além disso a pergunta já é de outro relatório.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        if inicio is None and fim is None:
            cur.execute("SELECT max(data) AS d FROM vendas WHERE id_unidade = %s "
                        "AND NOT cancelada AND NOT consumo_interno", (id_unidade,))
            ultimo = (cur.fetchone() or {}).get("d") or relogio.hoje_da_casa()
            inicio = fim = ultimo
        inicio = inicio or fim
        fim = fim or inicio
        if fim < inicio:
            raise HTTPException(status_code=400, detail="O fim do período vem antes do início.")
        if (fim - inicio).days > 731:
            raise HTTPException(status_code=400,
                                detail="O recorte passa de dois anos — estreite o período.")
        return painel_vendas.painel(cur, id_unidade, inicio, fim, agrupar, categorias,
                                    setores, produtos, ordem, limite)


@router.get("/{id_venda}")
def detalhe(id_venda: int, ctx: Contexto = Depends(_ver)) -> dict:
    """Uma venda inteira: cabeçalho, itens e o que cada item deixou.

    ⚠️ **O custo aqui é o CONGELADO no item**, não o custo de hoje. É ele que
    entrou no CMV teórico daquele dia, e recalcular na hora de mostrar faria a
    tela discordar do relatório — a diferença apareceria como variância sem
    causa. Item sem custo é item cujo prato não tem ficha; ele aparece dito
    assim, porque é o que explica um CMV teórico menor que o real.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT v.id, v.data, v.hora, v.origem, v.canal, v.documento, v.id_externo,
                      v.mesa, v.valor_total, v.desconto, v.cancelada, v.importada_em,
                      v.id_pessoa, v.cupom_base, v.cupom_desconto_pct, v.consumo_interno,
                      v.motivo, v.motivo_observacao, v.id_motivo_perda,
                      pm.nome AS motivo_perda,
                      f.nome AS pessoa,
                      u.nome AS usuario
                 FROM vendas v
                 LEFT JOIN usuarios u ON u.id = v.id_usuario
                 LEFT JOIN fornecedores f ON f.id = v.id_pessoa
                 LEFT JOIN perda_motivos pm ON pm.id = v.id_motivo_perda
                WHERE v.id = %s AND v.id_unidade = %s""",
            (id_venda, id_unidade),
        )
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")

        cur.execute(
            """SELECT vi.id, vi.codigo_pdv, vi.descricao_pdv, vi.id_produto,
                      vi.quantidade, vi.valor_unitario, vi.valor_total,
                      -- 🔑 O preço de tabela da linha. NULO quando a política
                      -- não a tocou, e aí o cheio É o cobrado — a tela cai
                      -- nele em vez de mostrar uma coluna vazia.
                      vi.valor_unitario_cheio,
                      vi.custo_ficha_unitario, vi.origem_custo,
                      p.nome AS produto, p.nome_curto AS produto_curto,
                      p.codigo AS produto_codigo, p.tipo,
                      c.nome AS categoria, s.nome AS setor
                 FROM venda_itens vi
                 LEFT JOIN produtos p ON p.id = vi.id_produto
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                WHERE vi.id_venda = %s
                ORDER BY vi.id""",
            (id_venda,),
        )
        itens = [dict(r) for r in cur.fetchall()]

        # Os movimentos de estoque que esta venda causou — a prova de que ela
        # saiu da prateleira, e o que o estorno devolveu quando foi cancelada.
        #
        # ⚠️ **O estorno NÃO se acha pela origem da venda.** Ele nasce com
        # `origem_tipo = 'ESTORNO'` e `origem_id` apontando para o movimento que
        # desfaz, não para a venda — procurar só por `origem_tipo = 'VENDA'`
        # mostrava a saída e escondia a devolução, e a tela de uma venda
        # cancelada dizia que o produto tinha saído e nunca voltado. A segunda
        # perna do OR é o que fecha o par.
        cur.execute(
            """WITH da_venda AS (
                   SELECT id FROM estoque_movimentos
                    WHERE origem_tipo = 'VENDA' AND origem_id = %s
               )
               SELECT m.id, m.id_produto, m.tipo, m.quantidade, m.custo_total,
                      m.data_movimento, m.id_estorno_de, p.nome AS produto, l.nome AS local
                 FROM estoque_movimentos m
                 JOIN produtos p ON p.id = m.id_produto
                 LEFT JOIN locais_estoque l ON l.id = m.id_local
                WHERE m.id IN (SELECT id FROM da_venda)
                   OR m.id_estorno_de IN (SELECT id FROM da_venda)
                ORDER BY m.id""",
            (id_venda,),
        )
        movimentos = [dict(r) for r in cur.fetchall()]

        # 🔑 Se aceita item novo, e por que não (20/10/2026) — a regra é do servidor.
        # 🔑 E o lote de cobrança em que ela está (22/10/2026), para a tela dizer.
        cur.execute(
            """SELECT v.id_consumo_lote, l.status AS lote_status
                 FROM vendas v LEFT JOIN consumo_lotes l ON l.id = v.id_consumo_lote
                WHERE v.id = %s""",
            (id_venda,))
        do_lote = dict(cur.fetchone() or {})
        por_que_nao = _por_que_nao_edita(cur, id_unidade, dict(venda) | do_lote)
        # 🔑 E se aceita trocar data e número (23/10/2026) — regra diferente da do item.
        por_que_nao_altera = _por_que_nao_altera(cur, id_unidade, dict(venda) | do_lote)

    custo = sum(float(i["quantidade"]) * float(i["custo_ficha_unitario"] or 0) for i in itens)
    receita = sum(float(i["valor_total"] or 0) for i in itens)
    return {
        **dict(venda),
        **do_lote,
        "pode_acrescentar": por_que_nao is None,
        "por_que_nao_acrescenta": por_que_nao,
        "pode_alterar": por_que_nao_altera is None,
        "por_que_nao_altera": por_que_nao_altera,
        "itens": itens,
        "movimentos": movimentos,
        "receita": receita,
        # ⚠️ O custo teórico só vale a soma quando TODO item tem ficha. Com um
        # item sem custo, a margem sairia alta demais e pareceria um resultado
        # excelente — por isso a tela recebe a contagem e diz "parcial".
        "custo_teorico": custo,
        "itens_sem_custo": sum(1 for i in itens if i["custo_ficha_unitario"] is None),
        "itens_sem_vinculo": sum(1 for i in itens if i["id_produto"] is None),
        # 🔑 **Custo que veio de ficha em RASCUNHO é um número, não um buraco —
        # mas ele ainda pode mudar.** Sem esta contagem, o custo de uma receita
        # não homologada seria indistinguível do de uma aprovada. É a mesma
        # razão do `itens_sem_custo`: o número entra na conta, e quem lê precisa
        # saber de onde ele veio.
        "itens_ficha_rascunho": sum(
            1 for i in itens if (i["origem_custo"] or "").startswith("ficha_rascunho")),
    }
