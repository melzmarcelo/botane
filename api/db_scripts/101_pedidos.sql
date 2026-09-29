-- Pedidos pelo catálogo do site: carrinho, pedido, confirmação pela casa.
--
-- 🔑 **Pedido do dono (28/09/2026):** *"o cliente poder realizar pedidos diretamente na tela
-- de catálogo … um carrinho de compras para enviar pedidos ao sistema … uma tela com pedidos,
-- um painel para acompanhar e aviso na tela inicial. O pagamento não será pelo sistema."*
-- Estudo e decisões em `docs/pedidos-estudo.md` (seção 0).
--
-- ⚠️ **O pedido NÃO vira venda** (decisão do dono): a casa lança no PDV, e a venda chega pela
-- busca de sempre. Aqui só se registra que foi lançado ("lançado no PDV" + número do cupom).
-- Idempotente.

-- A configuração é do CATÁLOGO (só origem PRODUTOS): "os catálogos que forem configurados
-- para aceitar pedidos, independente de loja".
CREATE TABLE IF NOT EXISTS catalogo_pedidos_config (
    id_catalogo          integer PRIMARY KEY REFERENCES catalogos(id) ON DELETE CASCADE,
    aceita               boolean NOT NULL DEFAULT false,
    retirada             boolean NOT NULL DEFAULT true,
    entrega              boolean NOT NULL DEFAULT false,
    taxa_entrega         numeric(12,2) NOT NULL DEFAULT 0 CHECK (taxa_entrega >= 0),
    pedido_minimo        numeric(12,2) NOT NULL DEFAULT 0 CHECK (pedido_minimo >= 0),
    -- Encomenda: o cliente escolhe dia e hora. Antecedência mínima em MINUTOS (o "30 min
    -- para ficar pronto") e máxima em DIAS (o bolo de sábado).
    antecedencia_min     integer NOT NULL DEFAULT 30 CHECK (antecedencia_min >= 0),
    antecedencia_max_dias integer NOT NULL DEFAULT 7 CHECK (antecedencia_max_dias BETWEEN 0 AND 60),
    -- As formas que o cliente pode escolher, e o texto da casa sobre o pagamento.
    pagamentos           text[] NOT NULL DEFAULT ARRAY['RETIRADA'],
    texto_pagamento      varchar(500),
    atualizado_em        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pedidos (
    id              serial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    -- 🔑 O número do BALCÃO ("pedido 128"), por loja. O id é interno.
    numero          integer NOT NULL,
    id_catalogo     integer REFERENCES catalogos(id) ON DELETE SET NULL,
    id_cliente      integer REFERENCES reserva_clientes(id) ON DELETE SET NULL,
    nome            varchar(120) NOT NULL,
    telefone        varchar(20) NOT NULL,
    modo            varchar(10) NOT NULL CHECK (modo IN ('RETIRADA', 'ENTREGA')),
    endereco        varchar(300),
    -- Dia e hora em que o cliente quer (retirar ou receber).
    para_quando     timestamptz NOT NULL,
    forma_pagamento varchar(10) NOT NULL CHECK (forma_pagamento IN ('RETIRADA', 'ENTREGA', 'WHATSAPP')),
    observacao      varchar(500),
    subtotal        numeric(12,2) NOT NULL DEFAULT 0,
    taxa_entrega    numeric(12,2) NOT NULL DEFAULT 0,
    total           numeric(12,2) NOT NULL DEFAULT 0,
    situacao        varchar(12) NOT NULL DEFAULT 'NOVO'
                    CHECK (situacao IN ('NOVO', 'CONFIRMADO', 'ENTREGUE', 'RECUSADO', 'CANCELADO')),
    motivo          varchar(300),
    -- Houve troca de produtos na confirmação (o original fica no histórico).
    alterado        boolean NOT NULL DEFAULT false,
    confirmado_em   timestamptz,
    confirmado_por  integer REFERENCES usuarios(id),
    -- 🔑 **"Lançado no PDV" é MARCA, não situação**: é a pergunta do painel ("confirmados que
    -- ainda não foram ao PDV"). O cupom, quando informado, liga o pedido à venda importada.
    lancado_pdv_em  timestamptz,
    lancado_por     integer REFERENCES usuarios(id),
    cupom_pdv       varchar(40),
    id_venda        bigint REFERENCES vendas(id) ON DELETE SET NULL,
    pago_em         timestamptz,
    pago_como       varchar(20),
    entregue_em     timestamptz,
    -- ⚠️ **Idempotência do envio** (regra 8): o site manda uma chave por carrinho; o toque
    -- duplo devolve o mesmo pedido em vez de criar outro.
    chave           varchar(60) NOT NULL,
    criado_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pedido_numero ON pedidos (id_unidade, numero);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pedido_chave ON pedidos (id_unidade, chave);
CREATE INDEX IF NOT EXISTS ix_pedido_situacao ON pedidos (id_unidade, situacao, para_quando);
CREATE INDEX IF NOT EXISTS ix_pedido_cliente ON pedidos (id_cliente, criado_em DESC);

CREATE TABLE IF NOT EXISTS pedido_itens (
    id              serial PRIMARY KEY,
    id_pedido       integer NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    id_produto      integer NOT NULL REFERENCES produtos(id),
    -- Nome e preço CONGELADOS no envio: mudar o preço amanhã não muda o pedido de hoje.
    nome            varchar(160) NOT NULL,
    quantidade      numeric(12,3) NOT NULL CHECK (quantidade > 0),
    preco_unitario  numeric(12,2) NOT NULL,
    total           numeric(12,2) NOT NULL,
    observacao      varchar(200),
    ordem           smallint NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_pedido_itens ON pedido_itens (id_pedido);

-- O que aconteceu com o pedido, e quem fez. Na troca, `detalhe` guarda os itens de antes.
CREATE TABLE IF NOT EXISTS pedido_historico (
    id          serial PRIMARY KEY,
    id_pedido   integer NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    acao        varchar(20) NOT NULL,
    de          varchar(12),
    para        varchar(12),
    detalhe     jsonb,
    id_usuario  integer REFERENCES usuarios(id),
    criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pedido_historico ON pedido_historico (id_pedido, criado_em);

-- O aviso de WhatsApp "pedido confirmado" aponta para o pedido (como o da reserva).
ALTER TABLE whatsapp_mensagens ADD COLUMN IF NOT EXISTS id_pedido integer
    REFERENCES pedidos(id) ON DELETE SET NULL;

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('pedidos.ver',    'Portal de Clientes', 'Ver os pedidos do site', 700),
    ('pedidos.operar', 'Portal de Clientes', 'Confirmar, trocar produtos, lançar no PDV e entregar pedidos', 705)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091): a 002 redefine os papéis de sistema antes desta. O Salão
-- atende o balcão e o telefone — é quem confirma e entrega.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'pedidos.%'
   AND p.nome IN ('Administrador', 'Gerente', 'Salão')
ON CONFLICT DO NOTHING;
