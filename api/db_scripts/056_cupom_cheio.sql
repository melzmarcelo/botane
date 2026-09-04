-- O preço CHEIO do item e a política congelada no cupom.
--
-- 🔑 **Motivo** (04/09/2026, pedido do dono): "ao acessar este cupom, ver o
-- valor cheio e o valor do desconto" e um relatório do que cada pessoa
-- consumiu e quanto teve de desconto.
--
-- ⚠️ **O preço cheio estava sendo PERDIDO.** A política reescreve
-- `venda_itens.valor_unitario` antes de gravar (o custo no lugar do preço, ou o
-- preço com desconto), e o valor de tabela não sobrava em lugar nenhum. Sem ele
-- não há como dizer quanto foi o desconto: `cheio - cobrado` é a única conta
-- honesta, e ela precisa dos dois lados.
ALTER TABLE venda_itens
    ADD COLUMN IF NOT EXISTS valor_unitario_cheio numeric(18,2);

COMMENT ON COLUMN venda_itens.valor_unitario_cheio IS
    'Preço antes da política da pessoa. NULL = a política não tocou nesta linha, '
    'e aí o cheio É o valor_unitario.';

-- ⚠️ **A política vai CONGELADA no cupom, como o custo da ficha.** Ela mora no
-- cadastro da pessoa e muda: quem passa de 20% para 30% de desconto faria todo
-- relatório do passado ser reescrito, e a venda de março passaria a se explicar
-- por uma regra de setembro. O relatório tem de dizer o que valia NO DIA.
ALTER TABLE vendas
    ADD COLUMN IF NOT EXISTS cupom_base varchar(10),
    ADD COLUMN IF NOT EXISTS cupom_desconto_pct numeric(5,2);

COMMENT ON COLUMN vendas.cupom_base IS
    'VENDA ou CUSTO no momento do lançamento. NULL = sem pessoa, ou política que '
    'não mudava nada.';

-- O relatório por pessoa pergunta sempre "esta pessoa, neste período".
CREATE INDEX IF NOT EXISTS ix_venda_pessoa_data
    ON vendas (id_unidade, id_pessoa, data)
    WHERE id_pessoa IS NOT NULL;
