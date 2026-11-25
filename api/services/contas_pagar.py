"""Contas a pagar (migração 163, etapa 1 do módulo Financeiro).

🔑 **Pedido do dono (24/11/2026)**: lançar o que há a pagar, a começar pelos freelancers — a
pessoa, o que é, o vencimento, se já foi agendado, se já foi pago; o agendado é baixado sozinho
na data; comprovante anexado. Estudo em `docs/financeiro-estudo.md`.

🔑 **A baixa automática não confere o banco**: ela registra que o pagamento agendado aconteceu.
Por isso a marca `baixado_automaticamente` e a lista "pagos sozinhos" no resumo — alguém olha.
⚠️ Toda mudança de situação trava as contas em ordem de id (`FOR UPDATE`), tudo ou nada.
⚠️ Não toca CMV nem estoque.
"""

import asyncio
import logging
import secrets
from datetime import date

from fastapi import HTTPException

import relogio
from database import get_cursor

log = logging.getLogger(__name__)

SITUACOES = {"A_PAGAR": "A pagar", "AGENDADO": "Agendado", "PAGO": "Pago",
             "CANCELADO": "Cancelado"}
FORMAS = {"PIX": "Pix", "TRANSFERENCIA": "Transferência", "BOLETO": "Boleto",
          "DINHEIRO": "Dinheiro", "CARTAO": "Cartão", "OUTRO": "Outro"}

_COLUNAS = """
    c.id, c.id_unidade, c.id_pessoa, c.id_categoria, c.descricao, c.funcao, c.competencia,
    c.vencimento, c.valor, c.observacao, c.status, c.agendado_para, c.forma, c.baixa_automatica,
    c.pago_em, c.valor_pago, c.baixado_automaticamente, (c.comprovante IS NOT NULL) AS tem_comprovante,
    c.lote, c.criado_em, c.id_conta_fixa, c.parcela, c.parcelas,
    coalesce(f.nome_fantasia, f.nome) AS pessoa, f.chave_pix, f.cnpj AS documento,
    cat.nome AS categoria, uc.nome AS criado_por_nome, up.nome AS pago_por_nome,
    (c.status IN ('A_PAGAR', 'AGENDADO') AND c.vencimento < %(hoje)s) AS atrasada"""

_JUNTAS = """
    FROM contas_pagar c
    JOIN fornecedores f ON f.id = c.id_pessoa
    LEFT JOIN financeiro_categorias cat ON cat.id = c.id_categoria
    LEFT JOIN usuarios uc ON uc.id = c.criado_por
    LEFT JOIN usuarios up ON up.id = c.pago_por"""


def consulta(id_unidade: int, status: list[str], de: date | None = None, ate: date | None = None,
             id_pessoa: int | None = None, id_categoria: int | None = None,
             busca: str | None = None, atrasadas: bool = False) -> tuple[str, dict]:
    """A consulta da tela e dos relatórios — uma só.

    🔑 O período é pelo VENCIMENTO no que está em aberto, e pela data do PAGAMENTO no que foi
    pago: "o que pagamos em novembro" é a pergunta de quem olha a aba Pagos.
    """
    termo = (busca or "").strip() or None
    sql = f"""SELECT {_COLUNAS} {_JUNTAS}
        WHERE c.id_unidade = %(u)s AND c.status = ANY(%(status)s)
          AND (%(de)s::date IS NULL OR coalesce(c.pago_em, c.vencimento) >= %(de)s)
          AND (%(ate)s::date IS NULL OR coalesce(c.pago_em, c.vencimento) <= %(ate)s)
          AND (%(pessoa)s::int IS NULL OR c.id_pessoa = %(pessoa)s)
          AND (%(cat)s::int IS NULL OR c.id_categoria = %(cat)s)
          AND (NOT %(atrasadas)s OR (c.status IN ('A_PAGAR', 'AGENDADO') AND c.vencimento < %(hoje)s))
          AND (%(busca)s::text IS NULL OR c.descricao ILIKE '%%' || %(busca)s || '%%'
               OR coalesce(f.nome_fantasia, f.nome) ILIKE '%%' || %(busca)s || '%%'
               OR coalesce(c.funcao, '') ILIKE '%%' || %(busca)s || '%%')
        ORDER BY CASE WHEN c.status = 'PAGO' THEN NULL ELSE c.vencimento END,
                 c.pago_em DESC NULLS LAST, lower(coalesce(f.nome_fantasia, f.nome)), c.id"""
    return sql, {"u": id_unidade, "status": status, "de": de, "ate": ate, "pessoa": id_pessoa,
                 "cat": id_categoria, "busca": termo, "atrasadas": atrasadas,
                 "hoje": relogio.hoje_da_casa()}


def totais(cur, sql: str, params: dict) -> dict:
    """Quantas e quanto no recorte da tela (a soma é do recorte inteiro, não da página)."""
    cur.execute(f"""SELECT count(*) AS n, coalesce(sum(coalesce(x.valor_pago, x.valor)), 0) AS valor,
                           count(*) FILTER (WHERE x.atrasada) AS atrasadas
                      FROM ({sql}) x""", params)
    r = cur.fetchone()
    return {"contas": r["n"], "valor": float(r["valor"]), "atrasadas": r["atrasadas"]}


def resumo(cur, id_unidade: int) -> dict:
    """Os números do topo: atrasado, vence hoje, na semana, agendado, pagos sozinhos hoje."""
    hoje = relogio.hoje_da_casa()
    cur.execute(
        """SELECT
             coalesce(sum(valor) FILTER (WHERE status IN ('A_PAGAR','AGENDADO') AND vencimento < %(h)s), 0) AS atrasado,
             count(*) FILTER (WHERE status IN ('A_PAGAR','AGENDADO') AND vencimento < %(h)s) AS n_atrasado,
             coalesce(sum(valor) FILTER (WHERE status IN ('A_PAGAR','AGENDADO') AND vencimento = %(h)s), 0) AS hoje,
             count(*) FILTER (WHERE status IN ('A_PAGAR','AGENDADO') AND vencimento = %(h)s) AS n_hoje,
             coalesce(sum(valor) FILTER (WHERE status IN ('A_PAGAR','AGENDADO')
                                          AND vencimento BETWEEN %(h)s AND %(h)s + 6), 0) AS semana,
             coalesce(sum(valor) FILTER (WHERE status = 'A_PAGAR'), 0) AS a_pagar,
             count(*) FILTER (WHERE status = 'A_PAGAR') AS n_a_pagar,
             coalesce(sum(valor) FILTER (WHERE status = 'AGENDADO'), 0) AS agendado,
             count(*) FILTER (WHERE status = 'AGENDADO') AS n_agendado,
             count(*) FILTER (WHERE status = 'PAGO' AND baixado_automaticamente AND pago_em = %(h)s)
                 AS pagos_sozinhos_hoje
           FROM contas_pagar WHERE id_unidade = %(u)s""",
        {"u": id_unidade, "h": hoje})
    r = dict(cur.fetchone())
    return {k: (float(v) if not k.startswith(("n_", "pagos")) else v) for k, v in r.items()}


DIAS_AGENDA = 14


def painel(cur, id_unidade: int, inicio: date, fim: date) -> dict:
    """O painel do Financeiro (etapa 2, 25/11/2026): o que vem pela frente e o mês.

    🔑 Duas perguntas, dois recortes:
    - **o que vem pela frente** não depende do período: atrasado, os próximos 14 dias dia a dia
      e as baixas automáticas dos últimos 7 dias (alguém confere no banco);
    - **o mês** (ou o período escolhido): pago (pela data do pagamento) × ainda em aberto (pelo
      vencimento), por categoria, por pessoa e por forma.
    ⚠️ Cancelada não entra em nada.
    """
    hoje = relogio.hoje_da_casa()
    p = {"u": id_unidade, "h": hoje, "de": inicio, "ate": fim, "dias": DIAS_AGENDA - 1}

    cur.execute(
        """SELECT vencimento AS data, count(*) AS contas, sum(valor) AS valor,
                  coalesce(sum(valor) FILTER (WHERE status = 'AGENDADO'), 0) AS agendado
             FROM contas_pagar
            WHERE id_unidade = %(u)s AND status IN ('A_PAGAR', 'AGENDADO')
              AND vencimento BETWEEN %(h)s AND %(h)s + %(dias)s
            GROUP BY vencimento ORDER BY vencimento""", p)
    agenda = [{"data": r["data"], "contas": r["contas"], "valor": float(r["valor"]),
               "agendado": float(r["agendado"])} for r in cur.fetchall()]

    cur.execute(
        f"""SELECT c.id, coalesce(f.nome_fantasia, f.nome) AS pessoa, c.descricao,
                   c.valor_pago AS valor, c.pago_em, c.forma
              {_JUNTAS}
             WHERE c.id_unidade = %(u)s AND c.status = 'PAGO' AND c.baixado_automaticamente
               AND c.pago_em BETWEEN %(h)s - 6 AND %(h)s
             ORDER BY c.pago_em DESC, lower(coalesce(f.nome_fantasia, f.nome)), c.id""", p)
    sozinhas = [dict(r) | {"valor": float(r["valor"])} for r in cur.fetchall()]

    # O período: pago pela data do pagamento, em aberto pelo vencimento — a mesma regra da tela.
    _no_periodo = """((c.status = 'PAGO' AND c.pago_em BETWEEN %(de)s AND %(ate)s)
                      OR (c.status IN ('A_PAGAR', 'AGENDADO') AND c.vencimento BETWEEN %(de)s AND %(ate)s))"""
    _somas = """coalesce(sum(c.valor_pago) FILTER (WHERE c.status = 'PAGO'), 0) AS pago,
                count(*) FILTER (WHERE c.status = 'PAGO') AS n_pago,
                coalesce(sum(c.valor) FILTER (WHERE c.status <> 'PAGO'), 0) AS em_aberto,
                count(*) FILTER (WHERE c.status <> 'PAGO') AS n_em_aberto"""

    def _numeros(r) -> dict:
        return {"pago": float(r["pago"]), "n_pago": r["n_pago"],
                "em_aberto": float(r["em_aberto"]), "n_em_aberto": r["n_em_aberto"],
                "total": float(r["pago"] + r["em_aberto"])}

    cur.execute(f"SELECT {_somas} FROM contas_pagar c WHERE c.id_unidade = %(u)s AND {_no_periodo}", p)
    periodo = _numeros(cur.fetchone())

    cur.execute(
        f"""SELECT coalesce(cat.nome, 'Sem categoria') AS categoria, {_somas}
              FROM contas_pagar c LEFT JOIN financeiro_categorias cat ON cat.id = c.id_categoria
             WHERE c.id_unidade = %(u)s AND {_no_periodo}
             GROUP BY cat.nome ORDER BY sum(coalesce(c.valor_pago, c.valor)) DESC""", p)
    por_categoria = [{"categoria": r["categoria"], **_numeros(r)} for r in cur.fetchall()]

    cur.execute(
        f"""SELECT c.id_pessoa, coalesce(f.nome_fantasia, f.nome) AS pessoa, {_somas}
              FROM contas_pagar c JOIN fornecedores f ON f.id = c.id_pessoa
             WHERE c.id_unidade = %(u)s AND {_no_periodo}
             GROUP BY c.id_pessoa, f.nome_fantasia, f.nome
             ORDER BY sum(coalesce(c.valor_pago, c.valor)) DESC""", p)
    por_pessoa = [{"id_pessoa": r["id_pessoa"], "pessoa": r["pessoa"], **_numeros(r)}
                  for r in cur.fetchall()]

    cur.execute(
        """SELECT coalesce(c.forma, 'OUTRO') AS forma, count(*) AS contas, sum(c.valor_pago) AS valor
             FROM contas_pagar c
            WHERE c.id_unidade = %(u)s AND c.status = 'PAGO' AND c.pago_em BETWEEN %(de)s AND %(ate)s
            GROUP BY 1 ORDER BY sum(c.valor_pago) DESC""", p)
    por_forma = [{"forma": r["forma"], "rotulo": FORMAS.get(r["forma"], r["forma"]),
                  "contas": r["contas"], "valor": float(r["valor"])} for r in cur.fetchall()]

    return {"hoje": hoje, "de": inicio, "ate": fim, "resumo": resumo(cur, id_unidade),
            "agenda": agenda, "baixadas_sozinhas": sozinhas, "periodo": periodo,
            "por_categoria": por_categoria, "por_pessoa": por_pessoa, "por_forma": por_forma}


def _pessoa(cur, id_pessoa: int) -> dict:
    cur.execute("SELECT id, coalesce(nome_fantasia, nome) AS nome, ativo FROM fornecedores WHERE id = %s",
                (id_pessoa,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=400, detail="Pessoa não encontrada no cadastro.")
    if not p["ativo"]:
        raise HTTPException(status_code=409, detail=f"{p['nome']} está inativo no cadastro de Pessoas.")
    return dict(p)


def _categoria(cur, id_categoria: int | None) -> None:
    if id_categoria is None:
        return
    cur.execute("SELECT 1 FROM financeiro_categorias WHERE id = %s", (id_categoria,))
    if not cur.fetchone():
        raise HTTPException(status_code=400, detail="Categoria não encontrada.")


def lancar(cur, id_unidade: int, id_usuario: int, dados: dict, lote: str | None = None) -> dict:
    p = _pessoa(cur, dados["id_pessoa"])
    _categoria(cur, dados.get("id_categoria"))
    cur.execute(
        """INSERT INTO contas_pagar (id_unidade, id_pessoa, id_categoria, descricao, funcao,
                                     competencia, vencimento, valor, observacao, lote, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, p["id"], dados.get("id_categoria"), dados["descricao"].strip(),
         (dados.get("funcao") or "").strip() or None, dados["competencia"], dados["vencimento"],
         dados["valor"], (dados.get("observacao") or "").strip() or None, lote, id_usuario))
    return {"id": cur.fetchone()["id"], "pessoa": p["nome"]}


def ratear(total, n: int) -> list:
    """O valor total em `n` parcelas, em centavos: a sobra vai nas primeiras (100/3 = 33,34 +
    33,33 + 33,33). ⚠️ Decimal, nunca float: a soma das parcelas é SEMPRE o total."""
    from decimal import Decimal
    centavos = int((Decimal(total) * 100).to_integral_value())
    base, sobra = divmod(centavos, n)
    return [Decimal(base + (1 if i < sobra else 0)) / 100 for i in range(n)]


def lancar_parcelado(cur, id_unidade: int, id_usuario: int, dados: dict) -> dict:
    """🔑 Uma compra em N vezes (etapa 3, migração 167): N contas, uma por mês a partir do
    vencimento informado, com `parcela`/`parcelas` e o mesmo `lote`. O `valor` é o TOTAL.
    A competência é a mesma em todas (o dia da compra). Tudo ou nada."""
    from services.contas_fixas import somar_meses
    n = dados["parcelas"]
    lote = f"PC{secrets.token_hex(4)}"
    valores = ratear(dados["valor"], n)
    ids = []
    for i, v in enumerate(valores):
        r = lancar(cur, id_unidade, id_usuario,
                   {**dados, "valor": v, "vencimento": somar_meses(dados["vencimento"], i)}, lote)
        cur.execute("UPDATE contas_pagar SET parcela = %s, parcelas = %s WHERE id = %s",
                    (i + 1, n, r["id"]))
        ids.append(r["id"])
    maior, menor = max(valores), min(valores)
    cada = (f"{n}x de R$ {maior:.2f}" if maior == menor
            else f"{n}x (R$ {maior:.2f} nas primeiras, R$ {menor:.2f} nas demais)")
    return {"ids": ids, "lote": lote, "pessoa": r["pessoa"],
            "message": f"Compra parcelada em {cada.replace('.', ',')}."}


def lancar_equipe(cur, id_unidade: int, id_usuario: int, dados: dict) -> dict:
    """Uma conta por pessoa da equipe do dia, todas no mesmo lote. Tudo ou nada."""
    pessoas = [i["id_pessoa"] for i in dados["itens"]]
    if len(set(pessoas)) != len(pessoas):
        raise HTTPException(status_code=400, detail="A mesma pessoa veio duas vezes na equipe.")
    lote = f"EQ{secrets.token_hex(4)}"
    feitas = []
    for i in dados["itens"]:
        feitas.append(lancar(cur, id_unidade, id_usuario, {
            "id_pessoa": i["id_pessoa"], "id_categoria": dados.get("id_categoria"),
            "descricao": dados["descricao"], "funcao": i.get("funcao"),
            "competencia": dados["data"], "vencimento": dados["vencimento"],
            "valor": i["valor"], "observacao": i.get("observacao")}, lote))
    total = sum(i["valor"] for i in dados["itens"])
    return {"ids": [f["id"] for f in feitas], "lote": lote,
            "message": f"{len(feitas)} conta(s) lançada(s), somando R$ {total:.2f}".replace(".", ",")}


def ultimo_da_pessoa(cur, id_unidade: int, id_pessoa: int) -> dict | None:
    """O último valor e a função da pessoa — o que a equipe do dia preenche sozinha."""
    cur.execute("""SELECT valor, funcao, id_categoria FROM contas_pagar
                    WHERE id_unidade = %s AND id_pessoa = %s AND status <> 'CANCELADO'
                    ORDER BY competencia DESC, id DESC LIMIT 1""", (id_unidade, id_pessoa))
    r = cur.fetchone()
    return {"valor": float(r["valor"]), "funcao": r["funcao"], "id_categoria": r["id_categoria"]} if r else None


def _travar(cur, id_unidade: int, ids: list[int]) -> dict[int, dict]:
    unicos = sorted(set(ids))
    cur.execute("""SELECT * FROM contas_pagar WHERE id = ANY(%s) AND id_unidade = %s
                    ORDER BY id FOR UPDATE""", (unicos, id_unidade))
    linhas = {r["id"]: dict(r) for r in cur.fetchall()}
    if len(linhas) != len(unicos):
        raise HTTPException(status_code=404, detail="Conta não encontrada nesta loja.")
    return linhas


def _exigir(linhas: dict[int, dict], permitidos: tuple[str, ...], acao: str) -> None:
    for c in linhas.values():
        if c["status"] not in permitidos:
            raise HTTPException(
                status_code=409,
                detail=f"A conta nº {c['id']} ({c['descricao']}) está {SITUACOES[c['status']].lower()}: "
                       f"não dá para {acao}.")


def corrigir(cur, id_unidade: int, id_conta: int, dados: dict) -> dict:
    c = _travar(cur, id_unidade, [id_conta])[id_conta]
    _exigir({id_conta: c}, ("A_PAGAR", "AGENDADO"), "corrigir")
    p = _pessoa(cur, dados["id_pessoa"])
    _categoria(cur, dados.get("id_categoria"))
    cur.execute(
        """UPDATE contas_pagar SET id_pessoa = %s, id_categoria = %s, descricao = %s, funcao = %s,
                  competencia = %s, vencimento = %s, valor = %s, observacao = %s WHERE id = %s""",
        (p["id"], dados.get("id_categoria"), dados["descricao"].strip(),
         (dados.get("funcao") or "").strip() or None, dados["competencia"], dados["vencimento"],
         dados["valor"], (dados.get("observacao") or "").strip() or None, id_conta))
    return {"antes": {k: str(c[k]) for k in ("id_pessoa", "valor", "vencimento", "descricao")}}


def agendar(cur, id_unidade: int, id_usuario: int, ids: list[int], data: date, forma: str,
            baixa_automatica: bool) -> dict:
    linhas = _travar(cur, id_unidade, ids)
    _exigir(linhas, ("A_PAGAR", "AGENDADO"), "agendar")
    cur.execute("""UPDATE contas_pagar SET status = 'AGENDADO', agendado_para = %s, forma = %s,
                          baixa_automatica = %s, agendado_por = %s
                    WHERE id = ANY(%s)""", (data, forma, baixa_automatica, id_usuario, list(linhas)))
    n = len(linhas)
    return {"ids": sorted(linhas),
            "message": f"{n} conta(s) agendada(s) para {data:%d/%m}"
                       + (" — com baixa automática na data" if baixa_automatica else "")}


def pagar(cur, id_unidade: int, id_usuario: int, ids: list[int], pago_em: date, forma: str,
          valor_pago=None, automatico: bool = False) -> dict:
    linhas = _travar(cur, id_unidade, ids)
    _exigir(linhas, ("A_PAGAR", "AGENDADO"), "pagar")
    if valor_pago is not None and len(linhas) > 1:
        raise HTTPException(status_code=400,
                            detail="Valor pago diferente só se informa pagando UMA conta.")
    for c in linhas.values():
        cur.execute("""UPDATE contas_pagar SET status = 'PAGO', pago_em = %s, forma = %s,
                              valor_pago = %s, pago_por = %s, baixado_automaticamente = %s
                        WHERE id = %s""",
                    (pago_em, forma, valor_pago if valor_pago is not None else c["valor"],
                     None if automatico else id_usuario, automatico, c["id"]))
    total = sum((valor_pago if valor_pago is not None else c["valor"]) for c in linhas.values())
    return {"ids": sorted(linhas),
            "message": f"{len(linhas)} conta(s) paga(s), R$ {total:.2f}".replace(".", ",")}


def estornar(cur, id_unidade: int, ids: list[int]) -> dict:
    """Desfaz a baixa: volta a AGENDADO se tinha agendamento, senão a A_PAGAR. O comprovante fica."""
    linhas = _travar(cur, id_unidade, ids)
    _exigir(linhas, ("PAGO",), "estornar a baixa")
    cur.execute("""UPDATE contas_pagar
                      SET status = CASE WHEN agendado_para IS NOT NULL THEN 'AGENDADO' ELSE 'A_PAGAR' END,
                          pago_em = NULL, valor_pago = NULL, pago_por = NULL,
                          baixado_automaticamente = false,
                          -- ⚠️ O agendado estornado não volta a ser baixado sozinho no mesmo dia: a
                          -- pessoa estornou porque o banco não pagou.
                          baixa_automatica = CASE WHEN baixado_automaticamente THEN false
                                                  ELSE baixa_automatica END
                    WHERE id = ANY(%s)""", (list(linhas),))
    return {"ids": sorted(linhas), "message": f"{len(linhas)} baixa(s) estornada(s)."}


def cancelar(cur, id_unidade: int, id_usuario: int, ids: list[int]) -> dict:
    linhas = _travar(cur, id_unidade, ids)
    _exigir(linhas, ("A_PAGAR", "AGENDADO"), "cancelar")
    cur.execute("""UPDATE contas_pagar SET status = 'CANCELADO', cancelado_por = %s,
                          cancelado_em = now() WHERE id = ANY(%s)""", (id_usuario, list(linhas)))
    return {"ids": sorted(linhas), "message": f"{len(linhas)} conta(s) cancelada(s)."}


def baixar_agendadas(cur, hoje: date | None = None) -> list[dict]:
    """A baixa automática: todo AGENDADO com baixa automática cuja data chegou vira PAGO.

    🔑 Paga na data AGENDADA (não na de hoje): é o dia em que o banco pagou. Roda no agendador e
    também antes de cada leitura da tela, para o que se vê nunca depender de o laço ter rodado.
    """
    hoje = hoje or relogio.hoje_da_casa()
    cur.execute("""UPDATE contas_pagar
                      SET status = 'PAGO', pago_em = agendado_para, valor_pago = valor,
                          baixado_automaticamente = true, pago_por = NULL
                    WHERE status = 'AGENDADO' AND baixa_automatica AND agendado_para <= %s
                RETURNING id, id_unidade, valor, agendado_para""", (hoje,))
    return [dict(r) for r in cur.fetchall()]


def baixar_e_registrar(cur) -> int:
    """`baixar_agendadas` com a auditoria de cada uma — o laço e a tela usam esta.

    🔑 Antes da baixa, gera as contas fixas do mês que chegou (etapa 3, 167): a conta fixa de
    débito automático que nasce já vencida é baixada na mesma passada.
    """
    import auditoria
    from services import contas_fixas
    for g in contas_fixas.gerar(cur):
        auditoria.registrar(cur, None, "conta_pagar", g["id"], "gerar_conta_fixa",
                            depois={"id_conta_fixa": g["id_conta_fixa"], "mes": str(g["mes"]),
                                    "valor": str(g["valor"])},
                            id_unidade=g["id_unidade"])
    feitas = baixar_agendadas(cur)
    for b in feitas:
        auditoria.registrar(cur, None, "conta_pagar", b["id"], "baixa_automatica",
                            depois={"valor": str(b["valor"]), "pago_em": str(b["agendado_para"])},
                            id_unidade=b["id_unidade"])
    return len(feitas)


async def laco(parar: asyncio.Event) -> None:
    """O agendador da baixa automática: confere a cada meia hora."""
    while not parar.is_set():
        try:
            with get_cursor() as cur:
                baixar_e_registrar(cur)
        except Exception:  # noqa: BLE001 — o laço não pode morrer
            log.exception("baixa automática das contas a pagar falhou")
        try:
            await asyncio.wait_for(parar.wait(), timeout=1800)
        except asyncio.TimeoutError:
            pass
