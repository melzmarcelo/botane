-- 161 — Finalizadoras, etapas 3 e 4: a conferência do caixa e a taxa de cada forma.
-- Idempotente. Só cria tabelas e a permissão: não reescreve dado nenhum.
--
-- 🔑 **Pedido do dono (24/11/2026)**: seguir com as etapas pendentes do estudo
-- `docs/pdv-finalizadoras-estudo.md` depois das finalizadoras (160).
--
-- 🔑 **Caixa**: o ESPERADO não se guarda — sai das finalizadoras do dia (dinheiro − troco), e
-- muda se o dia for relido. Guarda-se o CONTADO, quem contou e quando; a diferença é conta.
-- 🔑 **Taxas**: por loja e por forma. Não substitui a linha de cartão da Precificação (que é
-- texto livre e incide no preço): serve para estimar quanto o cartão levou e para mostrar a
-- taxa média REAL, pelo peso de cada forma nas vendas.

CREATE TABLE IF NOT EXISTS caixa_conferencias (
    id            serial PRIMARY KEY,
    id_unidade    integer NOT NULL REFERENCES unidades(id),
    data          date NOT NULL,
    contado       numeric(14,2) NOT NULL CHECK (contado >= 0),
    observacao    varchar(300),
    conferido_por integer REFERENCES usuarios(id),
    conferido_em  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_unidade, data)
);

CREATE TABLE IF NOT EXISTS forma_pagamento_taxas (
    id_unidade     integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    grupo          varchar(12) NOT NULL
                   CHECK (grupo IN ('DINHEIRO', 'CREDITO', 'DEBITO', 'PIX', 'VALE', 'OUTRO')),
    taxa_pct       numeric(6,3) NOT NULL CHECK (taxa_pct >= 0 AND taxa_pct < 100),
    atualizado_por integer REFERENCES usuarios(id),
    atualizado_em  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, grupo)
);

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('vendas.caixa', 'Vendas', 'Conferir o caixa: dinheiro esperado × contado, por dia', 545)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'vendas.caixa'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;
