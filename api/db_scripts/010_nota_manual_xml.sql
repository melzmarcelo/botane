-- Botané 010 — nota de entrada por XML da NF-e e por digitação manual.
-- Idempotente.

-- O XML já traz frete e impostos POR ITEM quando o fornecedor rateou. Nesse
-- caso não se rateia de novo: usa-se o que veio. As colunas guardam o valor
-- informado; NULL significa "rateie você".
ALTER TABLE nota_itens ADD COLUMN IF NOT EXISTS frete_informado  numeric(18,2);
ALTER TABLE nota_itens ADD COLUMN IF NOT EXISTS outros_informado numeric(18,2);

-- O XML como veio, para auditoria e para reprocessar se algum campo mudar de
-- interpretação depois.
ALTER TABLE notas_entrada ADD COLUMN IF NOT EXISTS xml_bruto text;

-- Nota digitada na mão não tem chave da NF-e; a unicidade passa a ser
-- fornecedor + número + série, senão a mesma nota entra duas vezes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_nota_manual
    ON notas_entrada (id_unidade, id_fornecedor, numero, coalesce(serie, ''))
    WHERE chave_nfe IS NULL AND id_fornecedor IS NOT NULL AND numero IS NOT NULL;
