-- Botané 015 — várias unidades de compra por produto, e acréscimo no item da
-- nota. Idempotente.
--
-- O produto tem UMA unidade de estoque (é nela que o saldo e o custo vivem),
-- mas se compra em várias: a mesma água vem em caixa de 12, fardo de 6 e
-- palete de 480. `produtos.fator_compra` só guardava um número, então quem
-- comprasse no palete tinha de corrigir a conversão na mão a cada nota.
CREATE TABLE IF NOT EXISTS produto_unidades (
    id          serial PRIMARY KEY,
    id_produto  integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    um          varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    -- Quantas unidades de ESTOQUE vêm em uma unidade desta: CX de 12 un = 12.
    fator       numeric(18,6) NOT NULL,
    padrao      boolean NOT NULL DEFAULT false,
    observacao  varchar(120),
    criado_em   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_produto_unidade_fator CHECK (fator > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_unidade
    ON produto_unidades (id_produto, upper(um));
-- Uma padrão por produto: é a que a tela sugere.
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_unidade_padrao
    ON produto_unidades (id_produto) WHERE padrao;
CREATE INDEX IF NOT EXISTS ix_produto_unidade_produto ON produto_unidades (id_produto);

-- O que já estava em `produtos.um_compra`/`fator_compra` vira a primeira linha,
-- marcada como padrão: ninguém perde conversão ao subir esta versão.
INSERT INTO produto_unidades (id_produto, um, fator, padrao)
SELECT p.id, p.um_compra, p.fator_compra, true
  FROM produtos p
 WHERE p.um_compra IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM produto_unidades u
                    WHERE u.id_produto = p.id AND upper(u.um) = upper(p.um_compra));

-- Acréscimo por item da nota. O desconto já existia; faltava o outro lado —
-- taxa de entrega, embalagem cobrada à parte, ajuste do fornecedor.
ALTER TABLE nota_itens ADD COLUMN IF NOT EXISTS valor_acrescimo numeric(18,2) NOT NULL DEFAULT 0;
