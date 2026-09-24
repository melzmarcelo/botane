-- Fidelidade: o cartão de visitas do Portal de Clientes.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"O cupom será por visita. Atualmente é
-- utilizado o LeadsFood, onde tem um QRCode na mesa, que o cliente lê e realiza o
-- check-in. Após 10, ele recebe um almoço grátis."* E: *"somente conta ponto de
-- segunda a sexta e pode consumir de segunda a sexta. Mas deixar configurado."*
-- Estudo em `docs/fidelidade-estudo.md`.
--
-- 🔑 **Um programa para a REDE**: o cadastro do cliente já é único por telefone
-- (087), então o cartão também é — visita na matriz e na filial contam juntas.
-- O que é POR LOJA é se ela participa: `reserva_config.fidelidade_ligada`.
-- Idempotente.

ALTER TABLE reserva_config
    ADD COLUMN IF NOT EXISTS fidelidade_ligada boolean NOT NULL DEFAULT false;

-- Uma linha só (id = 1), como `empresa`.
-- ⚠️ `dias_*` são ISO (1 = segunda … 7 = domingo), a convenção da casa desde
-- `parametros.fechamento_dia_semana` — e a de `reserva_horarios`.
CREATE TABLE IF NOT EXISTS fidelidade_config (
    id             smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    visitas        integer      NOT NULL DEFAULT 10 CHECK (visitas BETWEEN 1 AND 100),
    premio         varchar(120) NOT NULL DEFAULT 'Um almoço grátis',
    -- Dias para consumir o prêmio depois de completar o cartão.
    validade_dias  integer      NOT NULL DEFAULT 30 CHECK (validade_dias BETWEEN 1 AND 365),
    dias_pontua    smallint[]   NOT NULL DEFAULT '{1,2,3,4,5}',
    dias_consumo   smallint[]   NOT NULL DEFAULT '{1,2,3,4,5}',
    -- ⚠️ Check-in só com a casa ABERTA: o QR da mesa pode ser fotografado, e sem
    -- isto o cartão se completaria do sofá de casa.
    so_no_horario  boolean      NOT NULL DEFAULT true,
    -- 🔑 **O segredo impresso no QR.** Sem ele, qualquer um marca visita só
    -- abrindo o site. Gerar outro invalida os QR já impressos — é a saída se um
    -- vazar.
    token          varchar(32)  NOT NULL DEFAULT substr(md5(random()::text), 1, 12),
    -- O endereço que o QR abre. Na tabela, e não no `.env`, para a casa ajustar
    -- sem deploy (e para o teste local apontar para a porta 3200).
    site_url       varchar(200) NOT NULL DEFAULT 'https://reservas.botanedeliecafe.com.br',
    atualizado_em  timestamptz  NOT NULL DEFAULT now()
);
INSERT INTO fidelidade_config (id) VALUES (1) ON CONFLICT DO NOTHING;

-- O prêmio que o cartão completo gera. ⚠️ `premio`, `visitas` e `dias_consumo`
-- são CONGELADOS aqui: mudar a configuração amanhã não muda o que o cliente já
-- ganhou hoje.
CREATE TABLE IF NOT EXISTS fidelidade_premios (
    id             serial PRIMARY KEY,
    id_cliente     integer      NOT NULL REFERENCES reserva_clientes(id) ON DELETE CASCADE,
    -- Onde o cartão se completou.
    id_unidade     integer      NOT NULL REFERENCES unidades(id),
    codigo         varchar(8)   NOT NULL UNIQUE,
    premio         varchar(120) NOT NULL,
    visitas        integer      NOT NULL,
    dias_consumo   smallint[]   NOT NULL,
    emitido_em     timestamptz  NOT NULL DEFAULT now(),
    vence_em       date         NOT NULL,
    usado_em       timestamptz,
    usado_por      integer REFERENCES usuarios(id) ON DELETE SET NULL,
    id_unidade_uso integer REFERENCES unidades(id)
);
CREATE INDEX IF NOT EXISTS ix_fidelidade_premio_cliente ON fidelidade_premios (id_cliente);

-- Cada visita. 🔑 **UMA por cliente por dia, garantida pelo BANCO** (regra 8):
-- dois toques no QR, duas abas ou duas lojas no mesmo dia não viram duas visitas.
-- `id_premio` diz em que cartão a visita foi usada; nula = ainda conta para o atual.
CREATE TABLE IF NOT EXISTS fidelidade_checkins (
    id         bigserial PRIMARY KEY,
    id_cliente integer NOT NULL REFERENCES reserva_clientes(id) ON DELETE CASCADE,
    id_unidade integer NOT NULL REFERENCES unidades(id),
    data       date    NOT NULL,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    id_premio  integer REFERENCES fidelidade_premios(id) ON DELETE SET NULL,
    CONSTRAINT ux_fidelidade_um_por_dia UNIQUE (id_cliente, data)
);
CREATE INDEX IF NOT EXISTS ix_fidelidade_checkin_aberto
    ON fidelidade_checkins (id_cliente) WHERE id_premio IS NULL;

-- Permissões, no módulo do Portal de Clientes.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('fidelidade.operar',     'Portal de Clientes', 'Ver e entregar os prêmios da fidelidade', 690),
    ('fidelidade.configurar', 'Portal de Clientes', 'Configurar a fidelidade e imprimir os QR codes', 695)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ **Concedido AQUI**, como a 068 fez com `reservas.*`: a 002 re-semeia os
-- papéis de sistema ANTES desta, e o administrador ficaria sem as chaves até o
-- restart seguinte. O Salão entrega o prêmio no balcão; configurar é da gerência.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'fidelidade.%'
   AND (p.nome IN ('Administrador', 'Gerente')
        OR (p.nome = 'Salão' AND x.chave = 'fidelidade.operar'))
ON CONFLICT DO NOTHING;
