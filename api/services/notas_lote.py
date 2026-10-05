"""Lançar de uma vez as notas que já estão conciliadas — com prévia.

🔑 **Por que existe (05/10/2026).** No ar havia 94 notas conciliadas esperando o
clique de lançar, R$ 50 mil de compra fora do estoque. Cada uma era uma ida à
tela da nota; ninguém faz noventa idas, e enquanto elas esperam a venda sai sem
saldo (negativo, custo provisório) e o CMV do período fica sem a compra.

🔑 **A prévia É o lançamento, ensaiado e desfeito.** Cada nota passa pela MESMA
`importador.lancar_nota` dentro de um `SAVEPOINT`, que volta atrás no fim. Uma
prévia que reescrevesse as recusas (item sem produto, produto sem unidade,
cadastro arquivado, período fechado) seria a segunda cópia da regra — e
divergiria da de verdade na primeira recusa nova que o lançamento ganhasse.

⚠️ **Três destinos, e só o primeiro é lançado pelo lote:**

* **pronta** — o ensaio passou e nada pede olho;
* **conferir** — o ensaio passou, mas a nota declara uma conversão diferente da
  do cadastro (`fator_diverge`). Lançar assim pode pôr metade (ou o dobro) da
  mercadoria no razão, que é append-only: quem resolve é uma pessoa, na tela da
  nota. O lote NÃO lança estas, nem a pedido;
* **travada** — o lançamento recusaria, e a frase é a dele.

⚠️ **Da mais antiga para a mais nova.** O custo médio é calculado na ordem de
LANÇAMENTO; entrando em ordem de data, o razão nasce o mais perto possível da
ordem em que a mercadoria chegou.
"""
from __future__ import annotations

from fastapi import HTTPException

import auditoria
from services.omie import importador

PRONTA, CONFERIR, TRAVADA = "pronta", "conferir", "travada"


def _candidatas(cur, id_unidade: int, travar: bool = False) -> list[dict]:
    """As notas abertas desta loja sem item pendente, da mais antiga para a mais nova.

    ⚠️ Pelo ITEM, não pelo `status`: é a mesma pergunta que o lançamento faz, e
    um status desatualizado deixaria de fora nota que já está pronta.
    """
    cur.execute(
        """SELECT n.id, n.numero, n.serie, n.valor_total, n.origem, n.id_fornecedor,
                  coalesce(n.data_entrada, n.data_emissao) AS data,
                  coalesce(f.nome, n.nome_emitente) AS fornecedor,
                  (SELECT count(*) FROM nota_itens i
                    WHERE i.id_nota = n.id AND NOT i.ignorado) AS itens
             FROM notas_entrada n
             LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
            WHERE n.id_unidade = %s AND n.status IN ('IMPORTADA', 'CONCILIADA')
              AND NOT EXISTS (SELECT 1 FROM nota_itens i
                               WHERE i.id_nota = n.id AND i.id_produto IS NULL
                                 AND NOT i.ignorado)
            ORDER BY coalesce(n.data_entrada, n.data_emissao) NULLS LAST, n.id"""
        + (" FOR UPDATE OF n" if travar else ""),
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def _fatores_divergentes(cur, nota: dict) -> list[str]:
    """Os itens em que a nota declara uma conversão e o cadastro usaria outra.

    ⚠️ A mesma conta e a mesma tolerância de `GET /notas/{id}` — a lista e o
    detalhe não podem discordar sobre qual nota pede conferência.
    """
    cur.execute(
        """SELECT i.descricao_fornecedor, i.id_produto, i.codigo_fornecedor, i.um_nota,
                  i.codigo_omie, i.fator_declarado
             FROM nota_itens i
            WHERE i.id_nota = %s AND i.id_produto IS NOT NULL AND NOT i.ignorado
              AND i.fator_declarado IS NOT NULL
            ORDER BY i.seq""",
        (nota["id"],),
    )
    divergentes = []
    for item in cur.fetchall():
        usado = importador.fator_do_item_para_tela(
            cur, item["id_produto"], nota["id_fornecedor"], item["codigo_fornecedor"],
            item["um_nota"], item["codigo_omie"])
        declarado = item["fator_declarado"]
        if declarado and usado is not None and \
                abs(float(declarado) - float(usado)) > float(usado) * 0.005:
            divergentes.append(item["descricao_fornecedor"])
    return divergentes


def _ensaiar(cur, id_nota: int, id_usuario: int, id_local: int | None,
             pode_retroativo: bool, manter: bool) -> tuple[dict | None, str | None]:
    """Lança a nota dentro de um ponto de retorno. Devolve (resultado, recusa).

    Com `manter=False` o lançamento é sempre desfeito — é a prévia. Com
    `manter=True` ele fica quando deu certo, e uma nota recusada não leva as
    outras junto.
    """
    cur.execute("SAVEPOINT nota_do_lote")
    try:
        r = importador.lancar_nota(cur, id_nota, id_usuario, id_local, pode_retroativo)
    except HTTPException as e:
        cur.execute("ROLLBACK TO SAVEPOINT nota_do_lote")
        cur.execute("RELEASE SAVEPOINT nota_do_lote")
        return None, str(e.detail)
    if manter:
        cur.execute("RELEASE SAVEPOINT nota_do_lote")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT nota_do_lote")
        cur.execute("RELEASE SAVEPOINT nota_do_lote")
    return r, None


def _classificar(cur, nota: dict, id_usuario: int, id_local: int | None,
                 pode_retroativo: bool) -> dict:
    r, recusa = _ensaiar(cur, nota["id"], id_usuario, id_local, pode_retroativo, manter=False)
    linha = {
        "id": nota["id"], "numero": nota["numero"], "fornecedor": nota["fornecedor"],
        "data": nota["data"], "valor_total": float(nota["valor_total"] or 0),
        "itens": nota["itens"], "motivo": None,
    }
    if recusa:
        return linha | {"situacao": TRAVADA, "motivo": recusa}
    divergentes = _fatores_divergentes(cur, nota)
    if divergentes:
        mostra = ", ".join(divergentes[:2])
        resto = f" e mais {len(divergentes) - 2}" if len(divergentes) > 2 else ""
        return linha | {
            "situacao": CONFERIR,
            "motivo": (f"A nota declara uma conversão diferente da do cadastro em "
                       f"{mostra}{resto}. Confira na nota antes de lançar."),
        }
    # ⚠️ `fora_de_ordem`: quantos produtos desta nota já têm movimento com data
    # posterior à dela. Não trava nem pede conferência — a nota atrasada é o caso
    # comum, e é para ela que o lote existe —, mas a prévia mostra, porque esses
    # produtos pedem reprocessamento depois.
    return linha | {"situacao": PRONTA, "valor_estoque": r["valor"],
                    "fora_de_ordem": len(r.get("fora_de_ordem") or [])}


def _resumo(linhas: list[dict]) -> dict:
    def grupo(situacao: str) -> dict:
        do_grupo = [l for l in linhas if l["situacao"] == situacao]
        return {"notas": len(do_grupo),
                "valor": round(sum(l["valor_total"] for l in do_grupo), 2)}
    return {PRONTA: grupo(PRONTA), CONFERIR: grupo(CONFERIR), TRAVADA: grupo(TRAVADA)}


def _o_que_destrava(cur, ids_travadas: list[int]) -> list[dict]:
    """Os CADASTROS que seguram notas travadas, do que solta mais para o que solta menos.

    🔑 **A trava quase nunca é da nota, é do produto** — e o mesmo produto trava
    dezenas (medido na base local: 594 notas paradas por produto sem unidade de
    estoque, com "COGUMELO" sozinho em várias). Lida nota a nota, a lista manda
    abrir 594 telas; lida por produto, manda completar um cadastro e solta todas.
    ⚠️ **Isto ORIENTA, não decide.** Quem diz se a nota lança continua sendo o
    ensaio do lançamento; aqui só se nomeia o que consertar primeiro. Por isso
    cobre as duas causas que são do cadastro (sem unidade, arquivado) e mais
    nenhuma.
    """
    if not ids_travadas:
        return []
    cur.execute(
        """SELECT p.id, p.codigo, p.nome,
                  CASE WHEN NOT p.ativo THEN 'arquivado' ELSE 'sem_unidade' END AS causa,
                  count(DISTINCT i.id_nota) AS notas
             FROM nota_itens i
             JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_nota = ANY(%s) AND NOT i.ignorado
              AND (p.um_estoque IS NULL OR NOT p.ativo)
            GROUP BY p.id, p.codigo, p.nome, p.ativo
            ORDER BY count(DISTINCT i.id_nota) DESC, p.nome
            LIMIT 50""",
        (ids_travadas,),
    )
    return [dict(r) for r in cur.fetchall()]


def previa(cur, id_unidade: int, id_usuario: int, id_local: int | None = None,
           pode_retroativo: bool = False) -> dict:
    """O que o lote faria, sem gravar nada."""
    linhas = [_classificar(cur, n, id_usuario, id_local, pode_retroativo)
              for n in _candidatas(cur, id_unidade)]
    travadas = [l["id"] for l in linhas if l["situacao"] == TRAVADA]
    return {"notas": linhas, "resumo": _resumo(linhas),
            "destrava": _o_que_destrava(cur, travadas)}


def lancar(cur, id_unidade: int, id_usuario: int, ids: list[int] | None = None,
           id_local: int | None = None, pode_retroativo: bool = False) -> dict:
    """Lança as notas PRONTAS desta loja — todas, ou só as de `ids`.

    ⚠️ **Reclassifica AQUI em vez de confiar na lista da tela.** Entre ver a
    prévia e clicar, alguém pode ter lançado uma daquelas notas, fundido um
    produto ou fechado o período. `ids` só RESTRINGE: nota que não é desta loja,
    que não está pronta ou que pede conferência não entra por ter sido pedida.
    ⚠️ **Uma nota recusada não desfaz as outras** (ponto de retorno por nota):
    a recusa volta nomeada, e as demais ficam lançadas.
    """
    pedidas = set(ids) if ids is not None else None
    lancadas, fora = [], []
    fora_de_ordem: set[int] = set()
    for nota in _candidatas(cur, id_unidade, travar=True):
        if pedidas is not None and nota["id"] not in pedidas:
            continue
        linha = _classificar(cur, nota, id_usuario, id_local, pode_retroativo)
        if linha["situacao"] != PRONTA:
            fora.append(linha)
            continue
        r, recusa = _ensaiar(cur, nota["id"], id_usuario, id_local, pode_retroativo,
                             manter=True)
        if recusa:
            fora.append(linha | {"situacao": TRAVADA, "motivo": recusa})
            continue
        # A mesma linha de auditoria do lançamento nota a nota, com a marca do lote.
        auditoria.registrar(cur, id_usuario, "nota", nota["id"], "lancar",
                            depois=r | {"lote": True})
        lancadas.append(linha | {"itens_lancados": r["itens_lancados"],
                                 "valor_estoque": r["valor"]})
        fora_de_ordem.update(r.get("fora_de_ordem") or [])
    return {
        "lancadas": lancadas, "fora": fora,
        "notas": len(lancadas),
        "itens": sum(l["itens_lancados"] for l in lancadas),
        "valor": round(sum(l["valor_estoque"] for l in lancadas), 2),
        # Os PRODUTOS (distintos) que ficaram fora da ordem das datas — é a
        # lista de quem reprocessar, não a soma por nota.
        "fora_de_ordem": len(fora_de_ordem),
        "produtos_fora_de_ordem": sorted(fora_de_ordem),
    }
