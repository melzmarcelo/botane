-- Corrige o custo da ficha CONGELADO nas vendas: por unidade vendida (a porção), não por KG.
--
-- 🔑 **Pedido do dono (26/09/2026):** *"na venda o custo da ficha técnica está indo por KG,
-- não por unidade/porção, que é a correta … organizar o sistema para sempre considerar a
-- porção no custo unitário de uma ficha técnica."* O código já foi corrigido
-- (`custos.custo_unitario_da_ficha`); isto conserta o que JÁ tinha sido gravado.
--
-- A conta: o custo antigo era `total / rendimento`; o certo é `total / porções`
-- (`custos.custo_unitario_da_ficha`): SEMPRE a porção quando há mais de uma; e, com a
-- receita inteira sendo uma porção só de um produto contado em outra unidade, a ponte da
-- produção (1 unidade por receita). Então
--     certo = antigo × rendimento / porções
-- — o que PRESERVA o preço dos ingredientes do dia da venda. É só a divisão que muda.
--
-- ⚠️ O caso da GRANDEZA (receita em G, produto em KG, sem porções) fica de fora: ali o
-- fator depende da tabela de unidades — e a conta antiga já dava certo nele.
-- ⚠️ Só quando o produto tem UMA configuração de rendimento em todas as versões da ficha:
-- com versões diferentes não se sabe qual valia no dia, e chutar seria trocar um erro por
-- outro. Esses ficam como estão (e saem na contagem abaixo, no log do start).
-- ⚠️ Período de CMV FECHADO não se toca: o número dele já foi assinado.
-- ⚠️ **Idempotente pela marca `custo_revisto`**: a coluna nasce nula nas vendas que já
-- existiam e `true` nas novas (que já nascem certas). O UPDATE só pega as nulas e as marca;
-- rodar de novo não divide de novo.

ALTER TABLE venda_itens ADD COLUMN IF NOT EXISTS custo_revisto boolean;
ALTER TABLE venda_itens ALTER COLUMN custo_revisto SET DEFAULT true;

WITH ficha_do_produto AS (
    -- Uma linha por produto — só quando TODAS as versões vivas concordam na configuração.
    SELECT f.id_produto,
           min(f.rendimento_qtd) AS rendimento,
           min(f.porcoes)        AS porcoes,
           min(upper(f.rendimento_um)) AS rendimento_um
      FROM fichas_tecnicas f
     WHERE f.status IN ('HOMOLOGADA', 'RASCUNHO', 'ARQUIVADA')
     GROUP BY f.id_produto
    HAVING count(DISTINCT (f.rendimento_qtd, f.porcoes, upper(coalesce(f.rendimento_um, ''))))
           = 1
),
alvo AS (
    SELECT vi.id, fp.rendimento / fp.porcoes AS fator
      FROM venda_itens vi
      JOIN vendas v ON v.id = vi.id_venda
      JOIN produtos p ON p.id = vi.id_produto
      JOIN ficha_do_produto fp ON fp.id_produto = vi.id_produto
     WHERE vi.custo_revisto IS NULL
       AND vi.origem_custo LIKE 'ficha%'
       AND vi.custo_ficha_unitario IS NOT NULL
       AND fp.rendimento > 0 AND fp.porcoes > 0
       AND (fp.porcoes > 1
            OR (fp.rendimento_um IS NOT NULL AND p.um_estoque IS NOT NULL
                AND fp.rendimento_um <> upper(p.um_estoque)))
       AND fp.rendimento <> fp.porcoes
       AND NOT EXISTS (
            SELECT 1 FROM cmv_fechamentos c
             WHERE c.id_unidade = v.id_unidade AND c.status = 'FECHADO'
               AND v.data BETWEEN c.inicio AND c.fim)
)
UPDATE venda_itens vi
   SET custo_ficha_unitario = round(vi.custo_ficha_unitario * alvo.fator, 6),
       custo_revisto = true
  FROM alvo
 WHERE vi.id = alvo.id;

-- O resto das linhas antigas: conferidas, não precisavam de conserto (ou não dava para
-- saber qual versão valia). Marcadas para a próxima passada não as olhar de novo.
UPDATE venda_itens SET custo_revisto = true WHERE custo_revisto IS NULL;
