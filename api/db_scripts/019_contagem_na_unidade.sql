-- Botané 019 — a contagem guarda o que a pessoa CONTOU. Idempotente.
--
-- Quem conta o estoque conta na embalagem que está na mão: "três caixas", não
-- "trinta e seis unidades". Obrigar a converter de cabeça é onde o erro entra,
-- e o erro do inventário vira ajuste no razão.
--
-- `qtd_contada` continua sendo a verdade do sistema, na unidade de ESTOQUE —
-- é ela que o fechamento compara com o saldo. Ao lado dela ficam agora a
-- quantidade e a unidade como foram digitadas: sem isso, quem confere depois vê
-- 36 e não tem como saber que alguém contou 3 caixas de 12.
ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS qtd_informada numeric(18,4);
ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS um_informada varchar(6);
ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS contado_em timestamptz;
ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS contado_por integer REFERENCES usuarios(id);

COMMENT ON COLUMN inventario_itens.qtd_contada IS
    'Na unidade de ESTOQUE — é ela que o fechamento compara com o saldo.';
COMMENT ON COLUMN inventario_itens.qtd_informada IS
    'Como foi digitado, na unidade que a pessoa tinha na mão.';
