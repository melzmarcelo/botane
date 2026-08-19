-- Botané 007 — o razão de estoque e o custo médio móvel.
-- Idempotente.

CREATE TABLE IF NOT EXISTS perda_motivos (
    id    serial PRIMARY KEY,
    nome  varchar(80) NOT NULL,
    ativo boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_perda_motivo ON perda_motivos (lower(nome));

INSERT INTO perda_motivos (nome)
SELECT * FROM (VALUES
    ('Quebra'), ('Validade vencida'), ('Erro de preparo'), ('Cortesia'),
    ('Devolução do cliente'), ('Consumo interno'), ('Sobra de produção')
) AS m(nome)
WHERE NOT EXISTS (SELECT 1 FROM perda_motivos);

-- ============================================================ O RAZÃO
-- APPEND-ONLY. Nunca UPDATE, nunca DELETE. Correção é ESTORNO.
CREATE TABLE IF NOT EXISTS estoque_movimentos (
    id               bigserial PRIMARY KEY,
    id_unidade       integer NOT NULL REFERENCES unidades(id),
    id_local         integer NOT NULL REFERENCES locais_estoque(id),
    id_produto       integer NOT NULL REFERENCES produtos(id),
    data_movimento   timestamptz NOT NULL DEFAULT now(),
    tipo             varchar(30) NOT NULL,
    quantidade       numeric(18,4) NOT NULL,      -- + entrada, − saída
    custo_unitario   numeric(18,6) NOT NULL DEFAULT 0,
    custo_total      numeric(18,2) NOT NULL DEFAULT 0,
    -- Fotografia do momento: é o que permite auditar sem recalcular a série.
    saldo_apos       numeric(18,4) NOT NULL,
    custo_medio_apos numeric(18,6) NOT NULL,
    custo_provisorio boolean NOT NULL DEFAULT false,
    origem_tipo      varchar(20),                 -- NOTA|PRODUCAO|INVENTARIO|VENDA|MANUAL|TRANSFERENCIA
    origem_id        bigint,
    id_estorno_de    bigint REFERENCES estoque_movimentos(id),
    id_motivo_perda  integer REFERENCES perda_motivos(id),
    documento        varchar(60),
    observacao       text,
    id_usuario       integer REFERENCES usuarios(id),
    criado_em        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_mov_qtd CHECK (quantidade <> 0)
);
CREATE INDEX IF NOT EXISTS ix_mov_produto ON estoque_movimentos (id_produto, id_unidade, id);
CREATE INDEX IF NOT EXISTS ix_mov_data ON estoque_movimentos (id_unidade, data_movimento DESC);
CREATE INDEX IF NOT EXISTS ix_mov_origem ON estoque_movimentos (origem_tipo, origem_id);
CREATE INDEX IF NOT EXISTS ix_mov_tipo ON estoque_movimentos (tipo, data_movimento DESC);

-- Materialização do razão. A verdade é o razão; isto é cache transacional e é
-- a linha travada com FOR UPDATE antes de cada cálculo de médio.
CREATE TABLE IF NOT EXISTS estoque_saldos (
    id_unidade    integer NOT NULL REFERENCES unidades(id),
    id_local      integer NOT NULL REFERENCES locais_estoque(id),
    id_produto    integer NOT NULL REFERENCES produtos(id),
    quantidade    numeric(18,4) NOT NULL DEFAULT 0,
    custo_medio   numeric(18,6) NOT NULL DEFAULT 0,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, id_local, id_produto)
);
CREATE INDEX IF NOT EXISTS ix_saldo_produto ON estoque_saldos (id_produto);

-- ============================================================ LOTE E VALIDADE
-- Camada de CONTROLE, não de custo: a valorização continua no médio.
CREATE TABLE IF NOT EXISTS estoque_lotes (
    id         bigserial PRIMARY KEY,
    id_unidade integer NOT NULL REFERENCES unidades(id),
    id_local   integer NOT NULL REFERENCES locais_estoque(id),
    id_produto integer NOT NULL REFERENCES produtos(id),
    lote       varchar(40),
    validade   date,
    quantidade numeric(18,4) NOT NULL DEFAULT 0,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_lote_identificado CHECK (lote IS NOT NULL OR validade IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_lote ON estoque_lotes
    (id_unidade, id_local, id_produto, COALESCE(lote, ''), COALESCE(validade, '9999-12-31'));
CREATE INDEX IF NOT EXISTS ix_lote_validade
    ON estoque_lotes (validade) WHERE quantidade > 0;

-- Movimento SEM linha aqui saiu do saldo geral ("sem lote") — é o que torna a
-- informação opcional sem quebrar a conta.
CREATE TABLE IF NOT EXISTS movimento_lotes (
    id_movimento bigint NOT NULL REFERENCES estoque_movimentos(id) ON DELETE CASCADE,
    id_lote      bigint NOT NULL REFERENCES estoque_lotes(id),
    quantidade   numeric(18,4) NOT NULL,
    PRIMARY KEY (id_movimento, id_lote)
);

-- ============================================================ INVENTÁRIO
CREATE TABLE IF NOT EXISTS inventarios (
    id         serial PRIMARY KEY,
    id_unidade integer NOT NULL REFERENCES unidades(id),
    id_local   integer NOT NULL REFERENCES locais_estoque(id),
    data       date NOT NULL DEFAULT current_date,
    status     varchar(12) NOT NULL DEFAULT 'ABERTO',   -- ABERTO|FECHADO|CANCELADO
    observacao text,
    id_usuario integer REFERENCES usuarios(id),
    criado_em  timestamptz NOT NULL DEFAULT now(),
    fechado_em timestamptz,
    fechado_por integer REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS ix_inventario_local ON inventarios (id_local, status);

CREATE TABLE IF NOT EXISTS inventario_itens (
    id            bigserial PRIMARY KEY,
    id_inventario integer NOT NULL REFERENCES inventarios(id) ON DELETE CASCADE,
    id_produto    integer NOT NULL REFERENCES produtos(id),
    qtd_sistema   numeric(18,4) NOT NULL DEFAULT 0,
    qtd_contada   numeric(18,4),
    custo_medio   numeric(18,6) NOT NULL DEFAULT 0,
    observacao    text,
    UNIQUE (id_inventario, id_produto)
);

-- ============================================================ PRODUÇÃO
-- Uma produção consome a ficha e devolve o produzido. A versão e o custo ficam
-- congelados aqui: editar a receita amanhã não muda o que saiu hoje.
CREATE TABLE IF NOT EXISTS producoes (
    id             serial PRIMARY KEY,
    id_unidade     integer NOT NULL REFERENCES unidades(id),
    id_local       integer NOT NULL REFERENCES locais_estoque(id),
    id_produto     integer NOT NULL REFERENCES produtos(id),
    id_ficha       integer REFERENCES fichas_tecnicas(id),
    versao_ficha   smallint,
    quantidade     numeric(18,4) NOT NULL,
    custo_total    numeric(18,2) NOT NULL DEFAULT 0,
    custo_unitario numeric(18,6) NOT NULL DEFAULT 0,
    data           timestamptz NOT NULL DEFAULT now(),
    observacao     text,
    id_usuario     integer REFERENCES usuarios(id),
    CONSTRAINT ck_producao_qtd CHECK (quantidade > 0)
);
CREATE INDEX IF NOT EXISTS ix_producao_data ON producoes (id_unidade, data DESC);
