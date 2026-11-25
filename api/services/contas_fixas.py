"""Contas fixas: o aluguel, a internet e a luz, gerados sozinhos todo mês (migração 167).

🔑 Etapa 3 do módulo Financeiro (`docs/financeiro-estudo.md`). A conta fixa é o MOLDE; a conta de
cada mês nasce em `contas_pagar`, `antecedencia_dias` antes do vencimento, e dali em diante é uma
conta como outra qualquer.
🔑 **Idempotência é do banco** (regra 8): o índice único `(id_conta_fixa, competencia)` garante uma
conta por mês, e a geração é `ON CONFLICT DO NOTHING` — o laço e a tela podem rodar juntos.
⚠️ Mudar a conta fixa vale para os meses que AINDA não nasceram; a já gerada se corrige nela.
⚠️ Cancelar a conta de um mês não a faz nascer de novo: o mês continua ocupado.
"""

import calendar
from datetime import date, timedelta

from fastapi import HTTPException

import relogio

MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _gerar_registrando(cur) -> None:
    """A geração COM auditoria (e a baixa automática junto): a mesma passada do laço."""
    from services.contas_pagar import baixar_e_registrar
    baixar_e_registrar(cur)


def mes_da(d: date) -> date:
    return d.replace(day=1)


def somar_meses(d: date, n: int) -> date:
    """O mesmo dia `n` meses depois; 31 em fevereiro vira o último dia."""
    m = d.year * 12 + d.month - 1 + n
    ano, mes = m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def vencimento_do_mes(mes: date, dia: int) -> date:
    return mes.replace(day=min(dia, calendar.monthrange(mes.year, mes.month)[1]))


def _rotulo_mes(mes: date) -> str:
    return f"{MESES[mes.month - 1]}/{mes.year}"


def proxima(fixa: dict, hoje: date) -> dict | None:
    """O próximo mês que ainda não nasceu: quando vence e quando vai ser gerado."""
    if not fixa["ativo"]:
        return None
    mes = max(mes_da(fixa["inicio"]),
              somar_meses(fixa["ultimo_mes"], 1) if fixa.get("ultimo_mes") else mes_da(fixa["inicio"]))
    if fixa["fim"] and mes > fixa["fim"]:
        return None
    venc = vencimento_do_mes(mes, fixa["dia_vencimento"])
    return {"mes": mes, "vencimento": venc,
            "gera_em": max(hoje, venc - timedelta(days=fixa["antecedencia_dias"]))}


def gerar(cur, hoje: date | None = None, so_ids: list[int] | None = None) -> list[dict]:
    """Gera, de todas as contas fixas ativas, os meses cujo vencimento já entrou na antecedência.

    🔑 Do mês de `inicio` em diante (até `fim`), todo mês com `vencimento - antecedência <= hoje`
    que ainda não tem conta. Uma conta fixa criada com início no passado gera os meses atrasados
    de uma vez: é o que a pessoa pediu ao escolher o início.
    `so_ids` restringe a algumas contas fixas: é o que o teste usa para simular outra data sem
    gerar meses futuros das contas fixas de verdade.
    ⚠️ Nunca volta para trás do último mês já gerado: começa no mês seguinte a ele (ou no início,
    se for depois). Senão um mês pulado de propósito nasceria atrasado a cada meia hora.
    """
    hoje = hoje or relogio.hoje_da_casa()
    cur.execute("""SELECT f.*, (SELECT max(c.competencia) FROM contas_pagar c
                                 WHERE c.id_conta_fixa = f.id) AS ultimo_mes
                     FROM contas_fixas f
                    WHERE f.ativo AND (%s::int[] IS NULL OR f.id = ANY(%s))""", (so_ids, so_ids))
    feitas: list[dict] = []
    for f in cur.fetchall():
        f = dict(f)
        mes = mes_da(f["inicio"])
        if f["ultimo_mes"]:
            mes = max(mes, somar_meses(f["ultimo_mes"], 1))
        limite = mes_da(hoje + timedelta(days=f["antecedencia_dias"]))
        if f["fim"]:
            limite = min(limite, f["fim"])
        while mes <= limite:
            venc = vencimento_do_mes(mes, f["dia_vencimento"])
            if venc - timedelta(days=f["antecedencia_dias"]) <= hoje:
                obs = f["observacao"]
                if f["valor_variavel"]:
                    obs = " · ".join(x for x in (obs, "valor previsto: corrija quando a fatura chegar") if x)
                cur.execute(
                    """INSERT INTO contas_pagar
                           (id_unidade, id_pessoa, id_categoria, descricao, competencia, vencimento,
                            valor, observacao, id_conta_fixa, status, agendado_para, forma,
                            baixa_automatica, criado_por)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, NULL)
                       ON CONFLICT (id_conta_fixa, competencia) WHERE id_conta_fixa IS NOT NULL
                       DO NOTHING RETURNING id""",
                    (f["id_unidade"], f["id_pessoa"], f["id_categoria"],
                     f"{f['descricao']} — {_rotulo_mes(mes)}", mes, venc, f["valor"],
                     obs[:300] if obs else None, f["id"],
                     "AGENDADO" if f["agendar"] else "A_PAGAR",
                     venc if f["agendar"] else None, f["forma"]))
                r = cur.fetchone()
                if r:
                    feitas.append({"id": r["id"], "id_unidade": f["id_unidade"], "id_conta_fixa": f["id"],
                                   "mes": mes, "valor": f["valor"]})
            mes = somar_meses(mes, 1)
    return feitas


_COLUNAS = """
    f.*, coalesce(p.nome_fantasia, p.nome) AS pessoa, cat.nome AS categoria,
    (SELECT max(c.competencia) FROM contas_pagar c WHERE c.id_conta_fixa = f.id) AS ultimo_mes,
    (SELECT count(*) FROM contas_pagar c WHERE c.id_conta_fixa = f.id
                                         AND c.status IN ('A_PAGAR', 'AGENDADO')) AS em_aberto"""


def listar(cur, id_unidade: int, incluir_encerradas: bool = False) -> list[dict]:
    hoje = relogio.hoje_da_casa()
    cur.execute(f"""SELECT {_COLUNAS}
                      FROM contas_fixas f
                      JOIN fornecedores p ON p.id = f.id_pessoa
                      LEFT JOIN financeiro_categorias cat ON cat.id = f.id_categoria
                     WHERE f.id_unidade = %s AND (f.ativo OR %s)
                     ORDER BY NOT f.ativo, f.dia_vencimento, lower(f.descricao)""",
                (id_unidade, incluir_encerradas))
    saida = []
    for r in cur.fetchall():
        r = dict(r)
        r["proxima"] = proxima(r, hoje)
        saida.append(r)
    return saida


def _validar(cur, dados: dict) -> None:
    from services.contas_pagar import _categoria, _pessoa
    _pessoa(cur, dados["id_pessoa"])
    _categoria(cur, dados.get("id_categoria"))
    if dados.get("agendar") and not dados.get("forma"):
        raise HTTPException(status_code=400,
                            detail="Para nascer agendada (débito automático), diga a forma.")
    if dados.get("fim") and mes_da(dados["fim"]) < mes_da(dados["inicio"]):
        raise HTTPException(status_code=400, detail="O último mês vem antes do primeiro.")


def _campos(dados: dict) -> tuple:
    return (dados["id_pessoa"], dados.get("id_categoria"), dados["descricao"].strip(), dados["valor"],
            bool(dados.get("valor_variavel")), dados["dia_vencimento"], mes_da(dados["inicio"]),
            mes_da(dados["fim"]) if dados.get("fim") else None, dados.get("antecedencia_dias", 10),
            bool(dados.get("agendar")), dados.get("forma"),
            (dados.get("observacao") or "").strip() or None)


def criar(cur, id_unidade: int, id_usuario: int, dados: dict) -> dict:
    _validar(cur, dados)
    cur.execute(
        """INSERT INTO contas_fixas (id_pessoa, id_categoria, descricao, valor, valor_variavel,
                                     dia_vencimento, inicio, fim, antecedencia_dias, agendar,
                                     forma, observacao, id_unidade, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (*_campos(dados), id_unidade, id_usuario))
    novo = cur.fetchone()["id"]
    _gerar_registrando(cur)
    cur.execute("SELECT id FROM contas_pagar WHERE id_conta_fixa = %s ORDER BY competencia", (novo,))
    geradas = [x["id"] for x in cur.fetchall()]
    n = len(geradas)
    return {"id": novo, "geradas": geradas,
            "message": f"Conta fixa criada." + (f" {n} conta(s) já gerada(s)." if n else
                                                " A primeira conta nasce na antecedência do vencimento.")}


def _travar(cur, id_unidade: int, id_fixa: int) -> dict:
    cur.execute("SELECT * FROM contas_fixas WHERE id = %s AND id_unidade = %s FOR UPDATE",
                (id_fixa, id_unidade))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Conta fixa não encontrada nesta loja.")
    return dict(r)


def alterar(cur, id_unidade: int, id_fixa: int, dados: dict) -> dict:
    """⚠️ Vale para os meses que ainda não nasceram: a conta já gerada se corrige nela."""
    antes = _travar(cur, id_unidade, id_fixa)
    if not antes["ativo"]:
        raise HTTPException(status_code=409, detail="Esta conta fixa está encerrada: reative antes.")
    _validar(cur, dados)
    cur.execute(
        """UPDATE contas_fixas SET id_pessoa = %s, id_categoria = %s, descricao = %s, valor = %s,
                  valor_variavel = %s, dia_vencimento = %s, inicio = %s, fim = %s,
                  antecedencia_dias = %s, agendar = %s, forma = %s, observacao = %s
            WHERE id = %s""", (*_campos(dados), id_fixa))
    _gerar_registrando(cur)
    return {"antes": {k: str(antes[k]) for k in ("descricao", "valor", "dia_vencimento", "fim")},
            "message": "Conta fixa salva. Vale para os próximos meses."}


def encerrar(cur, id_unidade: int, id_usuario: int, id_fixa: int, cancelar_abertas: bool) -> dict:
    """Para de gerar. Com `cancelar_abertas`, cancela também as já geradas que vencem de hoje em
    diante e ainda estão em aberto (as atrasadas ficam: são dívida de verdade)."""
    f = _travar(cur, id_unidade, id_fixa)
    if not f["ativo"]:
        raise HTTPException(status_code=409, detail="Esta conta fixa já está encerrada.")
    cur.execute("""UPDATE contas_fixas SET ativo = false, encerrado_por = %s, encerrado_em = now()
                    WHERE id = %s""", (id_usuario, id_fixa))
    canceladas: list[int] = []
    if cancelar_abertas:
        cur.execute("""UPDATE contas_pagar SET status = 'CANCELADO', cancelado_por = %s,
                              cancelado_em = now()
                        WHERE id_conta_fixa = %s AND status IN ('A_PAGAR', 'AGENDADO')
                          AND vencimento >= %s
                    RETURNING id""", (id_usuario, id_fixa, relogio.hoje_da_casa()))
        canceladas = [r["id"] for r in cur.fetchall()]
    return {"canceladas": canceladas,
            "message": "Conta fixa encerrada: não gera mais."
                       + (f" {len(canceladas)} conta(s) em aberto cancelada(s)." if canceladas else "")}


def reativar(cur, id_unidade: int, id_fixa: int) -> dict:
    """⚠️ Volta a gerar a partir DESTE mês: os meses em que ficou encerrada não nascem atrasados."""
    f = _travar(cur, id_unidade, id_fixa)
    if f["ativo"]:
        raise HTTPException(status_code=409, detail="Esta conta fixa já está ativa.")
    mes = mes_da(relogio.hoje_da_casa())
    cur.execute("""UPDATE contas_fixas SET ativo = true, encerrado_por = NULL, encerrado_em = NULL,
                          inicio = greatest(inicio, %s),
                          fim = CASE WHEN fim < %s THEN NULL ELSE fim END
                    WHERE id = %s""", (mes, mes, id_fixa))
    _gerar_registrando(cur)
    return {"message": "Conta fixa reativada: volta a gerar a partir deste mês."}
