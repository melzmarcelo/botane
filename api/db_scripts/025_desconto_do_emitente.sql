-- O desconto que estava sendo tirado DUAS vezes — o espelho do frete (024).
--
-- O `vTotalItem` do Omie já vem líquido do desconto do item, e o
-- `vTotalDescontos` da nota é a SOMA desses mesmos descontos. O importador
-- gravava o item pelo `vTotalItem` (já líquido), subtraía o `vDesconto` de
-- novo e ainda rateava o total da nota por cima. Numa nota real:
--
--     item: 1 × 27,55 com vDesconto 1,36 → vTotalItem 26,19
--     custo gravado: 26,19 − 1,36 − 1,36 = 23,47   ← 10% ABAIXO da nota
--
-- A 024 já tinha posto a mercadoria em quantidade × preço, mas só nas notas em
-- que o emitente rateou frete. Esta termina o serviço em todas as notas do
-- Omie e zera o desconto da nota que já está nos itens.
--
-- ⚠️ Reescreve `nota_itens`, não o razão. Nota já LANÇADA precisa de estorno e
-- novo lançamento para o custo médio se corrigir.
--
-- Idempotente: depois da primeira vez a mercadoria já é quantidade × preço e o
-- desconto da nota já está sem a parte que mora nos itens.

WITH do_bruto AS (
    SELECT n.id                                                                AS id_nota,
           (item.dado -> 'itensCabec' ->> 'nSequencia')::int                   AS seq,
           coalesce((item.dado -> 'itensCabec' ->> 'nQtdeNFe')::numeric, 0)    AS qtd,
           coalesce((item.dado -> 'itensCabec' ->> 'nPrecoUnit')::numeric, 0)  AS preco,
           coalesce((item.dado -> 'itensCabec' ->> 'vDesconto')::numeric, 0)   AS desconto
      FROM notas_entrada n
           CROSS JOIN LATERAL jsonb_array_elements(
               coalesce(n.bruto -> 'itensRecebimento', '[]'::jsonb)) AS item(dado)
     WHERE n.bruto ? 'itensRecebimento'
)
UPDATE nota_itens i
   SET valor_total    = s.qtd * s.preco,
       valor_desconto = s.desconto
  FROM do_bruto s
 WHERE i.id_nota = s.id_nota AND i.seq = s.seq;

-- O desconto da NOTA passa a ser só o que não está em item nenhum. Sem isto o
-- rateio por valor tiraria de novo o que cada item já tirou.
UPDATE notas_entrada n
   SET valor_desconto = greatest(
           coalesce((n.bruto -> 'totais' ->> 'vTotalDescontos')::numeric, 0)
           - coalesce((SELECT sum(coalesce(
                          (item.dado -> 'itensCabec' ->> 'vDesconto')::numeric, 0))
                         FROM jsonb_array_elements(
                              coalesce(n.bruto -> 'itensRecebimento', '[]'::jsonb))
                              AS item(dado)), 0),
           0)
 WHERE n.bruto ? 'itensRecebimento';
