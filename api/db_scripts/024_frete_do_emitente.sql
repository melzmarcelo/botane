-- O frete que estava entrando DUAS vezes nas notas vindas do Omie.
--
-- O `vTotalItem` do recebimento de NF-e já vem com o frete e o IPI/ST rateados
-- pelo emitente. O importador tratava esse valor como mercadoria e rateava as
-- acessórias da nota de novo por cima. Numa nota real:
--
--     vTotalProdutos 256,00 + vFrete 40,00 = vTotalNFe 296,00
--     item: 2 × 128,00 = 256,00, mas vTotalItem = 296,00
--     custo gravado: 296,00 + 40,00 = 336,00   ← 13,5% acima da nota
--
-- Numa base de 30 notas foram R$ 74,44 a mais no razão. O erro contamina o
-- custo médio, e dali a ficha técnica, o CMV e a variância.
--
-- `mapeadores._acessorias_do_emitente` corrige a entrada; isto corrige o que
-- entrou antes. A mercadoria volta a ser quantidade × preço, e a sobra vira
-- acessória INFORMADA — que é o que impede o rateio por valor de somar de novo.
-- É a mesma regra que o caminho do XML já seguia.
--
-- ⚠️ Isto reescreve `nota_itens`, não o razão. Nota já LANÇADA precisa ser
-- estornada e lançada de novo para o custo médio se corrigir — o razão é
-- append-only, e correção lá é contrapartida, nunca UPDATE.
--
-- Idempotente: rodar de novo não muda nada, porque depois da primeira vez a
-- mercadoria já é quantidade × preço e a sobra já está em `frete_informado`.

WITH do_bruto AS (
    SELECT n.id                                          AS id_nota,
           (item.dado -> 'itensCabec' ->> 'nSequencia')::int          AS seq,
           coalesce((item.dado -> 'itensCabec' ->> 'nQtdeNFe')::numeric, 0)   AS qtd,
           coalesce((item.dado -> 'itensCabec' ->> 'nPrecoUnit')::numeric, 0) AS preco,
           coalesce((item.dado -> 'itensCabec' ->> 'vDesconto')::numeric, 0)  AS desconto,
           coalesce((item.dado -> 'itensCabec' ->> 'vTotalItem')::numeric, 0) AS total_item,
           coalesce(n.valor_frete, 0)                    AS frete_nota,
           coalesce(n.valor_outros, 0)                   AS outros_nota
      FROM notas_entrada n
           CROSS JOIN LATERAL jsonb_array_elements(
               coalesce(n.bruto -> 'itensRecebimento', '[]'::jsonb)) AS item(dado)
     WHERE n.bruto ? 'itensRecebimento'
),
com_sobra AS (
    SELECT *, greatest(total_item - (qtd * preco - desconto), 0) AS sobra
      FROM do_bruto
),
-- O rateio é do emitente só quando ALGUM item da nota traz sobra. Onde não
-- traz, as acessórias continuam sendo rateadas por valor, como sempre.
notas_rateadas AS (
    SELECT id_nota FROM com_sobra GROUP BY id_nota HAVING max(sobra) > 0.005
)
UPDATE nota_itens i
   SET valor_total      = s.qtd * s.preco,
       valor_desconto   = s.desconto,
       frete_informado  = CASE WHEN s.frete_nota + s.outros_nota > 0
                               THEN round(s.sobra * s.frete_nota
                                          / (s.frete_nota + s.outros_nota), 2)
                               ELSE s.sobra END,
       outros_informado = s.sobra - CASE WHEN s.frete_nota + s.outros_nota > 0
                                         THEN round(s.sobra * s.frete_nota
                                                    / (s.frete_nota + s.outros_nota), 2)
                                         ELSE s.sobra END
  FROM com_sobra s
 WHERE i.id_nota = s.id_nota
   AND i.seq = s.seq
   AND s.id_nota IN (SELECT id_nota FROM notas_rateadas);
