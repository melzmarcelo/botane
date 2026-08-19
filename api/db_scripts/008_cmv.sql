-- Botané 008 — vendas e fechamento de CMV. Idempotente.

CREATE TABLE IF NOT EXISTS vendas (
    id           bigserial PRIMARY KEY,
    id_unidade   integer NOT NULL REFERENCES unidades(id),
    data         date NOT NULL,
    hora         time,
    origem       varchar(20) NOT NULL DEFAULT 'PLANILHA',  -- PDV_LEGAL|IFOOD|PLANILHA|MANUAL
    canal        varchar(20),                              -- SALAO|BALCAO|DELIVERY|EVENTO
    documento    varchar(40),
    id_externo   varchar(60),
    mesa         varchar(20),
    valor_total  numeric(18,2) NOT NULL DEFAULT 0,
    desconto     numeric(18,2) NOT NULL DEFAULT 0,
    cancelada    boolean NOT NULL DEFAULT false,
    importada_em timestamptz NOT NULL DEFAULT now(),
    id_usuario   integer REFERENCES usuarios(id)
);
-- Idempotência da importação é do BANCO: reimportar o mesmo arquivo não duplica.
CREATE UNIQUE INDEX IF NOT EXISTS ux_venda_documento
    ON vendas (id_unidade, origem, documento) WHERE documento IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_venda_data ON vendas (id_unidade, data);

CREATE TABLE IF NOT EXISTS venda_itens (
    id                   bigserial PRIMARY KEY,
    id_venda             bigint NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    codigo_pdv           varchar(60),
    descricao_pdv        varchar(200),
    id_produto           integer REFERENCES produtos(id),   -- NULL = prato sem de-para
    quantidade           numeric(18,4) NOT NULL,
    valor_unitario       numeric(18,2) NOT NULL DEFAULT 0,
    valor_total          numeric(18,2) NOT NULL DEFAULT 0,
    -- Congelado na importação: o CMV teórico do passado não muda quando alguém
    -- edita a receita hoje.
    custo_ficha_unitario numeric(18,6),
    origem_custo         varchar(20)
);
CREATE INDEX IF NOT EXISTS ix_venda_item_produto ON venda_itens (id_produto);
CREATE INDEX IF NOT EXISTS ix_venda_item_venda ON venda_itens (id_venda);

-- O fechamento congela o período: depois dele, movimento retroativo é recusado
-- (a menos que quem lance tenha `estoque.retroativo`).
CREATE TABLE IF NOT EXISTS cmv_fechamentos (
    id              serial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    competencia     date NOT NULL,          -- primeiro dia do mês
    inicio          date NOT NULL,
    fim             date NOT NULL,
    estoque_inicial numeric(18,2) NOT NULL DEFAULT 0,
    compras         numeric(18,2) NOT NULL DEFAULT 0,
    estoque_final   numeric(18,2) NOT NULL DEFAULT 0,
    cmv_real        numeric(18,2) NOT NULL DEFAULT 0,
    cmv_teorico     numeric(18,2) NOT NULL DEFAULT 0,
    variancia       numeric(18,2) NOT NULL DEFAULT 0,
    perdas          numeric(18,2) NOT NULL DEFAULT 0,
    consumo_interno numeric(18,2) NOT NULL DEFAULT 0,
    ajustes         numeric(18,2) NOT NULL DEFAULT 0,
    receita         numeric(18,2) NOT NULL DEFAULT 0,
    food_cost_pct   numeric(7,3),
    status          varchar(12) NOT NULL DEFAULT 'FECHADO',  -- FECHADO|REABERTO
    detalhe         jsonb,
    fechado_por     integer REFERENCES usuarios(id),
    fechado_em      timestamptz NOT NULL DEFAULT now(),
    reaberto_por    integer REFERENCES usuarios(id),
    reaberto_em     timestamptz,
    UNIQUE (id_unidade, competencia)
);
CREATE INDEX IF NOT EXISTS ix_fechamento_periodo ON cmv_fechamentos (id_unidade, fim DESC);
