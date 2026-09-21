"""Catálogos — o cabeçalho do que a casa publica para o cliente.

🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de catálogos.
Onde teremos o cabeçalho do catálogo, origem — neste momento somente vamos ter
PDF —, o nome dele no site do cliente, o período de publicação, a situação:
rascunho, ativo, inativo."*

🔑 **O catálogo pertence a RESERVAS** (correção do dono no mesmo dia: *"o menu de
catálogo fica dentro de reservas, onde somente será demonstrada quando utilizado
reserva"*). A porta é a mesma da migração 068: enquanto `reservas_ligado`
estiver desligado nesta loja, o menu não mostra o item e **estas rotas
recusam** — as duas coisas, não só a primeira.
⚠️ **A trava do servidor não é redundância da do menu.** Esconder o item é
conforto; o que impede uma casa sem reservas de ganhar catálogo é a recusa aqui.

⚠️ **É a CAPA, e só ela.** Os itens do catálogo são a próxima fatia.

🔑 **Cada rota declara a permissão que exige** — regra da casa, nada de checagem
só na tela. `catalogos.ver` para ler, `catalogos.editar` para mexer.

⚠️ **Toda consulta passa por `unidade_atual`**, e não é zelo: o catálogo é de
cada loja, e uma rota que esquecesse o filtro deixaria a filial alterar o
cardápio da matriz. É a lição que `listar_fechamentos` do CMV pagou.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

import arquivos
import auditoria
from database import get_cursor
from models.catalogos import (
    CatalogoCreate, CatalogoResponse, CatalogoUpdate, ORIGENS, SITUACOES,
)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import catalogos as servico
from services import reservas as reservas_servico

router = APIRouter(prefix="/catalogos", tags=["catálogos"])

_VER = requer_permissao("catalogos.ver")
_EDITAR = requer_permissao("catalogos.editar")


def _unidade(cur, ctx: Contexto) -> int:
    """A loja atual — desde que ela tenha Reservas ligado.

    ⚠️ **409, não 403**: não é falta de permissão, é módulo desligado. A frase
    diz onde se liga, como a de Reservas — recusar sem dizer o caminho manda a
    pessoa procurar num menu que, justamente, não mostra o item.
    """
    id_unidade = unidade_atual(cur, ctx)
    if not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(
            status_code=409,
            detail=("O catálogo é do site de reservas, e o módulo de Reservas não está "
                    "ligado nesta loja. Ligue em Administração → Lojas, no parâmetro "
                    "Reservas."),
        )
    return id_unidade


# ⚠️ **`/opcoes` é declarado ANTES de `/{id_catalogo}`**: o FastAPI casa rotas
# na ordem de declaração, e com o parâmetro na frente "opcoes" viraria o id de
# um catálogo que não existe — 422 por um caminho que deveria funcionar.
@router.get("/opcoes")
def opcoes(ctx: Contexto = Depends(_VER)) -> dict:
    """O vocabulário do cadastro, dito pelo SERVIDOR.

    🔑 **Para a tela não manter a segunda cópia da lista.** É a mesma lição das
    três listas de `TIPOS` que divergiram caladas: a tela ofereceria uma origem
    que o servidor recusa, e nada denunciaria até alguém salvar.
    """
    with get_cursor() as cur:
        _unidade(cur, ctx)
    return {"origens": list(ORIGENS), "situacoes": list(SITUACOES)}


@router.get("", response_model=list[CatalogoResponse])
def listar(
    situacao: str | None = Query(default=None),
    ctx: Contexto = Depends(_VER),
) -> list[dict]:
    with get_cursor() as cur:
        return servico.listar(cur, _unidade(cur, ctx), situacao)


@router.get("/{id_catalogo}", response_model=CatalogoResponse)
def obter(id_catalogo: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.obter(cur, _unidade(cur, ctx), id_catalogo)


@router.post("", status_code=201, response_model=CatalogoResponse)
def criar(body: CatalogoCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        novo = servico.criar(cur, id_unidade, body.model_dump(), ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo", novo["id"], "criar",
                            depois=body.model_dump(mode="json"), id_unidade=id_unidade)
        return novo


@router.put("/{id_catalogo}", response_model=CatalogoResponse)
def atualizar(id_catalogo: int, body: CatalogoUpdate,
              ctx: Contexto = Depends(_EDITAR)) -> dict:
    """⚠️ `exclude_unset`: campo ausente não é campo nulo — ver o service."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        dados = body.model_dump(exclude_unset=True)
        depois = servico.atualizar(cur, id_unidade, id_catalogo, dados)
        # 🔑 **Publicar é o que muda o que o cliente vê**, então a situação fica
        # na auditoria com o antes e o depois. Um catálogo que saiu do ar sem
        # ninguém saber quem tirou é a pergunta que a auditoria existe para
        # responder.
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "alterar",
            antes={k: str(antes.get(k)) for k in dados if k in antes},
            depois={k: str(depois.get(k)) for k in dados if k in depois},
            id_unidade=id_unidade)
        return depois


@router.post("/{id_catalogo}/arquivo", response_model=CatalogoResponse)
async def enviar_arquivo(id_catalogo: int, arquivo: UploadFile = File(...),
                         ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Carrega o PDF que o site de reservas vai exibir.

    🔑 **Pedido do dono (21/09/2026):** *"criei o catálogo, agora tenho que
    poder carregar o PDF, neste caso para ele ser exibido."*

    ⚠️ **Os bytes são lidos ANTES de pedir a conexão.** Até 10 MB vindos pela
    rede com uma transação aberta prenderiam uma conexão do pool durante todo o
    envio — é a mesma razão pela qual `ler_pdf` é separado de `gravar`.

    ⚠️ **Substitui o anterior**, se houver: um catálogo tem UM arquivo, e a
    troca do cardápio é rotina. O antigo é apagado na mesma transação, depois de
    o registro já apontar para o novo.
    """
    conteudo, tipo, extensao = await arquivos.ler_pdf(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        depois = servico.guardar_arquivo(
            cur, id_unidade, id_catalogo, conteudo, tipo, extensao, arquivo.filename)
        # 🔑 **O arquivo é o que o cliente vê.** Trocá-lo muda o cardápio
        # publicado sem mexer em campo nenhum da capa — a auditoria é o único
        # lugar onde isso fica registrado.
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "enviar_arquivo",
            antes={"arquivo_nome": antes.get("arquivo_nome")},
            depois={"arquivo_nome": depois.get("arquivo_nome"),
                    "bytes": depois.get("arquivo_bytes")},
            id_unidade=id_unidade)
        return depois


@router.delete("/{id_catalogo}/arquivo", response_model=CatalogoResponse)
def remover_arquivo(id_catalogo: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Tira o PDF — o catálogo continua, sem arquivo.

    ⚠️ **Declarada ANTES de `DELETE /{id_catalogo}`**, como `/opcoes`: o FastAPI
    casa rotas na ordem, e o caminho mais específico precisa vir primeiro.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        depois = servico.remover_arquivo(cur, id_unidade, id_catalogo)
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "remover_arquivo",
            antes={"arquivo_nome": antes.get("arquivo_nome")},
            id_unidade=id_unidade)
        return depois


@router.delete("/{id_catalogo}")
def excluir(id_catalogo: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """⚠️ Só rascunho se apaga — o resto se inativa. A regra mora no service."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        r = servico.excluir(cur, id_unidade, id_catalogo)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo", id_catalogo, "excluir",
                            antes={"nome": antes["nome"], "situacao": antes["situacao"]},
                            id_unidade=id_unidade)
        return r
