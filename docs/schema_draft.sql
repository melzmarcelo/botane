-- Botane — rascunho do modelo de dados (fase 0)
-- PostgreSQL. Ainda NÃO é migração: vira 001_..._base.sql quando a fase 1 começar.
-- Convenções: numeric(18,6) para custo unitário, numeric(18,2) para valor,
-- timestamptz sempre, banco em UTC.

-- ============================================================ 1. ACESSO

-- A EMPRESA (uma linha). Guarda o que é do negócio, não da loja.
CREATE TABLE empresa (
    id              smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    -- identificação
    razao_social    varchar(160) NOT NULL,
    nome_fantasia   varchar(160),
    cnpj            varchar(18) NOT NULL,
    inscricao_estadual varchar(20),
    inscricao_municipal varchar(20),
    cnae_principal  varchar(10),
    regime_tributario varchar(20),        -- SIMPLES|PRESUMIDO|REAL|MEI
    data_abertura   date,
    -- contato
    telefone        varchar(20),
    whatsapp        varchar(20),
    email           varchar(160),
    site            varchar(160),
    instagram       varchar(80),
    -- endereço da matriz
    cep             varchar(9),
    logradouro      varchar(160),
    numero          varchar(20),
    complemento     varchar(80),
    bairro          varchar(80),
    cidade          varchar(80),
    uf              char(2),
    codigo_ibge     varchar(7),
    -- responsáveis
    responsavel_nome varchar(120),
    responsavel_cpf varchar(14),
    responsavel_email varchar(160),
    contador_nome   varchar(120),
    contador_crc    varchar(20),
    contador_email  varchar(160),
    contador_telefone varchar(20),
    -- marca (relatórios e PDF)
    logo_url        text,
    cor_primaria    varchar(9),
    -- auditoria
    criado_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_em   timestamptz NOT NULL DEFAULT now(),
    atualizado_por  integer
);

-- AS LOJAS. Uma hoje; o modelo não muda quando vier a segunda.
CREATE TABLE unidades (
    id              serial PRIMARY KEY,
    nome            varchar(120) NOT NULL,
    apelido         varchar(40),                -- aparece no seletor
    cnpj            varchar(18),                -- filial pode ter CNPJ próprio
    inscricao_estadual varchar(20),
    matriz          boolean NOT NULL DEFAULT false,
    -- endereço
    cep             varchar(9),
    logradouro      varchar(160),
    numero          varchar(20),
    complemento     varchar(80),
    bairro          varchar(80),
    cidade          varchar(80),
    uf              char(2),
    codigo_ibge     varchar(7),
    telefone        varchar(20),
    email           varchar(160),
    -- operação
    timezone        varchar(60) NOT NULL DEFAULT 'America/Sao_Paulo',
    horario_funcionamento jsonb,               -- {"seg":["11:00","23:00"], "dom":null}
    mesas           smallint,
    id_omie         varchar(40),                -- se o Omie separar por filial
    ativo           boolean NOT NULL DEFAULT true,
    criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_unidade_matriz ON unidades (matriz) WHERE matriz;

-- PARÂMETROS que mudam o comportamento do sistema. Por loja, com fallback na empresa.
CREATE TABLE parametros (
    id_unidade      integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    -- CMV e fechamento
    dia_fechamento_cmv smallint NOT NULL DEFAULT 1,
    bloquear_retroativo boolean NOT NULL DEFAULT true,
    -- estoque
    permitir_saldo_negativo boolean NOT NULL DEFAULT true,
    exigir_motivo_perda boolean NOT NULL DEFAULT true,
    exigir_local_movimento boolean NOT NULL DEFAULT true,
    casas_decimais_qtd smallint NOT NULL DEFAULT 3,
    -- validade
    alerta_validade_dias smallint NOT NULL DEFAULT 15,
    bloquear_saida_vencido boolean NOT NULL DEFAULT false,
    -- compras
    alerta_variacao_preco_pct numeric(5,2) NOT NULL DEFAULT 15,  -- avisa se a NF subiu mais que isso
    criar_produto_da_nota boolean NOT NULL DEFAULT true,          -- item novo vira produto rascunho
    atualizado_em   timestamptz NOT NULL DEFAULT now()
);

-- CREDENCIAIS DE INTEGRAÇÃO. Tabela à parte: valor cifrado, nunca devolvido pela API.
CREATE TABLE integracoes (
    id              serial PRIMARY KEY,
    id_unidade      integer REFERENCES unidades(id) ON DELETE CASCADE,
    servico         varchar(30) NOT NULL,       -- OMIE | PDV_LEGAL | SMTP
    ativa           boolean NOT NULL DEFAULT false,
    modo            varchar(10) NOT NULL DEFAULT 'simulado',   -- simulado | real
    credenciais     bytea,                      -- cifrado na aplicação (pgcrypto ou Fernet)
    config          jsonb,                      -- janela de sinc, filtros, ids padrão
    ultima_sincronizacao timestamptz,
    ultimo_status   varchar(20),
    ultima_mensagem text,
    atualizado_em   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_unidade, servico)
);

CREATE TABLE usuarios (
    id              serial PRIMARY KEY,
    nome            varchar(120) NOT NULL,
    email           varchar(160) NOT NULL UNIQUE,
    senha_hash      varchar(255) NOT NULL,
    telefone        varchar(20),
    foto_url        text,
    ativo           boolean NOT NULL DEFAULT true,
    ultimo_acesso   timestamptz,
    tentativas_login smallint NOT NULL DEFAULT 0,
    bloqueado_ate   timestamptz,
    criado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE papeis (
    id              serial PRIMARY KEY,
    nome            varchar(80) NOT NULL UNIQUE,
    descricao       text,
    sistema         boolean NOT NULL DEFAULT false   -- papel de fábrica, não editável
);

CREATE TABLE permissoes (
    chave           varchar(60) PRIMARY KEY,
    modulo          varchar(40) NOT NULL,
    descricao       text NOT NULL
);

CREATE TABLE papel_permissoes (
    id_papel        integer NOT NULL REFERENCES papeis(id) ON DELETE CASCADE,
    chave           varchar(60) NOT NULL REFERENCES permissoes(chave) ON DELETE CASCADE,
    PRIMARY KEY (id_papel, chave)
);

-- Escopo por loja: o mesmo usuário pode ser gerente em uma unidade e só leitura em outra.
CREATE TABLE usuario_papeis (
    id_usuario      integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_papel        integer NOT NULL REFERENCES papeis(id) ON DELETE CASCADE,
    id_unidade      integer REFERENCES unidades(id) ON DELETE CASCADE   -- NULL = todas
);
-- PK não aceita expressão; a unicidade (com NULL = "todas as unidades") vai em índice:
CREATE UNIQUE INDEX ux_usuario_papel ON usuario_papeis
    (id_usuario, id_papel, COALESCE(id_unidade, 0));

-- Restrição opcional por setor: ajudante lança perda só na área dele.
-- Sem linha aqui = sem restrição de setor.
CREATE TABLE usuario_setores (
    id_usuario      integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_setor        integer NOT NULL,
    PRIMARY KEY (id_usuario, id_setor)
);

CREATE TABLE sessoes (
    id              bigserial PRIMARY KEY,
    id_usuario      integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    refresh_hash    varchar(255) NOT NULL,
    expira_em       timestamptz NOT NULL,
    revogada_em     timestamptz,
    ip              varchar(45),
    agente          text,
    criada_em       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auditoria (
    id              bigserial PRIMARY KEY,
    id_usuario      integer REFERENCES usuarios(id),
    id_unidade      integer REFERENCES unidades(id),
    entidade        varchar(60) NOT NULL,
    id_entidade     varchar(60),
    acao            varchar(40) NOT NULL,
    antes           jsonb,
    depois          jsonb,
    em              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_auditoria_entidade ON auditoria (entidade, id_entidade, em DESC);

-- ============================================================ 2. CADASTROS

CREATE TABLE setores (
    id              serial PRIMARY KEY,
    id_unidade      integer REFERENCES unidades(id),
    nome            varchar(80) NOT NULL,
    cor             varchar(9),
    ativo           boolean NOT NULL DEFAULT true
);

CREATE TABLE locais_estoque (
    id              serial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    nome            varchar(80) NOT NULL,
    tipo            varchar(20) NOT NULL DEFAULT 'SECO',  -- SECO|RESFRIADO|CONGELADO|BAR
    ativo           boolean NOT NULL DEFAULT true
);

CREATE TABLE categorias (
    id              serial PRIMARY KEY,
    id_pai          integer REFERENCES categorias(id),
    nome            varchar(80) NOT NULL,
    tipo            varchar(20) NOT NULL,   -- INSUMO|REVENDA|PRODUZIDO|EMBALAGEM
    ativo           boolean NOT NULL DEFAULT true
);

CREATE TABLE unidades_medida (
    sigla           varchar(6) PRIMARY KEY,     -- KG, G, L, ML, UN, CX, FD
    nome            varchar(40) NOT NULL,
    grandeza        varchar(20) NOT NULL,       -- MASSA|VOLUME|UNIDADE
    fator_base      numeric(18,6) NOT NULL      -- para a base da grandeza (G, ML, UN)
);

CREATE TABLE fornecedores (
    id              serial PRIMARY KEY,
    nome            varchar(160) NOT NULL,
    nome_fantasia   varchar(160),
    cnpj            varchar(18),
    email           varchar(160),
    telefone        varchar(20),
    prazo_entrega_dias smallint,
    codigo_omie     varchar(40),
    ativo           boolean NOT NULL DEFAULT true,
    criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_fornecedores_cnpj ON fornecedores (cnpj) WHERE cnpj IS NOT NULL;

CREATE TABLE produtos (
    id              serial PRIMARY KEY,
    codigo          varchar(40) NOT NULL,
    nome            varchar(160) NOT NULL,
    nome_curto      varchar(60),
    tipo            varchar(20) NOT NULL,       -- INSUMO|REVENDA|PRODUZIDO|KIT|EMBALAGEM
    id_categoria    integer REFERENCES categorias(id),
    id_setor        integer REFERENCES setores(id),
    producao_propria boolean NOT NULL DEFAULT false,
    controla_estoque boolean NOT NULL DEFAULT true,
    um_estoque      varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    um_compra       varchar(6) REFERENCES unidades_medida(sigla),
    fator_compra    numeric(18,6) NOT NULL DEFAULT 1,   -- 1 CX = 12 UN
    perecivel       boolean NOT NULL DEFAULT false,
    validade_dias   smallint,
    estoque_minimo  numeric(18,3),
    estoque_maximo  numeric(18,3),
    ncm             varchar(10),
    codigo_barras   varchar(20),
    codigo_omie     varchar(40),
    -- controle opcional de lote/validade (por produto, nunca global)
    controla_lote   boolean NOT NULL DEFAULT false,
    controla_validade boolean NOT NULL DEFAULT false,
    -- procedência e maturidade do cadastro
    origem          varchar(10) NOT NULL DEFAULT 'MANUAL',   -- MANUAL | OMIE | NOTA | PDV
    status          varchar(10) NOT NULL DEFAULT 'ATIVO',    -- RASCUNHO | ATIVO | ARQUIVADO
    revisado_em     timestamptz,
    revisado_por    integer REFERENCES usuarios(id),
    ativo           boolean NOT NULL DEFAULT true,
    criado_em       timestamptz NOT NULL DEFAULT now(),
    criado_por      integer REFERENCES usuarios(id),
    CONSTRAINT ck_produtos_producao CHECK (
        NOT producao_propria OR tipo IN ('PRODUZIDO','KIT')
    ),
    -- produto nascido de nota entra RASCUNHO; só sai de rascunho com o que
    -- o custo por unidade de estoque exige
    CONSTRAINT ck_produtos_rascunho CHECK (
        status <> 'ATIVO' OR (um_estoque IS NOT NULL AND fator_compra > 0)
    )
);
CREATE UNIQUE INDEX ux_produtos_codigo ON produtos (codigo);
CREATE UNIQUE INDEX ux_produtos_omie ON produtos (codigo_omie) WHERE codigo_omie IS NOT NULL;
CREATE INDEX ix_produtos_busca ON produtos (ativo, tipo, nome);

CREATE TABLE produto_precos (
    id              serial PRIMARY KEY,
    id_produto      integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_unidade      integer REFERENCES unidades(id),
    preco_venda     numeric(18,2) NOT NULL,
    vigente_de      date NOT NULL,
    vigente_ate     date
);

CREATE TABLE produto_fornecedor (
    id_produto      integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_fornecedor   integer NOT NULL REFERENCES fornecedores(id) ON DELETE CASCADE,
    codigo_no_fornecedor varchar(60),
    embalagem       varchar(40),
    fator           numeric(18,6) NOT NULL DEFAULT 1,
    ultimo_preco    numeric(18,6),
    ultima_compra   date,
    PRIMARY KEY (id_produto, id_fornecedor)
);

-- ============================================================ 3. FICHA TÉCNICA

CREATE TABLE fichas_tecnicas (
    id              serial PRIMARY KEY,
    id_produto      integer NOT NULL REFERENCES produtos(id),
    versao          smallint NOT NULL DEFAULT 1,
    status          varchar(20) NOT NULL DEFAULT 'RASCUNHO',  -- RASCUNHO|HOMOLOGADA|ARQUIVADA
    rendimento_qtd  numeric(18,3) NOT NULL,
    rendimento_um   varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    porcoes         numeric(10,2) NOT NULL DEFAULT 1,
    tempo_preparo_min smallint,
    modo_preparo    text,
    foto_url        text,
    alergenos       text,
    vigente_de      date NOT NULL DEFAULT current_date,
    vigente_ate     date,
    homologada_por  integer REFERENCES usuarios(id),
    homologada_em   timestamptz,
    criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_ficha_versao ON fichas_tecnicas (id_produto, versao);
-- Só uma ficha homologada vigente por produto:
CREATE UNIQUE INDEX ux_ficha_vigente ON fichas_tecnicas (id_produto)
    WHERE status = 'HOMOLOGADA' AND vigente_ate IS NULL;

CREATE TABLE ficha_itens (
    id              serial PRIMARY KEY,
    id_ficha        integer NOT NULL REFERENCES fichas_tecnicas(id) ON DELETE CASCADE,
    id_insumo       integer REFERENCES produtos(id),
    id_subficha     integer REFERENCES fichas_tecnicas(id),
    qtd_bruta       numeric(18,4) NOT NULL,
    qtd_liquida     numeric(18,4) NOT NULL,
    um              varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    fator_correcao  numeric(10,4) NOT NULL DEFAULT 1,   -- bruto / líquido
    fator_coccao    numeric(10,4) NOT NULL DEFAULT 1,
    perda_percentual numeric(6,3) NOT NULL DEFAULT 0,
    observacao      text,
    ordem           smallint NOT NULL DEFAULT 0,
    CONSTRAINT ck_ficha_item_alvo CHECK (
        (id_insumo IS NOT NULL AND id_subficha IS NULL) OR
        (id_insumo IS NULL AND id_subficha IS NOT NULL)
    )
);
CREATE INDEX ix_ficha_itens_ficha ON ficha_itens (id_ficha);
-- Ciclo (ficha que se usa direta ou indiretamente) é recusado no service, na gravação.

-- ============================================================ 4. ESTOQUE

CREATE TABLE perda_motivos (
    id              serial PRIMARY KEY,
    nome            varchar(80) NOT NULL,
    ativo           boolean NOT NULL DEFAULT true
);

-- Livro-razão: APPEND-ONLY. Correção entra como ESTORNO, nunca UPDATE/DELETE.
CREATE TABLE estoque_movimentos (
    id              bigserial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    id_local        integer NOT NULL REFERENCES locais_estoque(id),
    id_produto      integer NOT NULL REFERENCES produtos(id),
    data_movimento  timestamptz NOT NULL DEFAULT now(),
    tipo            varchar(30) NOT NULL,
    quantidade      numeric(18,4) NOT NULL,       -- + entrada / − saída
    custo_unitario  numeric(18,6) NOT NULL,
    custo_total     numeric(18,2) NOT NULL,
    saldo_apos      numeric(18,4) NOT NULL,
    custo_medio_apos numeric(18,6) NOT NULL,
    custo_provisorio boolean NOT NULL DEFAULT false,  -- saída sem saldo: custo a confirmar
    origem_tipo     varchar(20),                  -- NOTA|PRODUCAO|INVENTARIO|VENDA|MANUAL
    origem_id       bigint,
    id_estorno_de   bigint REFERENCES estoque_movimentos(id),
    id_motivo_perda integer REFERENCES perda_motivos(id),
    observacao      text,
    id_usuario      integer REFERENCES usuarios(id),
    criado_em       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_mov_qtd CHECK (quantidade <> 0)
);
CREATE INDEX ix_mov_produto_data ON estoque_movimentos (id_produto, id_unidade, data_movimento);
CREATE INDEX ix_mov_data ON estoque_movimentos (id_unidade, data_movimento);
CREATE INDEX ix_mov_origem ON estoque_movimentos (origem_tipo, origem_id);

-- Materialização do razão. A verdade é o razão; isto é cache transacional.
CREATE TABLE estoque_saldos (
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    id_local        integer NOT NULL REFERENCES locais_estoque(id),
    id_produto      integer NOT NULL REFERENCES produtos(id),
    quantidade      numeric(18,4) NOT NULL DEFAULT 0,
    custo_medio     numeric(18,6) NOT NULL DEFAULT 0,
    atualizado_em   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, id_local, id_produto)
);
-- O motor faz SELECT ... FOR UPDATE nesta linha antes de calcular o médio.

-- LOTE E VALIDADE: camada de CONTROLE, não de custo.
-- O custo continua sendo o médio ponderado; lote não cria camada de preço (não é PEPS).
-- Só existe para produto com controla_lote/controla_validade ligado.
CREATE TABLE estoque_lotes (
    id              bigserial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    id_local        integer NOT NULL REFERENCES locais_estoque(id),
    id_produto      integer NOT NULL REFERENCES produtos(id),
    lote            varchar(40),
    validade        date,
    quantidade      numeric(18,4) NOT NULL DEFAULT 0,
    id_nota         bigint,                     -- de qual nota veio
    criado_em       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_lote_identificado CHECK (lote IS NOT NULL OR validade IS NOT NULL)
);
CREATE UNIQUE INDEX ux_lote ON estoque_lotes
    (id_unidade, id_local, id_produto, COALESCE(lote,''), COALESCE(validade,'9999-12-31'));
CREATE INDEX ix_lote_validade ON estoque_lotes (validade) WHERE quantidade > 0;

-- Qual lote cada movimento consumiu/gerou. Movimento SEM linha aqui saiu do
-- saldo geral ("sem lote") — é isso que torna a informação opcional.
CREATE TABLE movimento_lotes (
    id_movimento    bigint NOT NULL REFERENCES estoque_movimentos(id) ON DELETE CASCADE,
    id_lote         bigint NOT NULL REFERENCES estoque_lotes(id),
    quantidade      numeric(18,4) NOT NULL,
    PRIMARY KEY (id_movimento, id_lote)
);
-- Invariante: soma dos lotes de um produto <= saldo do produto no local.
-- A diferença é o "sem lote". Conferido por job e no inventário.

CREATE TABLE inventarios (
    id              serial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    id_local        integer NOT NULL REFERENCES locais_estoque(id),
    data            date NOT NULL,
    status          varchar(20) NOT NULL DEFAULT 'ABERTO',   -- ABERTO|FECHADO|CANCELADO
    observacao      text,
    id_usuario      integer REFERENCES usuarios(id),
    fechado_em      timestamptz
);

CREATE TABLE inventario_itens (
    id              bigserial PRIMARY KEY,
    id_inventario   integer NOT NULL REFERENCES inventarios(id) ON DELETE CASCADE,
    id_produto      integer NOT NULL REFERENCES produtos(id),
    qtd_sistema     numeric(18,4) NOT NULL,
    qtd_contada     numeric(18,4),
    custo_medio     numeric(18,6) NOT NULL,
    diferenca       numeric(18,4) GENERATED ALWAYS AS (COALESCE(qtd_contada,0) - qtd_sistema) STORED,
    UNIQUE (id_inventario, id_produto)
);

-- ============================================================ 5. NOTAS / OMIE

CREATE TABLE notas_entrada (
    id              bigserial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    chave_nfe       varchar(44),
    numero          varchar(20),
    serie           varchar(5),
    id_fornecedor   integer REFERENCES fornecedores(id),
    data_emissao    date,
    data_entrada    date,
    valor_produtos  numeric(18,2) NOT NULL DEFAULT 0,
    valor_frete     numeric(18,2) NOT NULL DEFAULT 0,
    valor_desconto  numeric(18,2) NOT NULL DEFAULT 0,
    valor_outros    numeric(18,2) NOT NULL DEFAULT 0,   -- IPI, ST
    valor_total     numeric(18,2) NOT NULL DEFAULT 0,
    origem          varchar(10) NOT NULL DEFAULT 'OMIE',  -- OMIE|MANUAL|XML
    id_omie         varchar(40),
    status          varchar(20) NOT NULL DEFAULT 'IMPORTADA', -- IMPORTADA|CONCILIADA|LANCADA|CANCELADA
    importada_em    timestamptz NOT NULL DEFAULT now(),
    lancada_em      timestamptz,
    lancada_por     integer REFERENCES usuarios(id)
);
-- Idempotência da importação é do BANCO, nunca do gatilho:
CREATE UNIQUE INDEX ux_nota_chave ON notas_entrada (chave_nfe) WHERE chave_nfe IS NOT NULL;
CREATE UNIQUE INDEX ux_nota_omie ON notas_entrada (id_omie) WHERE id_omie IS NOT NULL;

CREATE TABLE nota_itens (
    id              bigserial PRIMARY KEY,
    id_nota         bigint NOT NULL REFERENCES notas_entrada(id) ON DELETE CASCADE,
    seq             smallint NOT NULL,
    descricao_fornecedor varchar(200) NOT NULL,
    codigo_fornecedor varchar(60),
    ncm             varchar(10),
    quantidade      numeric(18,4) NOT NULL,
    um_nota         varchar(10),
    valor_unitario  numeric(18,6) NOT NULL,
    valor_desconto  numeric(18,2) NOT NULL DEFAULT 0,
    valor_frete_rateado numeric(18,2) NOT NULL DEFAULT 0,
    valor_outros_rateado numeric(18,2) NOT NULL DEFAULT 0,
    codigo_barras   varchar(20),                          -- EAN da NF: melhor chave natural
    lote_nf         varchar(40),
    validade_nf     date,
    id_produto      integer REFERENCES produtos(id),      -- NULL = pendência de de-para
    sugestao_produto integer REFERENCES produtos(id),     -- palpite por similaridade
    sugestao_score  numeric(5,2),                         -- 0..100; nunca vincula sozinho
    quantidade_convertida numeric(18,4),
    custo_aquisicao_unitario numeric(18,6),
    variacao_preco_pct numeric(7,2),                      -- vs. última compra do mesmo item
    UNIQUE (id_nota, seq)
);
CREATE INDEX ix_nota_itens_pendentes ON nota_itens (id_nota) WHERE id_produto IS NULL;

-- DE-PARA de sistemas externos (Omie e PDV Legal usam a mesma mesa).
-- Vincular uma vez ensina o sistema para sempre. N códigos externos → 1 produto:
-- o mesmo café pode ter código diferente em cada fornecedor.
CREATE TABLE codigos_externos (
    sistema         varchar(20) NOT NULL,       -- OMIE | PDV_LEGAL | FORNECEDOR
    codigo          varchar(60) NOT NULL,
    id_produto      integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    descricao_externa varchar(200),
    fator           numeric(18,6) NOT NULL DEFAULT 1,   -- CX do fornecedor → UM de estoque
    id_fornecedor   integer REFERENCES fornecedores(id),
    origem_vinculo  varchar(20) NOT NULL DEFAULT 'MANUAL', -- MANUAL|EAN|FORNECEDOR|CARGA
    confirmado_por  integer REFERENCES usuarios(id),
    confirmado_em   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sistema, codigo)
);
CREATE INDEX ix_codigos_externos_produto ON codigos_externos (id_produto);

CREATE TABLE omie_sync_log (
    id              bigserial PRIMARY KEY,
    servico         varchar(60) NOT NULL,
    chamada         varchar(60) NOT NULL,
    pagina          integer,
    registros       integer,
    status          varchar(20) NOT NULL,     -- OK|ERRO|VAZIO
    mensagem        text,
    iniciado_em     timestamptz NOT NULL DEFAULT now(),
    terminado_em    timestamptz
);

-- ============================================================ 6. VENDAS / CMV

CREATE TABLE vendas (
    id              bigserial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    data            date NOT NULL,
    hora            time,
    origem          varchar(20) NOT NULL DEFAULT 'PDV_LEGAL',  -- PDV_LEGAL|IFOOD|PLANILHA|MANUAL
    canal           varchar(20),                                -- SALAO|BALCAO|DELIVERY|EVENTO
    documento       varchar(40),                                -- nº do pedido/cupom no PDV
    id_externo      varchar(60),                                -- id do registro no PDV Legal
    mesa            varchar(20),
    valor_total     numeric(18,2) NOT NULL DEFAULT 0,
    desconto        numeric(18,2) NOT NULL DEFAULT 0,
    cancelada       boolean NOT NULL DEFAULT false,
    importada_em    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_unidade, origem, documento)
);

CREATE TABLE venda_itens (
    id              bigserial PRIMARY KEY,
    id_venda        bigint NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    codigo_pdv      varchar(60),                  -- código do item no PDV Legal
    descricao_pdv   varchar(200),
    id_produto      integer REFERENCES produtos(id),  -- NULL = prato ainda sem de-para
    quantidade      numeric(18,4) NOT NULL,
    valor_unitario  numeric(18,2) NOT NULL,
    valor_total     numeric(18,2) NOT NULL,
    custo_ficha_unitario numeric(18,6)     -- congelado na importação = CMV teórico
);
CREATE INDEX ix_venda_itens_produto ON venda_itens (id_produto);

CREATE TABLE cmv_fechamentos (
    id              serial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    competencia     date NOT NULL,          -- primeiro dia do mês
    estoque_inicial numeric(18,2) NOT NULL,
    compras         numeric(18,2) NOT NULL,
    estoque_final   numeric(18,2) NOT NULL,
    cmv_real        numeric(18,2) NOT NULL,
    cmv_teorico     numeric(18,2) NOT NULL,
    variancia       numeric(18,2) NOT NULL,
    receita         numeric(18,2) NOT NULL,
    food_cost_pct   numeric(6,3),
    status          varchar(20) NOT NULL DEFAULT 'ABERTO',   -- ABERTO|FECHADO
    fechado_por     integer REFERENCES usuarios(id),
    fechado_em      timestamptz,
    UNIQUE (id_unidade, competencia)
);
-- Movimento com data anterior a um fechamento FECHADO é recusado no service
-- (permissão cmv.reabrir libera, e a reabertura vai para a auditoria).
