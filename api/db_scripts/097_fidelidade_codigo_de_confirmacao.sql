-- Fidelidade: o método "código de confirmação" no caixa, e visita com mais de um selo.
--
-- 🔑 **Pedido do dono (27/09/2026):** *"hoje o método de pontuação é a leitura do QR code na
-- mesa. Na configuração da pontuação, vamos implementar o método código de confirmação: no
-- caixa tem um QR code, o cliente lê e aparece uma tela aguardando um código. Na tela do
-- nosso sistema aparecem os códigos e clientes; o usuário passa o código para o cliente
-- confirmar a visita. E na tela de códigos o usuário pode informar a quantidade de selos que
-- o cliente recebeu nesta visita, por padrão 1."*
--
-- ⚠️ **O código só existe na tela do CAIXA**, nunca na resposta ao celular: é ele que prova
-- que alguém da casa viu o cliente — por isso este método dispensa a localização.
-- Idempotente.

ALTER TABLE fidelidade_config
    ADD COLUMN IF NOT EXISTS metodo varchar(20) NOT NULL DEFAULT 'QRCODE_MESA';
ALTER TABLE fidelidade_config
    ADD COLUMN IF NOT EXISTS codigo_validade_min integer NOT NULL DEFAULT 30;
DO $$ BEGIN
    ALTER TABLE fidelidade_config ADD CONSTRAINT ck_fidelidade_metodo
        CHECK (metodo IN ('QRCODE_MESA', 'CODIGO_CAIXA'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE fidelidade_config ADD CONSTRAINT ck_fidelidade_codigo_validade
        CHECK (codigo_validade_min BETWEEN 2 AND 720);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 🔑 **Uma visita pode valer mais de um SELO.** `parte` existe para a SOBRA: a visita de 3
-- selos que completa um cartão com 1 é repartida — 1 vai para o prêmio, 2 ficam para o
-- cartão seguinte, numa linha "parte 1" do mesmo dia. A visita continua sendo UMA por dia
-- (a `parte 0`), e é o índice único que garante isso (regra 8).
ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS selos integer NOT NULL DEFAULT 1;
ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS parte smallint NOT NULL DEFAULT 0;
DO $$ BEGIN
    ALTER TABLE fidelidade_checkins ADD CONSTRAINT ck_fidelidade_selos CHECK (selos BETWEEN 1 AND 100);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE fidelidade_checkins DROP CONSTRAINT IF EXISTS ux_fidelidade_um_por_dia;
CREATE UNIQUE INDEX IF NOT EXISTS ux_fidelidade_visita
    ON fidelidade_checkins (id_cliente, data, parte);

-- O pedido de código: nasce quando o cliente lê o QR do caixa, morre confirmado,
-- cancelado ou vencido.
CREATE TABLE IF NOT EXISTS fidelidade_solicitacoes (
    id            serial PRIMARY KEY,
    id_cliente    integer NOT NULL REFERENCES reserva_clientes(id) ON DELETE CASCADE,
    id_unidade    integer NOT NULL REFERENCES unidades(id),
    codigo        varchar(6) NOT NULL,
    selos         integer NOT NULL DEFAULT 1 CHECK (selos BETWEEN 1 AND 100),
    status        varchar(12) NOT NULL DEFAULT 'PENDENTE'
                  CHECK (status IN ('PENDENTE', 'CONFIRMADA', 'CANCELADA', 'VENCIDA')),
    criada_em     timestamptz NOT NULL DEFAULT now(),
    expira_em     timestamptz NOT NULL,
    tentativas    integer NOT NULL DEFAULT 0,
    confirmada_em timestamptz,
    -- Quem mexeu nos selos ou cancelou, pelo caixa.
    atendido_por  integer REFERENCES usuarios(id) ON DELETE SET NULL,
    id_checkin    bigint REFERENCES fidelidade_checkins(id) ON DELETE SET NULL
);
-- ⚠️ UM pedido pendente por cliente: ler o QR de novo devolve o MESMO código, em vez de
-- encher a tela do caixa de pedidos repetidos.
CREATE UNIQUE INDEX IF NOT EXISTS ux_fidelidade_solicitacao_pendente
    ON fidelidade_solicitacoes (id_cliente) WHERE status = 'PENDENTE';
CREATE INDEX IF NOT EXISTS ix_fidelidade_solicitacao_loja
    ON fidelidade_solicitacoes (id_unidade, status, criada_em);
