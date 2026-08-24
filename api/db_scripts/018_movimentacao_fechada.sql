-- Botané 018 — a movimentação de estoque do mês, produto a produto,
-- congelada no fechamento. Idempotente.
--
-- O CMV do mês é uma linha só: estoque inicial + compras − estoque final. Ela
-- diz o RESULTADO e não diz de onde veio. Quem precisa conferir — ou explicar
-- ao contador — quer a conta por produto: o que tinha, o que entrou, o que
-- saiu, o que sobrou.
--
-- Enquanto o mês está aberto isso se calcula do razão. Depois de fechado, não:
-- o fechamento congela a linha de cada produto aqui. É a mesma promessa do
-- fechamento do CMV — o número que foi levado ao dono não muda depois.
CREATE TABLE IF NOT EXISTS cmv_movimentacao (
    id                serial PRIMARY KEY,
    id_fechamento     integer NOT NULL REFERENCES cmv_fechamentos(id) ON DELETE CASCADE,
    id_produto        integer NOT NULL REFERENCES produtos(id),
    -- Nome e código ficam GRAVADOS: renomear o produto depois não pode
    -- reescrever o relatório de um mês fechado.
    codigo            varchar(20),
    produto           varchar(200) NOT NULL,
    um_estoque        varchar(6),
    categoria         varchar(120),
    setor             varchar(120),
    qtd_inicial       numeric(18,4) NOT NULL DEFAULT 0,
    valor_inicial     numeric(18,2) NOT NULL DEFAULT 0,
    qtd_entradas      numeric(18,4) NOT NULL DEFAULT 0,
    valor_entradas    numeric(18,2) NOT NULL DEFAULT 0,
    qtd_saidas        numeric(18,4) NOT NULL DEFAULT 0,
    valor_saidas      numeric(18,2) NOT NULL DEFAULT 0,
    qtd_final         numeric(18,4) NOT NULL DEFAULT 0,
    valor_final       numeric(18,2) NOT NULL DEFAULT 0,
    custo_medio_final numeric(18,6) NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cmv_movimentacao
    ON cmv_movimentacao (id_fechamento, id_produto);
CREATE INDEX IF NOT EXISTS ix_cmv_movimentacao_produto ON cmv_movimentacao (id_produto);
