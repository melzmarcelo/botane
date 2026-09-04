-- Período de consumo: o ciclo que se abre, acumula e se fecha no pagamento.
--
-- 🔑 **Pedido do dono (04/09/2026):** "o Administrador vai e abre um periodo de
-- X dias, de tal dia a tal dia. ai todos os consumos vão para este periodo. ai
-- quando for realizado o pagamento e fecha este periodo. e estes valores em
-- aberto podem ser consultados pelo usuario".

CREATE TABLE IF NOT EXISTS consumo_periodos (
    id                serial PRIMARY KEY,
    id_unidade        integer NOT NULL REFERENCES unidades(id),
    -- Opcional: "Setembro/1ª quinzena". O par de datas já identifica.
    nome              varchar(60),
    inicio            date NOT NULL,
    fim               date NOT NULL,
    status            varchar(10) NOT NULL DEFAULT 'ABERTO'
                      CHECK (status IN ('ABERTO', 'FECHADO')),
    aberto_em         timestamptz NOT NULL DEFAULT now(),
    id_usuario_abriu  integer REFERENCES usuarios(id),
    fechado_em        timestamptz,
    id_usuario_fechou integer REFERENCES usuarios(id),
    observacao        text,
    CONSTRAINT ck_consumo_periodo_ordem CHECK (fim >= inicio)
);

-- ⚠️ **Um período aberto por loja, e a garantia é do BANCO.** A checagem em
-- código perde a corrida entre dois cliques, e o efeito seria dois ciclos
-- disputando o mesmo consumo — cada um fechando metade da dívida.
CREATE UNIQUE INDEX IF NOT EXISTS ux_consumo_periodo_aberto
    ON consumo_periodos (id_unidade) WHERE status = 'ABERTO';

CREATE INDEX IF NOT EXISTS ix_consumo_periodo_unidade
    ON consumo_periodos (id_unidade, fim DESC);

-- 🔑 **O carimbo é o que define "em aberto".** Venda com pessoa e SEM período é
-- consumo ainda não pago; com período, já foi fechado e cobrado.
--
-- ⚠️ **Deliberadamente NÃO se deriva das datas do período.** Fosse por data, um
-- período com as datas corrigidas depois moveria dívida já paga de volta para
-- aberto — e o saldo de quem já acertou mudaria sozinho. O carimbo é um fato do
-- fechamento, e fatos não se recalculam.
ALTER TABLE vendas
    ADD COLUMN IF NOT EXISTS id_consumo_periodo integer REFERENCES consumo_periodos(id);

COMMENT ON COLUMN vendas.id_consumo_periodo IS
    'Período em que este consumo foi fechado. NULL = ainda em aberto.';

-- O saldo de uma pessoa é sempre "as minhas vendas ainda sem período".
CREATE INDEX IF NOT EXISTS ix_venda_consumo_aberto
    ON vendas (id_unidade, id_pessoa)
    WHERE id_pessoa IS NOT NULL AND id_consumo_periodo IS NULL;

-- 🔑 **O recibo do fechamento, congelado.** Os totais são recalculáveis a
-- partir das vendas carimbadas — mas só enquanto ninguém apagar, cancelar ou
-- corrigir uma delas. O que foi cobrado de cada pessoa naquele dia é um fato, e
-- precisa continuar respondível anos depois, do jeito que foi cobrado.
CREATE TABLE IF NOT EXISTS consumo_periodo_pessoas (
    id          bigserial PRIMARY KEY,
    id_periodo  integer NOT NULL REFERENCES consumo_periodos(id) ON DELETE CASCADE,
    id_pessoa   integer NOT NULL REFERENCES fornecedores(id),
    cupons      integer NOT NULL DEFAULT 0,
    itens       integer NOT NULL DEFAULT 0,
    total_cheio numeric(18,2) NOT NULL DEFAULT 0,
    desconto    numeric(18,2) NOT NULL DEFAULT 0,
    total       numeric(18,2) NOT NULL DEFAULT 0,
    UNIQUE (id_periodo, id_pessoa)
);

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('consumo.periodos', 'CMV', 'Abrir e fechar período de consumo', 550)
ON CONFLICT (chave) DO NOTHING;

-- ⚠️ **Quem já fecha o CMV passa a fechar o consumo.** Sem esta linha o recurso
-- nasceria invisível para todo mundo menos o administrador, e ninguém saberia
-- por quê — é o mesmo cuidado do `estoque.inventario_criar`.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'consumo.periodos'
  FROM papel_permissoes pp
 WHERE pp.chave = 'cmv.fechamento'
ON CONFLICT DO NOTHING;
