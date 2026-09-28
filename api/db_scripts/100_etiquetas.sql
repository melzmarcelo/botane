-- Etiquetas de validade: o que se PRODUZ e o que se ABRE para consumo.
--
-- 🔑 **Pedido do dono (28/09/2026):** *"um novo módulo, o de Etiquetas: etiquetas para
-- controlar validade, quantidade e demais coisas úteis, em produtos produzidos e abertos
-- para consumo. Algo integrado, que controlamos de forma simples e rápida."*
-- Estudo em `docs/etiquetas-estudo.md`; regra em `api/services/etiquetas.py`.
-- Idempotente.

-- 🔑 **A validade depende do QUE aconteceu e de COMO se guarda.** O mesmo molho dura
-- 3 dias refrigerado e 60 congelado; o creme de leite, 3 dias depois de aberto. Um número
-- só (`produtos.validade_dias`) não diz isso — ele continua valendo como reserva para a
-- produção de quem não tem regra aqui.
CREATE TABLE IF NOT EXISTS produto_validades (
    id           serial PRIMARY KEY,
    id_produto   integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    evento       varchar(16) NOT NULL
                 CHECK (evento IN ('PRODUCAO', 'ABERTURA', 'DESCONGELAMENTO')),
    conservacao  varchar(12) NOT NULL
                 CHECK (conservacao IN ('REFRIGERADO', 'CONGELADO', 'AMBIENTE')),
    -- ⚠️ Em HORAS ou DIAS: arroz e maionese da casa vencem no meio do dia.
    prazo        integer NOT NULL CHECK (prazo > 0),
    unidade      varchar(5) NOT NULL DEFAULT 'DIAS' CHECK (unidade IN ('HORAS', 'DIAS')),
    -- A conservação que a tela já traz marcada para este evento.
    padrao       boolean NOT NULL DEFAULT false,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_produto, evento, conservacao)
);

-- O modelo da etiqueta, por LOJA: cada casa tem a sua impressora e o seu rolo.
CREATE TABLE IF NOT EXISTS etiqueta_config (
    id_unidade          integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    tamanho             varchar(8) NOT NULL DEFAULT '60x40'
                        CHECK (tamanho IN ('40x40', '50x30', '60x40', '100x50', 'A4')),
    mostrar_alergenos   boolean NOT NULL DEFAULT true,
    mostrar_lote        boolean NOT NULL DEFAULT true,
    mostrar_quantidade  boolean NOT NULL DEFAULT true,
    mostrar_qr          boolean NOT NULL DEFAULT true,
    texto_extra         varchar(80),
    atualizado_em       timestamptz NOT NULL DEFAULT now()
);

-- 🔑 **A etiqueta é um REGISTRO, não só um papel**: tem código (o do QR), situação e dono.
-- É o que deixa perguntar "o que vence hoje" sem abrir a câmara fria.
CREATE TABLE IF NOT EXISTS etiquetas (
    id                  bigserial PRIMARY KEY,
    -- Curto e sem letras que se confundem: é digitado quando o QR não lê.
    codigo              varchar(10) NOT NULL,
    id_unidade          integer NOT NULL REFERENCES unidades(id),
    id_produto          integer NOT NULL REFERENCES produtos(id),
    evento              varchar(16) NOT NULL
                        CHECK (evento IN ('PRODUCAO', 'ABERTURA', 'DESCONGELAMENTO')),
    conservacao         varchar(12) NOT NULL
                        CHECK (conservacao IN ('REFRIGERADO', 'CONGELADO', 'AMBIENTE')),
    feito_em            timestamptz NOT NULL DEFAULT now(),
    -- ⚠️ Data E hora (ver `produto_validades.unidade`).
    vence_em            timestamptz NOT NULL,
    -- Na unidade de ESTOQUE do produto: é o que o descarte lança como perda.
    quantidade          numeric(14,4),
    um                  varchar(10),
    id_producao         integer REFERENCES producoes(id) ON DELETE SET NULL,
    id_local            integer REFERENCES locais_estoque(id),
    -- O lote da produção (o mesmo de `estoque_lotes`) ou o do fabricante, na abertura.
    lote                varchar(40),
    validade_lote       date,
    validade_fabricante date,
    -- A etiqueta que esta substituiu (descongelamento, reetiquetagem).
    id_origem           bigint REFERENCES etiquetas(id),
    responsavel         varchar(120) NOT NULL,
    id_usuario          integer REFERENCES usuarios(id),
    observacao          varchar(200),
    status              varchar(12) NOT NULL DEFAULT 'ATIVA'
                        CHECK (status IN ('ATIVA', 'USADA', 'DESCARTADA', 'SUBSTITUIDA')),
    baixada_em          timestamptz,
    baixada_por         integer REFERENCES usuarios(id),
    motivo              varchar(200),
    -- ⚠️ **Descartar é PERDA no razão** (append-only, regra 1): o movimento fica aqui.
    id_movimento        bigint REFERENCES estoque_movimentos(id),
    impressoes          integer NOT NULL DEFAULT 1,
    criado_em           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_etiqueta_codigo ON etiquetas (codigo);
CREATE INDEX IF NOT EXISTS ix_etiqueta_ativas ON etiquetas (id_unidade, vence_em)
    WHERE status = 'ATIVA';
CREATE INDEX IF NOT EXISTS ix_etiqueta_producao ON etiquetas (id_producao);
CREATE INDEX IF NOT EXISTS ix_etiqueta_produto ON etiquetas (id_produto, criado_em DESC);

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('etiquetas.imprimir',    'Etiquetas', 'Imprimir etiquetas e dar baixa ("usei tudo")', 710),
    ('etiquetas.descartar',   'Etiquetas', 'Descartar pela etiqueta (lança a perda)', 715),
    ('etiquetas.configurar',  'Etiquetas', 'Validades dos produtos e modelo da etiqueta', 720)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091): a 002 redefine os papéis de sistema antes desta.
-- Quem produz e quem abre embalagem imprime; descartar é quem já aponta perda.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'etiquetas.%'
   AND (p.nome IN ('Administrador', 'Gerente')
        OR (p.nome IN ('Cozinha', 'Conferente / Estoque')
            AND x.chave IN ('etiquetas.imprimir', 'etiquetas.descartar'))
        OR (p.nome = 'Salão' AND x.chave = 'etiquetas.imprimir'))
ON CONFLICT DO NOTHING;
