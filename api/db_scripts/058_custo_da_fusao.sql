-- O custo de referência que a FUSÃO descartava, devolvido ao principal.
--
-- 🔑 **Relatado pelo dono (09/09/2026):** "o produto do PDV não tinha custo, o
-- produto do Omie tinha custo, aí vincula os dois, o produto ficou sem custo".
--
-- A fusão completa no principal o que estiver em branco nele — categoria,
-- setor, unidade, NCM, marca... — e `custo_referencia` **não estava na lista**.
-- É a mesma armadilha que já tinha comido a `marca`: a lista de campos é a
-- fonte única, e um campo novo que não entra nela deixa de migrar sem ninguém
-- notar. O código foi corrigido (`produtos_vinculo`); esta migração repara o
-- que já aconteceu.
--
-- O efeito era silencioso e caro: o principal ficava sem custo, a ficha
-- calculava com zero e o food cost saía bom demais — sem nada denunciando.
--
-- ⚠️ **Só preenche o que está VAZIO.** Custo de verdade nunca é sobrescrito, e
-- rodar de novo não muda nada: é idempotente por construção.
--
-- ⚠️ **A UNIDADE tem de bater.** O custo é sempre POR unidade de estoque:
-- copiar o número quando o absorvido contava em KG e o principal conta em UN
-- poria o preço do quilo no cadastro que conta unidades. Sem esta condição, a
-- reparação criaria um erro pior que o buraco que veio consertar.
--
-- ⚠️ **O elo é a OBSERVAÇÃO do absorvido** (`Fundido em <código> — <nome>`),
-- escrita pela própria fusão, e `produtos.codigo` é único. Não há coluna
-- ligando os dois: a fusão não guardou o par, e inventá-la agora não recupera
-- as fusões que já aconteceram.

WITH origem AS (
    -- DISTINCT ON: um principal pode ter absorvido vários cadastros. Vence o
    -- custo mais RECENTE — embalagem e preço mudam, e o de ontem descreve
    -- melhor a prateleira de hoje que o de dois anos atrás.
    SELECT DISTINCT ON (p.id)
           p.id AS id_principal,
           a.custo_referencia,
           a.custo_referencia_em,
           a.custo_referencia_origem
      FROM produtos p
      JOIN produtos a
        ON a.status = 'ARQUIVADO'
       AND a.id <> p.id
       AND a.observacao LIKE '%Fundido em ' || p.codigo || ' %'
     WHERE (p.custo_referencia IS NULL OR p.custo_referencia = 0)
       AND a.custo_referencia IS NOT NULL
       AND a.custo_referencia > 0
       AND upper(coalesce(p.um_estoque, '')) = upper(coalesce(a.um_estoque, ''))
       AND coalesce(p.um_estoque, '') <> ''
     ORDER BY p.id, a.custo_referencia_em DESC NULLS LAST, a.id DESC
)
UPDATE produtos p
   SET custo_referencia = o.custo_referencia,
       custo_referencia_em = o.custo_referencia_em,
       -- ⚠️ A ORIGEM é preservada, não reescrita: ela existe para daqui a seis
       -- meses dizer se aquele número foi importado ou digitado, e é essa
       -- diferença que decide se ele pode ser sobrescrito sem perguntar.
       custo_referencia_origem = coalesce(o.custo_referencia_origem, 'fusao')
  FROM origem o
 WHERE p.id = o.id_principal;
