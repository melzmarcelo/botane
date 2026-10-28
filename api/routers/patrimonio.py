"""Patrimônio — os bens da casa, a plaqueta com QR, a importação da planilha e a manutenção.

🔑 **Pedido do dono (27/10/2026)**: etapas 1 e 2 da proposta (cadastro com plaqueta e
importação; manutenção com plano, histórico e alertas). A regra mora em
`services/patrimonio.py`; a planilha em `services/patrimonio_planilha.py`.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

import auditoria
from database import get_cursor
from models.patrimonio import (Bem, BemParcial, ConferenciaAbrir, ConferenciaFechar,
                                Leitura, Manutencao)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import patrimonio as servico
from services import patrimonio_planilha as planilha
from services import patrimonio_conferencia as conferencia
from services import patrimonio_valor as valor_servico

router = APIRouter(prefix="/patrimonio", tags=["Patrimônio"])

_VER = requer_permissao("patrimonio.ver", "patrimonio.cadastrar", "patrimonio.manutencao",
                        "patrimonio.conferir")
_CADASTRAR = requer_permissao("patrimonio.cadastrar")
_MANUTENCAO = requer_permissao("patrimonio.manutencao", "patrimonio.cadastrar")
_CONFERIR = requer_permissao("patrimonio.conferir")


def _filtros(busca, situacao, preventiva, criticidade, setores, id_local,
             id_produto=None) -> dict:
    return {"busca": busca, "situacao": situacao, "preventiva": preventiva,
            "criticidade": criticidade, "setores": setores, "id_local": id_local,
            "id_produto": id_produto}


@router.get("")
def listar(busca: str | None = Query(default=None, max_length=80),
           situacao: list[str] | None = Query(default=None),
           preventiva: list[str] | None = Query(default=None),
           criticidade: list[str] | None = Query(default=None),
           setores: list[int] | None = Query(default=None),
           id_local: int | None = None,
           id_produto: int | None = None,
           limite: int = Query(default=50, ge=1, le=500),
           offset: int = Query(default=0, ge=0),
           resposta: Response = None,
           ctx: Contexto = Depends(_VER)) -> list[dict]:
    """Os bens da loja. ⚠️ Sem `situacao`, os baixados ficam de fora."""
    with get_cursor() as cur:
        return servico.listar(cur, unidade_atual(cur, ctx),
                              _filtros(busca, situacao, preventiva, criticidade, setores,
                                       id_local, id_produto),
                              limite=limite, offset=offset, resposta=resposta)


@router.get("/resumo")
def resumo(ctx: Contexto = Depends(_VER)) -> dict:
    """Por setor: quantos, críticos, parados, preventiva vencida, vencendo e sem plano."""
    with get_cursor() as cur:
        return servico.resumo(cur, unidade_atual(cur, ctx))


@router.get("/valor")
def valor(data: date | None = None, setores: list[int] | None = Query(default=None),
          ctx: Contexto = Depends(_VER)) -> dict:
    """141 — o valor do patrimônio numa data (hoje, sem data): compra, depreciação e valor
    atual, por setor e bem a bem."""
    with get_cursor() as cur:
        return valor_servico.valor(cur, unidade_atual(cur, ctx), data, setores)


@router.get("/a-cadastrar")
def a_cadastrar(ctx: Contexto = Depends(_VER)) -> list[dict]:
    """O produto Patrimônio que entrou (tem saldo) e ainda não virou bem — quantos faltam,
    e onde está."""
    with get_cursor() as cur:
        return servico.a_cadastrar(cur, unidade_atual(cur, ctx))


@router.get("/do-produto/{id_produto}")
def do_produto(id_produto: int, ctx: Contexto = Depends(_VER)) -> dict:
    """Os bens de um produto e a sugestão para cadastrar o próximo (da última entrada)."""
    with get_cursor() as cur:
        return servico.do_produto(cur, unidade_atual(cur, ctx), id_produto,
                                  ve_custo=ctx.pode("estoque.saldos"))


@router.get("/codigo/{codigo}")
def por_codigo(codigo: str, ctx: Contexto = Depends(_VER)) -> dict:
    """O que a plaqueta abre. ⚠️ Vale a loja DO BEM, não a do seletor: quem lê o QR pode
    estar com outra loja escolhida — e quem não enxerga aquela loja recebe 404."""
    with get_cursor() as cur:
        r = servico.por_codigo(cur, codigo)
        if not ctx.ve_unidade(r["id_unidade"]):
            raise HTTPException(status_code=404, detail="Nenhum bem com este código")
        # 🔑 A conferência aberta que procura este bem (140): a câmera do celular abre a
        # plaqueta, e quem está conferindo tem a leitura contada ali mesmo.
        return r | {"conferencia_aberta": conferencia.aberta_do_bem(cur, r["id"])}


@router.get("/plaquetas.pdf")
def plaquetas(ids: str = Query(min_length=1), ctx: Contexto = Depends(_CADASTRAR)) -> Response:
    """As plaquetas com QR, no rolo e na impressora da loja (os de Etiquetas)."""
    try:
        lista = list(dict.fromkeys(int(i) for i in ids.split(",") if i.strip()))[:200]
    except ValueError:
        raise HTTPException(status_code=400, detail="Lista de bens inválida")
    if not lista:
        raise HTTPException(status_code=400, detail="Escolha ao menos um bem")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        conteudo = servico.plaquetas_pdf(cur, lista, id_unidade)
        direta = servico.direta(cur, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "bem", lista[0], "plaquetas",
                            depois={"bens": lista}, id_unidade=id_unidade)
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="plaquetas.pdf"',
                             "X-Impressao": "direta" if direta else "pdf"})


@router.post("/importar")
async def importar(arquivo: UploadFile = File(...), simular: bool = True,
                   incluir_sugestoes: bool = True,
                   ctx: Contexto = Depends(_CADASTRAR)) -> dict:
    """A planilha de equipamentos (.xlsx da casa ou o CSV exportado daqui).

    ⚠️ **`simular=true` é o padrão**: a prévia diz o que entra, o que muda e o que é
    recusado, com o porquê, antes de qualquer escrita. Os bytes são lidos ANTES de pedir
    a conexão, como no envio de foto.
    """
    conteudo = await arquivo.read(planilha.MAXIMO_BYTES + 1)
    try:
        linhas = planilha.ler(conteudo)
    except planilha.PlanilhaInvalida as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with get_cursor() as cur:
        return planilha.aplicar(cur, unidade_atual(cur, ctx), linhas, ctx.id_usuario,
                                simular=simular, incluir_sugestoes=incluir_sugestoes)


# ---------------------------------------------------------------- conferência (140)
# ⚠️ ANTES de `/{id_bem}`: senão "conferencias" é lido como número de bem e vira 422.

@router.get("/conferencias")
def conferencias(ctx: Contexto = Depends(_VER)) -> list[dict]:
    """As conferências da loja, a aberta primeiro."""
    with get_cursor() as cur:
        return conferencia.listar(cur, unidade_atual(cur, ctx))


@router.post("/conferencias", status_code=201)
def abrir_conferencia(body: ConferenciaAbrir, ctx: Contexto = Depends(_CONFERIR)) -> dict:
    """Abre a conferência de um setor (ou da loja inteira) e fotografa os bens esperados."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        c = conferencia.abrir(cur, id_unidade, ctx.id_usuario, body.id_setor, body.observacao)
        auditoria.registrar(cur, ctx.id_usuario, "bem_conferencia", c["id"], "abrir",
                            depois={"setor": c["escopo"], "esperados": c["esperados"]},
                            id_unidade=id_unidade)
        return c | {"message": f"Conferência de {c['escopo']} aberta: "
                               f"{c['esperados']} bem(ns) a ler."}


@router.get("/conferencias/{id_conferencia}")
def obter_conferencia(id_conferencia: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return conferencia.obter(cur, id_conferencia, unidade_atual(cur, ctx))


@router.post("/conferencias/{id_conferencia}/leituras", status_code=201)
def ler_plaqueta(id_conferencia: int, body: Leitura, ctx: Contexto = Depends(_CONFERIR)) -> dict:
    """Uma plaqueta lida — o link do QR, o código digitado ou o apelido da casa.
    ⚠️ Sem auditoria por leitura: são dezenas por conferência, e o item já guarda quem
    leu e quando. O que se audita é abrir e fechar."""
    with get_cursor() as cur:
        return conferencia.ler(cur, id_conferencia, unidade_atual(cur, ctx), ctx.id_usuario,
                               body.texto)


@router.delete("/conferencias/{id_conferencia}/leituras/{id_item}")
def desfazer_leitura(id_conferencia: int, id_item: int,
                     ctx: Contexto = Depends(_CONFERIR)) -> dict:
    with get_cursor() as cur:
        return conferencia.desfazer_leitura(cur, id_conferencia, unidade_atual(cur, ctx),
                                            id_item) | {"message": "Leitura desfeita."}


@router.post("/conferencias/{id_conferencia}/fechar")
def fechar_conferencia(id_conferencia: int, body: ConferenciaFechar,
                       ctx: Contexto = Depends(_CONFERIR)) -> dict:
    """Aplica o resultado: conferido, transferido para cá, baixado ou mantido."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        c = conferencia.fechar(cur, id_conferencia, id_unidade, ctx.id_usuario,
                               baixar=body.baixar, motivo_baixa=body.motivo_baixa,
                               transferir=body.transferir, confirmar=body.confirmar)
        auditoria.registrar(cur, ctx.id_usuario, "bem_conferencia", id_conferencia, "fechar",
                            depois=c["resultado"] | {"baixados": body.baixar},
                            id_unidade=id_unidade)
        return c


@router.post("/conferencias/{id_conferencia}/cancelar")
def cancelar_conferencia(id_conferencia: int, ctx: Contexto = Depends(_CONFERIR)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        c = conferencia.cancelar(cur, id_conferencia, id_unidade, ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "bem_conferencia", id_conferencia, "cancelar",
                            id_unidade=id_unidade)
        return c


@router.get("/{id_bem}")
def obter(id_bem: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.obter(cur, id_bem, unidade_atual(cur, ctx),
                             ve_valor_estoque=ctx.pode("estoque.saldos"))


@router.post("", status_code=201)
def criar(body: Bem, ctx: Contexto = Depends(_CADASTRAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        bem = servico.criar(cur, id_unidade, ctx.id_usuario, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "bem", bem["id"], "criar",
                            depois=body.model_dump(mode="json"), id_unidade=id_unidade)
        return bem | {"message": f"Bem {bem['codigo']} cadastrado."}


@router.put("/{id_bem}")
def atualizar(id_bem: int, body: BemParcial, ctx: Contexto = Depends(_CADASTRAR)) -> dict:
    """⚠️ Só muda o que veio no corpo (`model_fields_set`)."""
    dados = body.model_dump(include=body.model_fields_set)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        antes, depois = servico.atualizar(cur, id_bem, id_unidade, dados)
        auditoria.registrar(cur, ctx.id_usuario, "bem", id_bem, "editar",
                            antes={k: str(antes.get(k)) for k in dados},
                            depois=body.model_dump(mode="json", include=body.model_fields_set),
                            id_unidade=id_unidade)
        return depois | {"message": "Bem salvo."}


@router.delete("/{id_bem}")
def excluir(id_bem: int, ctx: Contexto = Depends(_CADASTRAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        bem = servico.excluir(cur, id_bem, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "bem", id_bem, "excluir",
                            antes={"codigo": bem["codigo"], "descricao": bem["descricao"]},
                            id_unidade=id_unidade)
        return {"message": f"Bem {bem['codigo']} apagado."}


@router.post("/{id_bem}/manutencoes", status_code=201)
def registrar_manutencao(id_bem: int, body: Manutencao,
                         ctx: Contexto = Depends(_MANUTENCAO)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = servico.registrar_manutencao(cur, id_bem, id_unidade, ctx.id_usuario,
                                         body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "bem_manutencao", r["id"], "registrar",
                            depois={"bem": r["bem"]["codigo"], **body.model_dump(mode="json")},
                            id_unidade=id_unidade)
        return r | {"message": "Manutenção registrada."}


@router.delete("/manutencoes/{id_manutencao}")
def excluir_manutencao(id_manutencao: int, ctx: Contexto = Depends(_MANUTENCAO)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        m = servico.excluir_manutencao(cur, id_manutencao, id_unidade)
        auditoria.registrar(cur, ctx.id_usuario, "bem_manutencao", id_manutencao, "excluir",
                            antes={"bem": m["id_bem"], "tipo": m["tipo"], "data": str(m["data"])},
                            id_unidade=id_unidade)
        return {"message": "Registro apagado."}
