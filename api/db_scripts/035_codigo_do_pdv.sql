-- Botané 035 — o código do PDV vira campo do produto. Idempotente.
--
-- `produtos.codigo_omie` já era o vínculo com o Omie: uma coluna, única, que
-- sobrevive à troca do código da casa. O PDV não tinha equivalente — o vínculo
-- morava só em `codigos_externos`, invisível na tela do produto. Agora os dois
-- se leem lado a lado: **com os dois preenchidos, o cadastro é o mesmo produto
-- nas duas integrações**, e isso se enxerga sem abrir o banco.
--
-- ⚠️ **A coluna é o vínculo PRINCIPAL, não o único.** `codigos_externos`
-- continua guardando os APELIDOS, porque o caso é real: na conta do cliente,
-- "ENTREGA" tem QUATRO códigos de cardápio distintos apontando para a mesma
-- coisa. Uma coluna sozinha guardaria um e os outros três voltariam a virar
-- rascunho na importação seguinte — o duplicado renascendo sozinho.
--
-- A resolução do item de venda passa a ser: a coluna primeiro, os apelidos
-- depois. Uma regra, escrita num lugar só (`services/pdv/vinculo.py`).

ALTER TABLE produtos
    ADD COLUMN IF NOT EXISTS codigo_pdv varchar(40);

-- ⚠️ Único e PARCIAL, igual ao `ux_produto_omie`: nulo é o estado da esmagadora
-- maioria dos cadastros (todo insumo que não se vende no balcão), e um índice
-- único comum trataria os nulos como... nada — no Postgres eles não colidem,
-- mas o índice cheio de nulos é peso sem uso.
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_pdv
    ON produtos (codigo_pdv) WHERE codigo_pdv IS NOT NULL;

-- Traz para a coluna o que já está no de-para: para cada produto, UM código —
-- o menor, para a escolha ser estável entre execuções. Os demais ficam onde
-- estão e passam a ser os apelidos.
--
-- ⚠️ `DISTINCT ON` com a mesma ordenação do `ORDER BY` é o que garante um por
-- produto; sem isso o UPDATE tentaria gravar vários e o índice único recusaria.
UPDATE produtos p
   SET codigo_pdv = escolhido.codigo
  FROM (
        SELECT DISTINCT ON (id_produto) id_produto, codigo
          FROM codigos_externos
         WHERE sistema = 'PDV_LEGAL'
         ORDER BY id_produto, codigo
       ) AS escolhido
 WHERE p.id = escolhido.id_produto
   AND p.codigo_pdv IS NULL;
