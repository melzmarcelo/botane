"""Vendas — a outra metade do CMV.

Enquanto a API do PDV Legal não abre, a venda entra por planilha ou na mão. O
destino é o mesmo que a integração vai preencher, e o **custo da ficha é
congelado na importação**: o CMV teórico de março não muda quando alguém corrige
uma receita em abril.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from paginacao import pagina
from models.cmv import ImportarVendasRequest, PreviaCupomRequest, VendaResponse
from seguranca import Contexto, requer_permissao, unidade_atual
from services import cmv as motor
from services import consumo_pessoa as consumo
from services import consumo_periodo as ciclo
from services import estoque as motor_estoque
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
                      v.cancelada,
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

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)

        # 🔑 **Consumo de pessoa exige ciclo ABERTO** (pedido do dono,
        # 08/09/2026). O consumo so se lanca dentro de um ciclo: e nele que a
        # divida se acumula e por ele que ela se cobra.
        #
        # ⚠️ **A checagem e do SERVIDOR, e vale para todo caminho.** A tela de
        # lancamento avisa antes, mas ela nao e a unica porta: a importacao do
        # PDV chega aqui tambem. Uma venda com pessoa gravada fora de ciclo
        # ficaria em aberto para sempre, sem nunca aparecer num fechamento.
        #
        # ⚠️ Isto INVERTE a decisao de 04/09 ("o consumo nao espera o ciclo
        # existir"), a pedido de quem usa. O preco e o previsto la: sem ciclo
        # aberto, a casa para de registrar consumo de pessoa -- e a mensagem
        # abaixo precisa dizer exatamente o que fazer, ou vira um "nao deu".
        if any(v.id_pessoa for v in body.vendas) and not ciclo.periodo_aberto(cur, id_unidade):
            raise HTTPException(
                status_code=400,
                detail="Nao ha periodo de consumo aberto nesta loja. "
                       "Abra um periodo em Consumo antes de lancar venda com pessoa.",
            )

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
                                       cupom_base, cupom_desconto_pct, id_usuario)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (id_unidade, venda.data, venda.hora, venda.origem, venda.canal,
                 venda.documento, total, venda.desconto or 0, venda.cancelada,
                 venda.id_pessoa,
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
                id_produto = item.id_produto
                if not id_produto and item.codigo:
                    cur.execute(
                        "SELECT id FROM produtos WHERE lower(codigo) = lower(%s)", (item.codigo,)
                    )
                    achado = cur.fetchone()
                    id_produto = achado["id"] if achado else None
                if not id_produto and item.descricao:
                    # Último recurso: nome exato. Semelhança só sugere, nunca vincula.
                    cur.execute(
                        "SELECT id FROM produtos WHERE lower(nome) = lower(%s) AND ativo",
                        (item.descricao,),
                    )
                    achado = cur.fetchone()
                    id_produto = achado["id"] if achado else None

                custo, origem = (None, "sem_produto")
                if id_produto:
                    if id_produto not in custos_cache:
                        # 🔑 A loja vai junto: este custo é CONGELADO no item de
                        # venda. Calculado com o estoque das duas lojas, o erro
                        # fica gravado no CMV daquele mês, sem conserto.
                        custos_cache[id_produto] = motor.custo_teorico_do_produto(
                            cur, id_produto, id_unidade=id_unidade)
                    custo, origem = custos_cache[id_produto]
                else:
                    sem_vinculo += 1
                if custo is None:
                    sem_custo += 1
                if origem.startswith("ficha_rascunho"):
                    de_rascunho += 1

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
                itens_total += 1

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
                        """SELECT controla_estoque, id_local_padrao FROM produtos
                            WHERE id = %s""",
                        (id_produto,),
                    )
                    p_venda = cur.fetchone() or {}
                    if p_venda.get("controla_estoque"):
                        feito = agenda.producao_da_venda(
                            cur, id_unidade, id_produto, item.quantidade, ctx.id_usuario,
                            documento=venda.documento)
                        if feito:
                            produzidos_na_hora += 1
                        motor_estoque.lancar(
                            cur, id_unidade=id_unidade,
                            id_local=(feito or {}).get("id_local")
                                     or p_venda.get("id_local_padrao"),
                            id_produto=id_produto,
                            tipo="SAIDA_VENDA", quantidade=item.quantidade,
                            data_movimento=venda.data,
                            origem_tipo="VENDA", origem_id=id_venda,
                            documento=venda.documento, id_usuario=ctx.id_usuario,
                            observacao=("Produzido e vendido na hora" if feito
                                        else "Baixa da venda"),
                        )
                        baixados += 1

        auditoria.registrar(cur, ctx.id_usuario, "vendas", None, "importar",
                            depois={"vendas": importadas, "canceladas": canceladas,
                                    "itens": itens_total,
                                    "repetidas": repetidas, "sem_vinculo": sem_vinculo,
                                    "produzidos_na_hora": produzidos_na_hora,
                                    "baixados": baixados},
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
        "message": f"{importadas} venda(s) importada(s)"
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
        cur.execute("SELECT cancelada FROM vendas WHERE id = %s AND id_unidade = %s",
                    (id_venda, id_unidade))
        venda = cur.fetchone()
        if not venda:
            raise HTTPException(status_code=404, detail="Venda não encontrada")
        if venda["cancelada"]:
            raise HTTPException(status_code=400, detail="Esta venda já está cancelada.")

        cur.execute(
            """SELECT m.id FROM estoque_movimentos m
                WHERE m.origem_tipo = 'VENDA' AND m.origem_id = %s
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                   WHERE e.id_estorno_de = m.id)
                ORDER BY m.id DESC""",
            (id_venda,),
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
        cur.execute(
            """SELECT p.id AS id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                      p.id_local_padrao, l.nome AS local_destino,
                      count(*) AS itens, sum(vi.quantidade) AS quantidade,
                      min(v.data) AS desde, max(v.data) AS ate,
                      coalesce(sum(vi.quantidade * vi.custo_ficha_unitario), 0) AS custo
                 FROM venda_itens vi
                 JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                 JOIN produtos p ON p.id = vi.id_produto AND p.controla_estoque AND p.ativo
                 LEFT JOIN locais_estoque l ON l.id = p.id_local_padrao
                WHERE v.id_unidade = %s
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos m
                                   WHERE m.origem_tipo = 'VENDA' AND m.origem_id = v.id
                                     AND m.id_produto = vi.id_produto)
                GROUP BY p.id, p.codigo, p.nome, p.um_estoque, p.id_local_padrao, l.nome
                ORDER BY sum(vi.quantidade) DESC""",
            (id_unidade,),
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
        cur.execute(
            """SELECT vi.id, vi.id_produto, vi.quantidade, v.id AS id_venda, v.data,
                      v.documento, p.id_local_padrao
                 FROM venda_itens vi
                 JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                 JOIN produtos p ON p.id = vi.id_produto AND p.controla_estoque AND p.ativo
                WHERE v.id_unidade = %s
                  AND (%s::int IS NULL OR vi.id_produto = %s)
                  AND NOT EXISTS (SELECT 1 FROM estoque_movimentos m
                                   WHERE m.origem_tipo = 'VENDA' AND m.origem_id = v.id
                                     AND m.id_produto = vi.id_produto)
                ORDER BY v.data, v.id""",
            (id_unidade, id_produto, id_produto),
        )
        pendentes = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT id FROM locais_estoque WHERE id_unidade = %s AND ativo "
                    "ORDER BY principal DESC, id LIMIT 1", (id_unidade,))
        reserva = (cur.fetchone() or {}).get("id")
        baixados, recusados = 0, []
        for item in pendentes:
            try:
                motor_estoque.lancar(
                    cur, id_unidade=id_unidade,
                    id_local=item["id_local_padrao"] or reserva,
                    id_produto=item["id_produto"], tipo="SAIDA_VENDA",
                    quantidade=item["quantidade"], data_movimento=item["data"],
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


@router.get("/periodo-aberto")
def periodo_aberto(ctx: Contexto = Depends(_editar)) -> dict:
    """O ciclo de consumo em curso, ou nada.

    🔑 **Existe para a tela de lancamento avisar ANTES**, e nao depois de a
    pessoa montar o cupom inteiro e apertar salvar.

    ⚠️ Mora aqui, e nao em `/consumo`, por causa da chave: aquele router pede
    `consumo.periodos` ou `cmv.relatorios`, e quem lanca venda tem
    `cmv.fechamento` ou `cmv.painel`. Buscado la, o aviso daria 403 justamente
    para quem precisa dele. Aqui devolve so a existencia e as datas -- nenhum
    valor de ninguem.
    """
    with get_cursor() as cur:
        return {"aberto": ciclo.periodo_aberto(cur, unidade_atual(cur, ctx))}


# ⚠️ **`/{id_venda}` vem DEPOIS de `/sem-vinculo`, e a ordem é o que faz as duas
# funcionarem.** O FastAPI casa as rotas na ordem em que foram declaradas: com o
# parâmetro na frente, "sem-vinculo" viraria um id e o pedido morreria em 422
# antes de chegar à fila de de-para.
@router.get("/por-pessoa")
def por_pessoa(
    id_periodo: int | None = Query(default=None),
    id_pessoa: int | None = Query(default=None),
    detalhe: str = Query(default="sintetico", pattern="^(sintetico|analitico)$"),
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
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        periodo = None
        if id_periodo is not None:
            periodo = ciclo.por_id(cur, id_unidade, id_periodo)
            if not periodo:
                raise HTTPException(status_code=404, detail="Período não encontrado.")
        # ⚠️ A consulta mora no serviço porque a EXPORTAÇÃO usa a mesma: escrita
        # duas vezes, a tela e o arquivo entregue ao funcionário divergiriam
        # numa discussão sobre dinheiro.
        linhas = consumo.apurar(cur, id_unidade, periodo,
                                [id_pessoa] if id_pessoa else None, detalhe)
        return {
            # 🔑 **A tela recebe os ciclos junto com os dados.** Ela nao pode
            # busca-los em `/consumo/periodos`: aquele router pede
            # `consumo.periodos` ou `cmv.relatorios`, e este relatorio abre
            # tambem para `cmv.painel` -- quem entrasse por essa chave veria a
            # tela com o filtro vazio e nenhuma explicacao. Vindo daqui, as
            # opcoes sao exatamente as que este endpoint sabe atender.
            "periodo": periodo,
            "periodos": ciclo.para_escolher(cur, id_unidade),
            "detalhe": detalhe,
            "linhas": linhas,
            "total_cheio": round(sum(float(l["total_cheio"] or 0) for l in linhas), 2),
            "total": round(sum(float(l["total"] or 0) for l in linhas), 2),
            "desconto": round(
                sum(float(l["total_cheio"] or 0) - float(l["total"] or 0) for l in linhas), 2),
        }


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
                      v.id_pessoa, v.cupom_base, v.cupom_desconto_pct,
                      f.nome AS pessoa,
                      u.nome AS usuario
                 FROM vendas v
                 LEFT JOIN usuarios u ON u.id = v.id_usuario
                 LEFT JOIN fornecedores f ON f.id = v.id_pessoa
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
               SELECT m.id, m.tipo, m.quantidade, m.custo_total, m.data_movimento,
                      m.id_estorno_de, p.nome AS produto, l.nome AS local
                 FROM estoque_movimentos m
                 JOIN produtos p ON p.id = m.id_produto
                 LEFT JOIN locais_estoque l ON l.id = m.id_local
                WHERE m.id IN (SELECT id FROM da_venda)
                   OR m.id_estorno_de IN (SELECT id FROM da_venda)
                ORDER BY m.id""",
            (id_venda,),
        )
        movimentos = [dict(r) for r in cur.fetchall()]

    custo = sum(float(i["quantidade"]) * float(i["custo_ficha_unitario"] or 0) for i in itens)
    receita = sum(float(i["valor_total"] or 0) for i in itens)
    return {
        **dict(venda),
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
