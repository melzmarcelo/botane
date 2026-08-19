-- Botane 001 — empresa, lojas, parâmetros, integrações, acesso e auditoria.
-- Idempotente: o db_updater reroda o script quando o arquivo muda.

-- ============================================================ EMPRESA

CREATE TABLE IF NOT EXISTS empresa (
    id                  smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    razao_social        varchar(160) NOT NULL DEFAULT '',
    nome_fantasia       varchar(160),
    cnpj                varchar(18),
    inscricao_estadual  varchar(20),
    inscricao_municipal varchar(20),
    cnae_principal      varchar(10),
    regime_tributario   varchar(20),
    data_abertura       date,
    telefone            varchar(20),
    whatsapp            varchar(20),
    email               varchar(160),
    site                varchar(160),
    instagram           varchar(80),
    cep                 varchar(9),
    logradouro          varchar(160),
    numero              varchar(20),
    complemento         varchar(80),
    bairro              varchar(80),
    cidade              varchar(80),
    uf                  char(2),
    codigo_ibge         varchar(7),
    responsavel_nome    varchar(120),
    responsavel_cpf     varchar(14),
    responsavel_email   varchar(160),
    contador_nome       varchar(120),
    contador_crc        varchar(20),
    contador_email      varchar(160),
    contador_telefone   varchar(20),
    logo_url            text,
    cor_primaria        varchar(9),
    criado_em           timestamptz NOT NULL DEFAULT now(),
    atualizado_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_por      integer
);

CREATE TABLE IF NOT EXISTS unidades (
    id                  serial PRIMARY KEY,
    nome                varchar(120) NOT NULL,
    apelido             varchar(40),
    cnpj                varchar(18),
    inscricao_estadual  varchar(20),
    matriz              boolean NOT NULL DEFAULT false,
    cep                 varchar(9),
    logradouro          varchar(160),
    numero              varchar(20),
    complemento         varchar(80),
    bairro              varchar(80),
    cidade              varchar(80),
    uf                  char(2),
    codigo_ibge         varchar(7),
    telefone            varchar(20),
    email               varchar(160),
    timezone            varchar(60) NOT NULL DEFAULT 'America/Sao_Paulo',
    horario_funcionamento jsonb,
    mesas               smallint,
    id_omie             varchar(40),
    ativo               boolean NOT NULL DEFAULT true,
    criado_em           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_unidade_matriz ON unidades (matriz) WHERE matriz;

-- Parâmetros que mudam o comportamento do sistema, por loja.
CREATE TABLE IF NOT EXISTS parametros (
    id_unidade                integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    dia_fechamento_cmv        smallint NOT NULL DEFAULT 1,
    bloquear_retroativo       boolean NOT NULL DEFAULT true,
    permitir_saldo_negativo   boolean NOT NULL DEFAULT true,
    exigir_motivo_perda       boolean NOT NULL DEFAULT true,
    exigir_local_movimento    boolean NOT NULL DEFAULT true,
    casas_decimais_qtd        smallint NOT NULL DEFAULT 3,
    alerta_validade_dias      smallint NOT NULL DEFAULT 15,
    bloquear_saida_vencido    boolean NOT NULL DEFAULT false,
    alerta_variacao_preco_pct numeric(5,2) NOT NULL DEFAULT 15,
    criar_produto_da_nota     boolean NOT NULL DEFAULT true,
    atualizado_em             timestamptz NOT NULL DEFAULT now()
);

-- Credenciais de integração: cifradas na aplicação, nunca devolvidas pela API.
CREATE TABLE IF NOT EXISTS integracoes (
    id                   serial PRIMARY KEY,
    id_unidade           integer REFERENCES unidades(id) ON DELETE CASCADE,
    servico              varchar(30) NOT NULL,
    ativa                boolean NOT NULL DEFAULT false,
    modo                 varchar(10) NOT NULL DEFAULT 'simulado',
    credenciais          bytea,
    config               jsonb,
    ultima_sincronizacao timestamptz,
    ultimo_status        varchar(20),
    ultima_mensagem      text,
    atualizado_em        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_unidade, servico)
);

-- ============================================================ ACESSO

CREATE TABLE IF NOT EXISTS usuarios (
    id               serial PRIMARY KEY,
    nome             varchar(120) NOT NULL,
    email            varchar(160) NOT NULL UNIQUE,
    senha_hash       varchar(255) NOT NULL,
    telefone         varchar(20),
    foto_url         text,
    ativo            boolean NOT NULL DEFAULT true,
    ultimo_acesso    timestamptz,
    tentativas_login smallint NOT NULL DEFAULT 0,
    bloqueado_ate    timestamptz,
    trocar_senha     boolean NOT NULL DEFAULT false,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    criado_por       integer REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS papeis (
    id        serial PRIMARY KEY,
    nome      varchar(80) NOT NULL UNIQUE,
    descricao text,
    sistema   boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS permissoes (
    chave     varchar(60) PRIMARY KEY,
    modulo    varchar(40) NOT NULL,
    descricao text NOT NULL,
    ordem     smallint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS papel_permissoes (
    id_papel integer NOT NULL REFERENCES papeis(id) ON DELETE CASCADE,
    chave    varchar(60) NOT NULL REFERENCES permissoes(chave) ON DELETE CASCADE,
    PRIMARY KEY (id_papel, chave)
);

-- Escopo por loja: NULL = vale em todas.
CREATE TABLE IF NOT EXISTS usuario_papeis (
    id_usuario integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_papel   integer NOT NULL REFERENCES papeis(id) ON DELETE CASCADE,
    id_unidade integer REFERENCES unidades(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuario_papel
    ON usuario_papeis (id_usuario, id_papel, COALESCE(id_unidade, 0));

CREATE TABLE IF NOT EXISTS sessoes (
    id           bigserial PRIMARY KEY,
    id_usuario   integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    refresh_hash varchar(64) NOT NULL,
    expira_em    timestamptz NOT NULL,
    revogada_em  timestamptz,
    ip           varchar(45),
    agente       text,
    criada_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sessoes_hash ON sessoes (refresh_hash);
CREATE INDEX IF NOT EXISTS ix_sessoes_usuario ON sessoes (id_usuario, revogada_em);

CREATE TABLE IF NOT EXISTS auditoria (
    id          bigserial PRIMARY KEY,
    id_usuario  integer REFERENCES usuarios(id),
    id_unidade  integer REFERENCES unidades(id),
    entidade    varchar(60) NOT NULL,
    id_entidade varchar(60),
    acao        varchar(40) NOT NULL,
    antes       jsonb,
    depois      jsonb,
    ip          varchar(45),
    em          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_auditoria_entidade ON auditoria (entidade, id_entidade, em DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_em ON auditoria (em DESC);
