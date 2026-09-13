"""Fichas técnicas.

Duas regras de acesso que valem a pena ler antes de mexer:

1. **Ver a ficha e ver o custo são permissões diferentes.** Sem `fichas.custos`,
   nenhum campo de dinheiro sai daqui — não é só a tela que esconde.
2. **Ficha homologada não se edita.** Alterar receita publicada mudaria o custo
   histórico. Quem quer mudar cria uma nova versão.
3. 🔑 **A FOTO é a exceção da regra 2, e por um motivo prático:** o prato só
   pode ser fotografado depois de feito, e ele é feito depois de a ficha ser
   homologada. Exigir uma versão nova para pendurar a foto criaria uma versão
   que não difere em nada — e cada versão carrega histórico de custo. É o mesmo
   raciocínio do nome do inventário, editável com a contagem fechada: rótulo
   não mexe em item nem em razão.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

import arquivos
import auditoria
from database import get_cursor
from paginacao import com_total
from models.fichas import (FichaCreate, FichaDuplicar, FichaResponse, FichaResumo,
                           FichaUpdate, ItemFicha, LocaisDaFichaRequest,
                           RendimentoSugerido)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import custos

router = APIRouter(prefix="/fichas", tags=["fichas técnicas"])

# Ver a ficha: qualquer um dos dois níveis serve.
_ver = requer_permissao("fichas.visualizar", "fichas.editar")


def _num(v):
    """Decimal/None → float/None, só na borda da API."""
    return None if v is None else float(v)


def _gravar_itens(cur, id_ficha: int, itens: list[ItemFicha]) -> None:
    cur.execute("DELETE FROM ficha_itens WHERE id_ficha = %s", (id_ficha,))
    for ordem, item in enumerate(itens):
        if bool(item.id_insumo) == bool(item.id_subficha):
            raise HTTPException(
                status_code=400,
                detail="Cada linha da ficha aponta para um insumo OU uma sub-ficha.",
            )
        if item.id_subficha == id_ficha:
            raise HTTPException(status_code=400, detail="Uma ficha não pode usar a si mesma.")

        # Fator de correção: se vieram bruta e líquida, ele é a divisão das duas.
        fc = item.fator_correcao
        if item.qtd_liquida:
            fc = round(item.qtd_bruta / item.qtd_liquida, 4) or 1

        cur.execute(
            """INSERT INTO ficha_itens (id_ficha, id_insumo, id_subficha, qtd_bruta,
                                        qtd_liquida, um, fator_correcao, fator_coccao,
                                        observacao, ordem)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (id_ficha, item.id_insumo, item.id_subficha, item.qtd_bruta, item.qtd_liquida,
             item.um, fc, item.fator_coccao, item.observacao, item.ordem or ordem),
        )

    # Só depois de gravar dá para provar que a árvore continua sem ciclo.
    if id_ficha in custos.descendentes_da_ficha(cur, id_ficha):
        raise HTTPException(
            status_code=400,
            detail="Essa combinação faz a ficha usar a si mesma por dentro de uma sub-ficha.",
        )


def _travar_se_homologada(status: str) -> None:
    if status == "HOMOLOGADA":
        raise HTTPException(
            status_code=400,
            detail="Ficha homologada não é editável — crie uma nova versão para mudar a receita.",
        )


@router.get("", response_model=list[FichaResumo])
def listar(
    id_produto: int | None = None,
    status: str | None = None,
    busca: str | None = Query(default=None, max_length=80),
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(_ver),
) -> list[dict]:
    ve_custo = ctx.pode("fichas.custos")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.id, f.id_produto, p.nome AS produto, p.codigo, f.versao, f.status,
                   f.rendimento_qtd, f.rendimento_um, f.porcoes, f.criado_em AS atualizada_em,
                   f.foto_url,
                   (SELECT count(*) FROM ficha_itens i WHERE i.id_ficha = f.id) AS itens,
                   count(*) OVER () AS _total
              FROM fichas_tecnicas f
              JOIN produtos p ON p.id = f.id_produto
             WHERE (%s::int IS NULL OR f.id_produto = %s)
               AND (%s::varchar IS NULL OR f.status = %s)
               AND (%s::varchar IS NULL OR lower(p.nome) LIKE lower('%%' || %s || '%%'))
             ORDER BY lower(p.nome), f.versao DESC
             LIMIT %s OFFSET %s
            """,
            (id_produto, id_produto, status, status, busca, busca, limite, offset),
        )
        fichas = [dict(r) for r in cur.fetchall()]
        com_total(fichas, resposta, offset)

        for f in fichas:
            f["rendimento_qtd"] = _num(f["rendimento_qtd"])
            f["porcoes"] = _num(f["porcoes"])
            if ve_custo:
                c = custos.custo_da_ficha(cur, f["id"])
                f["custo_total"] = _num(c["custo_total"])
                f["custo_por_porcao"] = _num(c["custo_por_porcao"])
                f["custo_completo"] = c["completo"]
    return fichas


@router.get("/{id_ficha}", response_model=FichaResponse)
def obter(id_ficha: int, ctx: Contexto = Depends(_ver)) -> dict:
    ve_custo = ctx.pode("fichas.custos")
    with get_cursor() as cur:
        cur.execute(
            """SELECT f.*, p.nome AS produto, p.codigo, u.nome AS homologada_por_nome
                 FROM fichas_tecnicas f
                 JOIN produtos p ON p.id = f.id_produto
                 LEFT JOIN usuarios u ON u.id = f.homologada_por
                WHERE f.id = %s""",
            (id_ficha,),
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        ficha = dict(f)
        # Os destinos com rendimento próprio (migração 066). Lista vazia é o caso
        # de quase toda ficha: sem linha, vale o rendimento dela.
        cur.execute(
            """SELECT fl.id_local, l.nome AS local, fl.rendimento_qtd, fl.porcoes,
                      fl.porcao_qtd, fl.observacao
                 FROM ficha_locais fl
                 JOIN locais_estoque l ON l.id = fl.id_local
                WHERE fl.id_ficha = %s ORDER BY l.nome""",
            (id_ficha,),
        )
        locais = [{**dict(r), "rendimento_qtd": _num(r["rendimento_qtd"]),
                   "porcoes": _num(r["porcoes"]), "porcao_qtd": _num(r["porcao_qtd"])}
                  for r in cur.fetchall()]
        calculo = custos.custo_da_ficha(cur, id_ficha)

    itens = []
    for i in calculo["itens"]:
        item = {
            "id": i["id"],
            "id_insumo": i["id_insumo"],
            "id_subficha": i["id_subficha"],
            "nome": i["nome"],
            "codigo": i["codigo"],
            "qtd_bruta": _num(i["qtd_bruta"]),
            "qtd_liquida": _num(i["qtd_liquida"]),
            "um": i["um"],
            "fator_correcao": _num(i["fator_correcao"]),
            "fator_coccao": _num(i["fator_coccao"]),
            "observacao": i["observacao"],
            "ordem": i["ordem"],
            "aviso": i["aviso"],
            # Quanto isto vira na unidade do ESTOQUE: a receita pede 1 CX e o
            # razão baixa 12 PCT. Sem mostrar, a divergência só aparece no
            # inventário do fim do mês.
            "qtd_estoque": _num(i.get("qtd_estoque")),
            "conversao": i.get("conversao"),
            "um_estoque": i.get("um_estoque"),
        }
        if ve_custo:
            # Sem esta chave o dinheiro nem sai do servidor.
            item["custo_unitario"] = _num(i["custo_unitario"])
            item["custo_total"] = _num(i["custo_total"])
            item["origem_custo"] = i["origem_custo"]
        itens.append(item)

    resposta = {
        "id": ficha["id"],
        "id_produto": ficha["id_produto"],
        "produto": ficha["produto"],
        "codigo": ficha["codigo"],
        "versao": ficha["versao"],
        "status": ficha["status"],
        "rendimento_qtd": _num(ficha["rendimento_qtd"]),
        "rendimento_um": ficha["rendimento_um"],
        "porcoes": _num(ficha["porcoes"]),
        # ⚠️ **A resposta e montada campo por campo.** `SELECT f.*` traz a coluna
        # nova, mas quem nao entra nesta lista nao sai na API — e o sintoma e o
        # pior possivel: grava certo e volta nulo. Custou uma suite inteira
        # acusando o INSERT, que estava correto.
        "porcao_qtd": _num(ficha["porcao_qtd"]),
        "locais": locais,
        "tempo_preparo_min": ficha["tempo_preparo_min"],
        "modo_preparo": ficha["modo_preparo"],
        "alergenos": ficha["alergenos"],
        "observacao": ficha["observacao"],
        "vigente_de": ficha["vigente_de"],
        "vigente_ate": ficha["vigente_ate"],
        "homologada_em": ficha["homologada_em"],
        "homologada_por": ficha["homologada_por_nome"],
        "criado_em": ficha["criado_em"],
        "foto_url": ficha["foto_url"],
        "itens": itens,
        "ve_custo": ve_custo,
    }
    if ve_custo:
        resposta |= {
            "custo_total": _num(calculo["custo_total"]),
            "custo_por_porcao": _num(calculo["custo_por_porcao"]),
            "custo_por_unidade_rendimento": _num(calculo["custo_por_unidade_rendimento"]),
            "itens_sem_custo": calculo["itens_sem_custo"],
            "custo_completo": calculo["completo"],
        }
    return resposta


@router.post("", status_code=201)
def criar(body: FichaCreate, ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT nome, tipo, producao_propria FROM produtos WHERE id = %s", (body.id_produto,)
        )
        produto = cur.fetchone()
        if not produto:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        if produto["tipo"] not in ("PRODUZIDO", "KIT"):
            raise HTTPException(
                status_code=400,
                detail="Ficha técnica é de produto produzido ou kit. Ajuste o tipo do produto.",
            )

        cur.execute(
            "SELECT coalesce(max(versao), 0) + 1 AS proxima FROM fichas_tecnicas WHERE id_produto = %s",
            (body.id_produto,),
        )
        versao = cur.fetchone()["proxima"]

        cur.execute(
            """INSERT INTO fichas_tecnicas (id_produto, versao, rendimento_qtd, rendimento_um,
                                            porcoes, porcao_qtd, tempo_preparo_min, modo_preparo,
                                            alergenos, observacao, criado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (body.id_produto, versao, body.rendimento_qtd, body.rendimento_um, body.porcoes,
             body.porcao_qtd, body.tempo_preparo_min, body.modo_preparo, body.alergenos,
             body.observacao, ctx.id_usuario),
        )
        nova = cur.fetchone()["id"]
        _gravar_itens(cur, nova, body.itens)

        # Produto com ficha é produto de produção própria — deixa coerente aqui.
        if not produto["producao_propria"]:
            cur.execute(
                "UPDATE produtos SET producao_propria = true WHERE id = %s", (body.id_produto,)
            )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", nova, "criar",
                            depois={"produto": produto["nome"], "versao": versao,
                                    "itens": len(body.itens)})
    return {"id": nova, "versao": versao, "message": "Ficha criada"}


@router.put("/{id_ficha}")
def atualizar(id_ficha: int, body: FichaUpdate,
              ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    itens = dados.pop("itens", None)
    with get_cursor() as cur:
        cur.execute(
            """SELECT status, rendimento_qtd, rendimento_um, porcoes, porcao_qtd
                 FROM fichas_tecnicas WHERE id = %s""",
            (id_ficha,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        _travar_se_homologada(antes["status"])

        if dados:
            sets = ", ".join(f"{c} = %s" for c in dados)
            cur.execute(
                f"UPDATE fichas_tecnicas SET {sets} WHERE id = %s", [*dados.values(), id_ficha]
            )
        if itens is not None:
            _gravar_itens(cur, id_ficha, body.itens or [])
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "atualizar",
                            antes=dict(antes), depois=dados)
    return {"message": "Ficha salva"}


@router.post("/{id_ficha}/homologar")
def homologar(id_ficha: int,
              ctx: Contexto = Depends(requer_permissao("fichas.homologar"))) -> dict:
    """Publica a versão. A anterior é encerrada no mesmo instante."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_produto, status, versao FROM fichas_tecnicas WHERE id = %s", (id_ficha,)
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        if f["status"] == "HOMOLOGADA":
            raise HTTPException(status_code=400, detail="Esta versão já está homologada")

        cur.execute("SELECT count(*) AS n FROM ficha_itens WHERE id_ficha = %s", (id_ficha,))
        if not cur.fetchone()["n"]:
            raise HTTPException(status_code=400, detail="Ficha sem itens não pode ser homologada")

        cur.execute(
            """UPDATE fichas_tecnicas
                  SET status = 'ARQUIVADA', vigente_ate = current_date
                WHERE id_produto = %s AND status = 'HOMOLOGADA' AND vigente_ate IS NULL""",
            (f["id_produto"],),
        )
        cur.execute(
            """UPDATE fichas_tecnicas
                  SET status = 'HOMOLOGADA', homologada_por = %s, homologada_em = now(),
                      vigente_de = current_date, vigente_ate = NULL
                WHERE id = %s""",
            (ctx.id_usuario, id_ficha),
        )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "homologar",
                            depois={"versao": f["versao"]})
    return {"message": "Ficha homologada"}


def _copiar_ficha(cur, f, id_produto: int, id_usuario: int | None) -> tuple[int, int]:
    """Copia cabeçalho, foto e itens para uma ficha NOVA do produto indicado.

    🔑 **Uma cópia só, para dois usos.** `nova-versao` copia para o MESMO produto
    e `duplicar` para outro — o resto é idêntico, e escrever duas vezes seria
    garantir que um dia uma delas esquecesse a foto ou o fator de correção.
    Devolve `(id, versao)`.
    """
    cur.execute(
        "SELECT coalesce(max(versao), 0) + 1 AS proxima FROM fichas_tecnicas WHERE id_produto = %s",
        (id_produto,),
    )
    versao = cur.fetchone()["proxima"]
    cur.execute(
        """INSERT INTO fichas_tecnicas (id_produto, versao, rendimento_qtd, rendimento_um,
                                        porcoes, porcao_qtd, tempo_preparo_min, modo_preparo,
                                        alergenos, observacao, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_produto, versao, f["rendimento_qtd"], f["rendimento_um"], f["porcoes"],
         f["porcao_qtd"], f["tempo_preparo_min"], f["modo_preparo"], f["alergenos"],
         f["observacao"], id_usuario),
    )
    nova = cur.fetchone()["id"]
    # 🔑 **A foto vem junto, e o ARQUIVO é copiado — não a URL.** A versão nova
    # quase sempre é a mesma receita com um ajuste, e o prato continua o mesmo:
    # nascer sem foto obrigaria a fotografar de novo a cada versão.
    # ⚠️ Copiar só a URL deixaria as duas apontando para o mesmo arquivo, cujo
    # dono é a versão VELHA — e trocar a foto de lá apagaria a daqui, sem
    # ninguém ter tocado nesta ficha. Na DUPLICAÇÃO isso vale em dobro: o bolo
    # de banana começa com a foto do de morango, e trocá-la não pode mexer no
    # prato do outro.
    nova_foto = arquivos.copiar(f["foto_url"], f"ficha-{nova}", cur)
    if nova_foto:
        cur.execute("UPDATE fichas_tecnicas SET foto_url = %s WHERE id = %s",
                    (nova_foto, nova))
    cur.execute(
        """INSERT INTO ficha_itens (id_ficha, id_insumo, id_subficha, qtd_bruta, qtd_liquida,
                                    um, fator_correcao, fator_coccao, observacao, ordem)
           SELECT %s, id_insumo, id_subficha, qtd_bruta, qtd_liquida, um, fator_correcao,
                  fator_coccao, observacao, ordem
             FROM ficha_itens WHERE id_ficha = %s""",
        (nova, f["id"]),
    )
    # ⚠️ **Os destinos vêm junto** (migração 066). A versão nova é a mesma receita
    # com um ajuste, e os rendimentos por prateleira são parte dela: nascer sem
    # eles faria a produção para a vitrine voltar ao rendimento da câmara, calada.
    cur.execute(
        """INSERT INTO ficha_locais (id_ficha, id_local, rendimento_qtd, porcoes,
                                     porcao_qtd, observacao)
           SELECT %s, id_local, rendimento_qtd, porcoes, porcao_qtd, observacao
             FROM ficha_locais WHERE id_ficha = %s""",
        (nova, f["id"]),
    )
    return nova, versao


@router.put("/{id_ficha}/locais")
def gravar_locais(id_ficha: int, body: LocaisDaFichaRequest,
                  ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Os destinos desta receita, com o rendimento de cada um.

    🔑 **Pedido do dono (12/09/2026):** *"dentro da ficha técnica podemos ter os
    locais e informar rendimentos e porções por local, e ao programar a produção
    seleciona qual local será produzido"*. A massa que vai à vitrine passa pelo
    forno: o mesmo lote de ingredientes não rende o mesmo tanto.

    ⚠️ **Substitui a tabela inteira**, como `PUT /produtos/{id}/unidades` — as duas
    telas fazem a mesma coisa e é melhor que se pareçam.

    ⚠️ **Ficha homologada NÃO é editável**, e isto é receita: o rendimento divide
    o consumo, então mexer nele numa ficha publicada mudaria o custo já apurado.
    É a mesma trava dos itens.

    ⚠️ **O local tem de ser desta loja e estar ativo** — rendimento apontando para
    prateleira de outra unidade seria um número que nunca valeria para ninguém.
    """
    with get_cursor() as cur:
        cur.execute("SELECT status FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        _travar_se_homologada(f["status"])

        id_unidade = unidade_atual(cur, ctx)
        vistos: set[int] = set()
        for item in body.itens:
            if item.id_local in vistos:
                raise HTTPException(
                    status_code=400,
                    detail="A mesma prateleira aparece duas vezes — some num destino só.",
                )
            vistos.add(item.id_local)
            cur.execute(
                """SELECT nome FROM locais_estoque
                    WHERE id = %s AND id_unidade = %s AND ativo""",
                (item.id_local, id_unidade),
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="Prateleira não encontrada nesta loja, ou inativa.",
                )

        cur.execute("DELETE FROM ficha_locais WHERE id_ficha = %s", (id_ficha,))
        for item in body.itens:
            cur.execute(
                """INSERT INTO ficha_locais (id_ficha, id_local, rendimento_qtd, porcoes,
                                             porcao_qtd, observacao)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (id_ficha, item.id_local, item.rendimento_qtd, item.porcoes,
                 item.porcao_qtd, item.observacao),
            )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "locais",
                            depois={"destinos": len(body.itens)})
    return {"message": (f"{len(body.itens)} destino(s) gravado(s)" if body.itens
                        else "Destinos removidos — vale o rendimento da ficha")}


@router.post("/rendimento-sugerido")
def previa_do_rendimento(
        body: RendimentoSugerido,
        ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Quanto esta receita rende, somando os ingredientes — ANTES de gravar.

    🔑 **Pedido do dono (12/09/2026):** *"de onde vem o rendimento da receita? tem
    como ser gerada automaticamente? o sistema que a cliente utiliza soma todos os
    ingredientes e gera isto automaticamente"*.

    ⚠️ **Recebe os ITENS, não um id de ficha**, de propósito: a tela precisa do
    número enquanto a pessoa monta a receita, e numa ficha nova não há nada
    gravado para consultar. Sem estado, serve aos dois casos com uma rota só.

    ⚠️ **A conta NÃO é escrita aqui.** Ela mora em `custos.rendimento_sugerido`,
    junto do conversor de unidades — a regra de conversão do sistema é uma só, e
    uma segunda cópia num router divergiria dela no primeiro ajuste.

    ⚠️ **Nada é gravado, e é isso que faz o recurso ser seguro**: `rendimento_qtd`
    DIVIDE o consumo na produção (`lotes = quantidade ÷ rendimento`), então
    recalcular sozinho mudaria o custo unitário de tudo que a ficha produz, calado.
    A tela sugere; quem decide é quem lê.
    """
    with get_cursor() as cur:
        return custos.rendimento_sugerido(
            cur, [i.model_dump() for i in body.itens], body.um)


@router.post("/{id_ficha}/nova-versao", status_code=201)
def nova_versao(id_ficha: int,
                ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Copia a ficha para uma versão nova em rascunho — a publicada segue no ar."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        nova, versao = _copiar_ficha(cur, f, f["id_produto"], ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "ficha", nova, "nova_versao",
                            antes={"copiada_de": id_ficha}, depois={"versao": versao})
    return {"id": nova, "versao": versao, "message": f"Versão {versao} criada em rascunho"}


@router.post("/{id_ficha}/duplicar", status_code=201)
def duplicar(id_ficha: int, body: FichaDuplicar,
             ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """A mesma receita, para OUTRO produto — e depois se ajusta o que difere.

    🔑 **Pedido do dono (12/09/2026):** *"tenho Bolo de Morango e Bolo de Banana,
    a base da receita é a mesma, então gostaria de duplicar e ajustar, retirando
    o que não vai e adicionando o que precisa"*. Sem isto a segunda receita era
    redigitada item por item — e é aí que uma entra com 200 G de farinha e a
    outra com 250, sem ninguém ter decidido nada.

    ⚠️ **Nasce em RASCUNHO, sempre.** Cópia é ponto de partida, não receita
    aprovada: homologar continua sendo um ato separado.
    ⚠️ **O destino pode já ter ficha.** A cópia entra como a versão seguinte, em
    rascunho, e a vigente continua valendo até alguém homologar a nova — mesma
    regra de `nova-versao`, e não há por que inventar outra aqui.
    """
    with get_cursor() as cur:
        cur.execute("SELECT * FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")

        cur.execute("SELECT nome, tipo, producao_propria FROM produtos WHERE id = %s",
                    (body.id_produto,))
        destino = cur.fetchone()
        if not destino:
            raise HTTPException(status_code=404, detail="Produto de destino não encontrado")
        # A MESMA regra de quem cria ficha do zero: ficha é de produzido ou kit.
        if destino["tipo"] not in ("PRODUZIDO", "KIT"):
            raise HTTPException(
                status_code=400,
                detail="Ficha técnica é de produto produzido ou kit. Ajuste o tipo do produto.",
            )

        # ⚠️ **A receita não pode virar ingrediente de si mesma.** Se a ficha
        # copiada usa uma sub-ficha DO PRODUTO DE DESTINO, a cópia nasceria
        # dizendo que o bolo leva bolo. Não é ciclo de estrutura — as duas fichas
        # são objetos diferentes, e `descendentes_da_ficha` não acusaria nada —,
        # então a checagem tem de ser esta, olhando o produto por trás da
        # sub-ficha.
        cur.execute(
            """SELECT p.nome
                 FROM ficha_itens fi
                 JOIN fichas_tecnicas sf ON sf.id = fi.id_subficha
                 JOIN produtos p ON p.id = sf.id_produto
                WHERE fi.id_ficha = %s AND sf.id_produto = %s
                LIMIT 1""",
            (id_ficha, body.id_produto),
        )
        propria = cur.fetchone()
        if propria:
            raise HTTPException(
                status_code=400,
                detail=(f"Esta receita usa {propria['nome']} como ingrediente. Duplicá-la "
                        f"para {destino['nome']} criaria uma receita que se usa a si mesma."),
            )

        cur.execute("SELECT count(*) AS n FROM fichas_tecnicas WHERE id_produto = %s",
                    (body.id_produto,))
        tinha = cur.fetchone()["n"]
        nova, versao = _copiar_ficha(cur, f, body.id_produto, ctx.id_usuario)

        # Produto com ficha é produto de produção própria — a mesma coerência que
        # `criar` mantém. Sem isto o bolo novo teria receita e não apareceria na
        # agenda de produção.
        if not destino["producao_propria"]:
            cur.execute("UPDATE produtos SET producao_propria = true WHERE id = %s",
                        (body.id_produto,))

        auditoria.registrar(cur, ctx.id_usuario, "ficha", nova, "duplicar",
                            antes={"copiada_de": id_ficha},
                            depois={"produto": destino["nome"], "versao": versao})
    fim = (f" A ficha que {destino['nome']} já tinha continua valendo até você homologar esta."
           if tinha else "")
    return {"id": nova, "versao": versao,
            "message": (f"Receita copiada para {destino['nome']} — versão {versao}, "
                        f"em rascunho.{fim}")}


@router.delete("/{id_ficha}")
def arquivar(id_ficha: int,
             ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    """Arquiva. Ficha usada por outra não some, senão o custo dela quebraria."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM ficha_itens WHERE id_subficha = %s", (id_ficha,)
        )
        if cur.fetchone()["n"]:
            raise HTTPException(
                status_code=409,
                detail="Esta ficha é usada como sub-ficha em outra. Remova o vínculo antes.",
            )
        cur.execute(
            """UPDATE fichas_tecnicas SET status = 'ARQUIVADA', vigente_ate = current_date
                WHERE id = %s""",
            (id_ficha,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "arquivar")
    return {"message": "Ficha arquivada"}


@router.post("/{id_ficha}/foto")
async def enviar_foto(
    id_ficha: int,
    arquivo: UploadFile = File(...),
    ctx: Contexto = Depends(requer_permissao("fichas.editar")),
) -> dict:
    """A foto do prato pronto — o que a cozinha compara com o que está na mão.

    🔑 **Não passa pelo `_travar_se_homologada`, e é deliberado.** A ficha
    homologada é congelada porque mexer nela mudaria custo histórico; a foto não
    entra em conta nenhuma. E o prato só existe para ser fotografado DEPOIS de
    homologado — a trava obrigaria a abrir uma versão que não difere em nada
    para pendurar uma imagem.

    ⚠️ Quem manda a foto precisa de `fichas.editar`. VER a foto segue a ficha:
    ela não é dinheiro, então `fichas.custos` não a esconde.
    """
    # Os bytes vêm antes da transação: ler 2 MB da rede com uma conexão do pool
    # presa é prendê-la pelo tempo do envio.
    conteudo, tipo, extensao = await arquivos.ler_enviada(arquivo)

    # 🔑 **Gravar a nova, apontar para ela e apagar a antiga é UMA transação.**
    # Antes eram três, e entre a segunda e a terceira a foto antiga já tinha
    # sido apagada com a ficha ainda apontando para ela — a imagem sumia da
    # tela e do PDF, sem volta.
    with get_cursor() as cur:
        cur.execute("SELECT foto_url FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")

        # ⚠️ O `dono` é a FICHA, não o produto: duas versões do mesmo prato podem
        # ter fotos diferentes, e é a montagem que muda entre elas.
        url = arquivos.gravar(cur, conteudo, tipo, extensao, f"ficha-{id_ficha}")
        cur.execute("UPDATE fichas_tecnicas SET foto_url = %s WHERE id = %s", (url, id_ficha))
        arquivos.remover(antes["foto_url"], cur)
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "foto",
                            antes={"foto_url": antes["foto_url"]}, depois={"foto_url": url})
    return {"foto_url": url, "message": "Foto atualizada"}


@router.delete("/{id_ficha}/foto")
def remover_foto(id_ficha: int,
                 ctx: Contexto = Depends(requer_permissao("fichas.editar"))) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT foto_url FROM fichas_tecnicas WHERE id = %s", (id_ficha,))
        atual = cur.fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        cur.execute("UPDATE fichas_tecnicas SET foto_url = NULL WHERE id = %s", (id_ficha,))
        auditoria.registrar(cur, ctx.id_usuario, "ficha", id_ficha, "foto_remover",
                            antes={"foto_url": atual["foto_url"]})
    # ⚠️ Fora da transação: apagar o arquivo é irreversível, e a linha do banco
    # tem de estar gravada antes. Mesma ordem da logo da empresa.
    arquivos.remover(atual["foto_url"])
    return {"message": "Foto removida"}
