-- Botané 009 — notas de entrada vindas do Omie e o registro das sincronizações.
-- Traz também o de-para de código externo, usado por Omie e PDV. Idempotente.

-- DE-PARA de sistema externo. Vale para o Omie e para o PDV: N códigos
-- externos → 1 produto, porque o mesmo café tem código diferente em cada
-- fornecedor e ainda outro no PDV.
CREATE TABLE IF NOT EXISTS codigos_externos (
    sistema           varchar(20) NOT NULL,        -- OMIE | PDV_LEGAL | FORNECEDOR
    codigo            varchar(60) NOT NULL,
    id_produto        integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    descricao_externa varchar(200),
    fator             numeric(18,6) NOT NULL DEFAULT 1,  -- embalagem → un. de estoque
    id_fornecedor     integer REFERENCES fornecedores(id) ON DELETE SET NULL,
    origem_vinculo    varchar(20) NOT NULL DEFAULT 'MANUAL',
    confirmado_por    integer REFERENCES usuarios(id),
    confirmado_em     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sistema, codigo)
);
CREATE INDEX IF NOT EXISTS ix_codigos_externos_produto ON codigos_externos (id_produto);

CREATE TABLE IF NOT EXISTS notas_entrada (
    id             bigserial PRIMARY KEY,
    id_unidade     integer NOT NULL REFERENCES unidades(id),
    chave_nfe      varchar(44),
    numero         varchar(20),
    serie          varchar(5),
    id_fornecedor  integer REFERENCES fornecedores(id),
    cnpj_emitente  varchar(18),
    nome_emitente  varchar(160),
    data_emissao   date,
    data_entrada   date,
    valor_produtos numeric(18,2) NOT NULL DEFAULT 0,
    valor_frete    numeric(18,2) NOT NULL DEFAULT 0,
    valor_desconto numeric(18,2) NOT NULL DEFAULT 0,
    valor_outros   numeric(18,2) NOT NULL DEFAULT 0,   -- IPI, ST
    valor_total    numeric(18,2) NOT NULL DEFAULT 0,
    origem         varchar(10) NOT NULL DEFAULT 'OMIE', -- OMIE|MANUAL|XML
    id_omie        varchar(40),
    status         varchar(12) NOT NULL DEFAULT 'IMPORTADA', -- IMPORTADA|CONCILIADA|LANCADA|CANCELADA
    id_local       integer REFERENCES locais_estoque(id),
    importada_em   timestamptz NOT NULL DEFAULT now(),
    lancada_em     timestamptz,
    lancada_por    integer REFERENCES usuarios(id),
    bruto          jsonb                                 -- a resposta como veio
);
-- A idempotência da importação é do BANCO, nunca do gatilho: reimportar a mesma
-- nota não cria a segunda.
CREATE UNIQUE INDEX IF NOT EXISTS ux_nota_chave
    ON notas_entrada (chave_nfe) WHERE chave_nfe IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_nota_omie
    ON notas_entrada (id_omie) WHERE id_omie IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_nota_status ON notas_entrada (status, data_emissao DESC);

CREATE TABLE IF NOT EXISTS nota_itens (
    id                       bigserial PRIMARY KEY,
    id_nota                  bigint NOT NULL REFERENCES notas_entrada(id) ON DELETE CASCADE,
    seq                      smallint NOT NULL,
    descricao_fornecedor     varchar(200) NOT NULL,
    codigo_fornecedor        varchar(60),
    codigo_barras            varchar(20),
    ncm                      varchar(10),
    quantidade               numeric(18,4) NOT NULL,
    um_nota                  varchar(10),
    valor_unitario           numeric(18,6) NOT NULL DEFAULT 0,
    valor_total              numeric(18,2) NOT NULL DEFAULT 0,
    valor_desconto           numeric(18,2) NOT NULL DEFAULT 0,
    valor_frete_rateado      numeric(18,2) NOT NULL DEFAULT 0,
    valor_outros_rateado     numeric(18,2) NOT NULL DEFAULT 0,
    lote_nf                  varchar(40),
    validade_nf              date,
    -- NULL = pendência de de-para; a nota não é lançada enquanto houver uma.
    id_produto               integer REFERENCES produtos(id),
    sugestao_produto         integer REFERENCES produtos(id),
    sugestao_score           numeric(5,2),
    quantidade_convertida    numeric(18,4),
    custo_aquisicao_unitario numeric(18,6),
    variacao_preco_pct       numeric(9,2),
    ignorado                 boolean NOT NULL DEFAULT false,  -- não controla estoque
    UNIQUE (id_nota, seq)
);
CREATE INDEX IF NOT EXISTS ix_nota_item_pendente
    ON nota_itens (id_nota) WHERE id_produto IS NULL AND NOT ignorado;
CREATE INDEX IF NOT EXISTS ix_nota_item_produto ON nota_itens (id_produto);

CREATE TABLE IF NOT EXISTS sync_log (
    id           bigserial PRIMARY KEY,
    servico      varchar(30) NOT NULL,
    chamada      varchar(60) NOT NULL,
    pagina       integer,
    registros    integer,
    status       varchar(12) NOT NULL,      -- OK|ERRO|VAZIO
    mensagem     text,
    modo         varchar(10),               -- simulado|real
    iniciado_em  timestamptz NOT NULL DEFAULT now(),
    terminado_em timestamptz
);
CREATE INDEX IF NOT EXISTS ix_sync_log_data ON sync_log (servico, iniciado_em DESC);
