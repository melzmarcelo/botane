"""A conferência ANTES de fechar o período — o que ainda distorce o número.

🔑 **Por que existe (05/10/2026).** Fechar congela a apuração e a movimentação
que vai ao contador, e até aqui congelava o que estivesse lá. No ar, setembro
tinha R$ 235 mil de receita e um CMV real de R$ 3 mil: 94 notas conciliadas não
tinham sido lançadas, havia saldo negativo e 797 saídas com custo provisório.
Nada disso aparecia no caminho de quem clicava em "Fechar".

🔑 **AVISA, não impede.** Fechar com pendência é decisão de quem fecha — às
vezes a nota do dia 30 só chega no dia 5 e o contador não espera. Travar
empurraria a casa a não fechar nunca, que é pior: sem fechamento nada impede
lançar para trás. O que muda é que a pendência passa a ser VISTA antes do
botão, e fica registrada na auditoria do fechamento.

⚠️ **Tudo do PERÍODO e da LOJA**, não "de agora": o alerta da tela inicial
conta os últimos 30 dias; aqui a pergunta é o que distorce ESTE recorte.
A exceção é o saldo negativo, que só existe como estado de agora — e a frase
diz isso.
"""
from __future__ import annotations

from datetime import date, timedelta

from services import cmv as motor

IMPEDE_O_NUMERO = "distorce"   # muda o CMV do período
PEDE_OLHO = "atencao"          # não muda a conta, mas vale conferir


def _um(cur, sql: str, params: dict) -> dict:
    cur.execute(sql, params)
    return dict(cur.fetchone() or {})


def conferir(cur, id_unidade: int, inicio: date, fim: date) -> dict:
    """As pendências do período, cada uma com quantos, quanto e onde resolver.

    Devolve só o que TEM pendência — lista vazia quer dizer "pode fechar sem
    susto", e é isso que a tela diz.
    """
    p = {"u": id_unidade, "inicio": inicio, "limite": fim + timedelta(days=1), "fim": fim}
    itens: list[dict] = []

    def juntar(chave: str, peso: str, titulo: str, quantidade, detalhe: str, href: str,
               valor=None) -> None:
        if quantidade:
            itens.append({"chave": chave, "peso": peso, "titulo": titulo,
                          "quantidade": int(quantidade), "detalhe": detalhe, "href": href,
                          "valor": float(valor) if valor is not None else None})

    # ------------------------------------------------------------ compras
    r = _um(cur, """
        SELECT count(*) AS n, coalesce(sum(n.valor_total), 0) AS valor
          FROM notas_entrada n
         WHERE n.id_unidade = %(u)s AND n.status IN ('IMPORTADA', 'CONCILIADA')
           AND coalesce(n.data_entrada, n.data_emissao) >= %(inicio)s
           AND coalesce(n.data_entrada, n.data_emissao) < %(limite)s""", p)
    juntar("notas_nao_lancadas", IMPEDE_O_NUMERO, "Nota do período ainda não lançada",
           r.get("n"),
           "A compra não entrou no estoque: fica fora das compras do período, e o que foi "
           "vendido dela saiu sem saldo.",
           "/compras", r.get("valor"))

    # ------------------------------------------------------------ estoque
    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_movimentos
         WHERE id_unidade = %(u)s AND custo_provisorio
           AND data_movimento >= %(inicio)s AND data_movimento < %(limite)s""", p)
    juntar("custo_provisorio", IMPEDE_O_NUMERO, "Saída com custo provisório no período",
           r.get("n"),
           "Saiu sem saldo e usou o último custo conhecido — o custo dessas saídas é "
           "aproximado até a entrada que faltava ser lançada.",
           "/estoque")

    r = _um(cur, """
        SELECT count(*) AS n FROM estoque_saldos s
          JOIN produtos pr ON pr.id = s.id_produto
         WHERE s.id_unidade = %(u)s AND pr.ativo AND s.quantidade < 0""", p)
    juntar("saldo_negativo", IMPEDE_O_NUMERO, "Produto com saldo negativo hoje", r.get("n"),
           "O estoque final entra na conta com valor negativo. Falta uma entrada ou a "
           "contagem está errada.",
           "/estoque")

    r = _um(cur, """
        SELECT count(*) AS n FROM inventarios
         WHERE id_unidade = %(u)s AND status = 'ABERTO'
           AND data >= %(inicio)s AND data <= %(fim)s""", p)
    juntar("inventario_aberto", PEDE_OLHO, "Contagem de inventário em aberto", r.get("n"),
           "O ajuste da contagem só entra no estoque quando ela é fechada.",
           "/inventario")

    # ------------------------------------------------------------ vendas
    r = _um(cur, """
        SELECT count(*) AS n, coalesce(sum(vi.valor_total), 0) AS valor
          FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
         WHERE v.id_unidade = %(u)s AND NOT v.cancelada AND vi.id_produto IS NULL
           AND v.data >= %(inicio)s AND v.data <= %(fim)s""", p)
    juntar("vendas_sem_vinculo", IMPEDE_O_NUMERO, "Item vendido sem produto vinculado",
           r.get("n"),
           "A venda entra na receita, mas não baixa estoque nem tem custo teórico.",
           "/vendas/sem-vinculo", r.get("valor"))

    # ------------------------------------------------------------ a conta
    apuracao = motor.apurar(cur, id_unidade, inicio, fim)
    if float(apuracao["estoque_inicial"]) < 0:
        juntar("estoque_inicial_negativo", IMPEDE_O_NUMERO,
               "O período começa com estoque negativo", 1,
               "O estoque inicial é a base da conta. Negativo quer dizer saída lançada antes "
               "da entrada correspondente.",
               "/cmv", apuracao["estoque_inicial"])
    if float(apuracao["cmv_real"]) < 0:
        juntar("cmv_negativo", IMPEDE_O_NUMERO, "O CMV real do período está negativo", 1,
               "O estoque cresceu mais do que as compras lançadas explicam. Quase sempre é "
               "entrada sem nota ou nota de outro período.",
               "/cmv", apuracao["cmv_real"])

    # ⚠️ A identidade da movimentação: inicial + entradas − saídas = final. É a
    # conta que vai ao contador, congelada junto com o fechamento.
    linhas = motor.movimentacao_por_produto(cur, id_unidade, inicio, fim)
    abertos, diferenca = 0, 0.0
    for l in linhas:
        d = (float(l["valor_inicial"]) + float(l["valor_entradas"])
             - float(l["valor_saidas"]) - float(l["valor_final"]))
        # Um centavo por produto é arredondamento do custo médio, não defeito.
        if abs(d) > 0.02:
            abertos += 1
            diferenca += d
    juntar("movimentacao_nao_fecha", IMPEDE_O_NUMERO,
           "A movimentação não fecha em algum produto", abertos,
           "Inicial + entradas − saídas não dá o final. A causa comum é lançamento com data "
           "de trás, feito depois de outros movimentos do mesmo produto.",
           "/cmv", diferenca)

    cobertura = float(apuracao.get("cobertura_ficha_pct") or 0)
    if float(apuracao.get("receita") or 0) > 0 and cobertura < 50:
        em_texto = f"{cobertura:.1f}".replace(".", ",")
        juntar("cobertura_baixa", PEDE_OLHO, "Pouca receita coberta por ficha técnica", 1,
               f"Só {em_texto}% da receita tem custo de ficha. O CMV teórico, a "
               "variância e o food cost deste período não representam a casa.",
               "/fichas")

    return {
        "inicio": str(inicio), "fim": str(fim),
        "itens": itens,
        "distorcem": sum(1 for i in itens if i["peso"] == IMPEDE_O_NUMERO),
        "limpo": not itens,
    }
