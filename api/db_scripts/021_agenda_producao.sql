-- Botané 021 — agenda de produção e o modo de produzir. Idempotente.
--
-- Duas coisas que o sistema tratava igual e não são:
--
-- * A **massa de pizza** é produzida, guardada e sai depois — para venda ou
--   para outra receita. Ela tem estoque, tem mínimo, e alguém precisa DECIDIR
--   produzir antes que falte. É o que a agenda serve.
-- * O **café passado** não fica em estoque: a venda e a produção são o mesmo
--   instante. Registrar produção à mão para cada café vendido seria trabalho
--   que ninguém faz — e sem registrar, o insumo nunca baixa.
--
-- `modo_producao` separa os dois:
--   PARA_ESTOQUE  produz, guarda, sai depois       (padrão)
--   NA_HORA       a venda produz e baixa no mesmo lançamento
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS modo_producao varchar(14)
    NOT NULL DEFAULT 'PARA_ESTOQUE';

DO $$ BEGIN
    ALTER TABLE produtos ADD CONSTRAINT ck_produto_modo_producao
        CHECK (modo_producao IN ('PARA_ESTOQUE', 'NA_HORA'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMENT ON COLUMN produtos.modo_producao IS
    'PARA_ESTOQUE: produz e guarda. NA_HORA: a venda produz e baixa junto.';

-- A agenda é o PLANO: o que se pretende produzir e quando. Não mexe no estoque
-- — quem mexe é a produção, quando a linha da agenda é confirmada.
CREATE TABLE IF NOT EXISTS producao_agenda (
    id            serial PRIMARY KEY,
    id_unidade    integer NOT NULL REFERENCES unidades(id),
    id_produto    integer NOT NULL REFERENCES produtos(id),
    id_local      integer REFERENCES locais_estoque(id),
    data_prevista date NOT NULL,
    quantidade    numeric(18,4) NOT NULL,
    -- PLANEJADA | PRODUZIDA | CANCELADA
    status        varchar(12) NOT NULL DEFAULT 'PLANEJADA',
    -- MANUAL: alguém agendou. ALERTA: nasceu de "abaixo do mínimo".
    origem        varchar(10) NOT NULL DEFAULT 'MANUAL',
    observacao    varchar(240),
    -- A produção que cumpriu esta linha, quando cumprida.
    id_producao   integer REFERENCES producoes(id),
    criado_em     timestamptz NOT NULL DEFAULT now(),
    criado_por    integer REFERENCES usuarios(id),
    produzido_em  timestamptz,
    produzido_por integer REFERENCES usuarios(id),
    CONSTRAINT ck_agenda_quantidade CHECK (quantidade > 0)
);
CREATE INDEX IF NOT EXISTS ix_agenda_dia
    ON producao_agenda (id_unidade, data_prevista, status);
CREATE INDEX IF NOT EXISTS ix_agenda_produto ON producao_agenda (id_produto, status);

-- Um produto não precisa de duas linhas planejadas para o mesmo dia: somam-se.
CREATE UNIQUE INDEX IF NOT EXISTS ux_agenda_planejada
    ON producao_agenda (id_unidade, id_produto, data_prevista)
    WHERE status = 'PLANEJADA';

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('producao.agenda', 'Estoque', 'Agenda de produção', 365)
ON CONFLICT (chave) DO NOTHING;

-- Quem já produz, agenda. Cozinha e gerência recebem a chave nova.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'producao.agenda' FROM papeis p
 WHERE EXISTS (SELECT 1 FROM papel_permissoes x
                WHERE x.id_papel = p.id AND x.chave = 'estoque.saidas')
ON CONFLICT DO NOTHING;
