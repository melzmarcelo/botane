"""Quando um produto está EM USO numa loja — a pergunta feita num lugar só.

🔑 **Por que existe (05/10/2026).** O alerta "Produto em rascunho" marcava 1.356
no ar e ninguém o lia: quase todos são resíduo da carga do catálogo do Omie,
cadastros que nunca apareceram em nota, venda ou prateleira. Os que IMPORTAM
são os que a operação já está tocando — e esses ficavam enterrados no meio.

"Em uso" é qualquer uma das três:

* aparece em nota de entrada ainda ABERTA (vai travar o lançamento dela);
* foi vendido nos últimos 30 dias;
* tem saldo — positivo ou negativo — em alguma prateleira.

⚠️ **A condição é escrita UMA vez** e usada pelo alerta e pelo filtro da lista
de produtos: se as duas discordassem, o alerta diria 40 e a lista aberta por
ele mostraria outro número.
"""

# Espera o alias `p` para `produtos`. A loja aparece TRÊS vezes e entra por
# `.format(u=...)` com o marcador de quem chama: `%(u)s` (parâmetro nomeado) ou
# `%s` (posicional — aí são três valores na tupla, na ordem).
EM_USO = """(
    EXISTS (SELECT 1 FROM nota_itens ni JOIN notas_entrada ne ON ne.id = ni.id_nota
             WHERE ni.id_produto = p.id AND NOT ni.ignorado AND ne.id_unidade = {u}
               AND ne.status IN ('IMPORTADA', 'CONCILIADA'))
    OR EXISTS (SELECT 1 FROM venda_itens vi JOIN vendas ve ON ve.id = vi.id_venda
                WHERE vi.id_produto = p.id AND ve.id_unidade = {u} AND NOT ve.cancelada
                  AND ve.data >= current_date - 30)
    OR EXISTS (SELECT 1 FROM estoque_saldos es
                WHERE es.id_produto = p.id AND es.id_unidade = {u} AND es.quantidade <> 0)
)"""
