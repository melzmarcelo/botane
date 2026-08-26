-- Botané 004 — cadastros base: setores, locais, categorias, unidades de medida,
-- fornecedores e produtos. Idempotente.

-- ============================================================ APOIO

CREATE TABLE IF NOT EXISTS setores (
    id         serial PRIMARY KEY,
    id_unidade integer REFERENCES unidades(id) ON DELETE CASCADE,  -- NULL = todas
    nome       varchar(80) NOT NULL,
    cor        varchar(9),
    ordem      smallint NOT NULL DEFAULT 0,
    ativo      boolean NOT NULL DEFAULT true,
    criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_setor_nome
    ON setores (lower(nome), COALESCE(id_unidade, 0));

-- Setor é organizacional (cozinha, bar); local é físico e tem saldo.
CREATE TABLE IF NOT EXISTS locais_estoque (
    id         serial PRIMARY KEY,
    id_unidade integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    nome       varchar(80) NOT NULL,
    tipo       varchar(20) NOT NULL DEFAULT 'SECO',   -- SECO|RESFRIADO|CONGELADO|BAR
    principal  boolean NOT NULL DEFAULT false,
    ativo      boolean NOT NULL DEFAULT true,
    criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_local_nome ON locais_estoque (id_unidade, lower(nome));
-- Um local padrão por loja: é para onde vai a entrada quando ninguém escolhe.
CREATE UNIQUE INDEX IF NOT EXISTS ux_local_principal
    ON locais_estoque (id_unidade) WHERE principal;

CREATE TABLE IF NOT EXISTS categorias (
    id        serial PRIMARY KEY,
    id_pai    integer REFERENCES categorias(id) ON DELETE RESTRICT,
    nome      varchar(80) NOT NULL,
    tipo      varchar(20) NOT NULL DEFAULT 'INSUMO',  -- INSUMO|REVENDA|PRODUZIDO|EMBALAGEM|MATERIAL_LIMPEZA (029)
    ordem     smallint NOT NULL DEFAULT 0,
    ativo     boolean NOT NULL DEFAULT true,
    criado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_categoria_pai CHECK (id_pai IS NULL OR id_pai <> id)
);
CREATE INDEX IF NOT EXISTS ix_categoria_pai ON categorias (id_pai);

-- Unidades de medida. `fator_base` converte para a base da grandeza (G, ML, UN).
-- Embalagem (CX, FD, PCT) fica como UNIDADE com fator 1: quantas unidades vêm
-- na caixa é do PRODUTO (fator_compra), não da unidade de medida.
CREATE TABLE IF NOT EXISTS unidades_medida (
    sigla      varchar(6) PRIMARY KEY,
    nome       varchar(40) NOT NULL,
    grandeza   varchar(20) NOT NULL,          -- MASSA|VOLUME|UNIDADE
    fator_base numeric(18,6) NOT NULL DEFAULT 1,
    ativo      boolean NOT NULL DEFAULT true
);

INSERT INTO unidades_medida (sigla, nome, grandeza, fator_base) VALUES
    ('KG',  'Quilograma',  'MASSA',   1000),
    ('G',   'Grama',       'MASSA',   1),
    ('L',   'Litro',       'VOLUME',  1000),
    ('ML',  'Mililitro',   'VOLUME',  1),
    ('UN',  'Unidade',     'UNIDADE', 1),
    ('DZ',  'Dúzia',       'UNIDADE', 12),
    ('CX',  'Caixa',       'UNIDADE', 1),
    ('FD',  'Fardo',       'UNIDADE', 1),
    ('PCT', 'Pacote',      'UNIDADE', 1),
    ('BDJ', 'Bandeja',     'UNIDADE', 1)
ON CONFLICT (sigla) DO UPDATE
    SET nome = EXCLUDED.nome,
        grandeza = EXCLUDED.grandeza,
        fator_base = EXCLUDED.fator_base;

-- Restrição por setor (o ajudante conta só a área dele). Sem linha = sem limite.
CREATE TABLE IF NOT EXISTS usuario_setores (
    id_usuario integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_setor   integer NOT NULL REFERENCES setores(id) ON DELETE CASCADE,
    PRIMARY KEY (id_usuario, id_setor)
);

-- ============================================================ FORNECEDORES

CREATE TABLE IF NOT EXISTS fornecedores (
    id                 serial PRIMARY KEY,
    nome               varchar(160) NOT NULL,
    nome_fantasia      varchar(160),
    cnpj               varchar(18),
    email              varchar(160),
    telefone           varchar(20),
    whatsapp           varchar(20),
    contato            varchar(120),
    cidade             varchar(80),
    uf                 char(2),
    prazo_entrega_dias smallint,
    dias_entrega       varchar(40),        -- "seg,qua,sex"
    pedido_minimo      numeric(18,2),
    observacao         text,
    codigo_omie        varchar(40),
    ativo              boolean NOT NULL DEFAULT true,
    criado_em          timestamptz NOT NULL DEFAULT now(),
    criado_por         integer REFERENCES usuarios(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fornecedor_cnpj
    ON fornecedores (cnpj) WHERE cnpj IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_fornecedor_nome ON fornecedores (ativo, lower(nome));

-- ============================================================ PRODUTOS

CREATE TABLE IF NOT EXISTS produtos (
    id                serial PRIMARY KEY,
    codigo            varchar(40) NOT NULL,
    nome              varchar(160) NOT NULL,
    nome_curto        varchar(60),
    tipo              varchar(20) NOT NULL,   -- INSUMO|REVENDA|PRODUZIDO|KIT|EMBALAGEM|MATERIAL_LIMPEZA (029)
    id_categoria      integer REFERENCES categorias(id) ON DELETE SET NULL,
    id_setor          integer REFERENCES setores(id) ON DELETE SET NULL,
    producao_propria  boolean NOT NULL DEFAULT false,
    controla_estoque  boolean NOT NULL DEFAULT true,
    um_estoque        varchar(6) REFERENCES unidades_medida(sigla),
    um_compra         varchar(6) REFERENCES unidades_medida(sigla),
    fator_compra      numeric(18,6) NOT NULL DEFAULT 1,
    perecivel         boolean NOT NULL DEFAULT false,
    validade_dias     smallint,
    controla_lote     boolean NOT NULL DEFAULT false,
    controla_validade boolean NOT NULL DEFAULT false,
    estoque_minimo    numeric(18,3),
    estoque_maximo    numeric(18,3),
    ncm               varchar(10),
    codigo_barras     varchar(20),
    codigo_omie       varchar(40),
    origem            varchar(10) NOT NULL DEFAULT 'MANUAL',  -- MANUAL|OMIE|NOTA|PDV
    status            varchar(10) NOT NULL DEFAULT 'ATIVO',   -- RASCUNHO|ATIVO|ARQUIVADO
    observacao        text,
    revisado_em       timestamptz,
    revisado_por      integer REFERENCES usuarios(id),
    ativo             boolean NOT NULL DEFAULT true,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    criado_por        integer REFERENCES usuarios(id),
    CONSTRAINT ck_produto_producao CHECK (
        NOT producao_propria OR tipo IN ('PRODUZIDO', 'KIT')
    ),
    -- Produto ativo precisa do que decide o custo por unidade de estoque.
    CONSTRAINT ck_produto_rascunho CHECK (
        status <> 'ATIVO' OR (um_estoque IS NOT NULL AND fator_compra > 0)
    ),
    CONSTRAINT ck_produto_fator CHECK (fator_compra > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_codigo ON produtos (lower(codigo));
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_omie
    ON produtos (codigo_omie) WHERE codigo_omie IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_produto_barras
    ON produtos (codigo_barras) WHERE codigo_barras IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_produto_busca ON produtos (ativo, tipo, lower(nome));
CREATE INDEX IF NOT EXISTS ix_produto_categoria ON produtos (id_categoria);
CREATE INDEX IF NOT EXISTS ix_produto_rascunho ON produtos (status) WHERE status = 'RASCUNHO';

-- Código sequencial para quem não quer inventar um.
CREATE SEQUENCE IF NOT EXISTS seq_codigo_produto START 1;

-- Preço de venda com vigência: o histórico é o que permite recalcular margem
-- de um mês passado sem mentir.
CREATE TABLE IF NOT EXISTS produto_precos (
    id          serial PRIMARY KEY,
    id_produto  integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_unidade  integer REFERENCES unidades(id) ON DELETE CASCADE,
    preco_venda numeric(18,2) NOT NULL,
    vigente_de  date NOT NULL DEFAULT current_date,
    vigente_ate date,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    criado_por  integer REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS ix_preco_produto ON produto_precos (id_produto, vigente_de DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_preco_vigente
    ON produto_precos (id_produto, COALESCE(id_unidade, 0)) WHERE vigente_ate IS NULL;

-- De quem se compra, com que código e em que embalagem.
CREATE TABLE IF NOT EXISTS produto_fornecedor (
    id_produto           integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_fornecedor        integer NOT NULL REFERENCES fornecedores(id) ON DELETE CASCADE,
    codigo_no_fornecedor varchar(60),
    embalagem            varchar(40),
    fator                numeric(18,6) NOT NULL DEFAULT 1,
    ultimo_preco         numeric(18,6),
    ultima_compra        date,
    preferencial         boolean NOT NULL DEFAULT false,
    PRIMARY KEY (id_produto, id_fornecedor)
);
CREATE INDEX IF NOT EXISTS ix_prodforn_fornecedor ON produto_fornecedor (id_fornecedor);
