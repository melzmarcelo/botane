"""Traz as vendas do PDV Legal e as entrega ao caminho que já existia.

⚠️ **Este arquivo não sabe gravar venda.** Ele busca, traduz e passa adiante: o
destino é o mesmo `/vendas/importar` que a planilha usa, com o mesmo de-para, o
mesmo congelamento do custo da ficha e a mesma baixa de estoque. Era o que o
mapeamento previa — *"quando a API abrir, muda a fonte e não o resto"* — e é o
que impede o CMV de ter duas contas conforme a origem da venda.

⚠️ **A busca é DIA A DIA, e isso não é preciosismo.** A documentação do
`cupom/get` diz: intervalo máximo de 10 dias e **no máximo 100 registros**,
*"obs: se a data inicial e final forem iguais não existe limitação"*. Uma casa
com 48 cupons num dia comum estoura o teto em três dias de janela — e o corte
seria silencioso: 100 é um número plausível, ninguém veria falta nenhuma, e o
CMV do período sairia com receita a menos.
"""

from datetime import date, timedelta

from services.pdv import mapeadores, vinculo
from services.pdv.cliente import ClientePdv, ErroPdv

ORIGEM = "PDV_LEGAL"

# Teto de dias por chamada de sincronização. Não é limite da API — é limite de
# paciência: 60 dias são 60 requisições, e uma tela que fica dois minutos
# esperando parece travada.
TETO_DE_DIAS = 60


def janela(cur, id_unidade: int, dias: int | None, desde: date | None) -> tuple[date, date]:
    """De quando até quando buscar.

    ⚠️ **Sem parâmetro, vai desde a última venda importada com 2 dias de folga.**
    A folga existe porque cupom lançado com atraso (a venda de ontem que o caixa
    só fechou hoje) cairia fora se a janela começasse onde a anterior parou — e
    ninguém veria, porque o resultado seria "0 novas".
    """
    hoje = date.today()
    if desde:
        return desde, hoje
    if dias:
        return hoje - timedelta(days=dias - 1), hoje

    cur.execute(
        """SELECT max(data) AS ultima FROM vendas
            WHERE id_unidade = %s AND origem = %s""",
        (id_unidade, ORIGEM),
    )
    ultima = (cur.fetchone() or {}).get("ultima")
    if not ultima:
        # Primeira vez: uma semana. Buscar o histórico inteiro é decisão de quem
        # manda `desde=`, não um efeito colateral do primeiro clique.
        return hoje - timedelta(days=7), hoje
    return min(ultima - timedelta(days=2), hoje), hoje


def buscar(cliente: ClientePdv, filiais: str, inicio: date, fim: date) -> list[dict]:
    """Os cupons do período, um dia por chamada.

    Devolve a lista já traduzida. Cupom e item cancelados vêm junto: quem decide
    o que fazer com eles é `preparar`, e jogá-los fora aqui esconderia da tela
    quantos foram.
    """
    dias = (fim - inicio).days + 1
    if dias > TETO_DE_DIAS:
        inicio = fim - timedelta(days=TETO_DE_DIAS - 1)

    cupons: list[dict] = []
    d = inicio
    while d <= fim:
        # ⚠️ `d/d` — data inicial IGUAL à final. É a única forma sem teto de 100.
        bruto = cliente.get(f"/cupom/get/{d.isoformat()}/{d.isoformat()}/{filiais}")
        cupons.extend(mapeadores.lista_de_cupons(bruto))
        d += timedelta(days=1)
    return cupons


def preparar(cupons: list[dict], vinculos: dict[str, int] | None = None
             ) -> tuple[list[dict], dict]:
    """Separa o que vira venda do que não vira, e conta os dois.

    ⚠️ **Cupom cancelado não entra**, e **item cancelado dentro de cupom válido
    também não**: contá-lo infla a receita e o CMV teórico do período. São dois
    níveis de cancelamento, e o segundo é o que passa despercebido.

    ⚠️ **Cupom que fica sem item nenhum some.** Um cupom cujas linhas foram todas
    canceladas é um cupom cancelado na prática; gravá-lo vazio criaria uma venda
    de valor zero que aparece na contagem e não explica nada.
    """
    vendas, resumo = [], {"cancelados": 0, "itens_cancelados": 0, "sem_item": 0}

    for c in cupons:
        if c["cancelada"]:
            resumo["cancelados"] += 1
            continue

        itens = []
        for i in c["itens"]:
            if i["cancelado"]:
                resumo["itens_cancelados"] += 1
                continue
            if i["quantidade"] <= 0:
                continue
            # ⚠️ O vínculo vai RESOLVIDO daqui. O importador de vendas procura
            # produto pelo código DA CASA e pelo nome; o código do PDV é outra
            # coisa, e sem esta linha toda venda entraria sem vínculo mesmo com
            # o de-para montado.
            itens.append({
                "id_produto": (vinculos or {}).get(i["codigo"] or ""),
                "codigo": i["codigo"],
                "descricao": i["descricao"],
                "quantidade": float(i["quantidade"]),
                "valor_unitario": float(i["valor_unitario"]),
            })

        if not itens:
            resumo["sem_item"] += 1
            continue

        vendas.append({
            "data": c["data"],
            "documento": c["documento"],
            "canal": c["canal"],
            "origem": ORIGEM,
            "itens": itens,
        })

    return vendas, resumo


def sincronizar(cur, cliente: ClientePdv, id_unidade: int, filiais: str,
                dias: int | None = None, desde: date | None = None) -> dict:
    """Busca e prepara. **Quem grava é o importador de vendas**, não este arquivo.

    Devolve o que a tela precisa dizer: o período, quantos cupons vieram, quantos
    foram descartados e por quê, e a lista pronta para gravar.
    """
    inicio, fim = janela(cur, id_unidade, dias, desde)
    try:
        cupons = buscar(cliente, filiais, inicio, fim)
    except ErroPdv:
        raise
    vendas, resumo = preparar(cupons, vinculo.de_para(cur))
    return {
        "inicio": inicio,
        "fim": fim,
        "janela": f"{inicio.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}",
        "cupons": len(cupons),
        "vendas": vendas,
        **resumo,
    }
