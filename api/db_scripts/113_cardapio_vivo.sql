-- 113 — Cardápio Vivo, fase 1: acesso por mesa, feed, modo VITRINE, cadastro e eventos.
-- Idempotente. Estudo e decisões do dono em `docs/cardapio-vivo-estudo.md`.
--
-- 🔑 **Nada de cadastro novo de prato.** O feed é o catálogo de origem PRODUTOS (084)
-- com o produto que já existe (foto 083, nome de vitrine 085, preço da loja). Esta
-- migração só acrescenta o que faltava a cada um, no DONO de cada informação:
-- vídeo e restrições no PRODUTO (o mesmo prato em várias listas tem o mesmo vídeo),
-- destaque e esgotado no ITEM (é decisão daquele cardápio), dia e horário na SEÇÃO.

-- ---------------------------------------------------------------- produto
ALTER TABLE produtos
    ADD COLUMN IF NOT EXISTS video_url       varchar(300),
    ADD COLUMN IF NOT EXISTS video_capa_url  varchar(300),
    ADD COLUMN IF NOT EXISTS video_nome      varchar(255),
    ADD COLUMN IF NOT EXISTS video_bytes     integer,
    ADD COLUMN IF NOT EXISTS video_segundos  numeric(5,2),
    ADD COLUMN IF NOT EXISTS video_em        timestamptz,
    -- ⚠️ Lista FIXA (decisão do dono, 14/10/2026). O CHECK é quem garante; a tela
    -- lê o vocabulário do servidor.
    ADD COLUMN IF NOT EXISTS restricoes      text[] NOT NULL DEFAULT '{}';

ALTER TABLE produtos DROP CONSTRAINT IF EXISTS ck_produto_restricoes;
ALTER TABLE produtos ADD CONSTRAINT ck_produto_restricoes
    CHECK (restricoes <@ ARRAY['VEGANO', 'SEM_GLUTEN', 'SEM_LACTOSE']::text[]);

-- ---------------------------------------------------------------- item do catálogo
ALTER TABLE catalogo_itens
    ADD COLUMN IF NOT EXISTS destaque boolean NOT NULL DEFAULT false,
    -- ⚠️ Revoga a decisão 6 de 28/09 ("não haverá pausa"): o item esgotado continua
    -- no cardápio, MARCADO, e não pode ser adicionado. Esconder é opção da loja.
    ADD COLUMN IF NOT EXISTS esgotado boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------- seção: quando aparece
-- 🔑 `dias` é ISO (1 = segunda … 7 = domingo), como `reserva_horarios`. Nulo = todos.
-- A faixa pode virar a meia-noite (de 22:00 até 02:00). `horario_especial` faz a seção
-- aparecer também nos dias de `reserva_dias_especiais` — o "feriado" da casa.
ALTER TABLE catalogo_categorias
    ADD COLUMN IF NOT EXISTS dias             smallint[],
    ADD COLUMN IF NOT EXISTS hora_de          time,
    ADD COLUMN IF NOT EXISTS hora_ate         time,
    ADD COLUMN IF NOT EXISTS horario_especial boolean NOT NULL DEFAULT false;
ALTER TABLE catalogo_subcategorias
    ADD COLUMN IF NOT EXISTS dias             smallint[],
    ADD COLUMN IF NOT EXISTS hora_de          time,
    ADD COLUMN IF NOT EXISTS hora_ate         time,
    ADD COLUMN IF NOT EXISTS horario_especial boolean NOT NULL DEFAULT false;

ALTER TABLE catalogo_categorias DROP CONSTRAINT IF EXISTS ck_categoria_exibicao;
ALTER TABLE catalogo_categorias ADD CONSTRAINT ck_categoria_exibicao CHECK (
    (dias IS NULL OR (dias <@ ARRAY[1,2,3,4,5,6,7]::smallint[] AND cardinality(dias) > 0))
    AND ((hora_de IS NULL) = (hora_ate IS NULL)) AND (hora_de IS NULL OR hora_de <> hora_ate));
ALTER TABLE catalogo_subcategorias DROP CONSTRAINT IF EXISTS ck_subcategoria_exibicao;
ALTER TABLE catalogo_subcategorias ADD CONSTRAINT ck_subcategoria_exibicao CHECK (
    (dias IS NULL OR (dias <@ ARRAY[1,2,3,4,5,6,7]::smallint[] AND cardinality(dias) > 0))
    AND ((hora_de IS NULL) = (hora_ate IS NULL)) AND (hora_de IS NULL OR hora_de <> hora_ate));

-- ---------------------------------------------------------------- mesa: o token do QR
-- 🔑 **A URL da mesa leva um SEGREDO, não o número** (decisão do dono): com `/c/1/5`,
-- qualquer um em casa mandaria pedido para a mesa 5. Gerar de novo invalida o impresso.
-- ⚠️ **DEFAULT na coluna, não só o UPDATE**: o UPDATE cobre as mesas de hoje; a mesa
-- criada amanhã pelo cadastro do salão nasceria sem token e sem QR (a suíte pegou).
ALTER TABLE mesas ADD COLUMN IF NOT EXISTS token varchar(24);
ALTER TABLE mesas ALTER COLUMN token
    SET DEFAULT substr(md5(random()::text || clock_timestamp()::text), 1, 16);
UPDATE mesas SET token = substr(md5(random()::text || clock_timestamp()::text || id::text), 1, 16)
 WHERE token IS NULL;
ALTER TABLE mesas ALTER COLUMN token SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_mesa_token ON mesas (token);

-- ---------------------------------------------------------------- configuração por loja
CREATE TABLE IF NOT EXISTS cardapio_config (
    id_unidade        integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    -- O catálogo que a mesa abre (origem PRODUTOS). Nulo = cardápio vivo desligado.
    id_catalogo       integer REFERENCES catalogos(id) ON DELETE SET NULL,
    modo              varchar(8) NOT NULL DEFAULT 'VITRINE' CHECK (modo IN ('VITRINE', 'PEDIDO')),
    exige_confirmacao boolean NOT NULL DEFAULT true,
    -- Faixa em que o pedido pela mesa é aceito; fora dela cai para VITRINE.
    pedido_hora_de    time,
    pedido_hora_ate   time,
    chamar_garcom     boolean NOT NULL DEFAULT false,
    esconder_esgotado boolean NOT NULL DEFAULT false,
    -- Identidade visual da loja no feed. Nulo = a da casa.
    cor_principal     varchar(7) CHECK (cor_principal ~ '^#[0-9a-fA-F]{6}$'),
    cor_fundo         varchar(7) CHECK (cor_fundo ~ '^#[0-9a-fA-F]{6}$'),
    fonte             varchar(20) NOT NULL DEFAULT 'NEWSREADER',
    logo_url          varchar(300),
    -- LGPD: quantos meses o evento BRUTO fica; o agregado fica sempre.
    retencao_meses    smallint NOT NULL DEFAULT 13 CHECK (retencao_meses BETWEEN 1 AND 60),
    atualizado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_por    integer REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT ck_cardapio_faixa CHECK ((pedido_hora_de IS NULL) = (pedido_hora_ate IS NULL))
);

-- 🔑 **A exceção mais específica vence**: mesa → salão → loja. Campo nulo aqui herda.
CREATE TABLE IF NOT EXISTS cardapio_excecoes (
    id                serial PRIMARY KEY,
    id_unidade        integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_salao          integer REFERENCES saloes(id) ON DELETE CASCADE,
    id_mesa           integer REFERENCES mesas(id) ON DELETE CASCADE,
    modo              varchar(8) CHECK (modo IN ('VITRINE', 'PEDIDO')),
    exige_confirmacao boolean,
    pedido_hora_de    time,
    pedido_hora_ate   time,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_excecao_alvo CHECK ((id_salao IS NULL) <> (id_mesa IS NULL)),
    CONSTRAINT ck_excecao_faixa CHECK ((pedido_hora_de IS NULL) = (pedido_hora_ate IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_excecao_salao ON cardapio_excecoes (id_salao) WHERE id_salao IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_excecao_mesa ON cardapio_excecoes (id_mesa) WHERE id_mesa IS NOT NULL;

-- ---------------------------------------------------------------- adicionais do produto
-- 🔑 No PRODUTO, como o vídeo: o mesmo prato em duas listas tem os mesmos adicionais.
CREATE TABLE IF NOT EXISTS produto_adicionais_grupos (
    id         serial PRIMARY KEY,
    id_produto integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    nome       varchar(80) NOT NULL,
    minimo     smallint NOT NULL DEFAULT 0 CHECK (minimo >= 0),
    maximo     smallint NOT NULL DEFAULT 1 CHECK (maximo >= 1),
    ordem      smallint NOT NULL DEFAULT 0,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_adicional_faixa CHECK (minimo <= maximo)
);
CREATE INDEX IF NOT EXISTS ix_adicional_grupo_produto ON produto_adicionais_grupos (id_produto, ordem);

-- 🔑 A opção PODE apontar para um produto (decisão do dono): aí o preço sai da cascata
-- da loja e o custo da ficha dele. Sem produto, é texto + preço (nulo = sem acréscimo).
CREATE TABLE IF NOT EXISTS produto_adicionais_opcoes (
    id             serial PRIMARY KEY,
    id_grupo       integer NOT NULL REFERENCES produto_adicionais_grupos(id) ON DELETE CASCADE,
    nome           varchar(80) NOT NULL,
    preco          numeric(12,2) CHECK (preco >= 0),
    id_produto_ref integer REFERENCES produtos(id) ON DELETE SET NULL,
    ordem          smallint NOT NULL DEFAULT 0,
    ativo          boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_adicional_opcao_grupo ON produto_adicionais_opcoes (id_grupo, ordem);

-- ---------------------------------------------------------------- atenção (eventos)
-- ⚠️ **Sem dado pessoal.** O id da sessão é aleatório, gerado no navegador; o telefone
-- da identificação opcional (fase 2) NUNCA entra aqui.
CREATE TABLE IF NOT EXISTS cardapio_sessoes (
    id          uuid PRIMARY KEY,
    id_unidade  integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_mesa     integer REFERENCES mesas(id) ON DELETE SET NULL,
    modo        varchar(8) NOT NULL,
    dispositivo varchar(10) NOT NULL DEFAULT 'OUTRO',
    idioma      varchar(2),
    inicio      timestamptz NOT NULL DEFAULT now(),
    ultimo      timestamptz NOT NULL DEFAULT now(),
    eventos     integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_cardapio_sessao_loja ON cardapio_sessoes (id_unidade, inicio);

-- 🔑 **Append-only**, como o razão: o que o cliente fez não se corrige.
CREATE TABLE IF NOT EXISTS cardapio_eventos (
    id           bigserial PRIMARY KEY,
    id_sessao    uuid NOT NULL REFERENCES cardapio_sessoes(id) ON DELETE CASCADE,
    id_unidade   integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_mesa      integer REFERENCES mesas(id) ON DELETE SET NULL,
    tipo         varchar(20) NOT NULL CHECK (tipo IN (
                     'abriu_cardapio', 'viu_item', 'tocou_categoria', 'abriu_detalhe',
                     'adicionou', 'removeu', 'enviou_pedido', 'chamou_garcom',
                     'pediu_conta', 'saiu')),
    id_item      integer,
    id_produto   integer REFERENCES produtos(id) ON DELETE SET NULL,
    id_categoria integer,
    modo         varchar(8) NOT NULL,
    midia        varchar(7) CHECK (midia IN ('VIDEO', 'FOTO', 'NENHUMA')),
    duracao_ms   integer CHECK (duracao_ms >= 0),
    quando       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cardapio_evento_loja ON cardapio_eventos (id_unidade, quando);
CREATE INDEX IF NOT EXISTS ix_cardapio_evento_produto ON cardapio_eventos (id_produto, quando);
CREATE INDEX IF NOT EXISTS ix_cardapio_evento_sessao ON cardapio_eventos (id_sessao);

-- 🔑 **O que sobra depois da retenção.** Um dia, uma loja, um produto, uma mesa, uma hora
-- e uma mídia por linha — o painel lê daqui o que já saiu do bruto.
CREATE TABLE IF NOT EXISTS cardapio_agregados_dia (
    dia          date     NOT NULL,
    id_unidade   integer  NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_produto   integer  NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_mesa      integer  NOT NULL DEFAULT 0,
    hora         smallint NOT NULL,
    midia        varchar(7) NOT NULL,
    visualizacoes integer NOT NULL DEFAULT 0,
    atencao_ms   bigint   NOT NULL DEFAULT 0,
    detalhes     integer  NOT NULL DEFAULT 0,
    adicoes      integer  NOT NULL DEFAULT 0,
    remocoes     integer  NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, id_unidade, id_produto, id_mesa, hora, midia)
);
