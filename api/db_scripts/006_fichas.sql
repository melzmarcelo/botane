-- Botané 006 — fichas técnicas: a receita de cada produto de produção própria
-- e o custo que ela gera. Idempotente.

CREATE TABLE IF NOT EXISTS fichas_tecnicas (
    id                serial PRIMARY KEY,
    id_produto        integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    versao            smallint NOT NULL DEFAULT 1,
    status            varchar(12) NOT NULL DEFAULT 'RASCUNHO',  -- RASCUNHO|HOMOLOGADA|ARQUIVADA
    rendimento_qtd    numeric(18,4) NOT NULL DEFAULT 1,
    rendimento_um     varchar(6) REFERENCES unidades_medida(sigla),
    porcoes           numeric(10,2) NOT NULL DEFAULT 1,
    tempo_preparo_min smallint,
    modo_preparo      text,
    alergenos         text,
    foto_url          text,
    observacao        text,
    vigente_de        date NOT NULL DEFAULT current_date,
    vigente_ate       date,
    homologada_por    integer REFERENCES usuarios(id),
    homologada_em     timestamptz,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    criado_por        integer REFERENCES usuarios(id),
    CONSTRAINT ck_ficha_porcoes CHECK (porcoes > 0),
    CONSTRAINT ck_ficha_rendimento CHECK (rendimento_qtd > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ficha_versao ON fichas_tecnicas (id_produto, versao);
-- Uma homologada vigente por produto: é ela que o custo teórico usa.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ficha_vigente
    ON fichas_tecnicas (id_produto)
    WHERE status = 'HOMOLOGADA' AND vigente_ate IS NULL;
CREATE INDEX IF NOT EXISTS ix_ficha_produto ON fichas_tecnicas (id_produto, status);

CREATE TABLE IF NOT EXISTS ficha_itens (
    id               serial PRIMARY KEY,
    id_ficha         integer NOT NULL REFERENCES fichas_tecnicas(id) ON DELETE CASCADE,
    id_insumo        integer REFERENCES produtos(id) ON DELETE RESTRICT,
    id_subficha      integer REFERENCES fichas_tecnicas(id) ON DELETE RESTRICT,
    -- Bruta é o que SAI do estoque (é ela que custa); líquida é o que fica no prato.
    qtd_bruta        numeric(18,4) NOT NULL,
    qtd_liquida      numeric(18,4),
    um               varchar(6) REFERENCES unidades_medida(sigla),
    fator_correcao   numeric(10,4) NOT NULL DEFAULT 1,   -- bruta ÷ líquida
    fator_coccao     numeric(10,4) NOT NULL DEFAULT 1,   -- muda rendimento, não custo
    observacao       text,
    ordem            smallint NOT NULL DEFAULT 0,
    CONSTRAINT ck_item_alvo CHECK (
        (id_insumo IS NOT NULL AND id_subficha IS NULL)
        OR (id_insumo IS NULL AND id_subficha IS NOT NULL)
    ),
    CONSTRAINT ck_item_qtd CHECK (qtd_bruta > 0)
);
CREATE INDEX IF NOT EXISTS ix_ficha_itens_ficha ON ficha_itens (id_ficha, ordem);
CREATE INDEX IF NOT EXISTS ix_ficha_itens_insumo ON ficha_itens (id_insumo);
CREATE INDEX IF NOT EXISTS ix_ficha_itens_subficha ON ficha_itens (id_subficha);
-- Ciclo (ficha que usa a si mesma, direta ou indiretamente) é recusado na
-- gravação pelo service: em banco a checagem exigiria trigger recursivo.
